---
name: npm-sandbox-cache
description: 一時的なnpm installやPlaywright検証をsandbox環境で実行するときに適用する
---

# sandbox環境のnpmキャッシュにおける注意点

## 事象

workspace外の既定npm cache（`/home/doikawa/.npm`）へ書き込もうとすると、依存インストールが`EROFS`で失敗する。

## 原因

sandboxではworkspace外の既定npm cacheがread-onlyであり、npmが既定のキャッシュディレクトリへパッケージ情報を書き込めない。

## 正しい対処

一時または検証用のnpm installでは、タスク固有の一時ディレクトリをcacheに明示する。

```bash
npm install --cache /tmp/<task-specific-cache> <package>
```

`/tmp/<task-specific-cache>`は他タスクと共有せず、`HOME`や`.env`を変更しない。インストール後は、実行コマンドにも同じ依存環境を使用していることを確認する。
