---
name: service-transaction-test-mocking
description: service層のDBトランザクション異常系テストを追加するときに、repository境界とcommit障害を分離して検証する。
---

# service層トランザクションテストのモック境界

## 事象

commit時のDB接続障害を検証するテストで、repositoryの依存メソッドを差し替えなかったため、commit障害に到達する前に`execute`属性エラーが発生した。

## 原因

service層のテストでDBオブジェクトだけを簡略化し、repositoryが呼び出す`execute`などの境界を確認していなかった。

## 正しい対処

- service層のトランザクションテストでは、repositoryの書き込みメソッドを`AsyncMock`へ差し替える。
- DBの`commit`に`DBAPIError`を設定し、`rollback`の呼び出しと`raise_database_error`による変換を検証する。
- repositoryの実DB実行を含めるテストは、service層の異常系テストとは分離して実DBまたはrepositoryテストへ配置する。
