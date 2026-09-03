# 09 Alembicマイグレーション運用詳細設計

## 関連ドキュメント

- [../../basic_design/01_database.md](../../basic_design/01_database.md)（§1 マイグレーション方針、§6 マイグレーション方針図）
- [../../basic_design/06_infra_cicd.md](../../basic_design/06_infra_cicd.md)（§4 環境変数、§5 CI設計、§6 CD設計、§8 運用時の確認事項）
- [08_db_functions.md](./08_db_functions.md)（本ファイルが適用するDB関数・プロシージャ）
- [00_policy.md](./00_policy.md)（命名規約・共通カラム方針）
- [../infra/05_ci_workflow.md](../infra/05_ci_workflow.md)（CIでのマイグレーション適用手順）
- [../infra/02_dockerfile_api.md](../infra/02_dockerfile_api.md)（起動時 `alembic upgrade head` の実行箇所）

## 1. 概要

`basic_design/01_database.md` §1 の方針「`db/migrations/` は SQL の手動DDL置き場、`api/alembic/versions/` が実行される正」を受け、本ファイルでは Alembic による実際のマイグレーション運用（初期リビジョン構成・シードデータ・CI/テストでの適用手順・ロールバック方針・命名規約）を具体化する。

| 項目 | 内容 |
|------|------|
| ツール | Alembic（SQLAlchemy 2.x 用） |
| 設定ファイル | `api/alembic.ini` / `api/alembic/env.py` |
| 接続先 | `env.py` 内で `DATABASE_URL`（環境変数）から取得。`alembic.ini` にはURLをハードコードしない |
| `db/migrations/` の位置づけ | 参考用の手動DDLスナップショット置き場。CIやアプリ起動では**参照しない**（`api/alembic/versions/` のみが実行対象） |
| オートジェネレート | `alembic revision --autogenerate -m "<message>"` でモデル差分から下書きを生成し、CHECK制約・関数・トリガ適用は手動でリビジョンに追記する（`basic_design/01_database.md` §6） |

## 2. `api/alembic/versions/` ディレクトリ構成と初期リビジョン

### 2.1 リビジョンの分割方針

1テーブルにつき1リビジョンとせず、初期構築は「拡張有効化 → テーブル作成 → 関数・トリガ適用 → シードデータ」の順で意味のある単位に分割する。以降の変更は変更内容ごとに1リビジョン。

| リビジョンファイル（例） | 内容 |
|--------------------------|------|
| `0001_enable_extensions.py` | `CREATE EXTENSION IF NOT EXISTS pgcrypto` |
| `0002_create_users_table.py` | `users` テーブル、関連インデックス・CHECK制約 |
| `0003_create_oauth_accounts_table.py` | `oauth_accounts` テーブル |
| `0004_create_projects_table.py` | `projects` テーブル |
| `0005_create_project_members_table.py` | `project_members` テーブル（複合PK） |
| `0006_create_tasks_table.py` | `tasks` テーブル（`DEFERRABLE` 一意制約含む） |
| `0007_create_task_comments_table.py` | `task_comments` テーブル |
| `0008_create_login_history_table.py` | `login_history` テーブル |
| `0009_create_functions_and_triggers.py` | [08_db_functions.md](./08_db_functions.md) の4オブジェクト（`trg_set_updated_at` とその4トリガ、`fn_is_project_member`、`fn_next_task_position`、`sp_purge_login_history`） |
| `0010_seed_initial_admin.py` | 初期adminユーザーのシード（§3） |

**要検討**：上記のリビジョン分割・命名例（`0001_...` 等の連番接頭辞）は本詳細設計での具体化であり、基本設計に明記された正の構成ではない。実装時にAlembicの自動生成ハッシュIDとの整合をどう取るか（`down_revision` チェーンの実ファイル名）は実装担当の裁量とする。

### 2.2 リビジョンチェーン図

```mermaid
flowchart LR
    R1["0001<br/>拡張有効化"] --> R2["0002<br/>users"]
    R2 --> R3["0003<br/>oauth_accounts"]
    R3 --> R4["0004<br/>projects"]
    R4 --> R5["0005<br/>project_members"]
    R5 --> R6["0006<br/>tasks"]
    R6 --> R7["0007<br/>task_comments"]
    R7 --> R8["0008<br/>login_history"]
    R8 --> R9["0009<br/>関数・トリガ"]
    R9 --> R10["0010<br/>シード「初期admin」"]
    R10 -.->|"以降、機能追加ごとに1リビジョン"| RN["000N..."]
```

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
import uuid
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    email = os.environ["INITIAL_ADMIN_EMAIL"]
    username = os.environ["INITIAL_ADMIN_USERNAME"]
    password_hash = _hash_password(os.environ["INITIAL_ADMIN_PASSWORD"])
    op.execute(
        sa.text(
            """
            INSERT INTO users (id, username, email, password_hash, role,
                                is_active, email_verified_at, created_at, updated_at)
            VALUES (:id, :username, :email, :password_hash, 'admin',
                    true, now(), now(), now())
            ON CONFLICT (lower(username)) DO NOTHING
            """
        ).bindparams(id=str(uuid.uuid4()), username=username, email=email,
                      password_hash=password_hash)
    )

def downgrade() -> None:
    op.execute(sa.text("DELETE FROM users WHERE username = :u")
               .bindparams(u=os.environ["INITIAL_ADMIN_USERNAME"]))
```

`_hash_password` は `core/security.py` 相当の argon2 ラッパーをリビジョン内で直接importして使う想定。ハードコードした固定値ではなく、実行時の環境変数から都度生成する。

**要検討**：Alembicリビジョン内で環境変数未設定（`INITIAL_ADMIN_PASSWORD` 等が空）の場合の挙動（起動失敗させるか、スキップしてログ警告するか）は基本設計に明記がなく要検討。本設計では `os.environ[...]`（`KeyError` で起動失敗）を既定とし、CI環境ではダミー値を必ず注入する前提とする。

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

## 9. 不明点・要検討事項

- リビジョンファイルの連番接頭辞（`0001_`等）は本詳細設計での具体化であり、Alembic自動生成のハッシュIDとの命名整合方法（`down_revision` の実運用）は実装担当の裁量とする。
- `INITIAL_ADMIN_PASSWORD` 等が未設定の場合の挙動（起動失敗 or 警告スキップ）は基本設計に明記がなく、本設計では起動失敗を既定としたが要検討。
- CI上でのupgrade/downgrade往復健全性検証を必須ステップにするかは基本設計に記載がなく要検討（実行時間とのトレードオフ）。
- `db/migrations/` （手動DDL置き場）と `api/alembic/versions/` の内容をどの頻度・手順で同期させるか（自動生成スクリプトの要否）は基本設計に明記がなく要検討。
