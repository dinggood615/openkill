#!/bin/sh
# OpenKill production-capable renderer candidate.
#
# This file is intentionally unwired.  It transforms the versioned,
# line-oriented semantic input into a deterministic nft batch.  It never
# discovers state, invokes a firewall/network command, or mutates a dataplane.

SHELL_RENDERER_INPUT_VERSION=1
SHELL_NFT_RENDERER_VERSION=1
OKR_INPUT_VERSION=$SHELL_RENDERER_INPUT_VERSION
OKR_RENDERER_VERSION=$SHELL_NFT_RENDERER_VERSION
OKR_SEMANTIC_VERSION=1
OKR_CLASSIFIER_VERSION=1
OKR_IR_VERSION=1
OKR_MANIFEST_VERSION=1
OKR_MARK=0x162
OKR_MASK=0xffffffff
OKR_ROUTE_TABLE=354
OKR_RULE_PREF=1888
OKR_TAB=$(printf '\t')

okr_die()
{
	okr_error_code=$1
	shift
	printf 'openkill_nft_renderer: %s\n' "$*" >&2
	exit "$okr_error_code"
}

okr_valid_identifier()
{
	okr_identifier=$1
	[ -n "$okr_identifier" ] && [ "${#okr_identifier}" -le 128 ] || return 1
	case "$okr_identifier" in [A-Za-z_]* ) ;; *) return 1 ;; esac
	case "$okr_identifier" in *[!A-Za-z0-9_]* ) return 1 ;; esac
	return 0
}

okr_valid_number()
{
	okr_number=$1
	case "$okr_number" in
		''|*[!0-9]*) return 1 ;;
	esac
	[ "$okr_number" -ge 1 ] 2>/dev/null && [ "$okr_number" -le 65535 ] 2>/dev/null
}

okr_valid_order()
{
	okr_order=$1
	case "$okr_order" in
		''|*[!0-9]*) return 1 ;;
	esac
	return 0
}

okr_meta()
{
	awk -v FS="$OKR_TAB" -v key="$1" '$1 == "META" && $2 == key { print $3; found=1; exit } END { if (!found) exit 1 }' "$OKR_INPUT"
}

okr_valid_ipv4()
{
	printf '%s\n' "$1" | awk '
	function valid_prefix(p) { return p ~ /^[0-9]+$/ && p >= 0 && p <= 32 }
	function valid_v4(s, n, a, i) {
		n=split(s,a,".")
		if (n != 4) return 0
		for (i=1; i<=4; i++) if (a[i] !~ /^[0-9]+$/ || a[i] > 255) return 0
		return 1
	}
	BEGIN { bad=0 }
	{
		n=split($0,p,"/")
		if (n > 2 || !valid_v4(p[1])) bad=1
		if (n == 2 && !valid_prefix(p[2])) bad=1
	}
	END { exit bad ? 1 : 0 }
	'
}

okr_valid_ipv6()
{
	printf '%s\n' "$1" | awk '
	function valid_hextets(s, n, a, i) {
		if (s == "") return 0
		n=split(s,a,":")
		for (i=1; i<=n; i++) if (a[i] !~ /^[0-9A-Fa-f]{1,4}$/) return 0
		return n
	}
	function valid_v6(s, n, a, left, right, l, r) {
		if (s !~ /:/ || s ~ /[^0-9A-Fa-f:]/) return 0
		n=split(s,a,"::")
		if (n > 2) return 0
		if (n == 2) {
			l=valid_hextets(a[1]); r=valid_hextets(a[2])
			if (l == 0 && a[1] != "") return 0
			if (r == 0 && a[2] != "") return 0
			return (l + r < 8)
		}
		return valid_hextets(s) == 8
	}
	BEGIN { bad=0 }
	{
		n=split($0,p,"/")
		if (n > 2 || !valid_v6(p[1])) bad=1
		if (n == 2 && (p[2] !~ /^[0-9]+$/ || p[2] > 128)) bad=1
	}
	END { exit bad ? 1 : 0 }
	'
}

okr_valid_mac()
{
	printf '%s\n' "$1" | awk '
	BEGIN { bad=1 }
	{ if ($0 ~ /^[0-9A-Fa-f][0-9A-Fa-f](:[0-9A-Fa-f][0-9A-Fa-f]){5}$/) bad=0 }
	END { exit bad }
	'
}

okr_valid_element()
{
	okr_element=$1
	okr_element_type=$2
	okr_family=$3
	case "$okr_element_type" in
		ADDRESS)
			case "$okr_family" in
				IPv4) okr_valid_ipv4 "$okr_element" ;;
				IPv6) okr_valid_ipv6 "$okr_element" ;;
				*) return 1 ;;
			esac
				;;
		PREFIX)
			case "$okr_element" in */*) ;; *) return 1 ;; esac
			case "$okr_family" in
				IPv4) okr_valid_ipv4 "$okr_element" ;;
				IPv6) okr_valid_ipv6 "$okr_element" ;;
				*) return 1 ;;
			esac
				;;
		PORT) okr_valid_number "$okr_element" ;;
		MAC) okr_valid_mac "$okr_element" ;;
		INTERVAL)
			case "$okr_family" in IPv4|IPv6) ;; *) return 1 ;; esac
			okr_interval_left=${okr_element%%-*}
			okr_interval_right=${okr_element#*-}
			[ "$okr_interval_left" != "$okr_element" ] || return 1
			okr_valid_element "$okr_interval_left" ADDRESS "$okr_family" || return 1
			okr_valid_element "$okr_interval_right" ADDRESS "$okr_family" || return 1
			;;
		TOKEN)
			[ -n "$okr_element" ] || return 1
			case "$okr_element" in *[!A-Za-z0-9_.:-]*) return 1 ;; esac
			;;
		*) return 1 ;;
	esac
	return 0
}

okr_validate_csv()
{
	okr_csv_value=$1
	okr_csv_type=$2
	okr_csv_family=$3
	[ -z "$okr_csv_value" ] || [ "$okr_csv_value" = - ] && return 0
	okr_items=$(printf '%s\n' "$okr_csv_value" | awk -F',' '{ for (i=1; i<=NF; i++) { gsub(/^ +| +$/, "", $i); if ($i == "") exit 1; print $i } }') || return 1
	okr_csv_status=0
	printf '%s\n' "$okr_items" | while IFS= read -r okr_item; do
		okr_valid_element "$okr_item" "$okr_csv_type" "$okr_csv_family" || exit 1
	done || okr_csv_status=$?
	return "$okr_csv_status"
}

okr_valid_expression()
{
	okr_expression=$1
	[ -n "$okr_expression" ] || return 1
	case "$okr_expression" in
		*"$OKR_TAB"*|*";"*|*"'"*|*'`'*|*'$('*|*'\\'* ) return 1 ;;
	esac
	# Match expressions are already lowered by the upstream semantic model.
	# The only quoted token in the CURRENT corpus is the fixed TUN interface;
	# reject every other quote so an input field cannot escape the nft rule.
	case "$okr_expression" in
		*'"'*)
			case "$okr_expression" in
				*'iifname "utun"'*) ;;
				*) return 1 ;;
			esac
			;;
	esac
	return 0
}

okr_validate_action()
{
	okr_action_type=$1
	okr_action_expr=$2
	okr_action_family=$3
	okr_action_match=$4
	okr_tproxy_port=$5
	okr_redirect_port=$6
	case "$okr_action_type" in
		RETURN_NATIVE) [ "$okr_action_expr" = return ] || return 1 ;;
		MARK_PROXY) [ "$okr_action_expr" = "meta mark set $OKR_MARK" ] || return 1 ;;
		TPROXY_PROXY)
			case "$okr_action_family" in
				IPv4) okr_action_prefix=ip ;;
				IPv6) okr_action_prefix=ip6 ;;
				*) return 1 ;;
			esac
			[ "$okr_action_expr" = "tproxy $okr_action_prefix to :$okr_tproxy_port meta mark set $OKR_MARK" ] || return 1
			case "$okr_action_match" in *"meta l4proto tcp"*|*"meta l4proto udp"*) ;; *) return 1 ;; esac
			;;
		REDIRECT_PROXY)
			[ "$okr_action_expr" = "redirect to :$okr_redirect_port" ] || return 1
			case "$okr_action_match" in *"meta l4proto tcp"*) ;; *) return 1 ;; esac
			;;
		DNS_REDIRECT|JUMP)
			case "$okr_action_expr" in jump\ *) okr_target=${okr_action_expr#jump }; okr_valid_identifier "$okr_target" || return 1 ;; *) return 1 ;; esac
			;;
		ACCEPT_IF_REQUIRED) [ "$okr_action_expr" = accept ] || return 1 ;;
		CONTINUE_POLICY|ACTION_FROM_CLASSIFICATION) [ "$okr_action_expr" = counter ] || return 1 ;;
		NOT_OWNED|UNRESOLVED_SEMANTIC) [ "$okr_action_expr" = - ] || return 1 ;;
		ACCESS_DENY_REQUIRED|UNSUPPORTED_ACTION) return 1 ;;
		*) return 1 ;;
	esac
	return 0
}

okr_input_has_nul_byte()
{
	# Do not put input bytes in a shell variable.  `od` emits only printable
	# hex tokens, and the small awk filter below therefore remains safe on
	# BusyBox ash as well as host awk.  The marker makes an od failure
	# distinguishable from a clean file without relying on pipefail.
	okr_nul_input=$1
	{
		od -An -v -tx1 "$okr_nul_input" 2>/dev/null || printf '%s\n' OPENKILL_OD_ERROR
	} | awk '
		$0 == "OPENKILL_OD_ERROR" { failed=1; next }
		{ for (i=1; i<=NF; i++) if ($i == "00") found=1 }
		END {
			if (failed) exit 2
			if (found) exit 0
			exit 1
		}
	'
}

okr_validate_input()
{
	OKR_INPUT=$1
	[ -r "$OKR_INPUT" ] || okr_die 64 'input is not readable'
	okr_input_has_nul_byte "$OKR_INPUT"
	okr_nul_status=$?
	case "$okr_nul_status" in
		0) okr_die 64 'malformed input record' ;;
		1) ;;
		*) okr_die 64 'cannot scan input bytes' ;;
	esac
	okr_header=$(sed -n '1p' "$OKR_INPUT") || okr_die 64 'cannot read input header'
	[ "$okr_header" = "SHELL_RENDERER_INPUT_V1${OKR_TAB}1" ] || okr_die 66 'input version mismatch'

	# Read all metadata with one BusyBox awk pass.  Keeping the values in
	# shell variables avoids one process per field on small OpenWrt devices.
	okr_metadata=$(awk -v FS="$OKR_TAB" '$1 == "META" { print $2 "=" $3 }' "$OKR_INPUT") || okr_die 64 'cannot read metadata'
	while IFS='=' read -r okr_meta_key okr_meta_value; do
		case "$okr_meta_key" in
			profile) okr_profile=$okr_meta_value ;;
			owner) okr_owner=$okr_meta_value ;;
			backend) okr_backend=$okr_meta_value ;;
			run_mode) okr_run_mode=$okr_meta_value ;;
			semantic_spec_version) okr_semantic_meta=$okr_meta_value ;;
			classifier_contract_version) okr_classifier_meta=$okr_meta_value ;;
			nft_ir_version) okr_ir_meta=$okr_meta_value ;;
			ownership_manifest_version) okr_manifest_meta=$okr_meta_value ;;
			redirect_port) okr_redirect_meta=$okr_meta_value ;;
			tproxy_port) okr_tproxy_meta=$okr_meta_value ;;
			dns_port) okr_dns_meta=$okr_meta_value ;;
			mark) okr_mark=$okr_meta_value ;;
			mask) okr_mask=$okr_meta_value ;;
			route_table) okr_route_table=$okr_meta_value ;;
			rule_pref) okr_rule_pref=$okr_meta_value ;;
			router_self_proxy) okr_router_self=$okr_meta_value ;;
			component_state) okr_component_state=$okr_meta_value ;;
		esac
	done <<EOF
$okr_metadata
EOF
	[ -n "$okr_profile" ] || okr_die 66 'profile is missing'
	[ "$okr_profile" = current ] || okr_die 66 'only current profile is accepted'
	[ -n "$okr_owner" ] || okr_die 64 'owner is missing'
	case "$okr_owner" in OPENKILL|MIHOMO|DISABLED) ;; *) okr_die 64 'unknown owner' ;; esac
	[ -n "$okr_backend" ] || okr_die 64 'backend is missing'
	[ "$okr_backend" = modern_fw4_nft ] || okr_die 66 'unsupported backend'
	[ -n "$okr_run_mode" ] || okr_die 64 'run mode is missing'
	case "$okr_run_mode" in TUN|TPROXY|REDIRECT) ;; *) okr_die 64 'unknown run mode' ;; esac

	[ "$okr_semantic_meta" = 1 ] || okr_die 66 'semantic_spec_version mismatch'
	[ "$okr_classifier_meta" = 1 ] || okr_die 66 'classifier_contract_version mismatch'
	[ "$okr_ir_meta" = 1 ] || okr_die 66 'nft_ir_version mismatch'
	[ "$okr_manifest_meta" = 1 ] || okr_die 66 'ownership_manifest_version mismatch'
	for okr_port_key in redirect_port tproxy_port dns_port; do
		case "$okr_port_key" in
			redirect_port) okr_port=$okr_redirect_meta ;;
			tproxy_port) okr_port=$okr_tproxy_meta ;;
			dns_port) okr_port=$okr_dns_meta ;;
		esac
		[ -n "$okr_port" ] || okr_die 64 "$okr_port_key is missing"
		okr_valid_number "$okr_port" || okr_die 64 "invalid $okr_port_key"
	done
	[ -n "$okr_mark" ] || okr_die 66 'mark ABI is missing'
	[ -n "$okr_mask" ] || okr_die 66 'mark mask is missing'
	[ -n "$okr_route_table" ] || okr_die 66 'route table is missing'
	[ -n "$okr_rule_pref" ] || okr_die 66 'rule preference is missing'
	[ "$okr_mark" = "$OKR_MARK" ] && [ "$okr_mask" = "$OKR_MASK" ] && [ "$okr_route_table" = "$OKR_ROUTE_TABLE" ] && [ "$okr_rule_pref" = "$OKR_RULE_PREF" ] || okr_die 66 'mark ABI mismatch'
	[ -n "$okr_router_self" ] || okr_die 64 'router_self_proxy is missing'
	case "$okr_router_self" in 0|1) ;; *) okr_die 64 'invalid router_self_proxy' ;; esac
	[ -n "$okr_component_state" ] || okr_die 64 'component_state is missing'
	[ "$okr_component_state" = READY ] || okr_die 65 'unsupported current state'

	# Structural validation is deliberately performed before any output.  The
	# input is line-oriented so this remains available to BusyBox awk.
	awk -v FS="$OKR_TAB" '
		BEGIN {
			bad=0
			allowed_meta["profile"]=1; allowed_meta["owner"]=1; allowed_meta["backend"]=1; allowed_meta["run_mode"]=1
			allowed_meta["semantic_spec_version"]=1; allowed_meta["classifier_contract_version"]=1; allowed_meta["nft_ir_version"]=1; allowed_meta["ownership_manifest_version"]=1
			allowed_meta["redirect_port"]=1; allowed_meta["tproxy_port"]=1; allowed_meta["dns_port"]=1
			allowed_meta["mark"]=1; allowed_meta["mask"]=1; allowed_meta["route_table"]=1; allowed_meta["rule_pref"]=1
			allowed_meta["router_self_proxy"]=1; allowed_meta["component_state"]=1
		}
		NR == 1 { next }
		{
			if ($0 ~ /\r/ || index($0, "|") > 0) bad=1
			if ($1 == "META") { if (NF != 3 || !allowed_meta[$2] || seen_meta[$2]++) bad=1; next }
			if ($1 == "CHAIN" && NF != 10) bad=1
			else if ($1 == "SET" && NF != 8) bad=1
			else if ($1 == "ATTACH" && NF != 9) bad=1
			else if ($1 == "RULE" && NF != 12) bad=1
			else if ($1 == "UNSUPPORTED" && NF < 3) bad=1
			else if ($1 != "CHAIN" && $1 != "SET" && $1 != "ATTACH" && $1 != "RULE" && $1 != "UNSUPPORTED" && $1 != "META" && $1 != "") bad=1
			if ($1 == "CHAIN" || $1 == "SET" || $1 == "ATTACH" || $1 == "RULE") {
				if (seen_id[$2]++) bad=1
				if ($1 == "CHAIN" || $1 == "SET") if (seen_physical[$3]++) bad=1
			}
		}
		END { exit bad ? 1 : 0 }
	' "$OKR_INPUT" || okr_die 64 'malformed input record'

	okr_unsupported=0
	while IFS="$OKR_TAB" read -r okr_kind okr_a okr_b okr_c okr_d okr_e okr_f okr_g okr_h okr_i okr_j okr_k; do
		case "$okr_kind" in
			''|META) continue ;;
			UNSUPPORTED) okr_unsupported=1; continue ;;
			CHAIN)
				okr_valid_identifier "$okr_a" || okr_die 64 'invalid chain logical id'
				okr_valid_identifier "$okr_b" || okr_die 64 'invalid chain physical name'
				case "$okr_c" in IPv4|IPv6|ALL) ;; *) okr_die 64 'invalid chain family' ;; esac
				case "$okr_d" in TOPOLOGY|LOCAL|NODE|CHINA|ACCESS|SERVICE|DNS|PROXY_ACTION|WAN_INPUT|UPNP|OWNER) ;; *) okr_die 64 'invalid chain component' ;; esac
				case "$okr_e" in PREROUTING_PROXY|PREROUTING_MANGLE|OUTPUT_PROXY|OUTPUT_MANGLE|POSTROUTING|DNS_LAN|DNS_ROUTER|WAN_INPUT|UPNP|TOPOLOGY) ;; *) okr_die 64 'invalid chain role' ;; esac
				case "$okr_f" in 0|1) ;; *) okr_die 64 'invalid base-chain marker' ;; esac
				case "$okr_g" in -|nat) ;; *) okr_die 64 'invalid chain type' ;; esac
				case "$okr_h" in -|OUTPUT) ;; *) okr_die 64 'invalid chain hook' ;; esac
				case "$okr_i" in -|-1) ;; *) okr_die 64 'invalid chain priority' ;; esac
				;;
			SET)
				okr_valid_identifier "$okr_a" || okr_die 64 'invalid set logical id'
				okr_valid_identifier "$okr_b" || okr_die 64 'invalid set physical name'
				case "$okr_c" in IPv4|IPv6|ALL) ;; *) okr_die 64 'invalid set family' ;; esac
				case "$okr_d" in ADDRESS|PREFIX|PORT|MAC|INTERVAL|TOKEN) ;; *) okr_die 64 'invalid set element type' ;; esac
				case "$okr_c:$okr_d" in
					IPv4:ADDRESS|IPv4:PREFIX|IPv6:ADDRESS|IPv6:PREFIX|ALL:PORT|ALL:MAC|IPv4:INTERVAL|IPv6:INTERVAL|ALL:TOKEN) ;;
					*) okr_die 64 'set family and element type mismatch' ;;
				 esac
				case "$okr_g" in TOPOLOGY|LOCAL|NODE|CHINA|ACCESS|SERVICE|DNS|PROXY_ACTION|WAN_INPUT|UPNP|OWNER) ;; *) okr_die 64 'invalid set component' ;; esac
				case "$okr_e" in -|interval) ;; *) okr_die 64 'invalid set flags' ;; esac
				okr_validate_csv "$okr_f" "$okr_d" "$okr_c" || okr_die 64 'invalid set element'
				;;
			ATTACH)
				okr_valid_identifier "$okr_a" || okr_die 64 'invalid attachment id'
				case "$okr_b" in TOPOLOGY|LOCAL|NODE|CHINA|ACCESS|SERVICE|DNS|PROXY_ACTION|WAN_INPUT|UPNP|OWNER) ;; *) okr_die 64 'invalid attachment component' ;; esac
				case "$okr_c" in IPv4|IPv6|ALL) ;; *) okr_die 64 'invalid attachment family' ;; esac
				okr_valid_identifier "$okr_d" || okr_die 64 'invalid attachment source'
				okr_valid_expression "$okr_e" || okr_die 64 'invalid attachment match'
				[ "$okr_f" = JUMP ] || okr_die 64 'invalid attachment action type'
				okr_valid_expression "$okr_g" || okr_die 64 'invalid attachment action'
				[ "$okr_g" = "jump $okr_h" ] || okr_die 64 'attachment target does not match action'
				okr_valid_identifier "$okr_h" || okr_die 64 'invalid attachment target'
				;;
			RULE)
				okr_valid_identifier "$okr_a" || okr_die 64 'invalid rule id'
				case "$okr_b" in TOPOLOGY|LOCAL|NODE|CHINA|ACCESS|SERVICE|DNS|PROXY_ACTION|WAN_INPUT|UPNP|OWNER) ;; *) okr_die 64 'invalid rule component' ;; esac
				case "$okr_c" in IPv4|IPv6) ;; *) okr_die 64 'invalid rule family' ;; esac
				okr_valid_identifier "$okr_d" || okr_die 64 'invalid rule chain'
				okr_valid_order "$okr_e" || okr_die 64 'invalid rule order'
				okr_valid_expression "$okr_f" || okr_die 64 'invalid rule match'
				case "$okr_g" in RETURN_NATIVE|MARK_PROXY|TPROXY_PROXY|REDIRECT_PROXY|DNS_REDIRECT|ACCESS_DENY_REQUIRED|JUMP|ACCEPT_IF_REQUIRED|NOT_OWNED|UNSUPPORTED_ACTION|CONTINUE_POLICY|UNRESOLVED_SEMANTIC|ACTION_FROM_CLASSIFICATION) ;; *) okr_die 64 'unknown rule action' ;; esac
				if [ "$okr_h" != - ]; then okr_valid_expression "$okr_h" || okr_die 64 'invalid rule action expression'; fi
				okr_validate_action "$okr_g" "$okr_h" "$okr_c" "$okr_f" "$okr_tproxy_meta" "$okr_redirect_meta" || okr_die 65 'action does not match current execution contract'
				case "$okr_i" in -|DNS|NODE_ENDPOINT|LOCAL_DESTINATION|SELF_TRAFFIC|TUN_INGRESS|REPLY_TRAFFIC|SERVICE_PORT|CONTROL_PROTOCOL|FAKEIP|CHINA_PASS|CHINA_POLICY|ACCESS_CONTROL|DEFAULT_POLICY|EXPLICIT_DIRECT|EXPLICIT_PROXY) ;; *) okr_die 64 'invalid rule reason' ;; esac
				case "$okr_j" in -|BYPASS|PROXY|DNS_SPECIAL|DIRECT|ACCESS_DENY|NOT_OWNED) ;; *) okr_die 64 'invalid rule decision' ;; esac
				case "$okr_k" in -|BC-01|BC-04|BC-06|BC-07) ;; *) okr_die 64 'invalid current gap' ;; esac
				case "$okr_g:$okr_i:$okr_k" in
					UNRESOLVED_SEMANTIC:*|*:EXPLICIT_DIRECT:BC-01|*:EXPLICIT_PROXY:BC-01) okr_unsupported=1 ;;
				esac
				;;
		esac
	done < "$OKR_INPUT"
	[ "$okr_unsupported" -eq 0 ] || okr_die 65 'unsupported current state'
	return 0
}

okr_nft_type()
{
	case "$1:$2" in
		IPv4:ADDRESS|IPv4:PREFIX|IPv4:INTERVAL) printf 'ipv4_addr' ;;
		IPv6:ADDRESS|IPv6:PREFIX|IPv6:INTERVAL) printf 'ipv6_addr' ;;
		ALL:PORT) printf 'inet_service' ;;
		ALL:MAC) printf 'ether_addr' ;;
		ALL:TOKEN) printf 'integer' ;;
		*) return 1 ;;
	esac
}

okr_normalize_csv()
{
	okr_csv=$1
	okr_csv_type=$2
	[ -n "$okr_csv" ] && [ "$okr_csv" != - ] || return 0
	okr_sort_flags='-u'
	[ "$okr_csv_type" = PORT ] && okr_sort_flags='-n -u'
	printf '%s\n' "$okr_csv" | awk -F',' '{ for (i=1; i<=NF; i++) { gsub(/^ +| +$/, "", $i); if ($i != "") print $i } }' | LC_ALL=C sort $okr_sort_flags | awk 'BEGIN { first=1 } { if (!first) printf ", "; printf "%s", $0; first=0 } END { if (!first) printf "\n" }'
}

okr_trace_comment()
{
	okr_trace_id=$1
	okr_trace_component=$2
	okr_trace_reason=$3
	okr_trace_decision=$4
	if [ "$okr_trace_reason" = - ] || [ "$okr_trace_decision" = - ]; then
		okr_trace_full="OpenKill logical_id=$okr_trace_id component=$okr_trace_component owner=OPENKILL"
		okr_trace_compact="OpenKill id=$okr_trace_id c=$okr_trace_component o=OPENKILL"
	else
		okr_trace_full="OpenKill logical_id=$okr_trace_id component=$okr_trace_component reason=$okr_trace_reason decision=$okr_trace_decision owner=OPENKILL"
		okr_trace_compact="OpenKill logical_id=$okr_trace_id component=$okr_trace_component r=$okr_trace_reason d=$okr_trace_decision o=OPENKILL"
	fi
	okr_trace_size=${#okr_trace_full}
	if [ "$okr_trace_size" -le 128 ]; then
		printf '%s' "$okr_trace_full"
		return 0
	fi
	okr_trace_size=${#okr_trace_compact}
	if [ "$okr_trace_size" -le 128 ]; then
		printf '%s' "$okr_trace_compact"
		return 0
	fi
	printf 'OpenKill id=%s c=%s o=OPENKILL' "$okr_trace_id" "$okr_trace_component"
}

okr_render()
{
	okr_validate_input "$1" || return $?
	OKR_INPUT=$1
	printf '# OPENKILL_SHELL_NFT_RENDERER_V1 renderer_version=%s profile=%s backend=%s\n' "$OKR_RENDERER_VERSION" "$okr_profile" "$okr_backend"
	printf '# semantic_spec_version=%s classifier_contract_version=%s ir_version=%s manifest_version=%s\n' "$OKR_SEMANTIC_VERSION" "$OKR_CLASSIFIER_VERSION" "$OKR_IR_VERSION" "$OKR_MANIFEST_VERSION"
	printf '# table inet fw4 is an external FW4 reference; no parent table mutation is emitted\n'
	if [ "$okr_owner" != OPENKILL ]; then
		printf '# owner=%s; no OpenKill-owned desired objects\n' "$okr_owner"
		return 0
	fi

	# Prefix each record with a stable section/order key.  The original record
	# order is deliberately ignored; semantic rule order remains the numeric
	# order supplied by the upstream classifier.
	okr_sorted=$(awk -v FS="$OKR_TAB" '
		NR == 1 { next }
		$1 == "CHAIN" { printf "01|%s|%s\t%s\n", $3, $2, $0; next }
		$1 == "SET" { printf "02|%s|%s\t%s\n", $3, $2, $0; next }
		$1 == "ATTACH" { printf "03|%s|%s\t%s\n", $5, $2, $0; next }
		$1 == "RULE" { printf "04|%s|%010d|%s\t%s\n", $5, $6, $2, $0; next }
	' "$OKR_INPUT" | LC_ALL=C sort | awk -v FS="$OKR_TAB" '{ sub(/^[^\t]*\t/, ""); print }')

	okr_render_status=0
	printf '%s\n' "$okr_sorted" | while IFS="$OKR_TAB" read -r okr_kind okr_a okr_b okr_c okr_d okr_e okr_f okr_g okr_h okr_i okr_j okr_k; do
		case "$okr_kind" in
			CHAIN)
				if [ "$okr_g" = nat ]; then
					printf 'add chain inet fw4 %s { type nat hook output priority -1; }\n' "$okr_b"
				else
					printf 'add chain inet fw4 %s { }\n' "$okr_b"
				fi
				;;
			SET)
				okr_type=$(okr_nft_type "$okr_c" "$okr_d") || exit 67
				okr_flags=''
				case ",$okr_e," in *,interval,*) okr_flags=' flags interval;' ;; esac
				okr_elements=$(okr_normalize_csv "$okr_f" "$okr_d")
				if [ -n "$okr_elements" ]; then
					printf 'add set inet fw4 %s { type %s;%s elements = { %s }; }\n' "$okr_b" "$okr_type" "$okr_flags" "$okr_elements"
				else
					printf 'add set inet fw4 %s { type %s;%s }\n' "$okr_b" "$okr_type" "$okr_flags"
				fi
				;;
			ATTACH)
				okr_comment=$(okr_trace_comment "$okr_a" "$okr_b" - -)
				printf 'add rule inet fw4 %s %s %s comment "%s"\n' "$okr_d" "$okr_e" "$okr_g" "$okr_comment"
				;;
			RULE)
				case "$okr_g" in
					RETURN_NATIVE) okr_action='return' ;;
					MARK_PROXY) okr_action="meta mark set $OKR_MARK" ;;
					TPROXY_PROXY) okr_action="$okr_h" ;;
					REDIRECT_PROXY) okr_action="$okr_h" ;;
					DNS_REDIRECT|JUMP) okr_action="$okr_h" ;;
					ACCEPT_IF_REQUIRED) okr_action='accept' ;;
					CONTINUE_POLICY|ACTION_FROM_CLASSIFICATION) okr_action='counter' ;;
					NOT_OWNED|UNRESOLVED_SEMANTIC) continue ;;
					*) exit 65 ;;
				 esac
				[ -n "$okr_action" ] || exit 67
				okr_comment=$(okr_trace_comment "$okr_a" "$okr_b" "$okr_i" "$okr_j")
				printf 'add rule inet fw4 %s %s %s comment "%s"\n' "$okr_d" "$okr_f" "$okr_action" "$okr_comment"
				;;
			esac
	done || okr_render_status=$?
	[ "$okr_render_status" -eq 0 ] || return "$okr_render_status"
	return 0
}

openkill_render_nft_desired()
{
	[ $# -ge 1 ] && [ $# -le 2 ] || { okr_die 64 'usage: openkill_render_nft_desired INPUT [OUTPUT]' ; return $?; }
	okr_input_path=$1
	if [ $# -eq 2 ]; then
		okr_render "$okr_input_path" > "$2" || return $?
	else
		okr_render "$okr_input_path"
	fi
}

if [ "${0##*/}" = "openkill_nft_renderer.sh" ]; then
	openkill_render_nft_desired "$@"
	exit $?
fi
