---
name: db-return-value-mapping
description: DBプロシージャの戻り値をRepositoryからServiceへ受け渡す変更を行うときに型付きで写像する
---

# DB戻り値の写像における注意点

## 事象

DBプロシージャのOUTパラメータをRepositoryの戻り値として追加した際、SQLAlchemyの行マッピング値が`Any`となり、mypyの戻り値型検査に失敗する。

## 原因

`Result.mappings()`は列名を動的に扱うため、型チェッカーは取得値の実型を保証できない。

## 正しい対処

- Repositoryの公開戻り値型を明示し、DB行の値は`typing.cast`でその型へ写像する。
- OUTパラメータ名、NULL時の意味、対象なし時のService処理を設計書とテストで一致させる。
- `mypy app`を実行し、追加箇所の`Any`漏れがないことを確認する。既存の無関係なエラーは分離して報告する。
