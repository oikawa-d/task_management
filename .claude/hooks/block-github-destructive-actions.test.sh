#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
hook="$script_dir/block-github-destructive-actions.sh"

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
	rm -f "$fake_path"/*
	rmdir "$fake_path"
	if [[ "$status" -ne 2 ]]; then
		echo "jq不在時にhookがexit 2でブロックしませんでした (exit=$status): $command" >&2
		return 1
	fi
}

assert_allowed "gh pr view 123"
assert_allowed "git commit -m 'test'"
assert_blocked "gh pr merge 123 --squash"
assert_blocked "gh --repo oikawa-d/task_management pr merge 123"
assert_blocked "gh issue close 123"
assert_blocked "gh --repo oikawa-d/task_management issue close 123"
assert_blocked "gh api -X PUT repos/oikawa-d/task_management/pulls/123/merge"
assert_blocked "gh api repos/oikawa-d/task_management/pulls/123/merge --method PUT"
assert_blocked "gh issue edit 123 --state closed"
assert_blocked "gh --repo oikawa-d/task_management issue edit 123 --state=closed"
assert_blocked "git status; gh pr merge 123"
assert_blocked_without_jq "gh pr view 123"

echo "block-github-destructive-actions: すべてのケースが期待通りです"
