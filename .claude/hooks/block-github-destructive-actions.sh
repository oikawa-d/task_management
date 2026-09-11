#!/usr/bin/env bash

set -euo pipefail

REVIEWED_LABEL="reviewed"

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
if grep -Eq '(^|[^[:alnum:]_-])gh[^;&|[:cntrl:]]*[[:space:]]+pr[[:space:]]+merge([[:space:]]|$)' <<<"$command"; then
	merge_segment=$(grep -Eo 'gh[^;&|[:cntrl:]]*[[:space:]]+pr[[:space:]]+merge[^;&|[:cntrl:]]*' <<<"$command" | head -1)
	pr_number=$(grep -Eo '[0-9]+' <<<"$merge_segment" | head -1 || true)

	status=0
	has_reviewed_label "pr" "$pr_number" || status=$?

	if [[ "$status" -eq 0 ]]; then
		exit 0
	elif [[ "$status" -eq 2 ]]; then
		echo "ブロック: 対象PRの情報取得(gh pr view)に失敗したため、安全側でmergeをブロックします。ネットワークやPR番号を確認してください。" >&2
		exit 2
	else
		echo "ブロック: 対象PRに '${REVIEWED_LABEL}' ラベルがありません。.agents/review-policy.md に沿ったレビューで「受入可」のコメントを投稿したうえで、PR作成者以外がラベルを付与してください（例: gh pr edit <PR番号> --add-label ${REVIEWED_LABEL}）。" >&2
		exit 2
	fi
fi

# `gh issue close` を検出したら、対象issueにreviewedラベルがある場合のみ許可する。
if grep -Eq '(^|[^[:alnum:]_-])gh[^;&|[:cntrl:]]*[[:space:]]+issue[[:space:]]+close([[:space:]]|$)' <<<"$command"; then
	close_segment=$(grep -Eo 'gh[^;&|[:cntrl:]]*[[:space:]]+issue[[:space:]]+close[^;&|[:cntrl:]]*' <<<"$command" | head -1)
	issue_number=$(grep -Eo '[0-9]+' <<<"$close_segment" | head -1 || true)

	status=0
	has_reviewed_label "issue" "$issue_number" || status=$?

	if [[ "$status" -eq 0 ]]; then
		exit 0
	elif [[ "$status" -eq 2 ]]; then
		echo "ブロック: 対象issueの情報取得(gh issue view)に失敗、またはissue番号を特定できなかったため、安全側でcloseをブロックします。" >&2
		exit 2
	else
		echo "ブロック: 対象issueに '${REVIEWED_LABEL}' ラベルがありません。.agents/review-policy.md に沿ったレビューで「受入可」のコメントを投稿したうえで、PR作成者以外がラベルを付与してください（例: gh issue edit <Issue番号> --add-label ${REVIEWED_LABEL}）。" >&2
		exit 2
	fi
fi

exit 0
