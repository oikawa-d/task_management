# POST /api/projects（プロジェクト作成）

## 0. 関連ドキュメント

| ドキュメント | 内容 |
|--------------|------|
| [../../../basic_design/04_api.md](../../../basic_design/04_api.md) | §2.3 プロジェクトAPI一覧、§3.2 スキーマ（`POST /projects`）、§7.2 サービス層関数一覧 |
| [../../../basic_design/01_database.md](../../../basic_design/01_database.md) | §3.3 projects、§3.4 project_members、§4.3 プロジェクト作成時のデータ生成 |
| [../../../basic_design/03_auth.md](../../../basic_design/03_auth.md) | §9.2 `core/deps.py`（`get_current_user`）、§8 CSRF対策 |
| [./01_get_projects.md](./01_get_projects.md) | 作成後に一覧へ反映されるAPI |
| [../screen/06_dashboard.md](../../screen/06_dashboard.md) | 本APIを呼び出す画面（新規作成モーダル） |

## 1. 概要

| 項目 | 内容 |
|------|------|
| エンドポイント | `POST /api/projects` |
| 目的 | 新規プロジェクトを作成し、作成者をオーナー兼メンバーとして登録する |
| 認証 | 必要（session Cookie または `Authorization: Bearer`） |
| 認可 | member（ログイン済みの全ユーザーが作成可能。admin可） |
| CSRF検証 | 必要（session モードの更新系）。jwtモードは `Authorization` ヘッダのため通常不要 |
| Origin検証 | 必要（Cookieを利用する更新系リクエストのため） |
| AUTH_MODE差異 | session: `X-CSRF-Token` 検証あり／jwt: ヘッダ方式のためCSRF検証なし。作成処理自体に差異なし |
| 冪等性 | なし（同名でも複数作成可能。冪等キーは提供しない） |
| レート制限 | 対象外 |
| トランザクション境界 | `CALL sp_create_project(...)` 1回を1業務トランザクションとして実行し、projectとowner membershipを一体でcommit/rollback |

## 2. 入出力仕様

### 2.1 リクエスト

**ボディ（`application/json`）**

| 名前 | 型 | 必須 | 制約 | 説明 |
|------|----|------|------|------|
| name | string | ○ | 1〜100文字 | プロジェクト名 |
| description | string \| null | 任意 | 上限なし（`TEXT`）。省略時 `null` | 説明 |
| start_at | string(datetime) \| null | 任意 | ISO 8601（`TIMESTAMPTZ`として保存、UTC）。省略時 `null` | プロジェクト開始日時 |
| end_at | string(datetime) \| null | 任意 | ISO 8601（`TIMESTAMPTZ`として保存、UTC）。省略時 `null` | プロジェクト終了日時 |

`start_at` と `end_at` が両方とも指定された場合、`end_at >= start_at` を満たさなければ `422 VALIDATION_ERROR` とする（片方のみ指定、または両方 `null`/省略の場合は検証対象外）。

パスパラメータ／クエリパラメータ：なし。ヘッダ：`X-CSRF-Token`（sessionモードの更新系で必須）。

### 2.2 レスポンス

**`201 Created`**

```json
{
  "id": "3f1c2a10-...",
  "name": "Cerberus開発",
  "description": "学習用タスク管理システムの開発",
  "owner": { "id": "1a2b...", "username": "taro", "display_name": "山田 太郎" },
  "member_count": 1,
  "task_counts": { "todo": 0, "in_progress": 0, "done": 0 },
  "is_owner": true,
  "is_active": true,
  "start_at": null,
  "end_at": null,
  "created_at": "2026-09-03T04:05:06Z"
}
```

| フィールド | 型 | NULL | 説明 |
|-----------|----|----|------|
| id | string(uuid) | 不可 | 作成されたプロジェクトID |
| name | string | 不可 | プロジェクト名 |
| description | string | 可 | 説明 |
| owner | object | 不可 | 作成者自身（`current_user`） |
| member_count | integer | 不可 | 常に `1`（作成直後はオーナーのみ） |
| task_counts | object | 不可 | 常に全status `0` |
| is_owner | boolean | 不可 | 常に `true` |
| is_active | boolean | 不可 | 常に `true`（作成直後は有効） |
| start_at | string(datetime) | 可 | リクエストで指定した値、未指定時 `null` |
| end_at | string(datetime) | 可 | リクエストで指定した値、未指定時 `null` |
| created_at | string(datetime) | 不可 | ISO 8601 UTC |

`Set-Cookie` なし。共通ヘッダ `X-Request-ID` を全レスポンスに付与する。`Location` ヘッダは付与しない（本設計ではボディのみで完結させる）。

## 3. エラー仕様

| HTTP | code | 発生条件 | メッセージ | 備考 |
|------|------|----------|------------|------|
| 401 | `UNAUTHENTICATED` / `SESSION_EXPIRED` / `TOKEN_EXPIRED` / `TOKEN_INVALID` | 認証情報なし・無効 | 認証が必要です | `deps.get_current_user` |
| 403 | `USER_INACTIVE` | `is_active=false` | アカウントが無効化されています | |
| 403 | `CSRF_INVALID` | sessionモードでCSRFヘッダ／Origin不一致 | CSRFトークンが不正です | `deps.verify_origin` / `verify_csrf` |
| 422 | `VALIDATION_ERROR` | `name` 未指定・101文字以上、または `start_at`/`end_at` 両方指定時に `end_at < start_at` | 入力内容に誤りがあります | `details` にフィールド情報 |
| 503 | `SERVICE_UNAVAILABLE` | PostgreSQL 接続不能 | しばらくしてから再度お試しください | fail-close |

`basic_design/04_api.md` §4.2 のエラーコード体系から逸脱しない。

## 4. 処理シーケンス

```mermaid
sequenceDiagram
    autonumber
    participant FE as "React SPA"
    participant R as "projects_router"
    participant D as "deps（認証/CSRF）"
    participant S as "project_service"
    participant RP as "project_repository"
    participant PG as "PostgreSQL"

    FE->>R: POST /api/projects {name, description, start_at?, end_at?}
    R->>D: verify_origin / verify_csrf（sessionモードのみ実質検証）
    D-->>R: OK
    R->>D: get_current_user
    D-->>R: CurrentUser
    R->>R: pydanticでリクエストボディを検証（end_at>=start_atを含む）
    R->>S: create_project(user, payload)
    S->>PG: BEGIN
    S->>RP: sp_create_project(name, description, start_at, end_at, owner_id=user.id)
    RP->>PG: "SP/FN内部処理（正式呼び出しは§9.1参照）"
    PG-->>RP: project行
    RP-->>S: Project
    S->>RP: sp_create_project(project_id, user_id=user.id, invited_by=NULL)
    RP->>PG: "SP/FN内部処理（正式呼び出しは§9.1参照）"
    PG-->>RP: OK
    S->>PG: "SP/FN内部処理（正式呼び出しは§9.1参照）"
    alt INSERTのいずれかが失敗
        S->>PG: ROLLBACK
        S-->>R: InternalError
        R-->>FE: 500 INTERNAL_ERROR
    end
    S-->>R: ProjectSummary（member_count=1, task_counts=全0, is_owner=true）
    R-->>FE: 201 {project}
```

## 5. 処理フロー・分岐

```mermaid
flowchart TB
    A["リクエスト受信"] --> B["verify_origin"]
    B -->|"Origin不一致"| B1["403 CSRF_INVALID"]
    B -->|"OK"| C["session時のみ verify_csrf"]
    C -->|"CSRFヘッダ不一致"| C1["403 CSRF_INVALID"]
    C -->|"OK"| D["get_current_user"]
    D -->|"未認証"| D1["401 UNAUTHENTICATED系"]
    D -->|"is_active=false"| D2["403 USER_INACTIVE"]
    D -->|"OK"| E["pydanticでname/description/start_at/end_atを検証（end_at>=start_atを含む）"]
    E -->|"制約外"| E1["422 VALIDATION_ERROR"]
    E -->|"OK"| F["BEGIN"]
    F --> G["INSERT projects (owner_id=current_user.id, is_active=true, start_at, end_at)"]
    G --> H["INSERT project_members (project_id, user_id=current_user.id)"]
    H --> I["COMMIT"]
    I --> J["201 {project}"]
    G -.->|"失敗"| K["ROLLBACK → 500 INTERNAL_ERROR"]
    H -.->|"失敗"| K
```

## 6. 関数詳細

### 6.1 `api/routers/projects_router.py :: create_project`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def create_project(payload: ProjectCreateRequest, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db), _: None = Depends(verify_csrf)) -> ProjectSummaryResponse`（`payload` は `name`, `description`, `start_at`, `end_at` を保持） |
| 引数 | `payload`: リクエストボディ（pydantic検証済み） / `user`: 認証済みユーザー / `db`: DBセッション |
| 戻り値 | `ProjectSummaryResponse`（201） |
| 送出例外 | `CsrfInvalidError`（403）を `verify_csrf` 依存関係が送出 |
| 処理内容 | 1. `verify_origin` / `verify_csrf`（session時のみ実質検証）を依存関係として実行 2. `project_service.create_project` を呼び出す 3. 戻り値をそのまま201で返す |
| 副作用 | なし（副作用はservice層に委譲） |

### 6.2 `service/project_service.py :: create_project`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def create_project(user: CurrentUser, payload: ProjectCreateRequest, db: AsyncSession) -> ProjectSummary` |
| 引数 | `user`: 作成者 / `payload`: `name`, `description`, `start_at`, `end_at` / `db`: DBセッション |
| 戻り値 | `ProjectSummary`（`member_count=1`, `task_counts`全0, `is_owner=True`, `is_active=True` を固定値として組み立てる） |
| 送出例外 | `ValidationError`（`end_at < start_at`）→422、`InternalError`（INSERT失敗）→500、`ServiceUnavailableError`（DB接続不能）→503 |
| 処理内容 | 1. 入力形式をpydanticで検証し、API側で`project_id`を生成 2. repositoryが `CALL sp_create_project(project_id, user.id, name, description, start_at, end_at)` を1回呼ぶ 3. 成功後に `SELECT fn_get_project(project_id)` で応答を取得 4. SQLSTATE P0009等はAPIのAppErrorへ変換し、SP失敗時は全体をrollback |
| 副作用 | SP内部で `projects` とownerの `project_members` を更新 |

### 6.3 `repository/project_repository.py :: sp_create_project`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def sp_create_project(db: AsyncSession, project_id: UUID, owner_id: UUID, name: str, description: str \| None, start_at: datetime \| None, end_at: datetime \| None) -> None` |
| 引数 | 上記の通り |
| 戻り値 | なし。`project_id` は呼び出し元が生成済みの値を使用する |
| 送出例外 | SQLSTATE `P0009`（期間不正）等。APIの対応表でAppErrorへ変換 |
| 処理内容 | `CALL sp_create_project(:project_id, :owner_id, :name, :description, :start_at, :end_at)` のみを発行する。DB更新本体とowner登録はSP内部 |
| 副作用 | SP内のDB更新。repositoryは直接CRUDを持たない |

## 7. 関数相関図

```mermaid
flowchart LR
    R["projects_router.create_project"] --> D1["deps.verify_origin"]
    R --> D2["deps.verify_csrf"]
    R --> S["project_service.create_project"]
    S --> RP["repository.sp_create_project"]
    RP --> SP["CALL sp_create_project"]
    SP --> FN["SELECT fn_get_project"]
```

## 8. データ遷移図

```mermaid
flowchart LR
    A["POST /api/projects"] --> B["CALL sp_create_project"]
    B --> C["SP内部: project + owner membership"]
    C --> D["COMMIT（1業務トランザクション）"]
    E --> F["201 Created"]
    C -.->|"失敗"| G["ROLLBACK / 500 INTERNAL_ERROR"]
    D -.->|"失敗"| G
```

## 9. SP/FNデータアクセス一覧

### 9.1 正式なDBアクセス契約

本APIのrepositoryは、次のSP/FN呼び出しとDTO写像だけを行う。

| 種別 | 契約 | 説明 |
|------|------|------|
| create_project | `sp_create_project(p_project_id, p_owner_id, p_name, p_description, p_start_at, p_end_at)` | API生成IDでsp_create_projectを呼び出し、fn_get_projectの結果をレスポンスへ写像する |

repositoryはDBテーブルへ直結せず、SP/FN契約だけを呼び出す。 直下の従来のテーブルI/O表はSP/FN内部SQLの補足であり、repositoryの発行契約ではない。更新系の整合性制御、version検証、advisory lock、通知、SQLSTATE P0xxxはSP/FN層の責務である。存在・所属の事実判定はFNの空集合/falseを受け、404/403への変換はAPI層が行う。

**PostgreSQL**

| テーブル | 操作 | 条件・TTL | 備考 |
|----------|------|-----------|------|
| projects | INSERT | `owner_id = current_user.id`、`is_active`はDEFAULT `true`、`start_at`/`end_at`は指定値または`null` | トランザクション内。`ck_projects_period` CHECK制約あり |
| project_members | INSERT | `project_id`, `user_id = owner_id`, `invited_by = NULL` | 同一トランザクション。所属判定を一箇所に集約するため作成時に自分自身も登録する |

**Redis**

| キー | 操作 | TTL | 備考 |
|------|------|-----|------|
| `session:{sid}`（sessionモードのみ） | GET | `SESSION_TTL_SECONDS` | `deps.get_current_user` の認証確認 |
| `csrf:{sid}`（sessionモードのみ） | GET | `SESSION_TTL_SECONDS` | `deps.verify_csrf` によるCSRFトークン照合 |

## 10. バリデーション規則

| pydanticスキーマ | フィールド | 制約 | フロント（zod）との整合 |
|-------------------|-----------|------|--------------------------|
| `ProjectCreateRequest` | name | `str, min_length=1, max_length=100` | `zod.string().min(1).max(100)` |
| `ProjectCreateRequest` | description | `str \| None`, 省略時 `None` | `zod.string().nullable().optional()` |
| `ProjectCreateRequest` | start_at | `datetime \| None`, 省略時 `None` | `zod.string().datetime().nullable().optional()` |
| `ProjectCreateRequest` | end_at | `datetime \| None`, 省略時 `None` | `zod.string().datetime().nullable().optional()` |
| `ProjectCreateRequest` | （モデルバリデータ） | `start_at`と`end_at`が両方とも値を持つ場合、`end_at >= start_at`でなければ422 | `zod.object({...}).refine(end_at >= start_at when both present)` |

## 11. 非機能・セキュリティ考慮

| 観点 | 内容 |
|------|------|
| ログ出力 | 監査ログ対象（プロジェクト作成イベント）。`user_id`, `project_id`, `X-Request-ID` をINFOで構造化出力 |
| ユーザー列挙対策 | 該当なし |
| タイミング攻撃対策 | 該当なし |
| レート制限 | なし |
| CSRF/Origin | sessionモード：`verify_origin` + `verify_csrf` を必須依存関係とする。jwtモードはヘッダ認証のためCSRF検証対象外だが `verify_origin` は全モード共通で通す |
| fail-close方針 | INSERT失敗時は必ずロールバックし、部分的な作成（projectsのみ存在しproject_membersが無い状態）を発生させない |

## 12. テスト設計

| No | 区分 | ケース | 前提 | 期待結果 | pytest関数名案 |
|----|------|--------|------|----------|-----------------|
| 1 | 結合（実DB・実SP） | 正常作成でsp_create_project→sp_create_projectの順に呼ばれる | 実DB・実SPで検証 | 呼び出し順序とowner_id/user_idの整合を検証 | `test_create_project_calls_repository_in_order` |
| 2 | 単体 | sp_create_project失敗時にロールバックされる | `sp_create_project`がIntegrityErrorを送出するようモック | `rollback`が呼ばれ例外が再送出される | `test_create_project_rollback_on_member_insert_failure` |
| 3 | 結合 | 正常系でprojectsとproject_membersが同一トランザクションで作成される | 実PostgreSQL | 201、`project_members`に自分自身が1行存在 | `test_create_project_success` |
| 4 | 結合 | nameが101文字で422 | リクエストボディ不正 | `422 VALIDATION_ERROR` | `test_create_project_name_too_long` |
| 5 | 結合 | sessionモードでCSRFヘッダ欠落時403 | `X-CSRF-Token`を送らない | `403 CSRF_INVALID` | `test_create_project_missing_csrf_session_mode` |
| 6 | 結合 | 未認証は401 | Cookie/Bearerなし | `401 UNAUTHENTICATED` | `test_create_project_unauthenticated` |
| 7 | 結合 | is_active=falseは403 | 無効化ユーザーでログイン試行済みトークンを使用 | `403 USER_INACTIVE` | `test_create_project_inactive_user` |
| 8 | 結合 | start_at/end_at省略時はnullで作成される | `start_at`/`end_at`を送らない | `201`、レスポンスの`start_at`/`end_at`が`null`、`is_active`が`true` | `test_create_project_without_period` |
| 9 | 結合 | start_at/end_atを両方指定して作成できる | `end_at >= start_at`を満たす値を送信 | `201`、レスポンスに指定値が反映される | `test_create_project_with_valid_period` |
| 10 | 結合 | end_at < start_atは422 | `end_at`が`start_at`より前の値 | `422 VALIDATION_ERROR` | `test_create_project_invalid_period_returns_422` |

`AUTH_MODE=session` / `jwt` の両方で No.3・No.6を実施する。No.5はsessionモード固有のためjwtモードでは対象外（jwtは`Authorization`ヘッダのみでCSRF検証を行わないため）とし、その理由を明記する。

## 13. 不明点・要検討事項

| 区分 | 内容 | 影響 |
|------|------|------|
| なし | | |
