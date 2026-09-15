#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
hook="$script_dir/block-github-destructive-actions.sh"

# 実PRのラベル状態やネットワークに依存しないよう、gh をPATH上のスタブに差し替える。
# GH_STUB_MATCH/GH_STUB_EXIT/GH_STUB_JSON でテストごとに応答を制御する。
stub_dir=$(mktemp -d)
trap 'rm -rf "$stub_dir"' EXIT

cat > "$stub_dir/gh" <<'STUB'
#!/usr/bin/env bash
# どの番号でレビュー状態を確認したかを検証できるよう、呼び出し引数を記録する。
if [[ -n "${GH_STUB_CALLS:-}" ]]; then
	printf '%s\n' "$*" >> "$GH_STUB_CALLS"
fi
cmd="$1 $2"
case "$cmd" in
	# issue closeの判定で使うリポジトリ解決。GH_STUB_REPO_EXITで失敗を再現する。
	"repo view")
		if [[ "${GH_STUB_REPO_EXIT:-0}" != "0" ]]; then
			exit "${GH_STUB_REPO_EXIT}"
		fi
		printf '%s' "${GH_STUB_REPO:-oikawa-d/task_management}"
		exit 0
		;;
	# issueにリンクされたPRとそのラベルを返すGraphQL応答。
	"api graphql")
		if [[ "${GH_STUB_GRAPHQL_EXIT:-0}" != "0" ]]; then
			exit "${GH_STUB_GRAPHQL_EXIT}"
		fi
		graphql_number=""
		graphql_repo=""
		graphql_cursor=""
		for arg in "$@"; do
			case "$arg" in
				number=*) graphql_number="${arg#number=}" ;;
				owner=*) graphql_repo="${arg#owner=}"/"$graphql_repo" ;;
				repo=*) graphql_repo="${graphql_repo%%/*}"/"${arg#repo=}" ;;
				cursor=*) graphql_cursor="${arg#cursor=}" ;;
			 esac
		done
		if [[ -n "${GH_STUB_GRAPHQL_EXPECT_NUMBER:-}" && "$graphql_number" != "$GH_STUB_GRAPHQL_EXPECT_NUMBER" ]]; then
			exit 1
		fi
		if [[ -n "${GH_STUB_GRAPHQL_EXPECT_REPO:-}" && "$graphql_repo" != "$GH_STUB_GRAPHQL_EXPECT_REPO" ]]; then
			exit 1
		fi
		# JSONに `}` を含むため `${VAR:-default}` のデフォルト値では書けない。
		json="${GH_STUB_GRAPHQL_JSON:-}"
		if [[ -n "$graphql_cursor" ]]; then
			json="${GH_STUB_GRAPHQL_NEXT_JSON:-$json}"
		fi
		if [[ -z "$json" ]]; then
			json='{"data":{"repository":{"issue":{"closedByPullRequestsReferences":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[]}}}}}'
		fi
		printf '%s' "$json"
		exit 0
		;;
esac
if [[ "$cmd" == "${GH_STUB_MATCH:-}" ]]; then
	if [[ -n "${GH_STUB_EXIT:-}" && "${GH_STUB_EXIT}" != "0" ]]; then
		exit "${GH_STUB_EXIT}"
	fi
	json="${GH_STUB_JSON:-}"
	if [[ "$cmd" == "pr view" && -n "${GH_STUB_UNREVIEWED_PR:-}" && "$3" == "$GH_STUB_UNREVIEWED_PR" ]]; then
		json='{"labels":[]}'
	fi
	if [[ -z "$json" ]]; then
		json='{"labels":[]}'
	fi
	printf '%s' "$json"
	exit 0
fi
echo '{"labels":[]}'
STUB
chmod +x "$stub_dir/gh"

export PATH="$stub_dir:$PATH"

payload() {
	local command=$1
	jq -n --arg command "$command" '{tool_name: "Bash", tool_input: {command: $command}}'
}

assert_allowed() {
	local command=$1
	if payload "$command" | "$hook" >/dev/null 2>&1; then
		return 0
	fi
	echo "許可されるコマンドがブロックされました: $command" >&2
	return 1
}

assert_blocked() {
	local command=$1
	local status=0
	payload "$command" | "$hook" >/dev/null 2>&1 || status=$?
	# Claude Codeがツール実行を中断するのはexit 2のみ。他の非0はブロックにならない
	if [[ "$status" -ne 2 ]]; then
		echo "禁止されるコマンドがexit 2でブロックされませんでした (exit=$status): $command" >&2
		return 1
	fi
}

assert_blocked_with_message() {
	local command=$1
	local expected=$2
	local status=0 output
	output=$(payload "$command" | "$hook" 2>&1) || status=$?
	if [[ "$status" -ne 2 || "$output" != *"$expected"* ]]; then
		echo "期待したメッセージでブロックされませんでした (exit=$status, 期待: $expected): $command" >&2
		echo "$output" >&2
		return 1
	fi
}

assert_blocked_raw_stdin() {
	local raw_input=$1
	local status=0
	echo "$raw_input" | "$hook" >/dev/null 2>&1 || status=$?
	if [[ "$status" -ne 2 ]]; then
		echo "想定外の入力でexit 2になりませんでした (exit=$status): $raw_input" >&2
		return 1
	fi
}

# jqが存在しない環境ではfail-closeすること(#339)を検証するため、PATHをjq抜きに差し替えて実行する。
assert_blocked_without_jq() {
	local command=$1
	local fake_path
	fake_path=$(mktemp -d)
	for utility in bash cat env; do
		ln -s "$(command -v "$utility")" "$fake_path/$utility"
	done
	local input
	input=$(payload "$command")
	local status=0
	printf '%s\n' "$input" | PATH="$fake_path" "$hook" >/dev/null 2>&1 || status=$?
	rm -rf "$fake_path"
	if [[ "$status" -ne 2 ]]; then
		echo "jq不在時にhookがexit 2でブロックしませんでした (exit=$status): $command" >&2
		return 1
	fi
}

# 判定処理の大半はシェル関数内にあるため、関数内で想定外のエラーが起きた場合も
# exit 2(ブロック)になることを検証する。ERRトラップはerrtrace(set -E)が無いと関数へ
# 継承されず、終了コードが1になってClaude Codeがツール実行を継続してしまう。
# 実際に失敗を注入した複製で確認する(元のhookは変更しない)。
assert_fail_close_on_internal_error() {
	local command=$1
	local fixture_dir status=0
	fixture_dir=$(mktemp -d)
	cp -R "$script_dir/." "$fixture_dir/"
	sed -i 's/^gh_collect_executable_segments() {$/&\n\tfalse/' "$fixture_dir/lib/gh-command-parse.sh"
	# 注入が効いていないと常に成功する空振りテストになるため、注入結果を確認する。
	if [[ "$(sed -n '/^gh_collect_executable_segments() {$/{n;p;}' "$fixture_dir/lib/gh-command-parse.sh")" != $'\tfalse' ]]; then
		echo "テスト用のエラー注入に失敗しました: $fixture_dir/lib/gh-command-parse.sh" >&2
		rm -rf "$fixture_dir"
		return 1
	fi
	payload "$command" | "$fixture_dir/block-github-destructive-actions.sh" >/dev/null 2>&1 || status=$?
	rm -rf "$fixture_dir"
	if [[ "$status" -ne 2 ]]; then
		echo "関数内の想定外エラーがexit 2でブロックされませんでした (exit=$status): $command" >&2
		return 1
	fi
}

# hookがレビュー状態の確認に使った引数(=対象番号)を検証する。
assert_gh_called_with() {
	local command=$1
	local pattern=$2
	local calls
	calls=$(mktemp)
	GH_STUB_CALLS="$calls" payload "$command" | GH_STUB_CALLS="$calls" "$hook" >/dev/null 2>&1 || true
	if grep -q -- "$pattern" "$calls"; then
		rm -f "$calls"
		return 0
	fi
	echo "対象番号の判定が想定と異なります (期待: $pattern): $command" >&2
	echo "実際のgh呼び出し:" >&2
	cat "$calls" >&2
	rm -f "$calls"
	return 1
}

# hookが指定リポジトリ以外へ照会していないことを検証する。
assert_gh_not_called_with() {
	local command=$1
	local pattern=$2
	local calls
	calls=$(mktemp)
	GH_STUB_CALLS="$calls" payload "$command" | GH_STUB_CALLS="$calls" "$hook" >/dev/null 2>&1 || true
	if grep -q -- "$pattern" "$calls"; then
		echo "想定外のリポジトリ・番号へ照会しました (禁止: $pattern): $command" >&2
		cat "$calls" >&2
		rm -f "$calls"
		return 1
	fi
	rm -f "$calls"
	return 0
}

approve_json='{"labels":[{"name":"approve"}]}'
legacy_reviewed_json='{"labels":[{"name":"reviewed"}]}'
unreviewed_json='{"labels":[]}'

unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON

# --- 基本ケース(gh呼び出しを伴わない) ---
assert_allowed "gh pr view 123"
assert_allowed "git commit -m 'test'"

# 1. approveラベル無しのPRへのマージ -> exit 2
export GH_STUB_MATCH="pr view" GH_STUB_EXIT="0" GH_STUB_JSON="$unreviewed_json"
assert_blocked "gh pr merge 123 --squash"
assert_blocked "gh --repo oikawa-d/task_management pr merge 123"

# 2. approveラベル有りのPRへのマージ -> exit 0
export GH_STUB_JSON="$approve_json"
assert_allowed "gh pr merge 123 --squash"

# 2-1. 旧reviewedラベルだけではマージを許可しない
export GH_STUB_JSON="$legacy_reviewed_json"
assert_blocked "gh pr merge 123 --squash"
export GH_STUB_JSON="$approve_json"

# 3. PR番号省略時にカレントブランチのPRで判定されること
assert_allowed "gh pr merge --squash"
export GH_STUB_JSON="$unreviewed_json"
assert_blocked "gh pr merge --squash"

# 3-2. オプション値・フラグの数字を対象PRと誤認しないこと
export GH_STUB_JSON="$unreviewed_json"
assert_gh_called_with 'gh pr merge --subject "fix 999" 123 --squash' 'pr view 123'
assert_gh_called_with 'gh pr merge --body-file /tmp/999.md 123' 'pr view 123'
assert_gh_called_with "gh pr merge --squash feature/issue-999" 'pr view feature/issue-999'
assert_gh_called_with "gh pr merge -A author@example.com 123" 'pr view 123'
assert_gh_called_with "gh pr merge -Aauthor@example.com 123" 'pr view 123'

# 3-4. `--repo` やURLで指定した別リポジトリのPRを照会すること
# カレントリポジトリの同番号PRのapprove状態で許可・拒否してはならない。
assert_gh_called_with "gh pr merge --repo evil/other 123" 'pr view 123 --json labels --repo evil/other'
assert_gh_called_with "gh pr merge 123 -R evil/other" 'pr view 123 --json labels --repo evil/other'
assert_gh_called_with "gh pr merge --repo=evil/other 123" 'pr view 123 --json labels --repo evil/other'
assert_gh_called_with "gh pr merge https://github.com/evil/other/pull/123" '--repo github.com/evil/other'
assert_gh_called_with "gh pr merge --repo ghe.example/evil/other 123" 'pr view 123 --json labels --repo ghe.example/evil/other'
assert_gh_called_with "gh pr merge https://ghe.example/evil/other/pull/123" '--repo ghe.example/evil/other'
assert_blocked "gh pr merge --repo invalid 123"
# `--repo` 未指定ならカレントリポジトリ(=`--repo` を付けない)で照会すること
assert_gh_not_called_with "gh pr merge 123" '--repo'
# 引用文字列に含まれる `--repo` は実オプションではないため照会先に使わないこと
assert_gh_not_called_with 'gh pr merge --subject "see --repo evil/other" 123' 'evil/other'

# 3-5. サブコマンドより前に置かれたグローバルな `--repo` / `-R` も照会先へ反映すること
assert_gh_called_with "gh --repo evil/other pr merge 123" 'pr view 123 --json labels --repo evil/other'
assert_gh_called_with "gh --repo=evil/other pr merge 123" 'pr view 123 --json labels --repo evil/other'
assert_gh_called_with "gh -R evil/other pr merge 123" 'pr view 123 --json labels --repo evil/other'
assert_gh_called_with "gh -Revil/other pr merge 123" 'pr view 123 --json labels --repo evil/other'
assert_gh_called_with "gh -R=evil/other pr merge 123" 'pr view 123 --json labels --repo evil/other'
# サブコマンド後の短縮形の値連結(`-Rowner/repo`)も同様に解析すること
assert_gh_called_with "gh pr merge 123 -Revil/other" 'pr view 123 --json labels --repo evil/other'
assert_gh_called_with "gh pr merge 123 -R=evil/other" 'pr view 123 --json labels --repo evil/other'

# 3-3. 未知のフラグはブロックすること(fail-close)
assert_blocked "gh pr merge --unknown-option 999 123"

# 4. gh pr view 失敗時 -> exit 2 (fail-close)
export GH_STUB_EXIT="1"
assert_blocked "gh pr merge 123"
export GH_STUB_EXIT="0"

# 5. issue close は「issueを閉じるPR」のapproveラベルで判定する(#401)
# issue自身のラベルでは判定しないため、issueにapproveが付いていても許可してはならない。
linked_approve_json='{"data":{"repository":{"issue":{"closedByPullRequestsReferences":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"number":362,"labels":{"nodes":[{"name":"approve"}]}}]}}}}}'
linked_legacy_reviewed_json='{"data":{"repository":{"issue":{"closedByPullRequestsReferences":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"number":363,"labels":{"nodes":[{"name":"reviewed"}]}}]}}}}}'
linked_unreviewed_json='{"data":{"repository":{"issue":{"closedByPullRequestsReferences":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"number":374,"labels":{"nodes":[{"name":"review"}]}}]}}}}}'
linked_none_json='{"data":{"repository":{"issue":{"closedByPullRequestsReferences":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[]}}}}}'
linked_page_one_json='{"data":{"repository":{"issue":{"closedByPullRequestsReferences":{"pageInfo":{"hasNextPage":true,"endCursor":"cursor-1"},"nodes":[{"number":374,"labels":{"nodes":[{"name":"review"}]}}]}}}}}'
linked_page_two_json='{"data":{"repository":{"issue":{"closedByPullRequestsReferences":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"number":375,"labels":{"nodes":[{"name":"approve"}]}}]}}}}}'
linked_partial_error_json='{"data":{"repository":{"issue":{"closedByPullRequestsReferences":{"pageInfo":{"hasNextPage":false,"endCursor":null},"nodes":[{"number":376,"labels":{"nodes":[{"name":"reviewed"}]}}]}}}},"errors":[{"message":"partial failure"}]}'

# 5-1. リンクPRにapproveあり -> exit 0
export GH_STUB_GRAPHQL_JSON="$linked_approve_json"
assert_allowed "gh issue close 123"
assert_allowed "gh --repo oikawa-d/task_management issue close 123"
assert_allowed "gh issue close 123 --comment '対応完了'"
assert_allowed "gh issue close 123 --comment 'fix; done | keep & quoted'"

# 5-1-1. リンクPRに旧reviewedしかない場合はブロックする
export GH_STUB_GRAPHQL_JSON="$linked_legacy_reviewed_json"
assert_blocked "gh issue close 123"

# 5-2. リンクPRはあるがapproveなし -> exit 2
export GH_STUB_GRAPHQL_JSON="$linked_unreviewed_json"
assert_blocked "gh issue close 123"

# 5-3. リンクPRが無い(PR本文にClosesが無い) -> exit 2
export GH_STUB_GRAPHQL_JSON="$linked_none_json"
assert_blocked_with_message "gh issue close 123" "issueを閉じるPRが見つかりません"

# 5-4. issue自身にapproveラベルがあってもリンクPRが未approveならブロックされること
export GH_STUB_GRAPHQL_JSON="$linked_unreviewed_json" GH_STUB_MATCH="issue view" GH_STUB_JSON="$approve_json"
assert_blocked "gh issue close 123"
unset GH_STUB_MATCH GH_STUB_JSON

# 5-5. GraphQL呼び出し失敗 -> exit 2 (fail-close)
export GH_STUB_GRAPHQL_JSON="$linked_approve_json" GH_STUB_GRAPHQL_EXIT="1"
assert_blocked "gh issue close 123"
unset GH_STUB_GRAPHQL_EXIT

# 5-6. GraphQLの部分成功(data + errors)は成功扱いせず、fail-closeする
export GH_STUB_GRAPHQL_JSON="$linked_partial_error_json"
assert_blocked "gh issue close 123"
export GH_STUB_GRAPHQL_JSON="$linked_approve_json"

# 5-7. リポジトリ解決失敗 -> exit 2 (fail-close)。--repo指定があれば解決不要で許可される。
export GH_STUB_REPO_EXIT="1"
assert_blocked "gh issue close 123"
assert_allowed "gh issue close 123 --repo oikawa-d/task_management"
assert_allowed "gh issue close 123 -R oikawa-d/task_management"
assert_allowed "gh issue close 123 --repo github.com/oikawa-d/task_management"
unset GH_STUB_REPO_EXIT

# 5-7. issue番号を特定できない -> exit 2 (fail-close)
assert_blocked "gh issue close"

# 5-8. オプション値の数値をIssue番号にせず、実際の位置引数を照会する
export GH_STUB_GRAPHQL_JSON="$linked_approve_json" GH_STUB_GRAPHQL_EXPECT_NUMBER="456"
assert_allowed "gh issue close --comment 123 456"
assert_allowed "gh issue close --comment=123 456"
unset GH_STUB_GRAPHQL_EXPECT_NUMBER

# 5-9. コメント内の偽repo指定を実引数として解釈しない
export GH_STUB_GRAPHQL_EXPECT_REPO="oikawa-d/task_management"
assert_allowed "gh issue close 456 --comment '--repo attacker/other-repo'"
unset GH_STUB_GRAPHQL_EXPECT_REPO

# 5-10. GitHub Issue URL形式を受け付ける
export GH_STUB_GRAPHQL_EXPECT_NUMBER="456" GH_STUB_GRAPHQL_EXPECT_REPO="oikawa-d/task_management"
assert_allowed "gh issue close https://github.com/oikawa-d/task_management/issues/456"
unset GH_STUB_GRAPHQL_EXPECT_NUMBER GH_STUB_GRAPHQL_EXPECT_REPO

# 5-11. リンクPRをページングしてapproveを検索する
export GH_STUB_GRAPHQL_JSON="$linked_page_one_json" GH_STUB_GRAPHQL_NEXT_JSON="$linked_page_two_json"
assert_allowed "gh issue close 123"
unset GH_STUB_GRAPHQL_NEXT_JSON

unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON GH_STUB_GRAPHQL_JSON GH_STUB_GRAPHQL_NEXT_JSON

# 5-8. オプション値の数字を対象番号と誤認しないこと
# `--comment` の値に含まれる 999 ではなく、位置引数の 123 を対象にしなければならない。
export GH_STUB_GRAPHQL_JSON="$linked_unreviewed_json"
assert_gh_called_with 'gh issue close --comment "tracking 999" 123' 'number=123'
assert_gh_called_with "gh issue close --reason 'not planned' 123" 'number=123'
assert_gh_called_with 'gh issue close --comment="tracking 999" 123' 'number=123'
assert_gh_called_with 'gh issue close -R oikawa-d/task-999 123' 'number=123'
assert_blocked 'gh issue close --comment "tracking 999" 123'

# 5-10. Issue URLが別リポジトリを示す場合、そのリポジトリのリンクPRを照会すること
assert_gh_called_with "gh issue close https://github.com/evil/other/issues/123" \
	'owner=evil -F repo=other -F number=123'
assert_gh_called_with "gh issue close --repo evil/other 123" 'owner=evil -F repo=other -F number=123'
assert_gh_called_with "gh issue close --repo github.com/evil/other 123" \
	'api graphql .*--hostname github.com .*owner=evil -F repo=other -F number=123'
assert_gh_called_with "gh issue close --repo ghe.example/evil/other 123" \
	'api graphql .*--hostname ghe.example .*owner=evil -F repo=other -F number=123'
assert_gh_called_with "gh issue close https://ghe.example/evil/other/issues/123" \
	'api graphql .*--hostname ghe.example .*owner=evil -F repo=other -F number=123'
assert_blocked "gh issue close --repo invalid 123"

# 5-11. コメント等の引用文字列に含まれる `--repo` は照会先に使わず、カレントリポジトリを照会すること
assert_gh_called_with 'gh issue close --comment "text --repo evil/other" 123' \
	'owner=oikawa-d -F repo=task_management -F number=123'
assert_gh_not_called_with 'gh issue close --comment "text --repo evil/other" 123' 'owner=evil'

# 5-12. サブコマンドより前に置かれたグローバルな `--repo` / `-R` も照会先へ反映すること
assert_gh_called_with "gh --repo evil/other issue close 123" 'owner=evil -F repo=other -F number=123'
assert_gh_called_with "gh --repo=evil/other issue close 123" 'owner=evil -F repo=other -F number=123'
assert_gh_called_with "gh -R evil/other issue close 123" 'owner=evil -F repo=other -F number=123'
assert_gh_called_with "gh -Revil/other issue close 123" 'owner=evil -F repo=other -F number=123'
assert_gh_called_with "gh -R=evil/other issue close 123" 'owner=evil -F repo=other -F number=123'
assert_gh_called_with "gh issue close 123 -Revil/other" 'owner=evil -F repo=other -F number=123'
assert_gh_called_with "gh issue close 123 -R=evil/other" 'owner=evil -F repo=other -F number=123'
# サブコマンド前後いずれの位置でも、引用文字列の内容は実オプションとして扱わないこと
assert_gh_not_called_with 'gh issue close --comment "see gh --repo evil/other issue close 999" 123' 'owner=evil'

# 5-9. 未知のフラグは値を取るか判断できないため解析不能としてブロックすること(fail-close)
assert_blocked "gh issue close --unknown-option 999 123"

unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON GH_STUB_GRAPHQL_JSON

# 6. heredoc本文にコマンド名を含むだけのコマンド -> exit 0 (#388の回帰テスト)
heredoc_cmd=$(printf '%s\n' \
	"cat > ./tmp/handover.md <<'XEOF'" \
	"approve付与済み＋CI全チェック成功なら gh pr merge してよい" \
	"gh issue close 999" \
	"XEOF")
assert_allowed "$heredoc_cmd"

heredoc_cmd_unquoted=$(printf '%s\n' \
	"cat > ./tmp/note.md <<EOF2" \
	"gh pr merge 1" \
	"EOF2")
assert_allowed "$heredoc_cmd_unquoted"

heredoc_cmd_dash=$(printf '%s\n' \
	"cat <<-'EOF3'" \
	$'\tgh pr merge 1' \
	"EOF3")
assert_allowed "$heredoc_cmd_dash"

# 7. クォート内・echoの引数にコマンド名を含む場合 -> exit 0
assert_allowed 'echo "gh pr merge 123 --squash"'
assert_allowed "echo 'gh issue close 123'"
assert_allowed 'echo '\''$(gh pr merge 123)'\'''
assert_allowed 'echo "\$(gh pr merge 123)"'
assert_allowed 'echo "$(gh pr view 123)"'
assert_allowed "# gh pr merge 123 (コメント例)"

# heredoc風の記号が引用符内にある場合、後続行をheredoc本文として削除しないこと。
# 実際の後続コマンドはレビュー状態を検査する必要がある。
export GH_STUB_MATCH="pr view" GH_STUB_EXIT="0" GH_STUB_JSON="$unreviewed_json"
quoted_heredoc_marker=$(printf '%s\n' \
	"echo '<<EOF'" \
	"gh pr merge 123" \
	"EOF")
assert_blocked "$quoted_heredoc_marker"
quoted_double_heredoc_marker=$(printf '%s\n' \
	'echo "<<EOF2"' \
	"gh pr merge 123" \
	"EOF2")
assert_blocked "$quoted_double_heredoc_marker"
# コメント中のheredoc風記号は構文として扱わず、後続の破壊操作を検査すること。
comment_heredoc_marker=$(printf '%s\n' \
	"# <<EOF4" \
	"gh pr merge 123" \
	"EOF4")
assert_blocked "$comment_heredoc_marker"
inline_comment_heredoc_marker=$(printf '%s\n' \
	"true # <<EOF5" \
	"gh pr merge 123" \
	"EOF5")
assert_blocked "$inline_comment_heredoc_marker"
# クォートされていないheredoc本文のコマンド置換・backtickは実行され得るためブロックする。
assert_blocked $'cat <<EOF6\n$(gh pr merge 123)\nEOF6'
assert_blocked $'cat <<EOF7\n$(gh issue close 123)\nEOF7'
assert_blocked $'cat <<EOF8\n$(gh api -X PUT repos/oikawa-d/task_management/pulls/123/merge)\nEOF8'
assert_blocked $'cat <<EOF9\n`gh pr merge 123`\nEOF9'
# クォートされたheredoc本文は展開されないため、従来どおり除外する。
assert_allowed $'cat <<\'EOF10\n$(gh pr merge 123)\nEOF10'
unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON

# 8. 実際のマージコマンドは引き続きブロックされること(区切り文字経由も含む)
export GH_STUB_MATCH="pr view" GH_STUB_EXIT="0" GH_STUB_JSON="$unreviewed_json"
assert_blocked "git status; gh pr merge 123"
assert_blocked "true && gh pr merge 123"
assert_blocked "gh pr merge 123 || echo fallback"
# この文字列は実行されず、hookへの入力データとして渡すだけのため展開させない意図で単一引用符を使用する。
# shellcheck disable=SC2016
assert_blocked '$(echo dummy); gh pr merge 123'
assert_blocked "if true; then gh pr merge 123; fi"
assert_blocked "{ gh pr merge 123; }"
assert_blocked 'echo "$(gh pr merge 123)"'
assert_blocked 'echo "$(gh issue close 123)"'
assert_blocked 'echo "$(gh api -X PUT repos/oikawa-d/task_management/pulls/123/merge)"'
assert_blocked 'echo "$(echo "$(gh pr merge 123)")"'
assert_blocked 'echo "`gh pr merge 123`"'
export GH_STUB_JSON="$approve_json"
assert_allowed "if true; then gh pr merge 123; fi"
assert_allowed 'echo "$(gh pr merge 123)"'
unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON

# バックスラッシュ改行で分断されたコマンドも、実行時のコマンドとして検査すること。
export GH_STUB_MATCH="pr view" GH_STUB_EXIT="0" GH_STUB_JSON="$unreviewed_json"
assert_blocked $'gh pr \\\nmerge 123'
assert_blocked $'gh issue \\\nclose 123'
assert_blocked $'gh api -X \\\nPUT repos/oikawa-d/task_management/pulls/123/merge'
unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON

# タブは引数区切りとして扱い、引用符内改行は同一引数の一部として保持すること。
export GH_STUB_MATCH="pr view" GH_STUB_EXIT="0" GH_STUB_JSON="$unreviewed_json"
assert_gh_called_with $'gh pr merge\t123' 'pr view 123'
assert_gh_called_with $'gh pr merge 123 --subject "line one\nline two" --repo evil/other' \
	'pr view 123 --json labels --repo evil/other'
unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON

export GH_STUB_GRAPHQL_JSON="$linked_unreviewed_json"
assert_gh_called_with $'gh issue close\t123' 'number=123'
assert_gh_called_with $'gh issue close 123 --comment "line one\nline two" --repo evil/other' \
	'owner=evil -F repo=other -F number=123'
unset GH_STUB_GRAPHQL_JSON

# 9. 想定外エラー時 -> exit 2 (trap ... ERR)
assert_blocked_raw_stdin "これは不正なJSONです"

# 10. `gh pr merge` / `gh issue close` の代替経路 -> exit 2 (#339)
assert_blocked "gh api -X PUT repos/oikawa-d/task_management/pulls/123/merge"
assert_blocked "gh api -XPUT repos/oikawa-d/task_management/pulls/123/merge"
assert_blocked "gh api -X=PUT repos/oikawa-d/task_management/pulls/123/merge"
assert_blocked "gh api repos/oikawa-d/task_management/pulls/123/merge --method PUT"
assert_blocked "gh api repos/oikawa-d/task_management/pulls/123/merge --method=PUT"
assert_blocked "gh api repos/oikawa-d/task_management/pulls/123/merge -XPUT"
assert_blocked "gh api repos/oikawa-d/task_management/pulls/123/merge -X=PUT"
assert_blocked $'gh api -X PUT\trepos/oikawa-d/task_management/pulls/123/merge'
assert_blocked 'METHOD=PUT; gh api -X "$METHOD" repos/oikawa-d/task_management/pulls/123/merge'
assert_blocked 'ENDPOINT=repos/oikawa-d/task_management/pulls/123/merge; gh api -X PUT "$ENDPOINT"'
assert_blocked 'ENDPOINT=repos/oikawa-d/task_management/pulls/123/merge; gh api -X PUT "${ENDPOINT}?foo=bar"'
assert_blocked "gh api -X PUT /repos/oikawa-d/task_management/pulls/123/merge"
assert_blocked "gh api -X PUT 'repos/oikawa-d/task_management/pulls/123/merge?foo=bar'"
assert_allowed 'gh api -X PUT repos/oikawa-d/task_management/issues/123 -f body="$BODY"'
assert_blocked "gh issue edit 123 --state closed"
assert_blocked "gh --repo oikawa-d/task_management issue edit 123 --state=closed"

# 10-1. gh apiの値付きオプションをendpointと誤認しないこと
assert_blocked 'gh api -X PUT -H "Accept: application/vnd.github+json" repos/oikawa-d/task_management/pulls/123/merge'
assert_blocked "gh api -X PUT -q .sha repos/oikawa-d/task_management/pulls/123/merge"
assert_blocked 'gh api -X PUT -t "{{.sha}}" repos/oikawa-d/task_management/pulls/123/merge'
assert_blocked "gh api -X PUT --jq .sha repos/oikawa-d/task_management/pulls/123/merge"
assert_allowed 'gh api -H "Accept: application/vnd.github+json" repos/oikawa-d/task_management/pulls/123'

# 10-2. API経由のIssue close / GraphQL mutation -> exit 2
assert_blocked "gh api -X PATCH repos/oikawa-d/task_management/issues/123 -f state=closed"
assert_blocked "gh api --method PATCH /repos/oikawa-d/task_management/issues/123 -f state=closed"
assert_blocked 'gh api -X PATCH repos/oikawa-d/task_management/issues/123 -f "state=CLOSED"'
assert_blocked 'STATE=closed; gh api -X PATCH repos/oikawa-d/task_management/issues/123 -f state="$STATE"'
assert_allowed "gh api -X PATCH repos/oikawa-d/task_management/issues/123 -f title=updated"
assert_blocked "gh api -X PATCH repos/oikawa-d/task_management/issues/123 --input payload.json"
assert_blocked "gh api -X PATCH repos/oikawa-d/task_management/issues/123 --input=payload.json"
assert_blocked "gh api -X PATCH repos/oikawa-d/task_management/issues/123 --input -"
assert_blocked "gh api -X PATCH repos/oikawa-d/task_management/issues/123 -F state=@state.txt"
assert_blocked "gh api -X PATCH repos/oikawa-d/task_management/issues/123 -F state=-"
assert_blocked "gh api -X PATCH repos/oikawa-d/task_management/issues/123 --field state=@state.txt"
assert_blocked "gh api repos/oikawa-d/task_management/issues/123 --input payload.json"
assert_allowed "gh api -X PATCH repos/oikawa-d/task_management/issues/123 -F title=@title.txt"
assert_allowed "gh api repos/oikawa-d/task_management/pulls/123 -q .title"
assert_blocked $'gh api graphql -f query=\'mutation{mergePullRequest(input:{pullRequestId:"x"}){clientMutationId}}\''
assert_blocked $'gh api graphql -f query=\'mutation{closeIssue(input:{issueId:"x"}){clientMutationId}}\''
assert_allowed $'gh api graphql -f query=\'query{repository(owner:"o",name:"r"){id}}\''

# 10-3. 1回の入力に複数の破壊操作がある場合、全件を検査すること
export GH_STUB_JSON="$approve_json" GH_STUB_UNREVIEWED_PR="456" GH_STUB_GRAPHQL_JSON="$linked_unreviewed_json"
assert_blocked "gh pr merge 123 && gh pr merge 456"
assert_blocked "gh pr merge 123 && gh issue close 456"
unset GH_STUB_JSON GH_STUB_UNREVIEWED_PR GH_STUB_GRAPHQL_JSON

# 10-4. 算術シフトをheredoc開始と誤認しないこと / 終端語の無いheredocはfail-close
export GH_STUB_MATCH="pr view" GH_STUB_EXIT="0" GH_STUB_JSON="$unreviewed_json" GH_STUB_GRAPHQL_JSON="$linked_unreviewed_json"
assert_blocked $'shift=2\nvalue=$((1<<shift))\ngh pr merge 123'
assert_blocked $'value=$((1<<N))\ngh issue close 123'
assert_blocked $'value=$((1 << 2))\ngh pr merge 123'
assert_blocked $'value=$(( (1<<shift) + 1 ))\ngh pr merge 123'
assert_blocked $'x=${x#foo<<EOF}\ngh pr merge 123\nEOF'
assert_blocked $'cat <<EOF\ngh pr merge 123\n'
assert_allowed $'value=$((1<<shift))\necho "$value"'
unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON GH_STUB_GRAPHQL_JSON

# 10-5. GraphQLのqueryを静的に確認できない場合はfail-close
assert_blocked 'QUERY=mutation; gh api graphql -f query="$QUERY"'
assert_blocked 'gh api graphql -f query="$(cat query.graphql)"'
assert_blocked "gh api graphql -F query=@query.graphql"
assert_blocked "gh api graphql --input payload.json"
assert_blocked 'GRAPHQL=graphql; gh api "$GRAPHQL" -f '\''query=query{closeIssue(input:{issueId:"x"}){clientMutationId}}'\'''
assert_blocked 'gh api "$(printf graphql)" -f '\''query=query{mergePullRequest(input:{pullRequestId:"x"}){clientMutationId}}'\'''
assert_allowed "gh api graphql -f query='query{viewer{login}}' -F number=1"

# 10-6. REST mergeのmethod・endpointを同時にシェル展開した場合もブロックすること
assert_blocked 'METHOD=PUT ENDPOINT=repos/oikawa-d/task_management/pulls/123/merge; gh api -X "$METHOD" "$ENDPOINT"'
assert_blocked 'gh api -X "$METHOD" "$ENDPOINT"'
assert_allowed 'gh api "$ENDPOINT"'

# 10-7. コマンド名をシェル展開した破壊操作も検査対象とすること
export GH_STUB_MATCH="pr view" GH_STUB_EXIT="0" GH_STUB_JSON="$unreviewed_json" GH_STUB_GRAPHQL_JSON="$linked_unreviewed_json"
assert_blocked 'GH=gh; $GH pr merge 123'
assert_blocked 'GH=gh; "$GH" pr merge 123 --squash'
assert_blocked 'GH=gh; $GH issue close 123'
assert_blocked 'GH=gh; "$GH" issue close 123'
assert_blocked '$(which gh) pr merge 123'
assert_blocked '`which gh` pr merge 123'
assert_blocked '$GH api -X PUT repos/oikawa-d/task_management/pulls/123/merge'
assert_blocked 'GH=gh; $GH issue edit 123 --state closed'
# コマンド名が動的でも、対象PRにapproveラベルがあれば許可すること
export GH_STUB_JSON="$approve_json"
assert_allowed 'GH=gh; $GH pr merge 123 --squash'
unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON GH_STUB_GRAPHQL_JSON
# コマンド置換・バッククォート単体、および置換で渡された引数も検査対象とすること
export GH_STUB_MATCH="pr view" GH_STUB_EXIT="0" GH_STUB_JSON="$unreviewed_json"
assert_blocked '$(gh pr merge 123)'
assert_blocked '`gh pr merge 123`'
assert_blocked "gh pr merge \$(cat pr.txt)"
assert_blocked 'gh api -X PUT "$(cat endpoint.txt)"'
assert_blocked '/usr/bin/gh pr merge 123'
assert_blocked './bin/gh issue close 123'
assert_blocked 'exec gh pr merge 123'
assert_blocked 'exec gh api -X PUT repos/oikawa-d/task_management/pulls/123/merge'
assert_blocked 'env -- gh pr merge 123'
assert_blocked 'command -- gh issue close 123'
assert_blocked 'command -- gh api -X PUT repos/oikawa-d/task_management/pulls/123/merge'
# 前置wrapperを絶対・相対パスで指定しても、basenameが既知wrapperなら検出すること。
assert_blocked '/usr/bin/env gh pr merge 123'
assert_blocked '/usr/bin/env -- gh pr merge 123'
assert_blocked '/usr/bin/time gh pr merge 123'
assert_blocked '/usr/bin/command gh issue close 123'
assert_blocked "/usr/bin/env -S 'gh pr merge 123'"
assert_blocked "/usr/bin/env --split-string='gh issue close 123'"
# 既知ラッパーの未知オプションは実行位置を判定できないためfail-closeする。
assert_blocked 'env --unknown gh pr merge 123'
assert_blocked 'X=1 gh pr merge 123'
assert_blocked 'X=1 gh api -X PUT repos/oikawa-d/task_management/pulls/123/merge'
assert_blocked "env -S 'gh pr merge 123'"
assert_blocked "env --split-string='gh issue close 123'"
assert_blocked "env -S 'gh api -X PUT repos/oikawa-d/task_management/pulls/123/merge'"
assert_blocked "env -S'gh pr merge 123'"
assert_blocked 'env -S"gh issue close 123"'
# 14. sudo/xargs経由での呼び出しも検出すること(#390で拡張)
# `sudo gh pr merge 123` / `... | xargs gh pr merge` はPR作成者が誤って自分のPRを
# マージしてしまう典型的な前置形であり、既存のwrapper判定(env/exec等)と同じ枠組みで
# 安全に拡張できるため対応する。
export GH_STUB_MATCH="pr view" GH_STUB_EXIT="0" GH_STUB_JSON="$unreviewed_json"
assert_blocked "sudo gh pr merge 123"
assert_blocked "sudo gh issue close 123"
assert_blocked "echo 123 | xargs gh pr merge"
assert_blocked "echo 123 | xargs gh issue close"
# reviewedラベルがあれば許可されること(fail-closeへの一律ブロックではないことの確認)
export GH_STUB_JSON="$approve_json"
assert_allowed "sudo gh pr merge 123"
# xargsの未知オプション(-Iなど)は実行内容を復元できないためfail-closeする
export GH_STUB_JSON="$unreviewed_json"
assert_blocked "echo 123 | xargs -I{} gh pr merge {}"
unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON

# 14-2. sudo/xargsが文字列中の引数・コメントに現れるだけの場合は誤検知しないこと(#388の再発防止)
assert_allowed 'echo "sudo gh pr merge 123"'
assert_allowed "git commit -m 'fix: xargs gh pr merge の例を追記'"
assert_allowed "# sudo gh pr merge 123 (コメント例)"
sudo_heredoc_cmd=$(printf '%s\n' \
	"cat > ./tmp/note.md <<'EOF14'" \
	"sudo gh pr merge 123 として実行しないこと" \
	"echo 123 | xargs gh issue close" \
	"EOF14")
assert_allowed "$sudo_heredoc_cmd"
# merge/close以外のsudo/xargs呼び出しはブロック対象外であること
assert_allowed "sudo gh pr view 123"
assert_allowed "echo 123 | xargs gh pr comment --body test"
unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON

# 破壊操作を伴わないシェル展開は許可すること(過剰遮断の防止)
assert_allowed 'PYTHON=python3; $PYTHON scripts/run.py'
assert_allowed 'echo "$(date)"'
assert_allowed 'REV=$(git rev-parse HEAD); echo "$REV"'
assert_allowed '$GH pr view 123'

# 11. jq不在時 -> exit 2 (fail-close, #339)
assert_blocked_without_jq "gh pr view 123"

# 12. heredocのブロック理由を終了コードごとに出し分けること
export GH_STUB_MATCH="pr view" GH_STUB_EXIT="0" GH_STUB_JSON="$unreviewed_json"
assert_blocked_with_message $'cat <<EOF11\ngh pr merge 123\n' "終端語が見つからず"
assert_blocked_with_message $'cat <<EOF12\n$(gh pr merge 123)\nEOF12' "コマンド置換が含まれ"
unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON

# 13. 関数内の想定外エラーもexit 2でブロックすること(errtrace未設定だとexit 1で素通りする)
assert_fail_close_on_internal_error "gh pr merge 123"

echo "block-github-destructive-actions: すべてのケースが期待通りです"
