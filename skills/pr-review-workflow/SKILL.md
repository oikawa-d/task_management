---
name: pr-review-workflow
description: このtask_managementリポジトリでPRをレビューし、指摘対応からマージまで進めるときに必ず使う。gh CLIの認証が単一アカウント(oikawa-d)であるためGitHubの`Request changes`が自分のPRに付けられないという制約を前提に、レビュー結果の記録方法・修正エージェントへの委任・再レビューのループ・マージとissue closeまでの手順を定める。issueのラベル遷移は`issue-label-workflow`と併用する。
---

# PRレビューからマージまでの運用

## 大前提: 自分のPRには `Request changes` も `Approve` も付けられない

このリポジトリのPRはすべて `oikawa-d` が作成しており、gh CLIも同じアカウントで認証されている。GitHubは**自分自身のPRに対するレビュー提出を拒否する**ため、以下は必ず失敗する。

```bash
gh pr review <番号> --request-changes --body-file <file>
# => failed to create review: GraphQL: Review Can not request changes on your own pull request (addPullRequestReview)

gh pr review <番号> --approve
# => 同様に拒否される
```

**したがってレビュー結果は `gh pr comment` で本文コメントとして記録する。** 最初から `gh pr review` を試さず、`gh pr comment` を使う。

```bash
gh pr comment <番号> --body-file <file>
```

コメント冒頭に判定を明記し、GitHubのレビューステータスの代わりとする。

- `## レビュー結果: 要修正 (Changes requested)`
- `## レビュー結果: レビュー済み / LGTM`

`.agents/review-policy.md` が「レビュー結果は問題がない場合も『レビュー済み』と明記する」と定めているため、**LGTMの場合もマージ前に必ずコメントを残す**。

## レビューの実施単位

- 複数のPRを一度にレビューする場合、**PRごとに独立したサブエージェント**を起動する。レビューは読み取り専用なのでworktree分離は不要。
- レビュー用エージェントには「ファイル変更・コミット・push・`git checkout`・worktree作成・GitHubへのコメント投稿を禁止し、結果を報告するだけ」と明示する。差分は `gh pr diff <番号>`、ファイル全体は `git show origin/<branch>:<path>` で読ませる（作業ツリーを触らせない）。
- コメント投稿とマージは親エージェントが行う。委任先に判断と実行を同時に持たせない。

## レビューで見る観点

`.agents/review-policy.md` と `AGENTS.md` を必ず読んだうえで、PRの性質に応じた重点観点を指示する。

| PRの種類 | 重点観点 |
| --- | --- |
| GitHub Actions (CI/CD) | secrets の扱い、`pull_request_target` 等の危険トリガ、`permissions` の最小化、self-hosted runner のfork PR実行可否、ロールバック条件、action のバージョン固定 |
| 認証・認可 | トークン/Cookie/CSRF/OAuthリダイレクト、保存先、失効処理、エラーコードの一貫性、機密情報のログ出力、後方互換性 |
| フロントエンド(ポーリング/非同期) | `useEffect` のクリーンアップ、依存配列、リクエストの重複発火とレース、`AbortSignal` の伝搬、リトライ/バックオフ方針 |
| 管理者向け画面 | ルートガード(認証必須/ロール必須)の有無、個人情報の表示・ログ出力、破壊的操作の確認導線 |
| ドキュメント整合 | 同一の関数・エンドポイント・エラーコードが**他のドキュメントにも重複記載されていないか** grep で横断確認する |

### 見落としやすい確認

- **削除行が異常に多いPR**: `package-lock.json` の再生成なのか、意図しないソース削除なのかを必ず切り分ける。
- **PR本文とdiffの不一致**: 「〜を削除した」と書かれているのに実際は移設されている等。本文がstaleなままマージするとレビュワー・後続作業者を誤解させるので、本文の修正まで含めて対応する。
- **`gh pr checks` が "no checks reported" のケース**: チェックが無いのではなく紐づいていないだけのことがある。`gh run list` / `gh run view <id>` で実ワークフロー結果まで確認する。
- **同一プロシージャ/関数の記述漏れ**: 「他の対象の網羅的棚卸し」はスコープ外にできるが、**そのPRが対象としたもの自体の記述漏れはスコープ外にできない**。

## 要修正だった場合の進め方

自分のPRであっても、レビュー担当と修正担当は分ける。

1. **親エージェント**がレビュー結果を `gh pr comment` で投稿する（指摘ごとに「なぜ問題か」「推奨対応」を書く）。
2. `issue-label-workflow` に従い、対応するissueを `changes-requested` に更新する。
3. **修正用サブエージェントを起動する。** 複数PRを並行修正する場合は、Agentツールの `isolation: "worktree"` を必ず指定して各エージェントを独立worktreeに分離する（同一チェックアウトを共有すると `git checkout`/`add`/`commit` が競合する）。
   修正エージェントへの指示に必ず含める:
   - 対象ブランチ名と `git fetch && git checkout <branch> && git pull --ff-only`
   - レビュー指摘の全文（どのファイルの何行目を、なぜ、どう直すか）
   - テストを実行し**実測結果を報告**すること
   - コミット・push・`gh pr comment` での修正報告まで行うこと
   - **`gh pr merge` と issue の close は禁止**（マージは親エージェントが行う）
   - 自分のworktree外のファイルを変更しないこと
   - `.env` の読み取り・変更禁止（`.env.example` への追記は可）
4. 修正完了後、**別のサブエージェント**に再レビューさせる。修正した本人に合否判定させない。
5. マージ可能になるまで 1〜4 を繰り返す。

## マージとclose

マージ前に必ず確認する。

```bash
gh pr view <番号> --json mergeable,mergeStateStatus --jq '"\(.mergeable) \(.mergeStateStatus)"'
gh pr checks <番号>
```

- `MERGEABLE` / `CLEAN` かつ全チェックpassであること。`UNKNOWN` はGitHub側の判定待ちなので、数秒おいて再取得する。
- `AGENTS.md` の通り squash merge する。

```bash
gh pr merge <番号> --squash
git push origin --delete <branch>
```

### `--delete-branch` は使わない

`gh pr merge --squash --delete-branch` は、ローカルのブランチ切り替えに失敗すると以下で止まり、**リモートブランチが消えないまま終わる**ことがある。

```
failed to run git: fatal: 'develop' is already used by worktree at '...'
```

マージ自体は成功しているので、`gh pr view <番号> --json state` で `MERGED` を確認したうえで、`git push origin --delete <branch>` で明示的に削除する。

### close時の申し送り

マージ後、関連issueを `gh issue close <番号> -c "..."` でコメント付きにcloseする。スコープ外とした指摘・後続タスクへの申し送りは、closeコメントと**引き継ぎ先issueの両方**にコメントとして残す（片方だけだと追跡が切れる）。

`Closes #<番号>` がPR本文にあってもGitHubが自動closeしない場合があるので、マージ後に `gh issue view` でstateを必ず確認する。

## 作業前のworktree清掃

過去のエージェントが残したworktreeがブランチを掴んでいると、修正エージェントの分離worktreeが作れない。作業開始前に確認する。

```bash
git worktree list
```

不要なものがあれば、**未コミットの変更が無いかを確認し、ユーザーの許可を得てから**削除する。

```bash
git -C <worktree> status --porcelain   # 先に中身を確認
git worktree remove --force <worktree>
git worktree prune
```

`node_modules` が残っていてディレクトリを物理削除できない場合でも、`git worktree remove` / `prune` が通っていればブランチは解放されているので作業を続行できる。
