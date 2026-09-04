# infra/05 CIワークフロー（`.github/workflows/ci.yml`）

## 0. 関連ドキュメント

- 基本設計：[../../basic_design/06_infra_cicd.md](../../basic_design/06_infra_cicd.md)（§5 CI設計、§7 学習ポイント）、[../../basic_design/00_overview.md](../../basic_design/00_overview.md)
- 詳細設計：[01_docker_compose.md](./01_docker_compose.md)、[04_env_config.md](./04_env_config.md)、[06_cd_workflow.md](./06_cd_workflow.md)、[../database/09_migration.md](../database/09_migration.md)（マイグレーション適用手順）、[../auth/00_strategy_base.md](../auth/00_strategy_base.md)（`AUTH_MODE`切替）

## 1. 概要

| 項目 | 内容 |
|------|------|
| 対象 | `.github/workflows/ci.yml` |
| 責務 | push/pull_request をトリガーに、backend/frontendのLint・型チェック・テスト・カバレッジ検証、およびbackend/frontend/batch Dockerイメージのビルド確認（push なし）を行う |
| 適用条件 | `push: branches: [main, develop]`、`pull_request: branches: [main, develop]` |
| 依存先 | GitHub Actions `services`（PostgreSQL・Redis）、GHA組み込みキャッシュ（`actions/setup-python`・`actions/setup-node`）、`docker/build-push-action` |
| 実装ファイル | `.github/workflows/ci.yml` |

## 2. 構成要素

| 要素 | 種別 | 責務 | 備考 |
|------|------|------|------|
| `backend-lint` | ジョブ | `ruff check` / `ruff format --check` / `mypy app` | Python 3.14 |
| `backend-test` | ジョブ | `services`でPostgreSQL/Redis起動 → `alembic upgrade head` → `pytest --cov` | `AUTH_MODE`をmatrix化（`session`/`jwt`） |
| `frontend-lint` | ジョブ | `eslint .` / `tsc --noEmit` | Node v26 |
| `frontend-test` | ジョブ | `vitest run --coverage` | |
| `docker-build` | ジョブ | backend/frontend/batchイメージのビルド確認（`push: false`） | 4ジョブすべての成功後に実行 |
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
| 入力 | `push`/`pull_request`イベント（`main`/`develop`）、リポジトリのソース一式、GitHub Secrets（`CI_JWT_SECRET_KEY`等） |
| 出力 | 各ジョブの成功/失敗ステータス（required status checks）、カバレッジレポート（`coverage.xml`等、アーティファクト保存は任意） |
| 副作用 | `services`で起動した一時PostgreSQL/Redisへの書き込み（ジョブ終了時に破棄）。永続化なし。イメージはビルドのみでpushしない |

## 5. シーケンス図

### 5.1 CI全体フロー（正常系）

```mermaid
sequenceDiagram
    autonumber
    actor DEV as 開発者
    participant GH as GitHub
    participant BL as backend-lint
    participant BT as backend-test
    participant FL as frontend-lint
    participant FT as frontend-test
    participant DB as docker-build

    DEV->>GH: push / pull_request（main, develop）
    GH->>BL: ジョブ起動
    GH->>BT: ジョブ起動（matrix: session, jwt）
    GH->>FL: ジョブ起動
    GH->>FT: ジョブ起動
    par 4ジョブ並行実行
        BL->>BL: ruff check / format --check / mypy app
        BT->>BT: services起動 → alembic upgrade head → pytest --cov
        FL->>FL: eslint . / tsc --noEmit
        FT->>FT: vitest run --coverage
    end
    BL-->>GH: success
    BT-->>GH: success（2 matrix jobs）
    FL-->>GH: success
    FT-->>GH: success
    GH->>DB: ジョブ起動（needs: 上記4ジョブ）
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
    A["push / pull_request<br/>(main, develop)"] --> B["4ジョブを並行起動<br/>backend-lint / backend-test<br/>frontend-lint / frontend-test"]
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
    C -->|Yes| Q{"backend-lint/test<br/>frontend-lint/test<br/>すべてsuccess?"}
    K --> Q
    P --> Q
    Q -->|Yes| R["docker-build起動<br/>（push: false）"]
    Q -->|No| S["docker-buildはneeds未達成でskip扱い"]
    R --> T{"backend/frontend/batchとも<br/>ビルド成功?"}
    T -->|No| U["docker-build失敗"]
    T -->|Yes| V["全required status checks green"]
```

## 7. データ遷移図

なし。CIジョブは実行のたびに使い捨てのGitHub-hosted runner上で完結し、`services`のPostgreSQL/Redisもジョブ終了時に破棄される（永続データを持たない）。

## 8. 関数・処理詳細

### 8.1 `.github/workflows/ci.yml` :: ワークフロー定義（宣言的設定のため仕様として記載）

| 項目 | 内容 |
|------|------|
| シグネチャ / 定義 | `name: ci`。`on: { push: { branches: [main, develop] }, pull_request: { branches: [main, develop] } }` |
| 引数 / 入力 | GitHubイベントペイロード（`push`/`pull_request`）、GitHub Secrets |
| 戻り値 / 出力 | 各ジョブのconclusion（`success`/`failure`） |
| 送出例外 / 失敗条件 | いずれかのステップが非ゼロ終了した場合、そのジョブはfailureとなる |
| 処理内容 | 5ジョブ（`backend-lint`/`backend-test`/`frontend-lint`/`frontend-test`/`docker-build`）を定義し、`docker-build`のみ他4ジョブに`needs`で依存する。Docker buildでは`api`/`frontend`/`batch`の3イメージを作成する |
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
| シグネチャ / 定義 | `runs-on: ubuntu-latest`。`needs: [backend-lint, backend-test, frontend-lint, frontend-test]` |
| 引数 / 入力 | `api/Dockerfile`（[02_dockerfile_api.md](./02_dockerfile_api.md)）、`frontend/Dockerfile`（[03_dockerfile_frontend.md](./03_dockerfile_frontend.md)）、`batch/Dockerfile`（[08_dockerfile_batch.md](./08_dockerfile_batch.md)） |
| 戻り値 / 出力 | ビルド成功可否のみ（イメージはレジストリへpushしない） |
| 送出例外 / 失敗条件 | いずれかのDockerfileのビルドエラー |
| 処理内容 | 1. チェックアウト 2. `docker/setup-buildx-action@v3` 3. `docker/build-push-action@v6`を3回呼び出し（backend用・frontend用・batch用）、いずれも `push: false`、`cache-from: type=gha`、`cache-to: type=gha,mode=max` を指定 4. `VITE_API_BASE_URL`等のビルド時`ARG`はCIダミー値（`/api`）で埋める |
| 副作用 | runner上に一時イメージが生成されるが、レジストリへは送信されない |

## 9. 関数・要素相関図

```mermaid
flowchart LR
    TRIG["push / pull_request<br/>(main, develop)"] --> WF["ci.yml"]
    WF --> BL["backend-lint"]
    WF --> BT["backend-test<br/>(matrix: AUTH_MODE)"]
    WF --> FL["frontend-lint"]
    WF --> FT["frontend-test"]
    BT --> PGSVC["services: postgres:17-alpine"]
    BT --> RDSVC["services: redis:8-alpine"]
    BT --> MIG["alembic upgrade head"]
    MIG --> PGSVC
    BL --> DB["docker-build<br/>(needs: 4ジョブ)"]
    BT --> DB
    FL --> DB
    FT --> DB
    DB --> IMGBE["api/Dockerfile ビルド"]
    DB --> IMGFE["frontend/Dockerfile ビルド"]
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
| ブランチ保護 | `backend-lint`/`backend-test`（両matrix）/`frontend-lint`/`frontend-test`/`docker-build`をrequired status checksに設定し、いずれか未成功のPRはmain/developへマージ不可とする | [../../basic_design/06_infra_cicd.md](../../basic_design/06_infra_cicd.md) §5.4 |
| CI用ダミーSecrets | `CI_JWT_SECRET_KEY`/`CI_INITIAL_ADMIN_PASSWORD`等は本番用の値と別管理し、CI専用のGitHub Secretsとして登録する | 一般的なCI/CD運用指針 |

## 11. テスト設計

| No | 区分 | ケース | 前提 | 期待結果 | テスト名案 |
|----|------|--------|------|----------|-----------|
| 1 | 結合 | `backend-lint`：Lint違反があるコードをpush | 意図的に`ruff`違反を含むブランチ | ジョブが失敗し、後続`docker-build`が実行されない | `test_ci_backend_lint_fails_on_violation`（CIログで確認） |
| 2 | 結合 | `backend-test`：session/jwt両matrixでpytestが通る | `services`起動済み、正常なテストコード | 2つのmatrix jobがともにsuccess | `test_ci_backend_test_matrix_both_modes` |
| 3 | 結合 | `backend-test`：カバレッジ80%未満 | 意図的にテスト数を減らしたブランチ | `--cov-fail-under=80`によりジョブ失敗 | `test_ci_backend_coverage_below_threshold_fails` |
| 4 | 結合 | `frontend-test`：カバレッジ70%未満 | 意図的にテストを削除したブランチ | `vitest`のカバレッジ閾値未達で失敗 | `test_ci_frontend_coverage_below_threshold_fails` |
| 5 | 結合 | `docker-build`：4ジョブ成功後にのみ起動 | 4ジョブのいずれかが失敗する状態でpush | `docker-build`が`needs`未達成でskipされる | `test_ci_docker_build_requires_all_jobs_success` |
| 6 | 結合 | `docker-build`：GHCRへpushされない | 正常なpush | ビルドログに`push: false`相当（レジストリへの送信なし）が確認できる | `test_ci_docker_build_does_not_push` |
| 7 | 結合 | 依存キャッシュが効くこと | 同一ロックファイルで2回目のCI実行 | 2回目の`pip install`/`npm ci`が短時間で完了（キャッシュhit） | `test_ci_cache_hit_reduces_install_time` |
| 網羅できない範囲 | フォークPRでSecretsが渡されないことの実挙動確認 | - | GitHub側のプラットフォーム仕様であり自動テスト不可。ドキュメント記載の前提として扱う | - |

## 12. 不明点・要検討事項

| 区分 | 内容 | 影響 |
|------|------|------|
| 要検討 | `frontend-test`のカバレッジ閾値70%を`vitest.config.ts`側の`coverage.thresholds`で強制するか、CIステップ内で`--coverage.lines=70`のようにコマンド引数化するかは基本設計に明記がなく、実装時にどちらか一方へ統一する必要がある | `frontend/vitest.config.ts`、CIステップの引数 |
| 要検討 | `backend-test`の`cov-fail-under`対象範囲は基本設計§5.4で「`omit`は`alembic/versions/*`のみ」と明記されている。本書もこれに従うが、`api/app/main.py`等の起動処理を含めた実測値が本当に80%を達成できるかは実装時の検証が必要 |`api/.coveragerc`または`pyproject.toml`の`[tool.coverage]`設定 |
| 不明 | `requirements-dev.txt`（lint/test専用パッケージ群）というファイル名・分割方針は基本設計に明記がなく、本書が実装レベルの詳細として補った提案である | `api/requirements-dev.txt`の実在否 |
