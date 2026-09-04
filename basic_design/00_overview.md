# 00 全体設計

## 1. システム概要

チームでプロジェクトを作成し、タスクをカンバン形式（未着手／進行中／完了）で管理するWebアプリケーション。
`AUTH_MODE` により session 方式 / JWT 方式を切り替え可能とし、加えて Google OAuth2 ログインを常時提供する。

| 項目 | 内容 |
|------|------|
| バックエンド | FastAPI（Python 3.14） |
| フロントエンド | React 19 + Vite + TypeScript（Node v26） |
| 永続データストア | PostgreSQL 17 |
| セッションストア | Redis 8（永続化なし） |
| ORM / マイグレーション | SQLAlchemy 2.x + Alembic |
| 認証方式 | session（Cookie + Redis） / JWT（Access + Refresh） / Google OAuth2 |
| 定期実行 | `batch` コンテナ（常駐スケジューラ。現在は毎日10時・17時のタスク期限通知。将来の定期ジョブ追加基盤） |
| 基準タイムゾーン | `APP_TIMEZONE`（既定 `Asia/Tokyo`）。DBはUTC保存、日次境界・「10時・17時」の判定はこのTZで行う |
| CI/CD | GitHub Actions（CI: Lint・型チェック・テスト、CD: GHCR + self-hosted runner） |

## 2. システム構成

> drawio版：[diagrams/01_system_architecture.drawio](./diagrams/01_system_architecture.drawio)（公開ポート・CI/CD経路を含む詳細版）

```mermaid
flowchart TB
    subgraph client["クライアント"]
        BROWSER["ブラウザ<br/>React SPA"]
    end

    subgraph compose["Docker Compose ネットワーク"]
        FE["frontend<br/>Vite / Nginx"]
        API["backend<br/>FastAPI + Uvicorn"]
        BAT["batch<br/>常駐スケジューラ<br/>毎日10:00 / 17:00 JST"]
        PG[("postgres<br/>PostgreSQL 17")]
        RD[("redis<br/>Redis 8")]
        MAIL["mailpit<br/>開発用SMTP"]
    end

    subgraph external["外部サービス"]
        GOOGLE["Google OAuth2<br/>認可サーバー"]
    end

    BROWSER -->|"HTTPS/HTTP<br/>same-origin /api"| FE
    FE -->|"/api proxy<br/>Cookie or Bearer"| API
    API -->|"SQLAlchemy"| PG
    API -->|"redis-py"| RD
    BAT -->|"SQLAlchemy<br/>notifications INSERT"| PG
    BAT -->|"redis-py<br/>実行ロック"| RD
    API -->|"SMTP"| MAIL
    API -->|"token / userinfo"| GOOGLE
    BROWSER -->|"リダイレクト"| GOOGLE
```

## 3. バックエンドのレイヤ構成

> drawio版：[diagrams/02_backend_layers.drawio](./diagrams/02_backend_layers.drawio)（モジュール単位の詳細版）

依存方向は `api → service → repository → models` の一方向とし、`core` は全層から参照可能とする。

```mermaid
flowchart TB
    R["api/routers<br/>プレゼンテーション層"]
    S["schemas<br/>入出力DTO(pydantic)"]
    SV["service<br/>ビジネスロジック層"]
    AU["auth<br/>認証Strategy"]
    RP["repository<br/>データアクセス層"]
    M["models<br/>ORMモデル"]
    C["core<br/>config / logger / security / exceptions"]

    R --> S
    R --> SV
    SV --> AU
    SV --> RP
    RP --> M
    R -.-> C
    SV -.-> C
    AU -.-> C
    RP -.-> C
```

### ディレクトリ構成

```
project-root/
├── .github/workflows/{ci.yml, cd.yml}
├── api/
│   ├── alembic/{versions/, env.py, script.py.mako}
│   ├── alembic.ini
│   ├── app/
│   │   ├── main.py                # FastAPIアプリ生成・ミドルウェア登録
│   │   ├── core/
│   │   │   ├── config.py          # pydantic-settings による環境変数定義
│   │   │   ├── logger.py          # logging設定
│   │   │   ├── history_middleware.py # 全APIリクエストのapi_history記録
│   │   │   ├── security.py        # パスワードハッシュ、トークン署名
│   │   │   ├── exceptions.py      # 業務例外とハンドラ
│   │   │   └── deps.py            # 共通DI（現在ユーザー、DBセッション等）
│   │   ├── api/routers/           # auth, projects, tasks, comments, users, admin, notifications
│   │   ├── schemas/               # リクエスト/レスポンスDTO
│   │   ├── service/               # auth_service, project_service, task_service, notification_service...
│   │   ├── auth/                  # Strategy実装（session_auth/jwt_auth/oauth/base）
│   │   ├── repository/            # user_repo, project_repo, task_repo, notification_repo, redis_store...
│   │   ├── models/                # SQLAlchemy ORMモデル
│   │   ├── db.py                  # エンジン・セッションファクトリ
│   │   └── redis_client.py        # Redis接続プール
│   ├── tests/{unit/, integration/, conftest.py}
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/  （詳細は 05_frontend.md）
├── batch/
│   ├── app/
│   │   ├── main.py                # APScheduler 起動（常駐）
│   │   ├── core/{config.py, logger.py}
│   │   ├── jobs/due_notification_job.py
│   │   └── repository/            # batch専用のDB/Redisアクセス
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── db/{migrations/, functions/, procedures/}
├── docker-compose.yml
├── .env / .env.example
└── tmp/   （git管理外）
```

## 4. 画面遷移図

> drawio版：[diagrams/04_screen_flow.drawio](./diagrams/04_screen_flow.drawio)

```mermaid
stateDiagram-v2
    [*] --> Login: 未認証で任意URLへアクセス
    Login --> Register: 「新規会員登録はこちら」
    Login --> PasswordForgot: 「パスワードを忘れた方はこちら」
    Login --> Dashboard: ログイン成功
    Login --> Google: Googleでログイン
    Google --> Dashboard: コールバック成功（Google側で検証済みのメールのみ）
    Register --> Login: 登録成功（確認メール送信・自動ログインしない）
    Login --> Login: メール未認証のためログイン拒否（認証メール再送）
    [*] --> VerifyEmail: 確認メール内のリンク
    VerifyEmail --> Login: メール認証完了
    PasswordForgot --> PasswordReset: メール内リンク
    PasswordReset --> Login: リセット完了
    Dashboard --> ProjectBoard: プロジェクト選択
    ProjectBoard --> TaskDetail: タスクカード選択（モーダル）
    TaskDetail --> ProjectBoard: 閉じる
    Dashboard --> Settings: サイドバー「設定」
    Dashboard --> AdminUsers: サイドバー「管理」（adminのみ）
    Settings --> Dashboard
    AdminUsers --> Dashboard
    Dashboard --> Login: ログアウト
```

## 5. 全体シーケンス

### 5.1 ログイン〜カンバン表示（session モード）

```mermaid
sequenceDiagram
    autonumber
    actor U as ユーザー
    participant FE as React SPA
    participant API as FastAPI
    participant RD as Redis
    participant PG as PostgreSQL

    U->>FE: ID/メール + パスワード入力
    FE->>API: POST /api/auth/login
    API->>PG: SELECT users WHERE email=? OR username=?
    PG-->>API: user行
    API->>API: パスワード検証（argon2）
    API->>API: users の is_active / role / username を正として判定
    API->>RD: SETEX session:{sid} TTL=1800
    API->>RD: SETEX csrf:{sid} TTL=1800
    API->>PG: INSERT login_history(success=true)
    API-->>FE: 204 + Set-Cookie(sid, csrf_token)
    FE->>API: GET /api/auth/me (Cookie)
    API->>RD: GET session:{sid}
    RD-->>API: {user_id}
    API-->>FE: 200 {user}
    FE->>API: GET /api/projects
    API->>PG: 所属プロジェクト取得
    API-->>FE: 200 [projects]
    FE->>API: GET /api/projects/{id}/tasks
    API-->>FE: 200 [tasks]
    FE-->>U: カンバンボード描画
```

### 5.2 タスクのドラッグ＆ドロップによるステータス変更

```mermaid
sequenceDiagram
    autonumber
    actor U as ユーザー
    participant FE as React SPA
    participant API as FastAPI
    participant PG as PostgreSQL

    U->>FE: カードを「進行中」列にドロップ
    FE->>FE: 楽観的更新（ローカルstate即時反映）
    FE->>API: PATCH /api/tasks/{id} {status, position, version}
    API->>API: 認証・プロジェクト所属チェック
    API->>PG: version一致を確認してUPDATE<br/>status, position, version+1
    alt version一致
        PG-->>API: 更新後の行
        API-->>FE: 200 {task}
    else version不一致
        PG-->>API: 更新対象なし
        API-->>FE: 409
        FE->>FE: 最新ボードを再取得し、再操作を促す
        FE-->>U: 最新状態を表示
    else 認証・認可失敗またはその他の失敗
        API-->>FE: 4xx/5xx
        FE->>FE: ロールバック（元の列に戻す）
        FE-->>U: エラートースト表示
    end
```

## 6. 主要コンポーネント相関図

```mermaid
flowchart LR
    subgraph routers
        AR["auth_router"]
        PR["projects_router"]
        TR["tasks_router"]
        ADR["admin_router"]
        UR["users_router"]
        NR["notifications_router"]
    end

    subgraph service
        AS["auth_service"]
        PS["project_service"]
        TS["task_service"]
        US["user_service"]
        MS["mail_service"]
        NS["notification_service"]
    end

    subgraph auth_strategy
        BASE["AuthStrategy(ABC)"]
        SESS["SessionAuthStrategy"]
        JWTS["JwtAuthStrategy"]
        OA["GoogleOAuthProvider"]
    end

    subgraph repository
        URP["user_repository"]
        PRP["project_repository"]
        TRP["task_repository"]
        LRP["login_history_repository"]
        NRP["notification_repository"]
        RS["redis_store"]
    end

    AR --> AS
    PR --> PS
    TR --> TS
    UR --> US
    NR --> NS
    ADR --> US
    ADR --> PS

    AS --> BASE
    AS --> OA
    AS --> URP
    AS --> LRP
    AS --> MS
    BASE --> SESS
    BASE --> JWTS
    SESS --> RS
    JWTS --> RS
    PS --> PRP
    TS --> TRP
    TS --> NS
    NS --> NRP
    US --> URP
```

## 7. データ全体像

```mermaid
flowchart LR
    subgraph redis["Redis（揮発・TTL失効）"]
        S1["session:{sid}"]
        S2["csrf:{sid}"]
        S3["refresh:{token_hash}"]
        S4["oauth_state:{state}"]
        S5["pwreset:{token_hash}"]
        S6["refresh_used / refresh_family_revoked"]
        S7["oauth_handoff:{code}"]
        S8["emailverify / emailverify_current"]
        S9["lock:notify_due:{YYYY-MM-DD}:{slot}"]
    end

    subgraph batch["batch（常駐スケジューラ）"]
        B1["due_notification_job_10 / _17<br/>毎日10:00 / 17:00 JST"]
    end

    subgraph pg["PostgreSQL（永続）"]
        T1["users"]
        T2["oauth_accounts"]
        T3["projects"]
        T4["project_members"]
        T5["tasks"]
        T6["task_comments"]
        T7["login_history"]
        T8["notifications"]
        T9["api_history"]
        T10["batch_history"]
    end

    S1 -->|user_id| T1
    S3 -->|user_id| T1
    S5 -->|user_id| T1
    T7 -->|user_id| T1
    T9 -->|user_id（NULL可）| T1
    T8 -->|user_id| T1
    T8 -->|task_id| T5
    B1 -->|"due_at を走査"| T5
    B1 -->|"通知をINSERT"| T8
    B1 -->|"開始・完了・失敗を記録"| T10
    API["backend API"] -->|"リクエスト履歴をINSERT"| T9
```

「ログインが有効かどうか」の判定は Redis のみを参照し、「誰がいつログインしたか」の履歴は90日、API・batchの実行履歴は30日を既定の保持期間として PostgreSQL に残す。この分離により、Redis 再起動でログイン状態は失われても履歴は独立して残る。

## 8. 非機能設計サマリ

| 項目 | 方針 |
|------|------|
| パスワード保存 | argon2id（`passlib[argon2]`）。コストパラメータは環境変数化 |
| CSRF | sessionの更新系とjwtのrefresh/logoutでDouble Submit Cookie + Origin検証（[03_auth](./03_auth.md#8-csrf対策)） |
| トークン失効 | session/refresh はいずれも Redis のキー削除で即時失効 |
| ログ | 構造化ログ（JSON）に加え、APIは`api_history`、batchは`batch_history`へ保存。API・batchは30日、ログイン履歴は90日保持 |
| テスト | バックエンド pytest（Redis/PostgreSQL は実コンテナ接続）、フロント Vitest |
| 秘匿情報 | `.env` および GitHub Secrets 管理。リポジトリへ直接コミットしない |
| Redis永続化 | RDB/AOF 無効。再起動時に全ログアウトとなることを許容 |
| 定期実行 | `batch` コンテナの常駐スケジューラ。10時・17時の2つのcronジョブを登録し、二重実行はRedisの実行ロック（`lock:notify_due:{日付}:{slot}`）で防止（[02_redis](./02_redis.md#2-キー一覧)） |
| タイムゾーン | 保存はUTC（`TIMESTAMPTZ`）、業務上の日次境界の判定は `APP_TIMEZONE`（既定 `Asia/Tokyo`）。フロントは表示のみローカル変換 |
