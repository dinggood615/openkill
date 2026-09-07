#!/bin/sh
# Resolve the physical OpenWrt WAN device without selecting a tunnel or
# overlay interface. Mihomo uses this device for bootstrap DNS and node DNS.

openkill_wan_interface()
{
    local candidate mode fixed
    mode="$(uci -q get openkill.config.wan_interface_mode 2>/dev/null || echo auto)"
    fixed=""
    if [ "$mode" = "fixed" ]; then
        fixed="$(uci -q get openkill.config.wan_interface_name 2>/dev/null || true)"
    fi
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
