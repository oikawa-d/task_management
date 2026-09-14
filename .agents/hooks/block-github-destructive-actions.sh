#!/usr/bin/env bash

set -euo pipefail

REVIEWED_LABEL="reviewed"
# ブロックメッセージが案内するラベル付与コマンドのプレースホルダ。
# 実行時に `gh repo view` 等でリポジトリ名を解決しない理由は下記コメント参照。
REPO_PLACEHOLDER="<owner>/<repo>"

# 操作対象(PR/Issue)の解析は共通ライブラリへ切り出している。
# jq不在時のfail-close(#339)を検証できるよう、外部コマンドに依存せずシェル組み込みで解決する。
HOOK_DIR=$(cd "${BASH_SOURCE[0]%/*}" 2>/dev/null && pwd) || HOOK_DIR="."
# shellcheck source=lib/gh-substitution-parse.sh
source "$HOOK_DIR/lib/gh-substitution-parse.sh"
# shellcheck source=lib/gh-command-parse.sh
source "$HOOK_DIR/lib/gh-command-parse.sh"
# shellcheck source=lib/gh-target-parse.sh
source "$HOOK_DIR/lib/gh-target-parse.sh"
# shellcheck source=lib/gh-api-parse.sh
source "$HOOK_DIR/lib/gh-api-parse.sh"

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
		BEGIN {
			in_heredoc = 0
			strip_tabs = 0
			word = ""
			heredoc_quoted = 0
			quote = ""
			arith_depth = 0
			parameter_depth = 0
			single_quote = sprintf("%c", 39)
			double_quote = sprintf("%c", 34)
		}
		{
			if (in_heredoc) {
				line = $0
				if (strip_tabs) { sub(/^\t+/, "", line) }
				if (line == word) {
					in_heredoc = 0
					print $0
					next
				}
				if (!heredoc_quoted && has_command_substitution($0)) { exit 4 }
				next
			}
			print $0
			# 引用符内・エスケープされた `<<` はheredoc開始ではない。
			# quoteは行をまたいで保持するため、複数行の文字列も正しく扱う。
			line = $0
			for (i = 1; i <= length(line); i++) {
				char = substr(line, i, 1)
				if (quote == "single") {
					if (char == single_quote) { quote = "" }
					continue
				}
				if (quote == "double") {
					if (char == "\\") { i++ }
					else if (char == double_quote) { quote = "" }
					continue
				}
				if (char == "\\") { i++; continue }
				if (char == single_quote) { quote = "single"; continue }
				if (char == double_quote) { quote = "double"; continue }
				# コメント中の記号はshell構文ではないため、heredoc開始として扱わない。
				if (char == "#" && (i == 1 || substr(line, i - 1, 1) ~ /[[:space:];|&()<>]/)) { break }
				# パラメータ展開内の `<<` は文字列操作のパターンであり、heredocではない。
				if (parameter_depth > 0) {
					if (char == "{") { parameter_depth++ }
					else if (char == "}") { parameter_depth-- }
					continue
				}
				if (char == "$" && substr(line, i + 1, 1) == "{") {
					parameter_depth = 1
					i++
					continue
				}
				# 算術式 `$(( ))` 内のシフト演算子はheredoc開始ではない。
				# `$((1<<shift))` を開始語と誤認すると、終端語が現れないため
				# 以降の全行が検査対象から消え、ブロックを回避できてしまう。
				if (arith_depth > 0) {
					if (char == "(") { arith_depth++ }
					else if (char == ")") { arith_depth-- }
					continue
				}
				if (char == "$" && substr(line, i + 1, 2) == "((") {
					arith_depth = 2
					i += 2
					continue
				}
				if (char != "<" || substr(line, i + 1, 1) != "<") { continue }

				j = i + 2
				strip_tabs = 0
				if (substr(line, j, 1) == "-") {
					strip_tabs = 1
					j++
				}
				while (substr(line, j, 1) ~ /[[:space:]]/) { j++ }

				word = ""
				heredoc_quoted = 0
				marker_quote = substr(line, j, 1)
				if (marker_quote == single_quote || marker_quote == double_quote) {
					heredoc_quoted = 1
					j++
					while (j <= length(line) && substr(line, j, 1) != marker_quote) {
						word = word substr(line, j, 1)
						j++
					}
					if (j > length(line)) { word = "" }
				} else if (substr(line, j, 1) ~ /[A-Za-z_]/) {
					while (substr(line, j, 1) ~ /[A-Za-z0-9_]/) {
						word = word substr(line, j, 1)
						j++
					}
				}
				if (word != "") {
					in_heredoc = 1
					break
				}
			}
		}
		function has_command_substitution(text, i, char) {
			for (i = 1; i <= length(text); i++) {
				char = substr(text, i, 1)
				if (char == "\\") { i++; continue }
				if (char == "`") { return 1 }
				if (char == "$" && substr(text, i + 1, 1) == "(") { return 1 }
			}
			return 0
		}
		END {
			# 終端語が現れないheredocは以降の行を検査できないため、解析不能として扱う。
			if (in_heredoc) { exit 3 }
		}
	'
}

heredoc_status=0
command_for_match=$(strip_heredocs <<<"$command") || heredoc_status=$?
if (( heredoc_status != 0 )); then
	echo "ブロック: heredocの終端語が見つからず入力を解析できないため、安全側でブロックします。" >&2
	exit 2
fi
# シェルのバックスラッシュ改行はトークン間の空白として扱われるため、
# 操作名が改行で分断されても同じコマンドとして検査する。
command_for_match=${command_for_match//\\$'\n'/}

# コマンド位置の判定を厳格化する(#388)。
# 引用符外のコマンド区切り文字とコマンド置換で実行単位へ分割し、複合構文の予約語を
# 読み飛ばした実行位置が `gh` の場合のみ対象にする。
#
# 【検出できないケース(既知の限界)】この判定は誤検知の抑制が目的であり、意図的な回避を防ぐ
# ものではない。以下のような形は `gh` の直前に区切り文字が来ないため検出されない。
#   - クォートで包まれたコマンド: bash -c "gh pr merge 123 --squash" / sh -c 'gh issue close 123'
#   - コマンド文字列をファイルへ書き出してから実行する形: cat > run.sh ...; bash run.sh
#     (hookはBashツールのcommand文字列のみを見ており、ファイルの中身は読まない)
#   - 未対応のラッパーコマンドが `gh` の前に付く形: sudo gh pr merge 123
# 本hookは事故防止のガードレール(通常operationでの誤操作・誤検知の防止)であり、
# 迂回を意図した操作までは防げない。検出範囲の拡張は別途 #390 で検討する。

# 対象PRにreviewedラベルが付与されているか確認する。
# gh呼び出しに失敗した場合は必ずブロックする(fail-close)。
# 0=ラベルあり / 1=ラベルなし / 2=判定不能
has_reviewed_pr_label() {
	local selector="$1" # 空文字ならカレントブランチのPRで判定する(番号・URL・ブランチ名を受け付ける)
	local repo="$2" # 空文字ならカレントリポジトリ
	local labels_json
	local -a args=()

	if [[ -n "$selector" ]]; then
		args+=("$selector")
	fi
	args+=(--json labels)
	# `--repo` やURLで別リポジトリが指定された場合、同じリポジトリのPRを照会しなければ
	# 実対象とは別のPRのreviewed状態で許可・拒否してしまう。
	if [[ -n "$repo" ]]; then
		args+=(--repo "$repo")
	fi

	labels_json=$(gh pr view "${args[@]}" 2>/dev/null) || return 2

	if jq -e --arg label "$REVIEWED_LABEL" '.labels // [] | any(.name == $label)' <<<"$labels_json" >/dev/null 2>&1; then
		return 0
	fi
	return 1
}

# 解析済みの対象リポジトリを優先し、指定が無ければカレントリポジトリを解決する。
# 解析前のコマンド文字列をgrepすると、コメントや引用文字列に含まれる `--repo` を実オプションと
# 誤認して別リポジトリへ照会してしまうため、トークン解析の結果のみを使う。
resolve_repo() {
	local parsed_repo="$1"

	if [[ -n "$parsed_repo" ]]; then
		printf '%s' "$parsed_repo"
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
	local parsed_repo="$2" # コマンドで明示されたリポジトリ(空文字ならカレントリポジトリ)
	local repo owner name host response cursor="" linked_pr_count=0 page_node_count
	local -a graphql_args=(api graphql -f "query=$LINKED_PR_QUERY")

	if [[ -z "$issue_number" ]]; then
		return 2
	fi

	repo=$(resolve_repo "$parsed_repo") || return 2
	gh_split_repo_reference "$repo" || return 2
	owner="$GH_REPO_OWNER"
	name="$GH_REPO_NAME"
	host="$GH_REPO_HOST"
	if [[ -z "$owner" || -z "$name" ]]; then
		return 2
	fi
	if [[ -n "$host" ]]; then
		graphql_args+=(--hostname "$host")
	fi
	while true; do
		local -a request_args=("${graphql_args[@]}" -F "owner=$owner" -F "repo=$name" -F "number=$issue_number")
		if [[ -n "$cursor" ]]; then
			request_args+=(-F "cursor=$cursor")
		fi
		response=$(gh "${request_args[@]}" 2>/dev/null) || return 2

		# GraphQLはdataとerrorsを同時に返す部分成功があるため、トップレベルの
		# errorsフィールドが存在する応答は判定不能として安全側に倒す。
		if ! jq -e 'type == "object" and (has("errors") | not)' <<<"$response" >/dev/null 2>&1; then
			return 2
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
		page_node_count=$(jq -r '.data.repository.issue.closedByPullRequestsReferences.nodes | length' <<<"$response")
		linked_pr_count=$(( linked_pr_count + page_node_count ))

		if ! jq -e '.data.repository.issue.closedByPullRequestsReferences.pageInfo.hasNextPage' \
			<<<"$response" >/dev/null 2>&1; then
			if (( linked_pr_count == 0 )); then
				return 3
			fi
			return 1
		fi
		cursor=$(jq -r '.data.repository.issue.closedByPullRequestsReferences.pageInfo.endCursor // empty' <<<"$response")
		[[ -n "$cursor" ]] || return 2
	done
}

# `gh pr merge` の1件を検査する。戻り値0は許可、2はブロックを表す。
check_merge_segment() {
	local merge_segment="$1"
	local parse_status=0 status=0
	gh_parse_target "pr-merge" "$merge_segment" || parse_status=$?
	if (( GH_COMMAND_PREFIX_UNCERTAIN )); then
		echo "ブロック: ghの前置ラッパーを解析できないコマンド形式のため、安全側でmergeをブロックします。" >&2
		return 2
	fi
	if [[ "$parse_status" -ne 0 ]]; then
		echo "ブロック: 対象PRを特定できないコマンド形式のため、安全側でmergeをブロックします。PR番号・URL・ブランチ名を位置引数で指定してください。" >&2
		return 2
	fi

	status=0
	has_reviewed_pr_label "$GH_TARGET_SELECTOR" "$GH_TARGET_REPO" || status=$?

	if [[ "$status" -eq 0 ]]; then
		return 0
	elif [[ "$status" -eq 2 ]]; then
		echo "ブロック: 対象PRの情報取得(gh pr view)に失敗したため、安全側でmergeをブロックします。ネットワークやPR番号を確認してください。" >&2
		return 2
	else
		# `gh pr edit --add-label` はProjects(classic)廃止に伴うGraphQLエラー(projectCards参照)で
		# 失敗するため案内しない(#386)。REST APIの `gh api` 経由であれば同エンドポイントは
		# PR・issueの両方に使えて安定して成功するため、こちらを案内する。
		echo "ブロック: 対象PRに '${REVIEWED_LABEL}' ラベルがありません。.agents/review-policy.md に沿ったレビューで「受入可」のコメントを投稿したうえで、PR作成者以外がラベルを付与してください（例: gh api -X POST repos/${REPO_PLACEHOLDER}/issues/<PR番号>/labels -f \"labels[]=${REVIEWED_LABEL}\"）。" >&2
		return 2
	fi
}

# `gh issue close` の1件を検査する。戻り値0は許可、2はブロックを表す。
check_close_segment() {
	local close_segment="$1"
	local parse_status=0 issue_number="" issue_repo="" status=0
	# オプション値やリポジトリ名に含まれる数字を拾わないよう、位置引数のみを対象番号として扱う。
	gh_parse_target "issue-close" "$close_segment" || parse_status=$?
	if (( GH_COMMAND_PREFIX_UNCERTAIN )); then
		echo "ブロック: ghの前置ラッパーを解析できないコマンド形式のため、安全側でcloseをブロックします。" >&2
		return 2
	fi
	if [[ "$parse_status" -eq 0 && -n "$GH_TARGET_SELECTOR" ]]; then
		issue_number=$(gh_selector_to_number "$GH_TARGET_SELECTOR") || issue_number=""
	fi
	# URLで別リポジトリのissueが指定された場合、そのリポジトリのリンクPRを照会する。
	if [[ "$parse_status" -eq 0 ]]; then
		issue_repo="$GH_TARGET_REPO"
	fi

	status=0
	linked_pr_has_reviewed_label "$issue_number" "$issue_repo" || status=$?

	if [[ "$status" -eq 0 ]]; then
		return 0
	elif [[ "$status" -eq 2 ]]; then
		echo "ブロック: 対象issueのリンクPR取得(gh api graphql)に失敗、またはissue番号・リポジトリを特定できなかったため、安全側でcloseをブロックします。" >&2
		return 2
	elif [[ "$status" -eq 3 ]]; then
		echo "ブロック: issueを閉じるPRが見つかりません。PR本文に 'Closes #<Issue番号>' を記載してissueとリンクしてください（リンクしたPRがマージされればissueは自動closeされます）。" >&2
		return 2
	else
		# issues/<番号>/labels のREST APIエンドポイントはissueにもPRにも使えるため、
		# PR用メッセージ(#386)と同じ `gh api` 形式に統一する。
		echo "ブロック: 対象issueを閉じるPRに '${REVIEWED_LABEL}' ラベルがありません。.agents/review-policy.md に沿ったレビューで「受入可」のコメントを投稿したうえで、PR作成者以外がPRへラベルを付与してください（例: gh api -X POST repos/${REPO_PLACEHOLDER}/issues/<PR番号>/labels -f \"labels[]=${REVIEWED_LABEL}\"）。" >&2
		return 2
	fi
}

# 1回のBash入力に複数の破壊操作が含まれる場合も、引用符外の区切り文字で分割して全件を検査する。
# 正規表現による行単位の抽出ではタブや引用符内改行で対象引数が欠落するため、共通トークン解析を使う。
gh_collect_executable_segments "$command_for_match"
for command_segment in "${GH_COMMAND_SEGMENTS[@]}"; do
	if gh_segment_has_unparsed_wrapper "$command_segment"; then
		echo "ブロック: env --split-string/-S の実行文字列を解析できないため、安全側でブロックします。" >&2
		exit 2
	fi
	if gh_segment_is_action "$command_segment" "pr" "merge"; then
		check_merge_segment "$command_segment" || exit 2
	fi
	if gh_segment_is_action "$command_segment" "issue" "close"; then
		check_close_segment "$command_segment" || exit 2
	fi
	if gh_segment_is_api_merge "$command_segment"; then
		echo "ブロック: GitHub API経由のPR mergeは禁止されています。レビュー完了後に '${REVIEWED_LABEL}' ラベルを付与し、gh pr merge を使用してください。" >&2
		exit 2
	fi
	if gh_segment_is_api_issue_close "$command_segment"; then
		echo "ブロック: GitHub API経由のIssue closeは禁止されています。レビュー完了後に '${REVIEWED_LABEL}' ラベルを付与し、gh issue close を使用してください。" >&2
		exit 2
	fi
	if gh_segment_is_api_graphql_destructive "$command_segment"; then
		echo "ブロック: GraphQL mutation(mergePullRequest / closeIssue)によるPR merge・Issue closeは禁止されています。クエリ本体をシェル展開やファイルで渡す形も内容を検証できないためブロックします。レビュー完了後に '${REVIEWED_LABEL}' ラベルを付与し、gh pr merge / gh issue close を使用してください。" >&2
		exit 2
	fi
	if gh_segment_is_issue_state_close "$command_segment"; then
		echo "ブロック: --state closedによるIssue closeは禁止されています。レビュー完了後に '${REVIEWED_LABEL}' ラベルを付与し、gh issue close を使用してください。" >&2
		exit 2
	fi
done

exit 0
