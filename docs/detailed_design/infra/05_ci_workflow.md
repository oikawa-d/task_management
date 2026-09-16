# infra/05 CIワークフロー（`.github/workflows/ci.yml`）

## 0. 関連ドキュメント

- 基本設計：[../../basic_design/06_infra_cicd.md](../../basic_design/06_infra_cicd.md)（§5 CI設計、§7 学習ポイント）、[../../basic_design/00_overview.md](../../basic_design/00_overview.md)
- 詳細設計：[01_docker_compose.md](./01_docker_compose.md)、[04_env_config.md](./04_env_config.md)、[06_cd_workflow.md](./06_cd_workflow.md)、[../database/09_migration.md](../database/09_migration.md)（マイグレーション適用手順）、[../auth/00_strategy_base.md](../auth/00_strategy_base.md)（`AUTH_MODE`切替）

## 1. 概要

| 項目 | 内容 |
|------|------|
| 対象 | `.github/workflows/ci.yml` |
| 責務 | push/pull_request をトリガーに、backend/frontendのLint・型チェック・テスト・カバレッジ検証、batch専用コンテナからDB/Redisへの直接接続検証、およびbackend/frontend/batch Dockerイメージのビルド確認（push なし）を行う |
| 適用条件 | `push: branches: [main, develop]`、`pull_request`（baseブランチ制限なし） |
| 同時実行制御 | `group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}`、`cancel-in-progress: true`。同一PRまたは同一ブランチの古い実行をキャンセルする |
| 依存先 | GitHub Actions `services`（PostgreSQL・Redis）、Docker Compose、GHA組み込みキャッシュ（`actions/setup-python`・`actions/setup-node`）、`docker/build-push-action` |
| 実装ファイル | `.github/workflows/ci.yml` |

## 2. 構成要素

| 要素 | 種別 | 責務 | 備考 |
|------|------|------|------|
| `detect` | ジョブ | 実装ディレクトリとDockerfileの有無を判定し、後続ジョブの条件へ出力 | 依存なし。`api` / `batch` / `frontend` / `docker`を出力 |
| `docs-check` | ジョブ | 変更差分の空白エラーを検証 | 依存なし。pushまたはpull_requestの差分を検査 |
| `workflow-lint` | ジョブ | `ci.yml`の構成テストを実行 | 依存なし。`tests/ci/test_ci_workflow.py`を実行 |
| `hook-test` | ジョブ | GitHub破壊操作hookのシェルテストを実行 | 依存なし。`.agents/hooks/*.test.sh`を実行 |
| `backend-lint` | ジョブ | `ruff check` / `ruff format --check` / `mypy app` | `needs: detect`。`detect.api == 'true'`のとき実行。Python 3.14 |
| `backend-test` | ジョブ | `services`でPostgreSQL/Redis起動 → `alembic upgrade head` → `pytest --cov` | `needs: detect`、`detect.api == 'true'`。`AUTH_MODE`をmatrix化（`session`/`jwt`） |
| `frontend-lint` | ジョブ | `eslint .` / `tsc --noEmit` | `needs: detect`、`detect.frontend == 'true'`。Node v26 |
| `frontend-test` | ジョブ | `vitest run --coverage` | `needs: detect`、`detect.frontend == 'true'` |
| `batch-test` | ジョブ | `services`でPostgreSQL/Redis起動 → batchのlint・型チェック・テスト | `needs: detect`、`detect.batch == 'true'` |
| `batch-container-integration` | ジョブ | `compose.integration.yml`でPostgreSQL/Redisを起動し、batchコンテナから直接接続 | `needs: detect`、`detect.batch == 'true'`。`RUN_BATCH_CONTAINER_INTEGRATION=1`で受入テストを有効化 |
| `docker-build` | ジョブ | backend/frontend/batchイメージのビルド確認（`push: false`） | `needs: detect`およびbackend/frontend/batchの5検証job。`detect.docker == 'true'`のとき実行 |
| `postgres` service | GitHub Actions `services` | `backend-test`用の一時PostgreSQLコンテナ | `postgres:17-alpine` |
| `redis` service | GitHub Actions `services` | `backend-test`用の一時Redisコンテナ | `redis:8-alpine` |

## 3. 設定項目（環境変数）

| 変数名 | 型 | 既定値 | 用途 | 秘匿 |
|--------|-----|--------|------|------|
| `DATABASE_URL` | str | `postgresql+asyncpg://postgres:postgres@localhost:5432/cerberus_test` | `backend-test`ジョブの接続文字列（`services`のPostgreSQLへ`localhost`経由で接続） | 否（CI専用の固定値。本番`.env`とは別物） |
| `REDIS_URL` | str | `redis://localhost:6379/1`（`REDIS_TEST_DB`使用） | `backend-test`ジョブのRedis接続文字列 | 否 |
| `JWT_SECRET_KEY` | str | `${{ secrets.CI_JWT_SECRET_KEY }}` | jwtモードのテストに必要な署名鍵（CI用ダミー値） | **Secret**（GitHub Secrets） |
| `AUTH_MODE` | Literal["session","jwt"] | `strategy.matrix.auth_mode` | 両認証方式でテストを実行するためのmatrix変数 | 否 |
| `INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` | str | CIダミー値 | シードマイグレーション（[../database/09_migration.md](../database/09_migration.md)§3）に必須 | `INITIAL_ADMIN_PASSWORD`のみ**Secret**（`${{ secrets.CI_INITIAL_ADMIN_PASSWORD }}`） |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | str | CIダミー値 | `Settings`の必須項目バリデーションを通すためのダミー（実通信は行わない） | **Secret** |
| `SMTP_HOST` | str | 未使用（テストではモック） | メール送信はモック化し実通信しない | 否 |

上記以外の環境変数は [04_env_config.md](./04_env_config.md) の全一覧に従い、CIジョブの `env:` ブロックで注入する。値のハードコーディングを避け、GitHub Secretsまたはジョブ`env:`経由で供給する。

## 4. 全体の出入力

| 区分 | 内容 |
|------|------|
| 入力 | `push`イベント（`main`/`develop`）、またはbaseブランチを限定しない`pull_request`イベント、リポジトリのソース一式、GitHub Secrets（`CI_JWT_SECRET_KEY`等） |
| 出力 | 各ジョブの成功/失敗ステータス（required status checks）、カバレッジレポート（`coverage.xml`等、アーティファクト保存は任意） |
| 副作用 | `services`またはComposeで起動した一時PostgreSQL/Redisへの接続（ジョブ終了時に破棄）。永続化なし。イメージはビルドのみでpushしない |

## 5. シーケンス図

### 5.1 CI全体フロー（正常系）

```mermaid
sequenceDiagram
    autonumber
    actor DEV as 開発者
    participant GH as GitHub
    participant DET as detect
    participant DOC as docs-check
    participant WFL as workflow-lint
    participant HT as hook-test
    participant BL as backend-lint
    participant BT as backend-test
    participant FL as frontend-lint
    participant FT as frontend-test
    participant BATCHT as batch-test
    participant BI as batch-container-integration
    participant DB as docker-build

    DEV->>GH: push（main, develop）/ pull_request（base制限なし）
    GH->>GH: concurrency group単位で旧実行をキャンセル
    GH->>DET: ジョブ起動
    GH->>DOC: ジョブ起動
    GH->>WFL: ジョブ起動
    GH->>HT: ジョブ起動
    DET-->>GH: api / batch / frontend / docker の判定結果
    GH->>BL: `api`出力がtrueなら起動
    GH->>BT: `api`出力がtrueなら起動（matrix: session, jwt）
    GH->>FL: `frontend`出力がtrueなら起動
    GH->>FT: `frontend`出力がtrueなら起動
    GH->>BATCHT: `batch`出力がtrueなら起動
    GH->>BI: `batch`出力がtrueなら起動
    par 10個の検証jobを並行実行
        DOC->>DOC: git diff --check
        WFL->>WFL: ci.yml構成テスト
        HT->>HT: hookテスト
        BL->>BL: ruff check / format --check / mypy app
        BT->>BT: services起動 → alembic upgrade head → pytest --cov
        FL->>FL: eslint . / tsc --noEmit
        FT->>FT: vitest run --coverage
        BATCHT->>BATCHT: ruff check / format --check / mypy app → pytest --cov
        BI->>BI: Compose起動 → batchコンテナからDB/Redisへ接続
    end
    DET-->>GH: success
    DOC-->>GH: success
    WFL-->>GH: success
    HT-->>GH: success
    BL-->>GH: success
    BT-->>GH: success（2 matrix jobs）
    FL-->>GH: success
    FT-->>GH: success
    GH->>DB: ジョブ起動（needs: detectおよび上記5検証job）
    DB->>DB: docker/build-push-action（push: false）でbackend/frontend/batchをビルド
    DB-->>GH: success
    GH-->>DEV: 全チェックgreen（ブランチ保護の必須チェックを満たす）
```

### 5.2 backend-testでのカバレッジ不足（異常系）

```mermaid
sequenceDiagram
    autonumber
    participant GH as GitHub
    participant BT as backend-test
    participant PG as "services: postgres"
    participant RD as "services: redis"

    GH->>BT: ジョブ起動
    BT->>PG: healthcheck待機（pg_isready）
    BT->>RD: healthcheck待機（redis-cli ping）
    BT->>BT: alembic upgrade head
    BT->>BT: pytest --cov=app --cov-report=xml --cov-fail-under=80
    alt カバレッジ80%未満
        BT-->>GH: 失敗（exit code != 0）
        Note over GH: required status checkのためマージブロック
    else 80%以上
        BT-->>GH: success
    end
```

## 6. 処理フロー・分岐

```mermaid
flowchart TB
    A["push（main, develop）/<br/>pull_request（base制限なし）"] --> DET["detect<br/>api / batch / frontend / docker"]
    A --> DOC["docs-check"]
    A --> WFL["workflow-lint"]
    A --> HT["hook-test"]
    DET --> B["条件を満たす検証jobを並行起動<br/>backend-lint / backend-test<br/>frontend-lint / frontend-test<br/>batch-test / batch-container-integration"]
    B --> C{"backend-lint:<br/>ruff/mypyエラー0?"}
    C -->|No| F1["失敗・以降のdocker-buildへ進まない"]
    C -->|Yes| D["backend-test（matrix: session, jwt）"]
    D --> E{"services healthcheck OK?"}
    E -->|"No（タイムアウト）"| F2["ジョブ失敗<br/>fail-close：後続docker-buildは実行しない"]
    E -->|Yes| G["alembic upgrade head"]
    G --> H{"マイグレーション成功?"}
    H -->|No| F2
    H -->|Yes| I["pytest --cov=app --cov-fail-under=80"]
    I --> J{"両matrix（session/jwt）成功<br/>かつカバレッジ80%以上?"}
    J -->|No| F2
    J -->|Yes| K["backend-test成功"]
    B --> L["frontend-lint: eslint . / tsc --noEmit"]
    L --> M{"エラー0?"}
    M -->|No| F1
    M -->|Yes| N["frontend-test: vitest run --coverage"]
    N --> O{"カバレッジ70%以上?"}
    O -->|No| F3["ジョブ失敗"]
    O -->|Yes| P["frontend-test成功"]
    B --> BTEST["batch-test:<br/>ruff/mypy/pytest成功?"]
    BTEST -->|No| F4B["batch-test失敗"]
    BTEST -->|Yes| BTESTOK["batch-test成功"]
    B --> BI["batch-container-integration"]
    BI --> BJ{"batchコンテナから<br/>DB/Redis接続成功?"}
    BJ -->|No| F4["受入検証失敗"]
    BJ -->|Yes| BOK["batch-container-integration成功"]
    C -->|Yes| Q{"backend-lint/test<br/>frontend-lint/test<br/>batch-testを含む5検証jobがsuccess?"}
    K --> Q
    P --> Q
    Q -->|Yes| R["docker-build起動<br/>（needs: detect + 5検証job、push: false）"]
    Q -->|No| S["docker-buildはneeds未達成でskip扱い"]
    R --> T{"backend/frontend/batchとも<br/>ビルド成功?"}
    T -->|No| U["docker-build失敗"]
    T -->|Yes| V["全required status checks green"]
```

## 7. データ遷移図

CIジョブは実行のたびに使い捨てのGitHub-hosted runner上で完結し、`services`または`compose.integration.yml`のPostgreSQL/Redisもジョブ終了時に破棄される（永続データを持たない）。

## 8. 関数・処理詳細

### 8.1 `.github/workflows/ci.yml` :: ワークフロー定義（宣言的設定のため仕様として記載）

| 項目 | 内容 |
|------|------|
| シグネチャ / 定義 | `name: CI`。`on: { pull_request: {}, push: { branches: [develop, main] } }`。`concurrency: { group: "${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}", cancel-in-progress: true }` |
| 引数 / 入力 | GitHubイベントペイロード（`push`/`pull_request`）、GitHub Secrets |
| 戻り値 / 出力 | 各ジョブのconclusion（`success`/`failure`） |
| 送出例外 / 失敗条件 | いずれかのステップが非ゼロ終了した場合、そのジョブはfailureとなる |
| 処理内容 | baseブランチを限定せずPRを受け付け、`push`は`develop`/`main`だけを受け付ける。`detect`がcheckout済みツリーの実装ディレクトリ有無を判定し、該当する品質検証ジョブを起動する。`docker-build`は品質検証ジョブに`needs`で依存し、`batch-container-integration`はCompose上の実コンテナ検証を独立して行う。Docker buildでは`api`/`frontend`/`batch`の3イメージを作成する。同一PR（または同一push対象ブランチ）への新しい実行が始まると、同じconcurrency groupの実行中ジョブをキャンセルする |
| 副作用 | なし（ワークフロー定義自体はGitHub側の実行指示） |

### 8.2 `backend-lint` ジョブ

| 項目 | 内容 |
|------|------|
| シグネチャ / 定義 | `runs-on: ubuntu-latest`。`steps: checkout → setup-python(3.14, cache: pip) → pip install -r api/requirements.txt -r api/requirements-dev.txt → ruff check api/app → ruff format --check api/app → mypy api/app` |
| 引数 / 入力 | リポジトリソース（`api/`配下） |
| 戻り値 / 出力 | Lint/型チェック結果（exit code） |
| 送出例外 / 失敗条件 | `ruff check`のエラー、`ruff format --check`の差分検出、`mypy`の型エラーがそれぞれ非ゼロ終了 |
| 処理内容 | 1. チェックアウト 2. `actions/setup-python@v5`（`python-version: "3.14"`, `cache: pip`, `cache-dependency-path: api/requirements*.txt`） 3. 依存インストール 4. `ruff check` 5. `ruff format --check` 6. `mypy app`（`api/`をカレントディレクトリとする） |
| 副作用 | なし |

### 8.3 `backend-test` ジョブ

| 項目 | 内容 |
|------|------|
| シグネチャ / 定義 | `runs-on: ubuntu-latest`。`strategy: { matrix: { auth_mode: [session, jwt] } }`。`services: { postgres: {...}, redis: {...} }` |
| 引数 / 入力 | `services`コンテナのポート（`5432`/`6379`をrunnerの`localhost`にマップ）、3章の環境変数一式 |
| 戻り値 / 出力 | `pytest`終了コード、カバレッジレポート（`coverage.xml`） |
| 送出例外 / 失敗条件 | `services`のhealthcheckタイムアウト、`alembic upgrade head`失敗、`pytest`のテスト失敗、`--cov-fail-under=80`未達 |
| 処理内容 | 1. チェックアウト 2. `actions/setup-python@v5`（`cache: pip`） 3. 依存インストール 4. `services.postgres`（イメージ`postgres:17-alpine`、`env: POSTGRES_PASSWORD=postgres, POSTGRES_DB=cerberus_test`、`ports: ["5432:5432"]`、`options: --health-cmd pg_isready --health-interval 5s --health-timeout 5s --health-retries 5`）と`services.redis`（イメージ`redis:8-alpine`、`ports: ["6379:6379"]`、`options: --health-cmd "redis-cli ping" --health-interval 5s --health-timeout 5s --health-retries 5`）をGitHub Actionsが自動起動しhealthy待機 5. `env:`に`AUTH_MODE: ${{ matrix.auth_mode }}`を含む3章の変数を設定 6. `alembic upgrade head`（working-directory: `api`） 7. `pytest --cov=app --cov-report=xml --cov-fail-under=80`（`--cov-report=xml`は後続のカバレッジ確認用途） |
| 副作用 | `services`のPostgreSQL/Redisへの書き込み（ジョブ終了と同時に破棄） |

### 8.4 `frontend-lint` ジョブ

| 項目 | 内容 |
|------|------|
| シグネチャ / 定義 | `runs-on: ubuntu-latest`。`steps: checkout → setup-node(26, cache: npm) → npm ci → npm run lint (eslint) → npm run typecheck (tsc --noEmit)` |
| 引数 / 入力 | `frontend/`配下のソース、`package-lock.json` |
| 戻り値 / 出力 | Lint/型チェック結果 |
| 送出例外 / 失敗条件 | `eslint .`のエラー検出、`tsc --noEmit`の型エラー |
| 処理内容 | 1. チェックアウト 2. `actions/setup-node@v4`（`node-version: "26"`, `cache: npm`, `cache-dependency-path: frontend/package-lock.json`） 3. `npm ci`（working-directory: `frontend`） 4. `npx eslint .` 5. `npx tsc --noEmit` |
| 副作用 | なし |

### 8.5 `frontend-test` ジョブ

| 項目 | 内容 |
|------|------|
| シグネチャ / 定義 | `runs-on: ubuntu-latest`。`steps: checkout → setup-node(26, cache: npm) → npm ci → npm run test (vitest run --coverage)` |
| 引数 / 入力 | `frontend/`配下のテストコード |
| 戻り値 / 出力 | `vitest`終了コード、カバレッジレポート |
| 送出例外 / 失敗条件 | テスト失敗、カバレッジ70%未満（`vitest.config.ts`の`coverage.thresholds`で設定） |
| 処理内容 | 1. チェックアウト 2. `setup-node`（`cache: npm`） 3. `npm ci` 4. `vitest run --coverage`（閾値は`vitest.config.ts`側で定義し、ワークフローにはハードコードしない） |
| 副作用 | なし |

### 8.6 `docker-build` ジョブ

| 項目 | 内容 |
|------|------|
| シグネチャ / 定義 | `runs-on: ubuntu-latest`。`needs: [detect, backend-lint, backend-test, frontend-lint, frontend-test, batch-test]`。`if: needs.detect.outputs.docker == 'true'` |
| 引数 / 入力 | `api/Dockerfile`（[02_dockerfile_api.md](./02_dockerfile_api.md)）、`frontend/Dockerfile`（[03_dockerfile_frontend.md](./03_dockerfile_frontend.md)）、`batch/Dockerfile`（[08_dockerfile_batch.md](./08_dockerfile_batch.md)） |
| 戻り値 / 出力 | ビルド成功可否のみ（イメージはレジストリへpushしない） |
| 送出例外 / 失敗条件 | いずれかのDockerfileのビルドエラー |
| 処理内容 | 1. チェックアウト 2. `docker/setup-buildx-action@v3` 3. `docker/build-push-action@v6`を3回呼び出し（backendはcontext`.`・`api/Dockerfile`、frontendはcontext`frontend`・`frontend/Dockerfile`、batchはcontext`.`・`batch/Dockerfile`）、いずれも `push: false`、`cache-from: type=gha`、`cache-to: type=gha,mode=max` を指定 4. `VITE_API_BASE_URL`等のビルド時`ARG`はCIダミー値（`/api`）で埋める。`detect`およびbackend/frontend/batchの5検証jobが成功した後に実行する |
| 副作用 | runner上に一時イメージが生成されるが、レジストリへは送信されない |

### 8.7 `batch-container-integration` ジョブ

| 項目 | 内容 |
|------|------|
| シグネチャ / 定義 | `runs-on: ubuntu-latest`。`detect`の`batch=true`を条件に実行し、`RUN_BATCH_CONTAINER_INTEGRATION=1`を設定する |
| 引数 / 入力 | `docker-compose.yml`、`compose.integration.yml`、`.env.example`、`batch/tests/integration/` |
| 戻り値 / 出力 | `pytest`終了コード |
| 送出例外 / 失敗条件 | PostgreSQL/Redisの起動失敗、batchイメージのビルド失敗、batchコンテナ内の接続確認失敗 |
| 処理内容 | 1. Python 3.14を準備 2. `pytest`をインストール 3. PostgreSQL/RedisをComposeで起動 4. batchイメージをビルドしてテスト用probeを読み込み、SQLAlchemyの`SELECT 1`とredis-pyの`PING`をbatchコンテナ内で実行 5. Composeリソースを破棄 |
| 副作用 | CI専用の一時コンテナ・ネットワークを作成するが、ジョブ終了時に破棄する |

## 9. 関数・要素相関図

```mermaid
flowchart LR
    TRIG["push（main, develop）/<br/>pull_request（base制限なし）"] --> WF["ci.yml"]
    WF --> CONC["concurrency<br/>同一PR/ブランチの旧実行をcancel"]
    WF --> DET["detect<br/>実装有無を判定"]
    WF --> DOC["docs-check<br/>差分の空白検査"]
    WF --> WFL["workflow-lint<br/>ci.yml構成検査"]
    WF --> HT["hook-test<br/>hook回帰検査"]
    DET --> BL["backend-lint<br/>if: api"]
    WF --> BT["backend-test<br/>(matrix: AUTH_MODE)"]
    DET --> BT
    DET --> FL["frontend-lint<br/>if: frontend"]
    DET --> FT["frontend-test<br/>if: frontend"]
    DET --> BTEST["batch-test<br/>if: batch"]
    DET --> BI["batch-container-integration<br/>if: batch"]
    BI --> BPG["Compose: postgres"]
    BI --> BRD["Compose: redis"]
    BI --> BATCH["Compose: batch"]
    BATCH --> BPG
    BATCH --> BRD
    BT --> PGSVC["services: postgres:17-alpine"]
    BT --> RDSVC["services: redis:8-alpine"]
    BT --> MIG["alembic upgrade head"]
    MIG --> PGSVC
    DET --> DB["docker-build<br/>(if: docker)"]
    BL --> DB
    BT --> DB
    FL --> DB
    FT --> DB
    BTEST --> DB
    DB --> IMGBE["context . + api/Dockerfile ビルド<br/>db/を含む"]
    DB --> IMGFE["frontend/Dockerfile ビルド"]
    DB --> IMGBA["context . + batch/Dockerfile ビルド"]
    DB -.->|"push: false"| NOPUSH["GHCRへは送信しない"]
    WF --> BP["ブランチ保護<br/>required status checks"]
```

## 10. セキュリティ・非機能考慮

| 観点 | 方針 | 根拠 |
|------|------|------|
| Secretsの露出防止 | `JWT_SECRET_KEY`等はGitHub Secretsから`env:`へ注入し、ログへの出力・`echo`を行わない | [../../basic_design/06_infra_cicd.md](../../basic_design/06_infra_cicd.md) §7 |
| フォークPRからの実行 | `pull_request`トリガーではフォークPRに対してSecretsが渡されない挙動（GitHub標準仕様）を前提とし、フォークPR経由での不正なSecrets取得を防ぐ | GitHub Actions標準セキュリティモデル |
| イメージのpush禁止 | `docker-build`ジョブは`push: false`固定とし、CI実行だけでGHCRに意図しないイメージが公開されないようにする | [../../basic_design/06_infra_cicd.md](../../basic_design/06_infra_cicd.md) §5.2 |
| 依存キャッシュの汚染防止 | `cache-dependency-path`を`requirements*.txt`/`package-lock.json`に限定し、キャッシュキーがロックファイルのハッシュに連動するようにする（`actions/setup-python`/`actions/setup-node`標準機能） | GitHub Actions標準機能 |
| ブランチ保護 | `docs-check`/`workflow-lint`/`hook-test`/`backend-lint`/`backend-test`（両matrix）/`frontend-lint`/`frontend-test`/`batch-test`/`batch-container-integration`/`docker-build`をrequired status checksに設定し、いずれか未成功のPRは保護対象ブランチへマージ不可とする。baseがfeatureブランチのスタックPRにも同じCI結果を表示する | [../../basic_design/06_infra_cicd.md](../../basic_design/06_infra_cicd.md) §5.4 |
| CI用ダミーSecrets | `CI_JWT_SECRET_KEY`/`CI_INITIAL_ADMIN_PASSWORD`等は本番用の値と別管理し、CI専用のGitHub Secretsとして登録する | 一般的なCI/CD運用指針 |

## 11. テスト設計

| No | 区分 | ケース | 前提 | 期待結果 | テスト名案 |
|----|------|--------|------|----------|-----------|
| 1 | 結合 | `backend-lint`：Lint違反があるコードをpush | 意図的に`ruff`違反を含むブランチ | ジョブが失敗し、後続`docker-build`が実行されない | `test_ci_backend_lint_fails_on_violation`（CIログで確認） |
| 2 | 結合 | `backend-test`：session/jwt両matrixでpytestが通る | `services`起動済み、正常なテストコード | 2つのmatrix jobがともにsuccess | `test_ci_backend_test_matrix_both_modes` |
| 3 | 結合 | `backend-test`：カバレッジ80%未満 | 意図的にテスト数を減らしたブランチ | `--cov-fail-under=80`によりジョブ失敗 | `test_ci_backend_coverage_below_threshold_fails` |
| 4 | 結合 | `frontend-test`：カバレッジ70%未満 | 意図的にテストを削除したブランチ | `vitest`のカバレッジ閾値未達で失敗 | `test_ci_frontend_coverage_below_threshold_fails` |
| 5 | 結合 | `docker-build`：detectと5品質検証job成功後にのみ起動 | 5品質検証jobのいずれかが失敗する状態でpush | `docker-build`が`needs`未達成でskipされる | `test_ci_docker_build_requires_all_jobs_success` |
| 6 | 結合 | `docker-build`：GHCRへpushされない | 正常なpush | ビルドログに`push: false`相当（レジストリへの送信なし）が確認できる | `test_ci_docker_build_does_not_push` |
| 7 | 受入 | `batch-container-integration`：batch専用コンテナからDB/Redisへ接続 | Docker Engine、`.env.example`、`RUN_BATCH_CONTAINER_INTEGRATION=1` | batchコンテナ内のDB `SELECT 1`とRedis `PING`が成功する | `test_batch_container_connects_to_postgres_and_redis` |
| 8 | 結合 | 依存キャッシュが効くこと | 同一ロックファイルで2回目のCI実行 | 2回目の`pip install`/`npm ci`が短時間で完了（キャッシュhit） | `test_ci_cache_hit_reduces_install_time` |
| 9 | 設定 | baseがfeatureブランチのスタックPR | `pull_request`にbaseブランチ指定がないworkflow | `detect`を含むCI workflowが起動し、各ジョブの結果がPRへ報告される | `test_pull_request_trigger_has_no_base_branch_filter` |
| 10 | 設定 | 同一PRへ短時間に連続push | 同じPR番号で複数の`pull_request`実行が発生 | 後続実行が先行実行をキャンセルし、古い実行のrunner消費を抑制する | `test_concurrency_cancels_previous_run_for_same_pr` |
| 11 | 受入 | feature-base PRの実イベントとチェック表示 | PR #424（base=`feature/issue-412-stacked-pr-ci`） | `gh pr checks 424`でdetect、docs-check、workflow-lint、hook-test、backend-lint、backend-test（session/jwt）、frontend-lint、frontend-test、batch-test、batch-container-integration、docker-buildの全チェックが`pass` | [PR #424](https://github.com/oikawa-d/task_management/pull/424)、Actions run [34811431199](https://github.com/oikawa-d/task_management/actions/runs/34811431199) |
| 網羅できない範囲 | フォークPRでSecretsが渡されないことの実挙動確認 | - | GitHub側のプラットフォーム仕様であり自動テスト不可。ドキュメント記載の前提として扱う | - |

## 12. 不明点・要検討事項

| 区分 | 内容 | 影響 |
|------|------|------|
| 決定 | `frontend-test`のカバレッジ閾値70%は`frontend/vite.config.ts`の`test.coverage.thresholds`で強制する方式に統一した（CIステップ側には閾値をハードコードしない） | `frontend/vite.config.ts` |
| 要検討 | `backend-test`の`cov-fail-under`対象範囲は基本設計§5.4で「`omit`は`alembic/versions/*`のみ」と明記されている。本書もこれに従うが、`api/app/main.py`等の起動処理を含めた実測値が本当に80%を達成できるかは実装時の検証が必要 |`api/.coveragerc`または`pyproject.toml`の`[tool.coverage]`設定 |
| 決定 | lint/test専用パッケージ群は`api/requirements-dev.txt`として分割し、`backend-lint`/`backend-test`は`pip install -r requirements.txt -r requirements-dev.txt`でインストールする（`fastapi.testclient`が必要とする`httpx2`を含む） | `api/requirements-dev.txt` |
| 決定 | `pull_request`はbaseブランチを限定しない。GitHubの`pull_request`イベントはbaseが`develop`/`main`以外のスタックPRにもCIを起動し、`detect`はcheckout済みツリーのディレクトリ有無に基づいて従来どおりジョブを条件実行する | `.github/workflows/ci.yml`、§8.1 |
| 決定 | `push`はrunner消費を抑えるため`develop`/`main`に限定する。featureブランチの検証は`pull_request`で行い、featureブランチへのpushだけではCIを起動しない | `.github/workflows/ci.yml`、§8.1 |
| 決定 | concurrency groupはworkflow名とPR番号（push時はref）をキーにし、`cancel-in-progress: true`とする。同一PRへの連続pushでは最新実行を残し、先行実行をキャンセルする。workflow名を含めて他workflowとのgroup衝突を防ぐ | `.github/workflows/ci.yml`、§8.1 |
| 決定 | スタックPRのCIはGitHubが作るbaseとheadのマージ結果を検証する。base側が壊れている場合は子PRのCIも失敗し得るため、base側を先に修正するか、必要に応じてdevelopをbaseに変更してから再実行する。CIを意図的にスキップする運用は採用しない | GitHub `pull_request`運用 |
| 要検討 | featureブランチをbaseとするPRを実際に作成し、CI全ジョブの起動と`gh pr checks`への成功/失敗表示を確認する | GitHub上のPR作成が必要なためローカルでは未確認 | Issue #412の受入時に手動確認 |
