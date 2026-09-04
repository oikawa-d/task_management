# GET /api/tasks（横断的タスク一覧取得）

## 0. 関連ドキュメント

| ドキュメント | 内容 |
|--------------|------|
| [../../../basic_design/04_api.md](../../../basic_design/04_api.md) | §1 共通仕様、§2.4 エンドポイント一覧、§5 認可マトリクス |
| [../../../basic_design/01_database.md](../../../basic_design/01_database.md) | §3.5 tasks（`project_id` NULL許容、`is_active`） |
| [../../auth/05_rbac.md](../../auth/05_rbac.md) | `require_project_member` の判定、非所属404統一方針 |
| [../../database/06_table_tasks.md](../../database/06_table_tasks.md) | tasks テーブル詳細（`project_id` NULL許容化・`is_active`追加） |
| [./01_get_project_tasks.md](./01_get_project_tasks.md) | プロジェクト配下限定の一覧・カンバン取得API（本APIとの使い分け） |
| [./03_get_task.md](./03_get_task.md) | タスク1件詳細取得（同一の認可方針を流用） |
| [./11_post_tasks.md](./11_post_tasks.md) | 同一リソース群のフラット作成API |
| [../projects/01_get_projects.md](../projects/01_get_projects.md) | ページング・`include_inactive`の既存パターン（本APIも同様の方式を踏襲） |

## 1. 概要

| 項目 | 内容 |
|------|------|
| エンドポイント | `GET /api/tasks` |
| 目的 | ログインユーザーが参照可能な全タスクを、所属プロジェクトを横断して一覧する。プロジェクト未所属タスク（`project_id=NULL`）も対象に含む。`GET /api/projects/{project_id}/tasks`（[01](./01_get_project_tasks.md)）がカンバン描画用に単一プロジェクトの`status`別グルーピングを返すのに対し、本APIは複数プロジェクトを横断した単一のページング一覧を返す |
| 認証 | session モード：`cerberus_sid` Cookie ／ jwt モード：`Authorization: Bearer {access_token}` |
| 認可 | admin：全タスク（未所属タスクも含め無条件）。member：自分が所属する各プロジェクトの全タスク（`require_project_member`と同じ「メンバーなら誰でも閲覧可」の考え方を横断適用）＋自分が作成した未所属タスク（`project_id=NULL AND created_by=自分`）の合算 |
| CSRF検証 | 不要（参照系 GET） |
| Origin検証 | 不要 |
| AUTH_MODE差異 | 認証情報の解決方法のみ異なり、業務ロジックに差異なし |
| 冪等性 | あり（GET、副作用なし） |
| レート制限 | 対象外 |
| トランザクション境界 | 単一の読み取り専用SELECT（`AsyncSession` の暗黙トランザクション内で完結） |

## 2. 入出力仕様（全体の出入力）

### 2.1 リクエスト

**クエリパラメータ**

| 名前 | 型 | 必須 | 制約 | 説明 |
|------|----|----|------|------|
| page | integer | - | 1以上。既定 `1` | ページ番号 |
| per_page | integer | - | 1〜100。既定 `20`（`PAGINATION_DEFAULT_PER_PAGE` / `PAGINATION_MAX_PER_PAGE`） | 1ページあたり件数 |
| project_id | string | - | 省略可。UUID形式、または未所属タスクのみを指定する特別値 `"null"`（文字列リテラル） | 3種の状態を区別する：①省略＝認可範囲全体（所属プロジェクト全部＋自分の未所属タスク）②UUID指定＝そのプロジェクトのタスクのみに絞込（非所属なら404）③`"null"`指定＝未所属タスクのみに絞込。詳細は下記表 |
| status | string | - | `todo` / `in_progress` / `done` | 指定時はそのstatusのみに絞込 |
| include_inactive | boolean | - | 既定 `false` | `true` で `is_active=false`（論理削除済み）タスクも含める |
| sort | string | - | `created_at` / `due_at`。既定 `created_at` | ソートキー |
| order | string | - | `asc` / `desc`。既定 `desc` | ソート順 |

**`project_id` の絞込パターン（確定方針）**

| 指定 | 対象範囲 | 非所属・不正時の挙動 |
|------|----------|----------------------|
| 省略 | 認可範囲の全件（所属プロジェクトの全タスク ＋ 自分が作成した未所属タスク） | - |
| 有効なUUID | そのプロジェクトのタスクのみ | 非所属（かつ非admin）は404 `NOT_FOUND`（[01](./01_get_project_tasks.md)と同一方針。プロジェクトの存在有無を秘匿） |
| 文字列 `"null"` | 未所属タスクのみ。member/adminとも、未所属タスクの可視範囲規則（下記）がそのまま適用される | - |
| UUID・`"null"`のいずれでもない文字列 | - | 422 `VALIDATION_ERROR` |

**未所属タスク（`project_id=NULL`）の可視範囲**：admin は全件、member は `created_by=自分` の行のみ（[03_get_task.md](./03_get_task.md) §1と同一方針）。

パスパラメータ／ヘッダ（認証ヘッダ・Cookieを除く）／ボディ：なし。

### 2.2 レスポンス

**`200 OK`**

```json
{
  "items": [
    {
      "id": "b2e4...",
      "project_id": "3f1c2a10-...",
      "project_is_active": true,
      "title": "設計書をレビューする",
      "description": null,
      "status": "todo",
      "assignee": { "id": "9a1b...", "username": "taro", "display_name": "山田 太郎" },
      "created_by": { "id": "9a1b...", "username": "taro", "display_name": "山田 太郎" },
      "position": 0,
      "version": 1,
      "is_active": true,
      "due_at": null,
      "comment_count": 2,
      "created_at": "2026-09-01T00:00:00Z",
      "updated_at": "2026-09-01T00:00:00Z"
    }
  ],
  "meta": { "page": 1, "per_page": 20, "total": 1, "total_pages": 1 }
}
```

| フィールド | 型 | NULL可否 | 説明 |
|-----------|----|----------|------|
| items[].id | string(uuid) | 不可 | タスクID |
| items[].project_id | string(uuid) | 可 | 所属プロジェクトID。未所属タスクは `null` |
| items[].project_is_active | boolean | 可 | `projects.is_active`。`project_id` が `null` の場合は `null` |
| items[].title | string | 不可 | |
| items[].description | string | 可 | |
| items[].status | string | 不可 | `todo` / `in_progress` / `done` |
| items[].assignee | object | 可 | `{id, username, display_name}` |
| items[].created_by | object | 不可 | `{id, username, display_name}` |
| items[].position | integer | 不可 | 所属列内の並び順。未所属タスクは`project_id IS NULL`の仮想グループ内での位置（[11_post_tasks.md](./11_post_tasks.md) §6参照） |
| items[].version | integer | 不可 | 楽観ロック用 |
| items[].is_active | boolean | 不可 | `tasks.is_active` |
| items[].due_at | string(date-time) | 可 | ISO 8601 UTC |
| items[].comment_count | integer | 不可 | `task_comments` の件数 |
| items[].created_at / updated_at | string(datetime) | 不可 | ISO 8601 UTC |
| meta.page / per_page / total / total_pages | integer | 不可 | ページング情報 |

`Set-Cookie` の発行なし。`X-Request-ID` を全レスポンスに付与。

## 3. エラー仕様

| HTTP | code | 発生条件 | メッセージ | 備考 |
|------|------|----------|------------|------|
| 401 | `UNAUTHENTICATED` / `SESSION_EXPIRED` / `TOKEN_EXPIRED` / `TOKEN_INVALID` | 認証情報なし・無効 | 認証が必要です | |
| 403 | `USER_INACTIVE` | `is_active=false`（実行者） | アカウントが無効化されています | |
| 404 | `NOT_FOUND` | `project_id` に有効なUUIDを指定したが不存在または非所属member | プロジェクトが見つかりません | 存在有無を秘匿するため404で統一 |
| 422 | `VALIDATION_ERROR` | `page`/`per_page`/`status`/`sort`/`order`が制約外、`project_id`がUUIDでも`"null"`でもない | 入力内容に誤りがあります | |
| 503 | `SERVICE_UNAVAILABLE` | PostgreSQL接続不能 | 一時的にサービスを利用できません | fail-close |

## 4. 処理シーケンス

```mermaid
sequenceDiagram
    autonumber
    participant FE as "React SPA"
    participant R as "tasks_router"
    participant D as "deps: get_current_user"
    participant S as "task_service"
    participant PR as "project_repository"
    participant TR as "task_repository"
    participant PG as "PostgreSQL"

    FE->>R: "GET /api/tasks?project_id=...&page=1&per_page=20"
    R->>D: "認証（get_current_user）"
    D-->>R: "CurrentUser"
    R->>S: "list_tasks(user, filters)"
    alt "project_idが有効なUUID"
        S->>PR: "is_member(project_id, user.id)"
        PR->>PG: "SELECT project_members WHERE project_id AND user_id"
        alt "非所属 かつ 非admin"
            S-->>R: "NotFoundError"
            R-->>FE: "404 NOT_FOUND"
        end
    end
    S->>TR: "count(user, filters) / list(user, filters)"
    TR->>PG: "SELECT COUNT(*) / SELECT tasks<br/>WHERE (admin: 制約なし) OR<br/>(project_id IN 所属project_ids) OR<br/>(project_id IS NULL AND created_by=user.id)<br/>[AND project_idフィルタ] [AND status] [AND is_active=true]<br/>ORDER BY :sort :order LIMIT/OFFSET"
    PG-->>TR: "tasks行 + COUNT(task_comments)相関サブクエリ"
    TR->>PG: "selectinload(assignee) / selectinload(created_by) / selectinload(project) の追加SELECT"
    PG-->>TR: "users行 / projects行"
    TR-->>S: "list[TaskWithRelations], total"
    S-->>R: "Page[TaskSummary]"
    R-->>FE: "200 {items, meta}"
```

## 5. 処理フロー・分岐

```mermaid
flowchart TB
    A["リクエスト受信"] --> B{"クエリパラメータはpydantic検証OK?<br/>(project_idはUUID or 'null')"}
    B -->|"No"| E422["422 VALIDATION_ERROR"]
    B -->|"Yes"| C{"認証情報は有効?"}
    C -->|"No"| E401["401 UNAUTHENTICATED系"]
    C -->|"Yes"| D{"is_active?"}
    D -->|"No"| E403["403 USER_INACTIVE"]
    D -->|"Yes"| F{"project_idがUUID指定?"}
    F -->|"Yes"| G{"admin または<br/>project_membersに存在?"}
    G -->|"No"| E404["404 NOT_FOUND"]
    G -->|"Yes"| H["絞込条件を確定"]
    F -->|"No（省略 or 'null'）"| H
    H --> I["task_repository.list実行<br/>（認可範囲 ∩ project_idフィルタ ∩ statusフィルタ ∩ is_activeフィルタ）"]
    I --> J["200 {items, meta}"]
```

## 6. 関数詳細

### 6.1 `api/routers/tasks.py :: list_tasks`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def list_tasks(page: int = 1, per_page: int = 20, project_id: str \| None = None, status: TaskStatus \| None = None, include_inactive: bool = False, sort: Literal["created_at","due_at"] = "created_at", order: Literal["asc","desc"] = "desc", user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> TaskListResponse` |
| 引数 | 各クエリパラメータ（2.1節参照）／user: 認証済みユーザー／db: DBセッション |
| 戻り値 | `TaskListResponse`（`items`, `meta`） |
| 送出例外 | `ValidationError`（`project_id`がUUIDでも`"null"`でもない場合、422）、`NotFoundError`（`project_id`指定時の非所属、404） |
| 処理内容 | 1. `project_id` 文字列を `UUID \| Literal["unassigned"] \| None` に正規化（`"null"`は`"unassigned"`として扱う。それ以外の非UUID文字列は`ValidationError`）<br/>2. `task_service.list_tasks(user, page, per_page, project_id_filter, status, include_inactive, sort, order)` を呼び出す<br/>3. 結果をそのまま返す |
| 副作用 | なし |

### 6.2 `service/task_service.py :: list_tasks`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def list_tasks(user: CurrentUser, page: int, per_page: int, project_id_filter: UUID \| Literal["unassigned"] \| None, status: TaskStatus \| None, include_inactive: bool, sort: str, order: str) -> Page[TaskSummary]` |
| 引数 | 6.1と対応 |
| 戻り値 | `Page[TaskSummary]`（`items`, `total`） |
| 送出例外 | `NotFoundError`（`project_id_filter`がUUIDで非所属の場合） |
| 処理内容 | 1. `project_id_filter` がUUIDの場合、`user.role != 'admin'` なら `project_repository.is_member(project_id_filter, user.id)` を確認し、非所属なら `NotFoundError`<br/>2. `task_repository.count(user, ...)` と `task_repository.list(user, ...)` を呼び出す。認可範囲（admin=全件、member=所属project_ids＋自分が作成者の未所属タスク）はリポジトリ層のWHERE句に集約する（6.3参照）<br/>3. 取得した行を `TaskSummary`（`project_is_active`は`project`をeager loadした値、`project_id=NULL`なら`None`）に整形する |
| 副作用 | なし |

### 6.3 `repository/task_repository.py :: list`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def list(db: AsyncSession, user: CurrentUser, project_id_filter: UUID \| Literal["unassigned"] \| None, status: TaskStatus \| None, include_inactive: bool, sort: str, order: str, page: int, per_page: int) -> list[TaskWithRelations]` |
| 引数 | 6.2と対応 |
| 戻り値 | `assignee` / `created_by` / `project` をEager Loadした `Task` のリスト |
| 送出例外 | `OperationalError`（503へ変換） |
| 処理内容 | 1. 認可範囲のベース条件を構築：`user.role == 'admin'` なら条件なし（全件）。それ以外は `tasks.project_id IN (SELECT project_id FROM project_members WHERE user_id=:uid) OR (tasks.project_id IS NULL AND tasks.created_by=:uid)`<br/>2. `project_id_filter` がUUIDなら `AND tasks.project_id = :project_id_filter` を追加。`"unassigned"` なら `AND tasks.project_id IS NULL` を追加（この場合、非adminは手順1の条件と合わせて実質的に「自分が作成した未所属タスク」のみに絞られる）<br/>3. `status` 指定時は `AND tasks.status = :status`<br/>4. `include_inactive=False` の場合は `AND tasks.is_active = true`<br/>5. `ORDER BY :sort :order`、`OFFSET (page-1)*per_page LIMIT per_page`<br/>6. `comment_count` は `01_get_project_tasks.md` と同様に相関サブクエリで算出し、`assignee`/`created_by`/`project`（`project_id`が非NULLの行のみ対象）を`selectinload`で追加取得する |
| 副作用 | なし |

## 7. 関数相関図

```mermaid
flowchart LR
    R["tasks_router.list_tasks"] --> S["task_service.list_tasks"]
    S --> PR["project_repository.is_member"]
    S --> C["task_repository.count"]
    S --> L["task_repository.list"]
    L --> DB[("PostgreSQL<br/>tasks / users / projects")]
    C --> DB
    PR --> DBM[("PostgreSQL<br/>project_members")]
```

## 8. データ遷移図

読み取りのみで状態遷移なし。

```mermaid
flowchart LR
    subgraph read["参照範囲（PostgreSQL）"]
        T["tasks<br/>WHERE 認可範囲 ∩ 各種フィルタ"]
        U["users<br/>assignee / created_by（selectinload）"]
        P["projects<br/>project_is_active算出（project_id非NULL分のみselectinload）"]
        PM["project_members<br/>認可範囲の算出・project_idフィルタ時の所属確認"]
        C["task_comments<br/>COUNT（相関サブクエリ）"]
    end
    T -->|"assignee_id / created_by"| U
    T -->|"project_id"| P
    T -->|"project_id"| PM
    T -->|"id"| C
```

## 9. データアクセス一覧

**PostgreSQL**

| テーブル | 操作 | 条件・TTL | 備考 |
|----------|------|-----------|------|
| project_members | SELECT | `user_id=:uid`（認可範囲の所属project_id集合の算出）、`project_id`指定時の所属確認 | admin時は省略 |
| tasks | SELECT | 認可範囲 ∩ `project_id`/`status`/`is_active`フィルタ、`ORDER BY :sort :order` | 主クエリ |
| tasks | SELECT COUNT | 同上の条件 | `meta.total`算出用 |
| users | SELECT（`selectinload`の追加SELECT） | `assignee_id` / `created_by` | 表示用情報 |
| projects | SELECT（`selectinload`の追加SELECT） | `tasks.project_id`（非NULLのみ） | `project_is_active`算出用 |
| task_comments | SELECT（相関サブクエリ COUNT） | `task_id = tasks.id` | `comment_count`算出 |

**Redis**：使用なし。

## 10. バリデーション規則

| フィールド | pydanticスキーマ | 制約 | フロント（zod）との一致 |
|-----------|-------------------|------|--------------------------|
| page | `TaskListQuery.page` | `int, ge=1`、既定1 | `zod.number().int().min(1)` |
| per_page | `TaskListQuery.per_page` | `int, ge=1, le=100`、既定20 | `zod.number().int().min(1).max(100)` |
| project_id | `TaskListQuery.project_id` | `str \| None`。UUID形式または文字列`"null"`のみ許可し、それ以外は422（サービス層一歩手前のバリデータで判定） | フロントは未所属フィルタ選択時のみ文字列`"null"`を送信するUIとする |
| status | `TaskListQuery.status` | `Literal["todo","in_progress","done"] \| None` | セレクトボックスと一致 |
| include_inactive | `TaskListQuery.include_inactive` | `bool`、既定`False` | チェックボックスと一致 |
| sort | `TaskListQuery.sort` | `Literal["created_at","due_at"]`、既定`"created_at"` | ソートUIの選択肢と一致 |
| order | `TaskListQuery.order` | `Literal["asc","desc"]`、既定`"desc"` | 同上 |

## 11. 非機能・セキュリティ考慮

| 項目 | 内容 |
|------|------|
| ログ出力 | アクセスログ（INFO）のみ |
| ユーザー列挙対策 | `project_id`指定時、非所属プロジェクトは404で存在有無を秘匿（[01](./01_get_project_tasks.md)と同一方針） |
| タイミング攻撃対策 | 対象外 |
| レート制限 | なし |
| fail-close方針 | DB接続不能時は503 |
| N+1対策・クエリ回数 | 認可範囲の算出（`project_members`）、主クエリ（COUNT＋一覧の計2回）、`users`/`projects`の`selectinload`追加SELECT各1回の計5回程度。ページサイズに比例しない |
| 大量データ時の性能 | `project_id IN (サブクエリ)` は所属プロジェクト数に比例したインデックス参照になる。学習規模のデータ量では許容し、要検討事項に記載 |

## 12. テスト設計

| No | 区分 | ケース | 前提 | 期待結果 | pytest関数名案 |
|----|------|--------|------|----------|-----------------|
| 1 | 単体（モック） | project_id省略時のデフォルト範囲 | user=member、リポジトリをモック | `project_id_filter=None`でリポジトリ呼び出し | `test_list_tasks_default_scope` |
| 2 | 単体（モック） | project_id指定・非所属 | `is_member=False`、非admin | `NotFoundError`送出 | `test_list_tasks_project_filter_forbidden` |
| 3 | 単体（モック） | project_id="null"の正規化 | クエリ文字列`"null"` | `project_id_filter="unassigned"`としてサービス層へ渡る | `test_list_tasks_null_literal_normalized` |
| 4 | 単体（モック） | 不正なproject_id文字列 | `"not-a-uuid"` | `ValidationError`（422） | `test_list_tasks_invalid_project_id_string` |
| 5 | 結合 | memberは所属プロジェクトの全タスクを横断取得 | 実DB、所属プロジェクト2件・各2タスク | 200、4件返る | `test_list_tasks_member_cross_project` |
| 6 | 結合 | memberは自分の未所属タスクも含む | 実DB、`project_id=NULL`の自作タスク1件 | 200、所属プロジェクト分＋1件 | `test_list_tasks_includes_own_unassigned` |
| 7 | 結合 | memberは他人の未所属タスクを見えない | 実DB、他ユーザー作成の`project_id=NULL`タスク | 200、含まれない | `test_list_tasks_excludes_others_unassigned` |
| 8 | 結合 | project_id="null"指定で未所属のみ絞込 | 実DB、所属プロジェクトのタスクと自作未所属タスク | 200、未所属タスクのみ返る | `test_list_tasks_filter_unassigned_only` |
| 9 | 結合 | project_id=UUID指定で単一プロジェクトに絞込 | 実DB、複数プロジェクトに所属 | 200、指定プロジェクトのタスクのみ | `test_list_tasks_filter_by_project_id` |
| 10 | 結合 | adminは全ユーザーの未所属タスクを含め全件 | 実DB、複数ユーザーの未所属タスク | 200、全件に含まれる | `test_list_tasks_admin_sees_all_including_unassigned` |
| 11 | 結合 | 既定はis_active=falseを除外 | 実DB、`is_active=false`のタスクを含む | 200、含まれない | `test_list_tasks_excludes_inactive_by_default` |
| 12 | 結合 | include_inactive指定 | 実DB、`?include_inactive=true` | 200、`is_active=false`のタスクも含まれる | `test_list_tasks_include_inactive` |
| 13 | 結合 | statusフィルタ | 実DB、`?status=done` | 200、`status=done`のみ | `test_list_tasks_filter_by_status` |
| 14 | 結合 | ページング | 実DB、認可範囲に25件 | `per_page=20`で1ページ目20件、2ページ目5件 | `test_list_tasks_pagination` |
| 15 | パラメータ化 | AUTH_MODE両対応 | `AUTH_MODE=session` / `jwt` | 5・9・10を両モードで実行 | フィクスチャ `auth_mode` |

## 13. 不明点・要検討事項

| 区分 | 内容 | 影響 |
|------|------|------|
| 要検討 | `project_id` クエリで「未所属のみ」を表す方法として文字列リテラル `"null"` を採用したが、issue #10のブリーフに具体的なパラメータ形式の指定はない（クエリ文字列上は実際のUUID `null` 値を送れないための便宜的な設計）。別案として `unassigned=true` という独立の真偽値パラメータにする方が明快な可能性があり、フロント実装時に最終確認が必要 | クエリパラメータ設計・フロントとの合意 |
| 要検討 | `sort`/`order` パラメータは基本設計に明記がなく、本設計での独自追加（横断一覧のため既定の`position`順が意味を持たないための対応）。ソート対象フィールドを`created_at`/`due_at`の2種に限定した妥当性は要検討 | フロント側のソートUI設計との整合 |
| 要検討 | `project_id`指定時の絞込を「他エンドポイントと同様404で秘匿」としたが、一覧APIのフィルタとしての404が適切か（該当0件の200を返す設計も考えられる）は要検討 | エラーハンドリング方針の一貫性 |