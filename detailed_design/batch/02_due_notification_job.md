# batch/02 期限通知ジョブ詳細設計

## 0. 関連ドキュメント

| ドキュメント | 内容 |
|--------------|------|
| [../../basic_design/01_database.md](../../basic_design/01_database.md) | §3.5 tasks、§3.8 notifications、§5.5 `sp_purge_notifications`、§7 Q-7 |
| [../../basic_design/02_redis.md](../../basic_design/02_redis.md) | 期限通知実行ロック `lock:notify_due:{YYYY-MM-DD}:{slot}` |
| [../../basic_design/06_infra_cicd.md](../../basic_design/06_infra_cicd.md) | §2.1 batchコンテナ、§4.5通知設定 |
| [./00_overview.md](./00_overview.md) | batchの依存方向・設定・手動実行 |
| [./01_scheduler.md](./01_scheduler.md) | APSchedulerからの起動 |
| [../database/10_table_notifications.md](../database/10_table_notifications.md) | 通知DDL・`dedupe_key` |
| [../database/08_db_functions.md](../database/08_db_functions.md) | `sp_purge_notifications` |
| [../log/00_history.md](../log/00_history.md) | `batch_history`の開始・完了・失敗記録 |
| [../database/12_table_batch_history.md](../database/12_table_batch_history.md) | `batch_history`のカラム・状態制約 |

## 1. 概要

| 項目 | 内容 |
|------|------|
| 対象 | `batch/app/jobs/due_notification_job.py :: run_due_notification_job` |
| 実行時刻 | `NOTIFY_DUE_RUN_HOURS`（既定10時・17時）の各値に対応する2つのcronジョブ。分は `NOTIFY_DUE_CRON_MINUTE`、`APP_TIMEZONE`基準 |
| 対象タスク | `status <> 'done'`、`assignee_id IS NOT NULL`、`due_at IS NOT NULL`、`due_at <= 翌日10:00` |
| 下限 | 設けない。期限切れタスクも当日のリマインド対象とする |
| 作成通知 | 担当者へ `type='due_soon_batch'` を作成 |
| 重複防止 | Redisの日付・実行枠別ロックと `UNIQUE (user_id, dedupe_key)` の二重防御 |
| 保持期間 | ジョブ末尾で通知と`api_history`/`batch_history`の保持期間プロシージャを実行 |

「翌日10時まで」は境界値を含む（`due_at <= threshold`）。10時・17時の両枠で同じ境界を使う。DBにはUTCで保存し、`threshold`は実行日の`APP_TIMEZONE`翌日 `NOTIFY_DUE_TARGET_HOUR`（既定10時）をUTCへ変換する。

## 2. 入出力仕様

| 区分 | 内容 |
|------|------|
| 入力 | `BatchSettings`、現在時刻、PostgreSQL、Redis |
| 出力 | 作成件数、スキップ件数、`batch_history`の完了・失敗行、ログ。通知・履歴の期限超過行の削除 |
| 副作用 | Redisロック取得、notifications INSERT、`batch_history`状態更新、各保持期間プロシージャ実行 |

## 3. 処理シーケンス

```mermaid
sequenceDiagram
    autonumber
    participant SCH as AsyncIOScheduler
    participant JOB as due_notification_job
    participant RD as Redis
    participant PG as PostgreSQL
    participant HIS as batch_history

    SCH->>JOB: 実行日のdatetimeとslot（10/17）を渡して起動
    JOB->>HIS: run_idを採番しinprogressをINSERT
    JOB->>RD: SET lock:notify_due:{local_date}:{slot} runner_id NX EX
    alt ロック取得失敗
        RD-->>JOB: nil（別プロセスが実行済み/実行中）
        JOB-->>SCH: 何もせず終了
    else ロック取得成功
        RD-->>JOB: OK
        JOB->>PG: SELECT open tasks WHERE due_at <= threshold ORDER BY id LIMIT chunk
        loop チャンクごと
            JOB->>PG: INSERT notifications ... ON CONFLICT (user_id,dedupe_key) DO NOTHING
        end
        JOB->>PG: CALL sp_purge_notifications(NOTIFICATION_RETENTION_DAYS)
        JOB->>PG: CALL sp_purge_api_history(API_HISTORY_RETENTION_DAYS)
        JOB->>PG: CALL sp_purge_batch_history(BATCH_HISTORY_RETENTION_DAYS)
        JOB->>HIS: complete・終了時刻・件数をUPDATE
        Note over JOB,RD: 成功時はロックをTTLまで保持（実行済みマーカー）
        JOB-->>SCH: 作成件数をrun_id付きでログ出力
    else ジョブ本体またはパージで失敗
        JOB->>HIS: error・終了時刻・error内容をUPDATE
        JOB-->>SCH: エラーをrun_id付きでログ出力しプロセス継続
    end
```

## 4. 抽出・通知作成規則

```sql
SELECT id, project_id, title, assignee_id, due_at
  FROM tasks
 WHERE status <> 'done'
   AND assignee_id IS NOT NULL
   AND due_at IS NOT NULL
   AND due_at <= :threshold_utc
 ORDER BY id
 LIMIT :chunk_size;
```

通知は次の値をスナップショットする。

| カラム | 値 |
|--------|----|
| `user_id` | `tasks.assignee_id` |
| `task_id` | `tasks.id` |
| `type` | `due_soon_batch` |
| `title` | `tasks.title` |
| `body` | `期限が近いタスクです`（表示文言は定数化し、将来の多言語化に備える） |
| `due_at` | 抽出時点の`tasks.due_at` |
| `dedupe_key` | `batch:{local_date}:{slot}:{task_id}` |

同じタスクが同一実行枠で複数回抽出されても、`ON CONFLICT DO NOTHING`で1通知に収める。10時枠と17時枠は `slot` が異なるため、それぞれ1通知を作成する。翌日は日付が変わるため新しいリマインドを作成する。

## 5. Redisロック

ロックキーは `lock:notify_due:{APP_TIMEZONEの実行日}:{slot}`、値はランナー固有の`runner_id`、TTLは`NOTIFY_DUE_LOCK_TTL_SECONDS`とする。取得は `SET key runner_id NX EX ttl`。解放時はLuaまたはトランザクションで値を比較してからDELし、別実行者のロックを削除しない。TTL満了後の同一枠の再実行はDBの一意制約で重複を防ぐ。

## 6. 失敗時の扱い

| 失敗箇所 | 扱い |
|----------|------|
| Redis接続不能 | fail-close。通知作成を行わずERRORログ。次回スケジュールまたは`--run-once`で再実行 |
| タスクSELECT/INSERT失敗 | チャンクのトランザクションをロールバックしERRORログ。ジョブ全体を失敗扱い |
| パージ失敗 | 通知作成済みデータは維持し、ジョブを失敗扱い。次回にパージを再試行 |
| 1タスクの不正データ | エラーを記録し、他タスクの処理を継続できる単位で分離 |

いずれの結果でも、開始時に作成した`batch_history`を可能な限り`complete`または`error`へ更新する。履歴更新自体が失敗した場合はジョブ結果を上書きせず、`run_id`を含むERRORログだけを残す。プロセスが強制終了した場合は`inprogress`が残る。

ロック取得後の失敗時は、`runner_id` が自分の値であることを確認してからロックを削除する。成功時はロックを削除せずTTLまで保持する。これにより、成功後の同一slot再実行は抑止し、失敗後の `--run-once` は実行できる。部分成功したチャンクは保持され、再実行時は `UNIQUE (user_id, dedupe_key)` により未作成分だけが追加される。

### 6.1 ロック結果と再実行の期待値

| ケース | ロックの状態 | ジョブの結果 | 次の実行 |
|--------|--------------|--------------|----------|
| 正常終了 | TTLまで保持 | `complete`。同一slotの重複通知は作成しない | 同一slotはスキップ。別slotは実行 |
| タスク抽出・通知INSERT・パージ失敗 | 所有者確認後に削除 | `error`。確定済みチャンクは保持 | 同一slotのcronまたは `--run-once` で再実行。既存通知は重複しない |
| Redis接続不能 | 取得なし | 通知を作成せずfail-close | Redis復旧後に再実行 |
| 同一slotの同時実行 | `SET NX` 成功者だけ保持 | 取得敗者は処理せずスキップ | 敗者の通知作成はない |
| 成功後の手動再実行 | 既存ロックが残る | ロック取得失敗でスキップ | 障害復旧の手動再実行は失敗時に行う |

## 7. 関数詳細

| 関数 | シグネチャ | 責務 |
|------|------------|------|
| `run_due_notification_job` | `async def run_due_notification_job(now: datetime, settings: BatchSettings, notification_slot: str) -> JobResult` | ローカル日付・共通閾値算出、日付・実行枠別ロック、抽出、通知作成、パージ |
| `iter_due_tasks` | `AsyncIterator[DueTask]` | `due_at <= threshold`のタスクをチャンク取得 |
| `bulk_create_due_notifications` | `async def ...(tasks, run_date, notification_slot) -> int` | `ON CONFLICT DO NOTHING`で一括INSERT |
| `purge_notifications` | `async def purge_notifications(retention_days: int) -> int` | `CALL sp_purge_notifications(...)` |
| `purge_api_history` | `async def purge_api_history(retention_days: int) -> int` | `CALL sp_purge_api_history(...)`。対象は `api_history.created_at` |
| `purge_batch_history` | `async def purge_batch_history(retention_days: int) -> int` | `CALL sp_purge_batch_history(...)`。対象は `batch_history.started_at` |
| `start_batch_history` | `async def start_batch_history(batch_name: str, trigger_type: str, slot: str | None) -> UUID` | `batch_history`へ`inprogress`をINSERT |
| `finish_batch_history` | `async def finish_batch_history(run_id: UUID, result: JobResult) -> None` | 成否・終了時刻・件数をUPDATE |
| `purge_histories` | `async def purge_histories(settings: BatchSettings) -> None` | `purge_notifications`、`purge_api_history`、`purge_batch_history` を各設定値で実行。ログイン履歴は運用者が手動実行 |

batchのrepositoryはAPIのrouter/serviceをimportしない。接続・ORMモデル・通知INSERTをbatch内で完結させる。

## 8. テスト設計

| No | 区分 | ケース | 期待結果 | テスト名案 |
|----|------|--------|----------|------------|
| 1 | 単体 | 10時・17時実行時の閾値計算 | どちらも翌日10時ちょうどを含む同じUTC値になる | `test_due_threshold_is_shared_by_both_slots` |
| 2 | 結合 | 期限切れ・当日・翌日10時ちょうどを含む | 未完了かつ担当者ありの3件が対象 | `test_due_job_selects_past_and_boundary_tasks` |
| 3 | 結合 | `status='done'`、未割当、期限NULL | 通知を作成しない | `test_due_job_excludes_done_unassigned_and_no_due` |
| 4 | 結合 | 同じ実行枠のジョブを2回実行 | 2回目の作成件数0、重複なし | `test_due_job_is_idempotent_on_same_slot` |
| 5 | 結合 | 10時枠と17時枠を実行 | 同じタスクに各枠1件ずつ通知を作成する | `test_due_job_creates_one_notification_per_slot` |
| 6 | 結合 | 2プロセスが同じ実行枠で同時実行 | Redisロック取得者だけが抽出する | `test_due_job_uses_slot_scoped_redis_lock` |
| 7 | 結合 | 通知保持期間を超過した行がある | パージされ、期間内の行は残る | `test_due_job_purges_expired_notifications` |
| 8 | 結合 | ジョブが正常終了する | `batch_history`が`complete`になり、件数と終了時刻が保存される | `test_due_job_completes_batch_history` |
| 9 | 結合 | ジョブ本体またはパージが失敗する | `batch_history`が`error`になり、error_code/detailが保存される | `test_due_job_records_batch_failure` |
| 10 | 結合 | API・batch履歴が30日を超過する | 両テーブルの期限超過行だけが削除される | `test_due_job_purges_api_and_batch_history` |

## 9. 関数相関図

```mermaid
flowchart LR
    J["run_due_notification_job"] --> L["redis_lock"]
    J --> T["iter_due_tasks"]
    T --> I["bulk_create_due_notifications"]
    I --> N[("notifications")]
    J --> P["purge_histories"]
    P --> SP["sp_purge_notifications / api_history / batch_history"]
    J --> H["start_batch_history / finish_batch_history"]
    H --> BH[("batch_history")]
```

## 10. データ遷移図

```mermaid
flowchart TB
    A["起動日時・slot"] --> B["batch_history: inprogress"]
    B --> C{"Redisロック取得"}
    C -->|"失敗"| D["skipped・終了"]
    C -->|"成功"| E["期限対象タスクをチャンクSELECT"]
    E --> F["通知をチャンクINSERT<br/>ON CONFLICT DO NOTHING"]
    F --> G["保持期間プロシージャ"]
    G --> H["batch_history: complete"]
    E -.->|"DB/パージ失敗"| I["batch_history: error"]
    D --> J["ログ・ロックTTL"]
    H --> J
    I --> J
```

## 11. クエリ・トランザクション

| 処理 | 発行回数 | トランザクション境界 |
|------|----------|----------------------|
| 対象抽出 | `SELECT` はチャンクごとに1回 | チャンク単位でcommit。全件を1トランザクションに保持しない |
| 通知作成 | チャンクごとに `INSERT ... ON CONFLICT DO NOTHING` を1回 | 対象抽出と通知作成をチャンク単位でcommit |
| 保持期間処理 | 通知・API履歴・Batch履歴の `CALL` を各1回 | ジョブ本体のトランザクションとは分離 |
| 履歴 | 開始INSERT 1回、終了UPDATE 1回 | 本体処理とは分離し、履歴失敗でジョブ結果を変更しない |

対象0件でも保持期間処理と履歴終了処理は実行する。Redisロック取得失敗時は通知関連のDBクエリを発行しない。

## 12. 不明点・要検討事項

- ロック取得後にプロセスが強制終了した場合の `inprogress` 行は自動補正せず、運用者がログと照合する現行方針を維持する。
- チャンクサイズ・保持期間・ロックTTLの具体値は [../infra/04_env_config.md](../infra/04_env_config.md) の環境変数を正とする。
