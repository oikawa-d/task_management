---
name: shared-layer-bypass
description: API client・認証処理・共通ユーティリティなど横断的な処理を新しく書くとき、既に存在する共通基盤を迂回していないか確認するために使う。
---

# 共通基盤の迂回

## 事象

認証方式差異吸収アダプタ `frontend/src/api/authAdapter/`（`SessionAdapter`/`JwtAdapter`、`CSRF_HEADER_NAME` を定義）が実装・マージされていたにも関わらず、**リポジトリ全体で呼び出しが0件**だった。

```bash
$ grep -rn "authAdapter\|X-CSRF-Token" frontend/src --include='*.ts' --include='*.tsx' | grep -v '\.test\.'
frontend/src/api/authAdapter/constants.ts:7:export const CSRF_HEADER_NAME = "X-CSRF-Token";
```

各API clientが独自に `fetch` を呼び `credentials: "include"` のみを指定していたため、

- sessionモード: `X-CSRF-Token` が付かず、更新系APIが403 `CSRF_INVALID` で全滅する
- jwtモード: `Authorization: Bearer` が付かず、認証に失敗する

という状態になっていた。設計書は該当エンドポイントすべてでCSRFヘッダ必須と規定していた。

## 原因

- 共通基盤を実装するissueと、それを利用する各機能のissueが別々に分割されており、**利用側のissueに「共通基盤を使う」ことが受け入れ条件として書かれていなかった**
- 既存のAPI clientがGET専用だったため、CSRFヘッダが無くても動いてしまい、問題が顕在化しなかった
- 共通基盤の側にも、迂回を検出する仕組み（lintルール等）が無かった

## 正しい対処

### 実装前

- 横断的な処理（HTTP通信、認証、ロギング、エラーハンドリング、日時整形、バリデーション）を書く前に、**同種の基盤が既にあるか必ず検索する**

  ```bash
  grep -rn "<扱う概念>" <project>/src --include='*.ts' --include='*.tsx' -l
  ls <project>/src/api <project>/src/lib <project>/src/core 2>/dev/null
  ```

- 基盤が見つかった場合、その公開インターフェース（`index.ts`/`types.ts`）を読み、**既存の契約に利用側を合わせる**。基盤側のインターフェースを変更するのは最後の手段とする

### 実装後

- 新しく書いた横断的処理が、既存基盤と重複していないかを確認する
- 基盤を実装した場合は、**利用箇所が1件以上あることを確認してからPRを出す**。利用側が別issueなら、そのissueに「この基盤を経由すること」を受け入れ条件として明記する

### 検出の仕組み

- 共通基盤を経由すべき処理について、直接呼び出しを禁止するlintルール（`no-restricted-imports`、`no-restricted-syntax` 等）の導入を検討する
- 要検討: 本リポジトリではまだこのlintルールは未導入
