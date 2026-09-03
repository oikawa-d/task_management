# PATCH /api/admin/users/{user_id}/role（ロール変更）

## 0. 関連ドキュメント

| ドキュメント | 内容 |
|--------------|------|
| [../../../basic_design/04_api.md](../../../basic_design/04_api.md) | §2.5 管理者API一覧（自己変更・最後のadmin保護の記述）、§4.2 エラーコード体系 |
| [../../../basic_design/01_database.md](../../../basic_design/01_database.md) | §3.1 users |
| [../../../basic_design/03_auth.md](../../../basic_design/03_auth.md) | §9.2 `core/deps.py`（`require_admin`）。role/usernameは常にPostgreSQLの現在値を正とする方針 |
| [../../database/01_table_users.md](../../database/01_table_users.md) | users テーブル定義（`ck_users_role`、`update_role_and_status`） |
| [./01_get_admin_users.md](./01_get_admin_users.md) | ロール変更後に反映される一覧API |
| [./03_patch_admin_user_status.md](./03_patch_admin_user_status.md) | 同じ「自己変更禁止・最後のadmin保護」の判定順序を共有する有効化/無効化API |

## 1. 概要

| 項目 | 内容 |
|------|------|
| エンドポイント | `PATCH /api/admin/users/{user_id}/role` |
| 目的 | 管理者が対象ユーザーの `role`（`member` ⇔ `admin`）を変更する |
| 認証 | 必要 |
| 認可 | admin のみ |
| CSRF検証 | 必要（session モードの更新系メソッド。`X-CSRF-Token` ヘッダ + `csrf:{sid}` 一致） |
| Origin検証 | 必要（Cookieを利用する更新系のため。jwt モードはAuthorizationヘッダのみで良くOriginは必須検証としない） |
| AUTH_MODE差異 | 差異なし。認証確立後の業務ロジックはモードに依存しない |
| 冪等性 | なし（現在のroleと同じ値を指定した場合は実質変化なしだが、自己変更禁止・最終admin判定は毎回同一ロジックを通過させるため厳密な冪等操作としては扱わない） |
| レート制限 | 対象外 |
| トランザクション境界 | アドバイザリロック取得 → 最後の有効admin判定 → `UPDATE users` を単一トランザクションで実行 |

## 2. 入出力仕様

### 2.1 リクエスト

**パスパラメータ**

| 名前 | 型 | 必須 | 制約 | 説明 |
|------|----|------|------|------|
| user_id | string(uuid) | ○ | UUID形式 | 対象ユーザーID |

**ボディ**

| フィールド | 型 | 必須 | 制約 | 説明 |
|-----------|----|------|------|------|
| role | string | ○ | `member` / `admin` のいずれか | 変更後のロール |

クエリパラメータ／該当ヘッダ（認証・CSRF・Cookieを除く）：なし。

### 2.2 レスポンス

**`200 OK`**

```json
{
  "id": "3f1c2a10-...",
  "username": "taro",
  "email": "taro@example.com",
  "role": "admin",
  "is_active": true,
  "updated_at": "2026-09-04T00:00:00Z"
}
```

| フィールド | 型 | NULL | 説明 |
|-----------|----|----|------|
| id | string(uuid) | 不可 | ユーザーID |
| username | string | 不可 | ログインID |
| email | string | 不可 | メールアドレス |
| role | string | 不可 | 更新後のロール |
| is_active | boolean | 不可 | 有効フラグ（本APIでは変更しないが最新値を返す） |
| updated_at | string(datetime) | 不可 | トリガにより自動更新された日時 |

`Set-Cookie` なし。共通ヘッダ `X-Request-ID` を全レスポンスに付与する。

## 3. エラー仕様

| HTTP | code | 発生条件 | メッセージ | 備考 |
|------|------|----------|------------|------|
| 401 | `UNAUTHENTICATED` / `SESSION_EXPIRED` / `TOKEN_EXPIRED` / `TOKEN_INVALID` | 認証情報なし・失効・不正 | 認証情報が無効です | |
| 403 | `USER_INACTIVE` | 実行者自身が `is_active=false` | アカウントが無効化されています | |
| 403 | `FORBIDDEN` | 実行者の `role != admin` | 権限がありません | |
| 403 | `CSRF_INVALID` | sessionモードでCSRFヘッダ不一致・欠落 | CSRFトークンが不正です | |
| 404 | `NOT_FOUND` | `user_id` が存在しない | ユーザーが見つかりません | |
| 409 | `SELF_MODIFICATION_NOT_ALLOWED` | `user_id` が実行者自身 | 自分自身のロールは変更できません | 4章の判定順序を参照 |
| 409 | `LAST_ADMIN_REQUIRED` | 対象が現在 `role=admin` かつ `is_active=true` で、変更後 `role=member` にすると有効なadminが0人になる | 最後の管理者を降格することはできません | 4章の判定順序を参照 |
| 422 | `VALIDATION_ERROR` | `role` が `member`/`admin` 以外・`user_id` がUUID形式でない | 入力内容に誤りがあります | `details` にフィールド情報 |
| 503 | `SERVICE_UNAVAILABLE` | PostgreSQL / Redis 接続不能 | しばらくしてから再度お試しください | fail-close |

`basic_design/04_api.md` §4.2 のエラーコード体系から逸脱しない。

## 4. 処理シーケンス

```mermaid
sequenceDiagram
    autonumber
    participant FE as "React SPA"
    participant R as "admin_router"
    participant D as "deps.require_admin"
    participant CSRF as "deps.verify_csrf"
    participant S as "admin_user_service"
    participant RP as "user_repository"
    participant PG as "PostgreSQL"

    FE->>R: PATCH /api/admin/users/{user_id}/role {role}
    R->>D: 認証 + admin確認
    D-->>R: CurrentUser(role=admin)
    R->>CSRF: Origin/CSRF検証（sessionモードのみCSRF必須）
    CSRF-->>R: OK
    R->>S: change_role(actor=CurrentUser, target_id, new_role)
    S->>RP: get_by_id(target_id) FOR UPDATE
    RP->>PG: "SELECT * FROM users WHERE id=:target_id FOR UPDATE"
    alt 対象が存在しない
        PG-->>RP: 0件
        RP-->>S: None
        S-->>R: NotFoundError
        R-->>FE: 404 NOT_FOUND
    else 存在する
        PG-->>RP: user行（行ロック取得）
        RP-->>S: User
        S->>S: target_id == actor.id ?
        alt 自分自身
            S-->>R: SelfModificationError
            R-->>FE: 409 SELF_MODIFICATION_NOT_ALLOWED
        else 他ユーザー
            S->>PG: "SELECT pg_advisory_xact_lock(hashtext('admin_role_change'))"
            Note over S,PG: 同時実行される複数の降格リクエストを<br/>直列化するための順序ロック
            S->>S: 降格（admin→member）かつ現在is_active=trueか判定
            alt 降格に該当
                S->>RP: count_active_admins_excluding(target_id)
                RP->>PG: "SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=true AND id<>:target_id"
                PG-->>RP: 残る有効admin数
                alt 残る有効admin数が0
                    RP-->>S: 0
                    S-->>R: LastAdminRequiredError
                    R-->>FE: 409 LAST_ADMIN_REQUIRED
                end
            end
            S->>RP: update_role_and_status(target_id, role=new_role, is_active=None)
            RP->>PG: "UPDATE users SET role=:new_role WHERE id=:target_id RETURNING *"
            PG-->>RP: 更新後の行
            RP-->>S: User
            S-->>R: UserDetail
            R-->>FE: 200 {user}
        end
    end
```

## 5. 処理フロー・分岐

```mermaid
flowchart TB
    A["リクエスト受信"] --> B["pydanticでuser_id/roleを検証"]
    B -->|"制約外"| B1["422 VALIDATION_ERROR"]
    B -->|"OK"| C["deps.get_current_user + require_admin"]
    C -->|"認証NG"| C1["401系"]
    C -->|"role != admin"| C2["403 FORBIDDEN"]
    C -->|"OK"| D["Origin/CSRF検証（sessionモード）"]
    D -->|"不一致"| D1["403 CSRF_INVALID"]
    D -->|"OK"| E["対象ユーザーをFOR UPDATEで取得"]
    E -->|"存在しない"| E1["404 NOT_FOUND"]
    E -->|"存在する"| F{"target_id == actor.id?"}
    F -->|"Yes"| F1["409 SELF_MODIFICATION_NOT_ALLOWED"]
    F -->|"No"| G{"降格（admin→member）かつ<br/>現在is_active=true?"}
    G -->|"No（昇格・現状維持・既に無効）"| I["UPDATE users SET role"]
    G -->|"Yes"| H["advisory lock取得 →<br/>残る有効admin数をCOUNT"]
    H -->|"0"| H1["409 LAST_ADMIN_REQUIRED"]
    H -->|"1以上"| I
    I --> J["200 {user}"]
    E -.->|"DB接続不能"| K["503 SERVICE_UNAVAILABLE"]
```

**判定順序の理由**：自己変更禁止は対象が誰であっても一定のため、DBへの追加問い合わせ（admin数COUNT）を発生させる前に判定して早期リターンする。最後のadmin判定は「降格の場合のみ」発生する高コストな確認であり、かつ同時実行時の競合を避けるため、対象行の `FOR UPDATE` に加えて `pg_advisory_xact_lock` で「同時に複数の降格処理が発生する」レースを直列化してからCOUNTする。行ロックのみでは新規admin追加や無関係ユーザーの更新とは競合しないため、admin降格処理同士の直列化にはアドバイザリロックが必要となる。

## 6. 関数詳細

### 6.1 `api/routers/admin_router.py :: patch_admin_user_role`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def patch_admin_user_role(user_id: UUID, payload: AdminUserRoleUpdateRequest, actor: CurrentUser = Depends(require_admin), _: None = Depends(verify_csrf), db: AsyncSession = Depends(get_db)) -> AdminUserDetailResponse` |
| 引数 | `user_id`: パス / `payload.role`: ボディ / `actor`: admin確認済みユーザー / `db`: DBセッション |
| 戻り値 | `AdminUserDetailResponse` |
| 送出例外 | なし（サービス層の例外をそのまま伝播） |
| 処理内容 | 1. `require_admin`・`verify_csrf` を通過 2. `admin_user_service.change_role` を呼び出す 3. 結果をそのまま返す |
| 副作用 | なし（副作用は全てservice/repository層） |

### 6.2 `service/admin_user_service.py :: change_role`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def change_role(actor: CurrentUser, target_id: UUID, new_role: str, db: AsyncSession) -> User` |
| 引数 | `actor`: 実行者（admin） / `target_id`: 対象ユーザーID / `new_role`: 変更後ロール / `db`: DBセッション |
| 戻り値 | 更新後の `User` |
| 送出例外 | `NotFoundError`（404）/ `SelfModificationError`（409）/ `LastAdminRequiredError`（409） |
| 処理内容 | 1. `user_repository.get_for_update(target_id)` で対象行をロック付き取得。存在しなければ `NotFoundError` 2. `target_id == actor.id` なら `SelfModificationError` 3. 「現在 `role=admin` かつ `is_active=true` かつ `new_role=='member'`」の場合のみ降格とみなす 4. 降格時は `acquire_admin_role_change_lock()` でアドバイザリロックを取得後、`user_repository.count_active_admins_excluding(target_id)` が0なら `LastAdminRequiredError` 5. 上記いずれにも該当しなければ `user_repository.update_role_and_status(target_id, role=new_role, is_active=None)` を実行 |
| 副作用 | DB更新（`users.role`）。Redis更新なし（本APIはロール変更のみで、既存セッション/トークンの失効は行わない。次回以降のリクエストで `deps.get_current_user` がPostgreSQLの現在roleを再取得するため、認可判定には反映される） |

### 6.3 `repository/user_repository.py :: get_for_update`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def get_for_update(db: AsyncSession, user_id: UUID) -> User \| None` |
| 引数 / 戻り値 | `user_id`：対象ユーザーID / 該当行（行ロック取得済み）または `None` |
| 発行SQL | `SELECT * FROM users WHERE id = :user_id FOR UPDATE` |
| 送出例外 | なし（`None` を返す） |
| 処理内容 | 1. 対象行をロック付きで取得し、同一トランザクション内の後続 `UPDATE` までロックを保持する |
| 副作用 | 行ロック（トランザクション終了まで） |

### 6.4 `repository/user_repository.py :: count_active_admins_excluding`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def count_active_admins_excluding(db: AsyncSession, exclude_user_id: UUID) -> int` |
| 引数 / 戻り値 | `exclude_user_id`：対象ユーザー自身を除外するID / 対象ユーザー以外の有効admin数 |
| 発行SQL | `SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=true AND id <> :exclude_user_id` |
| 使用インデックス | `ix_users_role`（実件数が少ないためSeq Scanに落ちる可能性はある） |
| 送出例外 | `OperationalError` |
| 処理内容 | 1. アドバイザリロック取得後に呼び出すことで、同時に発行される複数の降格リクエストがいずれもロック解放を待ってから直列にCOUNTする 2. 結果が0なら呼び出し元が `LastAdminRequiredError` を送出する |
| 副作用 | なし |

### 6.5 `service/admin_user_service.py :: acquire_admin_role_change_lock`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def acquire_admin_role_change_lock(db: AsyncSession) -> None` |
| 引数 / 戻り値 | `db`: DBセッション / なし |
| 発行SQL | `SELECT pg_advisory_xact_lock(hashtext('admin_role_change'))` |
| 送出例外 | なし（取得できるまでブロックする。トランザクションコミット/ロールバックで自動解放） |
| 処理内容 | 1. 固定キー `'admin_role_change'` に対するトランザクションスコープのアドバイザリロックを取得し、同時に発生する降格判定を直列化する |
| 副作用 | アドバイザリロック取得（トランザクション終了まで） |

## 7. 関数相関図

```mermaid
flowchart LR
    R["admin_router.patch_admin_user_role"] --> S["admin_user_service.change_role"]
    S --> RP1["user_repository.get_for_update"]
    S --> L["admin_user_service.acquire_admin_role_change_lock"]
    S --> RP2["user_repository.count_active_admins_excluding"]
    S --> RP3["user_repository.update_role_and_status"]
    RP1 --> M["models.User"]
    RP2 --> M
    RP3 --> M
```

## 8. データ遷移図

```mermaid
stateDiagram-v2
    [*] --> role_current: 対象ユーザーの現在role/is_active
    role_current --> self_rejected: target_id == actor.id<br/>109 SELF_MODIFICATION_NOT_ALLOWED
    role_current --> last_admin_rejected: 降格 かつ 残る有効admin=0<br/>409 LAST_ADMIN_REQUIRED
    role_current --> role_updated: UPDATE users SET role<br/>advisory lock はコミットで解放
    self_rejected --> [*]
    last_admin_rejected --> [*]
    role_updated --> [*]
```

Redisのキー状態は変化しない（本APIはPostgreSQLの `users.role` のみを更新する）。

## 9. データアクセス一覧

**PostgreSQL**

| テーブル／関数 | 操作 | 条件・TTL | 備考 |
|----------------|------|-----------|------|
| users | SELECT ... FOR UPDATE | `id=:target_id` | 対象行ロック |
| users | SELECT COUNT | `role='admin' AND is_active=true AND id<>:target_id` | 降格判定時のみ実行 |
| `pg_advisory_xact_lock` | 関数呼び出し | キー `hashtext('admin_role_change')` | 降格判定時のみ実行。トランザクション終了で自動解放 |
| users | UPDATE | `id=:target_id` | `role` のみ更新。`updated_at` はトリガ |

**Redis**

| キー | 操作 | TTL | 備考 |
|------|------|-----|------|
| `session:{sid}`（sessionモードのみ） | GET | `SESSION_TTL_SECONDS` | `deps.get_current_user` の認証確認のみ。本APIはRedisを更新しない |

## 10. バリデーション規則

| pydanticスキーマ | フィールド | 制約 | フロント（zod）との整合 |
|-------------------|-----------|------|--------------------------|
| パスパラメータ | user_id | UUID形式 | `zod.string().uuid()` |
| `AdminUserRoleUpdateRequest` | role | `Literal["member","admin"]` | `zod.enum(["member","admin"])` |

## 11. 非機能・セキュリティ考慮

| 観点 | 内容 |
|------|------|
| ログ出力 | 監査ログ対象。`actor.id`, `target_id`, `old_role`, `new_role`, 結果（成功/409種別）, `X-Request-ID` をINFO出力 |
| ユーザー列挙対策 | admin専用APIのため対象外 |
| タイミング攻撃対策 | 該当なし |
| レート制限 | なし |
| fail-close方針 | PostgreSQL接続不能時は `503 SERVICE_UNAVAILABLE` |
| 競合対策 | `FOR UPDATE` による対象行ロックと `pg_advisory_xact_lock` による降格処理の直列化により、2件の同時降格リクエストが両方成功して有効adminが0人になる事態を防ぐ |
| 認可の即時反映 | ロール変更は既存のセッション/アクセストークンを失効させない。次回リクエスト以降 `deps.get_current_user` がPostgreSQLの現在role列を再取得して認可判定に使うため、降格は次のリクエストから反映される（sessionはRedisの `session:{sid}` からuser_idのみ取得しroleはDB参照、jwtも同様にroleをJWT/Redisに含めない設計のため） |

## 12. テスト設計

| No | 区分 | ケース | 前提 | 期待結果 | pytest関数名案 |
|----|------|--------|------|----------|-----------------|
| 1 | 単体 | 自己変更は最後のadmin判定より先に拒否される | `target_id == actor.id`、かつ実質的に最後のadminでもある状況 | `409 SELF_MODIFICATION_NOT_ALLOWED`、`count_active_admins_excluding`未呼び出し | `test_change_role_self_modification_checked_before_last_admin` |
| 2 | 単体 | 最後の有効adminの降格は拒否される | 有効admin1名のみが存在し、それを対象に`member`へ変更 | `409 LAST_ADMIN_REQUIRED` | `test_change_role_last_admin_required` |
| 3 | 単体 | 無効化済みadminは降格対象カウントに含めない | 対象以外に `role=admin, is_active=false` のユーザーが存在 | `count_active_admins_excluding` が0を返し `409 LAST_ADMIN_REQUIRED` | `test_change_role_inactive_admin_not_counted` |
| 4 | 単体 | 昇格（member→admin）は最後のadmin判定を経由しない | 対象が `role=member` | `count_active_admins_excluding` 未呼び出しで200相当の更新処理へ | `test_change_role_promotion_skips_last_admin_check` |
| 5 | 結合 | 対象ユーザーが存在しない場合は404 | 存在しないUUID | `404 NOT_FOUND` | `test_change_role_target_not_found` |
| 6 | 結合 | 通常の降格（他に有効adminがいる）は成功する | 有効admin2名のうち1名を対象に`member`へ変更 | `200`、`users.role='member'` | `test_change_role_demote_success_with_other_admin` |
| 7 | 結合 | 同時に2件の降格リクエストが飛んだ場合、片方のみ成功する | 有効admin2名に対し同時に相互を`member`へ降格するリクエストを発行 | 1件は`200`、もう1件は`409 LAST_ADMIN_REQUIRED`（advisory lockによる直列化） | `test_change_role_concurrent_demotion_serialized` |
| 8 | 結合 | member（非admin）はアクセス不可 | `role=member` の実行者 | `403 FORBIDDEN` | `test_change_role_forbidden_for_member` |
| 9 | 結合 | sessionモードでCSRFヘッダ欠落は403 | `AUTH_MODE=session` | `403 CSRF_INVALID` | `test_change_role_csrf_required_in_session_mode` |
| 10 | 結合 | roleに不正値を指定すると422 | `role="superadmin"` | `422 VALIDATION_ERROR` | `test_change_role_invalid_role_value` |

No.7は本APIの中核である競合制御の検証であり、`asyncio.gather` 等で同時に2リクエストを発行し実PostgreSQLコンテナ上で検証する（`AUTH_MODE`両方で実施する必要はなく、認証確立後の業務ロジック検証のため `session` モードのみで実施し理由を明記する）。

## 13. 不明点・要検討事項

| 区分 | 内容 | 影響 |
|------|------|------|
| 要検討 | 「自己変更禁止」を、変更後の値が現在と同じ場合（例：admin自身が`role=admin`を指定）にも一律で409とするか、実質変化がない場合は許容するかは基本設計に明記がない。本書では一律で拒否する方針とした |
| 要検討 | `pg_advisory_xact_lock` に用いるロックキー文字列（`'admin_role_change'`）は基本設計に記載がなく本書での提案。同一キーを[03_patch_admin_user_status.md](./03_patch_admin_user_status.md)の無効化処理とも共有すべきかは実装時に要確認（役割変更と無効化を同一ロックで直列化すればより安全だが、本書では役割変更用として独立させた） |
