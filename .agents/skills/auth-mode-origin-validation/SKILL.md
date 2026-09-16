---
name: auth-mode-origin-validation
description: 更新系APIのOrigin検証を認証方式に応じて配線・テストするときに使う
---

# 認証方式別Origin検証の注意点

## 事象

通常のJWT更新APIへOrigin検証を常に適用すると、Authorizationヘッダだけで認証するクライアントがOriginヘッダなしで拒否される。一方、既存テストがJWTでもOrigin必須を期待していると、仕様変更後に失敗する。

## 原因

Cookieを自動送信するsession方式と、Authorizationヘッダを明示送信するJWT方式では、通常APIのCSRF攻撃面が異なる。Cookieを利用する認証API（refresh/logout等）と通常のJWT APIを同じ依存関係で扱っている。

## 正しい対処

- 通常の更新系APIは`verify_origin_if_session`と`verify_csrf_if_session`を使い、session方式だけOrigin/CSRFを検証する。
- refresh/logoutなどCookieを利用する認証APIは、認証方式に関係なく`verify_origin`/`verify_csrf`を使う。
- sessionとJWTの両方について、Originあり・なし、CSRFあり・なしの期待動作をRouterテストで検証する。
- 依存関係を変更したら、既存テストがJWTへ誤ったOrigin必須を課していないか確認する。
