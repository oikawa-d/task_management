---
name: github-auth-status
description: GitHub CLIでPR、Issue、レビュー、API、pushなどを操作する前に、指定アカウントの認証状態を検証する
---

# GitHub CLI認証確認

GitHubに関係する操作の直前には、必ず次の2コマンドを**両方とも**そのまま実行する。

```bash
gh auth status --hostname github.com
gh api user --jq .login
```

## 判定

`gh auth status` の表示だけで判断してはいけない。`gh auth status` は `api.github.com` へ到達できない場合も
「The token ... is invalid.」と表示し、しかも**終了コード0を返す**。この表示はトークン失効の証拠にならない。

必ず `gh api user --jq .login` の出力で切り分ける。

| `gh api user` の出力 | 判定 | 取るべき行動 |
| --- | --- | --- |
| ログイン名(`oikawa-d`)が返り、終了コード0 | 正常 | 後続のGitHub操作へ進む |
| HTTPステータスを伴わない通信エラー<br>(`error connecting to api.github.com` / `dial tcp` / `connection refused` / `no such host` / `proxyconnect` / `i/o timeout` など、文言は環境で変わる) | **ネットワーク到達不可**。トークンは失効していない | 再ログインしない。サンドボックスのネットワーク遮断を疑い、権限昇格して再実行する。解消しない場合はユーザーに報告して停止する |
| `HTTP 401: Bad credentials` など**HTTPステータスを伴う**認証エラー | トークン失効 | ユーザーに報告し、`gh auth login -h github.com` を依頼して停止する |

切り分けの原則は「**HTTPステータスが返っているか**」である。ステータスが返っていれば通信は成立しており認証の問題、
返っていなければ通信自体が成立しておらず認証状態は不明（失効ではない）。

正常と判定できた場合のみ、さらに次を確認して後続操作へ進む。

- ログインアカウントが `oikawa-d` である
- `Active account: true` である
- pushや非公開リポジトリ操作では `repo` scope が表示される

## 禁止事項

- `gh auth status` の「token is invalid」表示のみを根拠に「トークンが失効した」と報告しない。必ず `gh api user` で裏を取る。
- ネットワーク到達不可のときに `gh auth logout` / `gh auth login` を実行しない。有効なトークンを破棄してしまう。
- 保存済みの過去の結果や推測で認証済みと判断しない。
- `--active` など別のオプションに置き換えない。

新しいセッションの開始時、認証関連エラーの発生後、別のGitHub操作へ移る前にも同じ確認を再実行する。
