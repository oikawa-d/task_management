# infra/08 batch Dockerfile詳細設計

## 0. 関連ドキュメント

- 基本設計：[../../basic_design/06_infra_cicd.md](../../basic_design/06_infra_cicd.md) §2.1・§3
- 詳細設計：[01_docker_compose.md](./01_docker_compose.md)、[04_env_config.md](./04_env_config.md)、[../batch/00_overview.md](../batch/00_overview.md)

## 1. 概要

| 項目 | 内容 |
|------|------|
| 対象 | `batch/Dockerfile`、`batch/requirements.txt` |
| 目的 | 期限通知スケジューラをAPIプロセスから分離した常駐コンテナとして実行する |
| ベース | builder/runtimeとも `python:3.14-slim` |
| 起動 | `python -m app.main` |
| ポート | 公開しない |
| 実行ユーザー | 非root `appuser` |
| マイグレーション | 実行しない。DBスキーマはbackendの起動処理が準備する |

## 2. 想定Dockerfile

```dockerfile
FROM python:3.14-slim AS builder
WORKDIR /build
COPY batch/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.14-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
COPY --from=builder /install /usr/local
COPY batch/app ./app
USER appuser
CMD ["python", "-m", "app.main"]
```

実装時は依存バージョンを`batch/requirements.txt`で固定し、APIのrequirementsを暗黙に共有しない。`DATABASE_URL`、`REDIS_URL`、`APP_TIMEZONE`等はComposeの環境変数から注入する。

## 3. ビルド・起動設定

| 項目 | 設定 |
|------|------|
| build context | リポジトリルート |
| dockerfile | `batch/Dockerfile` |
| restart | `unless-stopped` |
| depends_on | `postgres` / `redis` の`service_healthy` |
| healthcheck | `pgrep -f 'python -m app.main'`等でプロセス生存を確認 |
| logging | backendと同じ標準出力の構造化ログ。秘密情報を含めない |
| network | `cerberus_net`のみ |

## 4. セキュリティ・非機能

- rootで実行せず、書き込み可能領域をアプリの一時領域に限定する。
- `JWT_SECRET_KEY`、OAuth secret、SMTP passwordはbatchへ渡さない。
- batchはHTTPポートを持たず、APIを経由せずにDB/Redisへ内部接続する。
- `BATCH_ENABLED=false`でもコンテナは常駐できるが、定期ジョブは登録しない。

## 5. テスト設計

| ケース | 期待結果 | テスト名案 |
|--------|----------|------------|
| batchイメージのビルド | Docker buildが成功する | `test_batch_image_builds` |
| 非root確認 | `id -u`が0でない | `test_batch_container_runs_non_root` |
| 起動 | `python -m app.main`が設定を読み常駐する | `test_batch_entrypoint_starts_scheduler` |
| DB未準備 | depends_on待機後も再起動で復旧できる | `test_batch_restarts_after_database_readiness` |
