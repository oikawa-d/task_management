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
	if payload "$command" | "$hook" >/dev/null 2>&1; then
		echo "禁止されるコマンドが許可されました: $command" >&2
		return 1
	fi
}

assert_allowed "gh pr view 123"
assert_allowed "git commit -m 'test'"
assert_blocked "gh pr merge 123 --squash"
assert_blocked "gh issue close 123"
assert_blocked "git status; gh pr merge 123"
