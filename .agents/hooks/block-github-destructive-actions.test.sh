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
		# JSONに `}` を含むため `${VAR:-default}` のデフォルト値では書けない。
		if [[ -z "${GH_STUB_GRAPHQL_JSON:-}" ]]; then
			GH_STUB_GRAPHQL_JSON='{"data":{"repository":{"issue":{"closedByPullRequestsReferences":{"nodes":[]}}}}}'
		fi
		printf '%s' "$GH_STUB_GRAPHQL_JSON"
		exit 0
		;;
esac
if [[ "$cmd" == "${GH_STUB_MATCH:-}" ]]; then
	if [[ -n "${GH_STUB_EXIT:-}" && "${GH_STUB_EXIT}" != "0" ]]; then
		exit "${GH_STUB_EXIT}"
	fi
	json="${GH_STUB_JSON:-}"
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

reviewed_json='{"labels":[{"name":"reviewed"}]}'
unreviewed_json='{"labels":[]}'

unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON

# --- 基本ケース(gh呼び出しを伴わない) ---
assert_allowed "gh pr view 123"
assert_allowed "git commit -m 'test'"

# 1. reviewedラベル無しのPRへのマージ -> exit 2
export GH_STUB_MATCH="pr view" GH_STUB_EXIT="0" GH_STUB_JSON="$unreviewed_json"
assert_blocked "gh pr merge 123 --squash"
assert_blocked "gh --repo oikawa-d/task_management pr merge 123"

# 2. reviewedラベル有りのPRへのマージ -> exit 0
export GH_STUB_JSON="$reviewed_json"
assert_allowed "gh pr merge 123 --squash"

# 3. PR番号省略時にカレントブランチのPRで判定されること
assert_allowed "gh pr merge --squash"
export GH_STUB_JSON="$unreviewed_json"
assert_blocked "gh pr merge --squash"

# 3-2. オプション値・フラグの数字を対象PRと誤認しないこと
export GH_STUB_JSON="$unreviewed_json"
assert_gh_called_with 'gh pr merge --subject "fix 999" 123 --squash' 'pr view 123'
assert_gh_called_with 'gh pr merge --body-file /tmp/999.md 123' 'pr view 123'
assert_gh_called_with "gh pr merge --squash feature/issue-999" 'pr view feature/issue-999'

# 3-4. `--repo` やURLで指定した別リポジトリのPRを照会すること
# カレントリポジトリの同番号PRのreviewed状態で許可・拒否してはならない。
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
# サブコマンド後の短縮形の値連結(`-Rowner/repo`)も同様に解析すること
assert_gh_called_with "gh pr merge 123 -Revil/other" 'pr view 123 --json labels --repo evil/other'

# 3-3. 未知のフラグはブロックすること(fail-close)
assert_blocked "gh pr merge --unknown-option 999 123"

# 4. gh pr view 失敗時 -> exit 2 (fail-close)
export GH_STUB_EXIT="1"
assert_blocked "gh pr merge 123"
export GH_STUB_EXIT="0"

# 5. issue close は「issueを閉じるPR」のreviewedラベルで判定する(#401)
# issue自身のラベルでは判定しないため、issueにreviewedが付いていても許可してはならない。
linked_reviewed_json='{"data":{"repository":{"issue":{"closedByPullRequestsReferences":{"nodes":[{"number":362,"labels":{"nodes":[{"name":"reviewed"}]}}]}}}}}'
linked_unreviewed_json='{"data":{"repository":{"issue":{"closedByPullRequestsReferences":{"nodes":[{"number":374,"labels":{"nodes":[{"name":"review-requested"}]}}]}}}}}'
linked_none_json='{"data":{"repository":{"issue":{"closedByPullRequestsReferences":{"nodes":[]}}}}}'

# 5-1. リンクPRにreviewedあり -> exit 0
export GH_STUB_GRAPHQL_JSON="$linked_reviewed_json"
assert_allowed "gh issue close 123"
assert_allowed "gh --repo oikawa-d/task_management issue close 123"
assert_allowed "gh issue close 123 --comment '対応完了'"

# 5-2. リンクPRはあるがreviewedなし -> exit 2
export GH_STUB_GRAPHQL_JSON="$linked_unreviewed_json"
assert_blocked "gh issue close 123"

# 5-3. リンクPRが無い(PR本文にClosesが無い) -> exit 2
export GH_STUB_GRAPHQL_JSON="$linked_none_json"
assert_blocked "gh issue close 123"

# 5-4. issue自身にreviewedラベルがあってもリンクPRが未reviewedならブロックされること
export GH_STUB_GRAPHQL_JSON="$linked_unreviewed_json" GH_STUB_MATCH="issue view" GH_STUB_JSON="$reviewed_json"
assert_blocked "gh issue close 123"
unset GH_STUB_MATCH GH_STUB_JSON

# 5-5. GraphQL呼び出し失敗 -> exit 2 (fail-close)
export GH_STUB_GRAPHQL_JSON="$linked_reviewed_json" GH_STUB_GRAPHQL_EXIT="1"
assert_blocked "gh issue close 123"
unset GH_STUB_GRAPHQL_EXIT

# 5-6. リポジトリ解決失敗 -> exit 2 (fail-close)。--repo指定があれば解決不要で許可される。
export GH_STUB_REPO_EXIT="1"
assert_blocked "gh issue close 123"
assert_allowed "gh issue close 123 --repo oikawa-d/task_management"
assert_allowed "gh issue close 123 -R oikawa-d/task_management"
unset GH_STUB_REPO_EXIT

# 5-7. issue番号を特定できない -> exit 2 (fail-close)
assert_blocked "gh issue close"

unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON GH_STUB_GRAPHQL_JSON

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
assert_gh_called_with "gh issue close 123 -Revil/other" 'owner=evil -F repo=other -F number=123'
# サブコマンド前後いずれの位置でも、引用文字列の内容は実オプションとして扱わないこと
assert_gh_not_called_with 'gh issue close --comment "see gh --repo evil/other issue close 999" 123' 'owner=evil'

# 5-9. 未知のフラグは値を取るか判断できないため解析不能としてブロックすること(fail-close)
assert_blocked "gh issue close --unknown-option 999 123"

unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON GH_STUB_GRAPHQL_JSON

# 6. heredoc本文にコマンド名を含むだけのコマンド -> exit 0 (#388の回帰テスト)
heredoc_cmd=$(printf '%s\n' \
	"cat > ./tmp/handover.md <<'XEOF'" \
	"reviewed付与済み＋CI全チェック成功なら gh pr merge してよい" \
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
assert_allowed "# gh pr merge 123 (コメント例)"

# 8. 実際のマージコマンドは引き続きブロックされること(区切り文字経由も含む)
export GH_STUB_MATCH="pr view" GH_STUB_EXIT="0" GH_STUB_JSON="$unreviewed_json"
assert_blocked "git status; gh pr merge 123"
assert_blocked "true && gh pr merge 123"
assert_blocked "gh pr merge 123 || echo fallback"
# この文字列は実行されず、hookへの入力データとして渡すだけのため展開させない意図で単一引用符を使用する。
# shellcheck disable=SC2016
assert_blocked '$(echo dummy); gh pr merge 123'
unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON

# 9. 想定外エラー時 -> exit 2 (trap ... ERR)
assert_blocked_raw_stdin "これは不正なJSONです"

# 10. `gh pr merge` / `gh issue close` の代替経路 -> exit 2 (#339)
assert_blocked "gh api -X PUT repos/oikawa-d/task_management/pulls/123/merge"
assert_blocked "gh api repos/oikawa-d/task_management/pulls/123/merge --method PUT"
assert_blocked "gh issue edit 123 --state closed"
assert_blocked "gh --repo oikawa-d/task_management issue edit 123 --state=closed"

# 11. jq不在時 -> exit 2 (fail-close, #339)
assert_blocked_without_jq "gh pr view 123"

echo "block-github-destructive-actions: すべてのケースが期待通りです"
