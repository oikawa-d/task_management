#!/usr/bin/env bash

# `gh pr merge` / `gh issue close` のコマンド断片から、操作対象(PR/Issueのセレクタ)を解析する。
#
# 「最初に出現する数字」を対象番号とみなすと、オプション値やリポジトリ名に含まれる数字を
# 対象と誤認する(例: `gh issue close --comment "tracking 999" 123` で 999 を対象としてしまう)。
# レビュー状態を誤った番号で確認してしまうため、位置引数のみを対象として解析する。

# オプション値を取るフラグ(この次のトークンは位置引数ではない)。
GH_PR_MERGE_VALUE_FLAGS=(--author-email -A --body -b --body-file -F --match-head-commit --subject -t --repo -R)
# 値を取らないフラグ。
GH_PR_MERGE_BOOL_FLAGS=(--admin --auto --disable-auto --delete-branch -d --merge -m --rebase -r --squash -s --dry-run --help -h)
GH_ISSUE_CLOSE_VALUE_FLAGS=(--comment -c --reason -r --repo -R)
GH_ISSUE_CLOSE_BOOL_FLAGS=(--help -h)

# 配列に値が含まれるか判定する。
gh_contains() {
	local needle="$1"
	shift
	local item
	for item in "$@"; do
		[[ "$item" == "$needle" ]] && return 0
	done
	return 1
}

# セレクタがPR/IssueのURLの場合、URLに含まれるリポジトリ([HOST/]owner/repo)を取り出す。
gh_selector_to_repo() {
	local selector="$1"

	if [[ "$selector" =~ ^https?://([A-Za-z0-9.-]+(:[0-9]+)?)/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)/(issues|pull)/[0-9]+ ]]; then
		printf '%s/%s/%s' "${BASH_REMATCH[1]}" "${BASH_REMATCH[3]}" "${BASH_REMATCH[4]}"
		return 0
	fi
	return 1
}

# `[HOST/]OWNER/REPO` の形式を検証する。
gh_validate_repo_reference() {
	local repo="$1"

	[[ "$repo" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ||
		"$repo" =~ ^[A-Za-z0-9.-]+(:[0-9]+)?/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]]
}

# `[HOST/]OWNER/REPO` をホスト・owner・repoへ分解する。
# ホストが無い場合は空文字とし、ghの既定ホストを使用する。
gh_split_repo_reference() {
	local repo="$1"

	GH_REPO_HOST=""
	GH_REPO_OWNER=""
	GH_REPO_NAME=""

	if [[ "$repo" =~ ^([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)$ ]]; then
		GH_REPO_OWNER="${BASH_REMATCH[1]}"
		GH_REPO_NAME="${BASH_REMATCH[2]}"
		return 0
	fi
	if [[ "$repo" =~ ^([A-Za-z0-9.-]+(:[0-9]+)?)/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)$ ]]; then
		GH_REPO_HOST="${BASH_REMATCH[1]}"
		GH_REPO_OWNER="${BASH_REMATCH[3]}"
		GH_REPO_NAME="${BASH_REMATCH[4]}"
		return 0
	fi
	return 2
}

# トークンが `--repo` / `-R` のいずれかの形式なら、そのリポジトリ値を GH_TARGET_REPO へ格納する。
# 戻り値: 0=値を同一トークンから取得した / 1=次トークンが値(呼び出し側で読み飛ばす) / 2=該当なし
gh_take_repo_flag() {
	local token="$1"
	local next="${2:-}"

	case "$token" in
		--repo|-R)
			GH_TARGET_REPO="$next"
			return 1
			;;
		--repo=*)
			GH_TARGET_REPO="${token#*=}"
			return 0
			;;
		-R=*)
			GH_TARGET_REPO="${token#-R=}"
			return 0
			;;
		# pflagは短縮形に値を続けて書く `-Rowner/repo` 形式も受け付ける。
		-R?*)
			GH_TARGET_REPO="${token#-R}"
			return 0
			;;
	esac
	return 2
}

# 短縮形の値付きフラグに値が連結されている形式(`-Aauthor@example.com`等)を判定する。
# 完全一致のフラグは呼び出し側で次のトークンを値として消費するため、ここでは扱わない。
gh_is_attached_short_value_flag() {
	local token="$1"
	local flag

	shift
	for flag in "$@"; do
		[[ "$flag" == -? && "$token" == "$flag"?* ]] && return 0
	done
	return 1
}

# コマンド断片から操作対象のセレクタ(番号・URL・ブランチ名)と対象リポジトリを抽出する。
# 第1引数: pr-merge | issue-close
# 第2引数: コマンド断片
# 結果は GH_TARGET_SELECTOR / GH_TARGET_REPO へ格納する(いずれも該当が無ければ空文字)。
# リポジトリは「トークン化後の実オプション `--repo`/`-R`」→「セレクタのURL」の順で決定し、
# コメントや引用文字列の内容からは取得しない(誤ったリポジトリへ照会しないため)。
# 戻り値: 0=解析成功 / 2=解析不能(未知のフラグ等。呼び出し側でfail-closeする)
gh_parse_target() {
	local kind="$1"
	local segment="$2"
	local -a tokens=() value_flags=() bool_flags=()
	local subcommand='' action='' repo_from_url=''

	GH_TARGET_SELECTOR=""
	GH_TARGET_REPO=""

	case "$kind" in
		pr-merge)
			subcommand="pr"
			action="merge"
			value_flags=("${GH_PR_MERGE_VALUE_FLAGS[@]}")
			bool_flags=("${GH_PR_MERGE_BOOL_FLAGS[@]}")
			;;
		issue-close)
			subcommand="issue"
			action="close"
			value_flags=("${GH_ISSUE_CLOSE_VALUE_FLAGS[@]}")
			bool_flags=("${GH_ISSUE_CLOSE_BOOL_FLAGS[@]}")
			;;
		*)
			return 2
			;;
	esac

	while IFS= read -r -d '' line; do
		tokens+=("$line")
	done < <(gh_tokenize_segment "$segment")

	local index=0 total=${#tokens[@]} found=0
	# `gh ... <subcommand> <action>` の並びを探し、その直後から位置引数を解析する。
	for (( index = 0; index + 1 < total; index++ )); do
		if [[ "${tokens[index]}" == "$subcommand" && "${tokens[index + 1]}" == "$action" ]]; then
			found=1
			index=$(( index + 2 ))
			break
		fi
	done

	if (( ! found )); then
		return 2
	fi

	# `gh --repo owner/repo pr merge 123` のように、サブコマンドより前に置かれた
	# `--repo` / `-R` も有効なため、`gh` からサブコマンドまでの区間も解析する。
	local pre_index take_status
	for (( pre_index = 0; pre_index + 2 < index; pre_index++ )); do
		take_status=0
		gh_take_repo_flag "${tokens[pre_index]}" "${tokens[pre_index + 1]:-}" || take_status=$?
		if [[ "$take_status" -eq 1 ]]; then
			(( pre_index++ ))
		fi
	done

	local token end_of_options=0
	for (( ; index < total; index++ )); do
		token="${tokens[index]}"

		if (( ! end_of_options )); then
			if [[ "$token" == "--" ]]; then
				end_of_options=1
				continue
			fi

			# `--repo` / `-R` は形式が多いため、共通処理でまとめて解析する。
			take_status=0
			gh_take_repo_flag "$token" "${tokens[index + 1]:-}" || take_status=$?
			if [[ "$take_status" -eq 0 ]]; then
				continue
			elif [[ "$take_status" -eq 1 ]]; then
				(( index++ ))
				continue
			fi

			# `--flag=value` 形式は値が同一トークンに含まれるため、次トークンは消費しない。
			if [[ "$token" == --?*=* ]]; then
				if gh_contains "${token%%=*}" "${value_flags[@]}" || gh_contains "${token%%=*}" "${bool_flags[@]}"; then
					continue
				fi
				return 2
			fi

			if [[ "$token" == -* && "$token" != "-" ]]; then
				if gh_is_attached_short_value_flag "$token" "${value_flags[@]}"; then
					continue
				fi
				if gh_contains "$token" "${value_flags[@]}"; then
					(( index++ ))
					continue
				fi
				if gh_contains "$token" "${bool_flags[@]}"; then
					continue
				fi
				# 未知のフラグは値を取るか判断できないため、安全側で解析不能とする。
				return 2
			fi
		fi

		# 位置引数は最初の1つだけが操作対象。以降のトークンは `--repo` の検出のみ継続する。
		if [[ -z "$GH_TARGET_SELECTOR" ]]; then
			GH_TARGET_SELECTOR="$token"
		fi
	done

	# `--repo` の明示が無い場合のみ、セレクタのURLからリポジトリを決定する。
	if [[ -z "$GH_TARGET_REPO" ]]; then
		repo_from_url=$(gh_selector_to_repo "$GH_TARGET_SELECTOR") || repo_from_url=""
		GH_TARGET_REPO="$repo_from_url"
	fi

	if [[ -n "$GH_TARGET_REPO" ]] && ! gh_validate_repo_reference "$GH_TARGET_REPO"; then
		return 2
	fi

	# 位置引数なし(`gh pr merge --squash` のようにカレントブランチを対象とする形)もあり得る。
	return 0
}

# セレクタからIssue/PR番号を取り出す。番号・URLのみを受け付ける。
# 戻り値: 0=抽出成功(stdoutに番号) / 2=番号を特定できない
gh_selector_to_number() {
	local selector="$1"

	if [[ "$selector" =~ ^[0-9]+$ ]]; then
		printf '%s' "$selector"
		return 0
	fi

	if [[ "$selector" =~ ^https?://[^[:space:]]+/(issues|pull)/([0-9]+) ]]; then
		printf '%s' "${BASH_REMATCH[2]}"
		return 0
	fi

	return 2
}
