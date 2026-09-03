# 06 インフラ / CI・CD設計

## 1. 構成方針

| 項目 | 方針 |
|------|------|
| 実行環境 | ローカル（または自宅サーバー）の Docker Compose。クラウドは使用しない（要件書§0） |
| サービス構成 | `backend` / `frontend` / `postgres` / `redis` / `mailpit`（開発用SMTP。D-1により追加） |
| イメージ配布 | GHCR（GitHub Container Registry） |
| デプロイ | self-hosted runner から `docker compose pull && docker compose up -d` |
| ポート | 外部公開ポートは全て `.env` に定義。コンテナ内部ポートは固定値でよい |
| コマンド | `docker compose`（ハイフン付き `docker-compose` は使用しない） |

## 2. Docker Compose 構成

```mermaid
flowchart TB
    subgraph host["ホスト"]
        P1["${FRONTEND_PORT} → 80"]
        P2["${BACKEND_PORT} → 8000"]
        P3["${POSTGRES_PORT} → 5432"]
        P4["${REDIS_PORT} → 6379"]
        P5["${MAILPIT_UI_PORT} → 8025"]
    end

    subgraph net["cerberus_net (bridge)"]
        FE["frontend<br/>node:26 / nginx"]
        BE["backend<br/>python:3.14"]
        PG[("postgres:17<br/>volume: pgdata")]
        RD[("redis:8<br/>永続化なし")]
        MP["mailpit"]
    end

    P1 --> FE
    P2 --> BE
    P3 --> PG
    P4 --> RD
    P5 --> MP
    FE -->|"/api プロキシ"| BE
    BE --> PG
    BE --> RD
    BE --> MP
```

| サービス | イメージ | 依存 | ヘルスチェック | 備考 |
|----------|----------|------|---------------|------|
| `postgres` | `postgres:17-alpine` | - | `pg_isready` | volume `pgdata` で永続化 |
| `redis` | `redis:8-alpine` | - | `redis-cli ping` | `--save "" --appendonly no --maxmemory-policy noeviction`。**volumeなし** |
| `backend` | 自ビルド（`api/Dockerfile`） | postgres, redis（`service_healthy`） | `GET /health` | 起動時に `alembic upgrade head` |
| `frontend` | 自ビルド（`frontend/Dockerfile`） | backend | `GET /` | 本番相当はビルド成果物を nginx で配信 |
| `mailpit` | `axllent/mailpit` | - | - | SMTP `1025` / Web UI `8025`。開発専用 |

- `redis` に volume を割り当てないことで、要件書§4の「再起動で全ログアウト」という挙動を意図的に再現する
- `depends_on` は `condition: service_healthy` を用い、起動順序の競合を避ける
- 開発時はソースをバインドマウントしてホットリロード（`uvicorn --reload` / `vite dev`）、CD時はイメージ内の成果物を使う構成を `docker-compose.override.yml` で切り替える

## 3. Dockerfile 方針

### 3.1 backend（`api/Dockerfile`）

| 項目 | 内容 |
|------|------|
| ベース | `python:3.14-slim` |
| 構成 | マルチステージ（builder で `pip install --prefix`、runtime へコピー） |
| 実行ユーザー | 非root（`appuser`） |
| エントリポイント | `alembic upgrade head` → `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| キャッシュ | `requirements.txt` のみを先にコピーして `pip install` する（レイヤキャッシュ） |

### 3.2 frontend（`frontend/Dockerfile`）

| 項目 | 内容 |
|------|------|
| ベース | builder: `node:26-alpine` / runtime: `nginx:alpine` |
| 構成 | `npm ci` → `npm run build` → `dist/` を nginx へコピー |
| nginx設定 | SPA用に `try_files $uri /index.html`、`/api` を backend へ `proxy_pass` |
| ビルド時変数 | `VITE_*` は `ARG` で受け取る（ビルド時に埋め込まれるため、秘匿情報は渡さない） |

## 4. 環境変数一覧（`.env.example`）

`.env` はリポジトリにコミットせず、`.env.example` を雛形として配布する。CI/CD では GitHub Secrets から供給する。

### 4.1 共通・ポート

| 変数 | 例 | 説明 |
|------|-----|------|
| `COMPOSE_PROJECT_NAME` | `cerberus` | Compose プロジェクト名 |
| `APP_ENV` | `local` | `local` / `ci` / `production` |
| `LOG_LEVEL` | `INFO` | ログレベル |
| `FRONTEND_PORT` | `5173` | フロントの外部公開ポート |
| `BACKEND_PORT` | `8000` | APIの外部公開ポート |
| `POSTGRES_PORT` | `5432` | PostgreSQLの外部公開ポート |
| `REDIS_PORT` | `6379` | Redisの外部公開ポート |
| `MAILPIT_SMTP_PORT` | `1025` | Mailpit SMTPの外部公開ポート |
| `MAILPIT_UI_PORT` | `8025` | Mailpit Web UIの外部公開ポート |

### 4.2 データストア

| 変数 | 例 | 説明 |
|------|-----|------|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `cerberus` / *** / `cerberus` | PostgreSQL 初期化用 |
| `DATABASE_URL` | `postgresql+asyncpg://cerberus:***@postgres:5432/cerberus` | アプリ用接続文字列 |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` | `5` / `10` | コネクションプール |
| `REDIS_URL` | `redis://redis:6379/0` | アプリ用 |
| `REDIS_TEST_DB` | `1` | テスト用DB番号 |
| `LOGIN_HISTORY_RETENTION_DAYS` | `365` | `sp_purge_login_history` に渡す保持日数 |

### 4.3 認証

| 変数 | 例 | 説明 |
|------|-----|------|
| `AUTH_MODE` | `session` | `session` / `jwt` |
| `SESSION_TTL_SECONDS` | `1800` | セッションTTL |
| `ACCESS_TOKEN_TTL_SECONDS` | `900` | アクセストークン有効期限 |
| `REFRESH_TTL_SECONDS` | `1209600` | リフレッシュトークン有効期限（14日） |
| `JWT_SECRET_KEY` | *** | JWT署名鍵（**Secret**） |
| `JWT_ALGORITHM` | `HS256` | |
| `COOKIE_NAME_SESSION` / `COOKIE_NAME_CSRF` / `COOKIE_NAME_REFRESH` | `cerberus_sid` / `cerberus_csrf` / `cerberus_rt` | Cookie名 |
| `COOKIE_SECURE` | `false`（ローカルHTTP） | 本番相当では `true` |
| `COOKIE_SAMESITE` | `lax` | refresh Cookie は `strict` を別変数で指定 |
| `COOKIE_DOMAIN` | 空 | 必要時のみ設定 |
| `ARGON2_TIME_COST` / `ARGON2_MEMORY_COST` / `ARGON2_PARALLELISM` | `3` / `65536` / `4` | パスワードハッシュのコスト |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCK_WINDOW_SECONDS` | `5` / `900` | ログイン失敗のレート制限 |
| `CORS_ALLOW_ORIGINS` | `http://localhost:5173` | カンマ区切り |
| `ENABLE_API_DOCS` | `true` | `/api/docs` の有効化 |

### 4.4 OAuth2 / メール

| 変数 | 例 | 説明 |
|------|-----|------|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | *** | Google OAuth2（**Secret**） |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8000/api/auth/oauth/google/callback` | |
| `OAUTH_STATE_TTL_SECONDS` | `600` | state のTTL |
| `FRONTEND_BASE_URL` | `http://localhost:5173` | メール内リンク・OAuth後のリダイレクト先 |
| `SMTP_HOST` / `SMTP_PORT` | `mailpit` / `1025` | 開発は Mailpit |
| `SMTP_USER` / `SMTP_PASSWORD` | 空 | 本番SMTP利用時のみ（**Secret**） |
| `SMTP_USE_TLS` | `false` | |
| `MAIL_FROM` | `no-reply@cerberus.local` | 送信元 |
| `PASSWORD_RESET_TTL_SECONDS` | `1800` | リセットトークンTTL |

### 4.5 初期データ / フロント

| 変数 | 例 | 説明 |
|------|-----|------|
| `INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` | *** | seed 用管理者（**Secret**）。ハードコードしない |
| `VITE_API_BASE_URL` | `http://localhost:8000/api` | フロント（ビルド時埋め込み） |
| `VITE_AUTH_MODE` | `session` | フロント側の AuthAdapter 選択 |
| `VITE_GOOGLE_LOGIN_ENABLED` | `true` | Googleログインボタン表示 |
| `VITE_CSRF_COOKIE_NAME` | `cerberus_csrf` | |

**pydantic-settings による定義**：`api/app/core/config.py` に `Settings(BaseSettings)` を定義し、上記を型付きで受け取る。既定値はコード側に持たせるが、URL・ポート・秘密情報は必ず環境変数から取得する（ハードコード禁止）。

## 5. CI設計（`.github/workflows/ci.yml`）

### 5.1 トリガ

```yaml
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]
```

### 5.2 ジョブ構成

```mermaid
flowchart LR
    subgraph ci["ci.yml"]
        BL["backend-lint<br/>ruff + mypy"]
        BT["backend-test<br/>pytest（services: postgres/redis）"]
        FL["frontend-lint<br/>eslint + tsc --noEmit"]
        FT["frontend-test<br/>vitest"]
        DB["docker-build<br/>buildのみ / pushなし"]
    end
    BL --> DB
    BT --> DB
    FL --> DB
    FT --> DB
```

| ジョブ | 主なステップ | キャッシュ |
|--------|-------------|-----------|
| `backend-lint` | `ruff check` / `ruff format --check` / `mypy app` | `actions/setup-python` の `cache: pip` |
| `backend-test` | `services` で `postgres:17` / `redis:8` を起動 → `alembic upgrade head` → `pytest --cov=app --cov-report=xml` | 同上 |
| `frontend-lint` | `npm ci` → `eslint .` → `tsc --noEmit` | `actions/setup-node` の `cache: npm` |
| `frontend-test` | `npm ci` → `vitest run --coverage` | 同上 |
| `docker-build` | `docker/build-push-action`（`push: false`）で backend / frontend をビルド | GHA cache（`type=gha`） |

### 5.3 backend-test の環境変数

| 変数 | 値 |
|------|-----|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/cerberus_test` |
| `REDIS_URL` | `redis://localhost:6379/1` |
| `JWT_SECRET_KEY` | `${{ secrets.JWT_SECRET_KEY }}`（CI用のダミー値でよい） |
| `AUTH_MODE` | ジョブ内で `session` / `jwt` の matrix にする |
| `SMTP_HOST` | 未使用（テストではモック） |

```yaml
strategy:
  matrix:
    auth_mode: [session, jwt]
```

`AUTH_MODE` を matrix 化することで、両方式で全結合テストが通ることを保証する（本題材の中心テーマであるため）。

### 5.4 品質ゲート

| 項目 | 基準 |
|------|------|
| Lint / 型チェック | エラー0で必須 |
| バックエンドカバレッジ | 80% 以上（`--cov-fail-under=80`）。`omit` は `alembic/versions/*` のみ |
| フロントカバレッジ | 70% 以上（UI描画部分を含むため緩める） |
| PRマージ条件 | 上記全ジョブの成功を required status checks に設定 |

## 6. CD設計（`.github/workflows/cd.yml`）

### 6.1 フロー

```mermaid
sequenceDiagram
    autonumber
    actor DEV as 開発者
    participant GH as GitHub
    participant RUN as GitHub-hosted runner
    participant GHCR as GHCR
    participant SELF as self-hosted runner<br/>(自宅サーバー/PC)
    participant DC as Docker Compose

    DEV->>GH: main へマージ
    GH->>RUN: build-and-push ジョブ開始
    RUN->>RUN: docker build（backend / frontend）
    RUN->>GHCR: docker push<br/>tag: latest, sha-{短縮SHA}
    RUN-->>GH: 成功
    GH->>SELF: deploy ジョブ開始（needs: build-and-push）
    SELF->>SELF: .env を配置（GitHub Secrets から生成）
    SELF->>GHCR: docker compose pull
    SELF->>DC: docker compose up -d --remove-orphans
    DC->>DC: alembic upgrade head（backend起動時）
    SELF->>SELF: /health をポーリングして疎通確認
    alt ヘルスチェック失敗
        SELF->>DC: 直前のタグへロールバック（docker compose up -d）
        SELF-->>GH: ジョブ失敗
    else 成功
        SELF->>SELF: docker image prune -f
        SELF-->>GH: ジョブ成功
    end
```

### 6.2 ジョブ定義の要点

| 項目 | 内容 |
|------|------|
| トリガ | `on: push: branches: [main]` および `workflow_dispatch`（手動再実行） |
| イメージ名 | `ghcr.io/{owner}/cerberus-backend`、`ghcr.io/{owner}/cerberus-frontend` |
| タグ | `latest` と `sha-${{ github.sha }}`（ロールバック可能にするため両方付与） |
| 認証 | `docker/login-action` + `GITHUB_TOKEN`（`permissions: packages: write`） |
| deploy ジョブ | `runs-on: self-hosted`。`needs: build-and-push` |
| Secrets の受け渡し | deploy ジョブ内で `.env` をヒアドキュメント生成（`${{ secrets.* }}` を展開）。ワークフローログに出力しない |
| 環境 | GitHub Environments（`production`）を使い、必要に応じて承認を必須化 |
| 同時実行制御 | `concurrency: group: deploy-main, cancel-in-progress: false`（デプロイの競合を防ぐ） |

### 6.3 self-hosted runner のセットアップ

| 手順 | 内容 |
|------|------|
| 1 | リポジトリ Settings → Actions → Runners → New self-hosted runner |
| 2 | 対象マシンで配布スクリプトを実行し、`./config.sh --url ... --token ...` で登録 |
| 3 | `./svc.sh install && ./svc.sh start` でサービス常駐化（再起動後も動作） |
| 4 | runner 実行ユーザーを `docker` グループに追加 |
| 5 | ラベル（例：`self-hosted, linux, cerberus`）を付与し、ワークフローの `runs-on` で指定 |
| 注意 | self-hosted runner ではワークスペースが再利用されるため、`actions/checkout` の `clean: true` を明示する。またパブリックリポジトリでの利用は第三者PRからの任意コード実行リスクがあるため避ける |

## 7. 学習ポイント（要件書§8.3対応）

| 項目 | 本設計での該当箇所 |
|------|-------------------|
| ワークフロー構文（`on` / `jobs` / `steps`） | 5.1、6.2 |
| Secrets の利用方法 | 4章（**Secret** 表記の変数）、6.2 |
| 依存関係キャッシュ | 5.2（pip / npm / GHA build cache） |
| self-hosted runner | 6.3 |
| CI/CDのファイル分割 | `ci.yml`（品質検証）と `cd.yml`（配布・反映）に責務分離 |
| matrix ビルド | 5.3（`AUTH_MODE` の両方式検証） |

## 8. 運用時の確認事項

| 項目 | 内容 |
|------|------|
| バックアップ | `pgdata` volume の `pg_dump` 手動取得のみ（自動化はスコープ外） |
| 監視 | `/health` の手動確認のみ。監視・アラートはスコープ外（要件書§11） |
| ログ | コンテナ標準出力（`docker compose logs`）。集約はスコープ外 |
| シークレットローテーション | `JWT_SECRET_KEY` を変更すると全アクセストークンが無効になる（リフレッシュはRedis管理のため生存）。挙動を理解した上で実施すること |
| マイグレーション失敗時 | backend コンテナが起動失敗するため、直前タグへロールバックし `alembic downgrade` を手動実行する。**要検討**（自動ロールバック手順の整備） |
