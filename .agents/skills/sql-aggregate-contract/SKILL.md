---
name: sql-aggregate-contract
description: タスク一覧・詳細などに集計値を追加するとき、N+1を避けるSQL集約契約と設計書・静的テストを同時に確認する。
---

# SQL集約値の契約

## 適用条件

`tasks`の一覧・詳細・カレンダー・ボードにコメント件数などの集計値を追加または変更するときに適用する。

## 実装ルール

- 集計対象は`GROUP BY`で一度集約し、主クエリへ`LEFT JOIN`する。行ごとの相関`SELECT count(*)`は使用しない。
- 0件のタスクは`COALESCE`で0を返し、戻り値の型（例: `BIGINT`）をFNの戻り値契約と一致させる。
- repositoryからタスク件数に比例した追加クエリを発行しない。集計はDBのFN内部で完結させる。
- SQL資材、Alembicリビジョン、repositoryの写像、設計書のテーブル・Mermaid図を同じ変更で確認する。

## 検証

- 各対象FNに`GROUP BY task_id`と集約結果の`LEFT JOIN`があることを静的テストで確認する。
- 相関`SELECT count(*) FROM task_comments ... t.id`が残っていないことを確認する。
- コメント0件・複数件・ページングされた一覧を、実DB結合テストまたは同等のrepository契約テストで検証する。
- 設計書のクエリ回数・データアクセス表が「集約JOIN」と一致していることを確認する。
