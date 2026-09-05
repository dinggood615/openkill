#!/bin/sh
# OpenKill installer
set -eu

REPO="dinggood615/openkill"
PACKAGE_REF="master"
PROJECT_VERSION="2026-1019"
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

# Keep the selected repository configuration for update AND install.
WORK_DIR=$(mktemp -d /tmp/openkill-install.XXXXXX)
trap 'rm -rf "$WORK_DIR"' EXIT
FEED_CONFIG=""
pm_run(){
  if [ "$PM" = opkg ]; then
    if [ -n "$FEED_CONFIG" ]; then opkg -f "$FEED_CONFIG" "$@"; else opkg "$@"; fi
  else
    if [ -n "$FEED_CONFIG" ]; then apk --repositories-file "$FEED_CONFIG" "$@"; else apk "$@"; fi
  fi
}
prepare_feeds(){
  original="$WORK_DIR/feeds-original"
  : > "$original"
  if [ "$PM" = opkg ]; then
    for file in /etc/opkg.conf /etc/opkg/*.conf; do
      [ ! -f "$file" ] || cat "$file" >> "$original"
    done
  else
    for file in /etc/apk/repositories /etc/apk/repositories.d/*.list; do
      [ ! -f "$file" ] || cat "$file" >> "$original"
    done
  fi
  FEED_CANDIDATES="$original"
  # Change only the official host; preserve firmware paths, ABI and custom feeds.
  for mirror in https://mirrors.pku.edu.cn/openwrt https://mirrors.tuna.tsinghua.edu.cn/openwrt; do
    candidate="$WORK_DIR/feeds-$(echo "$mirror" | tr '/:' '__')"
    sed "s#https://downloads.openwrt.org/#$mirror/#g" "$original" > "$candidate"
    cmp -s "$original" "$candidate" || FEED_CANDIDATES="$FEED_CANDIDATES $candidate"
  done
  for candidate in $FEED_CANDIDATES; do
    FEED_CONFIG="$candidate"
    if pm_run update > "$WORK_DIR/feeds.log" 2>&1; then
      log "Dependency repository selected: $candidate"
      return 0
    fi
  done
  cat "$WORK_DIR/feeds.log" >&2
  die "All compatible dependency repositories failed"
}
install_dependency(){
  dep="$1"
  if [ "$PM" = opkg ]; then
    opkg status "$dep" 2>/dev/null | grep -q '^Status:.* installed$' && return 0
    operation=install
  else
    apk info -e "$dep" >/dev/null 2>&1 && return 0
    operation=add
  fi
  if pm_run "$operation" "$dep" > "$WORK_DIR/dependency.log" 2>&1; then return 0; fi
  # A working index does not guarantee that package downloads work.
  for candidate in $FEED_CANDIDATES; do
    [ "$candidate" != "$FEED_CONFIG" ] || continue
    FEED_CONFIG="$candidate"
    if pm_run update >> "$WORK_DIR/dependency.log" 2>&1 &&
       pm_run "$operation" "$dep" >> "$WORK_DIR/dependency.log" 2>&1; then return 0; fi
  done
  cat "$WORK_DIR/dependency.log" >&2
  return 1
}
install_dependencies(){
  log "Installing OpenKill runtime dependencies"
  prepare_feeds
  if [ "$PM" = opkg ]; then
    required="bash curl ca-bundle ip-full ruby ruby-yaml ruby-json lua kmod-tun unzip dnsmasq-full luci-compat"
    optional="ruby-base64 ruby-psych ruby-pstore kmod-inet-diag"
    if command -v fw4 >/dev/null 2>&1; then required="$required kmod-nft-tproxy"
    else required="$required kmod-ipt-tproxy iptables-mod-tproxy ipset"; optional="$optional kmod-ipt-extra kmod-ipt-nat iptables-mod-extra"; fi
  else
    required="bash curl ca-certificates ip-full ruby ruby-yaml ruby-json lua kmod-tun unzip dnsmasq-full luci-compat"
    optional="ruby-base64 ruby-psych ruby-pstore kmod-inet-diag"
    if command -v fw4 >/dev/null 2>&1; then required="$required kmod-nft-tproxy"
    else required="$required ipset iptables-mod-tproxy"; fi
  fi
  for dep in $required; do install_dependency "$dep" || die "Required dependency could not be installed: $dep"; done
  for dep in $optional; do install_dependency "$dep" || log "Optional dependency unavailable: $dep"; done
  # YAML and JSON are required for configuration and the release manifest.
  ruby -ryaml -rjson -e 'exit 0' || die "Ruby YAML/JSON runtime is incomplete"
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
    if score=$(curl -fsSL -o /dev/null -w '%{time_total}' --connect-timeout 8 --max-time 15 "$base/$rel" 2>/dev/null); then
      printf '%s %s\n' "$score" "$base" >> "$scores"
    fi
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
        *) die "Unsupported CPU architecture: $(uname -m)" ;;
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
  manifest="$WORK_DIR/latest.json"
  # Authoritative origin first; cached mirrors are only a connectivity fallback.
  for base in "https://raw.githubusercontent.com/$REPO/package/$PACKAGE_REF" "https://cdn.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF" "https://fastly.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF"; do
    if download "$base/latest-$EXT.json" "$manifest" >/dev/null 2>&1 &&
       ruby -rjson -e '
         d=JSON.parse(File.read(ARGV[0]))
         abort unless d["format"]==ARGV[1] && d["architecture"]=="all"
         abort unless d["version"].match?(/\A2026-[0-9]+\z/) && d["sha256"].match?(/\A[0-9a-f]{64}\z/)
         package_version = ARGV[1] == "apk" ? d["version"].sub("-", ".") : d["version"]
         expected="luci-app-openkill_#{package_version}_all.#{ARGV[1]}"
         abort unless d["filename"]==expected
         abort unless d["url"]=="https://github.com/"+ARGV[2]+"/releases/download/v"+d["version"]+"-"+ARGV[1]+"/"+expected
         puts [d["version"],d["filename"],d["sha256"],d["url"]]
       ' "$manifest" "$EXT" "$REPO" > "$WORK_DIR/metadata"; then break; fi
    : > "$WORK_DIR/metadata"
  done
  [ -s "$WORK_DIR/metadata" ] || die "No valid published $EXT release manifest is available"
  ver=$(sed -n '1p' "$WORK_DIR/metadata")
  name=$(sed -n '2p' "$WORK_DIR/metadata")
  checksum=$(sed -n '3p' "$WORK_DIR/metadata")
  release_url=$(sed -n '4p' "$WORK_DIR/metadata")
  PACKAGE_FILE="$WORK_DIR/$name"
  for url in "$release_url" "https://raw.githubusercontent.com/$REPO/package/$PACKAGE_REF/$name" "https://cdn.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF/$name" "https://fastly.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF/$name"; do
    if download "$url" "$PACKAGE_FILE" &&
       [ "$(sha256sum "$PACKAGE_FILE" | awk '{print $1}')" = "$checksum" ]; then
      log "Verified published $EXT version: $ver"
      return 0
    fi
  done
  die "Package download or SHA256 verification failed"
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
log "Installing OpenKill ${ver:-local package}"
if [ "$PM" = opkg ]; then pm_run install "$PACKAGE_FILE"; else pm_run add --allow-untrusted "$PACKAGE_FILE"; fi
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
printf 'OpenKill %s installation/update complete.\n' "${ver:-local package}"
