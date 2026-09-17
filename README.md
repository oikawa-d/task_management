# Cerberus

チームでプロジェクトとタスクを管理する学習用Webアプリです。Docker Composeでフロントエンド、API、PostgreSQL、Redis、期限通知バッチをまとめて起動できます。

## このアプリでできること

- メールアドレス／パスワード登録、メール認証、ログイン、ログアウト、パスワード再設定
- `session` または `jwt` の認証方式切り替えと、Google OAuth2ログイン
- プロジェクトの作成・編集・論理削除、メンバー招待
- プロジェクト所属／未所属タスクの作成・編集・論理削除
- 未着手・進行中・完了のカンバン管理、ドラッグ＆ドロップによるステータス変更
- 担当者、期限日時、タスクコメントの管理
- ダッシュボードのプロジェクト一覧・期限カレンダー表示
- 期限が近いタスクのアプリ内通知、未読件数表示、全件既読
- 管理者によるユーザー・プロジェクト・ログイン履歴の管理

期限通知は `APP_TIMEZONE`（既定：`Asia/Tokyo`）を基準に、毎日10時・17時に実行されます。メール通知やブラウザプッシュ通知は対象外です。

## 必要な環境

- Git
- Docker Engine または Docker Desktop
- Docker Compose v2（`docker compose` コマンド）
- モダンブラウザ

ローカル実行ではPython、Node.js、PostgreSQL、Redisをホストに個別インストールする必要はありません。コンテナ内で、Python 3.14、Node.js 26、PostgreSQL 17、Redis 8を使用します。

## 導入方法

```bash
git clone <repository-url>
cd task_management
cp .env.example .env
```

`.env`を開き、少なくとも次の値をローカル環境に合わせて設定します。

- `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`、`DATABASE_URL`
- `JWT_SECRET_KEY`（推測されにくい値）
- `INITIAL_ADMIN_EMAIL`、`INITIAL_ADMIN_USERNAME`、`INITIAL_ADMIN_PASSWORD`
- Googleログインを使う場合は `GOOGLE_LOGIN_ENABLED=true`、`GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`、`GOOGLE_REDIRECT_URI`

Googleログインを使わない場合は `GOOGLE_LOGIN_ENABLED=false` にします。メール送信は開発環境ではMailpitを利用するため、通常はSMTPサービスを別途用意する必要はありません。

## 初回設定と起動

```bash
docker compose -f docker-compose.yml -f compose.dev.yml --profile dev up --build -d
```

backendコンテナの起動時にAlembicのマイグレーションが実行されます。起動後、次のURLへアクセスしてください。

- アプリ：<http://localhost:5173>
- Mailpit（確認メール・再設定メールの確認）：<http://localhost:8025>
- APIドキュメント：<http://localhost:5173/api/docs>

登録後はMailpitで確認メールを開き、メール認証を完了してからログインします。管理者機能を利用する場合は、`INITIAL_ADMIN_*` の初期管理者作成処理が現行コードで自動実行されるか要確認です。自動作成されない場合の管理者登録手順は未定義です。

ログを確認するには次のコマンドを使います。

```bash
docker compose -f docker-compose.yml -f compose.dev.yml --profile dev logs -f
```

停止する場合は次を実行します。PostgreSQLのデータボリュームは保持されます。

```bash
docker compose -f docker-compose.yml -f compose.dev.yml --profile dev down
```

設定項目の一覧は[`.env.example`](./.env.example)、詳細な仕様は[`docs/`](./docs/)を参照してください。
