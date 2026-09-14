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

# トップレベルとコマンド置換内の実行単位をまとめて返す。
gh_collect_executable_segments() {
	local input="$1" substitution current queue_index
	local -a result=() substitutions=() split_segments=() queue=("$1")

	gh_split_command_segments "$input"
	result=("${GH_COMMAND_SEGMENTS[@]}")
	for (( queue_index = 0; queue_index < ${#queue[@]}; queue_index++ )); do
		current="${queue[queue_index]}"
		gh_extract_command_substitutions "$current"
		substitutions=("${GH_COMMAND_SUBSTITUTIONS[@]}")
		gh_extract_backtick_substitutions "$current"
		substitutions+=("${GH_BACKTICK_SUBSTITUTIONS[@]}")
		for substitution in "${substitutions[@]}"; do
			gh_split_command_segments "$substitution"
			split_segments=("${GH_COMMAND_SEGMENTS[@]}")
			result+=("${split_segments[@]}")
			queue+=("$substitution")
		done
	done
	GH_COMMAND_SEGMENTS=("${result[@]}")
}

gh_load_segment_tokens() {
	local segment="$1" token
	GH_SEGMENT_TOKENS=()
	while IFS= read -r -d '' token; do
		GH_SEGMENT_TOKENS+=("$token")
	done < <(gh_tokenize_segment "$segment")
}

# 複合構文の予約語等を読み飛ばし、実行位置にあるghのトークン番号を返す。
gh_find_executable_gh_index() {
	local index prefix_index token
	GH_COMMAND_INDEX=-1
	for (( index = 0; index < ${#GH_SEGMENT_TOKENS[@]}; index++ )); do
		[[ "${GH_SEGMENT_TOKENS[index]}" == "gh" ]] || continue
		for (( prefix_index = 0; prefix_index < index; prefix_index++ )); do
			token="${GH_SEGMENT_TOKENS[prefix_index]}"
			case "$token" in
				if|then|elif|else|while|until|do|'{'|'('|!|time|command|builtin|env) ;;
				[A-Za-z_][A-Za-z0-9_]*=*) ;;
				*) break 2 ;;
			esac
		done
		GH_COMMAND_INDEX=$index
		return 0
	done
	return 1
}

gh_segment_is_action() {
	local segment="$1" subcommand="$2" action="$3" index
	gh_load_segment_tokens "$segment"
	gh_find_executable_gh_index || return 1
	for (( index = GH_COMMAND_INDEX + 1; index + 1 < ${#GH_SEGMENT_TOKENS[@]}; index++ )); do
		if [[ "${GH_SEGMENT_TOKENS[index]}" == "$subcommand" &&
			"${GH_SEGMENT_TOKENS[index + 1]}" == "$action" ]]; then
			return 0
		fi
	done
	return 1
}

gh_segment_is_api_merge() {
	local segment="$1" token method_value option_value_kind='' endpoint=''
	local has_put=0 has_dynamic_method=0 api_index=-1 index
	gh_load_segment_tokens "$segment"
	gh_find_executable_gh_index || return 1
	for (( index = GH_COMMAND_INDEX + 1; index < ${#GH_SEGMENT_TOKENS[@]}; index++ )); do
		token="${GH_SEGMENT_TOKENS[index]}"
		if [[ "$token" == "api" ]]; then
			api_index=$index
			break
		fi
	done
	(( api_index >= 0 )) || return 1

	for (( index = api_index + 1; index < ${#GH_SEGMENT_TOKENS[@]}; index++ )); do
		token="${GH_SEGMENT_TOKENS[index]}"
		if [[ -n "$option_value_kind" ]]; then
			if [[ "$option_value_kind" == "method" ]]; then
				[[ "${token^^}" == "PUT" ]] && has_put=1
				[[ "$token" == *'$'* || "$token" == *'`'* ]] && has_dynamic_method=1
			fi
			option_value_kind=''
			continue
		fi

		case "$token" in
			-X|--method) option_value_kind='method'; continue ;;
			-X?*|--method=*)
				if [[ "$token" == -X* ]]; then
					method_value="${token#-X}"
					method_value="${method_value#=}"
				else
					method_value="${token#--method=}"
				fi
				if [[ "$method_value" == *'$'* || "$method_value" == *'`'* ]]; then
					has_dynamic_method=1
				elif [[ "${method_value^^}" == "PUT" ]]; then
					has_put=1
				fi
				continue
				;;
			-f|-F|--raw-field|--field|--input|--hostname|--cache)
				option_value_kind='other'
				continue
				;;
			-f?*|-F?*|--raw-field=*|--field=*|--input=*|--hostname=*|--cache=*) continue ;;
			--) continue ;;
			-*) continue ;;
		esac
		if [[ -z "$endpoint" ]]; then
			endpoint="$token"
		fi
	done

	if [[ "$endpoint" =~ ^/?repos/[^/]+/[^/]+/pulls/[0-9]+/merge(\?.*)?$ ]]; then
		(( has_put || has_dynamic_method ))
		return
	fi
	if [[ "$endpoint" == *'$'* || "$endpoint" == *'`'* ]]; then
		(( has_put ))
		return
	fi
	return 1
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
