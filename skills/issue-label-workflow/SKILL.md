---
name: issue-label-workflow
description: このtask_managementリポジトリでGitHub issueに対応する一連の作業(着手・PR作成・レビュー指摘対応・修正再開)のたびに必ず使う。issueに`in-progress`/`review-requested`/`changes-requested`ラベルで進捗状態を排他的に管理し、他エージェント・他人との作業重複を防ぐ。実装・レビュー・修正を別々のエージェントが担当する運用を前提とする。
---

# issueラベルによる進捗状態管理

このリポジトリではgh CLIの認証が単一のGitHubアカウント(oikawa-d)に紐づいているため、`assignee`では「誰が/どのエージェントが対応中か」を区別できない。また、実装・レビュー・修正を別々のエージェントが担当することが前提のため、「自分か他人か」でも判断できない。そのため、**「誰が」ではなく「issueが今どのフェーズにあるか」をラベルで管理し、これから始めようとしているフェーズの前提ラベルと一致するかだけを確認する。**ラベルは**issueのみ**に付与し、PR側はGitHub標準のレビュー機能(Approve/Request changes)をそのまま使う。

## 状態ラベル(常にどれか1つ、またはラベルなし)

- `in-progress` : 実装・修正作業中
- `review-requested` : PRを作成し、レビュー依頼中
- `changes-requested` : レビューで変更依頼があり、修正待ち

**3つのうち複数が同時に付いた状態を作らない。** ラベルを付ける際は、付与対象以外の状態ラベルが付いていれば必ず外す。

## フェーズごとの前提ラベル(共通ルール)

これから始めようとしている作業が下表のどのフェーズにあたるかを判断し、**開始前ラベル**と現在のラベルが一致するかを確認する。一致しなければ、担当エージェントが誰であるかに関わらず、フェーズの取り違え・重複着手・状態の更新漏れのいずれかが起きている可能性があるため、着手前にユーザーへ報告し確認する。

| これから行う作業 | 開始前ラベル(前提) | 開始後に付けるラベル |
| --- | --- | --- |
| 新規実装(未着手のissue) | ラベルなし | `in-progress` |
| レビュー | `review-requested` | (レビュー中はラベル変更なし。結果に応じて手順3または5へ) |
| 修正対応 | `changes-requested` | `in-progress` |

## 状態遷移

```
(未着手・ラベルなし)
      │ 着手
      ▼
 in-progress ───────────────┐
      │ PRを作成             │ 修正を再開
      ▼                     │
 review-requested            │
      │ レビューでchanges requested │
      ▼                     │
 changes-requested ─────────┘
      │
      ▼ (Approve → マージ)
 (ラベル解除・issue close)
```

## 手順

### 0. 対象issueとリポジトリの確定
- 対象のissue番号・リポジトリ(owner/repo)が不明な場合は補完せずユーザーに確認する。

### 1. 新規実装への着手前
- 必ず以下で現在のラベルとstateを取得する。

  ```bash
  gh issue view <番号> --repo <owner/repo> --json labels,state,title
  ```

- 前提ラベルは「ラベルなし」。`in-progress`/`review-requested`/`changes-requested` のいずれかが既に付いている場合、実装フェーズを始めてよい状態ではないので着手しない。誰が付けたラベルかに関わらず、現在どのフェーズかをユーザーに報告し、対応してよいか確認する。
- ラベルが何も付いていないことを確認できたら、`in-progress` を付与してから実装に進む。

  ```bash
  gh issue edit <番号> --repo <owner/repo> --add-label in-progress
  ```

- `state` が `CLOSED` の場合、着手前にユーザーに確認する。ただしレビュー指摘対応など、close済みPRに紐づく再オープン前提の作業であることが明確な場合はこの限りではない。

### 2. PR作成時
- PRを作成したら、`in-progress` を外し `review-requested` を付ける(このとき前提ラベルは `in-progress`)。

  ```bash
  gh issue edit <番号> --repo <owner/repo> --remove-label in-progress --add-label review-requested
  ```

### 3. レビューに着手する前
- レビューを依頼された/レビュー作業を始める前にも、必ず現在のラベルを確認する。前提ラベルは `review-requested`。付いていない場合、まだ実装中・レビュー対象外・フェーズ不一致の可能性があるため、着手前にユーザーに確認する。
- レビューの結果に応じて次のいずれかを行う。
  - **変更依頼あり**: PRに `Request changes` を付けた、またはレビューコメントで修正が必要と判断したら、`review-requested` を外し `changes-requested` を付ける。

    ```bash
    gh issue edit <番号> --repo <owner/repo> --remove-label review-requested --add-label changes-requested
    ```

  - **Approve → マージ**: 手順5へ進む。

### 4. 修正対応への着手前
- 前提ラベルは `changes-requested`。付いていない場合、まだレビュー中・フェーズ不一致の可能性があるため、着手前にユーザーに確認する。
- 前提ラベルを確認できたら、`changes-requested` を外し `in-progress` を付けてから修正する。

  ```bash
  gh issue edit <番号> --repo <owner/repo> --remove-label changes-requested --add-label in-progress
  ```

- 修正後、再度PRを更新・レビュー依頼したら手順2に戻り `review-requested` を付け直す。

### 5. 完了時(マージ・close)
- PRがマージされ、issueがcloseされたら状態ラベルを外す(close済みissueに状態ラベルを残さない)。

  ```bash
  gh issue edit <番号> --repo <owner/repo> --remove-label in-progress --remove-label review-requested --remove-label changes-requested
  ```

  (実際に付いているラベルのみ指定すればよく、付いていないラベルを指定してもエラーにはならない)

## 注意

- 複数issueをまとめて対応する場合(バッチ対応等)も、各issueごとにこの確認・付与を行う。1つでもこれから行う作業の前提ラベルと現在のラベルが一致しないissueがあれば、それだけを除外して報告する。
- 状態ラベルは進捗の一時的な管理用であり、issueの恒久的な分類ラベル(bug/enhancement等)とは役割が異なる。
