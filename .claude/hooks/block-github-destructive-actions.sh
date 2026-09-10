#!/usr/bin/env bash

set -euo pipefail

input=$(cat)
tool_name=$(jq -r '.tool_name // empty' <<<"$input")

if [[ "$tool_name" != "Bash" ]]; then
	exit 0
fi

command=$(jq -r '.tool_input.command // empty' <<<"$input")

if [[ "$command" =~ (^|[[:space:];&|])gh[[:space:]]+pr[[:space:]]+merge([[:space:]]|$) ]]; then
	echo "ブロック: PRを作成したエージェントはPRをmergeできません。ユーザー承認後に別の操作主体で実行してください。" >&2
	exit 2
fi

if [[ "$command" =~ (^|[[:space:];&|])gh[[:space:]]+issue[[:space:]]+close([[:space:]]|$) ]]; then
	echo "ブロック: エージェントによるIssue closeは禁止されています。ユーザー承認後に別の操作主体で実行してください。" >&2
	exit 2
fi

exit 0
