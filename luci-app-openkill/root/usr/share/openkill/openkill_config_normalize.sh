#!/bin/sh
# Normalize legacy UCI values before any YAML generation.  This is deliberately
# idempotent: it only writes when a value is missing or unsafe.
. /lib/functions.sh
. /usr/share/openkill/uci.sh

changed=0
set_default() {
    local key="$1" value="$2" current
    current="$(uci -q get openkill.config."$key" 2>/dev/null || true)"
    if [ -z "$current" ] || [ "$current" = "0" ] && [ "$key" = "en_mode" ]; then
        uci -q set openkill.config."$key"="$value"
        changed=1
    fi
}

set_default en_mode fake-ip
set_default proxy_mode rule
set_default find_process_mode off
set_default geodata_loader memconservative
set_default enable_tcp_concurrent 1
set_default enable_unified_delay 1
set_default disable_udp_quic 0

# TUN ownership is a single mutually-exclusive mode.  Older installations
# only have the two boolean-ish legacy fields.  Preserve the one unambiguous
# legacy choice (both values explicitly enabled means Mihomo-native); every
# other combination migrates to the safe OpenKill-owned path instead of
# allowing a split owner.  The old values remain as compatibility fields, but
# are derived from tun_owner below and are never user-controlled afterwards.
tun_owner="$(uci -q get openkill.config.tun_owner 2>/dev/null || true)"
if [ "$tun_owner" != "openkill" ] && [ "$tun_owner" != "mihomo" ]; then
    legacy_route="$(uci -q get openkill.config.tun_auto_route 2>/dev/null || true)"
    legacy_redirect="$(uci -q get openkill.config.tun_auto_redirect 2>/dev/null || true)"
    if [ "$legacy_route" = "1" ] && [ "$legacy_redirect" = "1" ]; then
        tun_owner=mihomo
    else
        tun_owner=openkill
    fi
    uci -q set openkill.config.tun_owner="$tun_owner"
    changed=1
fi
if [ "$tun_owner" = "mihomo" ]; then
    desired_route=1
    desired_redirect=1
else
    desired_route=0
    desired_redirect=0
fi
if [ "$(uci -q get openkill.config.tun_auto_route 2>/dev/null || true)" != "$desired_route" ]; then
    uci -q set openkill.config.tun_auto_route="$desired_route"
    changed=1
fi
if [ "$(uci -q get openkill.config.tun_auto_redirect 2>/dev/null || true)" != "$desired_redirect" ]; then
    uci -q set openkill.config.tun_auto_redirect="$desired_redirect"
    changed=1
fi
set_default tun_auto_detect_interface 1
set_default tun_strict_route 0
set_default tun_endpoint_independent_nat 0
set_default dashboard_bind_address lan
set_default dns_listen_address 127.0.0.1
set_default cn_port 9090

bind="$(uci -q get openkill.config.dashboard_bind_address 2>/dev/null || echo lan)"
case "$bind" in lan|*.*.*.*|\[*\]|*:* ) ;; *) uci -q set openkill.config.dashboard_bind_address=lan; changed=1 ;; esac
dns_bind="$(uci -q get openkill.config.dns_listen_address 2>/dev/null || echo 127.0.0.1)"
case "$dns_bind" in *.*.*.*|\[*\]|*:* ) ;; *) uci -q set openkill.config.dns_listen_address=127.0.0.1; changed=1 ;; esac

ipv6_enable="$(uci -q get openkill.config.ipv6_enable 2>/dev/null || echo 0)"
if [ "$ipv6_enable" != 1 ]; then
    for key in ipv6_mode enable_v6_udp_proxy ipv6_dns; do
        value="$(uci -q get openkill.config."$key" 2>/dev/null || true)"
        if [ -n "$value" ] && [ "$value" != 0 ]; then
            uci -q set openkill.config."$key"=0
            changed=1
        fi
    done
fi

# A deleted panel must never remain selected.  Pick the first installed panel
# so the status page can always provide a valid dashboard URL.
panel="$(uci -q get openkill.config.default_dashboard 2>/dev/null || true)"
if [ -z "$panel" ] || [ ! -d "/usr/share/openkill/ui/$panel" ]; then
    for panel in metacubexd zashboard yacd dashboard; do
        if [ -d "/usr/share/openkill/ui/$panel" ]; then
            uci -q set openkill.config.default_dashboard="$panel"
            changed=1
            break
        fi
    done
fi

if [ "$changed" = 1 ]; then
    uci -q commit openkill
fi
exit 0
