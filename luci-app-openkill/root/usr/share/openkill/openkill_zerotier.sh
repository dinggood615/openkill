#!/bin/sh
# Mihomo provides a built-in `type: zerotier` proxy node.  This helper only
# manages an optional firmware ZeroTier service for users who need a host
# overlay; it never installs a hard dependency or changes routes implicitly.

set -u

enabled="$(uci -q get openkill.config.feature_zerotier 2>/dev/null || printf '0')"
network_id="$(uci -q get openkill.config.zerotier_network_id 2>/dev/null || true)"
interface_name="$(uci -q get openkill.config.zerotier_interface 2>/dev/null || printf 'zt0')"
auto_start="$(uci -q get openkill.config.zerotier_auto_start 2>/dev/null || printf '0')"
ztcli="$(command -v zerotier-cli 2>/dev/null || true)"
service="/etc/init.d/zerotier"

status() {
    builtin="unknown"
    if [ -s /tmp/openkill/capabilities.env ]; then
        builtin="$(sed -n 's/^zerotier=//p' /tmp/openkill/capabilities.env | head -n 1)"
    fi
    case "$builtin" in
        1) printf 'Mihomo built-in node: supported (enable the global switch and add a ZeroTier node in Servers)\n' ;;
        0) printf 'Mihomo built-in node: not detected by the last capability probe\n' ;;
        *) printf 'Mihomo built-in node: capability not probed yet\n' ;;
    esac
    if [ -z "$ztcli" ] && [ ! -x "$service" ]; then
        printf 'System ZeroTier service: not installed (optional)\n'
        return 0
    fi
    if [ -n "$ztcli" ]; then
        printf 'System ZeroTier service: installed\n'
        "$ztcli" info 2>&1 | head -n 1
        [ -n "$network_id" ] && "$ztcli" listnetworks 2>&1 | grep -F "$network_id" || true
    else
        printf 'System ZeroTier service: present, CLI unavailable\n'
    fi
    printf 'OpenKill switch: %s; interface: %s\n' "$([ "$enabled" = 1 ] && printf enabled || printf disabled)" "$interface_name"
}

apply_config() {
    if [ "$enabled" != "1" ]; then
        printf 'ZeroTier switch is disabled; no service changes were made.\n'
        return 0
    fi
    if [ -z "$ztcli" ]; then
        printf 'System ZeroTier CLI is not installed; Mihomo built-in ZeroTier nodes remain available.\n'
        return 0
    fi
    if ! printf '%s\n' "$network_id" | grep -Eq '^[0-9a-fA-F]{16}$'; then
        printf 'ZeroTier network id must contain exactly 16 hexadecimal characters.\n' >&2
        return 2
    fi
    if [ -x "$service" ]; then
        "$service" start >/dev/null 2>&1 || true
        [ "$auto_start" = "1" ] && "$service" enable >/dev/null 2>&1 || true
    fi
    if "$ztcli" join "$network_id"; then
        printf 'ZeroTier joined network %s (interface hint: %s).\n' "$network_id" "$interface_name"
    else
        printf 'ZeroTier failed to join network %s.\n' "$network_id" >&2
        return 1
    fi
}

case "${1:-status}" in
    status) status ;;
    apply) apply_config ;;
    *) printf 'Usage: %s [status|apply]\n' "$0" >&2; exit 2 ;;
esac
