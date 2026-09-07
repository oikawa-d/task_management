# Repository Guidelines

## プロジェクト構成

このリポジトリは現在、アプリケーション本体ではなく設計ドキュメントを管理しています。

- `requirements/`：要件定義書
- `basic_design/`：システム概要、DB、Redis、認証、API、フロントエンド、インフラ、図
- `detailed_design/`：`api/`、`auth/`、`database/`、`infra/`、`screen/` 配下の詳細設計
- `README.md`：リポジトリ概要。設計書に記載された `api/`、`frontend/`、`tests/` は実装予定で、現在は未作成

要件・基本設計・詳細設計の間で、用語、エンドポイント、エラーコード、環境変数名、Mermaid図を常に一致させてください。

## ビルド・テスト・開発コマンド

現在は実行可能なビルド・テスト設定がないため、ドキュメント変更時は次を実行します。

```bash
git diff --check
```

実装後のローカル環境ではDocker Composeを使用します。

```bash
docker compose up -d
docker compose -f docker-compose.yml -f compose.dev.yml up
```

CIでは、`ruff check`、`ruff format --check`（タブインデント強制）、`mypy src/app`、`pytest --cov`、フロントエンドのESLint・TypeScriptチェック・Vitestカバレッジ、Dockerイメージビルドを実施します。実装ディレクトリ作成後は該当するチェックを実行してください。CI定義は`.github/workflows/ci.yml`、Ruff設定は`pyproject.toml`の`[tool.ruff.format]`（`indent-style = "tab"`）を参照してください。

## コーディング規約・命名

設計書はMarkdown見出しと簡潔な日本語で記述し、文書間のリンクは相対リンク、図はMermaidを使用します。Pythonは**タブ**インデント、関数・変数は`snake_case`、クラスは`PascalCase`とします。TypeScript/Reactのコンポーネントは`PascalCase`、フックは`useXxx`、定数は`UPPER_SNAKE_CASE`とします。PythonはRuff（`ruff format`でタブインデントを強制）、フロントエンドはESLintで検査します。

## テスト方針

バックエンドはpytest、フロントエンドはVitestを使用する予定です。テスト名は`test_login_endpoint_email_not_verified`や`KanbanBoard refetches board on 409 TASK_CONFLICT`のように、対象と期待動作が分かる名前にします。エンドポイントの動作やエラー処理を変更した場合は、設計書のテスト表も更新してください。

## コミット・プルリクエスト

既存の`<type>: <description>`形式に従います。例：`docs: 要件・基本・詳細設計の整合性を修正`、`fix: ...`、`ci: ...`。コミットは目的ごとに分けてください。プルリクエストには変更対象の文書、関連Issue、他文書への影響を記載し、図やUIを変更した場合は描画結果のスクリーンショットを添付してください。

## セキュリティ・設定

`.env`、認証情報、OAuthシークレット、JWT鍵、SMTPパスワードはコミットしないでください。`.env.example`とGitHub Secretsを使用します。認証、CSRF、OAuthリダイレクト、Cookie、エラーコードの変更は、要件・基本設計・詳細設計をまたぐ変更として扱い、関連文書をすべて更新してください。
