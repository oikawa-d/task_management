# 詳細設計 品質検査手順・結果

Issue #7（[フェーズ3: 設計書の現行化と品質基準を整備する](https://github.com/oikawa-d/task_management/issues/7)）で定める設計書の現行性・章構成・表記整合性に加え、issue #12のSP/FN責務移管を検証する手順である。対象はMarkdown設計書であり、実装コードや `.env` は検査対象にしない。

## 1. 必須章と対象ファイル

APIの必須章は「関連ドキュメント／概要／入出力／エラー／処理シーケンス／処理フロー／関数詳細／関数相関図／データ遷移図／テスト設計／不明点・要検討事項」とする。Batch・履歴・インフラは、処理対象に応じて同じ章を持ち、参照だけの章は「状態遷移なし」と明記する。

| 対象ファイル | 章の追跡方法・Issue #7で補完した箇所 |
|--------------|----------------------------------------|
| `api/notifications/01_get_notifications.md`、`02_get_notifications_unread_count.md` | 全必須章あり。`fn_list_notifications` / `fn_count_unread_notifications` の呼び出しとクエリ回数を記載 |
| `api/notifications/03_patch_notification_read.md`、`04_post_notifications_read_all.md` | 処理フロー・関数相関図・データ遷移図・クエリ／トランザクション・不明点を追加 |
| `batch/00_overview.md`、`01_scheduler.md`、`02_due_notification_job.md` | 全体方針・スケジューラ・ジョブの順に、入力／責務／例外／データ遷移を相互参照する |
| `database/11_table_api_history.md`、`12_table_batch_history.md` | テーブルI/O・記録シーケンス・状態遷移・履歴操作の責務と例外を追跡する |
| `log/00_history.md` | API／Batch／標準出力の記録対象、入力／出力、データ遷移を一つの流れで追跡する |
| `infra/08_dockerfile_batch.md` | BatchコンテナのI/O・起動シーケンス・分岐・関数／要素責務・データ遷移を追加 |
| `screen/06_dashboard.md` | 通知APIの参照先を現行詳細設計へ更新。通知ベル／パネルのUI・API連携を追跡する |

DB責務移管の必須確認対象は、`database/08_db_functions.md`（SP/FN一覧・SQLSTATE正）、`auth/05_rbac.md`（FNによる事実判定）、`basic_design/01_database.md`・`04_api.md`（基本設計への反映）、API詳細全体（projects/tasks/notifications/adminの31ファイルに加え、auth/usersの17ファイル）である。

横断的なクエリ説明の修正対象は、`api/projects/01_get_projects.md`、`api/admin/05_get_admin_projects.md`、`api/tasks/01_get_project_tasks.md`、`api/tasks/03_get_task.md`、`api/tasks/06_get_task_comments.md`、`api/projects/06_get_project_members.md`、`api/tasks/08_patch_comment.md`、`api/tasks/09_delete_comment.md` である。

## 2. 機械検査手順

リポジトリルートで実行する。以下の検査は読み取り専用で、`.env` を読み込まない。

### 2.1 差分と古い表現

```bash
git diff --check
rg -n -i --glob '*.md' --glob '!quality_check.md' '別担当作成中|通知API.*未作成|通知.*作成中|API.*未作成' detailed_design basic_design requirements
rg -n --glob '*.md' 'repository.*(SELECT .* FROM|INSERT INTO|UPDATE .* SET|DELETE FROM|FOR UPDATE)|selectinload|is_due_today' detailed_design/api
```

1つ目は出力なしで合格、2つ目は設計書に該当表現がないことを確認する。要件の機能説明に含まれる「実装予定」等を機械的に削除対象とはせず、現行設計の状態を示す文書だけを確認する。
3つ目は、例外であるhealth以外のrepository直接CRUD、通知のORM遅延ロード、独立した日時判定関数が残っていないことを確認する。検出した場合は `08_db_functions.md` の契約へ置き換える。

### 2.2 相対リンク

Markdownのリンクから外部URL・アンカーのみのリンクを除外し、相対パスのファイルが存在することを確認する。

```bash
python3 - <<'PY'
from pathlib import Path
import re

root = Path('.')
errors = []
for source in root.rglob('*.md'):
    for target in re.findall(r'\[[^]]+\]\(([^)]+)\)', source.read_text()):
        target = target.split('#', 1)[0].strip()
        if not target or re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', target):
            continue
        if not (source.parent / target).resolve().exists():
            errors.append(f'{source}: {target}')
if errors:
    print('\n'.join(errors))
    raise SystemExit(1)
print('relative links: OK')
PY
```

アンカー名の正当性は見出し変更時にレビューで確認する。外部URLの疎通は本検査の対象外とする。

### 2.3 Mermaidコードブロック

Mermaidブロックの開始・終了漏れを確認し、構文検査が可能な環境では Mermaid CLI でも検証する。

```bash
bad=0; while IFS= read -r -d '' file; do count=$(awk '/^```/{fences++} END {print fences % 2}' "$file"); if [ "$count" -ne 0 ]; then echo "$file"; bad=1; fi; done < <(find detailed_design basic_design -type f -name '*.md' -print0); test "$bad" -eq 0 && echo 'Mermaid fences: OK'
npx --yes @mermaid-js/mermaid-cli -i <(printf 'flowchart LR\n  A-->B\n') -o /tmp/mermaid-check.svg
```

CLIが利用できない場合はフェンス検査までを実施し、構文検査未実施であることを結果に明記する。`/tmp` の出力は一時ファイルである。

### 2.4 エンドポイント・環境変数・エラーコード

重複候補を抽出し、正規の定義と照合する。重複そのものは参照記載として許容し、同一キーに異なる定義がある場合だけ不整合とする。

```bash
rg -o --glob '*.md' '(GET|POST|PATCH|PUT|DELETE) /api[^ `。））]*' detailed_design basic_design | sort > /tmp/design-endpoints.txt
rg -o --glob '*.md' '\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b' detailed_design basic_design | sort -u > /tmp/design-env-candidates.txt
rg -o --glob '*.md' '\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b' basic_design/04_api.md | sort -u > /tmp/design-error-candidates.txt
```

SP/FNのSQLSTATE対応は次の検査で一意性を確認する。

```bash
rg -n '`P0[0-9]{3}`' detailed_design/database/08_db_functions.md
rg -n '`P0[0-9]{3}`|`(DUPLICATE_USERNAME|DUPLICATE_EMAIL|ALREADY_MEMBER|OWNER_CANNOT_BE_REMOVED|TASK_CONFLICT|ASSIGNEE_INACTIVE|SELF_MODIFICATION_NOT_ALLOWED|LAST_ADMIN_REQUIRED|INVALID_STATE)`' basic_design/04_api.md
```

`08_db_functions.md` §4の `P0001`〜`P0009` と `basic_design/04_api.md` §4.2の業務コードが1対1で対応し、Pコードに重複・欠番がないことを確認する。参照系の不存在・所属不可はPコードを発生させず、FNの空集合/falseからAPI層が404/403へ変換する。

エンドポイントは `detailed_design/README.md` と `basic_design/04_api.md`、環境変数は `detailed_design/infra/04_env_config.md`、エラーコードは `basic_design/04_api.md` を正とする。候補に正の定義がないもの、同一エンドポイントに異なるHTTPメソッド・パスが割り当てられたものを修正対象としてIssueまたはPRに記録する。

## 3. Issue #12 シナリオテスト結果

2026-09-04に本Issueの変更後状態で実施した結果を記録する。

| 検査 | 結果 |
|------|------|
| `git diff --check` | 合格 |
| SP/FN対象一覧とテーブル別repository契約 | 合格（50オブジェクト、主要5テーブル詳細でシグネチャ照合） |
| RBACの事実判定とHTTP変換 | 合格（`fn_is_project_member` / `fn_get_project` / `fn_get_comment_with_task`） |
| SQLSTATE `P0001`〜`P0009` とAPIエラーコード | 合格（重複・欠番なし） |
| API詳細48ファイルのSP/FN契約節 | 合格（system/healthはSELECT 1例外） |
| SQLレベル結合テスト設計への移行 | 合格（実装前のため実DB実行は未実施） |
| 現行設計の古い表現検索 | `detailed_design`・`basic_design`・`requirements` で該当なし |
| 相対リンク（ローカルファイル） | 合格 |
| Mermaidフェンス対応 | 合格 |
| Mermaid CLI構文検査 | 未実施（依存パッケージ未導入のため。フェンス検査で代替） |
| エンドポイント・環境変数・エラーコード候補 | 正の定義ファイルと照合する手順を追加。候補抽出結果はレビュー時に確認可能 |

## 4. 不明点・要検討事項

- Mermaid CLIをCIへ導入するかは、実装リポジトリ化後のCI設計で要検討とする。
- Markdownアンカーの存在検査は今回の手順では未自動化であり、見出し変更を含むPRのレビューで確認する。
- エンドポイント・環境変数・エラーコードの完全な重複排除は、正規定義を機械可読な一覧へ分離する段階で自動化する。
- 実装コードと実SQLが未作成の設計フェーズのため、`pytest-postgresql` を使う結合テストはテスト設計・テスト名までを確認し、実DBでの実行は実装フェーズへ持ち越す。これは網羅できない理由である。
- PL/pgSQL分岐カバレッジのCI計測ツールは候補が限定的なため要検討とする。
