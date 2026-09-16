#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
fixture_dir="$(mktemp -d)"
trap 'rm -rf -- "$fixture_dir"' EXIT

stub_path="$fixture_dir/gh"
export PATH="$fixture_dir:$PATH"

write_stub() {
	cat >"$stub_path"
	chmod +x "$stub_path"
}

write_stub <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$*" >>"${GH_CALL_LOG:?}"
case "$*" in
	"api repos/example/project/issues/42/labels")
		if grep -Fq -- "api -X POST repos/example/project/issues/42/labels -f labels[]=in-progress" "$GH_CALL_LOG"; then
			printf '%s\n' '[{"name":"task"},{"name":"in-progress"}]'
		else
			printf '%s\n' '[{"name":"task"},{"name":"review-request"}]'
		fi
		;;
	"api --include -X DELETE repos/example/project/issues/42/labels/review-request")
		printf '%s\n' 'HTTP/2.0 404 Not Found'
		exit 1
		;;
	"api -X POST repos/example/project/issues/42/labels -f labels[]=in-progress")
		;;
	*)
		echo "unexpected gh call: $*" >&2
		exit 1
		;;
esac
STUB

export GH_CALL_LOG="$fixture_dir/404-calls.log"
"$script_dir/set-review-state-label.sh" example/project 42 in-progress
grep -Fx -- 'api -X POST repos/example/project/issues/42/labels -f labels[]=in-progress' "$GH_CALL_LOG"
if grep -Fq -- 'labels/task' "$GH_CALL_LOG"; then
	echo "恒久ラベルを削除している" >&2
	exit 1
fi
unset GH_CALL_LOG

write_stub <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$*" >>"${GH_CALL_LOG:?}"
case "$*" in
	"api repos/example/project/issues/43/labels")
		printf '%s\n' '[{"name":"task"},{"name":"review-request"}]'
		;;
	"api --include -X DELETE repos/example/project/issues/43/labels/review-request")
		printf '%s\n' 'HTTP/2.0 401 Unauthorized'
		exit 1
		;;
	"api -X POST repos/example/project/issues/43/labels -f labels[]=in-progress")
		echo "認証エラー後に遷移先を付与している" >&2
		exit 1
		;;
	*)
		echo "unexpected gh call: $*" >&2
		exit 1
		;;
esac
STUB

export GH_CALL_LOG="$fixture_dir/401-calls.log"
if "$script_dir/set-review-state-label.sh" example/project 43 in-progress >"$fixture_dir/401-output.log" 2>&1; then
	echo "認証エラーを握りつぶしている" >&2
	exit 1
fi
if grep -Fq -- 'labels[]=in-progress' "$GH_CALL_LOG"; then
	echo "認証エラー後にPOSTしている" >&2
	exit 1
fi
grep -F -- '401 Unauthorized' "$fixture_dir/401-output.log"
unset GH_CALL_LOG

write_stub <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$*" >>"${GH_CALL_LOG:?}"
case "$*" in
	"api repos/example/project/issues/44/labels")
		printf '%s\n' '[{"name":"task"},{"name":"review-request"}]'
		;;
	"api --include -X DELETE repos/example/project/issues/44/labels/review-request")
		echo 'network unavailable' >&2
		exit 1
		;;
	"api -X POST repos/example/project/issues/44/labels -f labels[]=in-progress")
		echo "通信エラー後に遷移先を付与している" >&2
		exit 1
		;;
	*)
		echo "unexpected gh call: $*" >&2
		exit 1
		;;
esac
STUB

export GH_CALL_LOG="$fixture_dir/network-calls.log"
if "$script_dir/set-review-state-label.sh" example/project 44 in-progress >"$fixture_dir/network-output.log" 2>&1; then
	echo "通信エラーを握りつぶしている" >&2
	exit 1
fi
if grep -Fq -- 'labels[]=in-progress' "$GH_CALL_LOG"; then
	echo "通信エラー後に遷移先を付与している" >&2
	exit 1
fi
grep -F -- 'network unavailable' "$fixture_dir/network-output.log"
unset GH_CALL_LOG

write_stub <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$*" >>"${GH_CALL_LOG:?}"
case "$*" in
	"api repos/example/project/issues/45/labels")
		if grep -Fq -- "api -X POST repos/example/project/issues/45/labels -f labels[]=in-progress" "$GH_CALL_LOG"; then
			printf '%s\n' '[{"name":"task"},{"name":"in-progress"},{"name":"approve"}]'
		else
			printf '%s\n' '[{"name":"task"},{"name":"review-request"}]'
		fi
		;;
	"api --include -X DELETE repos/example/project/issues/45/labels/review-request")
		printf '%s\n' 'HTTP/2.0 204 No Content'
		;;
	"api -X POST repos/example/project/issues/45/labels -f labels[]=in-progress")
		;;
	*)
		echo "unexpected gh call: $*" >&2
		exit 1
		;;
esac
STUB

export GH_CALL_LOG="$fixture_dir/multiple-state-calls.log"
if "$script_dir/set-review-state-label.sh" example/project 45 in-progress >"$fixture_dir/multiple-state-output.log" 2>&1; then
	echo "複数の状態ラベルを検出できていない" >&2
	exit 1
fi
grep -F -- '状態ラベルの遷移後検証に失敗しました' "$fixture_dir/multiple-state-output.log"
unset GH_CALL_LOG

echo "set-review-state-label tests passed"
