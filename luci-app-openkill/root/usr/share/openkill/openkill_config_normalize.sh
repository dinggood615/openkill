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
set_default tun_auto_detect_interface 0
set_default tun_strict_route 0
set_default tun_endpoint_independent_nat 0
set_default dashboard_bind_address lan
set_default dns_listen_address 127.0.0.1
set_default cn_port 9090
set_default wan_interface_mode auto
set_default remote_service_bypass 0
set_default compatibility_fallback 0

compatibility_profile="$(uci -q get openkill.config.compatibility_profile 2>/dev/null || true)"
if [ -z "$compatibility_profile" ]; then
    # Preserve an explicitly selected native owner from older releases while
    # giving all other legacy installations the safer OpenKill-owned default.
    if [ "$tun_owner" = "mihomo" ]; then
        compatibility_profile=native
    else
        compatibility_profile=stable
    fi
    uci -q set openkill.config.compatibility_profile="$compatibility_profile"
    changed=1
fi
case "$compatibility_profile" in
    stable|performance|native) ;;
    *) compatibility_profile=stable; uci -q set openkill.config.compatibility_profile=stable; changed=1 ;;
esac
case "$compatibility_profile" in
    native)
        if [ "$tun_owner" != "mihomo" ]; then
            tun_owner=mihomo
            uci -q set openkill.config.tun_owner=mihomo
            changed=1
        fi
        ;;
    stable|performance)
        if [ "$tun_owner" != "openkill" ]; then
            tun_owner=openkill
            uci -q set openkill.config.tun_owner=openkill
            changed=1
        fi
        ;;
esac

# The high-performance dual-stack profile remains OpenKill-owned, but applies
# only safe Mihomo performance defaults.  It intentionally does not enable
# IPv6, force QUIC, or change the user's routing policy: those choices depend
# on the ISP and are kept in their dedicated settings.  Standard Geo loading
# uses more memory, so stable mode remains the low-memory default.
if [ "$compatibility_profile" = "performance" ]; then
    for key in enable_tcp_concurrent enable_unified_delay; do
        if [ "$(uci -q get openkill.config."$key" 2>/dev/null || true)" != "1" ]; then
            uci -q set openkill.config."$key"=1
            changed=1
        fi
    done
    if [ "$(uci -q get openkill.config.geodata_loader 2>/dev/null || true)" != "standard" ]; then
        uci -q set openkill.config.geodata_loader=standard
        changed=1
    fi
    for key in tun_strict_route tun_endpoint_independent_nat; do
        if [ "$(uci -q get openkill.config."$key" 2>/dev/null || true)" != "0" ]; then
            uci -q set openkill.config."$key"=0
            changed=1
        fi
    done
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

# One-time migration for installations created before the centralized
# compatibility page. The old broad service-port bypass and automatic TUN
# interface probing are unsafe defaults in an OpenVPN/PPPoE dual-stack setup.
# Users can re-enable an option explicitly after the migration.
compat_migration="$(uci -q get openkill.config.compat_migration_version 2>/dev/null || true)"
if [ "$compat_migration" != "2026-1108" ]; then
    uci -q set openkill.config.remote_service_bypass=0
    if [ "$compatibility_profile" = "native" ]; then
        uci -q set openkill.config.tun_auto_detect_interface=1
    else
        uci -q set openkill.config.tun_auto_detect_interface=0
    fi
    uci -q set openkill.config.compat_migration_version=2026-1108
    changed=1
fi

# Remove settings that only belonged to the retired Smart/LightGBM and
# oixCloud integrations. This is a one-time, idempotent UCI migration: the
# YAML migration above still handles legacy Smart groups, while no obsolete
# switches remain in the active runtime configuration or LuCI form.
legacy_cleanup_version="$(uci -q get openkill.config.feature_cleanup_version 2>/dev/null || true)"
if [ "$legacy_cleanup_version" != "2026-1109" ]; then
    legacy_keys="smart_enable auto_smart_switch smart_policy_priority smart_prefer_asn smart_enable_lgbm smart_collect smart_collect_size smart_collect_rate smart_tolerance lgbm_auto_update lgbm_custom_url lgbm_update_interval"
    cleanup_legacy_section() {
        local section="$1" key
        for key in $legacy_keys; do
            if uci -q get "openkill.${section}.${key}" >/dev/null 2>&1; then
                uci -q delete "openkill.${section}.${key}"
                changed=1
            fi
        done
    }
    cleanup_legacy_section config
    config_load openkill
    config_foreach cleanup_legacy_section config_overwrite
    uci -q set openkill.config.feature_cleanup_version=2026-1109
    changed=1
fi

# OpenKill-owned mode already controls routes and firewall rules. Bind the
# generated profile to the physical WAN instead of letting Mihomo select a
# tunnel after OpenVPN/PPPoE changes. Native ownership keeps auto detection.
if [ "$tun_owner" = "openkill" ] && [ "$(uci -q get openkill.config.tun_auto_detect_interface 2>/dev/null || true)" != "0" ]; then
    uci -q set openkill.config.tun_auto_detect_interface=0
    changed=1
elif [ "$tun_owner" = "mihomo" ] && [ "$(uci -q get openkill.config.tun_auto_detect_interface 2>/dev/null || true)" != "1" ]; then
    uci -q set openkill.config.tun_auto_detect_interface=1
    changed=1
fi

bind="$(uci -q get openkill.config.dashboard_bind_address 2>/dev/null || echo lan)"
case "$bind" in lan|*.*.*.*|\[*\]|*:* ) ;; *) uci -q set openkill.config.dashboard_bind_address=lan; changed=1 ;; esac
dns_bind="$(uci -q get openkill.config.dns_listen_address 2>/dev/null || echo 127.0.0.1)"
case "$dns_bind" in *.*.*.*|\[*\]|*:* ) ;; *) uci -q set openkill.config.dns_listen_address=127.0.0.1; changed=1 ;; esac

ipv6_enable="$(uci -q get openkill.config.ipv6_enable 2>/dev/null || echo 0)"
if [ "$ipv6_enable" != 1 ]; then
    # IPv6 traffic interception is subordinate to the master switch, but
    # IPv6 DNS resolution is intentionally independent.  This lets users
    # request AAAA records while keeping the router's IPv6 forwarding path
    # outside OpenKill (useful while an ISP's native IPv6 TCP path is being
    # repaired).  The old loop also cleared ipv6_dns and made the LuCI flag
    # appear to toggle itself off after every restart.
    for key in ipv6_mode enable_v6_udp_proxy; do
        value="$(uci -q get openkill.config."$key" 2>/dev/null || true)"
        if [ -n "$value" ] && [ "$value" != 0 ]; then
            uci -q set openkill.config."$key"=0
            changed=1
        fi
    done
fi

# Keep the independent DNS flag a strict boolean without tying it to the
# IPv6 firewall/TUN owner.  Mihomo treats dns.ipv6 as the AAAA-answer switch;
# top-level ipv6 controls traffic handling and they are not the same setting.
ipv6_dns="$(uci -q get openkill.config.ipv6_dns 2>/dev/null || echo 0)"
case "$ipv6_dns" in
    0|1) ;;
    *) uci -q set openkill.config.ipv6_dns=0; changed=1 ;;
esac

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
