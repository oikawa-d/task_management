---
name: integration-test-auth-fixtures
description: FastAPIのDB結合テストで認証済みHTTP操作をfixture化するときに使う
---

# FastAPI結合テストfixtureの注意点

## 事象

認証済みAPIを検証するfixtureで、生成したユーザーの識別子・パスワードをシナリオへ保持しないと、ログイン処理を再現できない。また、TestClientの既定接続元がIPアドレスとして解釈できず、INET型の監査ログ書き込みが失敗することがある。

## 原因

fixtureの生成値をテスト本体から参照できるデータモデルへ集約していなかった。さらに、TestClientが設定する仮想接続元を、PostgreSQLのINET列へ渡せる形式か確認していなかった。

## 正しい対処

- ユーザー作成時に生成したusernameとテスト用パスワードを、fixtureが返すシナリオへ明示的に保持する。
- 認証モードに応じてセッションCookieまたはJWTを返す共通authenticate fixtureを用意する。
- TestClientの接続元を`127.0.0.1`などの有効なIPへ設定し、認証・DB・Redisのキャッシュをテスト前後にクリアする。
- 認証経路を含む結合テストでは、ログインを含めたHTTPルートを実行し、fixture単独のモックで代替しない。
