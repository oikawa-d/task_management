# 変更レビュー方針

このファイルは、Codex と Claude Code が共通して参照するレビュー手順です。

## 必須ルール

- 実装・設定・ドキュメントを変更した場合は、コミットまたはPR作成の前に必ずレビューを行う。
- レビューでは、変更差分、関連する要件・設計書、テスト結果、セキュリティ上の影響を確認する。
- 指摘事項がある場合は、修正してから再レビューする。未解決の指摘を残したまま完了扱いにしない。
- レビューを実施できない場合は、その理由と未確認の範囲をPR本文または作業報告に明記する。

## レビュー手順

1. `git diff` と `git diff --check` で意図しない変更・空白エラーを確認する。
2. 変更箇所と関連コードを読み、要件・基本設計・詳細設計との整合性を確認する。
3. 変更内容に応じたテスト、静的解析、フォーマットチェックを実行する。
4. 境界値、異常系、権限・認証、機密情報の露出、後方互換性を確認する。
5. 指摘事項と検証結果をPRテンプレートのレビュー欄に記録する。

レビュー結果は、問題がない場合も「レビュー済み」と明記してください。

## レビューラベルの遷移

PRとIssueのラベルは、レビューの進行状況を並行作業中の他エージェントへ伝える手段です。状態が変わるたびに更新します。レビュー待ち・修正後の再レビュー待ちは`review-request`、レビュー中・修正中は`in-progress`、レビュー結果に問題がない場合はPRへ`approve`を使用します。

| タイミング | 対象 | 付与するラベル | 外すラベル |
|------------|------|----------------|------------|
| issueへ着手（worktree作成・実装開始） | Issue | `in-progress` | - |
| PR作成・レビュー依頼 | Issue | `review-request` | `in-progress` |
| PR作成・レビュー依頼 | PR | `review-request` | `in-progress` |
| レビュー着手 | Issue | `in-progress` | `review-request` |
| レビュー着手 | PR | `in-progress` | `review-request` |
| レビューで修正要求後の修正着手 | Issue/PR | `in-progress`を維持 | なし |
| 修正push後・再レビュー依頼 | Issue | `review-request` | `in-progress` |
| 修正push後・再レビュー依頼 | PR | `review-request` | `in-progress` |
| 「受入可」コメント投稿後（レビュー主体のみ） | PR | `approve` | `review-request`／`in-progress` |

- `in-progress`は実装・レビュー・修正の作業中、`review-request`はレビュー待ち・修正後の再レビュー待ちに使用します。
- `approve`はレビュー結果に問題がないPRにのみ付与します。
- IssueとPRは同じ状態ラベル遷移を行い、`approve`だけはPRに付与します。
- レビューで指摘があった場合は、レビューコメントの冒頭に`要修正 (Changes requested)`と明記します。レビュー中・修正中はIssueとPRを`in-progress`にし、修正担当はこのラベルを前提に着手します。
- 指摘の修正をpushして再レビューを依頼するときは、IssueとPRを`review-request`へ戻します。

### ラベル操作コマンド

`gh pr edit --add-label` / `--remove-label` は Projects classic 廃止に伴うエラーで失敗するため使用しません（#386）。`gh api` を使います。PRとissueはGitHub上で同じ番号空間のため、いずれも `issues/<番号>/labels` を対象とします。

```bash
# Issueへの付与
gh api -X POST repos/<owner>/<repo>/issues/<番号>/labels -f "labels[]=review-request"

# Issueからの削除
gh api -X DELETE repos/<owner>/<repo>/issues/<番号>/labels/review-request

# PRのレビュー待ちラベル
gh api -X POST repos/<owner>/<repo>/issues/<PR番号>/labels -f "labels[]=review-request"

# PRのレビュー中・修正中ラベル
gh api -X POST repos/<owner>/<repo>/issues/<PR番号>/labels -f "labels[]=in-progress"
gh api -X DELETE repos/<owner>/<repo>/issues/<PR番号>/labels/review-request

# PRのレビュー完了ラベル
gh api -X POST repos/<owner>/<repo>/issues/<PR番号>/labels -f "labels[]=approve"

# 現在のラベル確認
gh pr view <番号> --json labels --jq '[.labels[].name]|join(", ")'
gh issue view <番号> --json labels --jq '[.labels[].name]|join(", ")'
```

## `approve`ラベルの付与

- `approve`ラベルは、PR作成もしくはコード修正を行ったエージェント以外がこの方針に沿ったレビューを行い、PR上に「受入可」のコメントを投稿したうえで付与します。
- PR作成もしくはコード修正を行ったエージェント本人は、自身のPRに`approve`ラベルを付与してはいけません。ここでの判定はGitHubアカウントではなく、PR作成またはコード修正を行ったエージェントかどうかで行います。
- `approve`ラベル付与済み、かつCIの全チェックが成功したPRは、PR作成もしくはコード修正を行ったエージェント以外が都度のユーザー承認なしにsquash mergeしてよく、Issue closeも同様です。`approve`はPRにのみ付与します。
- レビュー担当エージェントとPR作成もしくはコード修正を行ったエージェントが同一GitHubアカウントになる場合、GitHubの承認レビューは利用できないため、`gh pr comment`で「受入可」を記録し、`gh api -X POST repos/<owner>/<repo>/issues/<PR番号>/labels -f "labels[]=approve"`でラベルを付与します。hookはPR作成・コード修正を行ったエージェントの識別までは行わず、`approve`ラベルの有無を検証します。
- `gh pr merge`は`.agents/hooks/block-github-destructive-actions.sh`（Claude Codeは`.claude/hooks/`、Codexは`.codex/hooks/`のラッパー経由）により、対象PRに`approve`ラベルが無い場合はブロックされます（fail-close）。
- `gh issue close`は同hookにより、**そのissueを閉じるPR**（本文の`Closes #<Issue番号>`でリンクされたPR）に`approve`ラベルが無い場合はブロックされます（fail-close）。判定はPR側の`approve`で行います。
- 上記のとおりissue closeの可否はPRとのリンクを前提とするため、PR本文の「関連Issue」欄には必ず`Closes #<Issue番号>`を記載してください。記載があればマージ時にissueは自動closeされ、手動closeは不要です。
