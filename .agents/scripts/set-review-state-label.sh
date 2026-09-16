#!/usr/bin/env bash

set -euo pipefail

usage() {
	echo "usage: $0 <owner/repo> <issue-or-pr-number> <review-request|in-progress|approve|none>" >&2
}

if [[ $# -ne 3 ]]; then
	usage
	exit 2
fi

repo_name="$1"
target_number="$2"
target_label="$3"
state_labels_json='["review-request","in-progress","approve"]'
endpoint="repos/${repo_name}/issues/${target_number}/labels"

if [[ ! "$repo_name" =~ ^[^/]+/[^/]+$ || ! "$target_number" =~ ^[0-9]+$ ]]; then
	usage
	exit 2
fi

case "$target_label" in
	review-request|in-progress|approve|none) ;;
	*)
		usage
		exit 2
		;;
esac

delete_state_label() {
	local label_name="$1"
	local response http_status

	if response="$(gh api --include -X DELETE "${endpoint}/${label_name}" 2>&1)"; then
		return 0
	fi

	http_status="$(sed -n 's/^HTTP\/[^ ]*[[:space:]]\+\([0-9][0-9][0-9]\).*/\1/p' <<<"$response" | head -n 1)"
	if [[ "$http_status" == "404" ]]; then
		return 0
	fi

	printf '%s\n' "$response" >&2
	return 1
}

labels_json="$(gh api "$endpoint")"

while IFS= read -r label_name; do
	[[ -z "$label_name" ]] && continue
	delete_state_label "$label_name"
done < <(
	jq -r --argjson state_labels "$state_labels_json" \
		'[.[] | select(.name as $label | ($state_labels | index($label)) != null) | .name] | .[]' \
		<<<"$labels_json"
)

if [[ "$target_label" != "none" ]]; then
	gh api -X POST "$endpoint" \
		-f "labels[]=${target_label}" >/dev/null
fi

labels_json="$(gh api "$endpoint")"
actual_state_labels="$(
	jq -r --argjson state_labels "$state_labels_json" \
		'[.[] | select(.name as $label | ($state_labels | index($label)) != null) | .name] | join(",")' \
		<<<"$labels_json"
)"
expected_state_labels=""
if [[ "$target_label" != "none" ]]; then
	expected_state_labels="$target_label"
fi

if [[ "$actual_state_labels" != "$expected_state_labels" ]]; then
	echo "状態ラベルの遷移後検証に失敗しました: expected=${expected_state_labels:-none}, actual=${actual_state_labels:-none}" >&2
	exit 1
fi
