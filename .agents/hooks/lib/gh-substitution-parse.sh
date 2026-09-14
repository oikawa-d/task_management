#!/usr/bin/env bash

# シェル文字列から、引用符内でも実行されるコマンド置換の本体を抽出する。

gh_extract_command_substitutions() {
	local input="$1" length=${#1}
	local index char quote='' substitution_quote='' depth=0 content=''
	GH_COMMAND_SUBSTITUTIONS=()

	for (( index = 0; index < length; index++ )); do
		char="${input:index:1}"
		if (( depth == 0 )); then
			if [[ "$quote" == "'" ]]; then
				[[ "$char" == "'" ]] && quote=''
				continue
			fi
			if [[ "$quote" == '"' ]]; then
				if [[ "$char" == '\' ]]; then
					(( index += 1 ))
				elif [[ "$char" == '"' ]]; then
					quote=''
				elif [[ "$char" == '$' && "${input:index + 1:1}" == '(' ]]; then
					depth=1
					content=''
					substitution_quote=''
					(( index += 1 ))
				fi
				continue
			fi
			case "$char" in
				\'|\") quote="$char" ;;
				'\') (( index += 1 )) ;;
				'$')
					if [[ "${input:index + 1:1}" == '(' ]]; then
						depth=1
						content=''
						substitution_quote=''
						(( index += 1 ))
					fi
					;;
			esac
			continue
		fi

		if [[ -n "$substitution_quote" ]]; then
			content+="$char"
			if [[ "$char" == "$substitution_quote" ]]; then
				substitution_quote=''
			elif [[ "$substitution_quote" == '"' && "$char" == '\' ]]; then
				(( index += 1 ))
				content+="${input:index:1}"
			elif [[ "$substitution_quote" == '"' && "$char" == '$' &&
				"${input:index + 1:1}" == '(' ]]; then
				(( depth += 1 ))
				(( index += 1 ))
				content+='('
			fi
			continue
		fi

		case "$char" in
			\'|\") substitution_quote="$char"; content+="$char" ;;
			'\')
				content+="$char"
				(( index += 1 ))
				content+="${input:index:1}"
				;;
			'$')
				content+="$char"
				if [[ "${input:index + 1:1}" == '(' ]]; then
					(( depth += 1 ))
					(( index += 1 ))
					content+='('
				fi
				;;
			'(') (( depth += 1 )); content+="$char" ;;
			')')
				depth=$(( depth - 1 ))
				if (( depth == 0 )); then
					GH_COMMAND_SUBSTITUTIONS+=("$content")
				else
					content+="$char"
				fi
				;;
			*) content+="$char" ;;
		esac
	done
}

gh_extract_backtick_substitutions() {
	local input="$1" length=${#1}
	local index char quote='' in_substitution=0 content=''
	GH_BACKTICK_SUBSTITUTIONS=()

	for (( index = 0; index < length; index++ )); do
		char="${input:index:1}"
		if (( in_substitution )); then
			if [[ "$char" == '\' ]]; then
				content+="$char"
				(( index += 1 ))
				content+="${input:index:1}"
			elif [[ "$char" == '`' ]]; then
				GH_BACKTICK_SUBSTITUTIONS+=("$content")
				in_substitution=0
				content=''
			else
				content+="$char"
			fi
			continue
		fi

		if [[ "$quote" == "'" ]]; then
			[[ "$char" == "'" ]] && quote=''
			continue
		fi
		if [[ "$char" == '\' ]]; then
			(( index += 1 ))
		elif [[ "$char" == "'" && -z "$quote" ]]; then
			quote="'"
		elif [[ "$char" == '"' ]]; then
			if [[ "$quote" == '"' ]]; then quote=''; else quote='"'; fi
		elif [[ "$char" == '`' ]]; then
			in_substitution=1
			content=''
		fi
	done
}
