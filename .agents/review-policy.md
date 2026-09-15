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

PRとissueのラベルは、レビューの進行状況を並行作業中の他エージェントへ伝える手段です。状態が変わるたびに更新します。IssueとPRは役割が異なるため同じラベルに揃えず、Issueは`in-progress`／`review`、PRはレビュー中に`in-progress`、レビュー完了後に`approve`を使用します。

| タイミング | 対象 | 付与するラベル | 外すラベル |
|------------|------|----------------|------------|
| issueへ着手（worktree作成・実装開始） | Issue | `in-progress` | - |
| PR作成・レビュー依頼 | Issue | `review` | `in-progress` |
| PR作成・レビュー依頼 | PR | `in-progress` | - |
| レビュー中・変更依頼あり・再レビュー依頼 | Issue | `review` | - |
| レビュー中・変更依頼あり・再レビュー依頼 | PR | `in-progress` | - |
| 「受入可」コメント投稿後（レビュー主体のみ） | PR | `approve` | `in-progress` |

- Issueの`in-progress`は重複着手防止用、Issueの`review`はレビュー中であることの表示に使用します。
- PRの`in-progress`はレビュー中・変更依頼後の修正中を含むレビュー工程全体を表します。レビュー待ちと変更依頼後を別ラベルへ分類しません。
- 指摘の修正に着手するときはIssueの`review`を`in-progress`へ変更し、修正をpushして再レビューを依頼するときにIssueを`review`へ戻します。PRは工程中`in-progress`を維持します。

### ラベル操作コマンド

`gh pr edit --add-label` / `--remove-label` は Projects classic 廃止に伴うエラーで失敗するため使用しません（#386）。`gh api` を使います。PRとissueはGitHub上で同じ番号空間のため、いずれも `issues/<番号>/labels` を対象とします。

```bash
# Issueへの付与
gh api -X POST repos/<owner>/<repo>/issues/<番号>/labels -f "labels[]=review"

# Issueからの削除
gh api -X DELETE repos/<owner>/<repo>/issues/<番号>/labels/review

# PRのレビュー中ラベル
gh api -X POST repos/<owner>/<repo>/issues/<PR番号>/labels -f "labels[]=in-progress"

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
