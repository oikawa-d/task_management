# Cerberus（タスク管理システム） 要件定義書（学習用）

## 0. 本書の位置づけ

フロントエンド⇔API⇔DB連携、複数の認証方式の実装・比較、GitHub Actionsを用いたCI/CD設計を学習することを目的とした題材の要件定義書。実務での使用は想定せず、学習の進め方が確認できる粒度でまとめている。

**確認事項（要合意）**

ヒアリング内容のうち、CI/CDについて「デプロイまで含めた本格的なCD」「ローカル/Docker Composeのみで完結」という2つの回答があったため、本書では以下のように解釈して設計している。

- クラウド（AWS/GCP等）は使用しない
- GitHub Actions上でビルド・テスト・Dockerイメージ作成までを自動化する
- self-hosted runner（自分のPCまたは自宅サーバー等にGitHub Actionsのランナーを常駐させる仕組み）を使い、mainブランチへのマージをトリガーにローカル環境のDocker Composeを再起動して反映する

クラウド上に実際にデプロイする構成を学びたい場合は、別案（無料枠のあるクラウドサービスを使う構成）も提示できるため、その場合は教えてほしい。

---

## 1. システム概要

チームでプロジェクトを作成し、タスクをカンバン形式（未着手／進行中／完了）で管理するWebアプリケーション。

アプリ名「Cerberus」は、冥界の門を守る三頭の番犬に由来する。本システムがsession／JWT／OAuth2という3つの認証方式を実装・比較する構成であることになぞらえている。

- 想定ユーザー：一般ユーザー、管理者
- 技術スタック：FastAPI（バックエンド）／React（フロントエンド）／PostgreSQL（永続データ）／Redis（ログイン状態の管理）

---

## 2. 画面一覧（7画面）

| No | 画面名 | 概要 |
|----|--------|------|
| 1 | ログイン画面 | メール/パスワードログイン、Googleログインボタンを配置 |
| 2 | 会員登録画面 | メール/パスワードでの新規登録 |
| 3 | ダッシュボード | 自分が所属するプロジェクトの一覧表示 |
| 4 | プロジェクト詳細（カンバンボード） | タスクをステータス別に表示、ドラッグ&ドロップで状態変更 |
| 5 | タスク詳細/編集 | タスクの内容編集、担当者アサイン、コメント |
| 6 | アカウント設定画面 | プロフィール編集、パスワード変更 |
| 7 | 管理者用ユーザー管理画面 | 全ユーザー・全プロジェクトの閲覧、権限変更（管理者のみアクセス可） |

---

## 3. 機能要件

### 3.1 認証機能（本題材の中心テーマ）

環境変数 `AUTH_MODE` で以下2方式を切り替え可能な設計とする（Strategyパターンをバックエンドの認証処理に適用）。

| モード | 概要 |
|--------|------|
| `session` | サーバー側のセッション情報をRedisに保持し、HttpOnly Cookieでセッションidを送受信。有効期限はRedisのTTLで管理する |
| `jwt` | アクセストークン（短命）＋リフレッシュトークン（長命）方式。アクセストークンは署名検証のみでサーバー側に保存しない。リフレッシュトークンはハッシュ化した上でRedisに保持し、TTL＝有効期限とする |

上記に加えて、モードに関わらず常時利用できるオプションとしてGoogleによるOAuth2ログインを実装する。

ログイン状態（有効なセッション／リフレッシュトークン）はRedisで一元管理し、期限切れになると自動的に失効させる。ログアウト時はRedis上の該当キーを削除することで即時失効させる。

**学習の進め方（比較の観点）**
- セッション方式とJWT方式で、ログアウト時の処理・トークン/セッションの失効方法がどう異なるか
- スケールする場合（サーバー台数が増えた場合）にどちらが有利か
- CSRF対策の要否の違い

### 3.2 プロジェクト・タスク管理機能

- プロジェクトのCRUD（作成・閲覧・更新・削除）
- プロジェクトへのメンバー招待
- タスクのCRUD、ステータス変更（未着手／進行中／完了）
- タスクへのコメント機能

### 3.3 ロール管理（RBAC）

- 一般ユーザー：自分が所属するプロジェクトのみ閲覧・操作可能
- 管理者：全ユーザー・全プロジェクトの閲覧、ユーザーの権限変更、プロジェクト削除が可能

---

## 4. 非機能要件

- パスワードはハッシュ化して保存する（bcryptまたはargon2）
- セッション/Cookie認証時はCSRF対策（CSRFトークンの発行・検証）を実装する
- JWT認証時はリフレッシュトークンのローテーションと失効管理を実装する
- バックエンドはpytest、フロントエンドはVitestまたはJestで自動テストを実装する
- 環境変数（DB接続情報、JWT署名鍵、OAuthクライアントシークレット等）はGitHub Secretsおよび`.env`で管理し、リポジトリに直接コミットしない
- Redisはインメモリストアのため、永続化設定（RDB/AOF）をしない場合、サーバー再起動時に全ログインユーザーがログアウト状態になる。学習用途では許容範囲だが、挙動として認識しておく
- ログインの成否履歴はRedisのTTL失効とは独立してPostgreSQLに記録し、監査目的で参照できるようにする

---

## 5. データストア設計（概要）

ログインの有効性チェックに使う情報はRedisで管理し、永続的に残す必要があるデータのみPostgreSQLに保存する構成とする。

### 5.1 PostgreSQL（永続データ）

| テーブル | 主なカラム | 備考 |
|----------|-----------|------|
| users | id, email, password_hash, role, created_at | roleは`member`/`admin` |
| oauth_accounts | id, user_id, provider, provider_user_id | Google等の外部ID紐付け用 |
| projects | id, name, owner_id, created_at | |
| project_members | project_id, user_id, joined_at | 複合主キー |
| tasks | id, project_id, title, status, assignee_id, created_at | statusは`todo`/`in_progress`/`done` |
| task_comments | id, task_id, user_id, body, created_at | |
| login_history | id, user_id, login_method, ip_address, success, created_at | ログイン試行の監査ログ。login_methodは`session`/`jwt`/`oauth_google`。Redis側の失効状況とは独立して保持し続ける |

### 5.2 Redis（ログイン状態の管理）

有効なセッション／リフレッシュトークンのみを保持し、TTLで自動失効させる。

| キー例 | バリュー | TTL | 用途 |
|--------|---------|-----|------|
| `session:{session_id}` | user_id, role等（JSON） | セッション有効期限（例：30分〜数時間） | session方式のログイン状態確認 |
| `refresh:{token_hash}` | user_id, 発行日時（JSON） | リフレッシュトークン有効期限（例：14日） | jwt方式のリフレッシュトークン有効性確認。ログアウト時に即削除して失効させる |

**補足**
- Redisの永続化設定（RDB/AOF）は行わない前提とする。サーバー再起動時にログイン状態が失われる点は許容する
- 「誰が・いつログインしたか」は上記`login_history`テーブル（PostgreSQL）で別途保持する

---

## 6. API設計（主要エンドポイント）

| メソッド | パス | 概要 |
|----------|------|------|
| POST | /auth/register | 会員登録 |
| POST | /auth/login | ログイン（AUTH_MODEに応じて処理分岐） |
| POST | /auth/logout | ログアウト |
| POST | /auth/refresh | トークン再発行（jwtモードのみ） |
| GET | /auth/oauth/google | Google OAuth2認可開始 |
| GET | /auth/oauth/google/callback | Google OAuth2コールバック |
| GET | /projects | 所属プロジェクト一覧取得 |
| POST | /projects | プロジェクト作成 |
| GET | /projects/{id}/tasks | タスク一覧取得 |
| POST | /projects/{id}/tasks | タスク作成 |
| PATCH | /tasks/{id} | タスク更新（ステータス変更含む） |
| GET | /admin/users | 全ユーザー一覧（管理者のみ） |

---

## 7. フロントエンド構成

- React（Vite）
- 状態管理：Context APIまたはZustand（学習目的であれば軽量なもので十分）
- APIクライアント：axios
- 認証方式の違い（トークンの保持場所やリフレッシュ処理の有無）をAPIクライアント層で吸収し、画面側のコードは方式に依存しない設計とする

---

## 8. CI/CD設計

### 8.1 CI（継続的インテグレーション）

プッシュ・プルリクエスト時にGitHub Actionsで以下を自動実行する。

- バックエンド：ruffまたはflake8によるLint、mypyによる型チェック、pytestによるテスト
- バックエンドのテストでは、GitHub Actionsの`services`機能でRedisおよびPostgreSQLのコンテナを起動し、実際の接続を伴うテストを実行する
- フロントエンド：ESLintによるLint、TypeScriptの型チェック、Vitest/Jestによるテスト
- Dockerイメージのビルド確認（buildのみ、pushは行わない）

### 8.2 CD（継続的デリバリー）

mainブランチへのマージをトリガーに以下を実行する。

- Dockerイメージをビルドし、GHCR（GitHub Container Registry）へpush
- self-hosted runnerを通じて、デプロイ対象環境（学習者自身のPC/サーバー）上で最新イメージをpullし、`docker compose up -d`で反映

### 8.3 ポイント

- ワークフロー構文（`on`によるトリガー設定、`jobs`と`steps`の書き方）
- Secretsの利用方法（DB接続情報やJWT署名鍵の受け渡し）
- pip/npmの依存関係キャッシュによるビルド時間短縮
- self-hosted runnerのセットアップと登録
- CIとCDでワークフローファイルを分割する設計（`ci.yml` / `cd.yml`）

---

## 9. ディレクトリ構成（例）

```
project-root/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── cd.yml
├── api/
│   ├── alembic/
│   │   ├── versions/        # マイグレーションファイル（自動生成 + 手動編集）
│   │   ├── env.py
│   │   └── script.py.mako
│   ├── alembic.ini
│   ├── app/
│   │   ├── main.py
│   │   ├── auth/
│   │   │   ├── session_auth.py
│   │   │   ├── jwt_auth.py
│   │   │   └── oauth.py
│   │   ├── models/
│   │   ├── routers/
│   │   ├── db.py
│   │   └── redis_client.py
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   └── auth/
│   ├── tests/
│   └── Dockerfile
├── db
|   ├── migrations/
│   ├── functions/        # PostgreSQL関数定義（.sqlファイル）
│   └── procedures/       # ストアドプロシージャ定義（.sqlファイル）
└── docker-compose.yml   # backend / frontend / postgres / redis の4サービスを定義
```

---

## 10. ロードマップ（推奨実装順）

1. Docker Composeで FastAPI + React + PostgreSQL + Redis の疎通確認
2. セッション/Cookie認証の実装（セッション情報をRedisに保存、TTL設定を含む）
3. JWT認証（アクセストークン＋リフレッシュトークン）の実装、`AUTH_MODE`での切り替え対応（リフレッシュトークンのRedis保存を含む）
4. Google OAuth2ログインの追加
5. RBAC（ロールベースアクセス制御）の実装
6. CI（Lint・型チェック・テスト自動化）の構築
7. Dockerイメージ化とCD（self-hosted runnerによる自動デプロイ）の構築
8. 3つの認証方式を比較し、違いを整理してまとめる

---

## 11. スコープ外（対象外とする範囲）

- クラウド環境への本番デプロイ、負荷分散、監視・アラート設計
- 決済機能、メール送信等の外部サービス連携（OAuth以外）
- モバイルアプリ対応
