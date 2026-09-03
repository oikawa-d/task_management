# 02 Redis設計

## 1. 設計方針

| 項目 | 方針 |
|------|------|
| バージョン | Redis 8（単一ノード） |
| 役割 | 「ログイン状態が有効か」を判定するための揮発ストア。永続データは持たない |
| 永続化 | RDB / AOF いずれも**無効**。再起動で全ログイン状態が失われることを許容（要件書§4） |
| 失効方式 | 全キーに TTL を設定し、期限切れで自動失効。ログアウト時は `DEL` で即時失効 |
| 値の形式 | JSON文字列（`SET` + TTL）。構造の把握が容易でCLIから確認しやすいため |
| DB番号 | `0` を本番/開発用、`1` をテスト用（`REDIS_DB` / `REDIS_TEST_DB` で切替） |
| キー名前空間 | `{用途}:{識別子}`。プレフィックスは環境変数 `REDIS_KEY_PREFIX`（既定は空）を前置可能 |
| クライアント | `redis-py`（asyncio版）。接続プールをアプリ起動時に生成し、`redis_client.py` で単一管理 |

## 2. キー一覧

| キー | 値（JSON） | TTL | 設定元 | 用途 |
|------|-----------|-----|--------|------|
| `session:{session_id}` | `{user_id, created_at, ip}` | `SESSION_TTL_SECONDS`（既定1800） | session方式のログイン | セッションの有効性判定。role/usernameはPostgreSQLを正とし、Redis値を認可に使わない |
| `csrf:{session_id}` | `{token}` | セッションと同一 | session方式のログイン | CSRFトークンの照合 |
| `refresh:{token_hash}` | `{user_id, issued_at, family_id}` | `REFRESH_TTL_SECONDS`（既定1209600 = 14日） | jwt方式のログイン/リフレッシュ | リフレッシュトークンの有効性判定。roleは保持しない |
| `refresh_used:{token_hash}` | `{user_id, family_id, used_at}` | `REFRESH_TTL_SECONDS` | ローテーション成功時 | 使用済みトークンの再提示から family を特定する tombstone |
| `refresh_family_revoked:{user_id}:{family_id}` | `1` | `REFRESH_TTL_SECONDS` | refresh token再利用検知時 | family失効を原子的に記録し、失効処理中の競合refreshも拒否 |
| `user_sessions:{user_id}` | Set（有効な session_id の集合） | `SESSION_TTL_SECONDS`（ログイン中のリクエストごとに延長） | session方式のログイン | 全端末ログアウト・管理者による強制ログアウト |
| `user_refresh:{user_id}` | Set（有効な token_hash の集合） | `REFRESH_TTL_SECONDS`（新規発行・ローテーション時に延長） | jwt方式のログイン | 同上（JWT方式） |
| `oauth_state:{state}` | `{redirect_to, code_verifier, nonce, created_at}` | `OAUTH_STATE_TTL_SECONDS`（既定600） | OAuth2認可開始 | ブラウザ結合済みstate・PKCE・OIDC nonceの検証値 |
| `oauth_handoff:{code}` | `{user_id, redirect_to, created_at}` | 60秒 | jwt OAuthコールバック | フロントへの一時コード。`GETDEL` でワンタイム消費 |
| `pwreset:{token_hash}` | `{user_id, requested_at}` | `PASSWORD_RESET_TTL_SECONDS`（既定1800） | パスワードリセット要求 | リセットトークンの有効性判定 |
| `emailverify:{token_hash}` | `{user_id, requested_at}` | `EMAIL_VERIFY_TTL_SECONDS`（既定86400 = 24時間） | 会員登録・認証メール再送 | メール認証トークンの有効性判定 |
| `emailverify_current:{user_id}` | 現在のtoken_hash | `EMAIL_VERIFY_TTL_SECONDS` | 会員登録・認証メール再送 | 再送時に旧メール認証トークンを失効させるための逆引き |
| `emailverify_sent:{user_id}` | 直近の送信時刻（数値） | `EMAIL_VERIFY_RESEND_INTERVAL_SECONDS`（既定60） | 認証メール送信時に `SETEX` | 認証メール再送のレート制限（メール爆撃の防止） |
| `login_fail:{key_hash}` | 連続失敗回数（数値） | `LOGIN_LOCK_WINDOW_SECONDS`（既定900） | ログイン失敗時に `INCR` | 正規化した識別子と確定済みクライアントIPの組み合わせ。メール/IDをRedisキーへ平文保存しない |

**値に保存しない情報**：パスワード、パスワードハッシュ、アクセストークンそのもの、リフレッシュトークンの平文。

## 3. TTL設計

```mermaid
flowchart TB
    subgraph session["session方式"]
        S1["ログイン<br/>session TTL=30分"] --> S2["リクエストごとに<br/>EXPIRE で延長（スライディング）"]
        S2 --> S3["30分無操作 → 自動失効"]
        S2 --> S4["ログアウト → DEL で即時失効"]
    end
    subgraph jwt["jwt方式"]
        J1["ログイン<br/>access TTL=15分（署名のみ）<br/>refresh TTL=14日（Redis保持）"] --> J2["access期限切れ<br/>→ /auth/refresh"]
        J2 --> J3["Luaで原子的に旧refreshを使用済み化<br/>新refreshをSETEX（ローテーション）"]
        J3 --> J2
        J1 --> J4["ログアウト → refreshをDEL<br/>accessは期限切れまで有効（最大15分）"]
    end
```

| キー | 延長（スライディング） | 理由 |
|------|----------------------|------|
| `session:{sid}` | **する** | 操作中の有効期限を延長するが、`created_at + SESSION_ABSOLUTE_TTL_SECONDS` を超えては延長しない |
| `refresh:{hash}` | **しない** | ローテーション時に新しいキーを発行するため、TTLは発行時点から固定 |
| `oauth_state`, `pwreset`, `emailverify` | しない | ワンタイム用途 |

> `session` はアイドルタイムアウト（既定30分）に加え、絶対有効期限（既定8時間）を設ける。`touch_session` はセッション作成時刻を確認し、残り時間が0以下なら延長せず失効扱いにする。

## 4. データ遷移図

### 4.1 session方式のキー遷移

```mermaid
stateDiagram-v2
    [*] --> 未ログイン
    未ログイン --> セッション有効: POST /auth/login<br/>SETEX session:{sid}<br/>SETEX csrf:{sid}<br/>SADD user_sessions:{uid}
    セッション有効 --> セッション有効: 認証付きリクエスト<br/>GET session:{sid} → EXPIRE で延長
    セッション有効 --> 未ログイン: POST /auth/logout<br/>DEL session:{sid} / csrf:{sid}<br/>SREM user_sessions:{uid}
    セッション有効 --> 未ログイン: TTL満了（Redisが自動削除）
    セッション有効 --> 未ログイン: Redis再起動（全キー消失）
    セッション有効 --> 未ログイン: 管理者による強制ログアウト<br/>user_sessions:{uid} を走査してDEL
```

### 4.2 jwt方式のリフレッシュトークン・ローテーション

```mermaid
sequenceDiagram
    autonumber
    participant FE as React SPA
    participant API as FastAPI
    participant RD as Redis

    FE->>API: POST /api/auth/refresh（HttpOnly Cookie + CSRF header）
    API->>API: sha256(Cookieのrefresh token) = hash<br/>新access/refreshを生成
    API->>RD: Luaでfamily失効確認・旧キー確認・原子的ローテーション
    alt 旧キーが存在しfamilyが有効
        RD-->>API: {user_id, family_id}
        API-->>FE: 200 {access_token} + Set-Cookie(新refresh, 新CSRF)
    else 旧キーが存在しない（失効済み・再利用）
        RD-->>API: revoked / reused + family情報
        API->>RD: refresh_family_revoked:{uid}:{family} をSETEX（原子的にfamily失効）
        API-->>FE: 401 TOKEN_REVOKED
    end
```

`family_id` は「1回のログインから派生するリフレッシュトークンの系列ID」。単純な `GET` → `DEL` → `SET` では同時リクエストが二重に成功し得るため、`rotate_refresh_token` は Redis Lua スクリプトで「family失効確認・旧キーの存在確認・旧キー削除・使用済み tombstone 作成・新キー作成」を原子的に実行する。旧キーがない場合は `refresh_used:{old_hash}` を確認し、tombstone があればそこから `user_id` / `family_id` を得て `refresh_family_revoked:{uid}:{family}` を設定する。全refresh処理はこのfamily失効キーも確認する。

### 4.3 OAuth2 state の遷移

```mermaid
stateDiagram-v2
    [*] --> state発行: GET /auth/oauth/google<br/>SETEX oauth_state:{state} TTL=10分
    state発行 --> 検証成功: callback でstateとCookie一致<br/>GETDEL（ワンタイム消費）
    state発行 --> 検証失敗: state不一致 / 期限切れ<br/>→ 400 INVALID_STATE
    検証成功 --> [*]
    検証失敗 --> [*]
```

## 5. 操作関数詳細（`repository/redis_store.py`）

すべて async 関数。TTL値は `core/config.py` の設定から受け取り、関数内にハードコードしない。

### 5.1 セッション操作

| 関数 | 引数 | 戻り値 | 処理概要 |
|------|------|--------|----------|
| `create_session` | `user_id: UUID`, `ip: str \| None`, `ttl: int` | `tuple[str, str]`（session_id, csrf_token） | `secrets.token_urlsafe(32)` で session_id と csrf_token を生成 → `SETEX session:{sid}` / `SETEX csrf:{sid}` / `SADD user_sessions:{uid}` / `EXPIRE user_sessions:{uid}` をパイプラインで実行 |
| `get_session` | `session_id: str` | `SessionData \| None` | `GET session:{sid}` → JSON復元。存在しなければ `None` |
| `touch_session` | `session_id: str`, `user_id: UUID`, `ttl: int`, `absolute_expires_at` | `bool` | セッション作成時刻を基に実効TTLを `min(ttl, absolute_expires_at - now())` で計算し、`EXPIRE session:{sid}` / `csrf:{sid}` / `user_sessions:{uid}` を同一処理で更新。セッションキーが無ければ `False` |
| `get_csrf_token` | `session_id: str` | `str \| None` | `GET csrf:{sid}` |
| `delete_session` | `session_id: str`, `user_id: UUID` | `None` | `DEL session:{sid}` / `DEL csrf:{sid}` / `SREM user_sessions:{uid}` |
| `delete_all_sessions` | `user_id: UUID` | `int`（削除件数） | `SMEMBERS user_sessions:{uid}` → 各 session/csrf を `DEL` → `DEL user_sessions:{uid}` |

### 5.2 リフレッシュトークン操作

| 関数 | 引数 | 戻り値 | 処理概要 |
|------|------|--------|----------|
| `store_refresh_token` | `token: str`, `user_id: UUID`, `family_id: str`, `ttl: int` | `None` | `sha256(token)` をキーに `SETEX refresh:{hash}` + `SADD user_refresh:{uid}` + `EXPIRE user_refresh:{uid} ttl` |
| `get_refresh_token` | `token: str` | `RefreshData \| None` | `GET refresh:{sha256(token)}` |
| `rotate_refresh_token` | `old_token: str`, `new_token: str`, `ttl: int` | `RefreshData \| TokenReused` | Luaスクリプトで旧キー確認・使用済み tombstone 作成・新キー `SETEX`・集合更新を原子的に実行。旧キーが既に使用済みなら `TOKEN_REUSED` と family 情報を返す |
| `revoke_refresh_token` | `token: str`, `user_id: UUID` | `None` | `DEL refresh:{hash}` + `SREM user_refresh:{uid}` |
| `revoke_token_family` | `user_id: UUID`, `family_id: str` | `int` | `refresh_family_revoked:{uid}:{family}` を設定し、`SMEMBERS user_refresh:{uid}` を走査して `family_id` 一致の有効キーを削除。使用済み tombstoneはTTLで失効 |
| `revoke_all_refresh_tokens` | `user_id: UUID` | `int` | ユーザーの全リフレッシュトークンを削除 |

### 5.3 その他

| 関数 | 引数 | 戻り値 | 処理概要 |
|------|------|--------|----------|
| `save_oauth_state` | `state: str`, `redirect_to: str`, `code_verifier: str`, `nonce: str`, `ttl: int` | `None` | `SETEX oauth_state:{state}` |
| `consume_oauth_state` | `state: str` | `OAuthStateData \| None` | `GETDEL oauth_state:{state}`（ワンタイム消費） |
| `save_oauth_handoff` | `code: str`, `user_id: UUID`, `redirect_to: str`, `ttl: int` | `None` | `SETEX oauth_handoff:{code}` |
| `consume_oauth_handoff` | `code: str` | `OAuthHandoffData \| None` | `GETDEL oauth_handoff:{code}`（ワンタイム消費） |
| `save_password_reset_token` | `token: str`, `user_id: UUID`, `ttl: int` | `None` | `SETEX pwreset:{sha256(token)}` |
| `consume_password_reset_token` | `token: str` | `UUID \| None` | `GETDEL pwreset:{hash}` → user_id を返す |
| `replace_email_verify_token` | `token: str`, `user_id: UUID`, `ttl: int` | `None` | Luaまたは同一トランザクション相当の処理で旧 `emailverify:{old_hash}` を削除し、新tokenと `emailverify_current:{uid}` を登録 |
| `consume_email_verify_token` | `token: str` | `UUID \| None` | `GETDEL emailverify:{hash}` → user_id を返す（ワンタイム消費） |
| `mark_email_verify_sent` | `user_id: UUID`, `interval: int` | `bool` | `SET emailverify_sent:{uid} NX EX interval`。`False` なら再送間隔内のため送信しない |
| `incr_login_failure` | `identifier: str`, `client_ip: str`, `window: int` | `int`（現在の失敗回数） | lower/trimした識別子と確定済みIPからキーを作り、`INCR` → 初回のみ `EXPIRE` |
| `reset_login_failure` | `identifier: str`, `client_ip: str` | `None` | 同じキーの `DEL` |
| `ping` | なし | `bool` | ヘルスチェック（`/health` から使用） |

### 5.4 関数相関図

```mermaid
flowchart LR
    subgraph strategy["認証Strategy"]
        SESS["SessionAuthStrategy"]
        JWTS["JwtAuthStrategy"]
    end
    subgraph service
        AS["auth_service"]
        US["user_service"]
    end
    subgraph store["redis_store"]
        F1["create_session / get_session<br/>touch_session / delete_session"]
        F2["store_refresh_token / get_refresh_token<br/>rotate_refresh_token / revoke_*"]
        F3["save/consume_oauth_state"]
        F4["save/consume_password_reset_token"]
        F5["incr/reset_login_failure"]
        F6["delete_all_sessions<br/>revoke_all_refresh_tokens"]
    end

    SESS --> F1
    JWTS --> F2
    AS --> F3
    AS --> F4
    AS --> F5
    US --> F6
```

## 6. 障害・運用時の挙動

| ケース | 挙動 | 対応 |
|--------|------|------|
| Redis 再起動 | 全キー消失 → 全ユーザーがログアウト状態。API は 401 を返す | フロントは 401 を検知してログイン画面へ遷移。要件書で許容済み |
| Redis 接続不能 | 認証判定ができないため、認証必須APIは **503 SERVICE_UNAVAILABLE** を返す（fail-close） | `/health` に Redis 接続状態を含める |
| メモリ枯渇 | `maxmemory-policy` は **`noeviction`** とする | セッションが勝手に消えるのを防ぐため。LRU等でのeviction は採用しない |
| TTL満了直後のアクセス | `GET` が nil → 401 `SESSION_EXPIRED` / `TOKEN_EXPIRED` | フロントは再ログインへ誘導 |
| 同一ユーザーの多重ログイン | 許容（`user_sessions` に複数 session_id が並ぶ） | 端末ごとにログアウト可能 |

> `user_sessions` / `user_refresh` は有効キー集合の管理用であり、追加・延長・削除を必ず同一パイプライン（またはLua）で行う。TTLが切れた個別キーは集合から自動削除されないため、全件失効処理では存在確認を行い、最後に集合を削除する。

## 7. テスト方針

| 区分 | 方針 |
|------|------|
| 単体テスト | `fakeredis` を用い、TTL・失効ロジックを検証 |
| 結合テスト | 実 Redis コンテナ（CI では GitHub Actions の `services`）に接続し、`REDIS_TEST_DB` を使用 |
| TTL検証 | TTL秒を短く上書き（例：1秒）した設定でテストし、`asyncio.sleep` 後に失効を確認 |
| 競合テスト | 同一refresh tokenで同時に2回rotateし、成功が1回だけであること、2回目でfamily失効markerが設定されることを確認 |
| 集合整合性 | session/refreshの作成・touch・削除後に個別キーとユーザー集合のTTL/内容が整合することを確認 |
| 後片付け | テストごとに `FLUSHDB`（テスト用DB番号に限定して実行） |
| 網羅できない範囲 | Redis 自身の障害（プロセスダウン中の挙動）は自動テストでは再現せず、手動確認とする |
