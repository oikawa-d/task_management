---
name: issue-label-workflow
description: このtask_managementリポジトリでGitHub issueに対応する一連の作業(着手・PR作成・レビュー指摘対応・修正再開)のたびに必ず使う。IssueとPRに`review-request`/`in-progress`、PRのレビュー完了後に`approve`を付与して進捗状態を管理し、他エージェント・他人との作業重複を防ぐ。実装・レビュー・修正を別々のエージェントが担当する運用を前提とする。
---

# issueラベルによる進捗状態管理

このリポジトリではgh CLIの認証が単一のGitHubアカウント(oikawa-d)に紐づいているため、`assignee`では「誰が/どのエージェントが対応中か」を区別できない。また、実装・レビュー・修正を別々のエージェントが担当することが前提のため、「自分か他人か」でも判断できない。そのため、**「誰が」ではなく「Issueが今どのフェーズにあるか」をラベルで管理し、これから始めようとしているフェーズの前提ラベルと一致するかだけを確認する。**レビュー待ち・修正後の再レビュー待ちは`review-request`、レビュー中・修正中は`in-progress`、問題のないレビュー完了PRは`approve`を付与する。1つのIssueに複数PRは作成しない。PR側は、gh CLIが単一アカウント認証のため**自分のPRに`Approve`/`Request changes`を提出できない**(GitHubが拒否する)。そのためレビュー結果は`gh pr comment`で判定を明記したコメントとして残す。詳細は`pr-review-workflow` skillを参照。

## 状態ラベル(常にどれか1つ、またはラベルなし)

- `review-request` : レビュー待ち・修正後の再レビュー待ち
- `in-progress` : 実装・レビュー・修正作業中
- `approve` : レビュー完了。PR側に付与する

**状態ラベルを複数同時に付けない。** ラベルを付ける際は、付与対象以外の状態ラベルが付いていれば必ず外す。各遷移では、付与前に`review-request`/`in-progress`/`approve`をすべて外してから、遷移先だけを付与する。

## フェーズごとの前提ラベル(共通ルール)

これから始めようとしている作業が下表のどのフェーズにあたるかを判断し、**開始前ラベル**と現在のラベルが一致するかを確認する。一致しなければ、担当エージェントが誰であるかに関わらず、フェーズの取り違え・重複着手・状態の更新漏れのいずれかが起きている可能性があるため、着手前にユーザーへ報告し確認する。

| これから行う作業 | 開始前ラベル(前提) | 開始後に付けるラベル |
| --- | --- | --- |
| 新規実装(未着手のissue) | ラベルなし | `in-progress` |
| レビュー | `review-request` | IssueとPRを`in-progress`へ変更してレビューを開始する |
| 修正対応（レビュー指摘後） | `in-progress` | IssueとPRの`in-progress`を維持する |

## 状態遷移

```
(未着手・ラベルなし)
      │ 着手
      ▼
 in-progress
      │ PRを作成
      ▼
 review-request
      │ レビュー開始
      ▼
 in-progress (Issue/PR)
      │ レビュー指摘後の修正着手も維持
      │ 再レビュー依頼
      ▼
 review-request
      │ レビュー完了
      ▼
 approve (PR)
      │ マージ・issue close
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

- 前提ラベルは「ラベルなし」。`in-progress`/`review-request`/`approve` のいずれかが既に付いている場合、実装フェーズを始めてよい状態ではないので着手しない。誰が付けたラベルかに関わらず、現在どのフェーズかをユーザーに報告し、対応してよいか確認する。
- ラベルが何も付いていないことを確認できたら、`in-progress` を付与してから実装に進む。

  ```bash
  gh issue edit <番号> --repo <owner/repo> --add-label in-progress
  ```

- 状態ラベルを削除する場合は、`bash .agents/scripts/set-review-state-label.sh` を使用する。このスクリプトが対象Issue/PRの現在のラベルを取得し、存在する状態ラベルだけを削除するため、未付与ラベルの削除によるHTTP 404で遷移処理が停止しない。削除直前の競合で発生したHTTP 404も無視するが、認証・通信エラーなど404以外の失敗は握りつぶさない。

- `state` が `CLOSED` の場合、着手前にユーザーに確認する。ただしレビュー指摘対応など、close済みPRに紐づく再オープン前提の作業であることが明確な場合はこの限りではない。

### 2. PR作成時
- PRを作成したら、Issueの`in-progress`を`review-request`へ変更し、PRに`review-request`を付ける(このときIssueの前提ラベルは`in-progress`)。

  ```bash
  bash .agents/scripts/set-review-state-label.sh <owner>/<repo> <番号> review-request
  bash .agents/scripts/set-review-state-label.sh <owner>/<repo> <PR番号> review-request
  ```

### 3. レビューに着手する前
- レビューを依頼された/レビュー作業を始める前にも、必ず現在のラベルを確認する。前提ラベルは `review-request`。付いていない場合、まだ実装中・レビュー対象外・フェーズ不一致の可能性があるため、着手前にユーザーに確認する。
- レビュー着手時はIssueとPRの既存状態ラベルをすべて外し、`in-progress`を付与する。

  ```bash
  bash .agents/scripts/set-review-state-label.sh <owner>/<repo> <番号> in-progress
  bash .agents/scripts/set-review-state-label.sh <owner>/<repo> <PR番号> in-progress
  ```

- **変更依頼あり**の場合は、レビューコメントの冒頭に`要修正 (Changes requested)`と明記したうえで、IssueとPRを`in-progress`へ変更する。修正中はこのラベルを維持する。
- **LGTM → マージ**の場合は、レビューコメントに「レビュー済み / LGTM」と明記し、PRの既存状態ラベルをすべて外してから`approve`を付与し、手順5へ進む。

  ```bash
  bash .agents/scripts/set-review-state-label.sh <owner>/<repo> <PR番号> approve
  ```

### 4. 修正対応への着手前
- 前提ラベルは `in-progress`。レビューで変更要求が記録された後、IssueとPRがこのラベルであることを確認してから修正する。
- 修正着手時はIssueとPRの`in-progress`を維持し、ラベル変更は行わない。

  ```bash
  gh issue view <番号> --repo <owner/repo> --json labels,state,title
  gh pr view <PR番号> --repo <owner/repo> --json labels,state
  ```

- 修正後、再度PRを更新・レビュー依頼したらIssueとPRを`review-request`へ戻す。

  ```bash
  bash .agents/scripts/set-review-state-label.sh <owner>/<repo> <番号> review-request
  bash .agents/scripts/set-review-state-label.sh <owner>/<repo> <PR番号> review-request
  ```

### 5. 完了時(マージ・close)
- PRがマージされ、issueがcloseされたら状態ラベルを外す(close済みissueに状態ラベルを残さない)。

  ```bash
  bash .agents/scripts/set-review-state-label.sh <owner>/<repo> <番号> none
  bash .agents/scripts/set-review-state-label.sh <owner>/<repo> <PR番号> none
  ```

  (状態ラベル以外の恒久ラベルは削除しない。遷移後は状態ラベルが0個になることを検証する)

## 注意

- 複数issueをまとめて対応する場合(バッチ対応等)も、各issueごとにこの確認・付与を行う。1つでもこれから行う作業の前提ラベルと現在のラベルが一致しないissueがあれば、それだけを除外して報告する。
- 状態ラベルは進捗の一時的な管理用であり、issueの恒久的な分類ラベル(bug/enhancement等)とは役割が異なる。
- 旧 `review` ラベルは使用せず、既存Issueに付いている場合は状態を確認したうえで`review-request`または`in-progress`へ移行する。
