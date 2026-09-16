#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
fixture_dir="$(mktemp -d)"
trap 'rm -rf -- "$fixture_dir"' EXIT

cat >"$fixture_dir/gh" <<'EOF'
#!/usr/bin/env bash

set -euo pipefail

printf '%s\n' "$*" >>"${GH_CALL_LOG:?}"

if [[ "$*" == "api repos/example/project/issues/42/labels" ]]; then
	printf '%s\n' '[{"name":"task"},{"name":"review-request"}]'
elif [[ "$*" == *"labels/in-progress"* ]]; then
	echo "unexpected deletion of absent label" >&2
	exit 1
fi
EOF
chmod +x "$fixture_dir/gh"

export GH_CALL_LOG="$fixture_dir/gh-calls.log"
export PATH="$fixture_dir:$PATH"

"$script_dir/set-review-state-label.sh" example/project 42 in-progress

grep -Fx -- 'api repos/example/project/issues/42/labels' "$GH_CALL_LOG"
grep -Fx -- 'api -X DELETE repos/example/project/issues/42/labels/review-request' "$GH_CALL_LOG"
grep -Fx -- 'api -X POST repos/example/project/issues/42/labels -f labels[]=in-progress' "$GH_CALL_LOG"
if grep -Fq -- 'labels/task' "$GH_CALL_LOG"; then
	echo "恒久ラベルを削除している" >&2
	exit 1
fi

cat >"$fixture_dir/gh" <<'EOF'
#!/usr/bin/env bash

set -euo pipefail

if [[ "$*" == "api repos/example/project/issues/43/labels" ]]; then
	echo "labels lookup failed" >&2
	exit 1
fi
EOF
chmod +x "$fixture_dir/gh"
if "$script_dir/set-review-state-label.sh" example/project 43 none; then
	echo "ラベル取得エラーを握りつぶしている" >&2
	exit 1
fi
