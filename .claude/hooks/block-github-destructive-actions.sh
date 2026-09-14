#!/usr/bin/env bash

# 実装は .agents/hooks/block-github-destructive-actions.sh に一本化している。
# Claude Code / Codex で判定ロジックが乖離すると、片方だけレビューゲートを迂回できてしまうため、
# 各エージェント側にはリポジトリ内の共通実装を呼び出すラッパーのみを置く。
set -euo pipefail

hook_dir=$(cd "${BASH_SOURCE[0]%/*}" 2>/dev/null && pwd) || hook_dir="."
exec "$hook_dir/../../.agents/hooks/block-github-destructive-actions.sh" "$@"
