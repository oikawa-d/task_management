"""ユーザー(users テーブル)へのデータアクセス層。

各関数はトランザクションのcommit/rollbackを行わない。呼び出し元のservice層が
同一セッションのcommitを担う。DB接続系の`OperationalError`は`raise_database_error`で
変換し、接続障害であれば`ServiceUnavailableError`として、それ以外は元の例外として送出する。
ユーザー名・メール重複などの業務エラー(SQLSTATE `P0001`/`P0002`)は本層では変換せず、
`sqlalchemy.exc.DBAPIError`のまま呼び出し元のservice層に伝播させ、service層で判定する。
"""

import uuid
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import raise_database_error
from app.models.user import User


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
	"""ユーザーIDを指定して1件取得する。

	DB関数 `fn_get_user` を呼び出し、users テーブルを検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		user_id: 検索対象のユーザーID。

	Returns:
		該当するUser。該当行が存在しない場合はNone。

	Raises:
		ServiceUnavailableError: DB接続障害が発生した場合。
		OperationalError: 接続障害以外のDB操作エラーが発生した場合、元の例外を再送出する。
	"""
	try:
		result = await db.execute(
			select(User).from_statement(text("SELECT * FROM fn_get_user(:user_id)")).params(user_id=user_id)
		)
		return result.scalars().one_or_none()
	except OperationalError as exc:
		raise_database_error(exc)


async def get_by_login_identifier(db: AsyncSession, identifier: str) -> User | None:
	"""ログイン識別子(ユーザー名またはメールアドレス)を指定して1件取得する。

	DB関数 `fn_find_user_by_identifier` を呼び出し、users テーブルを検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		identifier: ログインに使用されたユーザー名またはメールアドレス。

	Returns:
		該当するUser。該当行が存在しない場合はNone。

	Raises:
		ServiceUnavailableError: DB接続障害が発生した場合。
		OperationalError: 接続障害以外のDB操作エラーが発生した場合、元の例外を再送出する。
	"""
	try:
		result = await db.execute(
			select(User)
			.from_statement(text("SELECT * FROM fn_find_user_by_identifier(:identifier)"))
			.params(identifier=identifier)
		)
		return result.scalars().one_or_none()
	except OperationalError as exc:
		raise_database_error(exc)


async def get_by_email(db: AsyncSession, email: str) -> User | None:
	"""メールアドレスを指定して1件取得する。

	DB関数 `fn_find_user_by_email` を呼び出し、users テーブルを検索する。

	Args:
		db: 検索に使用する非同期DBセッション。
		email: 検索対象のメールアドレス。

	Returns:
		該当するUser。該当行が存在しない場合はNone。

	Raises:
		ServiceUnavailableError: DB接続障害が発生した場合。
		OperationalError: 接続障害以外のDB操作エラーが発生した場合、元の例外を再送出する。
	"""
	try:
		result = await db.execute(
			select(User).from_statement(text("SELECT * FROM fn_find_user_by_email(:email)")).params(email=email)
		)
		return result.scalars().one_or_none()
	except OperationalError as exc:
		raise_database_error(exc)


async def create(db: AsyncSession, username: str, email: str, password_hash: str | None) -> uuid.UUID:
	"""ユーザーを新規登録する。

	ストアドプロシージャ `sp_register_user` を呼び出し、users テーブルに1行挿入する
	副作用を持つ。本関数自体はcommitを行わず、呼び出し元のservice層が同一セッションで
	commitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		username: 登録するユーザー名。
		email: 登録するメールアドレス。
		password_hash: パスワードのハッシュ値。OAuth登録などパスワードを持たない場合はNone。

	Returns:
		作成されたユーザーのID。

	Raises:
		ServiceUnavailableError: DB接続障害が発生した場合。
		sqlalchemy.exc.DBAPIError: ユーザー名(SQLSTATE `P0001`)またはメールアドレス
			(SQLSTATE `P0002`)が既に登録済みの場合、元の例外を再送出する
			(業務エラーへの変換は呼び出し元のservice層が行う)。
	"""
	try:
		result = await db.execute(
			text("CALL sp_register_user(:username, :email, :password_hash, NULL)"),
			{"username": username, "email": email, "password_hash": password_hash},
		)
		user_id: uuid.UUID = result.mappings().one()["p_user_id"]
		return user_id
	except OperationalError as exc:
		raise_database_error(exc)


async def mark_email_verified(db: AsyncSession, user_id: uuid.UUID) -> None:
	"""ユーザーのメールアドレスを確認済みにする。

	ストアドプロシージャ `sp_verify_user_email` を呼び出し、users テーブルの該当行を
	更新する副作用を持つ。本関数自体はcommitを行わず、呼び出し元のservice層が
	同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		user_id: 対象ユーザーのID。

	Returns:
		None。

	Raises:
		ServiceUnavailableError: DB接続障害が発生した場合。
		OperationalError: 接続障害以外のDB操作エラーが発生した場合、元の例外を再送出する。
	"""
	try:
		await db.execute(text("CALL sp_verify_user_email(:user_id)"), {"user_id": user_id})
	except OperationalError as exc:
		raise_database_error(exc)


async def update_password(db: AsyncSession, user_id: uuid.UUID, password_hash: str) -> None:
	"""ユーザーのパスワードハッシュを更新する。

	ストアドプロシージャ `sp_update_user_password` を呼び出し、users テーブルの該当行を
	更新する副作用を持つ。本関数自体はcommitを行わず、呼び出し元のservice層が
	同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		user_id: 対象ユーザーのID。
		password_hash: 更新後のパスワードハッシュ値。

	Returns:
		None。

	Raises:
		ServiceUnavailableError: DB接続障害が発生した場合。
		OperationalError: 接続障害以外のDB操作エラーが発生した場合、元の例外を再送出する。
	"""
	try:
		await db.execute(
			text("CALL sp_update_user_password(:user_id, :password_hash)"),
			{"user_id": user_id, "password_hash": password_hash},
		)
	except OperationalError as exc:
		raise_database_error(exc)


async def update_profile(
	db: AsyncSession,
	user_id: uuid.UUID,
	last_name: str | None,
	first_name: str | None,
	last_name_kana: str | None,
	first_name_kana: str | None,
	birth_date: date | None,
) -> None:
	"""ユーザーのプロフィール情報を更新する。

	ストアドプロシージャ `sp_update_user_profile` を呼び出し、users テーブルの該当行を
	更新する副作用を持つ。本関数自体はcommitを行わず、呼び出し元のservice層が
	同一セッションでcommitする。

	Args:
		db: 更新に使用する非同期DBセッション。
		user_id: 対象ユーザーのID。
		last_name: 更新後の姓。指定しない場合はNone。
		first_name: 更新後の名。指定しない場合はNone。
		last_name_kana: 更新後の姓(カナ)。指定しない場合はNone。
		first_name_kana: 更新後の名(カナ)。指定しない場合はNone。
		birth_date: 更新後の生年月日。指定しない場合はNone。

	Returns:
		None。

	Raises:
		ServiceUnavailableError: DB接続障害が発生した場合。
		OperationalError: 接続障害以外のDB操作エラーが発生した場合、元の例外を再送出する。
	"""
	try:
		await db.execute(
			text(
				"CALL sp_update_user_profile("
				":user_id, :last_name, :first_name, :last_name_kana, :first_name_kana, :birth_date)"
			),
			{
				"user_id": user_id,
				"last_name": last_name,
				"first_name": first_name,
				"last_name_kana": last_name_kana,
				"first_name_kana": first_name_kana,
				"birth_date": birth_date,
			},
		)
	except OperationalError as exc:
		raise_database_error(exc)
