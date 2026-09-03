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
| CI/CD | GitHub Actions（CI: Lint・型チェック・テスト、CD: GHCR + self-hosted runner） |

## 2. 要件書からの設計判断一覧

要件定義書と画面イメージ（pptx）の間に差異があったため、以下のとおり合意して設計している。
（詳細は各設計書の該当章を参照）

| No | 論点 | 要件書 | pptx | 本設計での決定 | 影響 |
|----|------|--------|------|----------------|------|
| D-1 | パスワードリセット | メール送信は「スコープ外」 | slide3 にリセット画面あり | **メール送信まで含めて実装する**（SMTP連携） | [03_auth](./03_auth.md#6-パスワードリセット), [04_api](./04_api.md), [06](./06_infra_cicd.md) |
| D-2 | ユーザー属性 | users は id/email/password_hash/role/created_at のみ | 姓・名・フリガナ・生年月日を入力 | **pptx に合わせて users にカラム追加**。バリデーション（各30文字／メール50文字／パスワードポリシー）も設計に反映 | [01_database](./01_database.md#31-users), [05](./05_frontend.md) |
| D-3 | ログイン識別子 | email のみ | 「IDもしくはメールアドレス」 | **username カラムを追加し、email / username のどちらでもログイン可能にする** | [01_database](./01_database.md#31-users), [03_auth](./03_auth.md#41-パスワードログイン) |
| D-4 | 文字サイズ変更 | 記載なし | slide7 に設定項目あり | **フロントエンドの localStorage のみで保持**（DB・API変更なし） | [05_frontend](./05_frontend.md#8-アクセシビリティ設定文字サイズ) |
| D-5 | サイドバーナビゲーション | 記載なし | 全画面共通で `≡` / home / 管理 / 設定 / ログアウト | **共通レイアウトコンポーネントとして設計**。「管理」は `role = admin` のみ表示 | [05_frontend](./05_frontend.md#3-共通レイアウト) |

### 要検討事項

| No | 内容 | 状況 |
|----|------|------|
| T-1 | ディレクトリ構成が、要件書§9（`api/app/{auth,models,routers}`）とコーディング規約のレイヤ構成（`core/api/schemas/service/repository/models`）で食い違っている。本設計では**要件書のトップレベル構成（`api/`, `frontend/`, `db/`）を維持しつつ、`api/app/` 内部をレイヤ構成に合わせる**案を採用している | **要検討**（実装着手前に合意が必要） |
| T-2 | プロジェクトからのメンバー削除・脱退のAPIは要件書に記載がない。設計では追加している | 要検討 |
| T-3 | タスクの並び順（カンバン内のカード順序）の永続化方法。本設計では `tasks.position` を持たせる案とした | 要検討 |
| T-4 | パスワードリセットのメール送信基盤（本番SMTPを使うか、開発用のMailpit等に留めるか） | **要検討**。設計上は SMTP 設定を環境変数化し、開発環境は Mailpit を推奨 |
| T-5 | 生年月日の用途（年齢制限等）は不明。表示・保持のみとしている | **不明** |

## 3. システム構成

```mermaid
flowchart TB
    subgraph client["クライアント"]
        BROWSER["ブラウザ<br/>React SPA"]
    end

    subgraph compose["Docker Compose ネットワーク"]
        FE["frontend<br/>Vite / Nginx"]
        API["backend<br/>FastAPI + Uvicorn"]
        PG[("postgres<br/>PostgreSQL 17")]
        RD[("redis<br/>Redis 8")]
        MAIL["mailpit<br/>開発用SMTP"]
    end

    subgraph external["外部サービス"]
        GOOGLE["Google OAuth2<br/>認可サーバー"]
    end

    BROWSER -->|"HTTPS/HTTP"| FE
    BROWSER -->|"/api/* XHR<br/>Cookie or Bearer"| API
    API -->|"SQLAlchemy"| PG
    API -->|"redis-py"| RD
    API -->|"SMTP"| MAIL
    API -->|"token / userinfo"| GOOGLE
    BROWSER -->|"リダイレクト"| GOOGLE
```

## 4. バックエンドのレイヤ構成

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

### ディレクトリ構成（採用案・T-1）

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
│   │   │   ├── security.py        # パスワードハッシュ、トークン署名
│   │   │   ├── exceptions.py      # 業務例外とハンドラ
│   │   │   └── deps.py            # 共通DI（現在ユーザー、DBセッション等）
│   │   ├── api/routers/           # auth, projects, tasks, comments, users, admin
│   │   ├── schemas/               # リクエスト/レスポンスDTO
│   │   ├── service/               # auth_service, project_service, task_service...
│   │   ├── auth/                  # Strategy実装（session_auth/jwt_auth/oauth/base）
│   │   ├── repository/            # user_repo, project_repo, task_repo, redis_store...
│   │   ├── models/                # SQLAlchemy ORMモデル
│   │   ├── db.py                  # エンジン・セッションファクトリ
│   │   └── redis_client.py        # Redis接続プール
│   ├── tests/{unit/, integration/, conftest.py}
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/  （詳細は 05_frontend.md）
├── db/{migrations/, functions/, procedures/}
├── docker-compose.yml
├── .env / .env.example
└── tmp/   （git管理外）
```

## 5. 画面遷移図

```mermaid
stateDiagram-v2
    [*] --> Login: 未認証で任意URLへアクセス
    Login --> Register: 「新規会員登録はこちら」
    Login --> PasswordForgot: 「パスワードを忘れた方はこちら」
    Login --> Dashboard: ログイン成功
    Login --> Google: Googleでログイン
    Google --> Dashboard: コールバック成功
    Register --> Dashboard: 登録成功（自動ログイン）
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

## 6. 全体シーケンス

### 6.1 ログイン〜カンバン表示（session モード）

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
    API->>RD: SETEX session:{sid} TTL=1800
    API->>RD: SETEX csrf:{sid} TTL=1800
    API->>PG: INSERT login_history(success=true)
    API-->>FE: 204 + Set-Cookie(sid, csrf_token)
    FE->>API: GET /api/auth/me (Cookie)
    API->>RD: GET session:{sid}
    RD-->>API: {user_id, role}
    API-->>FE: 200 {user}
    FE->>API: GET /api/projects
    API->>PG: 所属プロジェクト取得
    API-->>FE: 200 [projects]
    FE->>API: GET /api/projects/{id}/tasks
    API-->>FE: 200 [tasks]
    FE-->>U: カンバンボード描画
```

### 6.2 タスクのドラッグ＆ドロップによるステータス変更

```mermaid
sequenceDiagram
    autonumber
    actor U as ユーザー
    participant FE as React SPA
    participant API as FastAPI
    participant PG as PostgreSQL

    U->>FE: カードを「進行中」列にドロップ
    FE->>FE: 楽観的更新（ローカルstate即時反映）
    FE->>API: PATCH /api/tasks/{id} {status, position}
    API->>API: 認証・プロジェクト所属チェック
    API->>PG: UPDATE tasks SET status, position, updated_at
    PG-->>API: 更新後の行
    API-->>FE: 200 {task}
    alt 失敗（403/409/500）
        FE->>FE: ロールバック（元の列に戻す）
        FE-->>U: エラートースト表示
    end
```

## 7. 主要コンポーネント相関図

```mermaid
flowchart LR
    subgraph routers
        AR["auth_router"]
        PR["projects_router"]
        TR["tasks_router"]
        ADR["admin_router"]
        UR["users_router"]
    end

    subgraph service
        AS["auth_service"]
        PS["project_service"]
        TS["task_service"]
        US["user_service"]
        MS["mail_service"]
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
        RS["redis_store"]
    end

    AR --> AS
    PR --> PS
    TR --> TS
    UR --> US
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
    US --> URP
```

## 8. データ全体像

```mermaid
flowchart LR
    subgraph redis["Redis（揮発・TTL失効）"]
        S1["session:{sid}"]
        S2["csrf:{sid}"]
        S3["refresh:{token_hash}"]
        S4["oauth_state:{state}"]
        S5["pwreset:{token_hash}"]
    end

    subgraph pg["PostgreSQL（永続）"]
        T1["users"]
        T2["oauth_accounts"]
        T3["projects"]
        T4["project_members"]
        T5["tasks"]
        T6["task_comments"]
        T7["login_history"]
    end

    S1 -->|user_id| T1
    S3 -->|user_id| T1
    S5 -->|user_id| T1
    T7 -->|user_id| T1
```

「ログインが有効かどうか」の判定は Redis のみを参照し、「誰がいつログインしたか」の履歴は PostgreSQL の `login_history` に残す。この分離により、Redis 再起動でログイン状態は失われても監査ログは残る。

## 9. 非機能設計サマリ

| 項目 | 方針 |
|------|------|
| パスワード保存 | argon2id（`passlib[argon2]`）。コストパラメータは環境変数化 |
| CSRF | session モード時のみ、Double Submit Cookie 方式で検証（[03_auth](./03_auth.md#7-csrf対策)） |
| トークン失効 | session/refresh はいずれも Redis のキー削除で即時失効 |
| ログ | 構造化ログ（JSON）。リクエストIDを付与し、認証イベントは監査目的で INFO 出力 |
| テスト | バックエンド pytest（Redis/PostgreSQL は実コンテナ接続）、フロント Vitest |
| 秘匿情報 | `.env` および GitHub Secrets 管理。リポジトリへ直接コミットしない |
| Redis永続化 | RDB/AOF 無効。再起動時に全ログアウトとなることを許容 |
