# Repository Guidelines

## プロジェクト構成

このリポジトリは設計ドキュメントと実装コードの両方を管理しています。

- `docs/requirements/`：要件定義書
- `docs/basic_design/`：システム概要、DB、Redis、認証、API、フロントエンド、インフラ、図
- `docs/detailed_design/`：`api/`、`auth/`、`database/`、`infra/`、`screen/` 配下の詳細設計
- `api/`：バックエンド（FastAPI）。`api/app/`が本体、`api/tests/`がpytest
- `batch/`：定期実行バッチ（常駐スケジューラ）。`batch/app/`が本体、`batch/tests/`がpytest
- `frontend/`：フロントエンド（Vite + React + TypeScript）
- `db/`：DBマイグレーション以外の関数・ストアドプロシージャ
- `README.md`：リポジトリ概要

要件・基本設計・詳細設計の間で、用語、エンドポイント、エラーコード、環境変数名、Mermaid図を常に一致させてください。ドキュメントのみの変更時は次を実行します。

```bash
git diff --check
```

## ビルド・テスト・開発コマンド

ローカル環境ではDocker Composeを使用します。

```bash
docker compose up -d
docker compose -f docker-compose.yml -f compose.dev.yml up
```

CIでは、`api/`・`batch/`それぞれに対して`ruff check`、`ruff format --check`（タブインデント強制）、`mypy app`、`pytest --cov`を実行し、フロントエンドのESLint・TypeScriptチェック・Vitestカバレッジ、`api/frontend/batch`各Dockerfileのイメージビルドを実施します。CI定義は`.github/workflows/ci.yml`、Ruff設定は`pyproject.toml`の`[tool.ruff.format]`（`indent-style = "tab"`）を参照してください。

## コーディング規約・命名

設計書はMarkdown見出しと簡潔な日本語で記述し、文書間のリンクは相対リンク、図はMermaidを使用します。Pythonは**タブ**インデント、関数・変数は`snake_case`、クラスは`PascalCase`とします。TypeScript/Reactのコンポーネントは`PascalCase`、フックは`useXxx`、定数は`UPPER_SNAKE_CASE`とします。PythonはRuff（`ruff format`でタブインデントを強制）、フロントエンドはESLintで検査します。

## テスト方針

バックエンドはpytest、フロントエンドはVitestを使用する予定です。テスト名は`test_login_endpoint_email_not_verified`や`KanbanBoard refetches board on 409 TASK_CONFLICT`のように、対象と期待動作が分かる名前にします。エンドポイントの動作やエラー処理を変更した場合は、設計書のテスト表も更新してください。

## コミット・プルリクエスト

既存の`<type>: <description>`形式に従います。例：`docs: 要件・基本・詳細設計の整合性を修正`、`fix: ...`、`ci: ...`。コミットは目的ごとに分けてください。プルリクエストには変更対象の文書、関連Issue、他文書への影響を記載し、図やUIを変更した場合は描画結果のスクリーンショットを添付してください。

PR作成後は作成した時点で作業完了とせず、CIの全チェックが成功次第、ユーザーへ都度確認せずsquash mergeまで実施してください。マージ後はリモート・ローカルの作業ブランチを削除し、関連issueをcloseしてください。CIが失敗した場合はmergeせず、原因を修正してから再度確認してください。

## セキュリティ・設定

`.env`、認証情報、OAuthシークレット、JWT鍵、SMTPパスワードはコミットしないでください。`.env.example`とGitHub Secretsを使用します。認証、CSRF、OAuthリダイレクト、Cookie、エラーコードの変更は、要件・基本設計・詳細設計をまたぐ変更として扱い、関連文書をすべて更新してください。
