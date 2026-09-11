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
cmd="$1 $2"
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

# 4. gh pr view 失敗時 -> exit 2 (fail-close)
export GH_STUB_EXIT="1"
assert_blocked "gh pr merge 123"
export GH_STUB_EXIT="0"

# 5. issue close のラベル有無2ケース
export GH_STUB_MATCH="issue view" GH_STUB_JSON="$unreviewed_json"
assert_blocked "gh issue close 123"
assert_blocked "gh --repo oikawa-d/task_management issue close 123"
export GH_STUB_JSON="$reviewed_json"
assert_allowed "gh issue close 123"

unset GH_STUB_MATCH GH_STUB_EXIT GH_STUB_JSON

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

echo "block-github-destructive-actions: すべてのケースが期待通りです"
