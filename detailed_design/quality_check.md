# 詳細設計 品質検査手順・結果

Issue #7（[フェーズ3: 設計書の現行化と品質基準を整備する](https://github.com/oikawa-d/task_management/issues/7)）で定める、設計書の現行性・章構成・表記整合性の確認手順である。対象はMarkdown設計書であり、実装コードや `.env` は検査対象にしない。

## 1. 必須章と対象ファイル

APIの必須章は「関連ドキュメント／概要／入出力／エラー／処理シーケンス／処理フロー／関数詳細／関数相関図／データ遷移図／テスト設計／不明点・要検討事項」とする。Batch・履歴・インフラは、処理対象に応じて同じ章を持ち、参照だけの章は「状態遷移なし」と明記する。

| 対象ファイル | 章の追跡方法・Issue #7で補完した箇所 |
|--------------|----------------------------------------|
| `api/notifications/01_get_notifications.md`、`02_get_notifications_unread_count.md` | 全必須章あり。`selectinload` の追加SELECTとクエリ回数を記載 |
| `api/notifications/03_patch_notification_read.md`、`04_post_notifications_read_all.md` | 処理フロー・関数相関図・データ遷移図・クエリ／トランザクション・不明点を追加 |
| `batch/00_overview.md`、`01_scheduler.md`、`02_due_notification_job.md` | 全体方針・スケジューラ・ジョブの順に、入力／責務／例外／データ遷移を相互参照する |
| `database/11_table_api_history.md`、`12_table_batch_history.md` | テーブルI/O・記録シーケンス・状態遷移・履歴操作の責務と例外を追跡する |
| `log/00_history.md` | API／Batch／標準出力の記録対象、入力／出力、データ遷移を一つの流れで追跡する |
| `infra/08_dockerfile_batch.md` | BatchコンテナのI/O・起動シーケンス・分岐・関数／要素責務・データ遷移を追加 |
| `screen/06_dashboard.md` | 通知APIの参照先を現行詳細設計へ更新。通知ベル／パネルのUI・API連携を追跡する |

横断的なクエリ説明の修正対象は、`api/projects/01_get_projects.md`、`api/admin/05_get_admin_projects.md`、`api/tasks/01_get_project_tasks.md`、`api/tasks/03_get_task.md`、`api/tasks/06_get_task_comments.md`、`api/projects/06_get_project_members.md`、`api/tasks/08_patch_comment.md`、`api/tasks/09_delete_comment.md` である。

## 2. 機械検査手順

リポジトリルートで実行する。以下の検査は読み取り専用で、`.env` を読み込まない。

### 2.1 差分と古い表現

```bash
git diff --check
rg -n -i --glob '*.md' --glob '!quality_check.md' '別担当作成中|通知API.*未作成|通知.*作成中|API.*未作成' detailed_design basic_design requirements
```

1つ目は出力なしで合格、2つ目は設計書に該当表現がないことを確認する。要件の機能説明に含まれる「実装予定」等を機械的に削除対象とはせず、現行設計の状態を示す文書だけを確認する。

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

エンドポイントは `detailed_design/README.md` と `basic_design/04_api.md`、環境変数は `detailed_design/infra/04_env_config.md`、エラーコードは `basic_design/04_api.md` を正とする。候補に正の定義がないもの、同一エンドポイントに異なるHTTPメソッド・パスが割り当てられたものを修正対象としてIssueまたはPRに記録する。

## 3. Issue #7 検査結果

2026-09-04に本Issueの変更後状態で実施した結果を記録する。

| 検査 | 結果 |
|------|------|
| `git diff --check` | 合格 |
| 現行設計の古い表現検索 | `detailed_design`・`basic_design`・`requirements` で該当なし |
| 相対リンク（ローカルファイル） | 合格 |
| Mermaidフェンス対応 | 合格 |
| Mermaid CLI構文検査 | 未実施（依存パッケージ未導入のため。フェンス検査で代替） |
| エンドポイント・環境変数・エラーコード候補 | 正の定義ファイルと照合する手順を追加。候補抽出結果はレビュー時に確認可能 |

## 4. 不明点・要検討事項

- Mermaid CLIをCIへ導入するかは、実装リポジトリ化後のCI設計で要検討とする。
- Markdownアンカーの存在検査は今回の手順では未自動化であり、見出し変更を含むPRのレビューで確認する。
- エンドポイント・環境変数・エラーコードの完全な重複排除は、正規定義を機械可読な一覧へ分離する段階で自動化する。
