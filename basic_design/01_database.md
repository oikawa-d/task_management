# 01 データベース設計（PostgreSQL）

## 1. 設計方針

| 項目 | 方針 |
|------|------|
| DBMS | PostgreSQL 17 |
| 保存対象 | 永続的に残す必要のあるデータのみ（ログイン有効性の判定は Redis 側で行う） |
| 主キー | `UUID`（`gen_random_uuid()` / pgcrypto）。URLに露出しても連番推測されないため |
| 文字列型 | `VARCHAR(n)` は入力上限がある項目、それ以外は `TEXT` |
| 日時型 | `TIMESTAMPTZ`（UTC保存）。アプリ側でタイムゾーン変換 |
| 列挙 | PostgreSQL の `ENUM` 型ではなく `VARCHAR + CHECK制約`（Alembic での値追加が容易なため） |
| 論理削除 | 行わない（学習用途のため物理削除）。ただし `users` のみ `is_active` で無効化を表現 |
| ORM | SQLAlchemy 2.x（`Mapped` / `mapped_column` の宣言的スタイル） |
| マイグレーション | Alembic。`db/migrations/` は SQL の手動DDL置き場、`api/alembic/versions/` が実行される正 |

## 2. ER図

> drawio版：[diagrams/03_er_diagram.drawio](./diagrams/03_er_diagram.drawio)（Redisキー・インデックス・DB関数の一覧を併記）

```mermaid
erDiagram
    users ||--o{ oauth_accounts : "外部ID紐付け"
    users ||--o{ projects : "owner"
    users ||--o{ project_members : "所属"
    projects ||--o{ project_members : "メンバー"
    projects ||--o{ tasks : "保有"
    users |o--o{ tasks : "assignee"
    users ||--o{ tasks : "created_by"
    tasks ||--o{ task_comments : "コメント"
    users ||--o{ task_comments : "投稿者"
    users |o--o{ login_history : "ログイン試行"

    users {
        uuid id PK
        varchar_50 username UK "ログインID"
        varchar_50 email UK
        text password_hash "OAuth専用ユーザーはNULL"
        varchar_30 last_name
        varchar_30 first_name
        varchar_30 last_name_kana
        varchar_30 first_name_kana
        date birth_date
        varchar_10 role "member / admin"
        boolean is_active
        timestamptz email_verified_at "NULL可（未認証）"
        timestamptz created_at
        timestamptz updated_at
    }
    oauth_accounts {
        uuid id PK
        uuid user_id FK
        varchar_20 provider "google"
        text provider_user_id "sub"
        text provider_email
        timestamptz created_at
    }
    projects {
        uuid id PK
        varchar_100 name
        text description
        uuid owner_id FK
        timestamptz created_at
        timestamptz updated_at
    }
    project_members {
        uuid project_id PK "FK: 複合主キーの一部"
        uuid user_id PK "FK: 複合主キーの一部"
        uuid invited_by FK
        timestamptz joined_at
    }
    tasks {
        uuid id PK
        uuid project_id FK
        varchar_150 title
        text description
        varchar_20 status "todo / in_progress / done"
        uuid assignee_id FK "NULL可"
        uuid created_by FK
        integer position "列内の並び順"
        date due_date "NULL可"
        timestamptz created_at
        timestamptz updated_at
    }
    task_comments {
        uuid id PK
        uuid task_id FK
        uuid user_id FK
        text body
        timestamptz created_at
        timestamptz updated_at
    }
    login_history {
        uuid id PK
        uuid user_id FK "未登録メール時はNULL"
        varchar_50 login_identifier "入力されたID/メール"
        varchar_20 login_method "session / jwt / oauth_google"
        inet ip_address
        text user_agent
        boolean success
        varchar_50 failure_reason "NULL可"
        timestamptz created_at
    }
```

## 3. テーブル定義

### 3.1 users

要件書の定義に加え、pptx（slide2 / slide1）に合わせて氏名・フリガナ・生年月日・`username` を追加している（設計判断 D-2 / D-3）。

| カラム | 型 | NULL | 既定値 | 制約・備考 |
|--------|----|------|--------|-----------|
| id | UUID | NO | `gen_random_uuid()` | PK |
| username | VARCHAR(50) | NO | - | UNIQUE。ログインID。半角英数字と `_` `-`（`CHECK`） |
| email | VARCHAR(50) | NO | - | UNIQUE。pptxの50文字制限に合わせる。`CHECK` で簡易形式検証 |
| password_hash | TEXT | YES | - | argon2id ハッシュ。Google のみで登録したユーザーは NULL |
| last_name | VARCHAR(30) | NO | - | 姓 |
| first_name | VARCHAR(30) | NO | - | 名 |
| last_name_kana | VARCHAR(30) | NO | - | 姓フリガナ。`CHECK` でひらがな/カタカナ/数字のみ |
| first_name_kana | VARCHAR(30) | NO | - | 名フリガナ。同上 |
| birth_date | DATE | NO | - | 用途は**不明**（T-5）。保持・表示のみ |
| role | VARCHAR(10) | NO | `'member'` | `CHECK (role IN ('member','admin'))` |
| is_active | BOOLEAN | NO | `true` | 管理者による無効化用 |
| email_verified_at | TIMESTAMPTZ | YES | `NULL` | メール認証の完了日時。`NULL` は未認証を意味しログインを拒否する（D-6）。真偽値ではなく日時で持ち、「いつ認証したか」を追跡可能にする |
| created_at | TIMESTAMPTZ | NO | `now()` | |
| updated_at | TIMESTAMPTZ | NO | `now()` | トリガで自動更新 |

**インデックス**

| 名称 | 定義 | 用途 |
|------|------|------|
| `uq_users_username` | UNIQUE (lower(username)) | 大文字小文字を区別しないログインID一意制約 |
| `uq_users_email` | UNIQUE (lower(email)) | 同上（メール） |
| `ix_users_role` | (role) | 管理者一覧・権限フィルタ |
| `ix_users_email_verified_at` | (email_verified_at) WHERE email_verified_at IS NULL | 未認証のまま放置されたユーザーの棚卸し（**要検討**：定期削除バッチを設けるか） |

**バリデーション（アプリ層 / pydantic）**

| 項目 | ルール | 出典 |
|------|--------|------|
| 姓・名 | 1〜30文字 | pptx slide2 |
| フリガナ | ひらがな・カタカナ・数字のみ、1〜30文字 | pptx slide2 |
| 生年月日 | プルダウン選択（年/月/日）。未来日不可 | pptx slide2 |
| メールアドレス | 50文字以内、半角英数字と `@ - _ . +` を許容 | pptx slide2 |
| パスワード | 8文字以上、かつ「大文字英字／小文字英字／数字／記号」のうち2種類以上を含む | pptx slide2 |

> pptx原文は「大文字・小文字英字、記号、数字のうち2種類以上」。本設計では上記4分類のうち2種類以上と解釈した。厳格化する場合は**要検討**。

### 3.2 oauth_accounts

| カラム | 型 | NULL | 備考 |
|--------|----|------|------|
| id | UUID | NO | PK |
| user_id | UUID | NO | FK → users.id `ON DELETE CASCADE` |
| provider | VARCHAR(20) | NO | `CHECK (provider IN ('google'))`。将来の拡張余地 |
| provider_user_id | TEXT | NO | Google の `sub` |
| provider_email | TEXT | YES | 参考情報（変更される可能性があるため識別子に使わない） |
| created_at | TIMESTAMPTZ | NO | |

**インデックス**：`uq_oauth_provider_user` UNIQUE (provider, provider_user_id)、`ix_oauth_user_id` (user_id)

### 3.3 projects

| カラム | 型 | NULL | 備考 |
|--------|----|------|------|
| id | UUID | NO | PK |
| name | VARCHAR(100) | NO | プロジェクト名 |
| description | TEXT | YES | |
| owner_id | UUID | NO | FK → users.id `ON DELETE RESTRICT`（オーナーが残る限りユーザー削除不可） |
| created_at | TIMESTAMPTZ | NO | |
| updated_at | TIMESTAMPTZ | NO | トリガで自動更新 |

**インデックス**：`ix_projects_owner_id` (owner_id)

### 3.4 project_members

| カラム | 型 | NULL | 備考 |
|--------|----|------|------|
| project_id | UUID | NO | PK(1) / FK → projects.id `ON DELETE CASCADE` |
| user_id | UUID | NO | PK(2) / FK → users.id `ON DELETE CASCADE` |
| invited_by | UUID | YES | FK → users.id `ON DELETE SET NULL` |
| joined_at | TIMESTAMPTZ | NO | |

- 複合主キー `(project_id, user_id)`
- プロジェクト作成時、オーナー自身も本テーブルへ登録する（所属判定を1箇所に集約するため）
- **インデックス**：`ix_project_members_user_id` (user_id)（ダッシュボードの所属一覧取得で使用）

### 3.5 tasks

| カラム | 型 | NULL | 既定値 | 備考 |
|--------|----|------|--------|------|
| id | UUID | NO | `gen_random_uuid()` | PK |
| project_id | UUID | NO | - | FK → projects.id `ON DELETE CASCADE` |
| title | VARCHAR(150) | NO | - | |
| description | TEXT | YES | - | |
| status | VARCHAR(20) | NO | `'todo'` | `CHECK (status IN ('todo','in_progress','done'))` |
| assignee_id | UUID | YES | - | FK → users.id `ON DELETE SET NULL` |
| created_by | UUID | NO | - | FK → users.id `ON DELETE RESTRICT` |
| position | INTEGER | NO | `0` | 同一 status 列内の並び順（T-3） |
| due_date | DATE | YES | - | |
| created_at | TIMESTAMPTZ | NO | `now()` | |
| updated_at | TIMESTAMPTZ | NO | `now()` | トリガで自動更新 |

**インデックス**

| 名称 | 定義 | 用途 |
|------|------|------|
| `ix_tasks_project_status_position` | (project_id, status, position) | カンバン表示の主クエリ |
| `ix_tasks_assignee_id` | (assignee_id) | 担当タスク絞り込み |

### 3.6 task_comments

| カラム | 型 | NULL | 備考 |
|--------|----|------|------|
| id | UUID | NO | PK |
| task_id | UUID | NO | FK → tasks.id `ON DELETE CASCADE` |
| user_id | UUID | NO | FK → users.id `ON DELETE RESTRICT` |
| body | TEXT | NO | 1〜2000文字（アプリ層で検証） |
| created_at | TIMESTAMPTZ | NO | |
| updated_at | TIMESTAMPTZ | NO | |

**インデックス**：`ix_task_comments_task_created` (task_id, created_at)

### 3.7 login_history

Redis の失効状況とは独立して保持し続ける監査ログ。

| カラム | 型 | NULL | 備考 |
|--------|----|------|------|
| id | UUID | NO | PK |
| user_id | UUID | YES | FK → users.id `ON DELETE SET NULL`。存在しないID入力時は NULL |
| login_identifier | VARCHAR(50) | NO | 入力された username / email（原文。パスワードは記録しない） |
| login_method | VARCHAR(20) | NO | `CHECK (login_method IN ('session','jwt','oauth_google'))` |
| ip_address | INET | YES | `X-Forwarded-For` を考慮して取得 |
| user_agent | TEXT | YES | |
| success | BOOLEAN | NO | |
| failure_reason | VARCHAR(50) | YES | `invalid_credentials` / `user_inactive` / `oauth_denied` 等 |
| created_at | TIMESTAMPTZ | NO | |

**インデックス**：`ix_login_history_user_created` (user_id, created_at DESC)、`ix_login_history_created` (created_at DESC)

> パスワードリセットの実行履歴はこのテーブルに含めない（`login_method` の CHECK 制約を汚さないため）。必要になった場合は `security_events` テーブルの追加を**要検討**。

## 4. データ遷移図

### 4.1 タスクのステータス遷移

```mermaid
stateDiagram-v2
    [*] --> todo: タスク作成
    todo --> in_progress: 着手（D&D / PATCH）
    in_progress --> done: 完了
    done --> in_progress: 差し戻し
    in_progress --> todo: 差し戻し
    todo --> done: 直接完了（許可する）
    done --> [*]: 削除
    todo --> [*]: 削除
    in_progress --> [*]: 削除
```

遷移制限は設けず、任意の status 間の変更を許可する（カンバンのD&Dを素直に反映するため）。

### 4.2 ユーザーの状態遷移

```mermaid
stateDiagram-v2
    [*] --> unverified: 登録フォーム送信（email_verified_at=NULL）
    unverified --> unverified: 認証メール再送
    unverified --> member: 確認メール内リンクで認証完了（email_verified_at=now）
    [*] --> member_oauth: Googleで新規登録（password_hash=NULL,<br/>email_verified_at=now：Google側で検証済み）
    member_oauth --> member: パスワード設定（password_hash付与）
    member --> admin: 管理者が権限変更
    admin --> member: 管理者が権限変更
    member --> inactive: 管理者が無効化（is_active=false）
    inactive --> member: 再有効化
    inactive --> [*]: 削除（オーナーのプロジェクトが無い場合のみ）
```

### 4.3 プロジェクト作成時のデータ生成

```mermaid
flowchart LR
    A["POST /projects"] --> B["BEGIN"]
    B --> C["INSERT projects<br/>(owner_id = 現在ユーザー)"]
    C --> D["INSERT project_members<br/>(project_id, owner_id)"]
    D --> E["COMMIT"]
    E --> F["201 Created"]
    C -.->|失敗| G["ROLLBACK / 500"]
    D -.->|失敗| G
```

## 5. DB関数・プロシージャ

`db/functions/` および `db/procedures/` に `.sql` として配置し、Alembic のマイグレーションから読み込んで適用する。

### 5.1 `db/functions/trg_set_updated_at.sql`

| 項目 | 内容 |
|------|------|
| 種別 | トリガ関数 |
| 入出力 | 引数なし / `RETURNS TRIGGER` |
| 処理 | `NEW.updated_at := now()` を設定して `NEW` を返す |
| 適用対象 | `users` / `projects` / `tasks` / `task_comments` の `BEFORE UPDATE` トリガ |

### 5.2 `db/functions/fn_is_project_member.sql`

| 項目 | 内容 |
|------|------|
| 引数 | `p_project_id UUID`, `p_user_id UUID` |
| 戻り値 | `BOOLEAN` |
| 処理 | `project_members` に該当行が存在するか、または `users.role = 'admin'` であれば `true` |
| 用途 | 認可チェックのDB側での再確認、およびSQLレベルの検証テスト |
| 備考 | アプリ層でも同等の判定を行う（二重防御）。正はアプリ層 |

### 5.3 `db/functions/fn_next_task_position.sql`

| 項目 | 内容 |
|------|------|
| 引数 | `p_project_id UUID`, `p_status VARCHAR` |
| 戻り値 | `INTEGER` |
| 処理 | `SELECT COALESCE(MAX(position), -1) + 1` を対象 (project_id, status) で取得 |
| 用途 | タスク新規作成時、および列間移動時の末尾追加 |

### 5.4 `db/procedures/sp_purge_login_history.sql`

| 項目 | 内容 |
|------|------|
| 引数 | `p_retention_days INTEGER` |
| 戻り値 | なし（`PROCEDURE`） |
| 処理 | `DELETE FROM login_history WHERE created_at < now() - (p_retention_days || ' days')::interval` |
| 用途 | 監査ログの保持期間管理。保持日数は環境変数 `LOGIN_HISTORY_RETENTION_DAYS` から渡す |
| 実行方法 | 手動またはバッチ。定期実行の仕組みは**要検討**（学習範囲ではcronを想定しない） |

## 6. マイグレーション方針

```mermaid
flowchart LR
    A["ORMモデル変更<br/>api/app/models/*.py"] --> B["alembic revision --autogenerate"]
    B --> C["生成されたversionを手動レビュー<br/>（CHECK制約・関数適用は手書き追加）"]
    C --> D["alembic upgrade head<br/>（起動時 or CIで実行）"]
    D --> E["pytest（実DB接続）"]
```

| 項目 | 方針 |
|------|------|
| 適用タイミング | ローカル/CD では backend コンテナ起動時のエントリポイントで `alembic upgrade head` |
| 初期リビジョン | 拡張有効化（`CREATE EXTENSION IF NOT EXISTS pgcrypto`）→ テーブル作成 → 関数・トリガ適用の順 |
| ダウングレード | 学習目的のため `downgrade()` も必ず記述する |
| 初期データ | 管理者アカウントを seed する（メール・初期パスワードは `.env` から取得。ハードコードしない） |
| テストDB | CI では GitHub Actions の `services` で PostgreSQL を起動し、テスト前に `alembic upgrade head` を実行 |

## 7. 主要クエリ

| No | 用途 | 概要 | 使用インデックス |
|----|------|------|-----------------|
| Q-1 | ログイン | `WHERE (lower(email)=:v OR lower(username)=:v) AND is_active`（取得後に `email_verified_at IS NULL` を判定） | `uq_users_email` / `uq_users_username` |
| Q-2 | ダッシュボード | `projects JOIN project_members ON ... WHERE pm.user_id = :me` | `ix_project_members_user_id` |
| Q-3 | カンバン取得 | `WHERE project_id=:pid ORDER BY status, position` | `ix_tasks_project_status_position` |
| Q-4 | タスク詳細 | tasks + assignee + comments（コメントは別クエリで取得しN+1を回避） | `ix_task_comments_task_created` |
| Q-5 | 管理者ユーザー一覧 | `ORDER BY created_at DESC LIMIT/OFFSET` | `ix_users_role` |
| Q-6 | ログイン履歴 | `WHERE user_id=:uid ORDER BY created_at DESC LIMIT 50` | `ix_login_history_user_created` |

> Q-2 / Q-3 では SQLAlchemy の `selectinload` を用い、N+1 クエリを避ける。
