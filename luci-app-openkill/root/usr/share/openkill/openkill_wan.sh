#!/bin/sh
# Resolve the physical OpenWrt WAN device without selecting a tunnel or
# overlay interface. Mihomo uses this device for bootstrap DNS and node DNS.

# The init script sources this helper before the shared snapshot helper, while
# yml_change.sh uses it on its own. Load the role functions lazily so both
# entry points can resolve custom/uppercase netifd interface names without a
# second implementation. No command is run while the file is sourced.
if ! command -v openkill_resolve_interface_roles >/dev/null 2>&1; then
    for network_helper in \
        "${IPKG_INSTROOT:-}/usr/share/openkill/openkill_network.sh" \
        /usr/share/openkill/openkill_network.sh; do
        [ -r "$network_helper" ] || continue
        . "$network_helper"
        command -v openkill_resolve_interface_roles >/dev/null 2>&1 && break
    done
fi

openkill_wan_interface()
{
    local candidate candidate4 candidate6 mode fixed role_file dump_file dump_owned role_snapshot
    mode="$(uci -q get openkill.config.wan_interface_mode 2>/dev/null || echo auto)"
    fixed=""
    if [ "$mode" = "fixed" ]; then
        fixed="$(uci -q get openkill.config.wan_interface_name 2>/dev/null || true)"
    fi

    # Prefer the normalized role selected from one netifd dump. The startup
    # snapshot is used when available; before the first snapshot, collect one
    # temporary dump so uppercase WAN/WAN6 and custom logical names work during
    # the WAN readiness gate as well.
    candidate4=""
    candidate6=""
    if command -v openkill_resolve_interface_roles >/dev/null 2>&1; then
        role_snapshot="${OPENKILL_NETWORK_SNAPSHOT:-/tmp/openkill-network.snapshot}"
        if [ -r "$role_snapshot" ] && command -v openkill_snapshot_value >/dev/null 2>&1; then
            candidate4="$(openkill_snapshot_value WAN4_L3_DEVICE "$role_snapshot" 2>/dev/null || true)"
            candidate6="$(openkill_snapshot_value WAN6_L3_DEVICE "$role_snapshot" 2>/dev/null || true)"
        else
            role_file="/tmp/openkill-wan-roles.$$"
            dump_file="${OPENKILL_INTERFACE_DUMP_FILE:-/tmp/openkill-wan-dump.$$}"
            dump_owned=0
            if [ ! -r "$dump_file" ]; then
                ubus call network.interface dump > "$dump_file" 2>/dev/null || : > "$dump_file"
                dump_owned=1
            fi
            openkill_resolve_interface_roles "$dump_file" "$role_file" 2>/dev/null || :
            candidate4="$(openkill_snapshot_value WAN4_L3_DEVICE "$role_file" 2>/dev/null || true)"
            candidate6="$(openkill_snapshot_value WAN6_L3_DEVICE "$role_file" 2>/dev/null || true)"
            rm -f "$role_file"
            [ "$dump_owned" -eq 1 ] && rm -f "$dump_file"
        fi
    fi
    for candidate in "$fixed" "$candidate4" "$candidate6"; do
        [ -n "$candidate" ] || continue
        case "$candidate" in
            tun*|utun*|zt*|tailscale*|docker*) continue ;;
        esac
        if ip link show dev "$candidate" >/dev/null 2>&1 &&
           { ip route show default dev "$candidate" 2>/dev/null; ip -6 route show default dev "$candidate" 2>/dev/null; } | grep -q .; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    for candidate in \
        "$fixed" \
        "$(/usr/share/openkill/openkill_get_network.lua pppoe 2>/dev/null | awk 'NF { print; exit }')" \
        "$(/usr/share/openkill/openkill_get_network.lua dhcp 2>/dev/null | awk 'NF { print; exit }')"; do
        [ -n "$candidate" ] || continue
        case "$candidate" in
            tun*|utun*|zt*|tailscale*|docker*) continue ;;
        esac
        if ip link show dev "$candidate" >/dev/null 2>&1 &&
           { ip route show default dev "$candidate" 2>/dev/null; ip -6 route show default dev "$candidate" 2>/dev/null; } | grep -q .; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    ip -4 route show default 2>/dev/null | awk '
        { for (i = 1; i <= NF; i++) if ($i == "dev") {
            d = $(i + 1)
            if (d !~ /^(tun|utun|zt|tailscale|docker)/) { print d; exit }
        }}'
}

openkill_wan_ready()
{
    local iface
    iface="$(openkill_wan_interface)"
    [ -n "$iface" ] || return 1
    ip link show dev "$iface" >/dev/null 2>&1 || return 1
    { ip route show default dev "$iface" 2>/dev/null; ip -6 route show default dev "$iface" 2>/dev/null; } | grep -q .
}

openkill_wait_wan()
{
    local attempts="${1:-30}"
    while [ "$attempts" -gt 0 ]; do
        openkill_wan_ready && return 0
        attempts=$((attempts - 1))
        sleep 1
    done
    return 1
}
