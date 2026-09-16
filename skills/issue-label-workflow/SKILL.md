---
name: issue-label-workflow
description: このtask_managementリポジトリでGitHub issueに対応する一連の作業(着手・PR作成・レビュー指摘対応・修正再開)のたびに必ず使う。Issueに`in-progress`/`review`、PRにレビュー中の`in-progress`/完了後の`approve`を付与して進捗状態を管理し、他エージェント・他人との作業重複を防ぐ。実装・レビュー・修正を別々のエージェントが担当する運用を前提とする。
---

# issueラベルによる進捗状態管理

このリポジトリではgh CLIの認証が単一のGitHubアカウント(oikawa-d)に紐づいているため、`assignee`では「誰が/どのエージェントが対応中か」を区別できない。また、実装・レビュー・修正を別々のエージェントが担当することが前提のため、「自分か他人か」でも判断できない。そのため、**「誰が」ではなく「Issueが今どのフェーズにあるか」をラベルで管理し、これから始めようとしているフェーズの前提ラベルと一致するかだけを確認する。**Issueは`in-progress`/`review`、PRはレビュー中に`in-progress`、完了後に`approve`を付与する。1つのIssueに複数PRは作成しない。PR側は、gh CLIが単一アカウント認証のため**自分のPRに`Approve`/`Request changes`を提出できない**(GitHubが拒否する)。そのためレビュー結果は`gh pr comment`で判定を明記したコメントとして残す。詳細は`pr-review-workflow` skillを参照。

## 状態ラベル(常にどれか1つ、またはラベルなし)

- `in-progress` : 実装・修正作業中
- `review` : PR作成後のレビュー待ち・レビュー中・変更依頼後の再レビュー待ち
- `approve` : レビュー完了。PR側に付与する

**状態ラベルを複数同時に付けない。** ラベルを付ける際は、付与対象以外の状態ラベルが付いていれば必ず外す。

## フェーズごとの前提ラベル(共通ルール)

これから始めようとしている作業が下表のどのフェーズにあたるかを判断し、**開始前ラベル**と現在のラベルが一致するかを確認する。一致しなければ、担当エージェントが誰であるかに関わらず、フェーズの取り違え・重複着手・状態の更新漏れのいずれかが起きている可能性があるため、着手前にユーザーへ報告し確認する。

| これから行う作業 | 開始前ラベル(前提) | 開始後に付けるラベル |
| --- | --- | --- |
| 新規実装(未着手のissue) | ラベルなし | `in-progress` |
| レビュー | `review` | (Issueはレビュー中このまま。結果に応じて手順4または5へ) |
| 修正対応 | `review` | `in-progress` |

## 状態遷移

```
(未着手・ラベルなし)
      │ 着手
      ▼
 in-progress ───────────────┐
      │ PRを作成             │ 修正を再開
      ▼                     │
 review (Issue) ────────────┐
      │ PR作成・レビュー      │ 修正を再開
      ▼                      │
 in-progress (PR)            │
      │ レビュー完了           │
      ▼                      │
 approve (PR)                │
      │ マージ・issue close    │
      ▼
 (ラベル解除)
```

## 手順

### 0. 対象issueとリポジトリの確定
- 対象のissue番号・リポジトリ(owner/repo)が不明な場合は補完せずユーザーに確認する。

### 1. 新規実装への着手前
- 必ず以下で現在のラベルとstateを取得する。

  ```bash
  gh issue view <番号> --repo <owner/repo> --json labels,state,title
  ```

- 前提ラベルは「ラベルなし」。`in-progress`/`review`/`approve` のいずれかが既に付いている場合、実装フェーズを始めてよい状態ではないので着手しない。誰が付けたラベルかに関わらず、現在どのフェーズかをユーザーに報告し、対応してよいか確認する。
- ラベルが何も付いていないことを確認できたら、`in-progress` を付与してから実装に進む。

  ```bash
  gh issue edit <番号> --repo <owner/repo> --add-label in-progress
  ```

- 状態ラベルを削除する場合は、先に `gh label list --repo <owner/repo>` でリポジトリに存在する正式名称を確認する。存在しないラベル名を `--remove-label` に渡すと、対象Issueの更新全体が失敗するため、実際に定義されている状態ラベルだけを指定する。

- `state` が `CLOSED` の場合、着手前にユーザーに確認する。ただしレビュー指摘対応など、close済みPRに紐づく再オープン前提の作業であることが明確な場合はこの限りではない。

### 2. PR作成時
- PRを作成したら、Issueの`in-progress`を`review`へ変更し、PRに`in-progress`を付ける(このときIssueの前提ラベルは`in-progress`)。

  ```bash
  gh issue edit <番号> --repo <owner/repo> --remove-label in-progress --add-label review
  gh api -X POST repos/<owner>/<repo>/issues/<PR番号>/labels -f "labels[]=in-progress"
  ```

### 3. レビューに着手する前
- レビューを依頼された/レビュー作業を始める前にも、必ず現在のラベルを確認する。前提ラベルは `review`。付いていない場合、まだ実装中・レビュー対象外・フェーズ不一致の可能性があるため、着手前にユーザーに確認する。
- **変更依頼あり**の場合は、レビューコメントの冒頭に`要修正 (Changes requested)`と明記したうえで、Issueの`review`を維持する。専用の状態ラベルは追加せず、修正作業を開始するときに手順4へ進む。
- **LGTM → マージ**の場合は、レビューコメントに「レビュー済み / LGTM」と明記し、PRに`approve`を付与してから手順5へ進む。

### 4. 修正対応への着手前
- 前提ラベルは `review`。付いていない場合、まだレビュー中・フェーズ不一致の可能性があるため、着手前にユーザーに確認する。
- 前提ラベルを確認できたら、Issueの`review`を`in-progress`へ変更してから修正する。PRの`in-progress`は維持する。

  ```bash
  gh issue edit <番号> --repo <owner/repo> --remove-label review --add-label in-progress
  ```

- 修正後、再度PRを更新・レビュー依頼したらIssueを`review`へ戻す。PRは`in-progress`を維持する。

### 5. 完了時(マージ・close)
- PRがマージされ、issueがcloseされたら状態ラベルを外す(close済みissueに状態ラベルを残さない)。

  ```bash
  gh issue edit <番号> --repo <owner/repo> --remove-label in-progress --remove-label review
  gh api -X DELETE repos/<owner>/<repo>/issues/<PR番号>/labels/in-progress
  gh api -X DELETE repos/<owner>/<repo>/issues/<PR番号>/labels/approve
  ```

  (実際に付いているラベルのみ指定すればよく、付いていないラベルを指定してもエラーにはならない)

## 注意

- 複数issueをまとめて対応する場合(バッチ対応等)も、各issueごとにこの確認・付与を行う。1つでもこれから行う作業の前提ラベルと現在のラベルが一致しないissueがあれば、それだけを除外して報告する。
- 状態ラベルは進捗の一時的な管理用であり、issueの恒久的な分類ラベル(bug/enhancement等)とは役割が異なる。
