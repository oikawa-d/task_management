#!/usr/bin/env bash

set -euo pipefail

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

if grep -Eq '(^|[^[:alnum:]_-])gh[^;&|[:cntrl:]]*[[:space:]]+pr[[:space:]]+merge([[:space:]]|$)' <<<"$command"; then
	echo "ブロック: PRを作成したエージェントはPRをmergeできません。ユーザー承認後に別の操作主体で実行してください。" >&2
	exit 2
fi

if grep -Eq '(^|[^[:alnum:]_-])gh[^;&|[:cntrl:]]*[[:space:]]+issue[[:space:]]+close([[:space:]]|$)' <<<"$command"; then
	echo "ブロック: エージェントによるIssue closeは禁止されています。ユーザー承認後に別の操作主体で実行してください。" >&2
	exit 2
fi

api_put_regex='(^|[^[:alnum:]_-])gh[^;&|[:cntrl:]]*[[:space:]]+api[^;&|[:cntrl:]]*((--method[=[:space:]]+|-X[[:space:]]+)PUT[^;&|[:cntrl:]]*repos/[^[:space:];|&]+/pulls/[0-9]+/merge|repos/[^[:space:];|&]+/pulls/[0-9]+/merge[^;&|[:cntrl:]]*((--method[=[:space:]]+|-X[[:space:]]+)PUT))'
if grep -Eiq "$api_put_regex" <<<"$command"; then
	echo "ブロック: GitHub API経由のPR mergeは禁止されています。ユーザー承認後に別の操作主体で実行してください。" >&2
	exit 2
fi

if grep -Eiq '(^|[^[:alnum:]_-])gh[^;&|[:cntrl:]]*[[:space:]]+issue[^;&|[:cntrl:]]*[[:space:]]+edit[^;&|[:cntrl:]]+[[:space:]]+--state([=[:space:]]+)closed([[:space:]]|$)' <<<"$command"; then
	echo "ブロック: --state closedによるIssue closeは禁止されています。ユーザー承認後に別の操作主体で実行してください。" >&2
	exit 2
fi

exit 0
