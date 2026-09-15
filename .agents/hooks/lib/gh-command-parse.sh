#!/usr/bin/env bash

# ghコマンドを実行せず、シェル文字列から操作単位とトークンを解析する。

# トークンがシェル展開(変数展開・コマンド置換)を含むかを判定する。
gh_token_is_dynamic() {
	[[ "$1" == *'$'* || "$1" == *'`'* ]]
}

# 実行ファイル名がghのパス指定も対象にする。
gh_token_is_gh_command() {
	[[ "$1" == "gh" || "${1##*/}" == "gh" ]] || gh_token_is_dynamic "$1"
}

# 実行可能な前置wrapperは、絶対・相対パスで指定される場合もあるためbasenameで判定する。
# sudo/xargsは`gh`が実行位置に来る一般的な前置形(`sudo gh pr merge 123` /
# `echo 123 | xargs gh pr merge`)のみを対象とし、未知オプションは他wrapper同様に
# fail-closeする(#390)。xargsは本来複数回実行され得るが、位置引数として書かれた
# PR/Issue番号の検査には支障がないため同じ枠組みで扱う。
gh_token_is_known_wrapper() {
	case "${1##*/}" in
		time|command|builtin|env|exec|sudo|xargs) return 0 ;;
		*) return 1 ;;
	esac
}

# 引用符内の改行を1トークンとして保持するため、NUL区切りで出力する。
# `$( ... )` とバッククォートは、空白や `(` `)` で分割するとコマンド名が `$(which gh)` の形の
# ときに実行位置を見失うため、1トークンとして保持する(終端走査は gh-substitution-parse.sh)。
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
				index=$(( index + 1 ))
				token+="${input:index:1}"
			else
				token+="$char"
			fi
			continue
		fi

		case "$char" in
			\'|\") quote="$char"; has_token=1 ;;
			'$')
				if [[ "${input:index+1:1}" == '(' ]]; then
					gh_scan_substitution_end "$input" "$index"
					token+="${input:index:GH_SUBSTITUTION_END - index + 1}"
					index=$GH_SUBSTITUTION_END
					has_token=1
					continue
				fi
				token+="$char"
				has_token=1
				;;
			'`')
				gh_scan_substitution_end "$input" "$index"
				token+="${input:index:GH_SUBSTITUTION_END - index + 1}"
				index=$GH_SUBSTITUTION_END
				has_token=1
				continue
				;;
			'\')
				index=$(( index + 1 ))
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
				index=$(( index + 1 ))
				segment+="${input:index:1}"
			fi
			continue
		fi

		case "$char" in
			\'|\") quote="$char"; segment+="$char" ;;
			'$')
				if [[ "${input:index+1:1}" == '(' ]]; then
					gh_scan_substitution_end "$input" "$index"
					segment+="${input:index:GH_SUBSTITUTION_END - index + 1}"
					index=$GH_SUBSTITUTION_END
					continue
				fi
				segment+="$char"
				;;
			'`')
				gh_scan_substitution_end "$input" "$index"
				segment+="${input:index:GH_SUBSTITUTION_END - index + 1}"
				index=$GH_SUBSTITUTION_END
				continue
				;;
			'\')
				segment+="$char"
				index=$(( index + 1 ))
				segment+="${input:index:1}"
				;;
			';'|'&'|'|'|'('|')'|$'\n')
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

# 複合構文の予約語等を読み飛ばし、実行位置にあるコマンドのトークン番号を返す。
# `gh` そのものに加え、`$GH` や `$(which gh)` のようなシェル展開も候補として扱う。
# 静的にghか判定できないため、破壊操作の引数が続く場合は検査対象に含める(fail-close)。
gh_find_executable_gh_index() {
	local index prefix_index token command_token wrapper='' expect_value=0
	GH_COMMAND_INDEX=-1
	GH_COMMAND_PREFIX_UNCERTAIN=0
	for (( index = 0; index < ${#GH_SEGMENT_TOKENS[@]}; index++ )); do
		command_token="${GH_SEGMENT_TOKENS[index]}"
		gh_token_is_gh_command "$command_token" || continue
		expect_value=0
		wrapper=''
		for (( prefix_index = 0; prefix_index < index; prefix_index++ )); do
			token="${GH_SEGMENT_TOKENS[prefix_index]}"
			if (( expect_value )); then
				expect_value=0
				continue
			fi
			if [[ "$token" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
				continue
			fi
			if gh_token_is_known_wrapper "$token"; then
				wrapper="${token##*/}"
				continue
			fi
			case "$token" in
				if|then|elif|else|while|until|do|'{'|'('|!) ;;
				--)
					case "$wrapper" in
						time|command|builtin|env|exec) wrapper='' ;;
						*) break 2 ;;
					esac
					;;
				-p)
					[[ "$wrapper" == time || "$wrapper" == command ]] || break 2
					;;
				-v|-V)
					[[ "$wrapper" == command ]] || break 2
					;;
				-i|--ignore-environment)
					[[ "$wrapper" == env ]] || break 2
					;;
				-u|--unset|-C|--chdir|-S|--split-string)
					[[ "$wrapper" == env ]] || break 2
					expect_value=1
					;;
				-a)
					[[ "$wrapper" == exec ]] || break 2
					expect_value=1
					;;
				--unset=*|--chdir=*|--split-string=*)
					[[ "$wrapper" == env ]] || break 2
					;;
				--default-signal=*|--block-signal=*|--ignore-signal=*|--name=*)
					[[ "$wrapper" == env ]] || break 2
					;;
				--default-signal|--block-signal|--ignore-signal|--name)
					[[ "$wrapper" == env ]] || break 2
					expect_value=1
					;;
				-*)
					# 既知ラッパーの未知オプションは、実行位置を判定できないため安全側に倒す。
					if [[ -n "$wrapper" ]]; then
						GH_COMMAND_PREFIX_UNCERTAIN=1
						break
					fi
					break 2
					;;
				*) break 2 ;;
			esac
		done
		(( expect_value )) && continue
		GH_COMMAND_INDEX=$index
		return 0
	done
	return 1
}

# envの-S/--split-stringは文字列を再分割して実行するため、内部の実行位置を
# 静的に復元できない。呼び出し側で入力全体をfail-closeするために検出する。
gh_segment_has_unparsed_wrapper() {
	local segment="$1" index token next
	gh_load_segment_tokens "$segment"
	for (( index = 0; index + 1 < ${#GH_SEGMENT_TOKENS[@]}; index++ )); do
		token="${GH_SEGMENT_TOKENS[index]}"
		next="${GH_SEGMENT_TOKENS[index + 1]}"
		if gh_token_is_known_wrapper "$token" && [[ "${token##*/}" == "env" &&
			( "$next" == "-S" || "$next" == -S?* || "$next" == "--split-string" || "$next" == --split-string=* ) ]]; then
			return 0
		fi
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

gh_segment_is_issue_state_close() {
	local segment="$1" token previous='' has_closed=0
	gh_segment_is_action "$segment" "issue" "edit" || return 1
	(( GH_COMMAND_PREFIX_UNCERTAIN )) && return 0
	for token in "${GH_SEGMENT_TOKENS[@]}"; do
		if [[ "${token,,}" == "--state=closed" ||
			"$previous" == "--state" && "${token,,}" == "closed" ]]; then
			has_closed=1
		fi
		previous="$token"
	done
	(( has_closed ))
}
