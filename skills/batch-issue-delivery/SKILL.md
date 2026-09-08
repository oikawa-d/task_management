---
name: batch-issue-delivery
description: このtask_managementリポジトリのbatch関連Issueを実装・統合・CI検証するときに使う。batch単体の通常開発や、batchと無関係なIssueには使わない。
---

# batch Issue対応

このリポジトリのbatch関連Issueでは、子Issueの実装だけでなく、親phase/roadmapの受け入れ条件まで確認する。詳細設計は `docs/detailed_design/batch/` と `docs/detailed_design/infra/` を正とする。

## 実装前の確認

- Issueごとに「実装task」か「親phase/roadmapの統合・受け入れ確認」かを分ける。親Issue向けの検証限定を実装taskへ誤って適用しない。
- `batch/app/main.py` が遅延importするモジュールを、実装後に実ファイルとして確認する。schedulerの登録テストだけで、実ジョブ本体の欠落を完了扱いにしない。
- batchのDB/Redis直接接続、Redisロック、通知dedupe、通知・api_history・batch_historyの保持期間パージが、親Issueの完了条件に含まれるか確認する。
- `.env`は読まない。テスト・CIには`.env.example`または明示したダミー環境変数を使う。

## テストとCIの注意

- `batch/pytest.ini`を追加・変更する場合、既存のpytest設定を上書きしない。非同期テストを使うため、`asyncio_mode = auto`を維持し、`batch/tests/conftest.py`がimportする`pytest-asyncio`とbatch/requirements.txtの依存をCIでインストールする。
- integration jobはテストファイルだけでなく、そのテストのconftest・fixture・import依存まで確認する。`pip install pytest`だけでは不十分になり得る。
- CI追加後は、失敗ログを最後まで取得して原因を分類する。`pytest_asyncio`や`pydantic_settings`のimport失敗は接続障害ではなくCI実行依存の不足である。
- Docker検証は`docker info`でdaemon接続可否を先に確認する。ソケット権限不足でローカル検証できない場合は、コード不具合と混同せず、CIまたはDocker利用可能な環境で検証する。
- ローカルでは、DB/Redis依存テスト、依存不要の単体テスト、Dockerテストを分けて実行し、未実施範囲と理由を報告する。

## 統合・完了確認

- 複数agentの変更は、各branchの`git diff origin/develop...origin/<branch> --stat`等で実差分を確認してから統合する。agentの口頭報告だけで取り込まない。
- `jobs`→`repository`→`models`の依存方向を守り、batchから`api/app`をimportしない。
- 成功時のRedis実行ロックはTTLまで保持し、失敗時だけ所有者確認後に解放する。`dedupe_key`のDB一意制約とRedisロックを併用する。
- PR merge後は、base branchが`develop`の場合でもIssueが自動closeされたかをGitHub上で確認する。OPENのままなら、対応PRとCI結果をコメントして明示的にcloseする。
- CI全項目成功、レビュー済み、Issue close、ローカルdevelop同期、作業worktree/branch整理までを完了条件とする。
