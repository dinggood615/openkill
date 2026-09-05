#!/bin/sh
# OpenKill installer
set -eu

REPO="dinggood615/openkill"
PACKAGE_REF="master"
PROJECT_VERSION="2026-1042"
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
  # json is bundled with the supported Ruby runtimes on several OpenWrt
  # releases and has no standalone package there.  Treat the split package as
  # optional when the interpreter already provides it.
  if [ "$dep" = "ruby-json" ] && ruby -rjson -e 'exit 0' >/dev/null 2>&1; then return 0; fi
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
  if [ "$PM" = opkg ]; then
    required="bash curl ca-bundle ip-full ruby ruby-yaml lua kmod-tun unzip dnsmasq-full luci-compat"
    optional="ruby-json ruby-base64 ruby-psych ruby-pstore kmod-inet-diag"
    if command -v fw4 >/dev/null 2>&1; then required="$required kmod-nft-tproxy"
    else required="$required kmod-ipt-tproxy iptables-mod-tproxy ipset"; optional="$optional kmod-ipt-extra kmod-ipt-nat iptables-mod-extra"; fi
  else
    required="bash curl ca-certificates ip-full ruby ruby-yaml lua kmod-tun unzip dnsmasq-full luci-compat"
    optional="ruby-json ruby-base64 ruby-psych ruby-pstore kmod-inet-diag"
      if command -v fw4 >/dev/null 2>&1; then required="$required kmod-nft-tproxy"
      else required="$required ipset iptables-mod-tproxy"; fi
  fi

  # Repairs and updates normally run on a router that already has the
  # runtime.  Avoid refreshing every feed in that case; a blocked mirror can
  # otherwise add minutes before the actual package download starts.
  need_feed=0
  for dep in $required; do
    if [ "$PM" = opkg ]; then
      opkg status "$dep" 2>/dev/null | grep -q '^Status:.* installed$' || { need_feed=1; break; }
    else
      apk info -e "$dep" >/dev/null 2>&1 || { need_feed=1; break; }
    fi
  done
  if [ "$need_feed" -eq 1 ]; then
    prepare_feeds
  else
    FEED_CONFIG=""
    log "Required dependencies already installed; feed refresh skipped"
  fi
  for dep in $required; do install_dependency "$dep" || die "Required dependency could not be installed: $dep"; done
  # Split Ruby modules are optional when the interpreter already provides the
  # feature.  Only query their package names when a required dependency made
  # a feed refresh necessary.
 if [ "$need_feed" -eq 1 ]; then
   for dep in $optional; do install_dependency "$dep" || log "Optional dependency unavailable: $dep"; done
 fi
 # YAML and JSON are required for configuration and the release manifest.
  if ! ruby -ryaml -rjson -e 'exit 0' >/dev/null 2>&1; then
    # Some firmware splits JSON/Base64/Psych/PStore into optional packages.
    # Retry those packages only when the interpreter really lacks a module;
    # this keeps the common already-installed path network-free.
    [ "$need_feed" -eq 1 ] || prepare_feeds
    for dep in $optional; do install_dependency "$dep" || log "Optional dependency unavailable: $dep"; done
  fi
  ruby -ryaml -rjson -e 'exit 0' || die "Ruby YAML/JSON runtime is incomplete"
}

download(){
  case "$1" in https://*) ;; *) die "HTTPS URL required";; esac
  # Metadata is passed a short timeout by callers; archives get a larger
  # bounded window.  The speed limit terminates a dead TLS stream promptly.
  timeout="${3:-120}"
  if command -v curl >/dev/null 2>&1; then
    curl -fL -sS --retry 1 --connect-timeout 8 --max-time "$timeout" \
      --speed-time 20 --speed-limit 256 "$1" -o "$2"
  elif command -v uclient-fetch >/dev/null 2>&1; then
    uclient-fetch -q -T "$timeout" -O "$2" "$1"
  else
    wget -q -T "$timeout" -O "$2" "$1"
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
    if score=$(curl -fsSL -o /dev/null -w '%{time_total}' --connect-timeout 8 --max-time 15 --speed-time 8 --speed-limit 64 "$base/$rel" 2>/dev/null); then
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
  sh -n /usr/share/openkill/openkill_core.sh || die "OpenKill core installer validation failed"
  sh -n /usr/share/openkill/openkill_update.sh || die "OpenKill updater validation failed"
  sh -n /usr/share/openkill/openkill_watchdog.sh || die "OpenKill watchdog validation failed"
  ruby -ryaml -rjson -e 'exit 0' || die "Ruby YAML/JSON runtime is incomplete"
}

resolve_package(){
  manifest="$WORK_DIR/latest.json"
  # Probe the manifest itself so the first successful source is also the
  # preferred package download mirror.  A source that returns a fast 404 is
  # never ranked as healthy.
  manifest_source=""
  if select_source "latest-$EXT.json"; then
    manifest_source="$SOURCE_ROOT"
  fi
  # Authoritative origin first; cached mirrors are only a connectivity fallback.
  for base in "$manifest_source" "https://raw.githubusercontent.com/$REPO/package/$PACKAGE_REF" "https://cdn.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF" "https://fastly.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF"; do
    [ -n "$base" ] || continue
    if download "$base/latest-$EXT.json" "$manifest" 30 >/dev/null 2>&1 &&
       ruby -rjson -e '
         d=JSON.parse(File.read(ARGV[0]))
         abort unless d["format"]==ARGV[1] && d["architecture"]=="all"
         abort unless d["version"].match?(/\A2026-[0-9]+\z/) && d["sha256"].match?(/\A[0-9a-f]{64}\z/)
         package_version = ARGV[1] == "apk" ? d["version"].sub("-", ".") : d["version"]
         expected="luci-app-openkill_#{package_version}_all.#{ARGV[1]}"
         abort unless d["filename"]==expected
         abort unless d["url"]=="https://github.com/"+ARGV[2]+"/releases/download/v"+d["version"]+"-"+ARGV[1]+"/"+expected
        puts [d["version"],d["filename"],d["sha256"],d["url"]]
       ' "$manifest" "$EXT" "$REPO" > "$WORK_DIR/metadata"; then
      manifest_source="$base"
      break
    fi
    : > "$WORK_DIR/metadata"
  done
  # Older package channels may not contain a manifest yet.  Query the release
  # API as a fallback so a newly published package is installable immediately.
  if [ ! -s "$WORK_DIR/metadata" ]; then
    release_json="$WORK_DIR/releases.json"
    for api in "https://api.github.com/repos/$REPO/releases?per_page=30" "https://ghfast.top/https://api.github.com/repos/$REPO/releases?per_page=30"; do
      if download "$api" "$release_json" 30 >/dev/null 2>&1; then
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
          # The first line is a normalized package-manager version; expose the
          # public date-counter version in the same shape as channel manifests.
          sed -n '2,5p' "$WORK_DIR/release-metadata" > "$WORK_DIR/metadata"
          break
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
  # Prefer the source that returned a valid manifest.  The release asset is
  # kept as a fallback, while mirrors are attempted with a bounded timeout.
  package_urls="$release_url https://raw.githubusercontent.com/$REPO/package/$PACKAGE_REF/$name https://cdn.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF/$name https://fastly.jsdelivr.net/gh/$REPO@package/$PACKAGE_REF/$name"
  if [ -n "$manifest_source" ]; then
    package_urls="$manifest_source/$name $package_urls"
  fi
  seen_urls=""
  for url in $package_urls; do
    [ -n "$url" ] || continue
    case " $seen_urls " in *" $url "*) continue;; esac
    seen_urls="$seen_urls $url"
    if download "$url" "$PACKAGE_FILE" 120 &&
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
# Even when dependencies were already present, install the local package
# through a deduplicated temporary config so stale system feeds cannot emit
# duplicate-src warnings during the package transaction.
[ -n "$FEED_CONFIG" ] || prepare_feeds no-update
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
printf 'OpenKill %s installation/update complete.\n' "${ver:-local package}"
