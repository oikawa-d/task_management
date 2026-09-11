# シェルのクォートを考慮してコマンド断片をトークン化する。
# evalはコマンド置換等を実行するため使用せず、hookの入力を安全に解析する。
tokenize_command_segment() {
	local segment="$1"
	local token="" quote="" escaped=0 token_started=0 char i

	TOKENS=()
	for ((i = 0; i < ${#segment}; i++)); do
		char="${segment:i:1}"
		if ((escaped)); then
			token+="$char"
			escaped=0
			token_started=1
			continue
		fi
		if [[ "$quote" == "'" ]]; then
			if [[ "$char" == "'" ]]; then
				quote=""
			else
				token+="$char"
			fi
			token_started=1
			continue
		fi
		if [[ "$quote" == '"' ]]; then
			if [[ "$char" == '"' ]]; then
				quote=""
			elif [[ "$char" == "\\" ]]; then
				escaped=1
			else
				token+="$char"
			fi
			token_started=1
			continue
		fi
		case "$char" in
			"'") quote="'"; token_started=1 ;;
			'"') quote='"'; token_started=1 ;;
			\\) escaped=1; token_started=1 ;;
			' '|$'\t')
				if ((token_started)); then
					TOKENS+=("$token")
					token=""
					token_started=0
				fi
				;;
			*) token+="$char"; token_started=1 ;;
		esac
	done

	if [[ -n "$quote" ]] || ((escaped)); then
		return 2
	fi
	if ((token_started)); then
		TOKENS+=("$token")
	fi
}

# `gh issue close` の実引数からIssue番号とリポジトリを抽出する。
# クォート内の文字列やオプション値を位置引数として扱わない。
# URL形式はGitHub.comのIssue URLに限定し、対象リポジトリもURLから取得する。
parse_issue_close_command() {
	local segment="$1"
	local gh_index=-1 close_index=-1 issue_number="" explicit_repo="" url_repo=""
	local arg i j positional_count=0 after_options=0

	if ! tokenize_command_segment "$segment"; then
		return 2
	fi

	for ((i = 0; i < ${#TOKENS[@]} - 2; i++)); do
		if [[ "${TOKENS[i]}" != "gh" ]]; then
			continue
		fi
		for ((j = i + 1; j < ${#TOKENS[@]} - 1; j++)); do
			if [[ "${TOKENS[j]}" == "issue" && "${TOKENS[j + 1]}" == "close" ]]; then
				gh_index=$i
				close_index=$((j + 1))
				break 2
			fi
		done
	done
	if ((gh_index < 0)); then
		return 2
	fi

	# `gh --repo owner/repo issue close` のグローバルrepo指定を読む。
	for ((i = gh_index + 1; i < close_index; i++)); do
		arg="${TOKENS[i]}"
		case "$arg" in
			--repo|-R)
				((i + 1 < close_index)) || return 2
				explicit_repo="${TOKENS[i + 1]}"
				i=$((i + 1))
				;;
			--repo=*|-R=*) explicit_repo="${arg#*=}" ;;
			-R?*) explicit_repo="${arg#-R}" ;;
		esac
	done

	for ((i = close_index + 1; i < ${#TOKENS[@]}; i++)); do
		arg="${TOKENS[i]}"
		if ((after_options == 1)); then
			:
		elif [[ "$arg" == "--" ]]; then
			after_options=1
			continue
		else
			case "$arg" in
				--repo|-R|--comment|-c|--reason|-r)
					((i + 1 < ${#TOKENS[@]})) || return 2
					if [[ "$arg" == "--repo" || "$arg" == "-R" ]]; then
						explicit_repo="${TOKENS[i + 1]}"
					fi
					i=$((i + 1))
					continue
					;;
				--repo=*|-R=*) explicit_repo="${arg#*=}"; continue ;;
				-R?*) explicit_repo="${arg#-R}"; continue ;;
				--comment=*|-c=*|--reason=*|-r=*) continue ;;
				--*) return 2 ;;
				-*) return 2 ;;
			esac
		fi

		positional_count=$((positional_count + 1))
		((positional_count == 1)) || return 2
		if [[ "$arg" =~ ^https://([^/]+)/([^/]+)/([^/]+)/issues/([0-9]+)/?$ ]]; then
			[[ "${BASH_REMATCH[1]}" == "github.com" ]] || return 2
			issue_number="${BASH_REMATCH[4]}"
			url_repo="${BASH_REMATCH[2]}/${BASH_REMATCH[3]}"
		elif [[ "$arg" =~ ^[0-9]+$ ]]; then
			issue_number="$arg"
		else
			return 2
		fi
	done

	[[ -n "$issue_number" ]] || return 2
	if [[ -n "$explicit_repo" && ! "$explicit_repo" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]]; then
		return 2
	fi
	if [[ -n "$explicit_repo" && -n "$url_repo" && "$explicit_repo" != "$url_repo" ]]; then
		return 2
	fi
	PARSED_ISSUE_NUMBER="$issue_number"
	PARSED_REPO="${explicit_repo:-$url_repo}"
}
