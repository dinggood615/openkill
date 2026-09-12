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

openkill_extract_node_endpoints()
{
    yaml_file="$1"
    v4_file="${2:-/tmp/openkill-node4}"
    v6_file="${3:-/tmp/openkill-node6}"
    domain_file="${4:-/tmp/openkill-node-domains}"
    [ -r "$yaml_file" ] || return 1
    : > "$v4_file" || return 1
    : > "$v6_file" || return 1
    : > "$domain_file" || return 1
    # Only literal server endpoints are authoritative here.  Domain names are
    # resolved by the existing bootstrap/native resolver at reload time and
    # are never converted from a client Fake-IP answer.
    awk '/^[[:space:]]*server:/ {sub(/^[[:space:]]*server:[[:space:]]*/, ""); gsub(/^["\047]/, ""); gsub(/["\047, #].*/, ""); print}' "$yaml_file" |
        while IFS= read -r endpoint; do
            endpoint=$(printf '%s' "$endpoint" | sed 's/^\[//; s/\]$//')
            case "$endpoint" in
                *:*) printf '%s\n' "$endpoint" >> "$v6_file" ;;
                ''|*[!0-9.]*) printf '%s\n' "$endpoint" >> "$domain_file" ;;
                *) printf '%s\n' "$endpoint" >> "$v4_file" ;;
            esac
        done
    sort -u "$v4_file" -o "$v4_file"
    sort -u "$v6_file" -o "$v6_file"
    sort -u "$domain_file" -o "$domain_file"
}

openkill_resolve_node_domains()
{
    domain_file="$1"; v4_file="$2"; v6_file="$3"
    [ -r "$domain_file" ] || return 1
    command -v getent >/dev/null 2>&1 || return 1
    command -v timeout >/dev/null 2>&1 || return 1
    resolved=0
    while IFS= read -r domain; do
        [ -n "$domain" ] || continue
        v4_result=$(timeout 5 getent ahostsv4 "$domain" 2>/dev/null | awk '$1 ~ /^[0-9.]+$/ {print $1}')
        v6_result=$(timeout 5 getent ahostsv6 "$domain" 2>/dev/null | awk '$1 ~ /:/ {print $1}')
        [ -n "$v4_result" ] && { printf '%s\n' "$v4_result" >> "$v4_file"; resolved=1; }
        [ -n "$v6_result" ] && { printf '%s\n' "$v6_result" >> "$v6_file"; resolved=1; }
    done < "$domain_file"
    sort -u "$v4_file" -o "$v4_file"; sort -u "$v6_file" -o "$v6_file"
    [ "$resolved" -eq 1 ]
}

openkill_refresh_node_endpoints()
{
    static4="$1"; static6="$2"; domains="$3"; applied4="$4"; applied6="$5"
    [ -r "$static4" ] && [ -r "$static6" ] || return 1
    tmp4="${applied4}.tmp.$$"; tmp6="${applied6}.tmp.$$"
    cp "$static4" "$tmp4" && cp "$static6" "$tmp6" || return 1
    if [ -s "$domains" ] && ! openkill_resolve_node_domains "$domains" "$tmp4" "$tmp6"; then
        rm -f "$tmp4" "$tmp6"
        # Transient DNS failure must not remove a known-good underlay.
        [ -r "$applied4" ] && [ -r "$applied6" ] || return 1
        return 1
    fi
    sort -u "$tmp4" -o "$tmp4"; sort -u "$tmp6" -o "$tmp6"
    mv "$tmp4" "$applied4" && mv "$tmp6" "$applied6"
}

openkill_render_node_sets()
{
    v4_file="$1"; v6_file="$2"; output_file="${3:-/tmp/openkill-node-sets.nft}"
    [ -r "$v4_file" ] && [ -r "$v6_file" ] || return 1
    tmp_file="${output_file}.tmp.$$"
    {
        printf 'add set inet fw4 openkill_node4 { type ipv4_addr; flags interval; auto-merge; }\n'
        printf 'add set inet fw4 openkill_node6 { type ipv6_addr; flags interval; auto-merge; }\n'
        while IFS= read -r endpoint; do [ -n "$endpoint" ] && printf 'add element inet fw4 openkill_node4 { %s }\n' "$endpoint"; done < "$v4_file"
        while IFS= read -r endpoint; do [ -n "$endpoint" ] && printf 'add element inet fw4 openkill_node6 { %s }\n' "$endpoint"; done < "$v6_file"
    } > "$tmp_file" && mv "$tmp_file" "$output_file"
}

openkill_owner_actions()
{
    desired_owner="$1"
    case "$desired_owner" in
        openkill) printf '%s\n' 'REMOVE_MIHOMO_AUTO_ROUTE' 'INSTALL_OPENKILL_RULES' 'INSTALL_OPENKILL_TABLE' 'ACTIVATE_CLASSIFIER' ;;
        mihomo) printf '%s\n' 'DEACTIVATE_CLASSIFIER' 'REMOVE_OPENKILL_RULES' 'REMOVE_OPENKILL_TABLE' 'ENABLE_MIHOMO_AUTO_ROUTE' ;;
        *) return 1 ;;
    esac
}

openkill_update_node_endpoints()
{
    old4="$1"; old6="$2"; new4="$3"; new6="$4"; diff_file="${5:-/tmp/openkill-node.diff}"
    [ -r "$new4" ] && [ -r "$new6" ] || return 1
    : > "$diff_file" || return 1
    [ ! -r "$old4" ] || ! cmp -s "$old4" "$new4" && printf 'NODE4_CHANGED\n' >> "$diff_file"
    [ ! -r "$old6" ] || ! cmp -s "$old6" "$new6" && printf 'NODE6_CHANGED\n' >> "$diff_file"
}

openkill_owner_transition()
{
    desired_owner="$1"; applied_file="$2"; result_file="$3"; apply_status="${4:-ok}"
    case "$desired_owner" in openkill|mihomo) ;; *) return 1 ;; esac
    [ "$apply_status" = ok ] || { printf 'OWNER_TRANSITION_FAILED\n' >&2; return 1; }
    tmp_file="${applied_file}.tmp.$$"
    printf 'OWNER=%s\n' "$desired_owner" > "$tmp_file" && mv "$tmp_file" "$applied_file"
    printf 'OWNER=%s\n' "$desired_owner" > "$result_file"
}

openkill_apply_component_state()
{
    component="$1"; desired_file="$2"; applied_file="$3"; apply_status="${4:-ok}"
    [ -r "$desired_file" ] || return 1
    [ "$apply_status" = ok ] || { printf '%s_APPLY_FAILED\n' "$component" >&2; return 1; }
    tmp_file="${applied_file}.tmp.$$"
    cp "$desired_file" "$tmp_file" && mv "$tmp_file" "$applied_file"
}

openkill_request_network_reconcile()
{
    state_dir="${1:-/tmp/openkill-network-reconcile}"
    reason="${2:-manual}"
    mkdir -p "$state_dir" || return 1
    openkill_reconcile_request_pending "$state_dir/pending" || return 1
    tmp_file="$state_dir/reason.tmp.$$"
    printf '%s\n' "$reason" > "$tmp_file" && mv "$tmp_file" "$state_dir/reason"
}

openkill_reconcile_worker_guard()
{
    state_dir="${1:-/tmp/openkill-network-reconcile}"
    max_passes="${2:-3}"
    lock_dir="$state_dir/lock"
    mkdir -p "$state_dir" || return 1
    openkill_reconcile_lock_acquire "$lock_dir" || return 2
    passes=0
    while [ -f "$state_dir/pending" ] && [ "$passes" -lt "$max_passes" ]; do
        rm -f "$state_dir/pending"
        passes=$((passes + 1))
    done
    printf '%s\n' "$passes" > "$state_dir/passes"
    openkill_reconcile_lock_release "$lock_dir"
    [ ! -f "$state_dir/pending" ]
}

openkill_runtime_integrity_action()
{
    desired_file="$1"; runtime_file="$2"
    [ -r "$desired_file" ] && [ -r "$runtime_file" ] || return 1
    chain_present=$(openkill_snapshot_value NFT_CHAIN_PRESENT "$runtime_file")
    owner=$(openkill_snapshot_value TUN_OWNER "$desired_file")
    if [ "$chain_present" != 1 ] && [ "$owner" = openkill ]; then
        printf 'REAPPLY_NFT\n'
    else
        printf 'NO_ACTION\n'
    fi
}

openkill_event_allowed()
{
    snapshot_file="$1"
    [ "$(openkill_snapshot_value ENABLE "$snapshot_file")" = 1 ]
}

openkill_generation_start()
{
    generation_file="${1:-/tmp/openkill-network-reconcile/generation}"
    generation_dir=$(dirname "$generation_file")
    mkdir -p "$generation_dir" || return 1
    generation="$(date +%s 2>/dev/null)-$$"
    tmp_file="${generation_file}.tmp.$$"
    printf '%s\n' "$generation" > "$tmp_file" && mv "$tmp_file" "$generation_file"
    printf '%s\n' "$generation"
}

openkill_generation_is_current()
{
    generation_file="$1"; expected="$2"
    [ -r "$generation_file" ] && [ "$(cat "$generation_file")" = "$expected" ]
}

openkill_remove_proxy_runtime()
{
    # Delete only OpenKill's marked rules and routes in its private table.
    # Native main/source-specific routes and third-party policy are untouched.
    ip rule del fwmark "$OPENKILL_FWMARK" table 354 pref "$OPENKILL_RULE_PREF" 2>/dev/null || true
    ip -6 rule del fwmark "$OPENKILL_FWMARK" table 354 pref "$OPENKILL_RULE_PREF" 2>/dev/null || true
    ip route del default dev utun table 354 2>/dev/null || true
    ip -6 route del default dev utun table 354 2>/dev/null || true
    ip route del local 0.0.0.0/0 dev lo table 354 2>/dev/null || true
    ip -6 route del local ::/0 dev lo table 354 2>/dev/null || true
}

openkill_verify_owner_runtime()
{
    owner="$1"
    case "$owner" in
        openkill)
            ip rule show | grep -q "fwmark $OPENKILL_FWMARK.*lookup 354" || return 1
            ip -6 rule show | grep -q "fwmark $OPENKILL_FWMARK.*lookup 354" || return 1
            ;;
        mihomo)
            ! ip rule show | grep -q "fwmark $OPENKILL_FWMARK.*lookup 354" || return 1
            ! ip -6 rule show | grep -q "fwmark $OPENKILL_FWMARK.*lookup 354" || return 1
            ;;
        *) return 1 ;;
    esac
}

openkill_owner_step()
{
    step="$1"
    [ -z "${OPENKILL_OWNER_TRACE:-}" ] || printf '%s\n' "$step" >> "$OPENKILL_OWNER_TRACE"
    [ "${OPENKILL_OWNER_FAIL_STEP:-}" != "$step" ]
}

openkill_apply_owner_transition()
{
    desired_owner="$1"; applied_file="$2"; generation_file="$3"; expected_generation="$4"; enabled="${5:-1}"
    [ "$enabled" = 1 ] || return 1
    openkill_generation_is_current "$generation_file" "$expected_generation" || return 1
    case "$desired_owner" in
        mihomo)
            openkill_owner_step DISABLE_CLASSIFIER || return 1
            openkill_generation_is_current "$generation_file" "$expected_generation" || return 1
            openkill_owner_step REMOVE_OPENKILL_RUNTIME || return 1
            [ "${OPENKILL_OWNER_DRY_RUN:-0}" = 1 ] || openkill_remove_proxy_runtime || return 1
            openkill_owner_step ENABLE_MIHOMO_OWNER || return 1
            ;;
        openkill)
            openkill_owner_step DISABLE_MIHOMO_OWNER || return 1
            openkill_generation_is_current "$generation_file" "$expected_generation" || return 1
            openkill_owner_step INSTALL_OPENKILL_ROUTE || return 1
            if [ "${OPENKILL_OWNER_DRY_RUN:-0}" != 1 ]; then
                [ -n "${OPENKILL_TUN_DEVICE:-}" ] || return 1
                ip route replace default dev "$OPENKILL_TUN_DEVICE" table 354 || return 1
                ip -6 route replace default dev "$OPENKILL_TUN_DEVICE" table 354 || return 1
                openkill_ensure_proxy_rule4 || return 1
                openkill_ensure_proxy_rule6 || return 1
            fi
            openkill_owner_step ACTIVATE_CLASSIFIER || return 1
            ;;
        *) return 1 ;;
    esac
    openkill_generation_is_current "$generation_file" "$expected_generation" || return 1
    openkill_owner_transition "$desired_owner" "$applied_file" "${applied_file}.result" ok
}

openkill_ensure_proxy_rule4() { ip rule show | grep -q "fwmark $OPENKILL_FWMARK.*lookup $OPENKILL_ROUTE_TABLE" || ip rule add fwmark "$OPENKILL_FWMARK" table "$OPENKILL_ROUTE_TABLE" pref "$OPENKILL_RULE_PREF"; }
openkill_ensure_proxy_rule6() { ip -6 rule show | grep -q "fwmark $OPENKILL_FWMARK.*lookup $OPENKILL_ROUTE_TABLE" || ip -6 rule add fwmark "$OPENKILL_FWMARK" table "$OPENKILL_ROUTE_TABLE" pref "$OPENKILL_RULE_PREF"; }
openkill_remove_proxy_rule4() { ip rule del fwmark "$OPENKILL_FWMARK" table "$OPENKILL_ROUTE_TABLE" pref "$OPENKILL_RULE_PREF" 2>/dev/null || true; }
openkill_remove_proxy_rule6() { ip -6 rule del fwmark "$OPENKILL_FWMARK" table "$OPENKILL_ROUTE_TABLE" pref "$OPENKILL_RULE_PREF" 2>/dev/null || true; }
