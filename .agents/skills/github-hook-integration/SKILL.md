---
name: github-hook-integration
description: GitHub破壊操作hookを複数の実装から共通化・統合するときに使う
---

# GitHub破壊操作hook統合時の注意点

## 事象

リンクPRのレビュー状態をGraphQLで確認するhookでは、1ページ目だけでなく、ページングされた全結果を検査する必要がある。

## 原因

統合時に実装差分だけを確認し、統合元が持つページング回帰テストを共通実装へ反映する確認が不足すると、テストfixtureと実装の契約が分離する。

## 正しい対処

- 統合前に各実装のGraphQLクエリ、`pageInfo`検証、cursor更新、fail-close条件を比較する。
- 共通実装へ統合した後、統合元ごとの回帰テストを同じ共通hookに対して実行する。
- `hasNextPage=true`、次ページのapprove PR、cursor欠落、不正なレスポンス形状をテストする。
- 統合後の共通実装と各クライアント用wrapperの参照先が一致することを確認する。
