#!/bin/sh
# Shared network snapshot and desired-state helpers.
# The collector reports native state only; OpenKill-owned objects are kept in
# the desired-state layer and are never inferred as WAN/native routes.

OPENKILL_FWMARK="0x162"
OPENKILL_FWMASK="0xffffffff"
OPENKILL_ROUTE_TABLE="0x162"
OPENKILL_RULE_PREF="1888"

openkill_collect_network_snapshot()
{
    snapshot_file="${1:-/tmp/openkill-network.snapshot}"
    snapshot_dir=$(dirname "$snapshot_file")
    mkdir -p "$snapshot_dir" || return 1
    tmp_file="${snapshot_file}.tmp.$$"
    : > "$tmp_file" || return 1

    wan4_device=$(uci -q get network.wan.device 2>/dev/null || uci -q get network.wan.ifname 2>/dev/null || true)
    wan6_device=$(uci -q get network.wan6.device 2>/dev/null || uci -q get network.wan6.ifname 2>/dev/null || true)
    [ -n "$wan4_device" ] || wan4_device=$(ubus call network.interface.wan status 2>/dev/null | jsonfilter -e '@.l3_device' 2>/dev/null || true)
    [ -n "$wan6_device" ] || wan6_device=$(ubus call network.interface.wan6 status 2>/dev/null | jsonfilter -e '@.l3_device' 2>/dev/null || true)

    printf 'SNAPSHOT_VERSION=1\n' >> "$tmp_file"
    printf 'WAN4_L3_DEVICE=%s\n' "$wan4_device" >> "$tmp_file"
    printf 'WAN6_L3_DEVICE=%s\n' "$wan6_device" >> "$tmp_file"
    printf 'WAN4_ADDRESSES=%s\n' "$(ip -4 addr show dev "$wan4_device" scope global 2>/dev/null | awk '/inet / {sub("/.*", "", $2); print $2}' | tr '\n' ' ')" >> "$tmp_file"
    printf 'WAN6_ADDRESSES=%s\n' "$(ip -6 addr show dev "$wan6_device" scope global 2>/dev/null | awk '/inet6 / {sub("/.*", "", $2); print $2}' | tr '\n' ' ')" >> "$tmp_file"
    printf 'NATIVE_IPV4_ROUTES=%s\n' "$(ip -4 route show table main 2>/dev/null | tr '\n' ';')" >> "$tmp_file"
    printf 'NATIVE_IPV6_ROUTES=%s\n' "$(ip -6 route show table main 2>/dev/null | tr '\n' ';')" >> "$tmp_file"
    printf 'NATIVE_IPV6_RULES=%s\n' "$(ip -6 rule show 2>/dev/null | tr '\n' ';')" >> "$tmp_file"
    printf 'INTERNAL_IPV6_PREFIXES=%s\n' "$(/usr/share/openkill/openkill_get_network.lua lan_cidr6 2>/dev/null | tr '\n' ' ')" >> "$tmp_file"
    printf 'DNS_SERVERS=%s\n' "$(ubus call network.interface dump 2>/dev/null | jsonfilter -e '@.interface[*].dns-server[*]' 2>/dev/null | tr '\n' ' ')" >> "$tmp_file"

    # Readiness is local: address + native route, never a public probe.
    if [ -n "$(grep -E '^WAN6_ADDRESSES=.' "$tmp_file")" ] &&
       grep -q '^NATIVE_IPV6_ROUTES=.*default' "$tmp_file"; then
        printf 'LOCAL_IPV6_READY=1\n' >> "$tmp_file"
    else
        printf 'LOCAL_IPV6_READY=0\n' >> "$tmp_file"
    fi
    printf 'PUBLIC_IPV6_HEALTH=unknown\n' >> "$tmp_file"
    mv "$tmp_file" "$snapshot_file"
}

openkill_build_desired_state()
{
    snapshot_file="$1"
    desired_file="${2:-/tmp/openkill-network.desired}"
    [ -r "$snapshot_file" ] || return 1
    # Do not source arbitrary snapshot data.  The model consumes only the
    # whitelisted fields and writes stable KEY=value output.
    ipv6_ready=$(sed -n 's/^LOCAL_IPV6_READY=//p' "$snapshot_file" | head -n 1)
    internal6=$(sed -n 's/^INTERNAL_IPV6_PREFIXES=//p' "$snapshot_file" | head -n 1)
    node4=$(sed -n 's/^NODE4_ENDPOINTS=//p' "$snapshot_file" | head -n 1)
    node6=$(sed -n 's/^NODE6_ENDPOINTS=//p' "$snapshot_file" | head -n 1)
    : > "$desired_file" || return 1
    printf 'OPENKILL_FWMARK=%s\nOPENKILL_FWMASK=%s\nOPENKILL_ROUTE_TABLE=%s\nOPENKILL_RULE_PREF=%s\n' \
        "$OPENKILL_FWMARK" "$OPENKILL_FWMASK" "$OPENKILL_ROUTE_TABLE" "$OPENKILL_RULE_PREF" >> "$desired_file"
    printf 'IPV4_PROXY_RULE=1\nIPV4_TUN_ROUTE=1\n' >> "$desired_file"
    if [ "$ipv6_ready" = 1 ]; then
        printf 'IPV6_PROXY_RULE=1\nIPV6_TUN_ROUTE=1\n'
    else
        printf 'IPV6_PROXY_RULE=0\nIPV6_TUN_ROUTE=0\n'
    fi >> "$desired_file"
    printf 'LOCALNETWORK6_PREFIXES=%s\n' "$internal6" >> "$desired_file"
    printf 'NODE4_ENDPOINTS=%s\nNODE6_ENDPOINTS=%s\n' "$(openkill_normalize_list "$node4")" "$(openkill_normalize_list "$node6")" >> "$desired_file"
    printf 'NATIVE_IPV6_ROUTE_MUTATIONS=0\nDNS_INTERCEPTION=1\nTUN_BACKEND=openkill\nTPROXY_BACKEND=legacy-compatible\n' >> "$desired_file"
}

openkill_snapshot_value()
{
    sed -n "s/^$1=//p" "$2" | head -n 1
}

openkill_normalize_list()
{
    printf '%s\n' "$*" | tr ' ;' '\n\n' | sed '/^$/d' | sort -u | tr '\n' ' ' | sed 's/[[:space:]]*$//'
}

openkill_network_fingerprint()
{
    snapshot_file="$1"
    fingerprint_file="${2:-/tmp/openkill-network.fingerprint}"
    [ -r "$snapshot_file" ] || return 1
    tmp_file="${fingerprint_file}.tmp.$$"
    {
        printf 'WAN4_L3_DEVICE=%s\n' "$(openkill_snapshot_value WAN4_L3_DEVICE "$snapshot_file")"
        printf 'WAN4_ADDRESSES=%s\n' "$(openkill_normalize_list "$(openkill_snapshot_value WAN4_ADDRESSES "$snapshot_file")")"
        printf 'WAN6_L3_DEVICE=%s\n' "$(openkill_snapshot_value WAN6_L3_DEVICE "$snapshot_file")"
        printf 'WAN6_ADDRESSES=%s\n' "$(openkill_normalize_list "$(openkill_snapshot_value WAN6_ADDRESSES "$snapshot_file")")"
        printf 'NATIVE_IPV6_ROUTES=%s\n' "$(openkill_normalize_list "$(openkill_snapshot_value NATIVE_IPV6_ROUTES "$snapshot_file")")"
        printf 'INTERNAL_IPV4_PREFIXES=%s\n' "$(openkill_normalize_list "$(openkill_snapshot_value INTERNAL_IPV4_PREFIXES "$snapshot_file")")"
        printf 'INTERNAL_IPV6_PREFIXES=%s\n' "$(openkill_normalize_list "$(openkill_snapshot_value INTERNAL_IPV6_PREFIXES "$snapshot_file")")"
        printf 'DNS_SERVERS=%s\n' "$(openkill_normalize_list "$(openkill_snapshot_value DNS_SERVERS "$snapshot_file")")"
        printf 'TUN_OWNER=%s\n' "$(openkill_snapshot_value TUN_OWNER "$snapshot_file")"
        printf 'IPV4_ENABLED=%s\nIPV6_ENABLED=%s\n' "$(openkill_snapshot_value IPV4_ENABLED "$snapshot_file")" "$(openkill_snapshot_value IPV6_ENABLED "$snapshot_file")"
    } > "$tmp_file" || return 1
    mv "$tmp_file" "$fingerprint_file"
}

openkill_classify_network_change()
{
    old_file="$1"
    new_file="$2"
    [ -r "$old_file" ] && [ -r "$new_file" ] || return 1
    changes=""
    old4=$(openkill_snapshot_value WAN4_L3_DEVICE "$old_file")
    new4=$(openkill_snapshot_value WAN4_L3_DEVICE "$new_file")
    old4a=$(openkill_snapshot_value WAN4_ADDRESSES "$old_file")
    new4a=$(openkill_snapshot_value WAN4_ADDRESSES "$new_file")
    [ "$old4:$old4a" = "$new4:$new4a" ] || changes="$changes WAN4_CHANGED"
    old6=$(openkill_snapshot_value WAN6_L3_DEVICE "$old_file")
    new6=$(openkill_snapshot_value WAN6_L3_DEVICE "$new_file")
    old6a=$(openkill_snapshot_value WAN6_ADDRESSES "$old_file")
    new6a=$(openkill_snapshot_value WAN6_ADDRESSES "$new_file")
    [ "$old6:$old6a" = "$new6:$new6a" ] || changes="$changes WAN6_CHANGED"
    [ "$(openkill_snapshot_value INTERNAL_IPV6_PREFIXES "$old_file")" = "$(openkill_snapshot_value INTERNAL_IPV6_PREFIXES "$new_file")" ] || changes="$changes PD_CHANGED INTERNAL_PREFIX_CHANGED"
    [ "$(openkill_snapshot_value DNS_SERVERS "$old_file")" = "$(openkill_snapshot_value DNS_SERVERS "$new_file")" ] || changes="$changes DNS_CHANGED"
    [ "$(openkill_snapshot_value TUN_OWNER "$old_file")" = "$(openkill_snapshot_value TUN_OWNER "$new_file")" ] || changes="$changes OWNER_MODE_CHANGED"
    [ -n "$changes" ] && printf '%s\n' "$changes" | sed 's/^ *//' || printf 'NO_RELEVANT_CHANGE\n'
}

openkill_desired_diff()
{
    old_file="$1"
    new_file="$2"
    [ -r "$old_file" ] && [ -r "$new_file" ] || return 1
    old_norm=$(sort "$old_file")
    new_norm=$(sort "$new_file")
    [ "$old_norm" = "$new_norm" ] && { printf 'NO_ACTION\n'; return 0; }
    [ "$(openkill_snapshot_value LOCALNETWORK6_PREFIXES "$old_file")" = "$(openkill_snapshot_value LOCALNETWORK6_PREFIXES "$new_file")" ] || printf 'LOCAL6_CHANGED\n'
    [ "$(openkill_snapshot_value NODE4_ENDPOINTS "$old_file")" = "$(openkill_snapshot_value NODE4_ENDPOINTS "$new_file")" ] || printf 'NODE4_CHANGED\n'
    [ "$(openkill_snapshot_value NODE6_ENDPOINTS "$old_file")" = "$(openkill_snapshot_value NODE6_ENDPOINTS "$new_file")" ] || printf 'NODE6_CHANGED\n'
    [ "$(openkill_snapshot_value TUN_OWNER "$old_file")" = "$(openkill_snapshot_value TUN_OWNER "$new_file")" ] || printf 'OWNER_CHANGED\n'
}

openkill_validate_owner_mode()
{
    owner=$(openkill_snapshot_value TUN_OWNER "$1")
    auto_route=$(openkill_snapshot_value MIHOMO_AUTO_ROUTE "$1")
    auto_redirect=$(openkill_snapshot_value MIHOMO_AUTO_REDIRECT "$1")
    case "$owner:$auto_route:$auto_redirect" in
        openkill:0:0) return 0 ;;
        mihomo:1:1|mihomo:1:0|mihomo:0:1) return 0 ;;
        *) printf 'DUAL_OWNER_OR_INVALID\n' >&2; return 1 ;;
    esac
}

openkill_reconcile_lock_acquire()
{
    lock_dir="${1:-/tmp/openkill-network-reconcile.lock}"
    mkdir "$lock_dir" 2>/dev/null
}

openkill_reconcile_lock_release()
{
    rmdir "${1:-/tmp/openkill-network-reconcile.lock}" 2>/dev/null || true
}

openkill_reconcile_request_pending()
{
    pending_file="${1:-/tmp/openkill-network-reconcile.pending}"
    tmp_file="${pending_file}.tmp.$$"
    printf '1\n' > "$tmp_file" && mv "$tmp_file" "$pending_file"
}

openkill_ensure_proxy_rule4() { ip rule show | grep -q "fwmark $OPENKILL_FWMARK.*lookup $OPENKILL_ROUTE_TABLE" || ip rule add fwmark "$OPENKILL_FWMARK" table "$OPENKILL_ROUTE_TABLE" pref "$OPENKILL_RULE_PREF"; }
openkill_ensure_proxy_rule6() { ip -6 rule show | grep -q "fwmark $OPENKILL_FWMARK.*lookup $OPENKILL_ROUTE_TABLE" || ip -6 rule add fwmark "$OPENKILL_FWMARK" table "$OPENKILL_ROUTE_TABLE" pref "$OPENKILL_RULE_PREF"; }
openkill_remove_proxy_rule4() { ip rule del fwmark "$OPENKILL_FWMARK" table "$OPENKILL_ROUTE_TABLE" pref "$OPENKILL_RULE_PREF" 2>/dev/null || true; }
openkill_remove_proxy_rule6() { ip -6 rule del fwmark "$OPENKILL_FWMARK" table "$OPENKILL_ROUTE_TABLE" pref "$OPENKILL_RULE_PREF" 2>/dev/null || true; }
