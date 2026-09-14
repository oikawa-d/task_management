#!/usr/bin/env bash

# Claude Code / Codex の設定ファイルに書かれたhookコマンドが、リポジトリの配置場所に依存せず
# 実際に起動できることを検証する。パスを絶対パスで固定すると、別のclone・worktreeでは
# hookが起動せず破壊操作ガードが無効化されるため、設定値そのものを展開して実行する。

set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/../.." && pwd)

work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT

# reviewedラベル無し(=ブロックされる)応答を返すghスタブ。
stub_dir="$work_dir/bin"
mkdir -p "$stub_dir"
cat > "$stub_dir/gh" <<'STUB'
#!/usr/bin/env bash
case "$1 $2" in
	"repo view") printf '%s' "oikawa-d/task_management" ;;
	"api graphql") printf '%s' '{"data":{"repository":{"issue":{"closedByPullRequestsReferences":{"nodes":[]}}}}}' ;;
	*) printf '%s' '{"labels":[]}' ;;
esac
STUB
chmod +x "$stub_dir/gh"

payload=$(jq -n '{tool_name: "Bash", tool_input: {command: "gh pr merge 123 --squash"}}')

# 設定ファイルからhookコマンドを取り出す。
hook_command() {
	local config=$1
	jq -r '.hooks.PreToolUse[0].hooks[0].command' "$config"
}

# 展開したhookコマンドを指定のcwd・環境で実行し、exit 2(ブロック)になることを確認する。
assert_config_blocks() {
	local label=$1 cwd=$2 command=$3
	shift 3
	local status=0 stderr
	stderr="$work_dir/stderr.log"
	printf '%s\n' "$payload" \
		| (cd "$cwd" && PATH="$stub_dir:$PATH" env "$@" bash -c "$command") >/dev/null 2>"$stderr" || status=$?
	if [[ "$status" -ne 2 ]]; then
		echo "設定ファイルのhookコマンドがブロックしませんでした (exit=$status): $label" >&2
		cat "$stderr" >&2
		return 1
	fi
	# hook内の想定外エラー(trap ... ERR)による偶然のexit 2ではなく、レビュー判定でブロックされたことを確認する。
	if ! grep -q "ラベルがありません" "$stderr"; then
		echo "レビュー判定以外の理由でブロックされました: $label" >&2
		cat "$stderr" >&2
		return 1
	fi
}

claude_command=$(hook_command "$repo_root/.claude/settings.json")
codex_command=$(hook_command "$repo_root/.codex/hooks.json")

# 1. Claude Code: $CLAUDE_PROJECT_DIR から解決できること
assert_config_blocks "claude/settings.json" "$repo_root" "$claude_command" "CLAUDE_PROJECT_DIR=$repo_root"

# 2. Codex: リポジトリ内をcwdとして起動した場合(gitから解決)
assert_config_blocks "codex/hooks.json (cwd=repo)" "$repo_root" "$codex_command"

# 3. Codex: リポジトリ外をcwdとしてCODEX_PROJECT_DIRを与えた場合
assert_config_blocks "codex/hooks.json (CODEX_PROJECT_DIR)" "$work_dir" "$codex_command" "CODEX_PROJECT_DIR=$repo_root"

# 4. 別の場所へ配置し直しても解決できること(パス固定でないことの検証)。
#    git管理外へコピーし、gitからの解決が失敗する経路も合わせて確認する。
copied_root="$work_dir/copied-repo"
mkdir -p "$copied_root"
cp -R "$repo_root/.agents" "$repo_root/.claude" "$repo_root/.codex" "$copied_root/"
assert_config_blocks "copied repo (cwd)" "$copied_root" "$codex_command"
assert_config_blocks "copied repo (CLAUDE_PROJECT_DIR)" "$work_dir" "$claude_command" "CLAUDE_PROJECT_DIR=$copied_root"

echo "hook-config: すべてのケースが期待通りです"
