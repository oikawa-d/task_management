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

case "$target_label" in
	review-request|in-progress|approve|none) ;;
	*)
		usage
		exit 2
		;;
esac

labels_json="$(gh api "repos/${repo_name}/issues/${target_number}/labels")"

while IFS= read -r label_name; do
	case "$label_name" in
		review-request|in-progress|approve)
		gh api -X DELETE "repos/${repo_name}/issues/${target_number}/labels/${label_name}" >/dev/null
		;;
	esac
done < <(jq -r '.[].name' <<<"$labels_json")

if [[ "$target_label" != "none" ]]; then
	gh api -X POST "repos/${repo_name}/issues/${target_number}/labels" \
		-f "labels[]=${target_label}" >/dev/null
fi
