#!/usr/bin/env bash

set -euo pipefail

REVIEWED_LABEL="reviewed"
# ブロックメッセージが案内するラベル付与コマンドのプレースホルダ。
# 実行時に `gh repo view` 等でリポジトリ名を解決しない理由は下記コメント参照。
REPO_PLACEHOLDER="<owner>/<repo>"

# issueを閉じるPR(本文のClosing keywordsでリンクされたPR)とそのラベルを取得するGraphQLクエリ。
# includeClosedPrs:true でクローズ済み・マージ済みのPRもリンク先として扱う。
LINKED_PR_QUERY='query($owner:String!,$repo:String!,$number:Int!,$cursor:String){repository(owner:$owner,name:$repo){issue(number:$number){closedByPullRequestsReferences(first:100,after:$cursor,includeClosedPrs:true){pageInfo{hasNextPage endCursor}nodes{number labels(first:50){nodes{name}}}}}}}'

# 想定外のエラー(パイプラインの異常終了等)は必ずブロック側に倒す(fail-close)。
# Claude CodeのPreToolUse hookはexit 2のみをブロックとして扱い、それ以外の非ゼロ終了は
# 非ブロッキングエラーとしてツール実行を継続してしまうため、想定外の失敗でも確実にexit 2にする。
trap 'echo "ブロック: hookスクリプト内で想定外のエラーが発生したため、安全側でブロックします。" >&2; exit 2' ERR

if ! command -v jq >/dev/null 2>&1; then
	echo "ブロック: hookの入力を検証するjqが見つからないため、fail-closeします。" >&2
	exit 2
fi

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
#
# 【検出できないケース(既知の限界)】この判定は誤検知の抑制が目的であり、意図的な回避を防ぐ
# ものではない。以下のような形は `gh` の直前に区切り文字が来ないため検出されない。
#   - クォートで包まれたコマンド: bash -c "gh pr merge 123 --squash" / sh -c 'gh issue close 123'
#   - コマンド文字列をファイルへ書き出してから実行する形: cat > run.sh ...; bash run.sh
#     (hookはBashツールのcommand文字列のみを見ており、ファイルの中身は読まない)
#   - `gh` の前に別コマンドが付く形: sudo gh pr merge 123 / env FOO=1 gh pr merge 123
# 本hookは事故防止のガードレール(通常operationでの誤操作・誤検知の防止)であり、
# 迂回を意図した操作までは防げない。検出範囲の拡張は別途 #390 で検討する。
CMD_BOUNDARY='(^|[;&|(`])[[:space:]]*'

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/issue-close-argument-parser.sh"

# 対象PRにreviewedラベルが付与されているか確認する。
# gh呼び出しに失敗した場合は必ずブロックする(fail-close)。
# 0=ラベルあり / 1=ラベルなし / 2=判定不能
has_reviewed_pr_label() {
	local number="$1" # 空文字ならカレントブランチのPRで判定する
	local labels_json

	if [[ -n "$number" ]]; then
		labels_json=$(gh pr view "$number" --json labels 2>/dev/null) || return 2
	else
		labels_json=$(gh pr view --json labels 2>/dev/null) || return 2
	fi

	if jq -e --arg label "$REVIEWED_LABEL" '.labels // [] | any(.name == $label)' <<<"$labels_json" >/dev/null 2>&1; then
		return 0
	fi
	return 1
}

# コマンド引数で明示されたrepoを優先し、無ければカレントリポジトリを解決する。
# 解決できない場合は失敗を返す(fail-close)。
resolve_repo() {
	local explicit_repo="$1"
	if [[ -n "$explicit_repo" ]]; then
		printf '%s' "$explicit_repo"
		return 0
	fi

	gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || return 1
}

# issueを閉じるPR(本文のClosing keywordsでリンクされたPR)にreviewedラベルがあるか確認する。
# `reviewed` はレビュー主体がPRへ付与するラベルであり、issue側には付与されない運用のため、
# issue closeの可否はissue自身ではなくリンクPRのラベルで判定する(#401)。
# 0=リンクPRにreviewedあり / 1=リンクPRはあるがreviewedなし / 3=リンクPRなし / 2=判定不能
linked_pr_has_reviewed_label() {
	local issue_number="$1"
	local explicit_repo="$2"
	local repo owner name response cursor=""

	if [[ -z "$issue_number" ]]; then
		return 2
	fi

	repo=$(resolve_repo "$explicit_repo") || return 2
	if [[ "$repo" != */* ]]; then
		return 2
	fi
	owner="${repo%%/*}"
	name="${repo#*/}"

	while true; do
		if [[ -n "$cursor" ]]; then
			response=$(gh api graphql -f query="$LINKED_PR_QUERY" \
				-F owner="$owner" -F repo="$name" -F number="$issue_number" -F cursor="$cursor" 2>/dev/null) || return 2
		else
			response=$(gh api graphql -f query="$LINKED_PR_QUERY" \
				-F owner="$owner" -F repo="$name" -F number="$issue_number" 2>/dev/null) || return 2
		fi

		if ! jq -e '
			.data.repository.issue.closedByPullRequestsReferences
			| (type == "object")
			and (.nodes | type == "array")
			and (.pageInfo | type == "object")
			and (.pageInfo.hasNextPage | type == "boolean")
		' <<<"$response" >/dev/null 2>&1; then
			return 2
		fi

		if jq -e --arg label "$REVIEWED_LABEL" '
			.data.repository.issue.closedByPullRequestsReferences.nodes
			| any((.labels.nodes // []) | any(.name == $label))
		' <<<"$response" >/dev/null 2>&1; then
			return 0
		fi

		if ! jq -e '.data.repository.issue.closedByPullRequestsReferences.pageInfo.hasNextPage' \
			<<<"$response" >/dev/null 2>&1; then
			return 1
		fi
		cursor=$(jq -r '.data.repository.issue.closedByPullRequestsReferences.pageInfo.endCursor // empty' <<<"$response")
		[[ -n "$cursor" ]] || return 2
	done
}

# `gh pr merge` を検出したら、対象PRにreviewedラベルがある場合のみ許可する。
if grep -Eq "${CMD_BOUNDARY}gh[^;&|[:cntrl:]]*[[:space:]]+pr[[:space:]]+merge([[:space:]]|\$)" <<<"$command_for_match"; then
	merge_segment=$(grep -Eo "${CMD_BOUNDARY}gh[^;&|[:cntrl:]]*[[:space:]]+pr[[:space:]]+merge[^;&|[:cntrl:]]*" <<<"$command_for_match" | head -1)
	pr_number=$(grep -Eo '[0-9]+' <<<"$merge_segment" | head -1 || true)

	status=0
	has_reviewed_pr_label "$pr_number" || status=$?

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

# `gh issue close` を検出したら、そのissueを閉じるPRにreviewedラベルがある場合のみ許可する。
if grep -Eq "${CMD_BOUNDARY}gh[^;&|[:cntrl:]]*[[:space:]]+issue[[:space:]]+close([[:space:]]|\$)" <<<"$command_for_match"; then
	close_segment=$(grep -Eo "${CMD_BOUNDARY}gh[^;&|[:cntrl:]]*[[:space:]]+issue[[:space:]]+close[^;&|[:cntrl:]]*" <<<"$command_for_match" | head -1)
	status=0
	parse_issue_close_command "$close_segment" || status=$?
	issue_number="${PARSED_ISSUE_NUMBER:-}"
	explicit_repo="${PARSED_REPO:-}"
	if [[ "$status" -eq 0 ]]; then
		linked_pr_has_reviewed_label "$issue_number" "$explicit_repo" || status=$?
	fi

	if [[ "$status" -eq 0 ]]; then
		exit 0
	elif [[ "$status" -eq 2 ]]; then
		echo "ブロック: 対象issueのリンクPR取得(gh api graphql)に失敗、またはissue番号・リポジトリを特定できなかったため、安全側でcloseをブロックします。" >&2
		exit 2
	elif [[ "$status" -eq 3 ]]; then
		echo "ブロック: issueを閉じるPRが見つかりません。PR本文に 'Closes #<Issue番号>' を記載してissueとリンクしてください（リンクしたPRがマージされればissueは自動closeされます）。" >&2
		exit 2
	else
		# issues/<番号>/labels のREST APIエンドポイントはissueにもPRにも使えるため、
		# PR用メッセージ(#386)と同じ `gh api` 形式に統一する。
		echo "ブロック: 対象issueを閉じるPRに '${REVIEWED_LABEL}' ラベルがありません。.agents/review-policy.md に沿ったレビューで「受入可」のコメントを投稿したうえで、PR作成者以外がPRへラベルを付与してください（例: gh api -X POST repos/${REPO_PLACEHOLDER}/issues/<PR番号>/labels -f \"labels[]=${REVIEWED_LABEL}\"）。" >&2
		exit 2
	fi
fi

# `gh pr merge` の代替経路となるGitHub API直叩き(PUT .../pulls/<番号>/merge)を塞ぐ。
# こちらはreviewedラベルの有無にかかわらず禁止し、mergeは `gh pr merge` に一本化する。
api_put_regex="${CMD_BOUNDARY}gh[^;&|[:cntrl:]]*[[:space:]]+api[^;&|[:cntrl:]]*((--method[=[:space:]]+|-X[[:space:]]+)PUT[^;&|[:cntrl:]]*repos/[^[:space:];|&]+/pulls/[0-9]+/merge|repos/[^[:space:];|&]+/pulls/[0-9]+/merge[^;&|[:cntrl:]]*((--method[=[:space:]]+|-X[[:space:]]+)PUT))"
if grep -Eiq "$api_put_regex" <<<"$command_for_match"; then
	echo "ブロック: GitHub API経由のPR mergeは禁止されています。レビュー完了後に '${REVIEWED_LABEL}' ラベルを付与し、gh pr merge を使用してください。" >&2
	exit 2
fi

# `gh issue close` の代替経路となる `gh issue edit --state closed` を塞ぐ。
if grep -Eiq "${CMD_BOUNDARY}gh[^;&|[:cntrl:]]*[[:space:]]+issue[^;&|[:cntrl:]]*[[:space:]]+edit[^;&|[:cntrl:]]+[[:space:]]+--state([=[:space:]]+)closed([[:space:]]|\$)" <<<"$command_for_match"; then
	echo "ブロック: --state closedによるIssue closeは禁止されています。レビュー完了後に '${REVIEWED_LABEL}' ラベルを付与し、gh issue close を使用してください。" >&2
	exit 2
fi

exit 0
