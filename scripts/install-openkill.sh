#!/bin/sh
# OpenKill installer
set -eu

REPO="dinggood615/openkill"
PACKAGE_REF="master"
PROJECT_VERSION="2026-1012"
ACTION=install
PACKAGE_FILE=""
BACKUP_DIR="/tmp/openkill-install-backup-$$"
ORIGINAL_ARGS="$#"
SOURCE_ROOT=""

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
if [ "$ORIGINAL_ARGS" -eq 0 ]; then
  if [ -r /dev/tty ]; then
    printf '%s\n' 'OpenKill 一键操作' '  1) 安装或修复' '  2) 更新软件包和内核' '  3) 卸载并清理数据'
    printf '请选择 [1-3，默认1]: '
    read -r choice < /dev/tty || choice=1
    case "$choice" in
      2) ACTION=update;;
      3) ACTION=uninstall;;
      *) ACTION=install;;
    esac
  else
    ACTION=install
  fi
fi
[ "$(id -u)" -eq 0 ] || die "Run as root"

if command -v opkg >/dev/null 2>&1; then PM=opkg; EXT=ipk
elif command -v apk >/dev/null 2>&1; then PM=apk; EXT=apk
else die "Neither opkg nor apk is available"; fi

install_dependencies(){
  log "Installing OpenKill runtime dependencies"
  if [ "$PM" = opkg ]; then
    refresh=0
    opkg update >/dev/null 2>&1 && refresh=1 || true
    if [ "$refresh" -eq 0 ] && [ -f /etc/opkg/distfeeds.conf ]; then
      # Try public mirrors without changing the user's persistent feed file.
      for mirror in "https://mirrors.pku.edu.cn/openwrt" "https://mirrors.tuna.tsinghua.edu.cn/openwrt"; do
        tmpfeeds="/tmp/openkill-distfeeds.$$"
        sed -E "s#https://downloads\\.openwrt\\.org#${mirror}#g" /etc/opkg/distfeeds.conf > "$tmpfeeds"
        if opkg -f "$tmpfeeds" update >/dev/null 2>&1; then refresh=1; rm -f "$tmpfeeds"; break; fi
        rm -f "$tmpfeeds"
      done
    fi
    [ "$refresh" -eq 1 ] || log "Package index update failed; using existing indexes"
    # 与原 OpenClash 安装器及其运行时诊断清单保持一致；不存在的内核
    # 模块会跳过，由当前固件的防火墙后端决定实际需要哪一组。
    deps="bash curl ca-bundle ip-full ruby ruby-yaml ruby-base64 ruby-psych ruby-pstore lua kmod-tun unzip dnsmasq-full luci-compat kmod-inet-diag kmod-nft-tproxy kmod-ipt-tproxy kmod-ipt-extra kmod-ipt-nat iptables-mod-tproxy iptables-mod-extra ipset"
    for dep in $deps; do
      opkg install "$dep" >/dev/null 2>&1 || log "Dependency unavailable or already provided by firmware: $dep"
    done
  else
    refresh=0
    apk update >/dev/null 2>&1 && refresh=1 || true
    if [ "$refresh" -eq 0 ] && [ -f /etc/apk/repositories ]; then
      for mirror in "https://mirrors.pku.edu.cn/openwrt" "https://mirrors.tuna.tsinghua.edu.cn/openwrt"; do
        tmprepos="/tmp/openkill-repositories.$$"
        sed -E "s#https://downloads\\.openwrt\\.org#${mirror}#g" /etc/apk/repositories > "$tmprepos"
        if apk --repositories-file "$tmprepos" update >/dev/null 2>&1; then refresh=1; rm -f "$tmprepos"; break; fi
        rm -f "$tmprepos"
      done
    fi
    [ "$refresh" -eq 1 ] || log "Package index update failed; using existing indexes"
    deps="bash curl ca-certificates iproute2 ruby ruby-yaml lua unzip dnsmasq-full nftables ipset"
    for dep in $deps; do
      apk add --no-cache "$dep" >/dev/null 2>&1 || log "Dependency unavailable or already provided by firmware: $dep"
    done
  fi
}

download(){
  case "$1" in https://*) ;; *) die "HTTPS URL required";; esac
  if command -v curl >/dev/null 2>&1; then curl -fL --retry 2 --connect-timeout 12 --max-time 180 "$1" -o "$2"
  elif command -v uclient-fetch >/dev/null 2>&1; then uclient-fetch -q -T 180 -O "$2" "$1"
  else wget -T 180 -O "$2" "$1"; fi
}

# Pick the quickest reachable distribution mirror once per run.  This keeps
# package, version and future resource downloads on the same healthy source;
# every download still has a fallback loop for transient failures.
select_source(){
  rel="$1"
  candidates="https://raw.githubusercontent.com/$REPO/package/$PACKAGE_REF https://cdn.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF https://fastly.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF"
  if ! command -v curl >/dev/null 2>&1; then
    for base in $candidates; do
      if download "$base/$rel" /tmp/openkill-source-probe.$$ >/dev/null 2>&1; then
        rm -f /tmp/openkill-source-probe.$$
        SOURCE_ROOT="$base"
        return 0
      fi
    done
    return 1
  fi
  scores=/tmp/openkill-source-scores.$$
  : > "$scores"
  for base in $candidates; do
    score=$(curl -fsSL -o /dev/null -w '%{time_total}' --connect-timeout 8 --max-time 15 "$base/$rel" 2>/dev/null || true)
    [ -n "$score" ] && printf '%s %s\n' "$score" "$base" >> "$scores"
  done
  SOURCE_ROOT=$(sort -n "$scores" 2>/dev/null | awk 'NR==1{print $2}')
  rm -f "$scores"
  [ -n "$SOURCE_ROOT" ]
}

install_core(){
  core=/usr/share/openkill/openkill_core.sh
  [ -x "$core" ] || die "OpenKill core installer is missing"
  # Fresh installs may not have an architecture selected yet. Set a safe
  # Meta-compatible default so the first install can download the stable core.
  if command -v uci >/dev/null 2>&1; then
    arch=$(uci -q get openkill.config.core_version || true)
    if [ -z "$arch" ] || [ "$arch" = "0" ]; then
      case "$(uname -m)" in
        x86_64|amd64) arch=linux-amd64-v1 ;;
        aarch64|arm64) arch=linux-arm64 ;;
        armv7l|armv7*) arch=linux-armv7 ;;
        armv6l|armv6*) arch=linux-armv6 ;;
        mips64el) arch=linux-mips64le ;;
        mipsel) arch=linux-mipsle-hardfloat ;;
        mips) arch=linux-mips-hardfloat ;;
        *) arch=linux-amd64-v1 ;;
      esac
      uci -q set openkill.config.core_version="$arch" || true
      uci -q commit openkill || true
      log "Detected core architecture: $arch"
    fi
  fi
  log "Installing the latest official stable Mihomo/Meta core"
  "$core" Meta || die "Official Mihomo/Meta core installation failed"
}

backup_config(){
  if [ -f /etc/config/openkill ] || [ -d /etc/openkill ]; then
    mkdir -p "$BACKUP_DIR"
    tar -czf "$BACKUP_DIR/config.tar.gz" /etc/config/openkill /etc/openkill 2>/dev/null || true
    log "Configuration backup: $BACKUP_DIR/config.tar.gz"
  fi
}

validate_install(){
  [ -f /etc/config/openkill ] || die "OpenKill configuration was not installed"
  [ -x /etc/init.d/openkill ] || die "OpenKill service was not installed"
  uci -q show openkill >/dev/null 2>&1 || die "OpenKill UCI configuration is invalid"
  sh -n /etc/init.d/openkill || die "OpenKill service script validation failed"
  sh -n /usr/share/openkill/openkill_watchdog.sh || die "OpenKill watchdog validation failed"
}

resolve_package(){
  version=/tmp/openkill-version.$$ 
  select_source version || true
  candidates="$SOURCE_ROOT https://raw.githubusercontent.com/$REPO/package/$PACKAGE_REF https://cdn.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF https://fastly.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF"
  for base in $candidates; do
    [ -n "$base" ] || continue
    download "$base/version" "$version" >/dev/null 2>&1 && break || true
  done
  [ -s "$version" ] || die "Could not retrieve OpenKill package version"
  ver=$(sed -n '1{s/^v//;s/[[:space:]]//g;p;}' "$version"); rm -f "$version"
  case "$ver" in ''|*[!0-9.\-]*) die "Invalid package version";; esac
  if [ "$EXT" = ipk ]; then name="luci-app-openkill_${ver}_all.ipk"; else name="luci-app-openkill_${ver}_all.apk"; fi
  for base in $candidates; do
    [ -n "$base" ] || continue
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
install_dependencies
[ -n "$PACKAGE_FILE" ] || resolve_package
[ -f "$PACKAGE_FILE" ] || die "Package file not found"
backup_config
log "Installing OpenKill $PROJECT_VERSION"
if [ "$PM" = opkg ]; then opkg install "$PACKAGE_FILE"; else apk add --allow-untrusted "$PACKAGE_FILE"; fi
validate_install
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
