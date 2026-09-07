# 構成図（drawio）

基本設計書の図のうち、レイアウトを保ったまま編集・共有したいものを drawio 形式で保持する。
いずれも**非圧縮のXML**（`mxfile` / `mxGraphModel`）で保存しているため、差分が git で追える。

## ファイル一覧

| ファイル | 図 | 対応する設計書 |
|----------|-----|----------------|
| [01_system_architecture.drawio](./01_system_architecture.drawio) | システム構成図（Docker Compose 6サービス、公開ポート、外部サービス、CI/CD経路） | [00_overview.md §2](../00_overview.md#2-システム構成) / [06_infra_cicd.md §2](../06_infra_cicd.md#2-docker-compose-構成) |
| [02_backend_layers.drawio](./02_backend_layers.drawio) | バックエンドのレイヤ / モジュール構成図（api → service → repository → models、認証Strategy、core、通知） | [00_overview.md §3](../00_overview.md#3-バックエンドのレイヤ構成) / [03_auth.md §2](../03_auth.md#2-strategyパターン設計) |
| [03_er_diagram.drawio](./03_er_diagram.drawio) | ER図（PostgreSQL 8テーブル）＋ Redisキー一覧・主要インデックス・DB関数 | [01_database.md §2](../01_database.md#2-er図) / [02_redis.md §2](../02_redis.md#2-キー一覧) |
| [04_screen_flow.drawio](./04_screen_flow.drawio) | 画面遷移図（11画面、認証ガード、モーダル、OAuth・メール認証/パスワードリセットのメール経路、ヘッダーの通知パネル） | [05_frontend.md §2](../05_frontend.md#2-画面一覧とルーティング) |
| [05_batch_architecture.drawio](./05_batch_architecture.drawio) | batch構成図（スケジューラ、期限通知ジョブ、DB/Redisアクセス、将来のメール通知拡張） | [07_batch.md §2](../07_batch.md#2-構成と責務) |

## 編集方法

| 手段 | 手順 |
|------|------|
| VS Code | 拡張機能「Draw.io Integration」（`hediet.vscode-drawio`）をインストールし、`.drawio` を直接開く |
| デスクトップアプリ | [drawio Desktop](https://github.com/jgraph/drawio-desktop) で開く |
| ブラウザ | [app.diagrams.net](https://app.diagrams.net) → File → Open from → Device |

## 編集時のルール

- **保存形式は「非圧縮XML」を維持する**（drawio の設定で `Compressed` を無効にする）。圧縮すると git 差分が読めなくなる
- 図を変更したら、対応する設計書（上表）の記述も併せて更新する
- 色の意味は各図の凡例ボックスに定義してある。新しい要素を追加する場合も同じ配色規則に従う
  - 青：クライアント / プレゼンテーション層 / 未認証画面
  - 緑：アプリケーション / ビジネスロジック / 認証必須画面
  - 橙：永続データ（PostgreSQL）・データアクセス層
  - 赤：揮発データ（Redis）・管理者専用
  - 黄：認証 Strategy・OAuth2 関連
  - 紫：メール（SMTP / Mailpit）
  - 灰：CI/CD・横断的基盤（core）
- 破線の枠はグループ（論理的な括り）またはモーダル、破線の矢印はリダイレクト・生成・継承・デプロイ経路を表す

## エクスポート

README や Pull Request での表示用として、対応するSVGも同じディレクトリに保持する。編集の正は `.drawio` とし、図を変更した場合はSVGを再生成して差分を同期する。

```
# drawio Desktop / CLI の場合
drawio --export --format svg --output 01_system_architecture.svg 01_system_architecture.drawio
```

> `.drawio` が編集用の正本、`.svg` は生成物としてコミット対象、`.png` は生成しない。
