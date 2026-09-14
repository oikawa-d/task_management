#!/usr/bin/env bash

# ghコマンドを実行せず、シェル文字列から操作単位とトークンを解析する。

# 引用符内の改行を1トークンとして保持するため、NUL区切りで出力する。
gh_tokenize_segment() {
	local input="$1"
	local length=${#input}
	local index char quote='' token='' has_token=0

	for (( index = 0; index < length; index++ )); do
		char="${input:index:1}"
		if [[ -n "$quote" ]]; then
			if [[ "$char" == "$quote" ]]; then
				quote=''
			elif [[ "$quote" == '"' && "$char" == '\' ]]; then
				(( index++ ))
				token+="${input:index:1}"
			else
				token+="$char"
			fi
			continue
		fi

		case "$char" in
			\'|\") quote="$char"; has_token=1 ;;
			'\')
				(( index++ ))
				token+="${input:index:1}"
				has_token=1
				;;
			[[:space:]])
				if (( has_token )); then
					printf '%s\0' "$token"
					token=''
					has_token=0
				fi
				;;
			*) token+="$char"; has_token=1 ;;
		esac
	done

	if (( has_token )); then
		printf '%s\0' "$token"
	fi
}

# 引用符外のシェル区切り文字ごとに分割し、GH_COMMAND_SEGMENTSへ格納する。
gh_split_command_segments() {
	local input="$1"
	local length=${#input}
	local index char quote='' segment=''
	GH_COMMAND_SEGMENTS=()

	for (( index = 0; index < length; index++ )); do
		char="${input:index:1}"
		if [[ -n "$quote" ]]; then
			segment+="$char"
			if [[ "$char" == "$quote" ]]; then
				quote=''
			elif [[ "$quote" == '"' && "$char" == '\' ]]; then
				(( index++ ))
				segment+="${input:index:1}"
			fi
			continue
		fi

		case "$char" in
			\'|\") quote="$char"; segment+="$char" ;;
			'\')
				segment+="$char"
				(( index++ ))
				segment+="${input:index:1}"
				;;
			';'|'&'|'|'|'`'|'('|')'|$'\n')
				if [[ -n "${segment//[[:space:]]/}" ]]; then
					GH_COMMAND_SEGMENTS+=("$segment")
				fi
				segment=''
				;;
			*) segment+="$char" ;;
		esac
	done

	if [[ -n "${segment//[[:space:]]/}" ]]; then
		GH_COMMAND_SEGMENTS+=("$segment")
	fi
}

gh_load_segment_tokens() {
	local segment="$1" token
	GH_SEGMENT_TOKENS=()
	while IFS= read -r -d '' token; do
		GH_SEGMENT_TOKENS+=("$token")
	done < <(gh_tokenize_segment "$segment")
}

gh_segment_is_action() {
	local segment="$1" subcommand="$2" action="$3" index
	gh_load_segment_tokens "$segment"
	[[ "${GH_SEGMENT_TOKENS[0]:-}" == "gh" ]] || return 1
	for (( index = 1; index + 1 < ${#GH_SEGMENT_TOKENS[@]}; index++ )); do
		if [[ "${GH_SEGMENT_TOKENS[index]}" == "$subcommand" &&
			"${GH_SEGMENT_TOKENS[index + 1]}" == "$action" ]]; then
			return 0
		fi
	done
	return 1
}

gh_segment_is_api_merge() {
	local segment="$1" token previous='' has_api=0 has_put=0 has_endpoint=0
	gh_load_segment_tokens "$segment"
	[[ "${GH_SEGMENT_TOKENS[0]:-}" == "gh" ]] || return 1
	for token in "${GH_SEGMENT_TOKENS[@]:1}"; do
		[[ "$token" == "api" ]] && has_api=1
		if [[ "${token^^}" =~ ^(-X=?|--METHOD=)PUT$ ||
			"${previous^^}" == "-X" && "${token^^}" == "PUT" ||
			"${previous^^}" == "--METHOD" && "${token^^}" == "PUT" ]]; then
			has_put=1
		fi
		[[ "$token" =~ ^repos/[^/]+/[^/]+/pulls/[0-9]+/merge$ ]] && has_endpoint=1
		previous="$token"
	done
	(( has_api && has_put && has_endpoint ))
}

gh_segment_is_issue_state_close() {
	local segment="$1" token previous='' has_closed=0
	gh_segment_is_action "$segment" "issue" "edit" || return 1
	for token in "${GH_SEGMENT_TOKENS[@]}"; do
		if [[ "${token,,}" == "--state=closed" ||
			"$previous" == "--state" && "${token,,}" == "closed" ]]; then
			has_closed=1
		fi
		previous="$token"
	done
	(( has_closed ))
}
