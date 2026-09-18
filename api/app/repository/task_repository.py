"""タスク(tasks テーブル)へのデータアクセス層。

各関数はトランザクションのcommit/rollbackを行わない。呼び出し元のservice層が
同一セッションのcommitを担う。楽観ロック競合(SQLSTATE `P0005`)・非アクティブな
担当者への割当(`P0006`)は`_raise_task_constraint_error`で業務例外に変換して送出する。
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_backend_settings
from app.core.exceptions import AssigneeInactiveError, TaskConflictError
from app.models.task import Task


@dataclass(frozen=True)
class TaskWithProjectStatus:
	"""fn_get_task/fn_get_project_board/fn_list_tasks の1行分（タスク本体＋project_is_active）。"""

	task: Task
	project_is_active: bool | None
	comment_count: int = 0


class TaskListResult(list[TaskWithProjectStatus]):
	"""タスク一覧に、全体件数(`total_count`)を付加したリスト。"""

	def __init__(self, items: list[TaskWithProjectStatus], total_count: int) -> None:
		"""タスク一覧と全体件数からリストを構築する。

		Args:
			items: タスク一覧の各要素。
			total_count: ページング前の全体件数。
		"""
		super().__init__(items)
		self.total_count = total_count


def _build_task(row: RowMapping) -> Task:
	"""クエリ結果の1行からTaskモデルを組み立てる。

	Args:
		row: `(task).*`形式で選択されたタスク列を含む1行。

	Returns:
		組み立てたTaskインスタンス。
	"""
	return Task(
		id=row["id"],
		project_id=row["project_id"],
		title=row["title"],
		description=row["description"],
		status=row["status"],
		assignee_id=row["assignee_id"],
		created_by=row["created_by"],
		position=row["position"],
		version=row["version"],
		due_at=row["due_at"],
		is_active=row["is_active"],
		created_at=row["created_at"],
		updated_at=row["updated_at"],
	)


def _build_task_with_project_status(row: RowMapping) -> TaskWithProjectStatus:
	"""クエリ結果の1行から、所属プロジェクトの有効状態・コメント数付きのタスクを組み立てる。

	Args:
		row: タスク列に加え`project_is_active`・`comment_count`を含む1行。
			`comment_count`が含まれない場合は0として扱う。

	Returns:
		組み立てたTaskWithProjectStatusインスタンス。
	"""
	return TaskWithProjectStatus(
		task=_build_task(row),
		project_is_active=row["project_is_active"],
		comment_count=int(row.get("comment_count", 0)),
	)


def _app_day_bounds_utc(now: datetime | None = None, app_timezone: str | None = None) -> tuple[datetime, datetime]:
	"""アプリケーションのタイムゾーンにおける「当日」の開始・終了時刻をUTCで算出する。

	タスクの期限(due_at)判定などで「アプリ設定タイムゾーンでの今日」の範囲をDB関数/
	プロシージャへ渡すために使用する。

	Args:
		now: 基準時刻。指定しない場合はUTCの現在時刻を用いる。
		app_timezone: 基準とするタイムゾーン名。指定しない場合は
			`get_backend_settings().app_timezone`を用いる。

	Returns:
		(当日開始時刻のUTC表現, 翌日開始時刻のUTC表現)のタプル。
	"""
	zone = ZoneInfo(app_timezone or get_backend_settings().app_timezone)
	local_now = (now or datetime.now(UTC)).astimezone(zone)
	local_date = local_now.date()
	start_local = datetime.combine(local_date, time.min, tzinfo=zone)
	end_local = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=zone)
	return start_local.astimezone(UTC), end_local.astimezone(UTC)


async def create(
	db: AsyncSession,
	project_id: uuid.UUID | None,
	created_by: uuid.UUID,
	assignee_id: uuid.UUID | None,
	title: str,
	body: str | None,
	status: str,
	due_at: datetime | None,
	position: int | None,
) -> uuid.UUID:
	"""タスクを新規作成する。

	ストアドプロシージャ `sp_create_task` を呼び出し、tasks テーブルに1行挿入する
	副作用を持つ。本関数自体はcommitを行わず、呼び出し元のservice層が同一セッションで
	commitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		project_id: 所属するプロジェクトID。個人タスクの場合はNone。
		created_by: 作成者のユーザーID。
		assignee_id: 担当者のユーザーID。未割当の場合はNone。
		title: タスクタイトル。
		body: タスク本文。指定しない場合はNone。
		status: タスクのステータス。
		due_at: 期限日時。指定しない場合はNone。
		position: 表示順を示す位置。指定しない場合はNone(DB側で採番)。

	Returns:
		作成されたタスクのID。

	Raises:
		AssigneeInactiveError: 指定した`assignee_id`が非アクティブなユーザーの場合
			(SQLSTATE `P0006`)。
		sqlalchemy.exc.DBAPIError: 上記以外のDB操作エラーが発生した場合、そのまま送出する。
	"""
	day_start_utc, day_end_utc = _app_day_bounds_utc()
	try:
		result = await db.execute(
			text(
				"CALL sp_create_task(:project_id, :created_by, :assignee_id, :title, :body, "
				":status, :due_at, :position, :day_start_utc, :day_end_utc, NULL)"
			),
			{
				"project_id": project_id,
				"created_by": created_by,
				"assignee_id": assignee_id,
				"title": title,
				"body": body,
				"status": status,
				"due_at": due_at,
				"position": position,
				"day_start_utc": day_start_utc,
				"day_end_utc": day_end_utc,
			},
		)
	except DBAPIError as exc:
		_raise_task_constraint_error(exc)
	task_id: uuid.UUID = result.mappings().one()["p_task_id"]
	return task_id


async def get_by_id(db: AsyncSession, task_id: uuid.UUID) -> TaskWithProjectStatus | None:
	"""タスクIDを指定して1件取得する。

	DB関数 `fn_get_task` を呼び出し、tasks テーブルを所属プロジェクトの有効状態・
	コメント数とともに検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		task_id: 検索対象のタスクID。

	Returns:
		該当するTaskWithProjectStatus。該当行が存在しない場合はNone。
	"""
	result = await db.execute(
		text("SELECT (task).*, project_is_active, comment_count FROM fn_get_task(:task_id)"),
		{"task_id": task_id},
	)
	row = result.mappings().one_or_none()
	return None if row is None else _build_task_with_project_status(row)


async def list_board(db: AsyncSession, project_id: uuid.UUID, include_inactive: bool) -> list[TaskWithProjectStatus]:
	"""指定プロジェクトのカンバンボード表示用タスク一覧を取得する。

	DB関数 `fn_get_project_board` を呼び出し、tasks テーブルを検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		project_id: 検索対象のプロジェクトID。
		include_inactive: Trueの場合、非アクティブなタスクも含める。

	Returns:
		該当するTaskWithProjectStatusのリスト。該当行が無い場合は空リスト。
	"""
	result = await db.execute(
		text(
			"SELECT (task).*, project_is_active, comment_count "
			"FROM fn_get_project_board(:project_id, :include_inactive)"
		),
		{"project_id": project_id, "include_inactive": include_inactive},
	)
	return [_build_task_with_project_status(row) for row in result.mappings().all()]


async def list_for_user_with_total(
	db: AsyncSession,
	user_id: uuid.UUID,
	project_id: uuid.UUID | None,
	status: str | None,
	include_inactive: bool,
	limit: int,
	offset: int,
	unassigned: bool = False,
) -> tuple[list[TaskWithProjectStatus], int]:
	"""指定ユーザーが参照可能なタスク一覧を、全体件数付きで取得する。

	DB関数 `fn_list_tasks` を呼び出し、tasks テーブルを検索する。該当行が0件の場合、
	`fn_list_tasks`側の`total_count`列が取得できないため、DB関数 `fn_count_tasks` を
	別途呼び出して件数のみ取得する。

	Args:
		db: 検索に使用する非同期DBセッション。
		user_id: 検索対象のユーザーID。
		project_id: プロジェクトIDでの絞り込み。指定しない場合はNone。
		status: ステータスでの絞り込み。指定しない場合はNone。
		include_inactive: Trueの場合、非アクティブなタスクも含める。
		limit: 取得件数の上限。
		offset: 取得開始位置(ページング用)。
		unassigned: Trueの場合、未割当のタスクのみに絞り込む。

	Returns:
		(該当するTaskWithProjectStatusのリスト, ページング前の全体件数)のタプル。
		該当行が無い場合はリストは空だが、件数は絞り込み条件に合致する全体件数を返す。
	"""
	result = await db.execute(
		text(
			"SELECT (task).*, project_is_active, comment_count, total_count FROM "
			"fn_list_tasks(:user_id, :project_id, :status, :include_inactive, :limit, :offset, :unassigned)"
		),
		{
			"user_id": user_id,
			"project_id": project_id,
			"status": status,
			"include_inactive": include_inactive,
			"limit": limit,
			"offset": offset,
			"unassigned": unassigned,
		},
	)
	rows = result.mappings().all()
	if rows:
		return [_build_task_with_project_status(row) for row in rows], int(rows[0]["total_count"])
	count_result = await db.execute(
		text("SELECT fn_count_tasks(:user_id, :project_id, :status, :include_inactive, :unassigned) AS count"),
		{
			"user_id": user_id,
			"project_id": project_id,
			"status": status,
			"include_inactive": include_inactive,
			"unassigned": unassigned,
		},
	)
	return [], int(count_result.scalar_one())


async def list_for_user(
	db: AsyncSession,
	user_id: uuid.UUID,
	project_id: uuid.UUID | None,
	status: str | None,
	include_inactive: bool,
	limit: int,
	offset: int,
	unassigned: bool = False,
) -> list[TaskWithProjectStatus]:
	"""指定ユーザーが参照可能なタスク一覧を、全体件数を付加したリストとして取得する。

	`list_for_user_with_total`の結果を`TaskListResult`(全体件数付きリスト)にまとめる
	薄いラッパー。

	Args:
		db: 検索に使用する非同期DBセッション。
		user_id: 検索対象のユーザーID。
		project_id: プロジェクトIDでの絞り込み。指定しない場合はNone。
		status: ステータスでの絞り込み。指定しない場合はNone。
		include_inactive: Trueの場合、非アクティブなタスクも含める。
		limit: 取得件数の上限。
		offset: 取得開始位置(ページング用)。
		unassigned: Trueの場合、未割当のタスクのみに絞り込む。

	Returns:
		`total_count`属性に全体件数を持つTaskListResult。該当行が無い場合は空リスト
		(ただし`total_count`は絞り込み条件に合致する全体件数)。
	"""
	items, total = await list_for_user_with_total(
		db, user_id, project_id, status, include_inactive, limit, offset, unassigned
	)
	return TaskListResult(items, total)


async def list_calendar(
	db: AsyncSession,
	user_id: uuid.UUID,
	from_utc: datetime,
	to_utc: datetime,
	scope: str,
	project_id: uuid.UUID | None,
) -> list[TaskWithProjectStatus]:
	"""カレンダー表示用に、指定期間内の期限を持つタスク一覧を取得する。

	DB関数 `fn_list_calendar_tasks` を呼び出し、tasks テーブルを`due_at`の範囲で
	検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		user_id: 検索対象のユーザーID。
		from_utc: 検索範囲の開始日時(UTC)。
		to_utc: 検索範囲の終了日時(UTC)。
		scope: 検索範囲の種別(自分のタスクのみ/プロジェクト全体等)。
		project_id: プロジェクトIDでの絞り込み。指定しない場合はNone。

	Returns:
		該当するTaskWithProjectStatusのリスト。該当行が無い場合は空リスト。
	"""
	result = await db.execute(
		text(
			"SELECT (task).*, project_is_active, comment_count FROM fn_list_calendar_tasks("
			":user_id, :from_utc, :to_utc, :scope, :project_id)"
		),
		{"user_id": user_id, "from_utc": from_utc, "to_utc": to_utc, "scope": scope, "project_id": project_id},
	)
	return [_build_task_with_project_status(row) for row in result.mappings().all()]


async def update(
	db: AsyncSession,
	task_id: uuid.UUID,
	editor_id: uuid.UUID,
	version: int,
	title: str,
	body: str | None,
	status: str,
	assignee_id: uuid.UUID | None,
	due_at: datetime | None,
	position: int | None,
	is_active: bool | None = None,
) -> None:
	"""タスクを更新する(楽観ロック付き)。

	ストアドプロシージャ `sp_update_task` を呼び出し、tasks テーブルの該当行を更新する
	副作用を持つ。`version`が現在のDB上の値と一致しない場合は更新せず競合エラーとする
	(楽観的並行性制御)。本関数自体はcommitを行わず、呼び出し元のservice層が
	同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		task_id: 更新対象のタスクID。
		editor_id: 更新を行うユーザーID。
		version: 更新前提となる楽観ロック用バージョン番号。
		title: 更新後のタイトル。
		body: 更新後の本文。指定しない場合はNone。
		status: 更新後のステータス。
		assignee_id: 更新後の担当者ID。未割当にする場合はNone。
		due_at: 更新後の期限日時。指定しない場合はNone。
		position: 更新後の表示位置。指定しない場合はNone。
		is_active: 更新後の有効状態。変更しない場合はNone。

	Returns:
		None。

	Raises:
		TaskConflictError: `version`がDB上の現在値と一致しない場合(SQLSTATE `P0005`、
			楽観ロック競合)。
		AssigneeInactiveError: 指定した`assignee_id`が非アクティブなユーザーの場合
			(SQLSTATE `P0006`)。
		sqlalchemy.exc.DBAPIError: 上記以外のDB操作エラーが発生した場合、そのまま送出する。
	"""
	day_start_utc, day_end_utc = _app_day_bounds_utc()
	try:
		await db.execute(
			text(
				"CALL sp_update_task(:task_id, :editor_id, :version, :title, :body, "
				":status, :assignee_id, :due_at, :position, :is_active, :day_start_utc, :day_end_utc)"
			),
			{
				"task_id": task_id,
				"editor_id": editor_id,
				"version": version,
				"title": title,
				"body": body,
				"status": status,
				"assignee_id": assignee_id,
				"due_at": due_at,
				"position": position,
				"is_active": is_active,
				"day_start_utc": day_start_utc,
				"day_end_utc": day_end_utc,
			},
		)
	except DBAPIError as exc:
		_raise_task_constraint_error(exc)


def _raise_task_constraint_error(exc: DBAPIError) -> None:
	"""タスク作成/更新時のDB例外を、SQLSTATEに応じた業務例外へ変換して送出する。

	Args:
		exc: `sp_create_task`/`sp_update_task`呼び出し時に捕捉した例外。

	Returns:
		None(必ず例外を送出するため、正常終了はしない)。

	Raises:
		TaskConflictError: SQLSTATEが`P0005`(楽観ロック競合)の場合。
		AssigneeInactiveError: SQLSTATEが`P0006`(非アクティブな担当者)の場合。
		DBAPIError: 上記以外の場合、元の例外をそのまま再送出する。
	"""
	sqlstate = getattr(exc.orig, "sqlstate", None)
	if sqlstate == "P0005":
		raise TaskConflictError() from exc
	if sqlstate == "P0006":
		raise AssigneeInactiveError() from exc
	raise exc


async def set_active(db: AsyncSession, task_id: uuid.UUID, is_active: bool) -> None:
	"""タスクの有効/無効状態を切り替える。

	ストアドプロシージャ `sp_deactivate_task` を呼び出し、tasks テーブルの`is_active`を
	更新する副作用を持つ。本関数自体はcommitを行わず、呼び出し元のservice層が
	同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		task_id: 対象のタスクID。
		is_active: 更新後の有効状態。

	Returns:
		None。
	"""
	await db.execute(
		text("CALL sp_deactivate_task(:task_id, :is_active)"),
		{"task_id": task_id, "is_active": is_active},
	)
