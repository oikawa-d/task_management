# 画面ワイヤーフレーム（drawio）

`05_frontend.md` の画面仕様（§2 画面一覧とルーティング、§3 共通レイアウト、§3.1 通知パネル、§7 画面別の主要仕様）を基に、
フロントエンドの各画面のUIワイヤーフレーム構成イメージを drawio 形式で保持する。
いずれも**非圧縮のXML**（`mxfile` / `mxGraphModel`）で保存しているため、差分が git で追える。

対象は全11画面＋共通レイアウト（AppLayout）＋ダッシュボードのカレンダー表示（issue #38）＝計13ファイル。画面1つにつき1ファイルで分割している。

## ファイル一覧

| ファイル | 画面 | パス | 参照節 |
|----------|------|------|--------|
| [00_app_layout.drawio](./00_app_layout.drawio) | 共通レイアウト（AppLayout：サイドバー・ヘッダー・通知ベル/パネル） | - | [05_frontend.md §3](../05_frontend.md#3-共通レイアウト) / [§3.1](../05_frontend.md#31-通知ベルと通知パネル) |
| [01_login.drawio](./01_login.drawio) | ログイン | `/login` | [05_frontend.md §7.1](../05_frontend.md#71-ログイン) |
| [02_register.drawio](./02_register.drawio) | 会員登録 | `/register` | [05_frontend.md §7.2](../05_frontend.md#72-会員登録) |
| [03_password_forgot.drawio](./03_password_forgot.drawio) | パスワード再設定要求 | `/password/forgot` | [05_frontend.md §2表](../05_frontend.md#2-画面一覧とルーティング)（詳細UIは要確認、図中に明記） |
| [04_password_reset.drawio](./04_password_reset.drawio) | パスワード再設定 | `/password/reset#token=` | [05_frontend.md §2表](../05_frontend.md#2-画面一覧とルーティング)（詳細UIは要確認、図中に明記） |
| [05_verify_email.drawio](./05_verify_email.drawio) | メール認証 | `/verify-email#token=` | [05_frontend.md §7.3](../05_frontend.md#73-メール認証) |
| [06_dashboard.drawio](./06_dashboard.drawio) | ダッシュボード（カード表示） | `/dashboard` | [05_frontend.md §7.4](../05_frontend.md#74-ダッシュボード) |
| [12_dashboard_calendar.drawio](./12_dashboard_calendar.drawio) | ダッシュボード（カレンダー表示） | `/dashboard`（表示切替タブ） | [05_frontend.md §7.4.1](../05_frontend.md#741-カレンダー表示issue-38) |
| [07_board.drawio](./07_board.drawio) | プロジェクト詳細（カンバン） | `/projects/:projectId` | [05_frontend.md §7.5](../05_frontend.md#75-カンバンボード) |
| [08_task_detail_modal.drawio](./08_task_detail_modal.drawio) | タスク詳細/編集モーダル | `/projects/:projectId/tasks/:taskId` | [05_frontend.md §7.5](../05_frontend.md#75-カンバンボード) |
| [09_settings.drawio](./09_settings.drawio) | アカウント設定 | `/settings` | [05_frontend.md §7.6](../05_frontend.md#76-アカウント設定) |
| [10_admin_users.drawio](./10_admin_users.drawio) | 管理者ユーザー管理 | `/admin/users` | [05_frontend.md §7.7](../05_frontend.md#77-管理者ユーザー管理) |
| [11_oauth_callback.drawio](./11_oauth_callback.drawio) | OAuthコールバック中継 | `/oauth/callback` | [05_frontend.md §2表](../05_frontend.md#2-画面一覧とルーティング) / [§7.3.1](../05_frontend.md#731-oauthコールバック中継) |

## 編集方法

| 手段 | 手順 |
|------|------|
| VS Code | 拡張機能「Draw.io Integration」（`hediet.vscode-drawio`）をインストールし、`.drawio` を直接開く |
| デスクトップアプリ | [drawio Desktop](https://github.com/jgraph/drawio-desktop) で開く |
| ブラウザ | [app.diagrams.net](https://app.diagrams.net) → File → Open from → Device |

## 編集時のルール

- **保存形式は「非圧縮XML」を維持する**（drawio の設定で `Compressed` を無効にする）。圧縮すると git 差分が読めなくなる
- 図を変更したら、対応する `05_frontend.md` の記述も併せて確認する（内容不一致を作らない）
- 色の意味は各図の凡例ボックスに定義してある。新しい要素を追加する場合も同じ配色規則に従う
  - 青（`#2E75B6`）：未認証画面（AuthLayout）の外枠
  - 緑（`#2E7D32`）：認証必須画面（AppLayout）の外枠
  - 赤（`#DD344C`）：管理者専用要素（「管理」タブ、ロール変更・有効/無効トグル・強制ログアウト等）
  - 黄（`#E7A500`）：OAuth関連（Googleログイン/新規登録ボタン、OAuthコールバック画面）
  - 灰（`#5A6B7B` 系）：通常のUI要素（ヘッダー・サイドバー・入力欄・カード・テーブル等のコンテナ）
  - 濃紺（`#232F3E`）：主要な操作ボタン、モーダルの半透明オーバーレイ
- 破線の枠は、ポップオーバー/モーダル/補足ノート/「要確認」マーカーを表す
- `08_task_detail_modal.drawio` は、`07_board.drawio`（カンバン）を簡略化した背景の上に、半透明オーバーレイ＋モーダル本体を重ねて表現している
- `05_frontend.md` に記載のない仕様は創作せず、図中に赤破線の「⚠ 要確認」ボックスとして明記している（該当箇所: `03_password_forgot`, `04_password_reset`, `06_dashboard` のプロジェクト作成モーダル内フィールド, `10_admin_users` のプロジェクト一覧タブ詳細）

## 検証

`gen.py` / `validate.py` は AWS構成図用ジェネレータ（`~/.claude/skills/architecture-diagram/`）を、
`icons` / `groups` を使わず `boxes` のみで流用している（`color` に `#RRGGBB` を直指定）。

```
python3 ~/.claude/skills/architecture-diagram/gen.py spec.json out.drawio
python3 ~/.claude/skills/architecture-diagram/validate.py out.drawio
# => OK: レイアウト違反なし
```

13ファイルすべてで検証済み（`OK: レイアウト違反なし`）。

## エクスポート

README や Pull Request での表示用として、対応するSVGも同じディレクトリに保持する。編集の正は `.drawio` とし、図を変更した場合はSVGを再生成して差分を同期する。

```
# drawio Desktop / CLI の場合
xvfb-run drawio --export --format svg --output 00_app_layout.svg 00_app_layout.drawio
```

> `.drawio` が編集用の正本、`.svg` は生成物としてコミット対象、`.png` は生成しない。
