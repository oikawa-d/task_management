#!/usr/bin/env bash

# シェル文字列から、引用符内でも実行されるコマンド置換の本体を抽出する。

# `$( ... )` またはバッククォートの終端位置を求め、GH_SUBSTITUTION_END へ返す。
# start には `$` またはバッククォートの位置を渡す。
# 引用符内の括弧・バッククォートは終端として扱わない。終端が無い場合は入力末尾を返す。
gh_scan_substitution_end() {
	local input="$1" start="$2" length=${#input}
	local index char quote='' depth=0
	GH_SUBSTITUTION_END=$(( length - 1 ))

	if [[ "${input:start:1}" == '`' ]]; then
		for (( index = start + 1; index < length; index++ )); do
			char="${input:index:1}"
			if [[ "$char" == '\' ]]; then
				index=$(( index + 1 ))
			elif [[ "$char" == '`' ]]; then
				GH_SUBSTITUTION_END=$index
				return 0
			fi
		done
		return 0
	fi

	for (( index = start + 1; index < length; index++ )); do
		char="${input:index:1}"
		if [[ -n "$quote" ]]; then
			if [[ "$quote" == '"' && "$char" == '\' ]]; then
				index=$(( index + 1 ))
			elif [[ "$char" == "$quote" ]]; then
				quote=''
			fi
			continue
		fi
		case "$char" in
			\'|\") quote="$char" ;;
			'\') index=$(( index + 1 )) ;;
			'(') depth=$(( depth + 1 )) ;;
			')')
				depth=$(( depth - 1 ))
				if (( depth == 0 )); then
					GH_SUBSTITUTION_END=$index
					return 0
				fi
				;;
		esac
	done
	return 0
}

# コマンド置換 `$( ... )` の本体を抽出する。
# 単一引用符内は展開されないため対象外、二重引用符内は展開されるため対象とする。
# ネストした置換は抽出結果をさらに解析することで検査される(gh_collect_executable_segments)。
gh_extract_command_substitutions() {
	local input="$1" length=${#1}
	local index char quote=''
	GH_COMMAND_SUBSTITUTIONS=()

	for (( index = 0; index < length; index++ )); do
		char="${input:index:1}"
		if [[ "$quote" == "'" ]]; then
			[[ "$char" == "'" ]] && quote=''
			continue
		fi
		if [[ "$char" == '\' ]]; then
			index=$(( index + 1 ))
			continue
		fi
		if [[ "$char" == '"' ]]; then
			if [[ "$quote" == '"' ]]; then quote=''; else quote='"'; fi
			continue
		fi
		if [[ -z "$quote" && "$char" == "'" ]]; then
			quote="'"
			continue
		fi
		if [[ "$char" == '$' && "${input:index + 1:1}" == '(' ]]; then
			gh_scan_substitution_end "$input" "$index"
			GH_COMMAND_SUBSTITUTIONS+=("${input:index + 2:GH_SUBSTITUTION_END - index - 2}")
			index=$GH_SUBSTITUTION_END
		fi
	done
}

# バッククォートによるコマンド置換の本体を抽出する。
gh_extract_backtick_substitutions() {
	local input="$1" length=${#1}
	local index char quote=''
	GH_BACKTICK_SUBSTITUTIONS=()

	for (( index = 0; index < length; index++ )); do
		char="${input:index:1}"
		if [[ "$quote" == "'" ]]; then
			[[ "$char" == "'" ]] && quote=''
			continue
		fi
		if [[ "$char" == '\' ]]; then
			index=$(( index + 1 ))
			continue
		fi
		if [[ "$char" == '"' ]]; then
			if [[ "$quote" == '"' ]]; then quote=''; else quote='"'; fi
			continue
		fi
		if [[ -z "$quote" && "$char" == "'" ]]; then
			quote="'"
			continue
		fi
		if [[ "$char" == '`' ]]; then
			gh_scan_substitution_end "$input" "$index"
			GH_BACKTICK_SUBSTITUTIONS+=("${input:index + 1:GH_SUBSTITUTION_END - index - 1}")
			index=$GH_SUBSTITUTION_END
		fi
	done
}
