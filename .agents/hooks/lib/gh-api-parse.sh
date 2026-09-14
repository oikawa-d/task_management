#!/usr/bin/env bash

# `gh api` 経由の破壊操作(PR merge / Issue close / GraphQL mutation)を解析する。
# gh-command-parse.sh のトークン解析を前提とするため、本ファイルより先にsourceすること。

# `gh api` のトークンを解析し、以下のグローバル変数へ結果を格納する。
#   GH_API_METHOD             : 大文字化したHTTPメソッド(未指定は空)
#   GH_API_HAS_DYNAMIC_METHOD : メソッドがシェル展開の場合1
#   GH_API_ENDPOINTS          : オプション値以外のトークン(=endpoint候補)
#   GH_API_FIELDS             : -f/-F等で渡されたフィールド指定
#   GH_API_IS_GRAPHQL         : endpointが graphql の場合1
# endpointを最初の非オプショントークン1件に限定すると、値付きオプションの追随漏れで
# 実endpointを取りこぼす(値がendpointとして確定してしまう)ため、候補は全件保持する。
gh_parse_api_segment() {
	local segment="$1" token option_value_kind='' index api_index=-1
	GH_API_METHOD=''
	GH_API_HAS_DYNAMIC_METHOD=0
	GH_API_ENDPOINTS=()
	GH_API_FIELDS=()
	GH_API_IS_GRAPHQL=0

	gh_load_segment_tokens "$segment"
	gh_find_executable_gh_index || return 1
	for (( index = GH_COMMAND_INDEX + 1; index < ${#GH_SEGMENT_TOKENS[@]}; index++ )); do
		if [[ "${GH_SEGMENT_TOKENS[index]}" == "api" ]]; then
			api_index=$index
			break
		fi
	done
	(( api_index >= 0 )) || return 1

	for (( index = api_index + 1; index < ${#GH_SEGMENT_TOKENS[@]}; index++ )); do
		token="${GH_SEGMENT_TOKENS[index]}"
		if [[ -n "$option_value_kind" ]]; then
			gh_api_record_value "$option_value_kind" "$token"
			option_value_kind=''
			continue
		fi

		case "$token" in
			-X|--method) option_value_kind='method'; continue ;;
			-f|-F|--raw-field|--field) option_value_kind='field'; continue ;;
			-H|-q|-t|-p|--header|--jq|--template|--input|--hostname|--cache|--preview)
				option_value_kind='other'
				continue
				;;
			-X?*) gh_api_record_value 'method' "$(gh_api_attached_value "$token" 2)"; continue ;;
			--method=*) gh_api_record_value 'method' "${token#--method=}"; continue ;;
			-f?*|-F?*) gh_api_record_value 'field' "$(gh_api_attached_value "$token" 2)"; continue ;;
			--raw-field=*) gh_api_record_value 'field' "${token#--raw-field=}"; continue ;;
			--field=*) gh_api_record_value 'field' "${token#--field=}"; continue ;;
			--) continue ;;
			-*) continue ;;
		esac

		[[ "$token" == "graphql" ]] && GH_API_IS_GRAPHQL=1
		GH_API_ENDPOINTS+=("$token")
	done
	return 0
}

# `-XPUT` / `-X=PUT` のように値を連結した短縮オプションから値部分を取り出す。
gh_api_attached_value() {
	local token="$1" prefix_length="$2" value
	value="${token:prefix_length}"
	printf '%s' "${value#=}"
}

gh_api_record_value() {
	local kind="$1" value="$2"
	case "$kind" in
		method)
			if gh_api_is_dynamic "$value"; then
				GH_API_HAS_DYNAMIC_METHOD=1
			else
				GH_API_METHOD="${value^^}"
			fi
			;;
		field) GH_API_FIELDS+=("$value") ;;
	esac
}

gh_api_is_dynamic() {
	[[ "$1" == *'$'* || "$1" == *'`'* ]]
}

# endpoint候補のいずれかが正規表現に一致するか、シェル展開で判定不能かを返す。
# 0=一致 / 1=不一致 / 2=判定不能(シェル展開を含む)
gh_api_match_endpoint() {
	local pattern="$1" endpoint has_dynamic=0
	for endpoint in "${GH_API_ENDPOINTS[@]}"; do
		if [[ "$endpoint" =~ $pattern ]]; then
			return 0
		fi
		gh_api_is_dynamic "$endpoint" && has_dynamic=1
	done
	(( has_dynamic )) && return 2
	return 1
}

gh_segment_is_api_merge() {
	local match_status=0
	gh_parse_api_segment "$1" || return 1
	gh_api_match_endpoint '^/?repos/[^/]+/[^/]+/pulls/[0-9]+/merge(\?.*)?$' || match_status=$?
	case "$match_status" in
		# endpointが確定している場合、メソッドがPUTか判定不能なら破壊操作とみなす。
		0) [[ "$GH_API_METHOD" == "PUT" ]] || (( GH_API_HAS_DYNAMIC_METHOD )) ;;
		# endpointがシェル展開の場合、明示的なPUT指定のときだけ対象とする。
		2) [[ "$GH_API_METHOD" == "PUT" ]] ;;
		*) return 1 ;;
	esac
}

# REST API経由のIssue close(`PATCH repos/<owner>/<repo>/issues/<番号>` + state=closed)。
gh_segment_is_api_issue_close() {
	local field match_status=0 has_state_closed=0
	gh_parse_api_segment "$1" || return 1
	for field in "${GH_API_FIELDS[@]}"; do
		if [[ "${field,,}" == "state=closed" ]] || \
			{ [[ "$field" == state=* ]] && gh_api_is_dynamic "$field"; }; then
			has_state_closed=1
		fi
	done
	(( has_state_closed )) || return 1
	[[ "$GH_API_METHOD" == "PATCH" || "$GH_API_METHOD" == "POST" ]] || (( GH_API_HAS_DYNAMIC_METHOD )) || return 1
	gh_api_match_endpoint '^/?repos/[^/]+/[^/]+/issues/[0-9]+(\?.*)?$' || match_status=$?
	# 0=一致 / 2=endpointがシェル展開(判定不能)はいずれも安全側でブロックする。
	[[ "$match_status" == "0" || "$match_status" == "2" ]]
}

# GraphQL mutation経由のPR merge / Issue close。
# クエリは -f query='...' 等で渡されるため、セグメント全体から mutation 名を検出する。
gh_segment_is_api_graphql_destructive() {
	local segment="$1" lowered
	gh_parse_api_segment "$segment" || return 1
	(( GH_API_IS_GRAPHQL )) || return 1
	lowered="${segment,,}"
	[[ "$lowered" == *mergepullrequest* || "$lowered" == *closeissue* ]]
}
