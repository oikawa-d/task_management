# Repository Guidelines

## プロジェクト構成

このリポジトリは設計ドキュメントと実装コードの両方を管理しています。

Codex・Claude Code共通のレビュー手順は [.agents/review-policy.md](./.agents/review-policy.md) に定義しています。変更をコミットまたはPRにする前に、必ず参照してレビューを完了してください。

依存追加を伴う並行PRは、[依存管理運用ルール](./.agents/dependency-management.md) に従って計画・実施してください。

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

## 仕様の優先順位

仕様の記載が複数箇所で食い違った場合、次の順で優先します。

1. `docs/requirements/`（要件定義書）
2. `docs/basic_design/`（基本設計）
3. `docs/detailed_design/`（詳細設計）
4. GitHub issueの本文

**issue本文と設計書が食い違う場合は、設計書が正です。** issue本文の指示に従って実装しないでください。

とりわけ**実装ファイルの配置**は、詳細設計書の「実装ファイル」欄を唯一の正とします。issue本文にファイルパスの記載があっても、設計書と異なる場合は設計書に従い、issue本文の是正を別途行ってください。

```bash
# 実装着手前に、対象機能の設計書が指定する実装ファイルを確認する
grep -rn "実装ファイル" docs/detailed_design/<領域>/*.md
```

食い違いを見つけた場合は、実装を進める前にissueを起票して記録してください。既存の実装が設計書と一致している場合は、その実装を正として設計書ではなくissue本文を更新します。

## ビルド・テスト・開発コマンド

ローカル環境ではDocker Composeを使用します。

```bash
docker compose up -d
docker compose -f docker-compose.yml -f compose.dev.yml --profile dev up
```

CIでは、`api/`・`batch/`それぞれに対して`ruff check`、`ruff format --check`（タブインデント強制）、`mypy app`、`pytest --cov`を実行し、フロントエンドのESLint・TypeScriptチェック・Vitestカバレッジ、`api/frontend/batch`各Dockerfileのイメージビルドを実施します。CI定義は`.github/workflows/ci.yml`、Ruff設定は`pyproject.toml`の`[tool.ruff.format]`（`indent-style = "tab"`）を参照してください。

## コーディング規約・命名

設計書はMarkdown見出しと簡潔な日本語で記述し、文書間のリンクは相対リンク、図はMermaidを使用します。Pythonは**タブ**インデント、関数・変数は`snake_case`、クラスは`PascalCase`とします。TypeScript/Reactのコンポーネントは`PascalCase`、フックは`useXxx`、定数は`UPPER_SNAKE_CASE`とします。PythonはRuff（`ruff format`でタブインデントを強制）、フロントエンドはESLintで検査します。

## テスト方針

バックエンドはpytest、フロントエンドはVitestを使用する予定です。テスト名は`test_login_endpoint_email_not_verified`や`KanbanBoard refetches board on 409 TASK_CONFLICT`のように、対象と期待動作が分かる名前にします。エンドポイントの動作やエラー処理を変更した場合は、設計書のテスト表も更新してください。

APIエンドポイントの結合テストは`api/tests/integration/`に配置します。service層の実DB結合テストは`api/tests/service/test_z_*_integration.py`に配置し、router/serviceの単体テストはそれぞれの層別ディレクトリに配置します。`test_z_`接頭辞は、DB状態や実行順に依存するservice結合テストの実行順を制御する必要がある場合に限って使用します。既存テストは現行の責務を維持し、一括移動・分割は行わず、今後の修正・追加時にこの方針へ段階的に合わせます。

## コミット・プルリクエスト

既存の`<type>: <description>`形式に従います。例：`docs: 要件・基本・詳細設計の整合性を修正`、`fix: ...`、`ci: ...`。コミットは目的ごとに分けてください。プルリクエストには変更対象の文書、関連Issue、他文書への影響を記載し、図やUIを変更した場合は描画結果のスクリーンショットを添付してください。

変更をコミットまたはPRにする前に、[共通レビュー方針](./.agents/review-policy.md)に従ったレビューを必ず実施し、結果を作業報告またはPR本文に記載してください。

PR作成後は作成した時点で作業完了とせず、PR作成もしくはコード修正を行ったエージェント以外が[共通レビュー方針](./.agents/review-policy.md)に沿ったレビューを行い「受入可」のコメントを投稿したうえで`approve`ラベルを付与してください。`approve`ラベルが付与済みかつCIの全チェックが成功したPRは、PR作成もしくはコード修正を行ったエージェント以外が都度のユーザー承認を得ることなくsquash mergeを実施してよく、Issue closeも同様です。PR作成もしくはコード修正を行ったエージェント本人は、自身が作成または修正したPRへの`approve`ラベル付与・merge・Issue closeを行ってはいけません。ここでの判定はGitHubアカウントではなく、PR作成またはコード修正を行ったエージェントかどうかで行います。同一GitHubアカウントを使用する別エージェントがレビューする場合、GitHubの承認レビューではなく`gh pr comment`で「受入可」を記録し、REST APIでラベルを付与してください。`gh pr merge`・`gh issue close`は`.agents/hooks/block-github-destructive-actions.sh`（Claude Codeは`.claude/hooks/`、Codexは`.codex/hooks/`のラッパー経由で呼び出します）によりブロックされます（判定条件は[共通レビュー方針](./.agents/review-policy.md)を参照）。hookを変更した場合は`bash .agents/hooks/block-github-destructive-actions.test.sh`と`bash .agents/hooks/hook-config.test.sh`を実行してください。マージ後はリモート・ローカルの作業ブランチを削除します。CIが失敗した場合はmergeせず、原因を修正してから再度確認してください。

レビューで指摘がある場合は、`gh pr comment`の冒頭に「要修正 (Changes requested)」と明記して変更要求を記録してください。指摘後のレビュー中・修正中はIssueとPRの`in-progress`を維持し、修正push後に再レビューを依頼するときはIssueとPRを`review-request`へ戻します。詳細は[issue-label-workflow](./skills/issue-label-workflow/SKILL.md)に従ってください。

## セキュリティ・設定

GitHub CLIの認証確認は、インストール済みバージョンとの互換性を保つため、必ず`gh auth status --hostname github.com`をそのまま実行してください。`--active`オプションは使用しないでください。認証確認に失敗した場合でも、PR参照の取得や差分確認などGitのみの読み取り操作は継続できますが、`gh`によるPR・Issue操作、API操作、pushは実行しないでください。

`.env`、認証情報、OAuthシークレット、JWT鍵、SMTPパスワードはコミットしないでください。`.env.example`とGitHub Secretsを使用します。認証、CSRF、OAuthリダイレクト、Cookie、エラーコードの変更は、要件・基本設計・詳細設計をまたぐ変更として扱い、関連文書をすべて更新してください。
