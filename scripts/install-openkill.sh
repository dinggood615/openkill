#!/bin/sh
# OpenKill installer
set -eu

REPO="dinggood615/openkill"
PACKAGE_REF="master"
PROJECT_VERSION="2026-1093"
ACTION=install
PACKAGE_FILE=""
LOCAL_PACKAGE_MODE=0
BACKUP_DIR="/tmp/openkill-install-backup-$$"
ORIGINAL_ARGS="$#"
SOURCE_ROOT=""
TOTAL_STEPS=8
CURRENT_STEP=0
INSTALL_LOG=""

log(){ printf '\n==> %s\n' "$*"; [ -z "$INSTALL_LOG" ] || printf '==> %s\n' "$*" >> "$INSTALL_LOG"; }
detail(){ printf '    %s\n' "$*"; [ -z "$INSTALL_LOG" ] || printf '    %s\n' "$*" >> "$INSTALL_LOG"; }
step(){ CURRENT_STEP=$((CURRENT_STEP + 1)); printf '\n[%s/%s] %s\n' "$CURRENT_STEP" "$TOTAL_STEPS" "$*"; [ -z "$INSTALL_LOG" ] || printf '[%s/%s] %s\n' "$CURRENT_STEP" "$TOTAL_STEPS" "$*" >> "$INSTALL_LOG"; }
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
if [ "$ACTION" = uninstall ]; then
  TOTAL_STEPS=1
elif [ -n "$PACKAGE_FILE" ]; then
  # A supplied local package skips remote manifest resolution and download.
  LOCAL_PACKAGE_MODE=1
  TOTAL_STEPS=7
else
  TOTAL_STEPS=9
fi
[ "$(id -u)" -eq 0 ] || die "Run as root"

if command -v opkg >/dev/null 2>&1; then PM=opkg; EXT=ipk
elif command -v apk >/dev/null 2>&1; then PM=apk; EXT=apk
else die "Neither opkg nor apk is available"; fi

# Keep the selected repository configuration for update AND install.
WORK_DIR=$(mktemp -d /tmp/openkill-install.XXXXXX)
trap 'rm -rf "$WORK_DIR"' EXIT
INSTALL_STAMP=$(date +%Y%m%d-%H%M%S 2>/dev/null || printf '%s' "$$")
INSTALL_LOG="/tmp/openkill-install-${INSTALL_STAMP}.log"
: > "$INSTALL_LOG" 2>/dev/null || INSTALL_LOG=""
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
  raw_original="$WORK_DIR/feeds-original.raw"
  refresh_feeds=1
  [ "${1:-}" = no-update ] && refresh_feeds=0
  : > "$raw_original"
  if [ "$PM" = opkg ]; then
    for file in /etc/opkg.conf /etc/opkg/*.conf; do
      [ ! -f "$file" ] || cat "$file" >> "$raw_original"
    done
  else
    for file in /etc/apk/repositories /etc/apk/repositories.d/*.list; do
      [ ! -f "$file" ] || cat "$file" >> "$raw_original"
    done
  fi
  # Firmware images often keep the same feed in both /etc/opkg.conf and a
  # generated *.conf file.  Deduplicate source lines before passing the
  # temporary configuration to opkg/apk; otherwise even a local package
  # install emits duplicate-src warnings and may refresh the same index twice.
  awk -v package_manager="$PM" '
    package_manager != "apk" && /^[[:space:]]*src([[:space:]]|\/)/ {
      key=$0
      sub(/#.*/, "", key)
      gsub(/[[:space:]]+/, " ", key)
      sub(/^ /, "", key)
      sub(/ $/, "", key)
      if (seen[key]++) next
    }
    package_manager == "apk" && /^[[:space:]]*[^#[:space:]]/ {
      key=$0
      sub(/#.*/, "", key)
      gsub(/[[:space:]]+/, " ", key)
      sub(/^ /, "", key)
      sub(/ $/, "", key)
      if (seen[key]++) next
    }
    { print }
  ' "$raw_original" > "$original"
  rm -f "$raw_original"
  FEED_CANDIDATES="$original"
  if [ "$refresh_feeds" -eq 0 ]; then
    FEED_CONFIG="$original"
    return 0
  fi
  # Only rewrite the official OpenWrt host. Vendor feeds such as
  # dl.openwrt.ai must remain unchanged: a generic mirror may return a package
  # with a different kernel ABI even when the path looks similar.
  if grep -Eq 'https?://downloads\.openwrt\.org/' "$original"; then
    for mirror in https://mirrors.pku.edu.cn/openwrt https://mirrors.tuna.tsinghua.edu.cn/openwrt; do
      candidate="$WORK_DIR/feeds-$(echo "$mirror" | tr '/:' '__')"
      sed -e "s#https://downloads.openwrt.org/#$mirror/#g" \
          -e "s#http://downloads.openwrt.org/#$mirror/#g" "$original" > "$candidate"
      cmp -s "$original" "$candidate" || FEED_CANDIDATES="$FEED_CANDIDATES $candidate"
    done
  else
    detail "Firmware uses a vendor/custom feed; keeping its exact repository for ABI compatibility"
  fi
  for candidate in $FEED_CANDIDATES; do
    FEED_CONFIG="$candidate"
    detail "Refreshing dependency indexes: $candidate"
    if pm_run update > "$WORK_DIR/feeds.log" 2>&1; then
      [ -z "$INSTALL_LOG" ] || cat "$WORK_DIR/feeds.log" >> "$INSTALL_LOG"
      log "Verified dependency repository: $candidate"
      return 0
    fi
    [ -z "$INSTALL_LOG" ] || cat "$WORK_DIR/feeds.log" >> "$INSTALL_LOG"
  done
  cat "$WORK_DIR/feeds.log" >&2
  die "All compatible dependency repositories failed"
}
is_installed(){
  dep="$1"
  if [ "$PM" = opkg ]; then
    opkg status "$dep" 2>/dev/null | grep -q '^Status:.* installed$'
  else
    apk info -e "$dep" >/dev/null 2>&1
  fi
}
run_pm_transaction(){
  transaction_log="$WORK_DIR/package-manager.log"
  if pm_run "$@" >> "$transaction_log" 2>&1; then
    [ -z "$INSTALL_LOG" ] || cat "$transaction_log" >> "$INSTALL_LOG"
    return 0
  fi
  [ -z "$INSTALL_LOG" ] || cat "$transaction_log" >> "$INSTALL_LOG"
  return 1
}
install_package_batch(){
  packages="$*"
  [ -n "$packages" ] || return 0
  if [ "$PM" = opkg ]; then operation=install; else operation=add; fi
  : > "$WORK_DIR/package-manager.log"
  if run_pm_transaction "$operation" $packages; then return 0; fi
  # A valid index does not guarantee that package archives are reachable. Retry
  # the complete missing batch on each remaining compatible repository.
  for candidate in $FEED_CANDIDATES; do
    [ "$candidate" != "$FEED_CONFIG" ] || continue
    FEED_CONFIG="$candidate"
    detail "Retrying dependency download with: $candidate"
    if pm_run update >> "$WORK_DIR/package-manager.log" 2>&1 &&
       run_pm_transaction "$operation" $packages; then return 0; fi
  done
  cat "$WORK_DIR/package-manager.log" >&2
  return 1
}
package_available(){
  dep="$1"
  if [ "$PM" = opkg ]; then
    pm_run list "$dep" 2>/dev/null | grep -q "^$dep "
  else
    pm_run search -x "$dep" >/dev/null 2>&1
  fi
}
install_dependency_set(){
  set_title="$1"
  set_required="$2"
  set_packages="$3"
  missing_packages=""
  total_packages=0
  installed_packages=0
  for dep in $set_packages; do
    total_packages=$((total_packages + 1))
    if is_installed "$dep"; then
      installed_packages=$((installed_packages + 1))
    else
      missing_packages="$missing_packages $dep"
    fi
  done
  detail "$set_title: $installed_packages/$total_packages already available"
  [ -n "$missing_packages" ] || return 0
  [ -n "$FEED_CONFIG" ] || prepare_feeds
  detail "Installing $set_title:$missing_packages"
  if install_package_batch $missing_packages; then
    for dep in $missing_packages; do
      is_installed "$dep" || die "Dependency installation did not complete: $dep"
    done
    return 0
  fi
  [ "$set_required" = required ] && die "Required dependencies could not be installed:$missing_packages"
  detail "Optional compatibility packages unavailable:$missing_packages"
  return 0
}
install_dependencies(){
  step "Checking and installing OpenKill runtime dependencies"
  # jsonfilter is part of the OpenWrt base toolchain on current images and is
  # used as a small, dependency-free fallback when ruby-json is not shipped.
  # Keeping it required makes remote package/core resolution work on minimal
  # firmware without forcing the much larger Ruby JSON extension.
  OPENKILL_REQUIRED_COMMON="bash curl ca-bundle ip-full jsonfilter ruby ruby-yaml lua kmod-tun unzip dnsmasq-full luci-compat"
  OPENKILL_OPTIONAL_COMMON="ruby-json ruby-base64 ruby-psych ruby-pstore kmod-inet-diag"
  OPENKILL_REQUIRED_FW4="kmod-nft-tproxy"
  OPENKILL_REQUIRED_FW3="kmod-ipt-tproxy iptables-mod-tproxy ipset"
  OPENKILL_OPTIONAL_FW3="kmod-ipt-extra kmod-ipt-nat iptables-mod-extra"
  if [ -r /usr/share/openkill/dependencies.conf ]; then
    # Existing installations provide the same manifest that is packaged with
    # OpenKill.  Fresh installs use the fallback above until the package lands.
    . /usr/share/openkill/dependencies.conf
  fi
  if [ "$PM" = opkg ]; then
    required="$OPENKILL_REQUIRED_COMMON"
    optional="$OPENKILL_OPTIONAL_COMMON"
    if command -v fw4 >/dev/null 2>&1; then required="$required $OPENKILL_REQUIRED_FW4"
    else required="$required $OPENKILL_REQUIRED_FW3"; optional="$optional $OPENKILL_OPTIONAL_FW3"; fi
  else
    required="$OPENKILL_REQUIRED_COMMON"
    required=$(printf '%s' "$required" | sed 's/ca-bundle/ca-certificates/g')
    optional="$OPENKILL_OPTIONAL_COMMON"
    if command -v fw4 >/dev/null 2>&1; then required="$required $OPENKILL_REQUIRED_FW4"
    else required="$required ipset iptables-mod-tproxy"; fi
  fi

  # Repairs and updates normally run on a router that already has the
  # runtime.  Avoid refreshing every feed in that case; a blocked mirror can
  # otherwise add minutes before the actual package download starts.
  need_feed=0
  for dep in $required; do
    is_installed "$dep" || { need_feed=1; break; }
  done
  if [ "$need_feed" -eq 1 ]; then
    prepare_feeds
  else
    FEED_CONFIG=""
    detail "All required dependencies are installed; index refresh skipped"
  fi
  install_dependency_set "required runtime dependencies" required "$required"
  # YAML is required by the runtime.  jsonfilter handles the small JSON
  # objects used by the installer/core resolver, so ruby-json remains an
  # optional accelerator rather than a fresh-install blocker.
  if ! ruby -ryaml -e 'exit 0' >/dev/null 2>&1; then
    [ -n "$FEED_CONFIG" ] || prepare_feeds
    available_optional=""
    for dep in $optional; do
      if package_available "$dep"; then available_optional="$available_optional $dep"
      else detail "Compatibility package is not supplied by this firmware: $dep"; fi
    done
    install_dependency_set "Ruby and diagnostic compatibility modules" optional "$available_optional"
  fi
  ruby -ryaml -e 'exit 0' || die "Ruby YAML runtime is incomplete"
  if ! ruby -rjson -e 'exit 0' >/dev/null 2>&1; then
    if command -v jsonfilter >/dev/null 2>&1; then
      detail "Ruby JSON extension unavailable; using OpenWrt jsonfilter for manifest/core metadata"
    elif [ "$LOCAL_PACKAGE_MODE" -eq 1 ]; then
      detail "Ruby JSON extension is unavailable; local package mode does not need remote manifest parsing"
    else
      [ -n "$FEED_CONFIG" ] || prepare_feeds
      json_packages=""
      if package_available ruby-json; then json_packages="ruby-json"; fi
      [ -n "$json_packages" ] || die "Neither jsonfilter nor Ruby JSON is available for published package resolution"
      install_dependency_set "Ruby JSON manifest module" required "$json_packages"
      ruby -rjson -e 'exit 0' || die "Ruby JSON runtime is incomplete"
    fi
  fi
}

download(){
  case "$1" in https://*) ;; *) die "HTTPS URL required";; esac
  download_url="$1"
  download_path="$2"
  # Metadata callers pass a short bound; archives receive a longer window so
  # a healthy but slow domestic connection is not mistaken for a stalled one.
  timeout="${3:-300}"
  show_progress="${4:-0}"
  rm -f "$download_path"
  if command -v curl >/dev/null 2>&1; then
    if [ "$show_progress" = 1 ]; then
      detail "Downloading $(basename "$download_path") with live progress"
      curl -fL -# --retry 1 --connect-timeout 8 --max-time "$timeout" \
        --speed-time 30 --speed-limit 512 "$download_url" -o "$download_path"
    else
      curl -fL -sS --retry 1 --connect-timeout 8 --max-time "$timeout" \
        --speed-time 15 --speed-limit 128 "$download_url" -o "$download_path"
    fi
  elif command -v uclient-fetch >/dev/null 2>&1; then
    uclient-fetch -q -T "$timeout" -O "$download_path" "$download_url"
  else
    wget -q -T "$timeout" -O "$download_path" "$download_url"
  fi
}

# Pick the quickest reachable distribution mirror once per run.  This keeps
# package, version and future resource downloads on the same healthy source;
# every download still has a fallback loop for transient failures.
select_source(){
  rel="$1"
  candidates="https://raw.githubusercontent.com/$REPO/package/$PACKAGE_REF https://cdn.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF https://fastly.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF"
  if ! command -v curl >/dev/null 2>&1; then
    for base in $candidates; do
      if download "$base/$rel" /tmp/openkill-source-probe.$$ 20 >/dev/null 2>&1; then
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
    detail "Testing package source: $base"
    if score=$(curl -fsSL -o /dev/null -w '%{time_total}' --connect-timeout 4 --max-time 8 --speed-time 4 --speed-limit 64 "$base/$rel" 2>/dev/null); then
      printf '%s %s\n' "$score" "$base" >> "$scores"
    fi
  done
  SOURCE_ROOT=$(sort -n "$scores" 2>/dev/null | awk 'NR==1{print $2}')
  source_time=$(sort -n "$scores" 2>/dev/null | awk 'NR==1{print $1}')
  rm -f "$scores"
  [ -z "$SOURCE_ROOT" ] || detail "Selected fastest valid package source: $SOURCE_ROOT (${source_time}s)"
  [ -n "$SOURCE_ROOT" ]
}

install_core(){
  core=/usr/share/openkill/openkill_core.sh
  [ -x "$core" ] || die "OpenKill core installer is missing"
  # Fresh installs may not have an architecture selected yet. Set a safe
  # Meta-compatible default so the first install can download the stable core.
  if command -v uci >/dev/null 2>&1; then
    arch=$(uci -q get openkill.config.core_arch || true)
    if [ -z "$arch" ] || [ "$arch" = "0" ]; then
      case "$(uname -m)" in
        x86_64|amd64) arch=linux-amd64-v1 ;;
        i[3-6]86) arch=linux-386 ;;
        aarch64|arm64) arch=linux-arm64 ;;
        armv7l|armv7*) arch=linux-armv7 ;;
        armv6l|armv6*) arch=linux-armv6 ;;
        armv5*) arch=linux-armv5 ;;
        mips64el) arch=linux-mips64le ;;
        mipsel) arch=linux-mipsle-hardfloat ;;
        mips) arch=linux-mips-hardfloat ;;
        riscv64) arch=linux-riscv64 ;;
        s390x) arch=linux-s390x ;;
        loongarch64) arch=linux-loong64-abi2 ;;
        *) die "Unsupported CPU architecture: $(uname -m)" ;;
      esac
      uci -q set openkill.config.core_arch="$arch" || true
      uci -q commit openkill || true
      log "Detected core architecture: $arch"
    fi
  fi
  step "Resolving and installing the latest official stable Mihomo/Meta core"
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
  sh -n /usr/share/openkill/openkill_core.sh || die "OpenKill core installer validation failed"
  sh -n /usr/share/openkill/openkill_update.sh || die "OpenKill updater validation failed"
  sh -n /usr/share/openkill/openkill_watchdog.sh || die "OpenKill watchdog validation failed"
  [ -x /usr/share/openkill/openkill_semantic_check.sh ] || die "OpenKill semantic validator is missing"
  sh -n /usr/share/openkill/openkill_semantic_check.sh || die "OpenKill semantic validator syntax check failed"
  ruby -ryaml -e 'exit 0' || die "Ruby YAML runtime is incomplete"
}

database_root(){
  database_dir="/etc/openkill"
  if command -v uci >/dev/null 2>&1 &&
     [ "$(uci -q get openkill.config.small_flash_memory 2>/dev/null || true)" = "1" ]; then
    database_dir="/tmp/etc/openkill"
  fi
  mkdir -p "$database_dir"
  printf '%s\n' "$database_dir"
}

database_fetch(){
  database_name="$1"
  database_path="$2"
  database_min_size="$3"
  shift 3
  database_tmp="$WORK_DIR/database-$database_name"
  for database_url in "$@"; do
    detail "Downloading database $database_name: $database_url"
    if download "$database_url" "$database_tmp" 180 1; then
      database_size=$(wc -c < "$database_tmp" 2>/dev/null || printf '0')
      if [ "$database_size" -ge "$database_min_size" ] &&
         ! head -c 512 "$database_tmp" | grep -qiE '<!doctype|<html|<head|<body'; then
        mv -f "$database_tmp" "$database_path"
        detail "Database ready: $database_path (${database_size} bytes)"
        return 0
      fi
      detail "Rejected invalid database response: $database_name"
    fi
    rm -f "$database_tmp"
  done
  detail "Database download unavailable; retaining the packaged copy: $database_name"
  return 1
}

download_databases(){
  step "Downloading GeoIP, GeoSite, ASN and China route databases"
  database_dir=$(database_root)
  database_ok=0
  database_fetch Country.mmdb "$database_dir/Country.mmdb" 10240 \
    "https://testingcf.jsdelivr.net/gh/alecthw/mmdb_china_ip_list@release/lite/Country.mmdb" \
    "https://fastly.jsdelivr.net/gh/alecthw/mmdb_china_ip_list@release/lite/Country.mmdb" \
    "https://cdn.jsdelivr.net/gh/alecthw/mmdb_china_ip_list@release/lite/Country.mmdb" \
    "https://raw.githubusercontent.com/alecthw/mmdb_china_ip_list/release/lite/Country.mmdb" && database_ok=$((database_ok + 1)) || true
  database_fetch GeoSite.dat "$database_dir/GeoSite.dat" 10240 \
    "https://testingcf.jsdelivr.net/gh/Loyalsoldier/v2ray-rules-dat@release/geosite.dat" \
    "https://fastly.jsdelivr.net/gh/Loyalsoldier/v2ray-rules-dat@release/geosite.dat" \
    "https://cdn.jsdelivr.net/gh/Loyalsoldier/v2ray-rules-dat@release/geosite.dat" \
    "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat" && database_ok=$((database_ok + 1)) || true
  database_fetch GeoIP.dat "$database_dir/GeoIP.dat" 10240 \
    "https://testingcf.jsdelivr.net/gh/Loyalsoldier/v2ray-rules-dat@release/geoip.dat" \
    "https://fastly.jsdelivr.net/gh/Loyalsoldier/v2ray-rules-dat@release/geoip.dat" \
    "https://cdn.jsdelivr.net/gh/Loyalsoldier/v2ray-rules-dat@release/geoip.dat" \
    "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat" && database_ok=$((database_ok + 1)) || true
  database_fetch ASN.mmdb "$database_dir/ASN.mmdb" 10240 \
    "https://testingcf.jsdelivr.net/gh/xishang0128/geoip@release/GeoLite2-ASN.mmdb" \
    "https://fastly.jsdelivr.net/gh/xishang0128/geoip@release/GeoLite2-ASN.mmdb" \
    "https://cdn.jsdelivr.net/gh/xishang0128/geoip@release/GeoLite2-ASN.mmdb" \
    "https://github.com/xishang0128/geoip/releases/latest/download/GeoLite2-ASN.mmdb" && database_ok=$((database_ok + 1)) || true

  # The China CIDR helper already validates and transforms both IPv4 and IPv6
  # lists for nftables/iptables.  Keep the packaged route sets as a safe
  # fallback when all external mirrors are temporarily unreachable.
  if [ -x /usr/share/openkill/openkill_chnroute.sh ]; then
    detail "Refreshing China IPv4/IPv6 route databases"
    if ! SHOW_DOWNLOAD_PROGRESS=1 /usr/share/openkill/openkill_chnroute.sh >> "${INSTALL_LOG:-/dev/null}" 2>&1; then
      detail "China route refresh failed; retaining the packaged route sets"
    fi
  fi
  for database_file in Country.mmdb GeoSite.dat GeoIP.dat ASN.mmdb china_ip_route.ipset china_ip6_route.ipset; do
    [ -s "$database_dir/$database_file" ] || detail "Database not present after install: $database_file"
  done
  detail "Database preparation finished ($database_ok/4 binary databases refreshed)"
}

validate_manifest(){
  manifest_path="$1"
  if command -v jsonfilter >/dev/null 2>&1; then
    manifest_version=$(jsonfilter -i "$manifest_path" -e '@.version' 2>/dev/null | sed -n '1p')
    manifest_format=$(jsonfilter -i "$manifest_path" -e '@.format' 2>/dev/null | sed -n '1p')
    manifest_arch=$(jsonfilter -i "$manifest_path" -e '@.architecture' 2>/dev/null | sed -n '1p')
    manifest_sha=$(jsonfilter -i "$manifest_path" -e '@.sha256' 2>/dev/null | sed -n '1p')
    manifest_name=$(jsonfilter -i "$manifest_path" -e '@.filename' 2>/dev/null | sed -n '1p')
    manifest_url=$(jsonfilter -i "$manifest_path" -e '@.url' 2>/dev/null | sed -n '1p')
    case "$manifest_version" in 2026-[0-9]*) ;; *) return 1;; esac
    [ "$manifest_format" = "$EXT" ] || return 1
    [ "$manifest_arch" = all ] || return 1
    case "$manifest_sha" in [0-9a-f][0-9a-f]*) ;; *) return 1;; esac
    package_version="$manifest_version"
    [ "$EXT" = apk ] && package_version=$(printf '%s' "$manifest_version" | sed 's/-/./')
    expected="luci-app-openkill_${package_version}_all.$EXT"
    [ "$manifest_name" = "$expected" ] || return 1
    expected_url="https://github.com/$REPO/releases/download/v${manifest_version}-${EXT}/${expected}"
    [ "$manifest_url" = "$expected_url" ] || return 1
    printf '%s\n%s\n%s\n%s\n' "$manifest_version" "$manifest_name" "$manifest_sha" "$manifest_url"
    return 0
  fi
  ruby -rjson -e '
    d=JSON.parse(File.read(ARGV[0]))
    version=d["version"].to_s
    abort unless d["format"]==ARGV[1] && d["architecture"]=="all"
    abort unless version.match?(/\A2026-[0-9]+\z/) && d["sha256"].to_s.match?(/\A[0-9a-f]{64}\z/)
    package_version = ARGV[1] == "apk" ? version.sub("-", ".") : version
    expected="luci-app-openkill_#{package_version}_all.#{ARGV[1]}"
    abort unless d["filename"]==expected
    abort unless d["url"]=="https://github.com/"+ARGV[2]+"/releases/download/v"+version+"-"+ARGV[1]+"/"+expected
    puts [version,d["filename"],d["sha256"],d["url"]]
  ' "$manifest_path" "$EXT" "$REPO"
}

select_newest_manifest(){
  ruby -e '
    # Do not use Array#> here: several OpenWrt Ruby builds only expose
    # Array#<=>, so a direct array comparison raises NoMethodError.  Compare
    # numeric components explicitly and keep the first (fastest) source on a
    # version tie.
    def version_compare(a, b)
      aa=a.to_s.split("-").map(&:to_i)
      bb=b.to_s.split("-").map(&:to_i)
      n=[aa.length, bb.length].max
      (0...n).each do |i|
        av=aa[i] || 0
        bv=bb[i] || 0
        return 1 if av > bv
        return -1 if av < bv
      end
      0
    end
    rows=File.readlines(ARGV[0], chomp: true)
    best=nil
    rows.each do |line|
      version,index,base,file=line.split("\t",4)
      replace=best.nil?
      if !replace
        comparison=version_compare(version, best[0])
        replace=comparison > 0 || (comparison == 0 && index.to_i < best[1].to_i)
      end
      if replace
        best=[version,index,base,file]
      end
    end
    puts [best[1],best[2],best[3]].join("\n") if best
  ' "$1"
}

version_greater(){
  ruby -e '
    def version_compare(a, b)
      aa=a.to_s.split("-").map(&:to_i)
      bb=b.to_s.split("-").map(&:to_i)
      n=[aa.length, bb.length].max
      (0...n).each do |i|
        av=aa[i] || 0
        bv=bb[i] || 0
        return 1 if av > bv
        return -1 if av < bv
      end
      0
    end
    exit(version_compare(ARGV[0], ARGV[1]) > 0 ? 0 : 1)
  ' "$1" "$2"
}

resolve_package(){
  step "Resolving the latest published OpenKill $EXT package"
  manifest="$WORK_DIR/latest.json"
  # Probe the manifest itself so the first successful source is also the
  # preferred package download mirror.  A source that returns a fast 404 is
  # never ranked as healthy.
  manifest_source=""
  if select_source "latest-$EXT.json"; then
    manifest_source="$SOURCE_ROOT"
  fi
  # A CDN can legally return an older cached branch manifest.  Query every
  # candidate with a cache-busting token, validate each record, and select the
  # highest published version.  The fastest source is only a tie-breaker and is
  # still preferred for the package archive after the version is selected.
  manifest_bases=""
  for base in "$manifest_source" "https://raw.githubusercontent.com/$REPO/package/$PACKAGE_REF" "https://cdn.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF" "https://fastly.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF"; do
    [ -n "$base" ] || continue
    case " $manifest_bases " in *" $base "*) continue;; esac
    manifest_bases="$manifest_bases $base"
  done
  manifest_rows="$WORK_DIR/manifest-rows"
  : > "$manifest_rows"
  manifest_nonce=$(date +%s 2>/dev/null || printf '%s' "$$")
  manifest_index=0
  for base in $manifest_bases; do
    manifest_index=$((manifest_index + 1))
    candidate_manifest="$WORK_DIR/manifest-${manifest_index}.json"
    manifest_url="$base/latest-$EXT.json?openkill_cache_bust=${manifest_nonce}_${manifest_index}"
    detail "Checking package manifest: $base"
    if download "$manifest_url" "$candidate_manifest" 15 >/dev/null 2>&1; then
      if candidate_metadata=$(validate_manifest "$candidate_manifest" 2>/dev/null); then
        candidate_version=$(printf '%s\n' "$candidate_metadata" | sed -n '1p')
        printf '%s\t%s\t%s\t%s\n' "$candidate_version" "$manifest_index" "$base" "$candidate_manifest" >> "$manifest_rows"
        detail "Found valid $EXT manifest: v$candidate_version"
      else
        detail "Rejected invalid or stale $EXT manifest: $base"
      fi
    fi
  done
  manifest_source=""
  if [ -s "$manifest_rows" ]; then
    chosen_manifest=$(select_newest_manifest "$manifest_rows")
    manifest_index=$(printf '%s\n' "$chosen_manifest" | sed -n '1p')
    manifest_source=$(printf '%s\n' "$chosen_manifest" | sed -n '2p')
    selected_manifest=$(printf '%s\n' "$chosen_manifest" | sed -n '3p')
    cp "$selected_manifest" "$manifest"
    validate_manifest "$manifest" > "$WORK_DIR/metadata"
    detail "Selected newest valid $EXT manifest: v$(sed -n '1p' "$WORK_DIR/metadata") from $manifest_source"
  else
    : > "$WORK_DIR/metadata"
  fi
  # A valid CDN manifest may still lag behind the package branch.  When the
  # selected record is older than this installer, query the GitHub Releases API
  # as an independent freshness check and replace it only when a newer release
  # is found.  If all API routes are unavailable, the validated manifest remains
  # a safe offline fallback.
  manifest_version=""
  [ ! -s "$WORK_DIR/metadata" ] || manifest_version=$(sed -n '1p' "$WORK_DIR/metadata")
  query_release_api=0
  if [ -z "$manifest_version" ] || version_greater "$PROJECT_VERSION" "$manifest_version"; then
    query_release_api=1
    [ -z "$manifest_version" ] || detail "Manifest v$manifest_version is behind installer v$PROJECT_VERSION; checking release APIs"
  fi
  if [ "$query_release_api" -eq 1 ]; then
    release_json="$WORK_DIR/releases.json"
    best_release_version="$manifest_version"
    for api in \
      "https://api.github.com/repos/$REPO/releases?per_page=30" \
      "https://ghfast.top/https://api.github.com/repos/$REPO/releases?per_page=30" \
      "https://github.dpik.top/https://api.github.com/repos/$REPO/releases?per_page=30" \
      "https://gh-proxy.com/https://api.github.com/repos/$REPO/releases?per_page=30"; do
      if download "$api" "$release_json" 10 >/dev/null 2>&1; then
        if ruby -rjson -e '
          begin
            releases=JSON.parse(File.read(ARGV[0]))
            ext=ARGV[1]
            rows=[]
            releases.each do |rel|
              tag=rel["tag_name"].to_s
              m=tag.match(/\Av(2026-[0-9]+)-#{Regexp.escape(ext)}\z/)
              next unless m
              asset=(rel["assets"]||[]).find{|a| a["name"].to_s.end_with?("."+ext) && a["name"].to_s.start_with?("luci-app-openkill_")}
              next unless asset
              digest=asset["digest"].to_s.sub(/^sha256:/,"")
              next unless digest.match?(/\A[0-9a-f]{64}\z/)
              rows << [m[1].sub(/-/,"."), m[1], asset["name"], digest, asset["browser_download_url"]]
            end
            row=rows.sort_by{|r| r[0].split(".").map(&:to_i)}.last
            puts row.join("\n") if row
          rescue StandardError
            exit 1
          end
        ' "$release_json" "$EXT" > "$WORK_DIR/release-metadata" && [ -s "$WORK_DIR/release-metadata" ]; then
          api_version=$(sed -n '2p' "$WORK_DIR/release-metadata")
          if [ -z "$best_release_version" ] || version_greater "$api_version" "$best_release_version"; then
            # The first line is a normalized package-manager version; expose the
            # public date-counter version in the same shape as channel manifests.
            sed -n '2,5p' "$WORK_DIR/release-metadata" > "$WORK_DIR/metadata"
            best_release_version="$api_version"
            manifest_source=""
            detail "Release API found newer published $EXT version: v$api_version"
          fi
        fi
      fi
    done
  fi
  [ -s "$WORK_DIR/metadata" ] || die "No valid published $EXT release manifest is available"
  ver=$(sed -n '1p' "$WORK_DIR/metadata")
  name=$(sed -n '2p' "$WORK_DIR/metadata")
  checksum=$(sed -n '3p' "$WORK_DIR/metadata")
  release_url=$(sed -n '4p' "$WORK_DIR/metadata")
  PACKAGE_FILE="$WORK_DIR/$name"
  detail "Verified published $EXT version: $ver"
  # Prefer the source that returned a valid manifest.  The release asset is
  # kept as a fallback, while mirrors are attempted with a bounded timeout.
  package_urls="$release_url https://raw.githubusercontent.com/$REPO/package/$PACKAGE_REF/$name https://cdn.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF/$name https://fastly.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF/$name"
  if [ -n "$manifest_source" ]; then
    package_urls="$manifest_source/$name $package_urls"
  fi
  seen_urls=""
  step "Downloading and verifying OpenKill $ver"
  for url in $package_urls; do
    [ -n "$url" ] || continue
    case " $seen_urls " in *" $url "*) continue;; esac
    seen_urls="$seen_urls $url"
    detail "Trying package download: $url"
    if download "$url" "$PACKAGE_FILE" 300 1 &&
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
  rm -rf /etc/openkill /tmp/etc/openkill /tmp/openkill /tmp/openkill.log /tmp/openkill-watchdog.lock /tmp/openkill-proxy-address.lock
  rm -f /etc/config/openkill /tmp/luci-indexcache
  printf 'OpenKill removed; shared system dependencies were retained.\n'
}

[ "$ACTION" = uninstall ] && { step "Removing OpenKill and its runtime data"; uninstall; exit 0; }
step "Detecting system: package manager=$PM, architecture=$(uname -m 2>/dev/null || echo unknown)"
detail "Installation log: ${INSTALL_LOG:-unavailable}"
install_dependencies
[ -n "$PACKAGE_FILE" ] || resolve_package
[ -f "$PACKAGE_FILE" ] || die "Package file not found"
# The package transaction itself has no feed dependency.  If a required
# runtime dependency was missing, install_dependencies already selected a
# compatible FEED_CONFIG; otherwise keep it empty so opkg uses its native
# system configuration exactly once.  Passing a second full feed file makes
# some opkg builds parse firmware sources twice and emit duplicate-src warnings.
backup_config
step "Installing OpenKill ${ver:-local package}"
if [ "$PM" = opkg ]; then pm_run install "$PACKAGE_FILE"; else pm_run add --allow-untrusted "$PACKAGE_FILE"; fi
step "Validating installed service and runtime"
validate_install
install_core
download_databases
# Remove credentials and generated files left by older oixCloud-based builds.
if command -v uci >/dev/null 2>&1; then
  for opt in oix_token oix_email oix_passwd oix_checkin oix_checkin_interval oix_checkin_multiple oix_params oix_default_params oix_show_info_page; do
    uci -q delete "openkill.config.$opt" || true
  done
  uci -q commit openkill || true
fi
rm -f /tmp/oix_checkin /tmp/oix_info /tmp/openkill_oix_version.json
rm -f /tmp/openkill_version_history.json /tmp/openkill_version_history_openkill.json
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
step "Completing installation and retaining recovery backup"
detail "Detailed installation log: ${INSTALL_LOG:-unavailable}"
printf 'OpenKill %s installation/update complete.\n' "${ver:-local package}"
