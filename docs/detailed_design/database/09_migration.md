# 09 Alembicマイグレーション運用詳細設計

## 関連ドキュメント

- [../../basic_design/01_database.md](../../basic_design/01_database.md)（§1 マイグレーション方針、§6 マイグレーション方針図）
- [../../basic_design/06_infra_cicd.md](../../basic_design/06_infra_cicd.md)（§4 環境変数、§5 CI設計、§6 CD設計、§8 運用時の確認事項）
- [08_db_functions.md](./08_db_functions.md)（本ファイルが適用するDB関数・プロシージャ）
- [00_policy.md](./00_policy.md)（命名規約・共通カラム方針）
- [../infra/05_ci_workflow.md](../infra/05_ci_workflow.md)（CIでのマイグレーション適用手順）
- [../infra/02_dockerfile_api.md](../infra/02_dockerfile_api.md)（起動時 `alembic upgrade head` の実行箇所）
- [../batch/02_due_notification_job.md](../batch/02_due_notification_job.md)（通知保持期間パージの呼び出し元）
- [../log/00_history.md](../log/00_history.md)（履歴の記録契機・保持期間）

## 1. 概要

`basic_design/01_database.md` §1 の方針「`db/migrations/` は SQL の手動DDL置き場、`api/alembic/versions/` が実行される正」を受け、本ファイルでは Alembic による実際のマイグレーション運用（初期リビジョン構成・シードデータ・CI/テストでの適用手順・ロールバック方針・命名規約）を具体化する。

| 項目 | 内容 |
|------|------|
| ツール | Alembic（SQLAlchemy 2.x 用） |
| 設定ファイル | `api/alembic.ini` / `api/alembic/env.py` |
| 接続先 | `env.py` 内で `DATABASE_URL`（環境変数）から取得。`alembic.ini` にはURLをハードコードしない |
| `db/migrations/` の位置づけ | 参考用の手動DDLスナップショット置き場。CIやアプリ起動では**参照しない**（`api/alembic/versions/` のみが実行対象） |
| オートジェネレート | `alembic revision --autogenerate -m "<message>"` でモデル差分から下書きを生成し、CHECK制約・関数・トリガ適用は手動でリビジョンに追記する（`basic_design/01_database.md` §6） |
| backendのbuild context | リポジトリルート（`docker build -f api/Dockerfile .`）。`api/`だけをcontextにせず、`db/functions/`・`db/procedures/`をruntimeイメージへ含める |
| runtime配置 | `api/`は`/app/api/`、SQL資材は`/app/db/functions/`・`/app/db/procedures/`へ配置する。Alembicリビジョンからは`Path(__file__).resolve().parents[3] / "db"`で参照する |

## 2. `api/alembic/versions/` ディレクトリ構成と初期リビジョン

### 2.1 リビジョンの分割方針

1テーブルにつき1リビジョンとせず、初期構築は「拡張有効化 → テーブル作成 → 関数・トリガ適用 → シードデータ」の順で意味のある単位に分割する。以降の変更は変更内容ごとに1リビジョン。

| リビジョンファイル（例） | 内容 |
|--------------------------|------|
| `0001_enable_extensions.py` | `CREATE EXTENSION IF NOT EXISTS pgcrypto` |
| `0002_create_users_table.py` | `users` テーブル、関連インデックス・CHECK制約 |
| `0003_create_oauth_accounts_table.py` | `oauth_accounts` テーブル |
| `0004_create_login_history_table.py` | `login_history` テーブル |
| `0005_create_auth_user_functions_and_triggers.py` | auth/usersの参照FN・更新SP、ログイン履歴トリガ |
| `0006_create_projects_table.py` | `projects` テーブル |
| `0007_create_project_members_table.py` | `project_members` テーブル（複合PK） |
| `0008_create_tasks_table.py` | `tasks` テーブル（`DEFERRABLE` 一意制約含む） |
| `0009_create_task_comments_table.py` | `task_comments` テーブル |
| `0010_create_project_task_functions_and_triggers.py` | project/task/commentの参照FN・更新SP、updated_atトリガ |
| `0011_create_notifications_table.py` | `notifications` テーブル、制約・インデックス、`sp_purge_notifications` |
| `0012_create_api_history_table.py` | `api_history` テーブル |
| `0013_create_batch_history_table.py` | `batch_history` テーブル |
| `0014_create_notification_history_functions_and_triggers.py` | 通知・履歴の参照FN、既読・パージSP、履歴トリガ |
| `0015_create_admin_functions.py` | admin用参照FN・更新SP |
| `0016_update_task_notification_procedures.py` | task作成・更新SPへAPI計算のUTC日境界を追加し、当日期限通知を統合 |
| `0017_add_login_history_column_comments.py` | `login_history`のテーブル・全カラムコメントを付与 |
| `0018_align_login_history_column_comments.py` | #276で付与した`id`コメントを設計書の定義に合わせて削除 |
| `0019_update_fn_list_notifications_return_type.py` | `fn_list_notifications`の戻り値をtask情報・total_countを含む`TABLE`型へ変更（`DROP FUNCTION`後に再作成）し、`fn_count_notifications`を新設 |
| `0020_add_admin_list_total_count_and_not_found.py` | admin一覧FNの総件数フォールバックと更新SPの対象不存在・OUT値を追加 |
| `0021_return_notification_read_results.py` | 通知既読SPに既読日時・更新件数のOUT値を追加 |
| `0022_add_calendar_task_function.py` | カレンダー表示用`fn_list_calendar_tasks`を追加 |

**要検討**：上記のリビジョン分割・命名例（`0001_...` 等の連番接頭辞）は本詳細設計での具体化であり、基本設計に明記された正の構成ではない。実装時にAlembicの自動生成ハッシュIDとの整合をどう取るか（`down_revision` チェーンの実ファイル名）は実装担当の裁量とする。

### 2.2 リビジョンチェーン図

```mermaid
flowchart LR
    R1["0001<br/>拡張有効化"] --> R2["0002<br/>users"]
    R2 --> R3["0003<br/>oauth_accounts"]
    R3 --> R4["0004<br/>login_history"]
    R4 --> R5["0005<br/>auth SP・FN"]
    R5 --> R6["0006<br/>projects"]
    R6 --> R7["0007<br/>project_members"]
    R7 --> R8["0008<br/>tasks"]
    R8 --> R9["0009<br/>task_comments"]
    R9 --> R10["0010<br/>project/task/comment<br/>SP・FN"]
    R10 --> R11["0011<br/>notifications"]
    R11 --> R12["0012<br/>api_history"]
    R12 --> R13["0013<br/>batch_history"]
    R13 --> R14["0014<br/>通知・履歴<br/>SP・FN"]
    R14 --> R15["0015<br/>admin SP・FN"]
    R15 --> R16["0016<br/>task通知SP更新"]
    R16 --> R17["0017<br/>login_historyコメント"]
    R17 --> R18["0018<br/>login_historyコメント整合"]
    R18 --> R19["0019<br/>fn_list_notifications<br/>戻り値変更"]
    R19 --> R20["0020<br/>admin一覧・更新SP整合"]
    R20 --> R21["0021<br/>通知既読結果"]
    R21 --> R22["0022<br/>カレンダータスクFN"]
```

### 2.7 SP/FN適用順序

`0010`、`0014`〜`0016`、`0019`、`0020`、`0021`は、対象テーブルのDDLと既存のUUID/CHECK/FK定義が完了した後に適用する。`0016`では、`0010`が作成するtask SPの旧シグネチャを削除して、`db/procedures/`の現行SQLを再適用する。`0019`では、`0014`が作成した`fn_list_notifications`（戻り値`SETOF notifications`）を`DROP FUNCTION`で削除してから`TABLE(notification notifications, task_title VARCHAR, task_project_id UUID, total_count BIGINT)`を返す現行定義で再作成する。PostgreSQLは`CREATE OR REPLACE FUNCTION`で既存関数の戻り値型を変更できないため、戻り値型を変えるリビジョンは必ずDROP→CREATEの手順を取る。各リビジョンはSQL資材を読み込んで作成し、repositoryの直接CRUDを追加しない。

| リビジョン | 依存するテーブル | 適用内容 |
|------------|------------------|----------|
| `0010` | `projects`, `tasks`, `task_comments` | project/task/commentの参照FN・更新SP。通知テーブル作成前のためtask SPはlegacy SQLを使用 |
| `0014` | `notifications`, `api_history`, `batch_history` | 通知・履歴の参照FN、既読・パージSP、履歴トリガ |
| `0015` | `users`, `projects`, `login_history` | admin参照FN・更新SP |
| `0016` | `notifications`, `tasks` | APIから受け取るUTC日境界でtask SPの当日期限通知を判定。downgradeではlegacy task SPへ戻す |
| `0019` | `notifications`, `tasks` | `fn_list_notifications`をDROP FUNCTIONしてtask情報・total_countを返す現行定義へ再作成し、`fn_count_notifications`を新設。downgradeではlegacy定義（`SETOF notifications`）へ戻す |
| `0020` | `users`, `projects`, `login_history` | admin一覧の総件数・更新SPの対象不存在とOUT値を現行定義へ再作成。downgradeではlegacy定義へ戻す |
| `0021` | `notifications` | 個別既読の`p_read_at`、全既読の`p_updated_count`をOUTで返すSPへ再作成。downgradeでは旧SPへ戻す |
| `0022` | `projects`, `tasks` | `fn_list_calendar_tasks`を追加し、APP_TIMEZONEから変換したUTC範囲・scope・有効状態で期限タスクを抽出 |

関数・プロシージャのDROPは依存するAPIが停止している環境でのみ行う。production CDではdowngradeを実行しない。

### 2.3 各リビジョンの構造（例：`0009_create_functions_and_triggers.py`）

```python
"""create functions and triggers

Revision ID: 0009
Revises: 0008
"""
from pathlib import Path
from alembic import op

FUNCTIONS_DIR = Path(__file__).resolve().parents[3] / "db" / "functions"

def upgrade() -> None:
    op.execute((FUNCTIONS_DIR / "trg_set_updated_at.sql").read_text())
    for table in ("users", "projects", "tasks", "task_comments"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_set_updated_at "
            f"BEFORE UPDATE ON {table} FOR EACH ROW "
            f"EXECUTE FUNCTION trg_set_updated_at();"
        )
    op.execute((FUNCTIONS_DIR / "fn_is_project_member.sql").read_text())
    op.execute((FUNCTIONS_DIR / "fn_next_task_position.sql").read_text())
    op.execute((FUNCTIONS_DIR.parent / "procedures" / "sp_purge_login_history.sql").read_text())

def downgrade() -> None:
    op.execute("DROP PROCEDURE IF EXISTS sp_purge_login_history(INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS fn_next_task_position(UUID, VARCHAR)")
    op.execute("DROP FUNCTION IF EXISTS fn_is_project_member(UUID, UUID)")
    for table in ("users", "projects", "tasks", "task_comments"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_set_updated_at ON {table}")
    op.execute("DROP FUNCTION IF EXISTS trg_set_updated_at()")
```

`db/functions/*.sql` / `db/procedures/*.sql` は手動DDL置き場（内容の正）であり、Alembicリビジョンは `op.execute()` でその内容を読み込んで適用する橋渡し役に徹する。SQL本体をリビジョンファイル内に直接ハードコードで重複させない。

### 2.4 `0011_create_notifications_table.py`（通知機能）

`0011`は既存データを失わない順序で適用する。まず`tasks.due_at TIMESTAMPTZ NULL`を追加し、既存の`tasks.due_date`を`APP_TIMEZONE`の00:00としてUTCへ変換してから旧列を削除する。その後に`notifications`、外部キー、CHECK制約、`uq_notifications_user_dedupe`、一覧・未読件数用インデックスを作成し、最後に`sp_purge_notifications`を適用する。

```python
import os
from pathlib import Path
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

def upgrade() -> None:
    op.add_column("tasks", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        sa.text(
            "UPDATE tasks SET due_at = timezone(:app_timezone, due_date::timestamp) "
            "WHERE due_date IS NOT NULL"
        ).bindparams(app_timezone=os.environ["APP_TIMEZONE"])
    )
    op.drop_column("tasks", "due_date")
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="SET NULL")),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("dedupe_key", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("type IN ('due_soon_batch','due_today_created','due_today_updated')", name="ck_notifications_type"),
        sa.UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_notifications_user_unread", "notifications", ["user_id"], postgresql_where=sa.text("read_at IS NULL"))
    procedures_dir = Path(__file__).resolve().parents[3] / "db" / "procedures"
    op.execute((procedures_dir / "sp_purge_notifications.sql").read_text())

def downgrade() -> None:
    op.execute("DROP PROCEDURE IF EXISTS sp_purge_notifications(INTEGER)")
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_column("tasks", "due_at")
```

`downgrade()`は通知履歴と期限日時を削除するため、本番CDのロールバックでは実行しない（§5）。

### 2.5 `0012_create_history_tables.py`（API・batch履歴）

`api_history`と`batch_history`を作成し、両テーブルの制約・検索用インデックス・`sp_purge_api_history`・`sp_purge_batch_history`を適用する。`batch_history`の`updated_at`には既存の`trg_set_updated_at`を適用する。`downgrade()`では両テーブルとプロシージャを削除するため、本番では実行しない。

詳細なDDLは [11_table_api_history.md](./11_table_api_history.md) と [12_table_batch_history.md](./12_table_batch_history.md)を正とし、リビジョン内に重複してハードコードしない。

### 2.6 `0013_alter_projects_tasks_lifecycle.py`（プロジェクト論理削除・期間、タスクの任意紐付け）

issue #10（プロジェクトの論理削除・開始終了日時、タスクのプロジェクト任意紐付け）に対応するリビジョン。`projects`/`tasks` 双方のスキーマ変更を1リビジョンにまとめる（同一issueの一体の変更のため分割しない）。適用順は「`projects` へのカラム追加・CHECK制約 → `tasks.project_id` のFK再作成 → `tasks` へのカラム追加」とし、`tasks.project_id` を先にNULL許容へ変更してから既存FKを一度落として `ON DELETE SET NULL` で貼り直す。

```python
"""alter projects and tasks lifecycle (issue #10)

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op

def upgrade() -> None:
    # projects: 論理削除フラグ・開始終了日時
    op.add_column("projects", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("projects", sa.Column("start_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("projects", sa.Column("end_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_projects_period",
        "projects",
        "start_at IS NULL OR end_at IS NULL OR end_at >= start_at",
    )

    # tasks.project_id: NOT NULL解除 + FKをON DELETE SET NULLへ付け替え
    op.alter_column("tasks", "project_id", nullable=True)
    op.drop_constraint("tasks_project_id_fkey", "tasks", type_="foreignkey")
    op.create_foreign_key(
        "tasks_project_id_fkey", "tasks", "projects",
        ["project_id"], ["id"], ondelete="SET NULL",
    )

    # tasks: 論理削除フラグ
    op.add_column("tasks", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))

def downgrade() -> None:
    op.drop_column("tasks", "is_active")

    op.drop_constraint("tasks_project_id_fkey", "tasks", type_="foreignkey")
    op.create_foreign_key(
        "tasks_project_id_fkey", "tasks", "projects",
        ["project_id"], ["id"], ondelete="CASCADE",
    )
    op.alter_column("tasks", "project_id", nullable=False)

    op.drop_constraint("ck_projects_period", "projects", type_="check")
    op.drop_column("projects", "end_at")
    op.drop_column("projects", "start_at")
    op.drop_column("projects", "is_active")
```

`downgrade()` は `tasks.project_id` を `NOT NULL` に戻す前提として、適用時点で `project_id IS NULL` の行が存在しないことを要求する（存在すればNOT NULL制約違反で失敗する）。本番運用では §5 の方針どおりdowngradeは実施しないため、ローカル開発・CI健全性検証でのみ使用する想定。既存データに未所属タスクが作成された後にこのリビジョンをdowngradeする運用上の対応（強制的にダミー`project_id`を割り当てる等）は基本設計に明記がなく要検討（§9参照）。

## 3. シードデータ（初期adminユーザー）

| 項目 | 内容 |
|------|------|
| 対象リビジョン | `0010_seed_initial_admin.py` |
| 取得元 | `INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD`（環境変数、`basic_design/06_infra_cicd.md` §4.5） |
| パスワードハッシュ化 | リビジョン内で argon2id ハッシュ化してから `INSERT`（平文を保存しない）。ハッシュパラメータは `ARGON2_TIME_COST` / `ARGON2_MEMORY_COST` / `ARGON2_PARALLELISM` に準拠 |
| `role` | `'admin'` |
| `email_verified_at` | シード時点の `now()` を設定（確認メールなしでログイン可能にする。`basic_design/06_infra_cicd.md` §4.5） |
| `is_active` | `true` |
| 冪等性 | `INSERT ... ON CONFLICT (lower(username)) DO NOTHING` とし、既存admin環境への再適用でエラーにならないようにする |

```python
"""seed initial admin user

Revision ID: 0010
Revises: 0009
"""
import os
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    email = os.environ["INITIAL_ADMIN_EMAIL"]
    username = os.environ["INITIAL_ADMIN_USERNAME"]
    password_hash = _hash_password(os.environ["INITIAL_ADMIN_PASSWORD"])
    op.execute(
        sa.text(
            """
            INSERT INTO users (username, email, password_hash, role,
                                is_active, email_verified_at, created_at, updated_at)
            VALUES (:username, :email, :password_hash, 'admin',
                    true, now(), now(), now())
            ON CONFLICT (lower(username)) DO NOTHING
            """
        ).bindparams(username=username, email=email, password_hash=password_hash)
    )

def downgrade() -> None:
    op.execute(sa.text("DELETE FROM users WHERE username = :u")
               .bindparams(u=os.environ["INITIAL_ADMIN_USERNAME"]))
```

`_hash_password` は `core/security.py` 相当の argon2 ラッパーをリビジョン内で直接importして使う想定。ハードコードした固定値ではなく、実行時の環境変数から都度生成する。

`INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` のいずれかが未設定または空文字の場合は、`os.environ[...]` と起動時バリデーションで失敗させる。seedをスキップして起動することはなく、CI環境では専用のダミーSecretを必ず注入する。

## 4. 適用手順

### 4.1 各環境での適用フロー

```mermaid
flowchart LR
    A["ORMモデル変更<br/>api/app/models/*.py"] --> B["alembic revision<br/>--autogenerate"]
    B --> C["生成versionをレビュー<br/>CHECK制約・関数適用を手動追記"]
    C --> D{"適用先環境"}
    D -->|"ローカル/CD"| E["backendコンテナ<br/>エントリポイントで自動実行"]
    D -->|"CI"| F["services起動後に<br/>ジョブステップで明示実行"]
    E --> G["alembic upgrade head"]
    F --> G
    G --> H["pytest（実DB接続）"]
```

### 4.2 環境別の適用方法

| 環境 | 適用トリガ | 実行者 | 補足 |
|------|-----------|--------|------|
| ローカル開発 | `docker compose up` 時、backendコンテナのエントリポイント | Docker Compose | `basic_design/06_infra_cicd.md` §3.1「エントリポイント：`alembic upgrade head` → `uvicorn ...`」 |
| CI（`backend-test`） | ジョブステップとして明示実行 | GitHub Actions | `services` で `postgres:17` / `redis:8` を起動後、`alembic upgrade head` → `pytest --cov=app --cov-report=xml`（`basic_design/06_infra_cicd.md` §5.2/5.3） |
| CD（本番相当） | `docker compose pull && docker compose up -d` 後、backendコンテナ起動時に自動実行 | self-hosted runner | 失敗時はbackendコンテナが起動失敗となり、deployジョブは失敗扱い（§5.2参照） |

### 4.3 CIでの適用コマンド例（`ci.yml` 抜粋、参考）

```yaml
- name: Run migrations
  working-directory: api
  env:
    DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/cerberus_test
    INITIAL_ADMIN_EMAIL: ci-admin@example.com
    INITIAL_ADMIN_USERNAME: ci_admin
    INITIAL_ADMIN_PASSWORD: ${{ secrets.CI_INITIAL_ADMIN_PASSWORD }}
  run: alembic upgrade head
```

環境変数はすべて `basic_design/06_infra_cicd.md` §4 に列挙された変数名をそのまま使用し、値をリビジョンやワークフローにハードコードしない。

## 5. ロールバック方針

| 項目 | 方針 |
|------|------|
| `downgrade()` の記述義務 | 学習目的のため全リビジョンで**必ず記述する**（`basic_design/01_database.md` §6） |
| 本番運用でのDB downgrade | 実施しない。`basic_design/06_infra_cicd.md` §8「マイグレーション失敗時」：アプリイメージだけを直前タグへ戻し、**適用済みmigrationを自動downgradeしない** |
| ロールバック対象 | アプリケーションイメージ（`sha-{短縮SHA}` タグ）のみ。DBスキーマは前進のみ |
| 不可逆変更への対応 | expand/contract方式で段階適用する（列追加→アプリ両対応デプロイ→旧列削除、のように分割） |
| `downgrade()` の用途 | ローカル開発での試行錯誤時の巻き戻し、およびCI上でのマイグレーション健全性検証（upgrade→downgrade→upgradeが通ることの確認）に限定して使用する |
| マイグレーション失敗時の一次対応 | backendコンテナは起動失敗のまま停止させる。運用者がDBバックアップとログを確認し原因を修正してから再実行する（自動リトライやスキップは行わない） |

### 5.1 CI上での健全性検証（推奨手順、要検討）

```mermaid
sequenceDiagram
    autonumber
    participant CI as CIジョブ
    participant DB as PostgreSQL(テスト用)
    CI->>DB: alembic upgrade head
    CI->>DB: alembic downgrade -1
    CI->>DB: alembic upgrade head
    CI->>CI: pytest 実行
```

**要検討**：upgrade→downgrade→upgradeの往復検証を `ci.yml` の必須ステップにするかは基本設計に明記がなく要検討。カバレッジ・実行時間とのトレードオフのため、本設計では「推奨」に留める。

## 6. 命名規約

| 対象 | 規約 | 例 |
|------|------|-----|
| リビジョンファイル | `alembic revision --autogenerate -m "<snake_case英語 or 日本語要約>"` で生成される自動ハッシュIDに、レビュー時に意味のある `-m` メッセージを必ず付与する | `alembic revision --autogenerate -m "add tasks table"` |
| リビジョンメッセージ | 変更内容を1行で要約（英語推奨、動詞から開始） | `create users table`, `add position unique constraint to tasks` |
| DB関数 | `fn_<動詞または対象>`（[08_db_functions.md](./08_db_functions.md) 準拠） | `fn_next_task_position` |
| トリガ関数 | `trg_<対象>` | `trg_set_updated_at` |
| トリガ本体 | `trg_<table>_<契機>` | `trg_users_set_updated_at` |
| プロシージャ | `sp_<動詞>` | `sp_purge_login_history` |
| インデックス | `ix_<table>_<column(s)>` | `ix_tasks_assignee_id` |
| 一意制約 | `uq_<table>_<column(s)>` | `uq_tasks_project_status_position` |
| 外部キー制約 | Alembic自動命名（`fk_<table>_<column>_<ref_table>`）に委ねる。手動追記時も同形式に揃える | `fk_tasks_project_id_projects` |
| CHECK制約 | `ck_<table>_<内容>` | `ck_tasks_status_valid` |

命名規約の詳細（テーブル・カラム側）は [00_policy.md](./00_policy.md) を正とし、本節はマイグレーション成果物（リビジョン・DBオブジェクト）固有の命名のみを扱う。

## 7. 関数相関図（マイグレーション適用の流れ）

```mermaid
flowchart LR
    MODEL["api/app/models/*.py"] -->|"autogenerate"| REV["api/alembic/versions/*.py"]
    SQLFILES["db/functions/*.sql<br/>db/procedures/*.sql<br/>（手動DDL置き場）"] -->|"op.execute()で読み込み"| REV
    REV -->|"alembic upgrade head"| ENTRY["backendエントリポイント<br/>または CIステップ"]
    ENTRY --> PG[("PostgreSQL")]
    ENTRY -->|"失敗時"| FAIL["backendコンテナ起動失敗<br/>/ CIジョブ失敗"]
```

## 8. テスト設計

| No | 区分 | ケース | 期待結果 | テスト名案 |
|----|------|--------|----------|-----------|
| 1 | 正常系 | クリーンDBに対して `alembic upgrade head` を実行 | 全リビジョンが成功し、全テーブル・関数・トリガが作成される | `test_migration_upgrade_head_succeeds` |
| 2 | 正常系 | `alembic upgrade head` 後、初期adminユーザーが1件存在する | `role='admin'`, `is_active=true`, `email_verified_at` が非NULL | `test_migration_seed_initial_admin_created` |
| 3 | 冪等性 | シードリビジョンを重複適用（同一usernameで再実行相当） | エラーにならず重複行が作成されない | `test_migration_seed_idempotent` |
| 4 | 異常系 | `INITIAL_ADMIN_PASSWORD` 等の環境変数が未設定の状態でシードリビジョンを適用 | 明示的なエラーで失敗する（サイレントスキップしない） | `test_migration_seed_missing_env_fails` |
| 5 | 正常系 | 各リビジョンの `downgrade()` を最新から1段ずつ実行し全て `0001` まで戻せる | エラーなく完了し、DBオブジェクトが全て削除される | `test_migration_downgrade_full_chain` |
| 6 | 正常系 | `upgrade head` → `downgrade -1` → `upgrade head` の往復 | 最終的なスキーマが初回 `upgrade head` と一致する | `test_migration_upgrade_downgrade_upgrade_roundtrip` |
| 7 | 正常系 | CI環境（`AUTH_MODE` matrix: session / jwt）でそれぞれマイグレーション適用後にpytestが通る | 両方式で成功する | `test_migration_ci_matrix_session_and_jwt` |
| 8 | 正常系 | 関数・トリガ適用リビジョン後、`UPDATE users` で `updated_at` が更新される | [08_db_functions.md](./08_db_functions.md) のテストと重複しない範囲でマイグレーション経由の適用を確認 | `test_migration_functions_applied_correctly` |
| 9 | 正常系 | `0012`適用後にAPI・batch履歴テーブルとプロシージャが存在する | 全制約・インデックス・パージプロシージャが作成される | `test_migration_history_tables_created` |
| 10 | 正常系 | `0012`のupgrade→downgrade | 履歴テーブル・プロシージャが削除される | `test_migration_history_downgrade` |
| 11 | 正常系 | `0013`適用後、`projects`に`is_active`/`start_at`/`end_at`、`tasks`に`is_active`が存在し、`tasks.project_id`がNULL許容になっている | 全カラム・`ck_projects_period`・`tasks_project_id_fkey`（`ON DELETE SET NULL`）が期待どおり作成される | `test_migration_0013_columns_and_constraints_created` |
| 12 | 正常系 | `0013`適用後に`project_id`をNULLとしてタスクをINSERTする | NOT NULL制約違反にならず成功する | `test_migration_0013_allows_null_project_id_task` |
| 13 | 異常系 | `project_id IS NULL`の行が存在する状態で`0013`をdowngradeする | `NOT NULL`制約違反で失敗する（想定どおりの挙動であることの確認） | `test_migration_0013_downgrade_fails_with_unassigned_tasks` |
| 14 | 正常系 | 未所属タスクが存在しない状態で`0013`のupgrade→downgrade→upgradeを実行する | 最終的なスキーマが初回`upgrade head`と一致する | `test_migration_0013_roundtrip_without_unassigned_tasks` |

## 9. 不明点・要検討事項

- リビジョンファイルの連番接頭辞（`0001_`等）は本詳細設計での具体化であり、Alembic自動生成のハッシュIDとの命名整合方法（`down_revision` の実運用）は実装担当の裁量とする。
- ~~`INITIAL_ADMIN_PASSWORD` 等が未設定の場合の挙動~~ → [`requirements/security_business_rules.md`](../../requirements/security_business_rules.md)で起動失敗が確定済み。本書§5の記述はこれと一致している。
- CI上でのupgrade/downgrade往復健全性検証を必須ステップにするかは基本設計に記載がなく要検討（実行時間とのトレードオフ）。
- `db/migrations/` （手動DDL置き場）と `api/alembic/versions/` の内容をどの頻度・手順で同期させるか（自動生成スクリプトの要否）は基本設計に明記がなく要検討。
- `0013`のdowngradeで`project_id IS NULL`の行が既に存在する場合の運用対応（強制的にダミー`project_id`を割り当てる、downgrade自体を禁止する等）は基本設計に明記がなく要検討。本設計では「本番ではdowngradeを実施しない」（§5）の方針に委ねる形とした。
