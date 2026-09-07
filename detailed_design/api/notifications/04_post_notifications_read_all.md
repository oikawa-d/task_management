# POST /api/notifications/read-all（通知をすべて既読にする）

## 0. 関連ドキュメント

| ドキュメント | 内容 |
|--------------|------|
| [../../../basic_design/04_api.md](../../../basic_design/04_api.md) | §3.3 通知スキーマ、§4.2 エラーコード、§5 認可マトリクス |
| [../../../basic_design/01_database.md](../../../basic_design/01_database.md) | §3.8 notifications、§4.1.1 通知状態遷移 |
| [../../auth/03_csrf.md](../../auth/03_csrf.md) | session方式の更新系CSRF検証 |
| [../../database/10_table_notifications.md](../../database/10_table_notifications.md) | `sp_mark_all_notifications_read` の更新条件と排他 |
| [../../../basic_design/05_frontend.md](../../../basic_design/05_frontend.md) | §3.1 「すべて既読にする」ボタン |

## 1. 概要

| 項目 | 内容 |
|------|------|
| エンドポイント | `POST /api/notifications/read-all` |
| 目的 | ログインユーザー自身の未読通知を一括で既読にする |
| 認証 | 必要（session Cookie または `Authorization: Bearer`） |
| 認可 | `notification.user_id = current_user.id` の本人一致のみ |
| CSRF検証 | 必要（session方式）。jwt方式は不要 |
| 冪等性 | あり。未読0件でも200を返す |
| レート制限 | user_id + 解決済みIP単位で60回/60秒。超過時は429 `TOO_MANY_ATTEMPTS`（`Retry-After`付き）、Redis障害時は503 |
| トランザクション境界 | `CALL sp_mark_all_notifications_read` 1回。既読件数・未読件数はSP結果またはFNで取得する |

## 2. 入出力仕様

リクエストボディ、クエリ、パスパラメータはない。session方式では `X-CSRF-Token` と認証Cookieを受け取る。

**`200 OK`**

```json
{ "updated_count": 3, "unread_count": 0 }
```

`updated_count` は今回既読化した行数、`unread_count` は処理後の本人宛て未読総数である。`Set-Cookie` は発行せず、`X-Request-ID` を付与する。

## 3. エラー仕様

| HTTP | code | 発生条件 |
|------|------|----------|
| 401 | `UNAUTHENTICATED` / `SESSION_EXPIRED` / `TOKEN_EXPIRED` / `TOKEN_INVALID` | 認証情報がない、または無効 |
| 403 | `USER_INACTIVE` | current userが無効化済み |
| 403 | `CSRF_INVALID` | session方式でCSRFが欠落・不一致 |
| 503 | `SERVICE_UNAVAILABLE` | PostgreSQL / Redis接続不能 |

## 4. 処理シーケンス

```mermaid
sequenceDiagram
    autonumber
    participant FE as NotificationPanel
    participant R as notifications_router
    participant D as get_current_user / verify_csrf
    participant S as notification_service
    participant NR as notification_repository
    participant PG as PostgreSQL

    FE->>R: POST /api/notifications/read-all
    R->>D: 認証 + session方式のみCSRF検証
    D-->>R: CurrentUser
    R->>S: sp_mark_all_notifications_read(user.id)
    S->>NR: sp_mark_all_notifications_read(db, user.id)
    NR->>PG: "SP/FN内部処理（正式呼び出しは§9.1参照）"
    PG-->>NR: rowcount
    NR->>PG: "SP/FN内部処理（正式呼び出しは§9.1参照）"
    PG-->>NR: 0
    NR-->>S: updated_count, unread_count
    S-->>R: ReadAllResponse
    R-->>FE: 200 {updated_count, unread_count}
```

## 5. 関数詳細

### 5.1 `api/routers/notifications_router.py :: mark_all_notifications_read`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def mark_all_notifications_read(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> NotificationReadAllResponse` |
| 処理 | CSRF検証済みの本人IDをサービスへ渡し、結果をそのまま返す |
| 送出例外 | 認証・CSRF・DB接続系の共通例外 |
| 副作用 | 本人の未読通知の`read_at`更新 |

### 5.2 `service/notification_service.py :: sp_mark_all_notifications_read`

`notification_repository.sp_mark_all_notifications_read(db, user_id)`を呼び出す。ユーザーIDをリクエストから受け取らず、認証済みユーザーからのみ解決する。

### 5.3 `repository/notification_repository.py :: sp_mark_all_notifications_read`

```sql
CALL sp_mark_all_notifications_read(:user_id);
```

`user_id` 一致かつ未読の行を一括で既読化する条件・更新件数の算出はSP内部の責務であり、repositoryは `CALL` のみを発行する。更新後は `SELECT fn_count_unread_notifications(:user_id)` を呼び、部分インデックス `ix_notifications_user_unread` を利用してレスポンスの `unread_count` を算出する。

## 6. 並行制御

個別既読化・ポーリング・全既読が同時に実行されても、`read_at IS NULL` 条件付きUPDATEが行ロック下で評価される。`updated_count`はそのトランザクションで実際に変更した行数であり、既読を二重計上しない。レスポンスの未読件数はフロントのキャッシュを上書きするが、次回ポーリングで再同期される。

## 7. 関数相関図

```mermaid
flowchart LR
    R["notifications_router.mark_all_notifications_read"] --> S["notification_service.sp_mark_all_notifications_read"]
    S --> NR["notification_repository.sp_mark_all_notifications_read"]
    NR --> N[("notifications（SP内部）")]
    NR -->|"SELECT fn_count_unread_notifications"| N
```

## 8. データ遷移図

```mermaid
flowchart LR
    A["本人の未読通知"] -->|"CALL sp_mark_all_notifications_read（同一トランザクション）"| B["本人の既読通知"]
    B --> C["更新件数と未読件数を集計"]
    C --> D["ReadAllResponse"]
    E["本人の未読0件"] -->|"UPDATE 0件"| C
    F["他人の通知"] --> G["状態変更なし"]
```

## 9. SP/FNデータアクセス一覧

### 9.1 正式なDBアクセス契約

本APIのrepositoryは、次のSP/FN呼び出しとDTO写像だけを行う。

| 種別 | 契約 | 説明 |
|------|------|------|
| sp_mark_all_notifications_read | `sp_mark_all_notifications_read(p_user_id)` | sp_mark_all_notifications_readを呼び出し、結果をレスポンスへ写像する |

repositoryはDBテーブルへ直結せず、SP/FN契約だけを呼び出す。 直下の従来のテーブルI/O表はSP/FN内部SQLの補足であり、repositoryの発行契約ではない。既読更新の条件と冪等性はSP層の責務であり、他人の通知・不存在の判定結果はAPI層で404へ変換する。


| 分岐 | 発行クエリ | トランザクション |
|------|------------|------------------|
| 常に | `CALL sp_mark_all_notifications_read` 1回 + `SELECT fn_count_unread_notifications` 1回 | 2呼び出しを1トランザクションでcommit |
| 認証/CSRF失敗 | 0回 | DB処理なし |

SPが返す更新件数を `updated_count` に使用するため、既読済み・他人の行は件数に含めない。

## 10. テスト設計

| No | 区分 | ケース | 期待結果 | テスト名案 |
|----|------|--------|----------|------------|
| 1 | 結合 | 本人に未読3件 | 200、`updated_count=3`、`unread_count=0` | `test_sp_mark_all_notifications_read_updates_own_unread_notifications` |
| 2 | 結合 | 未読0件で実行 | 200、`updated_count=0`、`unread_count=0` | `test_sp_mark_all_notifications_read_empty_is_success` |
| 3 | 結合 | 他人の未読が存在 | 本人分だけ更新、他人分は未読のまま | `test_sp_mark_all_notifications_read_never_updates_other_users` |
| 4 | 結合 | session方式でCSRF不正 | 403 `CSRF_INVALID`、DB更新なし | `test_sp_mark_all_notifications_read_rejects_invalid_csrf` |
| 5 | 結合 | 個別既読と同時実行 | 件数が負にならず、最終的に本人の未読が0 | `test_sp_mark_all_notifications_read_concurrent_sp_mark_notification_read_is_consistent` |

## 11. 不明点・要検討事項

- 個別既読化との同時実行時の最終的な未読件数はDBの行ロックに従う。通知更新を非同期キューへ移す場合は別設計とする。
