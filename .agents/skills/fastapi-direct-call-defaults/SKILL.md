---
name: fastapi-direct-call-defaults
description: FastAPIルーター関数を依存解決なしで直接テストするとき、Queryなどのデフォルト値とStarlette Request scopeを実値で補う
---

# FastAPIルーター直接テストの注意点

## 事象

FastAPIのルーター関数をpytestから直接呼び出すテストで、`Query(None)`が`None`として扱われず分岐が誤って実行された。また、Cookie参照を行う`Request`のscopeに`headers`がなく、実処理が例外になった。

## 原因

FastAPIが通常のリクエスト処理で解決する依存値を、直接関数呼び出しでは自動変換しないため。Starletteの`Request`も、テストで組み立てるscopeが実HTTP scopeの必須項目を満たしていないと、ヘッダ・Cookie参照時に失敗する。

## 正しい対処

- `Query`、`Path`、`Header`などの引数を直接渡す場合は、デフォルト値ではなく`None`や実際の入力値を明示する。
- `Request`を直接生成する場合は、少なくとも`type`、`method`、`path`、`headers`を含め、テスト対象が参照するscope項目を用意する。
- 依存解決後の挙動を検証するテストでは、可能な限り`TestClient`または`httpx`経由で実HTTPリクエストとして確認する。
