#!/bin/sh
# Shared network snapshot and desired-state helpers.
# The collector reports native state only; OpenKill-owned objects are kept in
# the desired-state layer and are never inferred as WAN/native routes.

OPENKILL_FWMARK="0x162"
OPENKILL_FWMASK="0xffffffff"
OPENKILL_ROUTE_TABLE="0x162"
OPENKILL_RULE_PREF="1888"

openkill_interface_json_value()
{
    json_file="$1"; index="$2"; field="$3"
    command -v jsonfilter >/dev/null 2>&1 || return 1
    case "$field" in
        ipv6-prefix-assignment*)
            field_expression="[\"ipv6-prefix-assignment\"]${field#ipv6-prefix-assignment}" ;;
        ipv4-address*)
            field_expression="[\"ipv4-address\"]${field#ipv4-address}" ;;
        ipv6-address*)
            field_expression="[\"ipv6-address\"]${field#ipv6-address}" ;;
        ipv6-prefix*)
            field_expression="[\"ipv6-prefix\"]${field#ipv6-prefix}" ;;
        dns-server*)
            field_expression="[\"dns-server\"]${field#dns-server}" ;;
        *)
            field_expression=".$field" ;;
    esac
    expression="@.interface[$index]$field_expression"
    value=$(jsonfilter -i "$json_file" -e "$expression" 2>/dev/null | sed -n '1p')
    # Older jsonfilter builds and lightweight test shims may only implement
    # dotted access. Keep that as a compatibility fallback, while production
    # uses bracket notation for netifd's hyphenated keys above.
    if [ -z "$value" ] && [ "$field_expression" != ".$field" ]; then
        value=$(jsonfilter -i "$json_file" -e "@.interface[$index].$field" 2>/dev/null | sed -n '1p')
    fi
    value=$(printf '%s' "$value" | sed 's/^"//; s/"$//')
    [ -n "$value" ] && printf '%s\n' "$value"
}

openkill_write_selected_interface_role()
{
    output_file="$1"; selected_name="$2"; selected_device="$3"; selected_index="$4"
    printf 'INTERFACE=%s\nDEVICE=%s\n' "$selected_name" "$selected_device" > "$output_file"
    [ -n "$selected_index" ] && printf 'INDEX=%s\n' "$selected_index" >> "$output_file"
    return 0
}

openkill_select_interface_role()
{
    records_file="$1"; explicit="$2"; canonical="$3"; route_devices="$4"; output_file="$5"; family="${6:-}"
    selected_name=""; selected_device=""; selected_index=""; matches=0

    # Explicit role configuration has precedence, but ambiguity is a hard
    # failure-safe result rather than an arbitrary first match.
    if [ -n "$explicit" ] && [ -r "$records_file" ]; then
        while IFS='|' read -r name l3_device device has4 has6 proto up index; do
            [ "$up" = false ] || [ "$up" = 0 ] && continue
            if [ "$name" = "$explicit" ] || [ "$l3_device" = "$explicit" ] || [ "$device" = "$explicit" ]; then
                matches=$((matches + 1)); selected_name="$name"; selected_device="${l3_device:-$device}"; selected_index="$index"
            fi
        done < "$records_file"
        [ "$matches" -eq 1 ] && {
            openkill_write_selected_interface_role "$output_file" "$selected_name" "$selected_device" "$selected_index"
            return 0
        }
        [ "$matches" -gt 1 ] && return 1
    fi

    # Canonical names are matched case-insensitively (WAN/WAN6 are common on
    # LuCI-derived configurations), but only when the match is unique.
    selected_name=""; selected_device=""; selected_index=""; matches=0
    if [ -r "$records_file" ]; then
        while IFS='|' read -r name l3_device device has4 has6 proto up index; do
            [ "$up" = false ] || [ "$up" = 0 ] && continue
            lower_name=$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')
            if [ "$lower_name" = "$canonical" ]; then
                matches=$((matches + 1)); selected_name="$name"; selected_device="${l3_device:-$device}"; selected_index="$index"
            fi
        done < "$records_file"
    fi
    [ "$matches" -eq 1 ] && {
        openkill_write_selected_interface_role "$output_file" "$selected_name" "$selected_device" "$selected_index"
        return 0
    }
    [ "$matches" -gt 1 ] && return 1

    # Custom logical names are resolved from the active native default-route
    # device. Source-specific IPv6 defaults are included by the route parser.
    route_matches=0; selected_name=""; selected_device=""; selected_index=""
    for route_device in $route_devices; do
        route_count=0; route_name=""; route_l3=""; route_index=""; family_matches=0; family_name=""; family_l3=""; family_index=""
        while IFS='|' read -r name l3_device device has4 has6 proto up index; do
            [ "$up" = false ] || [ "$up" = 0 ] && continue
            if [ "$name" = "$route_device" ] || [ "$l3_device" = "$route_device" ] || [ "$device" = "$route_device" ]; then
                route_count=$((route_count + 1)); route_name="$name"; route_l3="${l3_device:-$device}"; route_index="$index"
                role_family_match=0
                if [ "$family" = 4 ] && [ "$has4" = 1 ]; then
                    role_family_match=1
                elif [ "$family" = 6 ] && [ "$has6" = 1 ]; then
                    role_family_match=1
                elif [ "$family" = 4 ] && [ -z "$has4" ] && [ "$proto" != "dhcpv6" ] && [ "$proto" != "6in4" ]; then
                    role_family_match=1
                elif [ "$family" = 6 ] && [ -z "$has6" ] && [ "$proto" = "dhcpv6" ]; then
                    role_family_match=1
                fi
                if [ "$role_family_match" -eq 1 ]; then
                    family_matches=$((family_matches + 1)); family_name="$name"; family_l3="${l3_device:-$device}"; family_index="$index"
                fi
            fi
        done < "$records_file"
        if [ "$route_count" -eq 1 ]; then
            route_matches=$((route_matches + 1)); selected_name="$route_name"; selected_device="$route_l3"; selected_index="$route_index"
        elif [ "$route_count" -gt 1 ] && [ "$family_matches" -eq 1 ]; then
            # A dual-stack PPPoE can expose separate custom logical objects
            # that share one l3_device.  Use netifd's address-family data (or
            # its dhcpv6 proto) to select the role without guessing.
            route_matches=$((route_matches + 1)); selected_name="$family_name"; selected_device="$family_l3"; selected_index="$family_index"
        elif [ "$route_count" -eq 0 ] && [ -n "$route_device" ]; then
            # A route can exist before netifd publishes its object. The device
            # itself is still safe to use for native address collection.
            route_matches=$((route_matches + 1)); selected_name="$route_device"; selected_device="$route_device"; selected_index=""
        fi
    done
    [ "$route_matches" -eq 1 ] || return 1
    openkill_write_selected_interface_role "$output_file" "$selected_name" "$selected_device" "$selected_index"
}

openkill_resolve_interface_roles()
{
    roles_dump_file="$1"; roles_output_file="${2:-/tmp/openkill-interface-roles}"
    roles_output_dir=$(dirname "$roles_output_file")
    mkdir -p "$roles_output_dir" || return 1
    roles_tmp_file="${roles_output_file}.tmp.$$"
    : > "$roles_tmp_file" || return 1

    # Tests and recovery tooling may provide an already-normalized role
    # fixture. Production still uses the single netifd dump below.
    if [ -n "${OPENKILL_INTERFACE_ROLE_FIXTURE:-}" ] && [ -r "$OPENKILL_INTERFACE_ROLE_FIXTURE" ]; then
        if cp "$OPENKILL_INTERFACE_ROLE_FIXTURE" "$roles_tmp_file" && mv "$roles_tmp_file" "$roles_output_file"; then
            return 0
        fi
        rm -f "$roles_tmp_file"
        return 1
    fi
    [ -r "$roles_dump_file" ] || { rm -f "$roles_tmp_file"; return 1; }
    command -v jsonfilter >/dev/null 2>&1 || { rm -f "$roles_tmp_file"; return 1; }

    roles_records_file="${roles_tmp_file}.records"
    : > "$roles_records_file" || { rm -f "$roles_tmp_file"; return 1; }
    roles_index=0
    while [ "$roles_index" -lt 128 ]; do
        name=$(openkill_interface_json_value "$roles_dump_file" "$roles_index" interface)
        [ -n "$name" ] || break
        l3_device=$(openkill_interface_json_value "$roles_dump_file" "$roles_index" l3_device)
        device=$(openkill_interface_json_value "$roles_dump_file" "$roles_index" device)
        has4=; has6=; proto=
        [ -n "$(openkill_interface_json_value "$roles_dump_file" "$roles_index" 'ipv4-address[0].address')" ] && has4=1
        [ -n "$(openkill_interface_json_value "$roles_dump_file" "$roles_index" 'ipv6-address[0].address')" ] && has6=1
        proto=$(openkill_interface_json_value "$roles_dump_file" "$roles_index" proto)
        up=$(openkill_interface_json_value "$roles_dump_file" "$roles_index" up)
        printf '%s|%s|%s|%s|%s|%s|%s|%s\n' "$name" "$l3_device" "$device" "$has4" "$has6" "$proto" "$up" "$roles_index" >> "$roles_records_file"
        roles_index=$((roles_index + 1))
    done

    explicit4=$(uci -q get openkill.config.wan4_interface_name 2>/dev/null || true)
    explicit6=$(uci -q get openkill.config.wan6_interface_name 2>/dev/null || true)
    common_explicit=$(uci -q get openkill.config.wan_interface_name 2>/dev/null || true)
    [ -n "$explicit4" ] || explicit4="$common_explicit"
    [ -n "$explicit6" ] || explicit6="$common_explicit"
    # Only default-route devices identify an external role.  Connected LAN,
    # loopback, and throw/unreachable routes in the main table are not WAN
    # candidates and must not make a custom role appear ambiguous.
    route4_devices=$(ip -4 route show table main 2>/dev/null | awk '$1 == "default" {for (i=1;i<=NF;i++) if ($i=="dev") print $(i+1)}' | sort -u)
    route6_devices=$(ip -6 route show table main 2>/dev/null | awk '$1 == "default" {for (i=1;i<=NF;i++) if ($i=="dev") print $(i+1)}' | sort -u)
    roles_role4="${roles_tmp_file}.v4"; roles_role6="${roles_tmp_file}.v6"
    openkill_select_interface_role "$roles_records_file" "$explicit4" wan "$route4_devices" "$roles_role4" 4 || :
    openkill_select_interface_role "$roles_records_file" "$explicit6" wan6 "$route6_devices" "$roles_role6" 6 || :
    printf 'WAN4_INTERFACE=%s\nWAN4_L3_DEVICE=%s\nWAN4_INDEX=%s\n' \
        "$(openkill_snapshot_value INTERFACE "$roles_role4" 2>/dev/null || true)" \
        "$(openkill_snapshot_value DEVICE "$roles_role4" 2>/dev/null || true)" \
        "$(openkill_snapshot_value INDEX "$roles_role4" 2>/dev/null || true)" >> "$roles_tmp_file"
    printf 'WAN6_INTERFACE=%s\nWAN6_L3_DEVICE=%s\nWAN6_INDEX=%s\n' \
        "$(openkill_snapshot_value INTERFACE "$roles_role6" 2>/dev/null || true)" \
        "$(openkill_snapshot_value DEVICE "$roles_role6" 2>/dev/null || true)" \
        "$(openkill_snapshot_value INDEX "$roles_role6" 2>/dev/null || true)" >> "$roles_tmp_file"
    mv "$roles_tmp_file" "$roles_output_file" || {
        rm -f "$roles_tmp_file" "$roles_records_file" "$roles_role4" "$roles_role6"
        return 1
    }
    rm -f "$roles_records_file" "$roles_role4" "$roles_role6"
}

openkill_collect_network_snapshot()
{
    snapshot_file="${1:-/tmp/openkill-network.snapshot}"
    snapshot_dir=$(dirname "$snapshot_file")
    mkdir -p "$snapshot_dir" || return 1
    tmp_file="${snapshot_file}.tmp.$$"
    : > "$tmp_file" || return 1

    interface_dump="${OPENKILL_INTERFACE_DUMP_FILE:-${snapshot_file}.interfaces.$$}"
    interface_dump_owned=0
    if [ ! -r "$interface_dump" ]; then
        ubus call network.interface dump > "$interface_dump" 2>/dev/null || : > "$interface_dump"
        interface_dump_owned=1
    fi
    role_file="${snapshot_file}.roles.$$"
    openkill_resolve_interface_roles "$interface_dump" "$role_file" 2>/dev/null || :
    wan4_interface=$(openkill_snapshot_value WAN4_INTERFACE "$role_file" 2>/dev/null || true)
    wan6_interface=$(openkill_snapshot_value WAN6_INTERFACE "$role_file" 2>/dev/null || true)
    wan4_device=$(openkill_snapshot_value WAN4_L3_DEVICE "$role_file" 2>/dev/null || true)
    wan6_device=$(openkill_snapshot_value WAN6_L3_DEVICE "$role_file" 2>/dev/null || true)
    wan4_index=$(openkill_snapshot_value WAN4_INDEX "$role_file" 2>/dev/null || true)
    wan6_index=$(openkill_snapshot_value WAN6_INDEX "$role_file" 2>/dev/null || true)
    # Keep a narrow legacy fallback for installations without jsonfilter; it
    # is never preferred over the normalized netifd dump.
    [ -n "$wan4_device" ] || wan4_device=$(uci -q get network.wan.device 2>/dev/null || uci -q get network.wan.ifname 2>/dev/null || true)
    [ -n "$wan6_device" ] || wan6_device=$(uci -q get network.wan6.device 2>/dev/null || uci -q get network.wan6.ifname 2>/dev/null || true)

    printf 'SNAPSHOT_VERSION=1\n' >> "$tmp_file"
    printf 'SNAPSHOT_NORMALIZED=1\n' >> "$tmp_file"
    printf 'WAN4_INTERFACE=%s\n' "$wan4_interface" >> "$tmp_file"
    printf 'WAN6_INTERFACE=%s\n' "$wan6_interface" >> "$tmp_file"
    printf 'WAN4_L3_DEVICE=%s\n' "$wan4_device" >> "$tmp_file"
    printf 'WAN6_L3_DEVICE=%s\n' "$wan6_device" >> "$tmp_file"
    # Consume address data from the selected objects in the one netifd dump.
    # Both logical WAN objects may share an L3 device, so aggregate the two
    # selected indices by family and deduplicate below. The device scan is a
    # compatibility fallback for normalized role fixtures that have no index;
    # it is never used to choose a role or inspect unrelated interfaces.
    wan4_addresses=""
    wan6_addresses=""
    for selected_index in "$wan4_index" "$wan6_index"; do
        [ -n "$selected_index" ] || continue
        selected_values=$(openkill_interface_address_values "$interface_dump" "$selected_index" 4)
        [ -n "$selected_values" ] && wan4_addresses="$wan4_addresses $selected_values"
        selected_values=$(openkill_interface_address_values "$interface_dump" "$selected_index" 6)
        [ -n "$selected_values" ] && wan6_addresses="$wan6_addresses $selected_values"
    done
    [ -n "$wan4_addresses" ] || wan4_addresses=$(openkill_device_address_values "$wan4_device" 4 2>/dev/null || true)
    [ -n "$wan6_addresses" ] || wan6_addresses=$(openkill_device_address_values "$wan6_device" 6 2>/dev/null || true)
    printf 'WAN4_ADDRESSES=%s\n' "$(openkill_normalize_list "$wan4_addresses")" >> "$tmp_file"
    printf 'WAN6_ADDRESSES=%s\n' "$(openkill_normalize_list "$wan6_addresses")" >> "$tmp_file"
    # Address tokens are whitespace-separated in the normalized snapshot;
    # expand them as individual arguments so a trailing separator cannot make
    # the validator reject the otherwise valid host.
    printf 'WAN6_HOST_ADDRESSES=%s\n' "$(openkill_normalize_list "$(openkill_wan6_host_list $wan6_addresses)")" >> "$tmp_file"
    printf 'NATIVE_IPV4_ROUTES=%s\n' "$(ip -4 route show table main 2>/dev/null | tr '\n' ';')" >> "$tmp_file"
    printf 'NATIVE_IPV6_ROUTES=%s\n' "$(ip -6 route show table main 2>/dev/null | tr '\n' ';')" >> "$tmp_file"
    printf 'NATIVE_IPV6_RULES=%s\n' "$(ip -6 rule show 2>/dev/null | tr '\n' ';')" >> "$tmp_file"
    network_lua="${OPENKILL_NETWORK_LUA:-/usr/share/openkill/openkill_get_network.lua}"
    printf 'INTERNAL_IPV6_PREFIXES=%s\n' "$(OPENKILL_INTERFACE_DUMP_FILE="$interface_dump" "$network_lua" lan_cidr6 2>/dev/null | tr '\n' ' ' | awk '{$1=$1; print}')" >> "$tmp_file"
    dns_servers=""
    for selected_index in "$wan4_index" "$wan6_index"; do
        [ -n "$selected_index" ] || continue
        selected_values=$(openkill_interface_dns_values "$interface_dump" "$selected_index")
        [ -n "$selected_values" ] && dns_servers="$dns_servers $selected_values"
    done
    # A legacy normalized role fixture has no object indices. In that case only
    # the dump-wide DNS list is available; production selections use the
    # selected-object path above and therefore never include LAN-only DNS data.
    if [ -z "$wan4_index$wan6_index" ]; then
        dns_servers=$(jsonfilter -i "$interface_dump" -e '@.interface[*]["dns-server"][*]' 2>/dev/null |
            sed -n '1p' | tr '\n' ' ')
        [ -n "$dns_servers" ] || dns_servers=$(jsonfilter -i "$interface_dump" -e '@.interface[*].dns-server[*]' 2>/dev/null |
            sed -n '1p' | tr '\n' ' ')
    fi
    printf 'DNS_SERVERS=%s\n' "$(openkill_normalize_list "$dns_servers")" >> "$tmp_file"

    # Readiness is local: address + native route, never a public probe.
    native6_routes=$(openkill_snapshot_value NATIVE_IPV6_ROUTES "$tmp_file")
    wan6_addresses=$(openkill_snapshot_value WAN6_ADDRESSES "$tmp_file")
    ipv6_route_ready=0
    case "$native6_routes" in *default*) ipv6_route_ready=1 ;; esac
    if [ -n "$wan6_addresses" ] && [ "$ipv6_route_ready" -eq 1 ]; then
        printf 'LOCAL_IPV6_READY=1\n' >> "$tmp_file"
    else
        printf 'LOCAL_IPV6_READY=0\n' >> "$tmp_file"
    fi
    printf 'PUBLIC_IPV6_HEALTH=unknown\n' >> "$tmp_file"
    mv "$tmp_file" "$snapshot_file" || {
        rm -f "$tmp_file" "$role_file"
        [ "$interface_dump_owned" -eq 1 ] && rm -f "$interface_dump"
        return 1
    }
    [ "$interface_dump_owned" -eq 1 ] && rm -f "$interface_dump"
    rm -f "$role_file"
}

openkill_build_desired_state()
{
    snapshot_file="$1"
    desired_file="${2:-/tmp/openkill-network.desired}"
    [ -r "$snapshot_file" ] || return 1
    # Do not source arbitrary snapshot data.  The model consumes only the
    # whitelisted fields and writes stable KEY=value output.
    ipv6_ready=0; normalized_snapshot=0; internal6=""; wan6_hosts=""; node4=""; node6=""
    while IFS= read -r line; do
        case "$line" in
            LOCAL_IPV6_READY=*) ipv6_ready="${line#*=}" ;;
            SNAPSHOT_NORMALIZED=*) normalized_snapshot="${line#*=}" ;;
            INTERNAL_IPV6_PREFIXES=*) internal6="${line#*=}" ;;
            WAN6_HOST_ADDRESSES=*) wan6_hosts="${line#*=}" ;;
            NODE4_ENDPOINTS=*) node4="${line#*=}" ;;
            NODE6_ENDPOINTS=*) node6="${line#*=}" ;;
        esac
    done < "$snapshot_file"
    : > "$desired_file" || return 1
    printf 'OPENKILL_FWMARK=%s\nOPENKILL_FWMASK=%s\nOPENKILL_ROUTE_TABLE=%s\nOPENKILL_RULE_PREF=%s\n' \
        "$OPENKILL_FWMARK" "$OPENKILL_FWMASK" "$OPENKILL_ROUTE_TABLE" "$OPENKILL_RULE_PREF" >> "$desired_file"
    printf 'IPV4_PROXY_RULE=1\nIPV4_TUN_ROUTE=1\n' >> "$desired_file"
    if [ "$ipv6_ready" = 1 ]; then
        printf 'IPV6_PROXY_RULE=1\nIPV6_TUN_ROUTE=1\n'
    else
        printf 'IPV6_PROXY_RULE=0\nIPV6_TUN_ROUTE=0\n'
    fi >> "$desired_file"
    # Internal delegated/on-link prefixes bypass as networks.  WAN addresses
    # are represented separately as /128 hosts so the uplink /64 is never
    # accidentally treated as a local network.
    if [ "$normalized_snapshot" = 1 ]; then
        # The collector has already sorted and deduplicated both lists. Keep
        # this hot path shell-only; arbitrary fixture/user text still goes
        # through the defensive normalizer below.
        localnetwork6="$internal6 $wan6_hosts"
    else
        localnetwork6="$(openkill_normalize_tokens $internal6 $wan6_hosts)"
    fi
    printf 'LOCALNETWORK6_PREFIXES=%s\n' "$localnetwork6" >> "$desired_file"
    printf 'NODE4_ENDPOINTS=%s\nNODE6_ENDPOINTS=%s\n' "$(openkill_normalize_list "$node4")" "$(openkill_normalize_list "$node6")" >> "$desired_file"
    printf 'NATIVE_IPV6_ROUTE_MUTATIONS=0\nDNS_INTERCEPTION=1\nTUN_BACKEND=openkill\nTPROXY_BACKEND=legacy-compatible\n' >> "$desired_file"
}

openkill_snapshot_value()
{
    key="$1"; file="$2"
    while IFS= read -r line; do
        case "$line" in
            "$key="*) printf '%s\n' "${line#*=}"; return 0 ;;
        esac
    done < "$file"
}

openkill_interface_address_values()
{
    dump_file="$1"; interface_index="$2"; family="$3"
    [ -n "$interface_index" ] || return 1
    address_index=0
    while [ "$address_index" -lt 128 ]; do
        case "$family" in
            4)
                address=$(openkill_interface_json_value "$dump_file" "$interface_index" "ipv4-address[$address_index].address")
                [ -n "$address" ] || break
                openkill_valid_ipv4 "$address" && printf '%s\n' "${address%%/*}"
                ;;
            6)
                address=$(openkill_interface_json_value "$dump_file" "$interface_index" "ipv6-address[$address_index].address")
                [ -n "$address" ] || break
                mask=$(openkill_interface_json_value "$dump_file" "$interface_index" "ipv6-address[$address_index].mask")
                openkill_valid_ipv6 "$address" || {
                    address_index=$((address_index + 1))
                    continue
                }
                # netifd may expose link-local and multicast entries on an
                # external object as well. They are not usable WAN host
                # identities and must not become localnetwork6 bypasses.
                case "$address" in
                    [fF][eE]80:*|[fF][fF]*|::)
                        address_index=$((address_index + 1))
                        continue
                    ;;
                esac
                case "$mask" in
                    ''|*[!0-9]*) printf '%s\n' "${address%%/*}" ;;
                    *) [ "$mask" -le 128 ] 2>/dev/null && printf '%s/%s\n' "${address%%/*}" "$mask" ;;
                esac
                ;;
            *) return 1 ;;
        esac
        address_index=$((address_index + 1))
    done
}

openkill_interface_dns_values()
{
    dump_file="$1"; interface_index="$2"
    [ -n "$interface_index" ] || return 1
    dns_index=0
    while [ "$dns_index" -lt 64 ]; do
        dns_server=$(openkill_interface_json_value "$dump_file" "$interface_index" "dns-server[$dns_index]")
        [ -n "$dns_server" ] || break
        printf '%s\n' "$dns_server"
        dns_index=$((dns_index + 1))
    done
}

openkill_device_address_values()
{
    device="$1"; family="$2"
    [ -n "$device" ] || return 1
    case "$family" in
        4)
            ip -4 addr show dev "$device" 2>/dev/null |
                awk '$1 == "inet" && $0 !~ / scope (host|link)/ {sub("/.*", "", $2); print $2}'
            ;;
        6)
            ip -6 addr show dev "$device" 2>/dev/null |
                awk '$1 == "inet6" && $0 !~ / scope (host|link)/ {split($2, a, "/"); if (a[1] !~ /^fe80:/ && a[1] !~ /^ff/) print $2}'
            ;;
        *) return 1 ;;
    esac
}

openkill_normalize_list()
{
    [ -n "${1:-}" ] || return 0
    # Address, DNS, prefix, and endpoint fields are simple token lists.  Only
    # the semicolon is translated by tr; sed handles whitespace with its
    # regular-expression character class, and the final split is therefore
    # independent of BusyBox tr's character-set parser.  Do not use this
    # helper for free-form route text; openkill_normalize_text_lines below
    # preserves spaces inside each record.
    normalized=$(
        printf '%s\n' "$*" |
            tr ';' '\n' |
            sed -e 's/\r$//' -e '/^[[:space:]]*$/d' |
            while IFS= read -r record; do
                # These callers provide IP/CIDR/DNS tokens only.  Shell word
                # splitting is safe here and avoids another tr character-set
                # interpretation on BusyBox; free-form text uses the helper
                # below instead.
                for token in $record; do
                    printf '%s\n' "$token"
                done
            done |
            sort -u |
            tr '\n' ' '
    )
    normalized="${normalized% }"
    [ -n "$normalized" ] && printf '%s\n' "$normalized"
    return 0
}

openkill_normalize_text_lines()
{
    [ -n "${1:-}" ] || return 0
    # Native route records keep internal spaces. Ignore only data owned by the
    # transient OpenKill TUN/runtime and a dynamic kernel lifetime so the
    # semantic fingerprint remains about native network state. The raw
    # snapshot still retains every route for diagnostics.
    normalized=$(
        printf '%s\n' "$*" |
            tr ';' '\n' |
            sed -e 's/\r$//' \
                -e '/[[:space:]]dev[[:space:]]utun[[:space:]]/d' \
                -e '/[[:space:]]dev[[:space:]]utun$/d' \
                -e 's/[[:space:]][[:space:]]*expires[[:space:]][[:space:]]*[0-9][0-9]*[[:alnum:]._-]*//g' \
                -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e '/^$/d' |
            sort -u |
            tr '\n' ' '
    )
    normalized="${normalized% }"
    [ -n "$normalized" ] && printf '%s\n' "$normalized"
    return 0
}

openkill_normalize_tokens()
{
    # Snapshot list fields are already whitespace-separated tokens. Avoid the
    # delimiter parsing and two awk passes used for arbitrary user text while
    # still producing deterministic, duplicate-free output.
    normalized_tokens=$(printf '%s\n' "$@" | sort -u | tr '\n' ' ')
    printf '%s\n' "${normalized_tokens% }"
}

openkill_wan6_host_list()
{
    for address in "$@"; do
        host_address="${address%%/*}"
        openkill_valid_ipv6 "$host_address" || continue
        printf '%s/128\n' "$host_address"
    done | sort -u
}

openkill_wan6_host_addresses()
{
    snapshot_file="${OPENKILL_NETWORK_SNAPSHOT:-/tmp/openkill-network.snapshot}"
    if [ -r "$snapshot_file" ]; then
        openkill_wan6_host_list $(openkill_snapshot_value WAN6_ADDRESSES "$snapshot_file")
        return 0
    fi

    # A snapshot is normally available during startup/reconcile.  The
    # fallback still resolves the role from one netifd dump and never scans
    # every interface, which would reintroduce WAN-prefix over-bypass.
    role_file="/tmp/openkill-interface-roles.$$"
    dump_file="${OPENKILL_INTERFACE_DUMP_FILE:-/tmp/openkill-interface-dump.$$}"
    dump_owned=0
    if [ ! -r "$dump_file" ]; then
        ubus call network.interface dump > "$dump_file" 2>/dev/null || : > "$dump_file"
        dump_owned=1
    fi
    openkill_resolve_interface_roles "$dump_file" "$role_file" 2>/dev/null || :
    device=$(openkill_snapshot_value WAN6_L3_DEVICE "$role_file" 2>/dev/null || true)
    if [ -n "$device" ]; then
        ip -6 addr show dev "$device" 2>/dev/null |
            awk '$1 == "inet6" && $0 !~ / scope (host|link)/ {split($2,a,"/"); if (a[1] !~ /^fe80:/ && a[1] !~ /^ff/) print a[1]}' |
            while IFS= read -r host_address; do
                openkill_valid_ipv6 "$host_address" && printf '%s/128\n' "$host_address"
            done | sort -u
    fi
    rm -f "$role_file"
    [ "$dump_owned" -eq 1 ] && rm -f "$dump_file"
}

openkill_network_fingerprint()
{
    snapshot_file="$1"
    fingerprint_file="${2:-/tmp/openkill-network.fingerprint}"
    [ -r "$snapshot_file" ] || return 1
    tmp_file="${fingerprint_file}.tmp.$$"
    {
        printf 'WAN4_INTERFACE=%s\n' "$(openkill_snapshot_value WAN4_INTERFACE "$snapshot_file")"
        printf 'WAN4_L3_DEVICE=%s\n' "$(openkill_snapshot_value WAN4_L3_DEVICE "$snapshot_file")"
        printf 'WAN4_ADDRESSES=%s\n' "$(openkill_normalize_list "$(openkill_snapshot_value WAN4_ADDRESSES "$snapshot_file")")"
        printf 'WAN6_INTERFACE=%s\n' "$(openkill_snapshot_value WAN6_INTERFACE "$snapshot_file")"
        printf 'WAN6_L3_DEVICE=%s\n' "$(openkill_snapshot_value WAN6_L3_DEVICE "$snapshot_file")"
        printf 'WAN6_ADDRESSES=%s\n' "$(openkill_normalize_list "$(openkill_snapshot_value WAN6_ADDRESSES "$snapshot_file")")"
        printf 'NATIVE_IPV6_ROUTES=%s\n' "$(openkill_normalize_text_lines "$(openkill_snapshot_value NATIVE_IPV6_ROUTES "$snapshot_file")")"
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
    old4=$(openkill_snapshot_value WAN4_INTERFACE "$old_file")
    new4=$(openkill_snapshot_value WAN4_INTERFACE "$new_file")
    old4="$old4:$(openkill_snapshot_value WAN4_L3_DEVICE "$old_file")"
    new4="$new4:$(openkill_snapshot_value WAN4_L3_DEVICE "$new_file")"
    old4a=$(openkill_snapshot_value WAN4_ADDRESSES "$old_file")
    new4a=$(openkill_snapshot_value WAN4_ADDRESSES "$new_file")
    [ "$old4:$old4a" = "$new4:$new4a" ] || changes="$changes WAN4_CHANGED"
    old6=$(openkill_snapshot_value WAN6_INTERFACE "$old_file")
    new6=$(openkill_snapshot_value WAN6_INTERFACE "$new_file")
    old6="$old6:$(openkill_snapshot_value WAN6_L3_DEVICE "$old_file")"
    new6="$new6:$(openkill_snapshot_value WAN6_L3_DEVICE "$new_file")"
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
    # Fast path avoids two sort processes on the overwhelmingly common exact
    # no-op reconcile case.  Sorting remains for semantically equivalent files
    # whose line order differs.
    cmp -s "$old_file" "$new_file" && { printf 'NO_ACTION\n'; return 0; }
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

openkill_valid_ipv4()
{
    address="${1%%/*}"
    [ -n "$address" ] || return 1
    case "$address" in *[!0-9.]*|.*|*.|*..*) return 1 ;; esac
    old_ifs="$IFS"
    IFS=.
    set -- $address
    IFS="$old_ifs"
    [ "$#" -eq 4 ] || return 1
    for octet in "$@"; do
        case "$octet" in ''|*[!0-9]*) return 1 ;; esac
        [ "$octet" -le 255 ] 2>/dev/null || return 1
    done
}

openkill_valid_ipv6()
{
    address="${1%%/*}"
    [ -n "$address" ] || return 1
    # Validate the IPv6 shape without a subprocess. Exactly one optional ::
    # compression is allowed; every explicit hextet must contain 1..4
    # hexadecimal digits. This keeps nft batch rendering fork-free while
    # retaining the same rejection rules used by the resolver.
    case "$address" in *[!0-9A-Fa-f:]*|*[!0-9A-Fa-f:]) return 1 ;; esac
    ipv6_left=""; ipv6_right=""; ipv6_count=0
    case "$address" in
        *::* )
            case "${address#*::}" in *::*) return 1 ;; esac
            ipv6_left="${address%%::*}"
            ipv6_right="${address#*::}"
            case "$ipv6_left" in *:|:*|*::*) return 1 ;; esac
            case "$ipv6_right" in *:|:*|*::*) return 1 ;; esac
            if [ -n "$ipv6_left" ]; then
                old_ifs="$IFS"; IFS=:; set -- $ipv6_left; IFS="$old_ifs"
                for hextet in "$@"; do
                    case "$hextet" in ''|*[!0-9A-Fa-f]*) return 1 ;; esac
                    [ "${#hextet}" -le 4 ] || return 1
                    ipv6_count=$((ipv6_count + 1))
                done
            fi
            if [ -n "$ipv6_right" ]; then
                old_ifs="$IFS"; IFS=:; set -- $ipv6_right; IFS="$old_ifs"
                for hextet in "$@"; do
                    case "$hextet" in ''|*[!0-9A-Fa-f]*) return 1 ;; esac
                    [ "${#hextet}" -le 4 ] || return 1
                    ipv6_count=$((ipv6_count + 1))
                done
            fi
            [ "$ipv6_count" -lt 8 ] || return 1
            ;;
        * )
            case "$address" in :*|*:|*::*) return 1 ;; esac
            old_ifs="$IFS"; IFS=:; set -- $address; IFS="$old_ifs"
            [ "$#" -eq 8 ] || return 1
            for hextet in "$@"; do
                case "$hextet" in ''|*[!0-9A-Fa-f]*) return 1 ;; esac
                [ "${#hextet}" -le 4 ] || return 1
            done
            ;;
    esac
}

openkill_ipv6_in_cidr()
{
    address="${1%%/*}"
    query_address="$address"
    cidr_value="$2"
    network="${cidr_value%%/*}"
    prefix="${cidr_value##*/}"
    case "$prefix" in ''|*[!0-9]*) return 1 ;; esac
    [ "$prefix" -le 128 ] 2>/dev/null || return 1
    openkill_valid_ipv6 "$address" || return 1
    openkill_valid_ipv6 "$network" || return 1
    awk -v value="$query_address" -v net="$network" -v bits="$prefix" '
        function clear_array(a,    k) {
            for (k in a) delete a[k]
        }
        function part_count(part, out,    n,i,d,ch) {
            if (part == "") return 0
            n = split(part, out, ":")
            for (i = 1; i <= n; i++) {
                if (out[i] == "" || length(out[i]) > 4) return -1
                out[i] = tolower(out[i])
                for (d = 1; d <= length(out[i]); d++) {
                    ch = substr(out[i], d, 1)
                    if (index("0123456789abcdef", ch) == 0) return -1
                }
            }
            return n
        }
        function hex_value(part,    i,d,ch,total) {
            total = 0
            for (i = 1; i <= length(part); i++) {
                ch = substr(part, i, 1)
                d = index("0123456789abcdef", ch) - 1
                if (d < 0) return -1
                total = total * 16 + d
            }
            return total
        }
        function parse_ipv6(text, out,    first,left,right,left_n,right_n,i,j,pos) {
            clear_array(out)
            first = index(text, "::")
            if (first) {
                if (index(substr(text, first + 2), "::")) return 0
                left = substr(text, 1, first - 1)
                right = substr(text, first + 2)
                left_n = part_count(left, left_parts)
                right_n = part_count(right, right_parts)
                if (left_n < 0 || right_n < 0 || left_n + right_n >= 8) return 0
                pos = 1
                for (i = 1; i <= left_n; i++) out[pos++] = hex_value(left_parts[i])
                for (i = left_n + right_n + 1; i <= 8; i++) out[pos++] = 0
                for (j = 1; j <= right_n; j++) out[pos++] = hex_value(right_parts[j])
            } else {
                count = part_count(text, plain_parts)
                if (count != 8) return 0
                for (i = 1; i <= 8; i++) out[i] = hex_value(plain_parts[i])
            }
            return 1
        }
        BEGIN {
            if (!parse_ipv6(value, address_parts) || !parse_ipv6(net, network_parts)) exit 1
            remaining = bits + 0
            i = 1
            while (i <= 8 && remaining >= 16) {
                if (address_parts[i] != network_parts[i]) exit 1
                i++
                remaining -= 16
            }
            if (remaining > 0) {
                divisor = 2 ^ (16 - remaining)
                if (int(address_parts[i] / divisor) != int(network_parts[i] / divisor)) exit 1
            }
            exit 0
        }'
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
                *:*) openkill_valid_ipv6 "$endpoint" && printf '%s\n' "$endpoint" >> "$v6_file" ;;
                ''|*[!0-9.]*) printf '%s\n' "$endpoint" >> "$domain_file" ;;
                *) openkill_valid_ipv4 "$endpoint" && printf '%s\n' "$endpoint" >> "$v4_file" ;;
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
    command -v timeout >/dev/null 2>&1 || return 1
    resolved=0
    resolution_failed=0

    openkill_node_dns_servers() {
        dns_value="${OPENKILL_NODE_DNS_SERVERS:-}"
        if [ -z "$dns_value" ]; then
            dns_snapshot="${OPENKILL_NETWORK_SNAPSHOT:-/tmp/openkill-network.snapshot}"
            [ -r "$dns_snapshot" ] && dns_value=$(openkill_snapshot_value DNS_SERVERS "$dns_snapshot")
        fi
        if [ -z "$dns_value" ]; then
            for resolv_file in /tmp/resolv.conf.d/resolv.conf.auto /tmp/resolv.conf.auto /etc/resolv.conf; do
                [ -r "$resolv_file" ] || continue
                dns_value="$dns_value $(awk '$1 == "nameserver" {print $2}' "$resolv_file")"
            done
        fi
        for server in $dns_value; do
            case "$server" in
                127.*|0.0.0.0|::1|0:0:0:0:0:0:0:1) continue ;;
            esac
            printf '%s\n' "$server"
        done | sort -u
    }

    openkill_node4_is_fake() {
        node_address="$1"
        fake_range="${OPENKILL_FAKEIP_RANGE4:-}"
        [ -n "$fake_range" ] || fake_range=$(uci -q get openkill.config.fakeip_range 2>/dev/null || true)
        # Mihomo's common fake-ip defaults include both /16 and /15 forms.
        case "$fake_range" in
            ""|0) fake_range="198.18.0.0/15" ;;
        esac
        fake_network="${fake_range%%/*}"
        fake_prefix_length="${fake_range##*/}"
        case "$fake_prefix_length" in ''|*[!0-9]*) return 1 ;; esac
        # Compare IPv4 values as integers so configured /15, /10, and other
        # non-default fake-ip ranges are filtered without a new dependency.
        awk -F. -v address="$node_address" -v network="$fake_network" -v prefix="$fake_prefix_length" '
            function value(s, a) {
                if (split(s, a, ".") != 4) return -1
                return (((a[1] * 256 + a[2]) * 256 + a[3]) * 256 + a[4])
            }
            BEGIN {
                addr = value(address, aa); net = value(network, nn)
                if (addr < 0 || net < 0 || prefix < 0 || prefix > 32) exit 1
                if (prefix == 0) exit 0
                block = 2 ^ (32 - prefix)
                exit ((addr - (addr % block)) == (net - (net % block)) ? 0 : 1)
            }'
    }

    openkill_node6_is_fake() {
        node_address=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
        fake_range="${OPENKILL_FAKEIP_RANGE6:-}"
        [ -n "$fake_range" ] || fake_range=$(uci -q get openkill.config.fakeip_range6 2>/dev/null || true)
        [ -n "$fake_range" ] || fake_range="fdfe:dcba:9876::/64"
        openkill_ipv6_in_cidr "$node_address" "$fake_range"
    }

    openkill_append_node4() {
        node_address="$1"
        openkill_valid_ipv4 "$node_address" || return 1
        # A filtered Fake-IP is not a successful resolution.  Returning a
        # failure status here prevents the caller from treating an empty
        # endpoint set as a valid refresh.
        if openkill_node4_is_fake "$node_address"; then return 1; fi
        printf '%s\n' "$node_address" >> "$v4_file"
        resolved=1
    }
    openkill_append_node6() {
        node_address="$1"
        openkill_valid_ipv6 "$node_address" || return 1
        if openkill_node6_is_fake "$node_address"; then return 1; fi
        printf '%s\n' "$node_address" >> "$v6_file"
        resolved=1
    }

    dns_servers=$(openkill_node_dns_servers)
    while IFS= read -r domain; do
        [ -n "$domain" ] || continue
        domain_resolved=0
        if command -v nslookup >/dev/null 2>&1; then
            for server in $dns_servers; do
                v4_result=$(timeout "${OPENKILL_NODE_RESOLVE_TIMEOUT:-5}" nslookup -type=A "$domain" "$server" 2>/dev/null |
                    awk 'seen {for (i=1;i<=NF;i++) if ($i ~ /^[0-9]+(\.[0-9]+){3}$/) print $i} /^Name:/{seen=1}')
                v6_result=$(timeout "${OPENKILL_NODE_RESOLVE_TIMEOUT:-5}" nslookup -type=AAAA "$domain" "$server" 2>/dev/null |
                    awk 'seen {for (i=1;i<=NF;i++) if ($i ~ /^[0-9A-Fa-f:]+$/ && $i ~ /:/) print $i} /^Name:/{seen=1}')
                for node_address in $v4_result; do
                    openkill_append_node4 "$node_address" && domain_resolved=1
                done
                for node_address in $v6_result; do
                    openkill_append_node6 "$node_address" && domain_resolved=1
                done
                # Keep checking the remaining native resolvers so an A-only
                # answer from one server can still be paired with an AAAA
                # answer from another.  The endpoint files are deduplicated
                # below, so this does not accumulate duplicates.
            done
        fi
        # resolveip is present on a number of BusyBox/OpenWrt images and is a
        # safer native fallback than routing through client Fake-IP DNS.
        if [ "$domain_resolved" -eq 0 ] && [ -n "$dns_servers" ] && command -v resolveip >/dev/null 2>&1; then
            v4_result=$(timeout "${OPENKILL_NODE_RESOLVE_TIMEOUT:-5}" resolveip -4 "$domain" 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i ~ /^[0-9]+(\.[0-9]+){3}$/) print $i}')
            v6_result=$(timeout "${OPENKILL_NODE_RESOLVE_TIMEOUT:-5}" resolveip -6 "$domain" 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i ~ /^[0-9A-Fa-f:]+$/ && $i ~ /:/) print $i}')
            for node_address in $v4_result; do
                openkill_append_node4 "$node_address" && domain_resolved=1
            done
            for node_address in $v6_result; do
                openkill_append_node6 "$node_address" && domain_resolved=1
            done
        fi
        # getent is optional: retain compatibility where it exists, but never
        # make it a hard dependency on BusyBox systems that omit it.
        if [ "$domain_resolved" -eq 0 ] && [ -n "$dns_servers" ] && command -v getent >/dev/null 2>&1; then
            v4_result=$(timeout "${OPENKILL_NODE_RESOLVE_TIMEOUT:-5}" getent ahostsv4 "$domain" 2>/dev/null | awk '$1 ~ /^[0-9]+(\.[0-9]+){3}$/ {print $1}')
            v6_result=$(timeout "${OPENKILL_NODE_RESOLVE_TIMEOUT:-5}" getent ahostsv6 "$domain" 2>/dev/null | awk '$1 ~ /^[0-9A-Fa-f:]+$/ && $1 ~ /:/ {print $1}')
            for node_address in $v4_result; do
                openkill_append_node4 "$node_address" && domain_resolved=1
            done
            for node_address in $v6_result; do
                openkill_append_node6 "$node_address" && domain_resolved=1
            done
        fi
        [ "$domain_resolved" -eq 1 ] || resolution_failed=1
    done < "$domain_file"
    sort -u "$v4_file" -o "$v4_file"; sort -u "$v6_file" -o "$v6_file"
    [ "$resolution_failed" -eq 0 ] && [ "$resolved" -eq 1 ]
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
        if [ -r "$applied4" ] && [ -r "$applied6" ]; then
            return 1
        fi
        # On first start there may be no previous dynamic set. Static literal
        # endpoints remain safe to apply even when every domain lookup fails.
        cp "$static4" "$applied4" && cp "$static6" "$applied6" || return 1
        return 0
    fi
    sort -u "$tmp4" -o "$tmp4"; sort -u "$tmp6" -o "$tmp6"
    mv "$tmp4" "$applied4" && mv "$tmp6" "$applied6"
}

openkill_node_underlay_ready_for_noop()
{
    # Literal-only node sets are covered by the configuration fingerprint. A
    # domain endpoint can change while the generated YAML remains identical,
    # so refresh it into temporary files before accepting a no-op reconcile.
    domains_file="${1:-/tmp/openkill-node-domains}"
    static4_file="${2:-/tmp/openkill-node4.static}"
    static6_file="${3:-/tmp/openkill-node6.static}"
    applied4_file="${4:-/tmp/openkill-node4.desired}"
    applied6_file="${5:-/tmp/openkill-node6.desired}"
    [ -s "$domains_file" ] || return 0
    [ -r "$static4_file" ] && [ -r "$static6_file" ] || return 1
    [ -r "$applied4_file" ] && [ -r "$applied6_file" ] || return 1
    noop4="${applied4_file}.noop.$$"; noop6="${applied6_file}.noop.$$"
    cp "$static4_file" "$noop4" && cp "$static6_file" "$noop6" || {
        rm -f "$noop4" "$noop6"
        return 1
    }
    if ! openkill_resolve_node_domains "$domains_file" "$noop4" "$noop6"; then
        rm -f "$noop4" "$noop6"
        return 1
    fi
    result=1
    cmp -s "$noop4" "$applied4_file" && cmp -s "$noop6" "$applied6_file" && result=0
    rm -f "$noop4" "$noop6"
    return "$result"
}

openkill_render_node_sets()
{
    v4_file="$1"; v6_file="$2"; output_file="${3:-/tmp/openkill-node-sets.nft}"
    [ -r "$v4_file" ] && [ -r "$v6_file" ] || return 1
    tmp_file="${output_file}.tmp.$$"
    {
        printf 'add set inet fw4 openkill_node4 { type ipv4_addr; flags interval; auto-merge; }\n'
        printf 'add set inet fw4 openkill_node6 { type ipv6_addr; flags interval; auto-merge; }\n'
        while IFS= read -r endpoint; do openkill_valid_ipv4 "$endpoint" && printf 'add element inet fw4 openkill_node4 { %s }\n' "$endpoint"; done < "$v4_file"
        while IFS= read -r endpoint; do openkill_valid_ipv6 "$endpoint" && printf 'add element inet fw4 openkill_node6 { %s }\n' "$endpoint"; done < "$v6_file"
    } > "$tmp_file" && mv "$tmp_file" "$output_file"
}

# Render only OpenKill-owned dynamic set contents.  The transaction is safe to
# apply after the sets have been created and never flushes fw4 or native state.
openkill_render_nft_set_batch()
{
    v4_file="$1"; v6_file="$2"; output_file="${3:-/tmp/openkill-node-sets.batch}"
    [ -r "$v4_file" ] && [ -r "$v6_file" ] || return 1
    tmp_file="${output_file}.tmp.$$"
    {
        printf 'flush set inet fw4 openkill_node4\n'
        printf 'flush set inet fw4 openkill_node6\n'
        while IFS= read -r endpoint; do
            openkill_valid_ipv4 "$endpoint" && printf 'add element inet fw4 openkill_node4 { %s }\n' "$endpoint"
        done < "$v4_file"
        while IFS= read -r endpoint; do
            openkill_valid_ipv6 "$endpoint" && printf 'add element inet fw4 openkill_node6 { %s }\n' "$endpoint"
        done < "$v6_file"
    } > "$tmp_file" && mv "$tmp_file" "$output_file"
}

openkill_render_nft_set_update_batch()
{
    family="$1"; set_name="$2"; elements_file="$3"; output_file="${4:-/tmp/openkill-set-update.batch}"
    [ -r "$elements_file" ] || return 1
    case "$family" in 4) address_type=ipv4_addr ;; 6) address_type=ipv6_addr ;; *) return 1 ;; esac
    tmp_file="${output_file}.tmp.$$"
    {
        printf 'flush set inet fw4 %s\n' "$set_name"
        while IFS= read -r element; do
            [ -n "$element" ] && printf 'add element inet fw4 %s { %s }\n' "$set_name" "$element"
        done < "$elements_file"
    } > "$tmp_file" && mv "$tmp_file" "$output_file"
}

openkill_validate_nft_batch()
{
    batch_file="$1"
    [ -r "$batch_file" ] || return 1
    ! grep -Eq 'flush ruleset|flush table inet fw4|delete table inet fw4' "$batch_file" || return 1
    if command -v nft >/dev/null 2>&1 && [ "${OPENKILL_NFT_VALIDATE:-1}" = 1 ]; then
        nft -c -f "$batch_file" >/dev/null 2>&1 || return 1
    fi
}

openkill_replace_if_changed()
{
    new_file="$1"; current_file="$2"
    cmp -s "$new_file" "$current_file" 2>/dev/null && return 1
    tmp_file="${current_file}.tmp.$$"
    cp "$new_file" "$tmp_file" && mv "$tmp_file" "$current_file"
}

openkill_render_classifier_order()
{
    # Shared semantic order consumed by nft and legacy backends.
    printf '%s\n' CONTROL_BYPASS SELF_BYPASS NODE_BYPASS LOCAL_BYPASS USER_BYPASS CHINA_DIRECT USER_PROXY DEFAULT_POLICY
}

openkill_classifier_match()
{
    family="$1"; role="$2"
    case "$family:$role" in
        4:NODE_BYPASS) printf 'ip daddr @openkill_node4 counter return' ;;
        6:NODE_BYPASS) printf 'ip6 daddr @openkill_node6 counter return' ;;
        *) return 1 ;;
    esac
}

openkill_nft_string_quote()
{
    # nft parses strings inside its command language.  Keep the quotes in the
    # rendered command so shell word splitting can never turn a comment into
    # multiple nft arguments or allow embedded quotes to terminate the value.
    value="$1"
    escaped=$(printf '%s' "$value" | sed 's/\\/\\\\/g; s/"/\\"/g')
    printf '"%s"' "$escaped"
}

openkill_render_classifier_rule()
{
    family="$1"; chain="$2"; comment="${3:-OpenKill node underlay}"
    match=$(openkill_classifier_match "$family" NODE_BYPASS) || return 1
    printf 'insert rule inet fw4 %s %s comment %s\n' \
        "$chain" "$match" "$(openkill_nft_string_quote "$comment")"
}

openkill_render_dns_set_rules()
{
    family="$1"; domains_file="$2"; target_set="$3"; output_file="$4"; backend="${5:-nftset}"
    [ -r "$domains_file" ] || return 1
    tmp_file="${output_file}.tmp.$$"
    case "$family:$backend" in
        4:nftset) prefix="nftset=/"; suffix="/4#inet#fw4#$target_set" ;;
        6:nftset) prefix="nftset=/"; suffix="/6#inet#fw4#$target_set" ;;
        4:ipset|6:ipset) prefix="ipset=/"; suffix="/$target_set" ;;
        *) return 1 ;;
    esac
    awk 'NF && $0 !~ /^[[:space:]]*#/ {gsub(/[[:space:]]+/, "", $0); if ($0 ~ /[A-Za-z0-9-]+\.[A-Za-z]{2,}$/) print}' "$domains_file" |
        sort -u | awk -v p="$prefix" -v s="$suffix" '{print p $0 s}' > "$tmp_file" || return 1
    mv "$tmp_file" "$output_file"
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

openkill_minimal_apply_action()
{
    desired_file="$1"; applied_file="$2"; runtime_file="$3"
    [ -r "$desired_file" ] && [ -r "$applied_file" ] && [ -r "$runtime_file" ] || return 1
    owner=$(openkill_snapshot_value TUN_OWNER "$desired_file")
    chain_present=$(openkill_snapshot_value NFT_CHAIN_PRESENT "$runtime_file")
    [ "$owner" = openkill ] && [ "$chain_present" != 1 ] && { printf 'REAPPLY_NFT\n'; return 0; }
    cmp -s "$desired_file" "$applied_file" && { printf 'NO_ACTION\n'; return 0; }
    [ "$(openkill_snapshot_value LOCALNETWORK6_PREFIXES "$desired_file")" != "$(openkill_snapshot_value LOCALNETWORK6_PREFIXES "$applied_file")" ] && printf 'LOCAL6_CHANGED\n'
    [ "$(openkill_snapshot_value NODE4_ENDPOINTS "$desired_file")" != "$(openkill_snapshot_value NODE4_ENDPOINTS "$applied_file")" ] && printf 'NODE4_CHANGED\n'
    [ "$(openkill_snapshot_value NODE6_ENDPOINTS "$desired_file")" != "$(openkill_snapshot_value NODE6_ENDPOINTS "$applied_file")" ] && printf 'NODE6_CHANGED\n'
}

openkill_commit_applied_network_state()
{
    desired_file="$1"
    applied_file="${2:-/tmp/openkill-network.applied}"
    config_file="${3:-}"
    config_applied_file="${4:-/tmp/openkill-config.applied}"
    [ -r "$desired_file" ] || return 1
    applied_tmp="${applied_file}.tmp.$$"
    config_tmp=""
    cp "$desired_file" "$applied_tmp" || {
        rm -f "$applied_tmp"
        return 1
    }
    if [ -n "$config_file" ] && [ -r "$config_file" ]; then
        config_tmp="${config_applied_file}.tmp.$$"
        cp "$config_file" "$config_tmp" || {
            rm -f "$applied_tmp" "$config_tmp"
            return 1
        }
    fi
    mv "$applied_tmp" "$applied_file" || {
        rm -f "$applied_tmp" "$config_tmp"
        return 1
    }
    if [ -n "$config_tmp" ]; then
        mv "$config_tmp" "$config_applied_file" || {
            rm -f "$config_tmp"
            return 1
        }
    fi
}

openkill_commit_network_snapshot()
{
    snapshot_file="$1"
    applied_file="${2:-/tmp/openkill-network.snapshot}"
    [ -r "$snapshot_file" ] || return 1
    snapshot_tmp="${applied_file}.tmp.$$"
    cp "$snapshot_file" "$snapshot_tmp" || {
        rm -f "$snapshot_tmp"
        return 1
    }
    mv "$snapshot_tmp" "$applied_file" || {
        rm -f "$snapshot_tmp"
        return 1
    }
}

openkill_network_noop_ready()
{
    desired_file="$1"; applied_file="${2:-/tmp/openkill-network.applied}"
    runtime_file="${3:-}"; config_file="${4:-}"; config_applied_file="${5:-/tmp/openkill-config.applied}"
    fingerprint_file="${6:-}"; fingerprint_applied_file="${7:-/tmp/openkill-network.fingerprint}"
    [ -r "$desired_file" ] && [ -r "$applied_file" ] || return 1
    cmp -s "$desired_file" "$applied_file" || return 1
    if [ -n "$config_file" ]; then
        [ -r "$config_file" ] && [ -r "$config_applied_file" ] || return 1
        cmp -s "$config_file" "$config_applied_file" || return 1
    fi
    # A WAN/device change can leave the high-level desired sets unchanged but
    # still require route reconciliation.  Treat the normalized native
    # fingerprint as part of the no-op contract when the caller provides one.
    if [ -n "$fingerprint_file" ]; then
        [ -r "$fingerprint_file" ] && [ -r "$fingerprint_applied_file" ] || return 1
        cmp -s "$fingerprint_file" "$fingerprint_applied_file" || return 1
    fi
    # The production caller performs the runtime checks once and supplies this
    # result. Fixtures can expose the same contract without system commands.
    if [ "${OPENKILL_RUNTIME_HEALTHY:-0}" = 1 ]; then
        printf 'NO_ACTION\n'
        return 0
    fi
    if [ -n "$runtime_file" ] && [ "$(openkill_snapshot_value RUNTIME_HEALTHY "$runtime_file")" = 1 ]; then
        printf 'NO_ACTION\n'
        return 0
    fi
    return 1
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
