---
name: github-cli-body-file
description: GitHub CLIでMarkdown本文を指定するときにシェル展開を防ぐために使う。
---

# GitHub CLI本文の安全な指定

## 事象

Markdownのバッククォートを含むPull Request本文をシェルのダブルクォート引数へ直接埋め込むと、本文中の文字列がコマンド置換として実行され、GitHub上の本文からコード表記やコマンド名が欠落する。

## 原因

GitHub CLIの引数へ渡す前に、シェルがバッククォートや`$()`を解釈するため、Markdown本文を文字列リテラルとして扱えない。

## 正しい対処

本文は`apply_patch`で一時Markdownファイルへ作成し、`gh pr create --body-file`または`gh pr edit --body-file`で渡す。本文更新後は`gh pr view --json body`でバッククォート、Issue参照、テスト結果が保持されていることを確認する。本文をGitHub APIへ送る場合も、ファイル内容を単一の`body`値として渡し、本文そのものをシェルコマンドへ直接記述しない。
