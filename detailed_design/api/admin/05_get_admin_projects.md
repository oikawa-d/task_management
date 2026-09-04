# GET /api/admin/projects（全プロジェクト一覧取得）

## 0. 関連ドキュメント

| ドキュメント | 内容 |
|--------------|------|
| [../../../basic_design/04_api.md](../../../basic_design/04_api.md) | §2.3 `GET /projects`（admin 全件）、§2.5 管理者API一覧、§4.2 エラーコード体系、§5 認可マトリクス、§7.2 サービス層関数一覧 |
| [../../../basic_design/01_database.md](../../../basic_design/01_database.md) | §3.3 projects、§3.4 project_members、§3.5 tasks、§7 主要クエリ（Q-2） |
| [../../../basic_design/05_frontend.md](../../../basic_design/05_frontend.md) | §7.7 管理者ユーザー管理（プロジェクト一覧タブ） |
| [../projects/01_get_projects.md](../projects/01_get_projects.md) | `GET /projects`（admin時は全件返却）。本APIとの使い分けは1章参照 |
| [./01_get_admin_users.md](./01_get_admin_users.md) | 同じ管理者画面から呼ばれる姉妹API（クエリ設計・ページング規約を統一） |
| [./06_delete_admin_project.md](./06_delete_admin_project.md) | 本一覧の削除操作 |
| [../../screen/10_admin_users.md](../../screen/10_admin_users.md) | 本APIを呼び出す画面（管理者ユーザー管理画面・プロジェクト一覧タブ） |

## 1. 概要

| 項目 | 内容 |
|------|------|
| エンドポイント | `GET /api/admin/projects` |
| 目的 | 管理者が全プロジェクトをページング・検索付きで一覧参照する（管理者画面のプロジェクト一覧タブ専用） |
| 認証 | 必要（session Cookie または `Authorization: Bearer`） |
| 認可 | admin のみ |
| CSRF検証 | 不要（参照系 GET） |
| Origin検証 | 不要（Cookie発行・更新系ではないため） |
| AUTH_MODE差異 | 差異なし（`deps.get_current_user` が方式差を吸収する） |
| 冪等性 | あり（GET） |
| レート制限 | 対象外 |
| トランザクション境界 | 単一の読み取りトランザクション（更新なし） |

`GET /projects` との使い分けは以下のとおりである。

| 観点 | `GET /projects`（`04_get_project...` 参照）※admin利用時 | `GET /admin/projects`（本API） |
|------|-----------------------------------------------------|--------------------------------|
| 主用途 | ダッシュボード画面（`screen/06_dashboard.md`）。adminも自分用ダッシュボードとして全件を閲覧できる副次効果を持つに過ぎない | 管理者ユーザー管理画面のプロジェクト一覧タブ（`screen/10_admin_users.md`）専用 |
| 認可 | member（自分の所属分のみ）／admin（全件） | admin固定。member/オーナーは403（一般ユーザーには存在自体を見せない） |
| `is_owner` | あり（自分がオーナーかどうかをダッシュボードで表示するため） | なし（管理者視点の一覧であり「自分のプロジェクトか」は無関係） |
| 検索 (`q`) | なし | あり（プロジェクト名の部分一致） |
| 削除操作との連携 | なし（削除は `DELETE /projects/{id}` でオーナー/admin向け） | あり（`DELETE /admin/projects/{project_id}` と対になる管理者専用の削除導線） |
| 内部実装 | `project_repository.count_all` / `list_all`（`q=None`固定で呼び出し） | 同じ `count_all` / `list_all` を `q` 付きで呼び出す（クエリ実装を共有し重複実装しない） |

## 2. 入出力仕様

### 2.1 リクエスト

**クエリパラメータ**

| 名前 | 型 | 必須 | 制約 | 説明 |
|------|----|------|------|------|
| page | integer | 任意 | 1以上。既定 `1` | ページ番号 |
| per_page | integer | 任意 | 1〜100。既定 `20`（`PAGINATION_DEFAULT_PER_PAGE` / `PAGINATION_MAX_PER_PAGE`） | 1ページあたり件数 |
| q | string | 任意 | 100文字以内 | プロジェクト名 (`projects.name`) の部分一致検索（大文字小文字区別なし） |

パスパラメータ／ヘッダ（認証ヘッダ・Cookieを除く）／ボディ：なし。

### 2.2 レスポンス

**`200 OK`**

```json
{
  "items": [
    {
      "id": "3f1c2a10-...",
      "name": "Cerberus開発",
      "description": "学習用タスク管理システムの開発",
      "owner": { "id": "1a2b...", "username": "taro", "display_name": "山田 太郎" },
      "member_count": 3,
      "task_counts": { "todo": 4, "in_progress": 2, "done": 7 },
      "created_at": "2026-09-01T00:00:00Z"
    }
  ],
  "meta": { "page": 1, "per_page": 20, "total": 1, "total_pages": 1 }
}
```

| フィールド | 型 | NULL | 説明 |
|-----------|----|----|------|
| items[].id | string(uuid) | 不可 | プロジェクトID |
| items[].name | string | 不可 | プロジェクト名 |
| items[].description | string | 可 | 説明 |
| items[].owner.id / username | string | 不可 | オーナーの識別情報 |
| items[].owner.display_name | string | 不可 | `last_name + ' ' + first_name`（未設定項目があれば `username` を代替表示。[01_get_projects.md](../projects/01_get_projects.md) と同一規則） |
| items[].member_count | integer | 不可 | `project_members` の件数 |
| items[].task_counts.todo / in_progress / done | integer | 不可 | status別タスク件数。0件のstatusも `0` を返す |
| items[].created_at | string(datetime) | 不可 | ISO 8601 UTC |
| meta.page / per_page / total / total_pages | integer | 不可 | ページング情報 |

`is_owner` フィールドは含めない（1章参照）。`Set-Cookie` なし。共通ヘッダ `X-Request-ID` を全レスポンスに付与する。

## 3. エラー仕様

| HTTP | code | 発生条件 | メッセージ | 備考 |
|------|------|----------|------------|------|
| 401 | `UNAUTHENTICATED` / `SESSION_EXPIRED` / `TOKEN_EXPIRED` / `TOKEN_INVALID` | 認証情報なし・失効・不正 | 認証情報が無効です | `deps.get_current_user` |
| 403 | `USER_INACTIVE` | `users.is_active=false` | アカウントが無効化されています | |
| 403 | `FORBIDDEN` | `role != admin` | 権限がありません | `deps.require_admin` |
| 422 | `VALIDATION_ERROR` | `page` / `per_page` / `q` が制約外 | 入力内容に誤りがあります | `details` にフィールド情報 |
| 503 | `SERVICE_UNAVAILABLE` | PostgreSQL / Redis 接続不能 | しばらくしてから再度お試しください | fail-close |

`basic_design/04_api.md` §4.2 のエラーコード体系から逸脱しない。

## 4. 処理シーケンス

```mermaid
sequenceDiagram
    autonumber
    participant FE as "React SPA"
    participant R as "admin_router"
    participant D as "deps.require_admin"
    participant S as "admin_project_service"
    participant RP as "project_repository"
    participant PG as "PostgreSQL"

    FE->>R: GET /api/admin/projects?page=1&per_page=20&q=Cerberus
    R->>D: 認証 + admin確認
    D-->>R: CurrentUser(role=admin)
    R->>S: list_projects(query, page, per_page)
    S->>RP: count_all(q)
    RP->>PG: "SELECT COUNT(*) FROM projects WHERE lower(name) LIKE lower(:q)||'%'"
    PG-->>RP: total
    S->>RP: list_all(q, page, per_page)
    RP->>PG: "SELECT projects.* FROM projects WHERE ... ORDER BY created_at DESC LIMIT/OFFSET"
    PG-->>RP: project行（owner を selectinload 済み）
    RP-->>S: Project一覧
    S->>RP: aggregate_member_counts(project_ids)
    RP->>PG: "SELECT project_id, COUNT(*) FROM project_members WHERE project_id = ANY(:ids) GROUP BY project_id"
    S->>RP: aggregate_task_counts(project_ids)
    RP->>PG: "SELECT project_id, status, COUNT(*) FROM tasks WHERE project_id = ANY(:ids) GROUP BY project_id, status"
    S->>S: 集計結果をAdminProjectSummaryへマージ
    S-->>R: Page[AdminProjectSummary]
    R-->>FE: 200 {items, meta}
    alt DB/Redis 不通
        RP-->>S: OperationalError / RedisError
        S-->>R: ServiceUnavailableError
        R-->>FE: 503 SERVICE_UNAVAILABLE
    end
```

## 5. 処理フロー・分岐

```mermaid
flowchart TB
    A["リクエスト受信"] --> B["pydanticでpage/per_page/qを検証"]
    B -->|"制約外"| B1["422 VALIDATION_ERROR"]
    B -->|"OK"| C["deps.get_current_user"]
    C -->|"認証情報なし/不正"| C1["401 UNAUTHENTICATED / SESSION_EXPIRED / TOKEN_EXPIRED"]
    C -->|"is_active=false"| C2["403 USER_INACTIVE"]
    C -->|"OK"| E["deps.require_admin"]
    E -->|"role != admin"| E1["403 FORBIDDEN"]
    E -->|"OK"| F["project_repository.count_all(q)"]
    F --> G["project_repository.list_all(q)"]
    G --> H["project_idsで member_count / task_counts をバッチ集計"]
    H --> I["AdminProjectSummaryへマージ"]
    I --> J["200 {items, meta}"]
    F -.->|"DB接続不能"| K["503 SERVICE_UNAVAILABLE"]
```

## 6. 関数詳細

### 6.1 `api/routers/admin_router.py :: list_admin_projects`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def list_admin_projects(query: AdminProjectListQuery = Depends(), user: CurrentUser = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> AdminProjectListResponse` |
| 引数 | `query`: `page`/`per_page`/`q`（クエリ） / `user`: admin確認済みユーザー / `db`: DBセッション |
| 戻り値 | `AdminProjectListResponse`（`items`, `meta`） |
| 送出例外 | なし（サービス層の例外を `AppError` としてそのまま伝播） |
| 処理内容 | 1. `require_admin` により403判定を完了させる 2. `admin_project_service.list_projects` を呼び出す 3. 戻り値をそのままレスポンスとして返す |
| 副作用 | なし |

### 6.2 `service/admin_project_service.py :: list_projects`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def list_projects(query: AdminProjectListQuery, db: AsyncSession) -> Page[AdminProjectSummary]` |
| 引数 | `query`: 検索・ページング条件 / `db`: DBセッション |
| 戻り値 | `Page[AdminProjectSummary]`（`items: list[AdminProjectSummary]`, `total: int`） |
| 送出例外 | `ServiceUnavailableError`（PostgreSQL接続不能時）→503 |
| 処理内容 | 1. `project_repository.count_all(q)` で総件数取得 2. `project_repository.list_all(q, page, per_page)` で該当ページの行を取得（owner は `selectinload`） 3. 取得した `project_ids` で `aggregate_member_counts` / `aggregate_task_counts` をそれぞれ1回ずつ呼び出す 4. Python側で `member_count` / `task_counts`（0補完）をマージし `AdminProjectSummary` を組み立てる（`is_owner` は算出しない） |
| 副作用 | なし（読み取りのみ） |

### 6.3 `repository/project_repository.py :: count_all` / `list_all`（`q` 引数を追加）

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def count_all(db: AsyncSession, q: str \| None = None) -> int` ／ `async def list_all(db: AsyncSession, q: str \| None = None, page: int = 1, per_page: int = 20) -> list[Project]` |
| 引数 | `q`: プロジェクト名の部分一致条件（`None` なら全件対象） / `page`, `per_page`: ページング |
| 戻り値 | 件数 ／ `owner` を eager load 済みの `Project` エンティティのリスト |
| 送出例外 | `OperationalError`（DB不通） |
| 処理内容 | 1. [01_get_projects.md §6.3](../projects/01_get_projects.md) で定義済みの `list_all`（admin向け全件取得）に `q` 引数を追加する形で拡張し、`GET /projects` のadmin分岐と本APIで実装を共有する 2. `q` 指定時は `lower(name) LIKE lower(:q)||'%'`（前方一致）を `WHERE` に追加 3. `ORDER BY created_at DESC` 4. `OFFSET (page-1)*per_page LIMIT per_page`（`count_all` はページングなし） |
| 副作用 | なし |

### 6.4 `repository/project_repository.py :: aggregate_member_counts` / `aggregate_task_counts`

[01_get_projects.md §6.4](../projects/01_get_projects.md) と同一の既存関数をそのまま再利用する（実装の重複を避ける）。

## 7. 関数相関図

```mermaid
flowchart LR
    R["admin_router.list_admin_projects"] --> S["admin_project_service.list_projects"]
    S --> RP1["project_repository.count_all"]
    S --> RP2["project_repository.list_all"]
    S --> RP3["project_repository.aggregate_member_counts"]
    S --> RP4["project_repository.aggregate_task_counts"]
    RP1 --> M["models.Project"]
    RP2 --> M
    RP2 --> MO["models.User(owner)"]
    RP3 --> MPM["models.ProjectMember"]
    RP4 --> MT["models.Task"]
```

## 8. データ遷移図

読み取りのみで状態遷移なし。

```mermaid
flowchart LR
    subgraph PG["PostgreSQL（参照範囲）"]
        T1["projects"]
        T2["project_members"]
        T3["tasks"]
        T4["users（owner）"]
    end
    S["admin_project_service.list_projects"] -->|"SELECT / COUNT"| T1
    S -->|"SELECT（件数集計）"| T2
    S -->|"SELECT（status別集計）"| T3
    S -->|"SELECT（owner表示名）"| T4
```

## 9. データアクセス一覧

**PostgreSQL**

| テーブル | 操作 | 条件 | 備考 |
|----------|------|------|------|
| projects | SELECT | `q` 指定時は `name` 部分一致、なければ全件 | `ORDER BY created_at DESC LIMIT/OFFSET` |
| projects | SELECT COUNT | 同上 | `meta.total` 算出用 |
| users | SELECT | `projects.owner_id` に対する eager load | owner表示用、N+1回避 |
| project_members | SELECT + GROUP BY | `project_id = ANY(:ids)` | `member_count` 集計 |
| tasks | SELECT + GROUP BY | `project_id = ANY(:ids)` | `task_counts` 集計 |

**Redis**

| キー | 操作 | TTL | 備考 |
|------|------|-----|------|
| `session:{sid}`（sessionモードのみ） | GET | `SESSION_TTL_SECONDS` | `deps.get_current_user` の認証確認のみで本APIの業務データではない |

## 10. バリデーション規則

| pydanticスキーマ | フィールド | 制約 | フロント（zod）との整合 |
|-------------------|-----------|------|--------------------------|
| `AdminProjectListQuery` | page | `int, ge=1`, 既定1 | `zod.number().int().min(1)` |
| `AdminProjectListQuery` | per_page | `int, ge=1, le=100`, 既定 `PAGINATION_DEFAULT_PER_PAGE` | `zod.number().int().min(1).max(100)` |
| `AdminProjectListQuery` | q | `str \| None, max_length=100` | `zod.string().max(100).optional()` |

## 11. 非機能・セキュリティ考慮

| 観点 | 内容 |
|------|------|
| ログ出力 | 監査ログ対象外（参照系）。アクセスログに `user_id`(admin), `q`, `page`, `per_page`, `X-Request-ID` を構造化出力 |
| ユーザー列挙対策 | admin専用APIのため対象外（一般ユーザーからは403で内容を隠蔽） |
| タイミング攻撃対策 | 該当なし |
| レート制限 | なし |
| fail-close方針 | PostgreSQL接続不能時は `503 SERVICE_UNAVAILABLE` |
| N+1対策 | owner は `selectinload` で1往復、`member_count`/`task_counts` はプロジェクト件数に依らず定数回のクエリ（バッチ集計）に抑える（[01_get_projects.md](../projects/01_get_projects.md) と同じ方針） |

## 12. テスト設計

| No | 区分 | ケース | 前提 | 期待結果 | pytest関数名案 |
|----|------|--------|------|----------|-----------------|
| 1 | 単体 | 一般ユーザーはアクセス不可 | `role=member` のCurrentUser | `403 FORBIDDEN`、リポジトリ未呼び出し | `test_list_admin_projects_forbidden_for_member` |
| 2 | 単体 | q指定時に名称部分一致条件が組み立てられる | repositoryをモック | 発行されたSQL条件に `name` のLIKE条件が含まれる | `test_list_admin_projects_query_builds_name_like` |
| 3 | 単体 | is_ownerフィールドが出力に含まれない | サービス層の戻り値スキーマを検証 | `AdminProjectSummary` に `is_owner` キーが存在しない | `test_list_admin_projects_response_has_no_is_owner` |
| 4 | 結合 | 検索条件なしで全プロジェクトが返る（他ユーザー所有分も含む） | 3ユーザーがそれぞれ所有するプロジェクトを作成 | `total=3` で全件返る | `test_list_admin_projects_returns_all_owners_projects` |
| 5 | 結合 | qによるプロジェクト名検索が機能する | `name="Cerberus開発"` を含む複数プロジェクト | `q=Cerberus` で該当プロジェクトのみ返る | `test_list_admin_projects_search_by_name` |
| 6 | 結合 | ページングが正しく機能する | プロジェクト25件を作成 | 1ページ目20件、`total=25`、`total_pages=2` | `test_list_admin_projects_pagination` |
| 7 | 結合 | member（オーナー含む）はアクセス不可 | 一般メンバー・オーナーのCurrentUserでGET | `403 FORBIDDEN` | `test_list_admin_projects_forbidden_for_owner_non_admin` |
| 8 | 結合 | 未認証は401 | Cookie/Bearerなし | `401 UNAUTHENTICATED` | `test_list_admin_projects_unauthenticated` |
| 9 | 結合 | N+1が発生しないことの確認 | プロジェクト10件、SQLAlchemyのクエリカウンタで検証 | 発行クエリ数が定数（プロジェクト件数に比例しない） | `test_list_admin_projects_query_count_constant` |

`AUTH_MODE=session` / `jwt` の両方で No.8（401判定経路の違い：`SESSION_EXPIRED` と `TOKEN_EXPIRED`）をパラメータ化して実施する。

## 13. 不明点・要検討事項

| 区分 | 内容 | 影響 |
|------|------|------|
| 要検討 | `q` によるプロジェクト名検索は基本設計に明記がなく、`GET /admin/users` の `q` 検索との一貫性を意図した本書での提案。基本設計側での明文化が望ましい |
| 要検討 | `project_repository.count_all` / `list_all` に `q` 引数を追加する変更は、既存の `GET /projects`（[01_get_projects.md](../projects/01_get_projects.md)）が呼び出す箇所にも影響するため、実装時は後方互換（`q=None` 既定）を厳守する必要がある |
