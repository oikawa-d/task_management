---
name: sqlalchemy-from-statement-relationships
description: SQLAlchemyのfrom_statementでORMリレーションを使うrepositoryを実装・変更するときに適用する
---

# from_statementとORMリレーションの注意点

## 事象

`select(Model).from_statement(...)` で取得したORMモデルでは、モデルに `lazy="joined"` を設定していてもリレーションが未ロードになる場合がある。非同期セッションでその属性へアクセスすると、`MissingGreenlet` または未設定値による実行時エラーになる。

## 原因

`from_statement` は任意SQLの結果をORMへ写像するため、通常のORM SELECTで適用されるjoined loadingを暗黙に保証しない。テストがモックした関連オブジェクトを返していると、このDB実行時の差異を検出できない。

## 正しい対処

- 実DBのrepositoryテストで、取得直後にサービス層が関連属性を参照する経路を検証する
- 関連が必要な場合は `selectinload` などの明示的なloaderを指定し、クエリ回数とN+1の有無を確認する
- DB関数の戻り値に関連列を含める設計の場合は、関数の戻り値型・migration・repository写像・設計書を同時に更新する
