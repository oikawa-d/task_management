# DB詳細設計 00 設計方針

## 0. 関連ドキュメント

- `../../basic_design/01_database.md`（正。本書はこれを詳細化したものであり、内容が矛盾する場合は基本設計側が正）
- `../../basic_design/00_overview.md`
- `../../requirements/task_management_requirements.md`
- `./01_table_users.md` / `./02_table_oauth_accounts.md` / `./03_table_login_history.md` / `./11_table_api_history.md` / `./12_table_batch_history.md`（本書の方針に従うテーブル詳細）

## 1. 本書の位置づけ

`basic_design/01_database.md` の設計方針・命名規約・型方針・共通カラム・列挙表現・削除方針・ER図を、実装（DDL・SQLAlchemyモデル・マイグレーション）に落とし込めるレベルまで詳細化する。テーブル個別の定義（カラム定義・DDL・インデックス・リポジトリ関数）は `01_table_*.md` 以降で扱い、本書では全テーブルに共通する方針のみを扱う。

`users` / `oauth_accounts` / `login_history` / `notifications` / `api_history` / `batch_history` の詳細は本書とあわせて各テーブル設計書を参照する。`projects` 以降のテーブルおよび DB関数・マイグレーション運用は別担当ファイル（`04_table_projects.md` 〜 `12_table_batch_history.md`）で扱うため本書では個別定義を繰り返さない。

## 2. 基本方針（`basic_design/01_database.md` §1 の再掲・詳細化）

| 項目 | 方針 | 補足 |
|------|------|------|
| DBMS | PostgreSQL 17 | Docker Compose の `postgres` サービス |
| 保存対象 | 永続的に残す必要のあるデータのみ | ログイン有効性の判定は Redis 側（`../../basic_design/02_redis.md`） |
| 主キー | `UUID`（`gen_random_uuid()`、`pgcrypto` 拡張） | URL露出時の連番推測を防止 |
| 文字列型 | 入力上限がある項目は `VARCHAR(n)`、それ以外は `TEXT` | 上限は基本設計のカラム定義に従う |
| 日時型 | `TIMESTAMPTZ`（UTC保存） | `APP_TIMEZONE`（既定`Asia/Tokyo`）を基準にアプリ層で表示・日次境界を判定し、DBへはUTCで保存する |
| 列挙 | `VARCHAR + CHECK制約` | PostgreSQLの `ENUM` 型は使わない（Alembicでの値追加が容易なため） |
| 論理削除 | 行わない（物理削除） | `users` のみ `is_active` で無効化を表現。他テーブルはFKの `ON DELETE` 挙動に従う |
| ORM | SQLAlchemy 2.x（`Mapped` / `mapped_column` の宣言的スタイル） | `api/app/models/` |
| マイグレーション | Alembic | `db/migrations/` は手動DDL置き場、`api/alembic/versions/` が実行される正（詳細は `09_migration.md`） |

## 3. 命名規約

| 対象 | 規約 | 例 |
|------|------|-----|
| テーブル名 | 複数形スネークケース | `users` / `oauth_accounts` / `login_history`（例外：不可算名詞はそのまま） |
| カラム名 | スネークケース | `email_verified_at` |
| 主キー制約名 | `pk_<table>` | `pk_users` |
| 外部キー制約名 | `fk_<table>_<column>_<ref_table>` | `fk_oauth_accounts_user_id_users` |
| CHECK制約名 | `ck_<table>_<column>` | `ck_users_role` |
| 一意制約名 | `uq_<table>_<column(s)>` | `uq_oauth_accounts_provider_provider_user_id` |
| インデックス名 | `ix_<table>_<column(s)>` | `ix_users_created_at` |
| 外部キー参照カラム | `<単数形テーブル名>_id` | `user_id` → `users.id` |
| SQLAlchemyモデルクラス | 単数形パスカルケース | `User` / `OAuthAccount` / `LoginHistory` |
| ORMモデルファイル | `models/<単数形スネークケース>.py` | `models/user.py` |
| リポジトリファイル | `repository/<単数形スネークケース>_repository.py` | `repository/user_repository.py` |

制約名・インデックス名はAlembicの `op.create_check_constraint` 等に明示的に渡し、自動生成された無名の制約名に依存しない。

## 4. 型方針（詳細）

| 論理型 | PostgreSQL型 | SQLAlchemy型 | 備考 |
|--------|--------------|--------------|------|
| ID | `UUID` | `UUID(as_uuid=True)`（`sqlalchemy.dialects.postgresql`） | 既定値はDB側 `server_default=text("gen_random_uuid()")` |
| 短い文字列（上限あり） | `VARCHAR(n)` | `String(n)` | `n` は基本設計のカラム定義表に従う |
| 長文・可変長 | `TEXT` | `Text` | `password_hash` / `description` / `body` 等 |
| 真偽値 | `BOOLEAN` | `Boolean` | |
| 整数 | `INTEGER` | `Integer` | `position` / `version` 等 |
| 日付のみ | `DATE` | `Date` | `birth_date` |
| 日時 | `TIMESTAMPTZ` | `datetime` | `tasks.due_at` / `notifications.due_at`。DBはUTC保存、表示・日次判定は`APP_TIMEZONE` |
| 日時（タイムゾーン付き） | `TIMESTAMPTZ` | `DateTime(timezone=True)` | UTCで保存 |
| IPアドレス | `INET` | `INET`（`sqlalchemy.dialects.postgresql`） | `login_history.ip_address` |
| 列挙 | `VARCHAR(n) + CHECK` | `String(n)` + `CheckConstraint` | Python側は `Literal` 型または `enum.StrEnum` をスキーマ層（pydantic）で使用し、DB側は文字列として保持 |

## 5. 共通カラム

全テーブル共通ではなく、テーブルの性質ごとに以下の共通パターンを適用する（`basic_design/01_database.md` のER図・テーブル定義に準拠）。

| パターン | 対象カラム | 適用テーブル |
|----------|-----------|--------------|
| 主キー | `id UUID PK DEFAULT gen_random_uuid()` | `users` / `oauth_accounts` / `projects` / `tasks` / `task_comments` / `login_history` / `api_history` / `batch_history`（`project_members` のみ複合PKで対象外） |
| 作成日時 | `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` | 通常の永続テーブルと`api_history`。`batch_history`は起動時刻を`started_at`として保持 |
| 更新日時 | `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`（トリガで自動更新） | `users` / `projects` / `tasks` / `task_comments` / `batch_history`（状態更新を持つテーブル）。`oauth_accounts` / `login_history` / `api_history` / `project_members`は追記専用 |

`updated_at` の自動更新は `db/functions/trg_set_updated_at.sql`（トリガ関数）を対象テーブルの `BEFORE UPDATE` に適用する（詳細は `04_table_projects.md` 以降および `08_db_functions.md` を参照。`users` テーブルへの適用は `01_table_users.md` §3・§4 に記載）。

## 6. UUID採番方針

- 主キーの採番は **DB側**（`gen_random_uuid()`）で行い、アプリ層でUUIDを生成してINSERTすることはしない。理由：採番責務をDBに一元化し、複数の挿入経路（API・マイグレーションのseed）で採番ロジックが分岐しないようにするため。例外として `api_history.request_id` は主キーではない相関IDのため、API履歴ミドルウェアが `uuid.uuid4()` で生成してレスポンス・ログ・DBへ同じ値を渡す。
- `pgcrypto` 拡張を初期マイグレーションで `CREATE EXTENSION IF NOT EXISTS pgcrypto` により有効化する（`09_migration.md` の初期リビジョンで実施。本書では前提のみ記載）。
- SQLAlchemyモデル側では `mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))` とし、Python側で `default=uuid4` は設定しない（DBの既定値と二重管理にしないため）。
- UUIDのバージョンはPostgreSQLの `gen_random_uuid()` が生成する v4 に従う。
- `request_id` の生成元は API の履歴ミドルウェア、形式は UUID v4 文字列とする（例：`550e8400-e29b-41d4-a716-446655440000`）。DBの `api_history.id` は `gen_random_uuid()`、`request_id` はアプリから必須値としてINSERTする。

## 7. CHECK制約による列挙表現

`ENUM` 型を使わず `VARCHAR(n) + CHECK` で列挙を表現する方針（理由：Alembicでの値追加時に `ALTER TYPE ... ADD VALUE` のトランザクション制約を回避できるため）。

| テーブル | カラム | 許容値 | 制約名 |
|----------|--------|--------|--------|
| `users` | `role` | `member` / `admin` | `ck_users_role` |
| `oauth_accounts` | `provider` | `google` | `ck_oauth_accounts_provider` |
| `tasks` | `status` | `todo` / `in_progress` / `done` | `ck_tasks_status` |
| `login_history` | `login_method` | `session` / `jwt` / `oauth_google` | `ck_login_history_login_method` |
| `api_history` | `status` | `success` / `error` | `ck_api_history_status` |
| `batch_history` | `trigger_type` | `scheduled` / `manual` | `ck_batch_history_trigger_type` |
| `batch_history` | `status` | `inprogress` / `complete` / `error` | `ck_batch_history_status` |

CHECK制約の記述形式：`CHECK (<column> IN ('value1', 'value2', ...))`。値の追加はAlembicのマイグレーションで `CHECK` 制約を `DROP` → `ADD` し直す（値の削除を伴わない追加であれば新しいリビジョンで制約定義を更新する）。

アプリ層（pydantic schemas）でも同じ許容値を `Literal` または `enum.StrEnum` として二重に定義し、リクエストバリデーションの時点で不正値を弾く（DB側のCHECK制約は最終防衛線）。

## 8. 物理削除方針

- 全テーブルで論理削除フラグ（`deleted_at` 等）は持たない。削除はSQLの `DELETE` による物理削除を基本とする。
- 例外は `users` のみで、`is_active`（管理者による無効化）を用いて「利用停止」を表現する。`users` に対する削除API自体は基本設計で提供されない（`01_table_users.md` §7 参照）。
- 親テーブル削除時の子テーブル挙動は外部キーの `ON DELETE` 句に従う（`CASCADE` / `RESTRICT` / `SET NULL`）。各テーブルの詳細は `01_table_users.md` 〜 `03_table_login_history.md` の「制約・インデックス」節、および `projects` 以降は担当ファイルを参照。
- `login_history` / `api_history` / `batch_history` は保持期間超過分をそれぞれの `sp_purge_*_history` プロシージャによる物理削除の対象とする（保持期間はそれぞれ90日 / 30日 / 30日）。

## 9. 全体ER図

`users` / `oauth_accounts` / `login_history` を中心に、関連する他テーブルとの関係のみを示す（`projects` 以降の内部構造は担当ファイルを参照）。

```mermaid
erDiagram
    users ||--o{ oauth_accounts : "外部ID紐付け"
    users |o--o{ login_history : "ログイン試行（未登録メール時はuser_id NULL）"
    users |o--o{ api_history : "API利用者（未認証時はuser_id NULL）"
    users ||--o{ projects : "owner"
    users ||--o{ project_members : "所属"
    users |o--o{ tasks : "assignee"
    users ||--o{ tasks : "created_by"
    users ||--o{ task_comments : "投稿者"

    users {
        uuid id PK
        varchar_50 username UK
        varchar_50 email UK
        text password_hash "NULL可"
        varchar_10 role
        boolean is_active
        timestamptz email_verified_at "NULL可"
    }
    oauth_accounts {
        uuid id PK
        uuid user_id FK
        varchar_20 provider
        text provider_user_id
    }
    login_history {
        uuid id PK
        uuid user_id FK "NULL可"
        varchar_20 login_method
        boolean success
    }
    api_history {
        uuid id PK
        uuid request_id UK
        varchar_10 method
        varchar_255 path
        varchar_20 status
        smallint status_code
        uuid user_id FK
        integer duration_ms
        timestamptz created_at
    }
    batch_history {
        uuid id PK
        uuid run_id UK
        varchar_100 batch_name
        varchar_20 status
        timestamptz started_at
        timestamptz ended_at
        timestamptz updated_at
    }
    projects {
        uuid id PK
        uuid owner_id FK
    }
    project_members {
        uuid project_id PK
        uuid user_id PK
    }
    tasks {
        uuid id PK
        uuid assignee_id FK "NULL可"
        uuid created_by FK
    }
    task_comments {
        uuid id PK
        uuid user_id FK
    }
```

## 10. マイグレーション運用との関係

DDLの実適用（Alembicリビジョンの構成・初期データseed・CI/CDでの `alembic upgrade head` 実行タイミング）は `09_migration.md`（別担当）で扱う。本書および `01_table_*.md` 〜 `03_table_*.md` に記載するDDLは、Alembicリビジョンに落とし込む際の設計上の正として参照される。

## 11. 不明点・要検討事項

- `TIMESTAMPTZ` で保存した日時をアプリ層でどのタイムゾーンに変換して返却するか（`APP_TIMEZONE` 等の環境変数が基本設計に定義されていない）は不明。要検討。
- CHECK制約の値追加時のAlembic運用（`DROP CONSTRAINT` → `ADD CONSTRAINT` の具体的な手順・ダウングレード時の扱い）は `09_migration.md` 側で詳細化が必要（本書では方針のみ記載）。要検討。
