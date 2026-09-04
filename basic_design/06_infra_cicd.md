# 06 インフラ / CI・CD設計

## 1. 構成方針

| 項目 | 方針 |
|------|------|
| 実行環境 | ローカル（または自宅サーバー）の Docker Compose。クラウドは使用しない（要件書§0） |
| サービス構成 | `backend` / `frontend` / `postgres` / `redis`。`mailpit` は開発Compose profileだけで有効化し、デプロイ環境は外部SMTPを使う |
| イメージ配布 | GHCR（GitHub Container Registry） |
| デプロイ | self-hosted runner から `docker compose pull && docker compose up -d` |
| ポート | 通常は `frontend` のみをloopbackまたは必要な公開IFへ公開。backend / PostgreSQL / Redis / SMTPはComposeネットワーク内に閉じ、開発用の追加ポートも `127.0.0.1` に限定 |
| コマンド | `docker compose`（ハイフン付き `docker-compose` は使用しない） |

## 2. Docker Compose 構成

```mermaid
flowchart TB
    subgraph host["ホスト"]
        P1["${FRONTEND_PORT} → 80"]
    end

    subgraph net["cerberus_net (bridge)"]
        FE["frontend<br/>node:26 / nginx"]
        BE["backend<br/>python:3.14"]
        BA["batch<br/>python:3.14<br/>常駐スケジューラ"]
        PG[("postgres:17<br/>volume: pgdata")]
        RD[("redis:8<br/>永続化なし")]
        MP["mailpit"]
    end

    P1 --> FE
    FE -->|"/api プロキシ"| BE
    BE --> PG
    BE --> RD
    BE --> MP
    BA --> PG
    BA --> RD
```

| サービス | イメージ | 依存 | ヘルスチェック | 備考 |
|----------|----------|------|---------------|------|
| `postgres` | `postgres:17-alpine` | - | `pg_isready` | volume `pgdata` で永続化。ホストポートは公開しない |
| `redis` | `redis:8-alpine` | - | `redis-cli ping` | `--save "" --appendonly no --maxmemory-policy noeviction`。**volumeなし**。ホストポートは公開しない |
| `backend` | 自ビルド（`api/Dockerfile`） | postgres, redis（`service_healthy`） | `GET /health` | 起動時に `alembic upgrade head` |
| `batch` | 自ビルド（`batch/Dockerfile`） | postgres, redis（`service_healthy`） | プロセス生存監視（`pgrep -f app.main`） | 常駐スケジューラ。ポートは公開しない。マイグレーションは実行しない（backend の責務） |
| `frontend` | 自ビルド（`frontend/Dockerfile`） | backend | `GET /` | 本番相当はビルド成果物を nginx で配信 |
| `mailpit` | `axllent/mailpit` | - | - | SMTP `1025` / Web UI `8025`。`dev` profile専用。UI/SMTPはloopback公開のみ |

- `redis` に volume を割り当てないことで、要件書§4の「再起動で全ログアウト」という挙動を意図的に再現する
- `depends_on` は `condition: service_healthy` を用い、起動順序の競合を避ける。backendはmailpitを使う開発profileでのみmailpitにも依存する
- 開発時はソースをバインドマウントしてホットリロード（`uvicorn --reload` / `vite dev`）、CD時はイメージ内の成果物を使う構成を `docker-compose.override.yml` で切り替える
- 基本Composeは `frontend` の `/api` proxyを経由する。`backend` / `postgres` / `redis` は `ports` を持たず、開発者が直接接続する場合だけ `compose.dev.yml` で `127.0.0.1:${...}` を追加する
- `mailpit` は `profiles: [dev]` とし、production/CDでは起動しない。productionの `SMTP_HOST` は外部SMTPを指定する
- `batch` は `backend` に依存させない（HTTP APIを呼ばずDB/Redisへ直接アクセスするため）。ただしスキーマは backend 起動時の `alembic upgrade head` に依存するため、`restart: unless-stopped` とし、テーブル未作成で起動に失敗した場合は再起動で回復させる
- `batch` を1レプリカに限定する（`deploy.replicas` を指定しない）。複数起動しても Redis の実行ロックと `UNIQUE (user_id, dedupe_key)` により通知は重複しないが、無駄なDB走査を避けるため

### 2.1 batch コンテナの構成

| 項目 | 内容 |
|------|------|
| 役割 | 定期実行ジョブの常駐スケジューラ。現在は要件書§3.4 N-1（毎日10時・17時の期限通知）を実行し、将来のメール通知等の定期ジョブ追加にも使用する |
| スケジューラ | APScheduler（`AsyncIOScheduler` + `CronTrigger`）。タイムゾーンは `APP_TIMEZONE` |
| ジョブ | `due_notification_job_10` と `due_notification_job_17` の2つを登録し、`NOTIFY_DUE_RUN_HOURS` と `NOTIFY_DUE_CRON_MINUTE` に従って実行する。ジョブ末尾で `sp_purge_notifications` を呼び保持期間超過分を削除する |
| 二重実行防止 | Redis の `lock:notify_due:{YYYY-MM-DD}:{slot}`（`SET NX EX`）。詳細は [02_redis.md §4.4](./02_redis.md#44-期限通知バッチの実行ロック) |
| 依存の方向 | `jobs → repository → models`。`api/app` のコードは import せず、共有が必要なORMモデルは `batch` 側に同等の定義を置く（コンテナ間でソースを共有しないため） |
| 手動実行 | `docker compose run --rm batch python -m app.main --run-once due_notification --slot 10`（17時枠は`--slot 17`。障害時のリカバリ用） |

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

### 3.3 batch（`batch/Dockerfile`）

| 項目 | 内容 |
|------|------|
| ベース | `python:3.14-slim` |
| 構成 | マルチステージ（builder で `pip install --prefix`、runtime へコピー）。backend と同じ方針 |
| 実行ユーザー | 非root（`appuser`） |
| エントリポイント | `python -m app.main`（常駐。`alembic upgrade head` は実行しない） |
| キャッシュ | `requirements.txt` のみを先にコピーして `pip install` する |

## 4. 環境変数一覧（`.env.example`）

`.env` はリポジトリにコミットせず、`.env.example` を雛形として配布する。CI/CD では GitHub Secrets から供給する。

### 4.1 共通・ポート

| 変数 | 例 | 説明 |
|------|-----|------|
| `COMPOSE_PROJECT_NAME` | `cerberus` | Compose プロジェクト名 |
| `APP_ENV` | `local` | `local` / `ci` / `production` |
| `LOG_LEVEL` | `INFO` | ログレベル |
| `APP_TIMEZONE` | `Asia/Tokyo` | 業務上の日次境界（「当日」「10時・17時」）の判定に使うタイムゾーン。DBはUTC保存のまま。backend / batch の両方に渡す |
| `FRONTEND_PORT` | `5173` | フロントの外部公開ポート |
| `BACKEND_PORT` | `8000` | 開発時にbackendへ接続する場合だけ `127.0.0.1` に公開。通常のCompose/CDでは未公開 |
| `POSTGRES_PORT` | `5432` | 開発用DB接続が必要な場合だけ `127.0.0.1` に公開 |
| `REDIS_PORT` | `6379` | 開発用Redis接続が必要な場合だけ `127.0.0.1` に公開 |
| `MAILPIT_SMTP_PORT` | `1025` | Mailpitを使う開発時だけ `127.0.0.1` に公開 |
| `MAILPIT_UI_PORT` | `8025` | Mailpitを使う開発時だけ `127.0.0.1` に公開 |

### 4.2 データストア

| 変数 | 例 | 説明 |
|------|-----|------|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `cerberus` / *** / `cerberus` | PostgreSQL 初期化用 |
| `DATABASE_URL` | `postgresql+asyncpg://cerberus:***@postgres:5432/cerberus` | アプリ用接続文字列 |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` | `5` / `10` | コネクションプール |
| `REDIS_URL` | `redis://redis:6379/0` | アプリ用 |
| `REDIS_KEY_PREFIX` | 空 | 環境を共有する場合のRedisキー名前空間 |
| `REDIS_TEST_DB` | `1` | テスト用DB番号 |
| `LOGIN_HISTORY_RETENTION_DAYS` | `90` | `sp_purge_login_history` に渡すログイン履歴の保持日数 |
| `NOTIFICATION_RETENTION_DAYS` | `90` | `sp_purge_notifications` に渡す通知の保持日数 |
| `API_HISTORY_RETENTION_DAYS` | `30` | `sp_purge_api_history` に渡すAPI履歴の保持日数 |
| `BATCH_HISTORY_RETENTION_DAYS` | `30` | `sp_purge_batch_history` に渡すbatch履歴の保持日数 |
| `API_HISTORY_BODY_MAX_BYTES` | `65536` | `api_history.body`へ保存するJSON bodyの最大サイズ |
| `API_HISTORY_ERROR_DETAIL_MAX_LENGTH` | `4000` | `api_history.error_detail`の最大文字数 |
| `PAGINATION_DEFAULT_PER_PAGE` / `PAGINATION_MAX_PER_PAGE` | `20` / `100` | ページング対象APIの既定件数・上限。上限超過は422 |

### 4.3 認証

| 変数 | 例 | 説明 |
|------|-----|------|
| `AUTH_MODE` | `session` | `session` / `jwt` |
| `SESSION_TTL_SECONDS` | `1800` | セッションTTL |
| `SESSION_ABSOLUTE_TTL_SECONDS` | `28800` | sessionの絶対有効期限（8時間）。アイドル延長の上限 |
| `ACCESS_TOKEN_TTL_SECONDS` | `900` | アクセストークン有効期限 |
| `REFRESH_TTL_SECONDS` | `1209600` | リフレッシュトークン有効期限（14日） |
| `JWT_SECRET_KEY` | *** | JWT署名鍵（**Secret**） |
| `JWT_ALGORITHM` | `HS256` | |
| `COOKIE_NAME_SESSION` / `COOKIE_NAME_CSRF` / `COOKIE_NAME_REFRESH` / `COOKIE_NAME_OAUTH_STATE` | `cerberus_sid` / `cerberus_csrf` / `cerberus_rt` / `cerberus_oauth_state` | Cookie名 |
| `COOKIE_SECURE` | `false`（ローカルHTTP） | 本番相当では `true` |
| `COOKIE_SAMESITE` / `COOKIE_SAMESITE_REFRESH` | `lax` / `strict` | session/CSRFはLax、jwt refreshはStrict。別オリジン構成ではSecure + 明示CSRF/Origin検証を必須 |
| `COOKIE_DOMAIN` | 空 | 必要時のみ設定 |
| `ARGON2_TIME_COST` / `ARGON2_MEMORY_COST` / `ARGON2_PARALLELISM` | `3` / `65536` / `4` | パスワードハッシュのコスト |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCK_WINDOW_SECONDS` | `5` / `900` | ログイン失敗のレート制限 |
| `RATE_LIMIT_REGISTER_MAX_REQUESTS` / `RATE_LIMIT_REGISTER_WINDOW_SECONDS` | `5` / `900` | 会員登録のIP単位Rate Limit |
| `RATE_LIMIT_EMAIL_VERIFY_MAX_REQUESTS` / `RATE_LIMIT_EMAIL_VERIFY_RESEND_MAX_REQUESTS` | `10` / `5` | メール認証・再送のIP単位Rate Limit |
| `RATE_LIMIT_PASSWORD_FORGOT_MAX_REQUESTS` / `RATE_LIMIT_PASSWORD_RESET_MAX_REQUESTS` | `5` / `10` | パスワード再設定要求・実行のIP単位Rate Limit |
| `RATE_LIMIT_OAUTH_MAX_REQUESTS` / `RATE_LIMIT_OAUTH_WINDOW_SECONDS` | `10` / `900` | OAuth開始・callback・exchangeの各IP単位Rate Limit |
| `RATE_LIMIT_NOTIFICATION_READ_MAX_REQUESTS` / `RATE_LIMIT_NOTIFICATION_WRITE_MAX_REQUESTS` | `120` / `60` | 通知APIのuser_id + IP単位Rate Limit（時間窓60秒） |
| `TRUSTED_PROXY_CIDRS` | 空 | `X-Forwarded-For`を信頼するProxyのCIDR。空の場合は接続元IPのみ使用 |
| `CORS_ALLOW_ORIGINS` | `http://localhost:5173` | カンマ区切り |
| `ENABLE_API_DOCS` | `true` | `/api/docs` の有効化 |

### 4.4 OAuth2 / メール

| 変数 | 例 | 説明 |
|------|-----|------|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | *** | Google OAuth2（**Secret**） |
| `GOOGLE_LOGIN_ENABLED` | `true` | Googleログイン機能の有効/無効 |
| `GOOGLE_REDIRECT_URI` | `http://localhost:5173/api/auth/oauth/google/callback` | frontendのsame-origin `/api` proxyを経由。外部公開時はfrontendのHTTPS URL |
| `GOOGLE_AUTHORIZE_ENDPOINT` | `https://accounts.google.com/o/oauth2/v2/auth` | Google認可エンドポイント |
| `GOOGLE_TOKEN_ENDPOINT` | `https://oauth2.googleapis.com/token` | Google tokenエンドポイント |
| `GOOGLE_USERINFO_ENDPOINT` | `https://openidconnect.googleapis.com/v1/userinfo` | Google userinfoエンドポイント |
| `GOOGLE_JWKS_URI` | `https://www.googleapis.com/oauth2/v3/certs` | Google公開鍵取得元 |
| `GOOGLE_JWKS_CACHE_TTL_SECONDS` | `3600` | Google公開鍵キャッシュTTL |
| `OAUTH_STATE_TTL_SECONDS` | `600` | state のTTL |
| `OAUTH_HANDOFF_TTL_SECONDS` | `60` | jwtモードのOAuth一時コードTTL |
| `OAUTH_DEFAULT_REDIRECT_TO` | `/dashboard` | OAuth完了後の既定遷移先 |
| `FRONTEND_BASE_URL` | `http://localhost:5173` | メール内リンク・OAuth後のリダイレクト先 |
| `SMTP_HOST` / `SMTP_PORT` | `mailpit` / `1025` | 開発は Mailpit |
| `SMTP_USER` / `SMTP_PASSWORD` | 空 | 本番SMTP利用時のみ（**Secret**） |
| `SMTP_USE_TLS` | `false` | |
| `MAIL_FROM` | `no-reply@cerberus.local` | 送信元 |
| `PASSWORD_RESET_TTL_SECONDS` | `1800` | リセットトークンTTL |
| `EMAIL_VERIFY_TTL_SECONDS` | `86400` | メール認証トークンTTL（24時間） |
| `EMAIL_VERIFY_RESEND_INTERVAL_SECONDS` | `60` | 認証メール再送の最小間隔 |

### 4.5 通知 / 定期実行（batch）

| 変数 | 例 | 説明 |
|------|-----|------|
| `NOTIFY_DUE_RUN_HOURS` | `10,17` | 期限通知バッチを登録する実行時刻（`APP_TIMEZONE` 基準）。値ごとに別cronジョブを1つずつ登録する |
| `NOTIFY_DUE_CRON_MINUTE` | `0` | 期限通知バッチの実行分 |
| `NOTIFY_DUE_TARGET_HOUR` | `10` | 10時・17時の両実行枠で共通して使う対象期限の翌日境界（`APP_TIMEZONE` 基準） |
| `NOTIFY_DUE_LOCK_TTL_SECONDS` | `82800` | 実行ロック `lock:notify_due:{日付}:{slot}` のTTL（23時間） |
| `NOTIFY_DUE_BATCH_CHUNK_SIZE` | `500` | 通知INSERTを分割する件数。1回のトランザクションを短く保つ |
| `BATCH_ENABLED` | `true` | `false` にするとスケジューラを登録せず常駐のみ（CI・検証用） |

`NOTIFY_DUE_RUN_HOURS` / `NOTIFY_DUE_CRON_MINUTE` / `NOTIFY_DUE_TARGET_HOUR` をコードに直書きせず環境変数化することで、「10時・17時に実行／翌日10時まで」という業務ルールを設定変更だけで調整できるようにする。`NOTIFY_DUE_RUN_HOURS` の各値は独立したcronジョブとして登録する。

### 4.6 初期データ / フロント

| 変数 | 例 | 説明 |
|------|-----|------|
| `INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` | *** | seed 用管理者（**Secret**）。3項目すべて必須。未設定・空文字ならAlembic/backendを起動しない。ハードコードしない |
| `VITE_API_BASE_URL` | `/api` | フロントのAPIベースURL（ビルド時埋め込み）。認証モード等は `/auth/config` で実行時取得 |
| `VITE_NOTIFICATION_POLL_INTERVAL_MS` | `60000` | 未読通知件数のポーリング間隔（ミリ秒。ビルド時埋め込み） |

**pydantic-settings による定義**：`api/app/core/config.py` および `batch/app/core/config.py` に `Settings(BaseSettings)` を定義し、上記を型付きで受け取る。既定値はコード側に持たせるが、URL・ポート・秘密情報は必ず環境変数から取得する（ハードコード禁止）。

初期管理者の3環境変数は起動時に空文字も含めて検証する。不足時はseedをスキップせず、HTTP受付前にbackendをfail-closeで終了させる。CIでは専用のダミーSecretを注入する。

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
        BAT["batch-test<br/>ruff + mypy + pytest"]
        FL["frontend-lint<br/>eslint + tsc --noEmit"]
        FT["frontend-test<br/>vitest"]
        DB["docker-build<br/>buildのみ / pushなし"]
    end
    BL --> DB
    BT --> DB
    BAT --> DB
    FL --> DB
    FT --> DB
```

| ジョブ | 主なステップ | キャッシュ |
|--------|-------------|-----------|
| `backend-lint` | `ruff check` / `ruff format --check` / `mypy app` | `actions/setup-python` の `cache: pip` |
| `backend-test` | `services` で `postgres:17` / `redis:8` を起動 → `alembic upgrade head` → `pytest --cov=app --cov-report=xml` | 同上 |
| `frontend-lint` | `npm ci` → `eslint .` → `tsc --noEmit` | `actions/setup-node` の `cache: npm` |
| `frontend-test` | `npm ci` → `vitest run --coverage` | 同上 |
| `batch-test` | `ruff check` / `mypy app` → `services` の `postgres:17` / `redis:8` に接続して `pytest --cov=app` | `actions/setup-python` の `cache: pip` |
| `docker-build` | `docker/build-push-action`（`push: false`）で backend / frontend / batch をビルド | GHA cache（`type=gha`） |

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
    RUN->>RUN: docker build（backend / frontend / batch）
    RUN->>GHCR: docker push<br/>tag: latest, sha-{短縮SHA}
    RUN-->>GH: 成功
    GH->>SELF: deploy ジョブ開始（needs: build-and-push）
    SELF->>SELF: .env を配置（GitHub Secrets から生成）
    SELF->>GHCR: docker compose pull
    SELF->>DC: docker compose up -d --remove-orphans
    DC->>DC: alembic upgrade head（backend起動時）
    SELF->>SELF: frontend経由の /api/health をポーリングして疎通確認
    alt ヘルスチェック失敗
        SELF->>DC: アプリイメージだけ直前タグへ戻して再起動（DB downgradeなし）
        SELF-->>GH: ジョブ失敗
    else 成功
        SELF->>SELF: Cerberus管理ラベル付きイメージだけprune
        SELF-->>GH: ジョブ成功
    end
```

### 6.2 ジョブ定義の要点

| 項目 | 内容 |
|------|------|
| トリガ | `on: push: branches: [main]` および `workflow_dispatch`（手動再実行） |
| イメージ名 | `ghcr.io/{owner}/cerberus-backend`、`ghcr.io/{owner}/cerberus-frontend`、`ghcr.io/{owner}/cerberus-batch` |
| タグ | `latest` と `sha-${{ github.sha }}`（ロールバック可能にするため両方付与） |
| 認証 | `docker/login-action` + `GITHUB_TOKEN`（`permissions: packages: write`） |
| deploy ジョブ | `runs-on: self-hosted`。`needs: build-and-push` |
| Secrets の受け渡し | deploy ジョブ内で `.env` をヒアドキュメント生成（`${{ secrets.* }}` を展開）。ワークフローログに出力しない |
| 環境 | GitHub Environments（`production`）を使い、必要に応じて承認を必須化 |
| 同時実行制御 | `concurrency: group: deploy-main, cancel-in-progress: false`（デプロイの競合を防ぐ） |
| イメージ削除 | `docker image prune` は `com.cerberus.managed=true` ラベル付きイメージだけを対象にする。共有ホスト上の他プロジェクトを削除しない |

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
| ログ | 構造化標準出力に加え、APIは`api_history`、batchは`batch_history`へ保存。API・batchは30日、ログイン履歴は90日。集約基盤はスコープ外 |
| 定期通知の確認 | `docker compose logs batch` で10時・17時の実行ログ（対象件数・作成件数）を確認する。実行されていない場合は `BATCH_ENABLED` と `APP_TIMEZONE`、Redisの `lock:notify_due:{日付}:{slot}` の残存を確認し、必要なら `docker compose run --rm batch python -m app.main --run-once due_notification --slot 10` で手動実行する |
| 通知の肥大化 | `notifications` は `sp_purge_notifications`（`NOTIFICATION_RETENTION_DAYS`、既定90日）で日次ジョブ内から削除される。保持日数を延ばす場合は行数の増加に注意する |
| 履歴の肥大化 | `api_history` / `batch_history` は `sp_purge_api_history` / `sp_purge_batch_history`（各既定30日）で日次削除する。`login_history`は`sp_purge_login_history`（既定90日）で削除する |
| シークレットローテーション | `JWT_SECRET_KEY` を変更すると全アクセストークンが無効になる（リフレッシュはRedis管理のため生存）。挙動を理解した上で実施すること |
| マイグレーション失敗時 | backend コンテナは起動失敗とし、DBバックアップとログを確認して原因を修正する。アプリイメージだけを直前タグへ戻し、**適用済みmigrationを自動downgradeしない**。旧アプリが新しいスキーマと後方互換であることを前提にし、不可逆変更はexpand/contract方式で段階適用する |
