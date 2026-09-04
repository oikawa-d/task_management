# PATCH /api/notifications/{notification_id}/read（通知を既読にする）

## 0. 関連ドキュメント

| ドキュメント | 内容 |
|--------------|------|
| [../../../basic_design/04_api.md](../../../basic_design/04_api.md) | §3.3 通知スキーマ、§4.2 エラーコード、§5 認可マトリクス |
| [../../../basic_design/01_database.md](../../../basic_design/01_database.md) | §3.8 notifications、§4.1.1 通知状態遷移 |
| [../../auth/03_csrf.md](../../auth/03_csrf.md) | session方式の更新系CSRF検証 |
| [../../database/10_table_notifications.md](../../database/10_table_notifications.md) | `mark_read` の更新条件と排他 |
| [./01_get_notifications.md](./01_get_notifications.md) | 通知一覧・レスポンススキーマ |

## 1. 概要

| 項目 | 内容 |
|------|------|
| エンドポイント | `PATCH /api/notifications/{notification_id}/read` |
| 目的 | ログインユーザー自身の通知を既読にする |
| 認証 | 必要（session Cookie または `Authorization: Bearer`） |
| 認可 | `notification.user_id = current_user.id` の本人一致のみ。adminも他人の通知は操作不可 |
| CSRF検証 | 必要（session方式）。jwt方式はBearer認証のため不要 |
| Origin検証 | 不要（Cookie発行を伴わない一般更新API） |
| 冪等性 | あり。既読済みでも `read_at` を上書きせず200を返す |
| レート制限 | user_id + 解決済みIP単位で60回/60秒。超過時は429 `TOO_MANY_ATTEMPTS`（`Retry-After`付き）、Redis障害時は503 |
| トランザクション境界 | 対象行の更新と未読件数取得を1トランザクションで行う |

## 2. 入出力仕様

### 2.1 リクエスト

| 名前 | 型 | 必須 | 制約 |
|------|----|------|------|
| notification_id | string(uuid) | ○ | UUID v4形式 |

ボディは持たない。session方式では `cerberus_sid` / `cerberus_csrf` Cookie と `X-CSRF-Token` ヘッダを受け取る。

### 2.2 レスポンス

**`200 OK`**

```json
{
  "id": "8f2a...",
  "read_at": "2026-09-04T02:00:00Z",
  "unread_count": 2
}
```

既読済みの場合は既存の `read_at` を返す。成功時に `Set-Cookie` は発行せず、`X-Request-ID` を付与する。

## 3. エラー仕様

| HTTP | code | 発生条件 |
|------|------|----------|
| 401 | `UNAUTHENTICATED` / `SESSION_EXPIRED` / `TOKEN_EXPIRED` / `TOKEN_INVALID` | 認証情報がない、または無効 |
| 403 | `USER_INACTIVE` | current userが無効化済み |
| 403 | `CSRF_INVALID` | session方式でCSRFが欠落・不一致 |
| 404 | `NOT_FOUND` | 通知が存在しない、または他ユーザーの通知を指定 |
| 422 | `VALIDATION_ERROR` | notification_idがUUID形式でない |
| 503 | `SERVICE_UNAVAILABLE` | PostgreSQL / Redis接続不能 |

他人の通知も404に統一し、通知IDの存在を列挙できないようにする。

## 4. 処理シーケンス

```mermaid
sequenceDiagram
    autonumber
    participant FE as React SPA
    participant R as notifications_router
    participant D as get_current_user / verify_csrf
    participant S as notification_service
    participant NR as notification_repository
    participant PG as PostgreSQL

    FE->>R: PATCH /api/notifications/{id}/read
    R->>D: 認証 + session方式のみCSRF検証
    D-->>R: CurrentUser
    R->>S: mark_read(notification_id, user.id)
    S->>NR: mark_read(db, notification_id, user.id)
    NR->>PG: UPDATE ... WHERE id=:id AND user_id=:me AND read_at IS NULL
    alt 対象なし
        NR->>PG: SELECT read_at WHERE id=:id AND user_id=:me
        PG-->>NR: 行なし
        NR-->>S: NotFoundError
        S-->>R: 404 NOT_FOUND
    else 未読または既読
        NR->>PG: SELECT COUNT(*) WHERE user_id=:me AND read_at IS NULL
        PG-->>NR: read_at + unread_count
        NR-->>S: ReadNotification
        S-->>R: ReadNotificationResponse
        R-->>FE: 200 {id, read_at, unread_count}
    end
```

## 5. 関数詳細

### 5.1 `api/routers/notifications_router.py :: mark_notification_read`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def mark_notification_read(notification_id: UUID, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> NotificationReadResponse` |
| 処理 | session方式では依存性でCSRF検証後、`notification_service.mark_read`を呼び出す |
| 送出例外 | `NotFoundError`（404）、認証・CSRF・DB接続系の共通例外 |
| 副作用 | 本人の通知1行の`read_at`更新 |

### 5.2 `service/notification_service.py :: mark_read`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def mark_read(db: AsyncSession, notification_id: UUID, user_id: UUID) -> NotificationReadResult` |
| 処理 | repositoryへ`user_id`を必ず渡し、対象行がなければ404。既読済みは値を保持したまま未読件数だけ再計算する |
| 副作用 | 既読化と未読件数取得 |

### 5.3 `repository/notification_repository.py :: mark_read`

```sql
UPDATE notifications
   SET read_at = COALESCE(read_at, now())
 WHERE id = :notification_id
   AND user_id = :user_id
RETURNING id, read_at;
```

`user_id` 条件をSQLに含め、サービス層の検証漏れがあっても他人の通知を更新できないようにする。更新0件後の存在確認も同じ `id AND user_id` 条件で行う。

## 6. テスト設計

| No | 区分 | ケース | 期待結果 | テスト名案 |
|----|------|--------|----------|------------|
| 1 | 結合 | 未読の本人通知を既読化 | 200、`read_at`設定、未読件数が1減る | `test_mark_read_own_unread_notification` |
| 2 | 結合 | 既読済み通知を再度指定 | 200、元の`read_at`を保持 | `test_mark_read_is_idempotent` |
| 3 | 結合 | 他人の通知IDを指定 | 404、通知は変更されない | `test_mark_read_other_users_notification_returns_404` |
| 4 | 結合 | session方式でCSRF不正 | 403 `CSRF_INVALID`、DB更新なし | `test_mark_read_rejects_invalid_csrf` |
| 5 | 単体 | notification_idが不正 | 422 `VALIDATION_ERROR` | `test_mark_read_rejects_invalid_id` |
