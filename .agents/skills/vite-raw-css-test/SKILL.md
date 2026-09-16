---
name: vite-raw-css-test
description: VitestでViteのrawファイル読込結果を検証するときに使う
---

# Vite raw CSSテストの注意点

## 事象

`import.meta.glob`に`?raw`と`import: "default"`を指定したテストで、CSS本文を文字列として扱うと実行環境によって`css.split is not a function`が発生する。

## 原因

Vite/Vitestの変換結果が、raw本文そのものではなく`default`プロパティを持つモジュールオブジェクトになる場合がある。

## 正しい対処

rawファイルのテストでは、読込結果の型を`string | { default: string }`として扱い、文字列の場合と`default`プロパティの場合の両方を正規化してから検証する。修正後はVitestだけでなく、lintとtypecheckも実行する。
