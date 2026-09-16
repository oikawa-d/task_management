---
name: pr-integration
description: 現行developと未マージPRの実装を同じ作業ブランチへ統合するときに使う
---

# 未マージPR統合時の注意点

## 事象

PR作成時点と現在の`develop`で認証・ルーティング実装が並行して変更されている場合、PRコミットの単純なcherry-pickで複数ファイルの競合が発生する。

## 原因

PRの親コミットと現在の`develop`の差分を確認せず、変更対象が設定画面だけだと判断して取り込むため、共通ファイルの差分も同時に適用される。

## 正しい対処

1. PRの親コミット、現在の`develop`、PR差分の関係を`git show`と`git diff`で確認する。
2. 共通ファイルは現在の`develop`の実装を保持し、PR固有の画面・テスト・ルート差分だけを統合する。
3. ルート公開名、認証ガード、既存管理者ルートを確認し、対象画面へ到達する統合テストを実行する。
4. `git diff origin/develop...HEAD`で統合後の差分に対象外の上書きがないことを確認する。

5. 共通API client・認証adapterを統合する場合は、`fetch(`や独自adapter生成を全clientで検索し、対象APIが共通基盤を経由していることを確認する。
6. Query・store・認証などのhookを利用する画面は、実アプリと同じProviderを統合テストでも配置する。route単体テストにも必要なProviderを明示する。
7. API契約を厳格化した場合は、既存テストfixtureへ必須レスポンス項目を追加し、`/auth/config`など前段リクエストを含むmockの呼び出し順を再現する。
8. 共通layoutと画面PRを統合した後は、同一routeへの重複リンク・重複route定義がないことを確認する。
