#!/bin/sh
# Guard the plugin settings UI against accidentally shipping newly-added
# English labels/descriptions.  Protocol names and product names are allowed.
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PO="$ROOT_DIR/luci-app-openkill/po/zh-cn/openkill.zh-cn.po"
[ -s "$PO" ] || { echo "missing zh-cn catalog" >&2; exit 1; }

required='Auto keeps route ownership with OpenKill firewall; enable only when Mihomo should install routes itself.
Automatic (OpenKill firewall)
Mihomo manages routes
Leave automatic to avoid duplicate firewall redirects on older or vendor firmware.
Mihomo manages redirect
Let Mihomo select the active uplink interface; recommended for multi-WAN and IPv6 networks.
Drop traffic that cannot be resolved through the TUN route. Keep disabled for maximum compatibility.
Adds NAT mapping work; enable only when a UDP application requires endpoint-independent mapping.
TUN Ownership Mode
Select exactly one TUN and transparent firewall owner. The two modes cannot run at the same time; switching requires a service restart.
OpenKill unified management (recommended)
Mihomo native auto-management (advanced)
Controller Listen Scope
LAN address (recommended)
LAN binds to the router LAN address; loopback keeps the API local. Avoid exposing the controller on WAN.
DNS Listen Address
Keep the Mihomo DNS listener on loopback when dnsmasq redirects local queries.
Local device only (recommended)
Run local-network and IPv6 route maintenance on the first cycle and then at this interval; a larger value lowers background load.
Resolve AAAA records through the configured DNS path. Enable only when the router has a working IPv6 route; the local YAML keeps a short IPv6 fallback window.'

missing=""
while IFS= read -r key; do
    [ -n "$key" ] || continue
    if ! grep -Fq "msgid \"$key\"" "$PO"; then
        missing="${missing}${key}\n"
    fi
done <<EOF
$required
EOF
[ -z "$missing" ] || { printf '%b' "$missing" >&2; exit 1; }
printf 'OpenKill Chinese UI catalog passed.\n'
