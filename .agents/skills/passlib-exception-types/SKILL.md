---
name: passlib-exception-types
description: Passlibのハッシュ検証エラーを捕捉するときに適用する。
---

# Passlib例外型の扱い

## 事象

不正なハッシュ検証時に、Passlibの`InvalidHashError`を例外クラスとして捕捉すると実行時に`TypeError`が発生する。

## 原因

`passlib.exc.InvalidHashError`は例外クラスではなく、互換性のための関数として公開されている。例外ハンドラの`except`に指定できない。

## 正しい対処

Passlibの不正ハッシュは`UnknownHashError`または`ValueError`として捕捉する。Ruff formatterの設定によっては例外タプルを崩すため、個別の`except`節を使う。実装前に対象シンボルが`BaseException`のサブクラスか確認し、不正ハッシュのテストを必ず実行する。
