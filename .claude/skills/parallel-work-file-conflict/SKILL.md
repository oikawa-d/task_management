---
name: parallel-work-file-conflict
description: 複数のissue・PR・サブエージェントで並行作業を分割するとき、同一ファイルへの競合を事前に回避するために使う。
---

# 並行作業によるファイル競合

## 事象

同一phase配下のtaskを並行して実装した結果、10件のオープンPRのうち5件が `CONFLICTING/DIRTY` になった。

### 依存定義ファイルの同一行編集

4つのPRが `frontend/package.json` に**完全に同一の差分**を独立に作っていた（`react-dom` の行末カンマ付与位置まで一致）。

```
#234: + "react-router-dom": "^7.18.3"
#230: + "react-router-dom": "^7.18.3"
#229: + "react-router-dom": "^7.18.3",  + "zustand": "^5.0.15"
#228: + "react-router-dom": "^7.18.3",  + "zustand": "^5.0.15"
```

`package-lock.json` も5PRで変更されており、手動解決が極めて困難な競合になった。

### 同一パスのファイルを別々に新規作成

2つのPRが同一パスのファイルを**それぞれ `new file` として作成**し、内容が非互換になった。

| ファイル | PR A | PR B |
|---|---|---|
| `features/board/types.ts` | `BoardResponse { columns }` 型 | `BoardColumns` エイリアス |
| `features/board/components/TaskCard.tsx` | dnd-kit未使用の素の `<button>` | dnd-kit 使用版 |

### 既存実装の上書き

あるPRは、base作成後にdevelopへマージされた `AppLayout.tsx`/`authStore.ts`/`routes.ts` を**新規ファイルとして作り直して**いた。マージすれば認証ガード・既存画面・CD定義が失われる状態だった。

## 原因

- phase分解の段階で、配下taskが**どのファイルを触るか**を洗い出していなかった
- 共通依存（`react-router-dom`、`zustand` 等）を機能PRに混ぜていた
- 古いbaseから分岐したまま長期間rebaseせず、developの進行に追従していなかった
- 並行するサブエージェントを同一チェックアウトで動かした（過去に実際に事故が発生）

## 正しい対処

### task分割時

- phase issueの本文に、**配下taskが変更するファイルの一覧**を書き出す。重複があれば分割方針を見直す
- **共通依存の追加は単独taskに切り出し、機能taskより先にマージする**。機能PRに依存追加を混ぜない
- 同一ファイルを触るtaskは並行させず、直列に並べる

### 実装着手時

```bash
git fetch origin --prune
git switch develop && git pull --ff-only origin develop
```

- **必ず最新のdevelopから分岐する**。着手前に必ず実行する
- 作業が長期化した場合、PR作成前に `git rebase origin/develop` で追従させる
- 新規ファイルを作る前に、そのパスが既に存在するかを確認する

  ```bash
  git fetch origin && git ls-tree -r origin/develop --name-only | grep <path>
  ```

### サブエージェントへ委任するとき

- **ファイルを変更する並行エージェントは、必ず独立したgit worktreeに分離する**（Agentツールの `isolation: "worktree"`）。同一チェックアウトを共有させると、並行する `git checkout`/`add`/`commit` が競合する
- 読み取り専用（調査・レビューのみ）の並行エージェントはworktree分離不要
- 各エージェントの完了後、口頭報告だけで信用せず実差分を検証する

  ```bash
  git diff origin/develop...origin/<branch> --stat
  ```

### PR作成後

- `gh pr view <n> --json mergeable,mergeStateStatus` で競合状態を確認する
- 複数PRがopenのとき、変更ファイルの重複を洗い出す

  ```bash
  for n in <PR番号...>; do gh pr view $n --json files -q ".files[].path" | sed "s|^|$n |"; done \
    | awk '{print $2}' | sort | uniq -c | sort -rn | awk '$1>1'
  ```
