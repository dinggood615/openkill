#!/bin/sh
# OpenKill installer (pre-release baseline; first published version will be 2026-1000)
set -eu

REPO="dinggood615/openkill"
PACKAGE_REF="master"
PROJECT_VERSION="2026-1000"
ACTION=install
PACKAGE_FILE=""

log(){ printf '\n==> %s\n' "$*"; }
die(){ printf 'Error: %s\n' "$*" >&2; exit 1; }
usage(){ cat <<'EOF'
OpenKill installer
  --install       Install or repair OpenKill
  --update        Update OpenKill and its official stable Mihomo/Meta core
  --uninstall     Remove OpenKill and its data
  --package-file  Install a local IPK/APK file
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --install) ACTION=install; shift;;
    --update) ACTION=update; shift;;
    --uninstall) ACTION=uninstall; shift;;
    --package-file) PACKAGE_FILE="${2:-}"; shift 2;;
    -h|--help) usage; exit 0;;
    *) die "Unknown option: $1";;
  esac
done
[ "$(id -u)" -eq 0 ] || die "Run as root"

if command -v opkg >/dev/null 2>&1; then PM=opkg; EXT=ipk
elif command -v apk >/dev/null 2>&1; then PM=apk; EXT=apk
else die "Neither opkg nor apk is available"; fi

download(){
  case "$1" in https://*) ;; *) die "HTTPS URL required";; esac
  if command -v curl >/dev/null 2>&1; then curl -fL --retry 2 --connect-timeout 12 --max-time 180 "$1" -o "$2"
  elif command -v uclient-fetch >/dev/null 2>&1; then uclient-fetch -q -T 180 -O "$2" "$1"
  else wget -T 180 -O "$2" "$1"; fi
}

install_core(){
  core=/usr/share/openkill/openkill_core.sh
  [ -x "$core" ] || die "OpenKill core installer is missing"
  log "Installing the latest official stable Mihomo/Meta core"
  "$core" Meta || die "Official Mihomo/Meta core installation failed"
}

resolve_package(){
  version=/tmp/openkill-version.$$
  for base in \
    "https://raw.githubusercontent.com/$REPO/package/$PACKAGE_REF" \
    "https://cdn.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF" \
    "https://fastly.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF"; do
    download "$base/version" "$version" >/dev/null 2>&1 && break || true
  done
  [ -s "$version" ] || die "Could not retrieve OpenKill package version"
  ver=$(sed -n '1{s/^v//;s/[[:space:]]//g;p;}' "$version"); rm -f "$version"
  case "$ver" in ''|*[!0-9.\-]*) die "Invalid package version";; esac
  if [ "$EXT" = ipk ]; then name="luci-app-openkill_${ver}_all.ipk"; else name="luci-app-openkill-${ver}.apk"; fi
  for base in \
    "https://raw.githubusercontent.com/$REPO/package/$PACKAGE_REF" \
    "https://cdn.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF" \
    "https://fastly.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF"; do
    PACKAGE_FILE="/tmp/openkill-package.$EXT"
    download "$base/$name" "$PACKAGE_FILE" >/dev/null 2>&1 && return 0 || true
  done
  die "Could not retrieve $name"
}

uninstall(){
  [ -x /etc/init.d/openkill ] && /etc/init.d/openkill stop >/dev/null 2>&1 || true
  if [ "$PM" = opkg ]; then opkg remove luci-app-openkill >/dev/null 2>&1 || true
  else apk del openkill luci-app-openkill >/dev/null 2>&1 || true; fi
  rm -rf /etc/openkill /tmp/etc/openkill /tmp/openkill /tmp/openkill.log
  rm -f /etc/config/openkill /tmp/luci-indexcache
  printf 'OpenKill removed; shared system dependencies were retained.\n'
}

[ "$ACTION" = uninstall ] && { uninstall; exit 0; }
[ -n "$PACKAGE_FILE" ] || resolve_package
[ -f "$PACKAGE_FILE" ] || die "Package file not found"
log "Installing OpenKill $PROJECT_VERSION"
if [ "$PM" = opkg ]; then opkg install "$PACKAGE_FILE"; else apk add --allow-untrusted "$PACKAGE_FILE"; fi
[ -x /etc/init.d/openkill ] || die "OpenKill service was not installed"
install_core
# Remove credentials and generated files left by older oixCloud-based builds.
if command -v uci >/dev/null 2>&1; then
  for opt in oix_token oix_email oix_passwd oix_checkin oix_checkin_interval oix_checkin_multiple oix_params oix_default_params oix_show_info_page; do
    uci -q delete "openkill.config.$opt" || true
  done
  uci -q commit openkill || true
fi
rm -f /tmp/oix_checkin /tmp/oix_info /tmp/openkill_oix_version.json
rm -f "/etc/openkill/config/oixCloud - smart.yaml"
# Remove obsolete Smart/LGBM state so the installation remains Meta-only.
rm -f /etc/openkill/Model.bin /tmp/etc/openkill/Model.bin
rm -rf /etc/openkill/cache/smart /tmp/etc/openkill/cache/smart
if command -v uci >/dev/null 2>&1; then
  for opt in smart_enable auto_smart_switch smart_policy_priority smart_prefer_asn smart_tolerance smart_enable_lgbm smart_collect smart_collect_size smart_collect_rate lgbm_auto_update lgbm_update_interval lgbm_custom_url; do
    uci -q delete "openkill.config.$opt" || true
  done
  uci -q commit openkill || true
fi
rm -f /tmp/luci-indexcache /tmp/luci-modulecache/*openkill* 2>/dev/null || true
rm -f "$PACKAGE_FILE"
printf 'OpenKill %s installation/update complete.\n' "$PROJECT_VERSION"
