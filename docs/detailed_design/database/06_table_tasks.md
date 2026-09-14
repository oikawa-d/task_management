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
  - `../api/tasks/` 配下に新設予定：`GET /api/tasks`（横断一覧）、`POST /api/tasks`（`project_id`任意でのフラット作成）。ファイルは既存9ファイルの次番号で新規作成される想定（API設計担当が対応。issue #10 ブリーフ参照）
- 関連テーブル：[`04_table_projects.md`](./04_table_projects.md)、[`05_table_project_members.md`](./05_table_project_members.md)、[`01_table_users.md`](./01_table_users.md)、[`07_table_task_comments.md`](./07_table_task_comments.md)
- DB関数：[`08_db_functions.md`](./08_db_functions.md)（`fn_next_task_position`）

## 1. 概要

| 項目 | 内容 |
|------|------|
| テーブル名 / 論理名 | `tasks` / タスク |
| 役割 | プロジェクト配下のタスク。カンバンの3列（`todo`/`in_progress`/`done`）に `status` で分類され、列内の並び順を `position` で保持する |
| 想定件数・増加傾向 | プロジェクト数 × 平均タスク数。学習用途のため小〜中規模 |
| ライフサイクル | 作成契機：`POST /api/projects/{project_id}/tasks`（`project_id`はパス由来）、または `POST /api/tasks`（bodyの`project_id`は任意・NULL可）。更新契機：`PATCH /api/tasks/{task_id}`（title/description/status/assignee/position/due_at/is_active、`version` 必須）。削除契機：`DELETE /api/tasks/{task_id}` → 論理削除（`is_active=false`への更新）。物理削除は行わない。プロジェクトが無効化（論理削除）されてもタスクは削除されない |
| 関連ORMモデル | `models/task.py :: Task` |

## 2. カラム定義

| 論理名 | カラム名 | 型 | NULL | 既定値 | 主キー/一意 | 説明 |
|--------|----------|----|------|--------|--------------|------|
| ID | `id` | UUID | NO | `gen_random_uuid()` | PK | |
| プロジェクトID | `project_id` | UUID | YES | - | FK → `projects.id` | `ON DELETE SET NULL`。NULLはプロジェクト未所属タスクを表す |
| タイトル | `title` | VARCHAR(150) | NO | - | - | 1〜150文字（アプリ層） |
| 説明 | `description` | TEXT | YES | - | - | |
| ステータス | `status` | VARCHAR(20) | NO | `'todo'` | - | `CHECK (status IN ('todo','in_progress','done'))` |
| 担当者 | `assignee_id` | UUID | YES | - | FK → `users.id` | `ON DELETE SET NULL`。指定時は有効なプロジェクトメンバーであること（アプリ層検証） |
| 作成者 | `created_by` | UUID | NO | - | FK → `users.id` | `ON DELETE RESTRICT` |
| 並び順 | `position` | INTEGER | NO | `0` | 一意（`project_id, status` 内） | `CHECK (position >= 0)`。`UNIQUE (project_id, status, position) DEFERRABLE INITIALLY DEFERRED` |
| バージョン | `version` | INTEGER | NO | `1` | - | 楽観的排他制御用。`CHECK (version > 0)`。更新成功時に+1 |
| 期限日時 | `due_at` | TIMESTAMPTZ | YES | - | - | UTC保存。表示・日次境界の判定は`APP_TIMEZONE` |
| 有効フラグ | `is_active` | BOOLEAN | NO | `true` | - | 論理削除フラグ。`false` は無効化（論理削除）済みを表す |
| 作成日時 | `created_at` | TIMESTAMPTZ | NO | `now()` | - | |
| 更新日時 | `updated_at` | TIMESTAMPTZ | NO | `now()` | - | `trg_set_updated_at` トリガで自動更新 |

基本設計 `01_database.md` §3.5 の定義から逸脱しない（`project_id` のNULL許容化・`is_active` 追加は issue #10 対応として本改訂で追加）。

タスクのレスポンスには `project_is_active`（boolean、`project_id`がNULLの場合は`null`）を含める。DBに永続カラムとして保持するのではなく、`projects` とのJOINで都度取得する派生値である（§8.6参照）。

## 3. DDL

```sql
CREATE TABLE tasks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID REFERENCES projects(id) ON DELETE SET NULL,
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
    due_at       TIMESTAMPTZ,
    is_active    BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_tasks_project_status_position
        UNIQUE (project_id, status, position) DEFERRABLE INITIALLY DEFERRED
);

COMMENT ON TABLE tasks IS 'カンバンのタスク。statusで列を、positionで列内順序を表す';
COMMENT ON COLUMN tasks.project_id IS 'FK: projects.id ON DELETE SET NULL。NULLはプロジェクト未所属タスクを表す';
COMMENT ON COLUMN tasks.status IS 'todo / in_progress / done のいずれか（CHECK制約）';
COMMENT ON COLUMN tasks.position IS '同一 project_id, status 内の並び順（0起点）';
COMMENT ON COLUMN tasks.version IS '楽観的排他制御用。PATCH成功時に+1';
COMMENT ON COLUMN tasks.is_active IS '論理削除フラグ。false は DELETE /api/tasks/{id} による無効化済みを表す';

CREATE INDEX ix_tasks_assignee_id ON tasks (assignee_id);

CREATE TRIGGER trg_tasks_set_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION trg_set_updated_at();
```

`DEFERRABLE` な一意制約はPostgreSQLの仕様上、テーブル定義内の `CONSTRAINT ... UNIQUE (...) DEFERRABLE` としてのみ定義可能（`CREATE UNIQUE INDEX` では不可）なため、上記DDLのテーブル制約1本のみで表現する。

**`project_id IS NULL` 行における一意制約の限界**：PostgreSQLのUNIQUE制約はNULLを互いに異なる値として扱うため、`uq_tasks_project_status_position` は `project_id IS NULL`（プロジェクト未所属タスク）の行同士では機能せず、同一 `status`/`position` を持つ複数の未所属タスクが共存し得る。DDL自体はこの挙動を変更せず維持する（`project_id` を含む複合UNIQUE制約でNULLを同一視させるPostgreSQL標準の方法は無いため）。実用上の対応はアプリ層のadvisory lockキー生成で行う（§8.1参照）。DB制約だけでは重複を防げない点は §13 の要検討事項として明記する。

## 4. 制約・インデックス

| 種別 | 名称 | 対象カラム | 内容 | 目的（対応クエリ） |
|------|------|-----------|------|---------------------|
| PK | `tasks_pkey` | `id` | 主キー | タスク詳細取得 |
| FK | `tasks_project_id_fkey` | `project_id` | → `projects.id` `ON DELETE SET NULL` | `projects` の物理削除経路が無いため通常運用では発火しない防御的制約。意味上は「プロジェクトが消えたらタスクを未所属にする」を表す |
| FK | `tasks_assignee_id_fkey` | `assignee_id` | → `users.id` `ON DELETE SET NULL` | ユーザー削除時に担当者を自動的に未割当へ（本設計では所属解除はアプリ層UPDATEで対応。§11参照） |
| FK | `tasks_created_by_fkey` | `created_by` | → `users.id` `ON DELETE RESTRICT` | 作成者の履歴保護。ユーザーは無効化のみで物理削除しないため通常は問題にならない |
| CHECK | `ck_tasks_status` | `status` | `status IN ('todo','in_progress','done')` | 不正な状態値の混入防止 |
| CHECK | `ck_tasks_position_non_negative` | `position` | `position >= 0` | 並び順の健全性 |
| CHECK | `ck_tasks_version_positive` | `version` | `version > 0` | 楽観ロック値の健全性 |
| UNIQUE（遅延） | `uq_tasks_project_status_position` | `(project_id, status, position)` | `DEFERRABLE INITIALLY DEFERRED` | 列内重複防止。再採番中の一時的な重複をトランザクション内で許容しつつCOMMIT時に検証。**`project_id IS NULL` の行同士では機能しない**（上記コラム参照） |
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
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
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
    due_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped["Project | None"] = relationship("Project", back_populates="tasks", lazy="joined")
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
    projects |o--o{ tasks : "project_id（NULL可）"
    users |o--o{ tasks : "assignee_id（NULL可）"
    users ||--o{ tasks : "created_by"
    tasks ||--o{ task_comments : "task_id"

    tasks {
        uuid id PK
        uuid project_id FK "NULL可（未所属タスク）"
        varchar_150 title
        text description
        varchar_20 status "todo/in_progress/done"
        uuid assignee_id FK "NULL可"
        uuid created_by FK
        integer position
        integer version
        timestamptz due_at "期限日時。UTC保存、NULL可"
        boolean is_active "論理削除フラグ"
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
    done --> [*]: "DELETE /tasks/:id（論理削除）"
    todo --> [*]: "DELETE /tasks/:id（論理削除）"
    in_progress --> [*]: "DELETE /tasks/:id（論理削除）"
```

`[*]` への遷移は `is_active=false` への論理削除であり、行自体は削除されない（`status` は最後の値を保持したまま無効化される）。

### 7.2 行全体のライフサイクルと再採番の契機

```mermaid
flowchart LR
    A["POST /tasks"] --> B["advisory lock 取得<br/>(project_id, status)"]
    B --> C["fn_next_task_position で末尾position採番"]
    C --> D["INSERT tasks<br/>version=1"]
    D --> E["ROW 生成完了"]

    E --> F["PATCH /tasks/:id"]
    F -->|"status/position変更あり"| G["旧列・新列のadvisory lockをキー昇順で取得"]
    G --> H["対象行をFOR UPDATE<br/>→ version一致確認"]
    F -->|"status/position変更なし"| H
    H -->|"status/position変更あり"| I["旧列: 後続positionを-1で詰める<br/>新列: 挿入位置以降を+1でずらす"]
    H -->|"status/position変更なし"| L["UPDATE title/description/assignee/due_at<br/>version=version+1"]
    I --> J["移動対象へ最終position設定<br/>UPDATE version=version+1"]
    J --> K["COMMIT（DEFERRED制約検証）"]
    L --> K

    E --> M["DELETE /tasks/:id"]
    M --> N["UPDATE tasks SET is_active=false<br/>version=version+1"]
    N --> O["200 OK<br/>position詰め（compaction）は行わない"]

    O --> R["PATCH /tasks/:id<br/>is_active=true（再有効化）"]
    R --> S["UPDATE tasks SET is_active=true"]
```

論理削除（`is_active=false`）はDELETE時点の `position`/`status` をそのまま保持し、後続タスクの `position` 詰めは行わない。無効化されたタスクは一覧・カンバンから除外されるだけで、`position` にギャップが生じても列内の並び順（`ORDER BY position`）自体は崩れないため実用上問題ない（物理削除時代の詰め直しロジックは廃止する。§8.5参照）。

## 8. SP/FNリポジトリ契約

repositoryは下表のSP/FN呼び出しとDTO写像だけを行う。advisory lock、position再採番、version検証、通知INSERTはSP内部へ移し、repositoryで直接 `SELECT` / `INSERT` / `UPDATE` / `DELETE` を行わない。

| repository契約 | DB呼び出し | 戻り値・エラー |
|----------------|------------|----------------|
| `acquire_status_lock` / `next_position` | 単独公開しない。`sp_create_task` / `sp_update_task` 内でlock→`fn_next_task_position` | SPトランザクション内でのみ有効 |
| `insert` | `CALL sp_create_task(:project_id, :created_by, :assignee_id, :title, :body, :status, :due_at, :position, :day_start_utc, :day_end_utc, :task_id)`（`:task_id` はOUTパラメータ。DB側で `gen_random_uuid()` により採番される。日境界はAPIがUTCへ変換して渡す） | `fn_get_task(:task_id)`で作成結果を取得 |
| `get_by_id_for_update` | `SELECT fn_get_task(:task_id)` | 存在しなければ空集合。行ロックはSP内部 |
| `update_with_optimistic_lock` / reorder | `CALL sp_update_task(:task_id, :editor_id, :version, :title, :body, :status, :assignee_id, :due_at, :position, :day_start_utc, :day_end_utc)` | version不一致は `P0005 TASK_CONFLICT` |
| `deactivate` / `reactivate` | `CALL sp_deactivate_task(:task_id, :is_active)` | `is_active`だけ変更、position詰めなし |
| `list_by_project_grouped` | `SELECT fn_get_project_board(:project_id, :include_inactive)` | status/position順のFN結果を3列へ写像 |
| 横断一覧 | `SELECT fn_list_tasks(:user_id, :project_id, :status, :include_inactive, :limit, :offset)` | 権限スコープはFN内で判定 |
| カレンダー一覧 | `SELECT (task).*, project_is_active FROM fn_list_calendar_tasks(:user_id, :from_utc, :to_utc, :scope, :project_id)` | 日付範囲・scopeごとの権限・有効タスク判定はFN内で行う |

repositoryは上表のSP/FN呼び出しと戻り値のDTO写像のみを実装し、`tasks` テーブルへの直接SELECT/INSERT/UPDATE/DELETEは行わない。`sp_create_task` / `sp_update_task` の内部処理契約は[08_db_functions.md](./08_db_functions.md) §3.8を正とし、以下は advisory lock・position再採番・楽観ロックの具体的なアルゴリズムをSP内部実装の要点として補足するものである（repositoryから直接発行しない）。

### 8.1 `sp_create_task` 内部：advisory lockとposition採番

| 項目 | 内容 |
|------|------|
| ロックキー生成 | `pg_advisory_xact_lock(hashtextextended(:project_id::text || ':' || :status, 0))`。`project_id` が `NULL`（未所属タスク）の場合は固定プレースホルダ文字列 `'00000000-0000-0000-0000-000000000000'` に変換してからロックキーを生成し、未所属タスク全体を1つの仮想グループとして直列化する（`uq_tasks_project_status_position` がNULL同士の重複を検出できない問題をSP内で補う。§13参照） |
| position採番 | lock取得後に `fn_next_task_position(:project_id, :status)` を呼び、`COALESCE(MAX(position), -1) + 1` を採番する |
| INSERT | 採番したidと `position` で `tasks` へINSERTする。`version` はDB既定値 `1` を使用する |

### 8.2 `sp_update_task` 内部：行ロックと楽観ロック

| 項目 | 内容 |
|------|------|
| 行ロック | status/position変更時は対象タスクの `(project_id, status)` advisory lockをキー文字列の昇順で先に取得し、その後 `SELECT ... FROM tasks WHERE id = :task_id FOR UPDATE` 相当の行ロックをSP内で取得する。status/position変更なしでも行ロックを取得し、`version` チェックとUPDATEの間の競合を防ぐ（advisory lockは「列全体」、本ロックは「この1行」が対象という違いに注意）。行ロックを先に取得すると、同じ列への並行更新で相互に行ロックを待つdeadlockが発生し得る。 |
| 楽観ロック | `UPDATE tasks SET ..., version = version + 1 WHERE id = :id AND version = :expected_version` で行を絞り込み、影響行数0件なら `version` 不一致として `P0005 TASK_CONFLICT` を送出する |
| 実行順序 | status/positionが変わる場合は §8.3〜8.4 の再採番処理を同一トランザクションで実施してから本UPDATEを発行する |

### 8.3 `sp_update_task` 内部：同一列内での並べ替え（reorder）

| 項目 | 内容 |
|------|------|
| 前提 | `acquire_status_lock` 相当のadvisory lockを取得済みであること |
| 手順 | 1. 移動対象を退避値（`COALESCE(MAX(position), -1) + 1 + COUNT(*)`）へ一時UPDATE<br/>2. 対象位置以降を+1（前方へ移動する場合）または-1（後方へ移動する場合）でずらす<br/>3. 移動対象を最終位置へUPDATE |
| 一意制約との関係 | `uq_tasks_project_status_position` は `DEFERRABLE INITIALLY DEFERRED` のため、上記3段階の一時的な重複はCOMMITまで許容され、最終検証で解消する |

### 8.4 `sp_update_task` 内部：列間移動（move_to_status_tail）

| 項目 | 内容 |
|------|------|
| 手順 | 1. 旧列の移動対象より後続の `position` を-1で詰める<br/>2. `fn_next_task_position(:project_id, :new_status)` で新列の末尾positionを取得<br/>3. 移動対象を新列・新positionへUPDATE |
| ロック順序 | `(project_id, old_status)` と `(project_id, new_status)` のadvisory lockを**キー文字列の昇順**で取得し、デッドロックを防止する |

### 8.5 `sp_deactivate_task` 内部：論理削除・再有効化

| 項目 | 内容 |
|------|------|
| 論理削除 | `UPDATE tasks SET is_active = false, version = version + 1 WHERE id = :id`。**position の詰め（compaction）は行わない**（`status`/`position` は変更しない）。`task_comments` は `tasks` 行自体を物理削除しないため `ON DELETE CASCADE` は発火せず、無効化後もコメント履歴は参照可能なまま残る |
| 再有効化 | `UPDATE tasks SET is_active = true, version = version + 1 WHERE id = :id`。認可はAPI層（作成者/プロジェクトオーナー/admin）で事前判定する。`position`/`status` はDELETE時点の値のまま復元される |
| advisory lock | いずれも不要（`position` を変更しないため列内の直列化対象にならない） |

### 8.6 `fn_get_project_board` 内部：カンバン取得

| 項目 | 内容 |
|------|------|
| 参照SQL | `tasks` と `projects` を `LEFT JOIN` し、`project_is_active`（`projects.is_active`。`project_id` がNULLの行は `null`）を1クエリで返す。デフォルトは `is_active = true` のみを対象とし、`p_include_inactive=true` で無効化済みタスクも含める。`ORDER BY status, position ASC` |
| N+1回避 | コメント件数は `task_comment_repository.count_by_task_ids()` で別クエリ集計する |

`GET /api/tasks`（横断一覧、`fn_list_tasks`）も同様に `projects` を `LEFT JOIN` して `project_is_active` を含める。`project_id IS NULL` を指定した絞り込みは `WHERE t.project_id IS NULL AND t.created_by = :user_id`（未所属タスクは作成者本人のみ参照可）とする。

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
    TR -->|"deactivate"| T1
    TS -->|"reactivate_task"| TR
    TR -->|"reactivate"| T1

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
| Q-Task-6 | 論理削除 | `UPDATE tasks SET is_active=false WHERE id=:id` | PK | Index Scan（1行、後続position詰めは行わないためこれのみ） |
| Q-Task-7 | カンバン取得（project_is_active付き） | `tasks LEFT JOIN projects ON project_id ORDER BY status, position` | `uq_tasks_project_status_position` | Index Scan → Nested Loop（`projects` PK Lookup） |

## 11. 整合性・並行制御

| 項目 | 内容 |
|------|------|
| FK CASCADE（`project_id`） | `ON DELETE SET NULL`。`projects` の物理削除経路が無いため通常運用では発火しない防御的制約。`projects` が論理削除（`is_active=false`）されてもタスクの `project_id` は変更されない |
| FK CASCADE（`assignee_id`） | `ON DELETE SET NULL`。`users` 行自体の削除時にのみ発火。所属解除（`project_members` 削除）はDBのFKでは発火しないため、`05_table_project_members.md` §8.5 のアプリ層UPDATEで対応 |
| FK CASCADE（`created_by`） | `ON DELETE RESTRICT`。作成者の履歴を保護 |
| CHECK制約 | `ck_tasks_status`（3値のみ許可）、`ck_tasks_position_non_negative`、`ck_tasks_version_positive` |
| 一意制約（遅延） | `uq_tasks_project_status_position` は `DEFERRABLE INITIALLY DEFERRED`。再採番の中間状態（退避値経由）での一時的重複をトランザクション内で許容し、COMMIT時に最終検証する。ただし `project_id IS NULL` の行同士では機能しないため、advisory lockキー生成でNULLを固定プレースホルダに変換して直列化することで実質的な衝突を防ぐ（§8.1、§13） |
| 論理削除（`is_active`） | `DELETE /api/tasks/{id}` は `UPDATE tasks SET is_active=false` のみを発行し、`position` の詰め（compaction）は行わない。再有効化は `PATCH /api/tasks/{id}` に `is_active=true` を指定して行う（作成者/プロジェクトオーナー/adminのみ） |
| 楽観ロック（`version`） | `PATCH /tasks/{id}` は `version` を必須パラメータとし、`UPDATE ... WHERE id=:id AND version=:expected_version` で一致した場合のみ更新、成功時に `version+1`。不一致時は影響行数0件を検知して `409 TASK_CONFLICT` |
| advisory lock | `pg_advisory_xact_lock(hashtextextended(project_id \|\| ':' \|\| status, 0))` で `(project_id, status)` 単位に position 採番・再採番を直列化。`_xact_` 系のためトランザクション終了で自動解放。列間移動時は旧列・新列のロックをキー文字列の昇順で取得しデッドロックを回避 |
| トランザクション境界 | 作成：lock取得→採番→INSERTを1トランザクション。更新（status/position変更あり）：対象列のadvisory lock取得→`FOR UPDATE`→version確認→再採番UPDATE群→楽観ロックUPDATEを1トランザクション。論理削除・再有効化：`UPDATE tasks SET is_active=...` 単文（position詰めを行わないためadvisory lock・複数UPDATEは不要） |
| ロックの二重性 | 行ロック（`FOR UPDATE`/`version`列）は「この1タスク」、advisory lockは「同じ列の複数タスク」の同時更新を防ぐ。目的が異なるため併用する |

## 12. テスト設計

| No | 区分 | ケース | 期待結果 | テスト名案 |
|----|------|--------|----------|------------|
| T-1 | 制約違反（CHECK） | `status='invalid'` / `position=-1` でINSERT/UPDATEを試みる | それぞれ `ck_tasks_status` / `ck_tasks_position_non_negative` 違反でDBエラー | `test_task_check_constraints_reject_invalid_values` |
| T-2 | 制約違反（UNIQUE） | advisory lockを取らずに同一 `(project_id, status, position)` を持つ2行を並行INSERT | 一意制約違反、またはadvisory lockにより直列化されて後続が採番し直される | `test_concurrent_task_creation_serialized_by_advisory_lock` |
| T-3 | 論理削除の非連鎖確認 | プロジェクトを `DELETE /api/projects/{id}` で無効化（論理削除）する | 配下の `tasks` は削除も `project_id` NULL化もされず、`is_active` も変化しない | `test_project_deactivation_does_not_affect_tasks` |
| T-3' | 防御的制約の確認 | （実運用では到達しない）テスト内で直接 `DELETE FROM projects` を発行する | 配下の `tasks.project_id` が `SET NULL` になり、`task_comments` はCASCADE削除される | `test_direct_physical_project_delete_sets_task_project_id_null` |
| T-4 | 並行更新（楽観ロック） | 2クライアントが同じ `version` を元に同時 `PATCH` する | 先着のみ成功し `version+1`、後着は `409 TASK_CONFLICT` | `test_patch_task_version_conflict_returns_409` |
| T-5 | 並び順 | 列内の中間位置へタスクを移動する | 移動元より後ろの要素が詰まり、移動先以降がずれ、`position` に欠番・重複が生じない | `test_reorder_within_status_keeps_positions_contiguous` |
| T-6 | 列間移動 | `todo` → `in_progress` へ `position` 指定なしで移動する | 旧列の後続が詰まり、新列の末尾に採番される | `test_move_status_appends_to_tail_of_new_column` |
| T-7 | 論理削除時の非compaction確認 | 列の中間のタスクを `DELETE /tasks/{id}` で論理削除する | `is_active=false` になるのみで、後続タスクの `position` は詰められずギャップが残る | `test_deactivate_task_does_not_compact_positions` |
| T-8 | advisory lock | 同一 `(project_id, status)` への複数の作成・移動リクエストを並行実行 | 採番・並べ替えが直列化され、`uq_tasks_project_status_position` 違反が発生しない | `test_advisory_lock_prevents_position_collision_under_concurrency` |
| T-8' | advisory lock（未所属タスク） | `project_id IS NULL` の複数タスクを同一 `status` へ並行作成する | プレースホルダキーにより直列化され、`position` の実質的な重複が生じない | `test_advisory_lock_serializes_unassigned_tasks` |
| T-9 | FK | `assignee_id` に非メンバーのユーザーIDを指定して作成/更新する | アプリ層バリデーションで拒否（`422`または`400`。DB制約ではなくサービス層検証） | `test_assign_non_member_user_rejected` |
| T-10 | デフォルト値 | `status`/`position`/`version`/`is_active` を指定せずにINSERTする | `status='todo'`、`position` は `next_position` 経由の採番値、`version=1`、`is_active=true` となる | `test_create_task_defaults_applied` |
| T-11 | 再有効化 | 作成者/プロジェクトオーナー/admin が無効化済みタスクに `PATCH /tasks/{id}` で `is_active=true` を指定 | `is_active` が `true` に戻り、`position`/`status` はDELETE時点の値のまま | `test_reactivate_task_sets_is_active_true` |
| T-12 | project_id NULL許容 | `project_id` を指定せずに `POST /api/tasks` でタスクを作成する | `tasks.project_id` が `NULL` で作成され、FK違反にならない | `test_create_task_without_project_succeeds` |
| T-13 | project_is_active | 無効化済みプロジェクト配下の有効タスクを取得する | レスポンスの `project_is_active` が `false`、タスク自体は一覧・カンバンに表示される | `test_task_response_includes_project_is_active` |
| T-14 | project_is_active（未所属） | `project_id IS NULL` のタスクを取得する | レスポンスの `project_is_active` が `null` | `test_task_response_project_is_active_null_when_unassigned` |
| T-15 | 一覧デフォルト絞り込み | `GET /api/tasks` をデフォルトパラメータで実行 | `is_active=true` のタスクのみ返る | `test_list_tasks_default_excludes_inactive` |

## 13. 不明点・要検討事項

- `position` のDB既定値は `01_database.md` の定義上 `0` だが、実運用では常に `fn_next_task_position` 経由で採番するため素の既定値 `0` が使われる場面は基本的に無い（DBスキーマ上の安全弁としてのみ機能する）。この理解でよいか要確認。
- advisory lockのキー生成方法（`hashtextextended(project_id || ':' || status, 0)`）は基本設計に具体的な実装が無いため、本書での具体化である。`pg_advisory_xact_lock` は単一bigint引数版を用いる想定だが、2引数版（`(classid, objid)` 形式）を用いるかは実装時に確定すること（要検討）。
- 列間移動時のロック取得順序（キー文字列の昇順固定によるデッドロック回避）は基本設計に記載がなく、本書での具体化である。
- **`project_id IS NULL` 行に対するUNIQUE制約の限界**：`uq_tasks_project_status_position` はPostgreSQLの仕様上NULL同士を区別するため、未所属タスク間では機能しない。issue #40で、advisory lockキー生成でNULLを固定プレースホルダ（`'00000000-0000-0000-0000-000000000000'`）に変換して直列化する現行方針（アプリ層での直列化）を維持することで確定した。advisory lockを経由しない経路が将来追加された場合の対応は、そのとき改めて検討する。
- `start_at`/`end_at` を持つ `projects` の期間外に作成された未所属タスクの扱い（業務ロジック上の制約を設けるか）は基本設計に明記がなく要検討（[`04_table_projects.md`](./04_table_projects.md) §13も参照）。
- `GET /api/tasks`（横断一覧）における未所属タスクの参照範囲は、issue #40で「作成者本人のみ」の現行方針のまま確定した。
