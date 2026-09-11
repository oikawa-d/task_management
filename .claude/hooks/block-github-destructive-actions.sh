#!/usr/bin/env bash

set -euo pipefail

REVIEWED_LABEL="reviewed"
# ブロックメッセージが案内するラベル付与コマンドのプレースホルダ。
# 実行時に `gh repo view` 等でリポジトリ名を解決しない理由は下記コメント参照。
REPO_PLACEHOLDER="<owner>/<repo>"

# 想定外のエラー(パイプラインの異常終了等)は必ずブロック側に倒す(fail-close)。
# Claude CodeのPreToolUse hookはexit 2のみをブロックとして扱い、それ以外の非ゼロ終了は
# 非ブロッキングエラーとしてツール実行を継続してしまうため、想定外の失敗でも確実にexit 2にする。
trap 'echo "ブロック: hookスクリプト内で想定外のエラーが発生したため、安全側でブロックします。" >&2; exit 2' ERR

input=$(cat)
tool_name=$(jq -r '.tool_name // empty' <<<"$input")

if [[ "$tool_name" != "Bash" ]]; then
	exit 0
fi

command=$(jq -r '.tool_input.command // empty' <<<"$input")

# heredoc本文(<<WORD ... WORD / <<'WORD' ... WORD / <<-WORD ... WORD)を検査対象から除去する。
# heredoc本文はシェルに解釈されるコマンドではなく、単なるテキストデータのため、
# 本文に "gh pr merge" 等の文字列が含まれていても誤検知してはならない(#388)。
# heredocの開始行自体(<<WORDの行)は残すため、開始行に別コマンドが同居していても検査は継続される。
strip_heredocs() {
	awk '
		BEGIN { in_heredoc = 0; strip_tabs = 0; word = "" }
		{
			if (in_heredoc) {
				line = $0
				if (strip_tabs) { sub(/^\t+/, "", line) }
				if (line == word) {
					in_heredoc = 0
					print $0
				}
				next
			}
			print $0
			if (match($0, /<<-?[[:space:]]*"?'"'"'?[A-Za-z_][A-Za-z0-9_]*"?'"'"'?/)) {
				tok = substr($0, RSTART, RLENGTH)
				strip_tabs = (tok ~ /^<<-/) ? 1 : 0
				gsub(/<<-?[[:space:]]*/, "", tok)
				gsub(/["'"'"']/, "", tok)
				word = tok
				in_heredoc = 1
			}
		}
	'
}

command_for_match=$(strip_heredocs <<<"$command")

# コマンド位置の判定を厳格化する(#388)。
# `gh` が実際にコマンドとして実行され得る位置(行頭、または `;` `&` `|` `` ` `` `(` の直後)に
# ある場合のみを対象とし、クォート内・他コマンドの引数・コメント中の文字列は対象外にする。
# (完全なシェル構文解析ではないため、あくまで現実的な緩和策。判定に迷う場合はブロック側に倒す。)
CMD_BOUNDARY='(^|[;&|(`])[[:space:]]*'

# 対象(PR番号 or Issue番号)にreviewedラベルが付与されているか確認する。
# gh呼び出しに失敗した場合は必ずブロックする(fail-close)。
has_reviewed_label() {
	local kind="$1" # pr | issue
	local number="$2" # 空文字ならカレントブランチ(prのみ)/省略不可(issue)
	local labels_json

	if [[ "$kind" == "pr" ]]; then
		if [[ -n "$number" ]]; then
			labels_json=$(gh pr view "$number" --json labels 2>/dev/null) || return 2
		else
			labels_json=$(gh pr view --json labels 2>/dev/null) || return 2
		fi
	else
		if [[ -z "$number" ]]; then
			return 2
		fi
		labels_json=$(gh issue view "$number" --json labels 2>/dev/null) || return 2
	fi

	if jq -e --arg label "$REVIEWED_LABEL" '.labels // [] | any(.name == $label)' <<<"$labels_json" >/dev/null 2>&1; then
		return 0
	fi
	return 1
}

# `gh pr merge` を検出したら、対象PRにreviewedラベルがある場合のみ許可する。
if grep -Eq "${CMD_BOUNDARY}gh[^;&|[:cntrl:]]*[[:space:]]+pr[[:space:]]+merge([[:space:]]|\$)" <<<"$command_for_match"; then
	merge_segment=$(grep -Eo "${CMD_BOUNDARY}gh[^;&|[:cntrl:]]*[[:space:]]+pr[[:space:]]+merge[^;&|[:cntrl:]]*" <<<"$command_for_match" | head -1)
	pr_number=$(grep -Eo '[0-9]+' <<<"$merge_segment" | head -1 || true)

	status=0
	has_reviewed_label "pr" "$pr_number" || status=$?

	if [[ "$status" -eq 0 ]]; then
		exit 0
	elif [[ "$status" -eq 2 ]]; then
		echo "ブロック: 対象PRの情報取得(gh pr view)に失敗したため、安全側でmergeをブロックします。ネットワークやPR番号を確認してください。" >&2
		exit 2
	else
		# `gh pr edit --add-label` はProjects(classic)廃止に伴うGraphQLエラー(projectCards参照)で
		# 失敗するため案内しない(#386)。REST APIの `gh api` 経由であれば同エンドポイントは
		# PR・issueの両方に使えて安定して成功するため、こちらを案内する。
		echo "ブロック: 対象PRに '${REVIEWED_LABEL}' ラベルがありません。.agents/review-policy.md に沿ったレビューで「受入可」のコメントを投稿したうえで、PR作成者以外がラベルを付与してください（例: gh api -X POST repos/${REPO_PLACEHOLDER}/issues/<PR番号>/labels -f \"labels[]=${REVIEWED_LABEL}\"）。" >&2
		exit 2
	fi
fi

# `gh issue close` を検出したら、対象issueにreviewedラベルがある場合のみ許可する。
if grep -Eq "${CMD_BOUNDARY}gh[^;&|[:cntrl:]]*[[:space:]]+issue[[:space:]]+close([[:space:]]|\$)" <<<"$command_for_match"; then
	close_segment=$(grep -Eo "${CMD_BOUNDARY}gh[^;&|[:cntrl:]]*[[:space:]]+issue[[:space:]]+close[^;&|[:cntrl:]]*" <<<"$command_for_match" | head -1)
	issue_number=$(grep -Eo '[0-9]+' <<<"$close_segment" | head -1 || true)

	status=0
	has_reviewed_label "issue" "$issue_number" || status=$?

	if [[ "$status" -eq 0 ]]; then
		exit 0
	elif [[ "$status" -eq 2 ]]; then
		echo "ブロック: 対象issueの情報取得(gh issue view)に失敗、またはissue番号を特定できなかったため、安全側でcloseをブロックします。" >&2
		exit 2
	else
		# issues/<番号>/labels のREST APIエンドポイントはissueにもPRにも使えるため、
		# PR用メッセージ(#386)と同じ `gh api` 形式に統一する。
		echo "ブロック: 対象issueに '${REVIEWED_LABEL}' ラベルがありません。.agents/review-policy.md に沿ったレビューで「受入可」のコメントを投稿したうえで、PR作成者以外がラベルを付与してください（例: gh api -X POST repos/${REPO_PLACEHOLDER}/issues/<Issue番号>/labels -f \"labels[]=${REVIEWED_LABEL}\"）。" >&2
		exit 2
	fi
fi

exit 0
