---
name: alembic-sql-source-mapping
description: Alembicリビジョンが履歴用SQL資材を参照する変更を行うときに、参照先のファイル名と配置を検証する
---

# AlembicとSQL資材の対応における注意点

## 事象

履歴用のlegacy SQL資材をリネームして保存した場合、Alembicリビジョンの参照名と実ファイル名が一致しないと、CIのupgrade時に`FileNotFoundError`が発生する。

## 原因

SQL資材の論理名と履歴を示す物理ファイル名を別々に決め、migrationが実際に読むパスをcommit前に検証していなかった。

## 正しい対処

- migrationの各`Path`参照について、対象ディレクトリの実ファイル名と照合する。
- 履歴保存用にファイル名を変更する場合は、論理SQL名から物理ファイル名への明示的なマッピングを1か所に定義する。
- `alembic upgrade head`を実行するCIジョブと同じ作業ディレクトリ・ファイル配置で、upgrade対象リビジョンのファイル読込を確認する。
