# tasks テーブル 詳細設計

## 0. 関連ドキュメント

- 基本設計（正）：[`../../basic_design/01_database.md`](../../basic_design/01_database.md#35-tasks)
- 全体設計：[`../../basic_design/00_overview.md`](../../basic_design/00_overview.md)
- 本テーブルを操作するAPI詳細設計
  - [`../api/tasks/01_get_project_tasks.md`](../api/tasks/01_get_project_tasks.md) GET /api/projects/{project_id}/tasks
  - [`../api/tasks/02_post_project_tasks.md`](../api/tasks/02_post_project_tasks.md) POST /api/projects/{project_id}/tasks
  - [`../api/tasks/03_get_task.md`](../api/tasks/03_get_task.md) GET /api/tasks/{task_id}
  - [`../api/tasks/04_patch_task.md`](../api/tasks/04_patch_task.md) PATCH /api/tasks/{task_id}
  - [`../api/tasks/05_delete_task.md`](../api/tasks/05_delete_task.md) DELETE /api/tasks/{task_id}
- 関連テーブル：[`04_table_projects.md`](./04_table_projects.md)、[`05_table_project_members.md`](./05_table_project_members.md)、[`01_table_users.md`](./01_table_users.md)、[`07_table_task_comments.md`](./07_table_task_comments.md)
- DB関数：[`08_db_functions.md`](./08_db_functions.md)（`fn_next_task_position`）

## 1. 概要

| 項目 | 内容 |
|------|------|
| テーブル名 / 論理名 | `tasks` / タスク |
| 役割 | プロジェクト配下のタスク。カンバンの3列（`todo`/`in_progress`/`done`）に `status` で分類され、列内の並び順を `position` で保持する |
| 想定件数・増加傾向 | プロジェクト数 × 平均タスク数。学習用途のため小〜中規模 |
| ライフサイクル | 作成契機：`POST /api/projects/{project_id}/tasks`。更新契機：`PATCH /api/tasks/{task_id}`（title/description/status/assignee/position/due_date、`version` 必須）。削除契機：`DELETE /api/tasks/{task_id}`、またはプロジェクト削除時のCASCADE。物理削除のみ |
| 関連ORMモデル | `models/task.py :: Task` |

## 2. カラム定義

| 論理名 | カラム名 | 型 | NULL | 既定値 | 主キー/一意 | 説明 |
|--------|----------|----|------|--------|--------------|------|
| ID | `id` | UUID | NO | `gen_random_uuid()` | PK | |
| プロジェクトID | `project_id` | UUID | NO | - | FK → `projects.id` | `ON DELETE CASCADE` |
| タイトル | `title` | VARCHAR(150) | NO | - | - | 1〜150文字（アプリ層） |
| 説明 | `description` | TEXT | YES | - | - | |
| ステータス | `status` | VARCHAR(20) | NO | `'todo'` | - | `CHECK (status IN ('todo','in_progress','done'))` |
| 担当者 | `assignee_id` | UUID | YES | - | FK → `users.id` | `ON DELETE SET NULL`。指定時は有効なプロジェクトメンバーであること（アプリ層検証） |
| 作成者 | `created_by` | UUID | NO | - | FK → `users.id` | `ON DELETE RESTRICT` |
| 並び順 | `position` | INTEGER | NO | `0` | 一意（`project_id, status` 内） | `CHECK (position >= 0)`。`UNIQUE (project_id, status, position) DEFERRABLE INITIALLY DEFERRED` |
| バージョン | `version` | INTEGER | NO | `1` | - | 楽観的排他制御用。`CHECK (version > 0)`。更新成功時に+1 |
| 期限日 | `due_date` | DATE | YES | - | - | |
| 作成日時 | `created_at` | TIMESTAMPTZ | NO | `now()` | - | |
| 更新日時 | `updated_at` | TIMESTAMPTZ | NO | `now()` | - | `trg_set_updated_at` トリガで自動更新 |

基本設計 `01_database.md` §3.5 の定義から逸脱しない。

## 3. DDL

```sql
CREATE TABLE tasks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title        VARCHAR(150) NOT NULL,
    description  TEXT,
    status       VARCHAR(20) NOT NULL DEFAULT 'todo'
                 CONSTRAINT ck_tasks_status CHECK (status IN ('todo', 'in_progress', 'done')),
    assignee_id  UUID REFERENCES users(id) ON DELETE SET NULL,
    created_by   UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    position     INTEGER NOT NULL DEFAULT 0
                 CONSTRAINT ck_tasks_position_non_negative CHECK (position >= 0),
    version      INTEGER NOT NULL DEFAULT 1
                 CONSTRAINT ck_tasks_version_positive CHECK (version > 0),
    due_date     DATE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_tasks_project_status_position
        UNIQUE (project_id, status, position) DEFERRABLE INITIALLY DEFERRED
);

COMMENT ON TABLE tasks IS 'カンバンのタスク。statusで列を、positionで列内順序を表す';
COMMENT ON COLUMN tasks.status IS 'todo / in_progress / done のいずれか（CHECK制約）';
COMMENT ON COLUMN tasks.position IS '同一 project_id, status 内の並び順（0起点）';
COMMENT ON COLUMN tasks.version IS '楽観的排他制御用。PATCH成功時に+1';

CREATE INDEX ix_tasks_assignee_id ON tasks (assignee_id);

CREATE TRIGGER trg_tasks_set_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION trg_set_updated_at();
```

`DEFERRABLE` な一意制約はPostgreSQLの仕様上、テーブル定義内の `CONSTRAINT ... UNIQUE (...) DEFERRABLE` としてのみ定義可能（`CREATE UNIQUE INDEX` では不可）なため、上記DDLのテーブル制約1本のみで表現する。

## 4. 制約・インデックス

| 種別 | 名称 | 対象カラム | 内容 | 目的（対応クエリ） |
|------|------|-----------|------|---------------------|
| PK | `tasks_pkey` | `id` | 主キー | タスク詳細取得 |
| FK | `tasks_project_id_fkey` | `project_id` | → `projects.id` `ON DELETE CASCADE` | プロジェクト削除時にタスクを自動削除 |
| FK | `tasks_assignee_id_fkey` | `assignee_id` | → `users.id` `ON DELETE SET NULL` | ユーザー削除時に担当者を自動的に未割当へ（本設計では所属解除はアプリ層UPDATEで対応。§11参照） |
| FK | `tasks_created_by_fkey` | `created_by` | → `users.id` `ON DELETE RESTRICT` | 作成者の履歴保護。ユーザーは無効化のみで物理削除しないため通常は問題にならない |
| CHECK | `ck_tasks_status` | `status` | `status IN ('todo','in_progress','done')` | 不正な状態値の混入防止 |
| CHECK | `ck_tasks_position_non_negative` | `position` | `position >= 0` | 並び順の健全性 |
| CHECK | `ck_tasks_version_positive` | `version` | `version > 0` | 楽観ロック値の健全性 |
| UNIQUE（遅延） | `uq_tasks_project_status_position` | `(project_id, status, position)` | `DEFERRABLE INITIALLY DEFERRED` | 列内重複防止。再採番中の一時的な重複をトランザクション内で許容しつつCOMMIT時に検証 |
| INDEX | `ix_tasks_assignee_id` | `assignee_id` | B-tree | 担当タスク絞り込み、メンバー削除時の一括NULL化（`05_table_project_members.md` §8.5） |

`uq_tasks_project_status_position` はカンバン表示クエリ（`WHERE project_id=:pid ORDER BY status, position`）の実行計画でも利用される。

## 5. SQLAlchemyモデル定義

```python
class TaskStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("status IN ('todo','in_progress','done')", name="ck_tasks_status"),
        CheckConstraint("position >= 0", name="ck_tasks_position_non_negative"),
        CheckConstraint("version > 0", name="ck_tasks_version_positive"),
        UniqueConstraint(
            "project_id", "status", "position",
            name="uq_tasks_project_status_position",
            deferrable=True, initially="DEFERRED",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="todo")
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped["Project"] = relationship("Project", back_populates="tasks", lazy="joined")
    assignee: Mapped["User | None"] = relationship(
        "User", foreign_keys=[assignee_id], lazy="joined"
    )
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by], lazy="noload")
    comments: Mapped[list["TaskComment"]] = relationship(
        "TaskComment", back_populates="task", cascade="all, delete-orphan", lazy="noload"
    )
```

`comments` は件数が多くなり得るため `lazy="noload"` とし、コメント一覧は `task_comment_repository` の専用クエリで取得する（N+1回避、`01_database.md` Q-4）。

## 6. ER関連図

```mermaid
erDiagram
    projects ||--o{ tasks : "project_id"
    users |o--o{ tasks : "assignee_id（NULL可）"
    users ||--o{ tasks : "created_by"
    tasks ||--o{ task_comments : "task_id"

    tasks {
        uuid id PK
        uuid project_id FK
        varchar_150 title
        text description
        varchar_20 status "todo/in_progress/done"
        uuid assignee_id FK "NULL可"
        uuid created_by FK
        integer position
        integer version
        date due_date "NULL可"
        timestamptz created_at
        timestamptz updated_at
    }
```

## 7. データ遷移図

### 7.1 status カラムの状態遷移（基本設計 §4.1 と同一。遷移制限なし）

```mermaid
stateDiagram-v2
    [*] --> todo: "POST /projects/:id/tasks"
    todo --> in_progress: "PATCH /tasks/:id status=in_progress"
    in_progress --> done: "PATCH /tasks/:id status=done"
    done --> in_progress: "PATCH /tasks/:id status=in_progress（差し戻し）"
    in_progress --> todo: "PATCH /tasks/:id status=todo（差し戻し）"
    todo --> done: "PATCH /tasks/:id status=done（直接完了）"
    done --> [*]: "DELETE /tasks/:id"
    todo --> [*]: "DELETE /tasks/:id"
    in_progress --> [*]: "DELETE /tasks/:id"
```

### 7.2 行全体のライフサイクルと再採番の契機

```mermaid
flowchart LR
    A["POST /tasks"] --> B["advisory lock 取得<br/>(project_id, status)"]
    B --> C["fn_next_task_position で末尾position採番"]
    C --> D["INSERT tasks<br/>version=1"]
    D --> E["ROW 生成完了"]

    E --> F["PATCH /tasks/:id<br/>version一致確認"]
    F -->|"status/position変更あり"| G["advisory lock 取得<br/>(project_id, 旧status)<br/>(project_id, 新status)"]
    G --> H["移動対象を退避値へ一時UPDATE<br/>(max+件数+1)"]
    H --> I["旧列: 後続positionを-1で詰める<br/>新列: 挿入位置以降を+1でずらす"]
    I --> J["移動対象へ最終position設定<br/>UPDATE version=version+1"]
    J --> K["COMMIT（DEFERRED制約検証）"]

    F -->|"status/position変更なし"| L["UPDATE title/description/assignee/due_date<br/>version=version+1"]

    E --> M["DELETE /tasks/:id"]
    M --> N["advisory lock 取得<br/>(project_id, status)"]
    N --> O["DELETE tasks 実行"]
    O --> P["後続positionを-1で詰める"]
    P --> Q["ROW 消滅（CASCADE: task_comments削除）"]
```

## 8. リポジトリ関数詳細

### 8.1 `repository/task_repository.py :: acquire_status_lock`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def acquire_status_lock(session: AsyncSession, *, project_id: UUID, status: str) -> None` |
| 引数 / 戻り値 | プロジェクトID・ステータス → なし（ロック取得のみ） |
| 発行SQL | ```sql\nSELECT pg_advisory_xact_lock(\n  hashtextextended(:project_id::text || ':' || :status, 0)\n);\n``` |
| 使用インデックス | 該当なし（advisory lockはロックテーブルであり行ロックではない） |
| 送出例外 | なし（`pg_advisory_xact_lock` はトランザクション終了時に自動解放） |
| 処理内容 | 1. `project_id` と `status` の組み合わせを64bitハッシュ化してロックキーとする<br/>2. 同一列に対する position 採番・再採番を直列化し、同時作成/移動時の一意制約違反やpositionの飛び・重複を防ぐ |

### 8.2 `repository/task_repository.py :: next_position`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def next_position(session: AsyncSession, *, project_id: UUID, status: str) -> int` |
| 引数 / 戻り値 | プロジェクトID・ステータス → 末尾に採番すべき `position` |
| 発行SQL | ```sql\nSELECT fn_next_task_position(:project_id, :status);\n``` |
| 使用インデックス | `uq_tasks_project_status_position`（関数内部の `MAX(position)` 集計で使用） |
| 送出例外 | なし |
| 処理内容 | 1. 呼び出し前に `acquire_status_lock` を同一トランザクションで取得済みであることが前提<br/>2. `fn_next_task_position`（[`08_db_functions.md`](./08_db_functions.md)）が `COALESCE(MAX(position), -1) + 1` を返す |

### 8.3 `repository/task_repository.py :: insert`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def insert(session: AsyncSession, task: Task) -> Task` |
| 引数 / 戻り値 | 未永続化の `Task` エンティティ → 採番済み `Task` |
| 発行SQL | ```sql\nINSERT INTO tasks\n  (project_id, title, description, status, assignee_id, created_by, position, due_date)\nVALUES\n  (:project_id, :title, :description, :status, :assignee_id, :created_by, :position, :due_date)\nRETURNING id, version, created_at, updated_at;\n``` |
| 使用インデックス | `uq_tasks_project_status_position`（制約検証） |
| 送出例外 | `ConflictError`（`uq_tasks_project_status_position` 違反時。advisory lock内で `next_position` を呼んでいれば通常発生しない） |
| 処理内容 | `session.add()` + `flush()`。`version` はDB既定値 `1` を使用 |

### 8.4 `repository/task_repository.py :: get_by_id_for_update`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def get_by_id_for_update(session: AsyncSession, task_id: UUID) -> Task \| None` |
| 引数 / 戻り値 | タスクID → `Task`（存在しなければ `None`） |
| 発行SQL | ```sql\nSELECT id, project_id, title, description, status, assignee_id,\n       created_by, position, version, due_date, created_at, updated_at\nFROM tasks WHERE id = :task_id\nFOR UPDATE;\n``` |
| 使用インデックス | PK |
| 送出例外 | なし |
| 処理内容 | 1. `PATCH /tasks/{id}` の直前に行ロック（`FOR UPDATE`）を取得し、`version` チェックとUPDATEの間の競合を防ぐ（advisory lockは「列全体」、本ロックは「この1行」が対象という違いに注意） |

### 8.5 `repository/task_repository.py :: update_with_optimistic_lock`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def update_with_optimistic_lock(session: AsyncSession, task: Task, *, expected_version: int, changes: dict) -> Task` |
| 引数 / 戻り値 | 対象エンティティ・期待バージョン・更新差分 → 更新後 `Task` |
| 発行SQL | ```sql\nUPDATE tasks\nSET title = COALESCE(:title, title),\n    description = CASE WHEN :description_set THEN :description ELSE description END,\n    status = COALESCE(:status, status),\n    assignee_id = CASE WHEN :assignee_set THEN :assignee_id ELSE assignee_id END,\n    position = COALESCE(:position, position),\n    due_date = CASE WHEN :due_date_set THEN :due_date ELSE due_date END,\n    version = version + 1\nWHERE id = :id AND version = :expected_version\nRETURNING id, status, position, version, updated_at;\n``` |
| 使用インデックス | PK。`WHERE` 句の `version` 一致条件はPK取得後のフィルタ |
| 送出例外 | `ConflictError("TASK_CONFLICT")`（`RETURNING` が0行、すなわち `version` 不一致） |
| 処理内容 | 1. `UPDATE ... WHERE id=:id AND version=:expected_version` で行を絞り込む<br/>2. 影響行数0件なら `version` 不一致とみなし `409 TASK_CONFLICT` に変換<br/>3. status/position が変わる場合は事前に §8.6〜8.7 の再採番処理を同一トランザクションで実施してから本UPDATEを発行する |

### 8.6 `repository/task_repository.py :: reorder_within_status`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def reorder_within_status(session: AsyncSession, *, project_id: UUID, status: str, moving_task_id: UUID, target_position: int) -> None` |
| 引数 / 戻り値 | 同一列内での移動条件 → なし |
| 発行SQL | ```sql\n-- 1. 移動対象を退避値へ\nUPDATE tasks SET position = (\n  SELECT COALESCE(MAX(position), -1) + 1 + COUNT(*) FROM tasks\n  WHERE project_id = :project_id AND status = :status\n) WHERE id = :moving_task_id;\n-- 2. 対象位置以降を+1（前方へ移動する場合）または-1（後方へ移動する場合）でずらす\nUPDATE tasks SET position = position + :shift\nWHERE project_id = :project_id AND status = :status\n  AND id <> :moving_task_id\n  AND position BETWEEN :range_start AND :range_end;\n-- 3. 移動対象を最終位置へ\nUPDATE tasks SET position = :target_position WHERE id = :moving_task_id;\n``` |
| 使用インデックス | `uq_tasks_project_status_position`（`DEFERRABLE INITIALLY DEFERRED` によりCOMMIT時まで違反検査を遅延） |
| 送出例外 | `ConflictError`（COMMIT時に制約違反が残っていた場合。ロジック上は発生しない想定） |
| 処理内容 | 1. `acquire_status_lock` 済みであることが前提<br/>2. 退避値へ一時移動 → 間の行をシフト → 最終位置を設定、の3段階UPDATEで一意制約の一時的な重複（`DEFERRABLE INITIALLY DEFERRED` によりCOMMITまで許容）を回避しつつ整合させる |

### 8.7 `repository/task_repository.py :: move_to_status_tail`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def move_to_status_tail(session: AsyncSession, *, project_id: UUID, moving_task_id: UUID, old_status: str, new_status: str) -> int` |
| 引数 / 戻り値 | 列間移動の条件 → 新列での採番位置 |
| 発行SQL | ```sql\n-- 旧列の後続を詰める\nUPDATE tasks SET position = position - 1\nWHERE project_id = :project_id AND status = :old_status\n  AND position > (SELECT position FROM tasks WHERE id = :moving_task_id);\n-- 新列の末尾position取得\nSELECT fn_next_task_position(:project_id, :new_status);\n-- 移動対象を新列・新positionへ更新\nUPDATE tasks SET status = :new_status, position = :new_position\nWHERE id = :moving_task_id;\n``` |
| 使用インデックス | `uq_tasks_project_status_position` |
| 送出例外 | なし（advisory lockで直列化済み） |
| 処理内容 | `acquire_status_lock(project_id, old_status)` と `(project_id, new_status)` を**キー文字列の昇順**で取得しデッドロックを防止 → 旧列の詰め → 新列末尾へ挿入、の順で実行。`update_with_optimistic_lock` の直前に呼ばれる |

### 8.8 `repository/task_repository.py :: delete_and_compact`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def delete_and_compact(session: AsyncSession, task: Task) -> None` |
| 引数 / 戻り値 | 削除対象の `Task` → なし |
| 発行SQL | ```sql\nDELETE FROM tasks WHERE id = :id;\nUPDATE tasks SET position = position - 1\nWHERE project_id = :project_id AND status = :status AND position > :deleted_position;\n``` |
| 使用インデックス | `uq_tasks_project_status_position` |
| 送出例外 | なし |
| 処理内容 | `acquire_status_lock(project_id, status)` を取得してから実行。`task_comments` はDBの `ON DELETE CASCADE` で自動削除されるためアプリ側で個別削除しない |

### 8.9 `repository/task_repository.py :: list_by_project_grouped`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def list_by_project_grouped(session: AsyncSession, project_id: UUID) -> dict[str, list[Task]]` |
| 引数 / 戻り値 | プロジェクトID → `{"todo": [...], "in_progress": [...], "done": [...]}` |
| 発行SQL | ```sql\nSELECT id, title, description, status, assignee_id, position, version, due_date\nFROM tasks WHERE project_id = :project_id\nORDER BY status, position ASC;\n``` |
| 使用インデックス | `uq_tasks_project_status_position` |
| 送出例外 | なし |
| 処理内容 | 1クエリで取得しアプリ側で `status` ごとにグルーピング。コメント件数は `task_comment_repository.count_by_task_ids()` で別クエリ集計しN+1を回避 |

## 9. 関数相関図

```mermaid
flowchart LR
    subgraph service
        TS["task_service"]
    end
    subgraph repository
        TR["task_repository"]
    end
    subgraph db
        FN1["fn_next_task_position()"]
        T1[("tasks")]
    end

    TS -->|"create_task"| TR
    TR -->|"acquire_status_lock"| T1
    TR -->|"next_position"| FN1
    FN1 -->|"MAX(position)+1"| T1
    TR -->|"insert"| T1

    TS -->|"update_task"| TR
    TR -->|"get_by_id_for_update"| T1
    TR -->|"reorder_within_status /<br/>move_to_status_tail"| T1
    TR -->|"update_with_optimistic_lock"| T1

    TS -->|"delete_task"| TR
    TR -->|"delete_and_compact"| T1

    TS -->|"get_board"| TR
    TR -->|"list_by_project_grouped"| T1
```

## 10. 想定クエリと性能

| No | ユースケース | クエリ概要 | 使用インデックス | 想定計画 |
|----|-------------|-----------|-------------------|----------|
| Q-Task-1 | カンバン取得 | `WHERE project_id=:pid ORDER BY status, position` | `uq_tasks_project_status_position` | Index Scan（ソート済みのため追加Sort不要） |
| Q-Task-2 | タスク詳細 | `WHERE id=:id` | PK | Index Scan（1行） |
| Q-Task-3 | 末尾position採番 | `SELECT COALESCE(MAX(position),-1)+1 WHERE project_id=:pid AND status=:status` | `uq_tasks_project_status_position` | Index Scan（Backward、最終要素のみ） |
| Q-Task-4 | 担当タスク絞り込み | `WHERE assignee_id=:uid` | `ix_tasks_assignee_id` | Index Scan |
| Q-Task-5 | 楽観ロック更新 | `UPDATE ... WHERE id=:id AND version=:v` | PK | Index Scan（1行、`FOR UPDATE` 併用） |
| Q-Task-6 | 削除時の後続詰め | `UPDATE ... WHERE project_id=:pid AND status=:status AND position>:p` | `uq_tasks_project_status_position` | Index Scan |

## 11. 整合性・並行制御

| 項目 | 内容 |
|------|------|
| FK CASCADE（`project_id`） | `ON DELETE CASCADE`。プロジェクト削除時にタスクを自動削除し、`task_comments` も連鎖削除される |
| FK CASCADE（`assignee_id`） | `ON DELETE SET NULL`。`users` 行自体の削除時にのみ発火。所属解除（`project_members` 削除）はDBのFKでは発火しないため、`05_table_project_members.md` §8.5 のアプリ層UPDATEで対応 |
| FK CASCADE（`created_by`） | `ON DELETE RESTRICT`。作成者の履歴を保護 |
| CHECK制約 | `ck_tasks_status`（3値のみ許可）、`ck_tasks_position_non_negative`、`ck_tasks_version_positive` |
| 一意制約（遅延） | `uq_tasks_project_status_position` は `DEFERRABLE INITIALLY DEFERRED`。再採番の中間状態（退避値経由）での一時的重複をトランザクション内で許容し、COMMIT時に最終検証する |
| 楽観ロック（`version`） | `PATCH /tasks/{id}` は `version` を必須パラメータとし、`UPDATE ... WHERE id=:id AND version=:expected_version` で一致した場合のみ更新、成功時に `version+1`。不一致時は影響行数0件を検知して `409 TASK_CONFLICT` |
| advisory lock | `pg_advisory_xact_lock(hashtextextended(project_id \|\| ':' \|\| status, 0))` で `(project_id, status)` 単位に position 採番・再採番を直列化。`_xact_` 系のためトランザクション終了で自動解放。列間移動時は旧列・新列のロックをキー文字列の昇順で取得しデッドロックを回避 |
| トランザクション境界 | 作成：lock取得→採番→INSERTを1トランザクション。更新（status/position変更あり）：`FOR UPDATE`→lock取得→再採番UPDATE群→楽観ロックUPDATEを1トランザクション。削除：lock取得→DELETE→後続詰めUPDATEを1トランザクション |
| ロックの二重性 | 行ロック（`FOR UPDATE`/`version`列）は「この1タスク」、advisory lockは「同じ列の複数タスク」の同時更新を防ぐ。目的が異なるため併用する |

## 12. テスト設計

| No | 区分 | ケース | 期待結果 | テスト名案 |
|----|------|--------|----------|------------|
| T-1 | 制約違反（CHECK） | `status='invalid'` / `position=-1` でINSERT/UPDATEを試みる | それぞれ `ck_tasks_status` / `ck_tasks_position_non_negative` 違反でDBエラー | `test_task_check_constraints_reject_invalid_values` |
| T-2 | 制約違反（UNIQUE） | advisory lockを取らずに同一 `(project_id, status, position)` を持つ2行を並行INSERT | 一意制約違反、またはadvisory lockにより直列化されて後続が採番し直される | `test_concurrent_task_creation_serialized_by_advisory_lock` |
| T-3 | CASCADE削除 | プロジェクトを削除する | 配下の `tasks` と `task_comments` が連鎖削除される | `test_delete_project_cascades_tasks_and_comments` |
| T-4 | 並行更新（楽観ロック） | 2クライアントが同じ `version` を元に同時 `PATCH` する | 先着のみ成功し `version+1`、後着は `409 TASK_CONFLICT` | `test_patch_task_version_conflict_returns_409` |
| T-5 | 並び順 | 列内の中間位置へタスクを移動する | 移動元より後ろの要素が詰まり、移動先以降がずれ、`position` に欠番・重複が生じない | `test_reorder_within_status_keeps_positions_contiguous` |
| T-6 | 列間移動 | `todo` → `in_progress` へ `position` 指定なしで移動する | 旧列の後続が詰まり、新列の末尾に採番される | `test_move_status_appends_to_tail_of_new_column` |
| T-7 | 削除時の再採番 | 列の中間のタスクを削除する | 削除後、後続タスクの `position` が1つずつ詰まる | `test_delete_task_compacts_following_positions` |
| T-8 | advisory lock | 同一 `(project_id, status)` への複数の作成・移動リクエストを並行実行 | 採番・並べ替えが直列化され、`uq_tasks_project_status_position` 違反が発生しない | `test_advisory_lock_prevents_position_collision_under_concurrency` |
| T-9 | FK | `assignee_id` に非メンバーのユーザーIDを指定して作成/更新する | アプリ層バリデーションで拒否（`422`または`400`。DB制約ではなくサービス層検証） | `test_assign_non_member_user_rejected` |
| T-10 | デフォルト値 | `status`/`position`/`version` を指定せずにINSERTする | `status='todo'`、`position` は `next_position` 経由の採番値、`version=1` となる | `test_create_task_defaults_applied` |

## 13. 不明点・要検討事項

- `position` のDB既定値は `01_database.md` の定義上 `0` だが、実運用では常に `fn_next_task_position` 経由で採番するため素の既定値 `0` が使われる場面は基本的に無い（DBスキーマ上の安全弁としてのみ機能する）。この理解でよいか要確認。
- advisory lockのキー生成方法（`hashtextextended(project_id || ':' || status, 0)`）は基本設計に具体的な実装が無いため、本書での具体化である。`pg_advisory_xact_lock` は単一bigint引数版を用いる想定だが、2引数版（`(classid, objid)` 形式）を用いるかは実装時に確定すること（要検討）。
- 列間移動時のロック取得順序（キー文字列の昇順固定によるデッドロック回避）は基本設計に記載がなく、本書での具体化である。
