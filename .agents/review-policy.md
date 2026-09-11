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

PRとissueのラベルは、レビューの進行状況を並行作業中の他エージェントへ伝える手段です。状態が変わるたびに更新し、**PR側とissue側の両方を同じ状態に揃えます**。

| タイミング | 付与するラベル | 外すラベル |
|------------|----------------|------------|
| issueへ着手（worktree作成・実装開始） | `in-progress` | - |
| PR作成・レビュー依頼 | `review-requested` | `in-progress` |
| Changes Requestedを受領 | `changes-requested` | `review-requested` |
| 指摘の修正をpushし再レビューを依頼 | `review-requested` | `changes-requested` |
| 「受入可」コメント投稿後（レビュー主体のみ） | `reviewed` | `review-requested` |

- `in-progress` は重複着手防止用です。複数セッション・複数エージェントが並行するため、着手したら必ず付与します。
- 指摘の修正に着手してからpushするまでの間は `changes-requested` を維持します。この期間に `review-requested` を付けたままにすると、他エージェントが再レビュー可能と誤認します。
- 指摘の一部を未対応で残したまま再レビューを依頼する場合も `review-requested` へ戻し、未対応の指摘をPRコメントに明記します。

### ラベル操作コマンド

`gh pr edit --add-label` / `--remove-label` は Projects classic 廃止に伴うエラーで失敗するため使用しません（#386）。`gh api` を使います。PRとissueはGitHub上で同じ番号空間のため、いずれも `issues/<番号>/labels` を対象とします。

```bash
# 付与（複数指定可）
gh api -X POST repos/<owner>/<repo>/issues/<番号>/labels -f "labels[]=review-requested"

# 削除
gh api -X DELETE repos/<owner>/<repo>/issues/<番号>/labels/changes-requested

# 現在のラベル確認
gh pr view <番号> --json labels --jq '[.labels[].name]|join(", ")'
gh issue view <番号> --json labels --jq '[.labels[].name]|join(", ")'
```

## `reviewed`ラベルの付与

- `reviewed`ラベルは、PRを作成した本人以外がこの方針に沿ったレビューを行い、PR上に「受入可」のコメントを投稿したうえで付与します。
- PRを作成したエージェントは、自身が作成したPRに`reviewed`ラベルを付与してはいけません。
- `reviewed`ラベル付与済み、かつCIの全チェックが成功したPRは、PR作成者以外が都度のユーザー承認なしにsquash mergeしてよく、Issue closeも同様です。
- `gh pr merge`・`gh issue close`は`.claude/hooks/block-github-destructive-actions.sh`により、対象に`reviewed`ラベルが無い場合はブロックされます（fail-close）。
