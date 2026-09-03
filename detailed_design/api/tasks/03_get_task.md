# GET /api/tasks/{task_id}（タスク詳細取得）

## 0. 関連ドキュメント

| ドキュメント | 内容 |
|--------------|------|
| [../../../basic_design/04_api.md](../../../basic_design/04_api.md) | §2.4 エンドポイント一覧、§5 認可マトリクス |
| [../../../basic_design/01_database.md](../../../basic_design/01_database.md) | §3.5 tasks、§7 Q-4 |
| [../../auth/05_rbac.md](../../auth/05_rbac.md) | `require_project_member`、404統一方針 |
| [../../database/06_table_tasks.md](../../database/06_table_tasks.md) | tasks テーブル詳細 |
| [./01_get_project_tasks.md](./01_get_project_tasks.md) | 一覧取得（カンバン用）との差異 |
| [./04_patch_task.md](./04_patch_task.md) | 本APIで取得した `version` を使う更新API |
| [./06_get_task_comments.md](./06_get_task_comments.md) | コメント一覧（本APIとは別クエリ） |
| [../../screen/08_task_detail_modal.md](../../screen/08_task_detail_modal.md) | 本APIを使用するタスク詳細モーダル |

## 1. 概要

| 項目 | 内容 |
|------|------|
| エンドポイント | `GET /api/tasks/{task_id}` |
| 目的 | タスク1件の詳細情報を取得する。`task_id` からプロジェクト所属を辿って認可する点が `/projects/{id}/tasks` 系と異なる |
| 認証 | session モード：`cerberus_sid` Cookie ／ jwt モード：`Authorization: Bearer {access_token}` |
| 認可 | プロジェクトメンバー（`task_id` → `tasks.project_id` を特定した上で `require_project_member` 相当の判定。admin は無条件許可） |
| CSRF検証 | 不要（参照系GET） |
| Origin検証 | 不要 |
| AUTH_MODE差異 | 認証情報の解決方法のみ異なり、業務ロジックに差異なし |
| 冪等性 | あり |
| レート制限 | 対象外 |
| トランザクション境界 | 単一の読み取り専用SELECT |

## 2. 入出力仕様（全体の出入力）

### 2.1 リクエスト

**パスパラメータ**

| 名前 | 型 | 必須 | 制約 | 説明 |
|------|----|----|------|------|
| task_id | string(uuid) | ○ | UUID v4形式 | 対象タスクID |

**クエリパラメータ**：なし
**ヘッダ**：`Authorization`（jwtモード必須）
**Cookie**：`cerberus_sid`（sessionモード必須）
**ボディ**：なし

### 2.2 レスポンス

**`200 OK`**

```json
{
  "id": "b2e4...",
  "project_id": "3f1c2a10-...",
  "title": "設計書をレビューする",
  "description": "詳細説明のテキスト",
  "status": "todo",
  "assignee": { "id": "9a1b...", "username": "taro", "display_name": "山田 太郎" },
  "created_by": { "id": "9a1b...", "username": "taro", "display_name": "山田 太郎" },
  "position": 0,
  "version": 1,
  "due_date": null,
  "comment_count": 2,
  "created_at": "2026-09-01T00:00:00Z",
  "updated_at": "2026-09-01T00:00:00Z"
}
```

| フィールド | 型 | NULL可否 | 説明 |
|-----------|----|----------|------|
| id | string(uuid) | 不可 | タスクID |
| project_id | string(uuid) | 不可 | 所属プロジェクトID |
| title | string | 不可 | |
| description | string | 可 | |
| status | string | 不可 | `todo` / `in_progress` / `done` |
| assignee | object | 可 | `{id, username, display_name}` |
| created_by | object | 不可 | `{id, username, display_name}` |
| position | integer | 不可 | 列内位置 |
| version | integer | 不可 | 楽観ロック用。以後の `PATCH` で必須 |
| due_date | string(date) | 可 | |
| comment_count | integer | 不可 | `task_comments` の件数 |
| created_at / updated_at | string(datetime) | 不可 | ISO 8601 UTC |

`Set-Cookie` の発行なし。`X-Request-ID` を全レスポンスに付与。

## 3. エラー仕様

| HTTP | code | 発生条件 | メッセージ | 備考 |
|------|------|----------|------------|------|
| 401 | `UNAUTHENTICATED` / `SESSION_EXPIRED` / `TOKEN_EXPIRED` / `TOKEN_INVALID` | 認証情報なし・無効 | 認証が必要です | |
| 403 | `USER_INACTIVE` | `is_active=false` | アカウントが無効化されています | |
| 404 | `NOT_FOUND` | `task_id` 不存在、または所属プロジェクトへの非所属member | タスクが見つかりません | 存在有無を隠すため、非所属も404で統一 |
| 503 | `SERVICE_UNAVAILABLE` | PostgreSQL接続不能 | 一時的にサービスを利用できません | fail-close |

## 4. 処理シーケンス

```mermaid
sequenceDiagram
    autonumber
    participant FE as "React SPA"
    participant R as "tasks_router"
    participant D as "deps: get_current_user"
    participant S as "task_service"
    participant TR as "task_repository"
    participant PG as "PostgreSQL"

    FE->>R: "GET /api/tasks/{task_id}"
    R->>D: "認証（get_current_user）"
    D-->>R: "CurrentUser"
    R->>S: "get_task_detail(task_id, current_user)"
    S->>TR: "get_with_project(task_id)"
    TR->>PG: "SELECT tasks JOIN projects<br/>WHERE tasks.id = task_id"
    PG-->>TR: "task行 + project_id"
    alt "タスクが存在しない"
        TR-->>S: "None"
        S-->>R: "NotFoundError"
        R-->>FE: "404 NOT_FOUND"
    else "存在する"
        TR-->>S: "TaskWithProject"
        S->>S: "current_userがproject_membersに所属 or adminか確認"
        alt "非所属"
            S-->>R: "NotFoundError"
            R-->>FE: "404 NOT_FOUND"
        else "所属 または admin"
            S->>TR: "count_comments(task_id)"
            TR->>PG: "SELECT COUNT(*) FROM task_comments WHERE task_id"
            PG-->>TR: "comment_count"
            TR-->>S: "comment_count"
            S-->>R: "TaskDetailResponse"
            R-->>FE: "200 {task}"
        end
    end
```

## 5. 処理フロー・分岐

```mermaid
flowchart TB
    A["リクエスト受信"] --> B{"task_idはUUID形式?"}
    B -->|"No"| E422["422 VALIDATION_ERROR"]
    B -->|"Yes"| C{"認証情報は有効?"}
    C -->|"No"| E401["401 UNAUTHENTICATED系"]
    C -->|"Yes"| D{"is_active?"}
    D -->|"No"| E403["403 USER_INACTIVE"]
    D -->|"Yes"| F{"tasks.id = task_idが存在?"}
    F -->|"No"| E404a["404 NOT_FOUND"]
    F -->|"Yes"| G{"project_idを特定し<br/>admin または所属メンバー?"}
    G -->|"No"| E404b["404 NOT_FOUND"]
    G -->|"Yes"| H["comment_count集計"]
    H --> I["200 レスポンス生成"]
```

## 6. 関数詳細

### 6.1 `api/routers/tasks.py :: get_task`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def get_task(task_id: UUID, current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> TaskDetailResponse` |
| 引数 | task_id: 対象タスクID／current_user: 現在ユーザー／db: DBセッション |
| 戻り値 | `TaskDetailResponse`（200） |
| 送出例外 | `NotFoundError`（404） |
| 処理内容 | 1. `task_service.get_task_detail(task_id, current_user)` を呼び出す<br/>2. 結果を200で返す |
| 副作用 | なし |

### 6.2 `service/task_service.py :: get_task_detail`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def get_task_detail(task_id: UUID, user: CurrentUser) -> TaskDetailResponse` |
| 引数 | task_id: 対象タスクID／user: 現在ユーザー |
| 戻り値 | `TaskDetailResponse` |
| 送出例外 | `NotFoundError`（タスク不存在、または非所属） |
| 処理内容 | 1. `task_repository.get_with_project(task_id)` でタスクと `project_id` を取得。`None` なら `NotFoundError`<br/>2. `user.role != 'admin'` の場合、`project_repository.is_member(project_id, user.id)` で所属確認。非所属なら `NotFoundError`（プロジェクト単体APIと同じ404統一方針）<br/>3. `task_repository.count_comments(task_id)` で `comment_count` を取得し、レスポンスDTOに合成 |
| 副作用 | なし |

### 6.3 `repository/task_repository.py :: get_with_project`

| 項目 | 内容 |
|------|------|
| シグネチャ | `async def get_with_project(db: AsyncSession, task_id: UUID) -> TaskWithProject \| None` |
| 引数 | db: DBセッション／task_id: 対象タスクID |
| 戻り値 | `TaskWithProject`（`Task` に `assignee` / `created_by` をEager Loadしたもの）または `None` |
| 送出例外 | `OperationalError`（503へ変換） |
| 処理内容 | 1. `tasks` を `id = task_id` で1件取得し、`assignee`（`users`）・`created_by`（`users`）を `selectinload` でEager Load<br/>2. 存在しない場合は `None` を返す（例外は投げない。所属確認前の存在チェックはサービス層で行う） |
| 副作用 | なし |

## 7. 関数相関図

```mermaid
flowchart LR
    R["tasks_router.get_task"] --> S["task_service.get_task_detail"]
    S --> TR["task_repository.get_with_project"]
    S --> PR["project_repository.is_member"]
    S --> CC["task_repository.count_comments"]
    TR --> DB[("PostgreSQL<br/>tasks / users")]
    PR --> DBM[("PostgreSQL<br/>project_members")]
    CC --> DBC[("PostgreSQL<br/>task_comments")]
```

## 8. データ遷移図

読み取りのみで状態遷移なし。参照範囲は以下の通り。

```mermaid
flowchart LR
    subgraph read["参照範囲（PostgreSQL）"]
        T["tasks<br/>WHERE id = :task_id"]
        U["users<br/>assignee / created_by（JOIN）"]
        PM["project_members<br/>所属確認（非adminのみ）"]
        C["task_comments<br/>COUNT（別クエリ）"]
    end
    T -->|"project_id"| PM
    T -->|"assignee_id / created_by"| U
    T -->|"id"| C
```

## 9. データアクセス一覧

**PostgreSQL**

| テーブル | 操作 | 条件・TTL | 備考 |
|----------|------|-----------|------|
| tasks | SELECT | `id = task_id` | JOIN先の `project_id` から認可判定を行う起点 |
| users | SELECT（JOIN） | `assignee_id` / `created_by` | 表示用情報のEager Load |
| project_members | SELECT | `project_id`, `user_id` | admin以外の所属確認 |
| task_comments | SELECT（COUNT） | `task_id = :task_id` | `comment_count` 算出。一覧取得（[01](./01_get_project_tasks.md)）とは別クエリでN+1にならない（対象が1件のため） |

**Redis**：使用なし。

## 10. バリデーション規則

| フィールド | pydanticスキーマ | 制約 | フロント（zod）との一致 |
|-----------|-------------------|------|--------------------------|
| task_id（パス） | FastAPI型ヒント `UUID` | UUID v4形式。不一致は422 | ルーティング側でUUID形式チェック |

## 11. 非機能・セキュリティ考慮

| 項目 | 内容 |
|------|------|
| ログ出力 | アクセスログ（INFO）のみ。監査ログ対象外（参照系） |
| ユーザー列挙対策 | タスク不存在・非所属のいずれも404で統一し、存在有無を秘匿する |
| タイミング攻撃対策 | 対象外 |
| レート制限 | なし |
| fail-close方針 | DB接続不能時は503 |

## 12. テスト設計

| No | 区分 | ケース | 前提 | 期待結果 | pytest関数名案 |
|----|------|--------|------|----------|-----------------|
| 1 | 単体（モック） | 正常系 | リポジトリが `TaskWithProject` を返す | `TaskDetailResponse` に整形される | `test_get_task_detail_success` |
| 2 | 単体（モック） | タスク不存在 | リポジトリが `None` を返す | `NotFoundError` 送出 | `test_get_task_detail_not_found` |
| 3 | 単体（モック） | 非所属member | `is_member` が `False` | `NotFoundError` 送出 | `test_get_task_detail_forbidden_as_not_found` |
| 4 | 結合 | 正常系取得（所属member） | 実DB、対象タスクにコメント2件 | 200、`comment_count=2` | `test_get_task_success` |
| 5 | 結合 | 存在しないtask_id | 実DB、ランダムUUID | 404 `NOT_FOUND` | `test_get_task_not_found` |
| 6 | 結合 | 非所属member | 実DB、他プロジェクトのタスク | 404 `NOT_FOUND` | `test_get_task_forbidden_as_404` |
| 7 | 結合 | admin | 実DB、非所属プロジェクトのタスクでも200 | 200 | `test_get_task_admin_bypass` |
| 8 | パラメータ化 | AUTH_MODE両対応 | `AUTH_MODE=session` / `jwt` | 4〜7を両モードで実行 | フィクスチャ `auth_mode` |

## 13. 不明点・要検討事項

なし
