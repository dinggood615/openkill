#!/bin/bash
# OpenKill official Mihomo (Meta) core installer.
# The core is resolved from MetaCubeX/mihomo's latest stable release so a
# package can install a working core even when package CI is still running.
. /lib/functions.sh
. /usr/share/openkill/log.sh
. /usr/share/openkill/uci.sh
. /usr/share/openkill/openkill_curl.sh
. /usr/share/openkill/openkill_ps.sh

set_lock() {
   # Fresh OpenWrt installations may not have the shared lock directory yet.
   # Create it before opening the descriptor so the first core update cannot
   # fail before any download or validation takes place.
   mkdir -p /tmp/lock 2>/dev/null || return 1
   exec 872>"/tmp/lock/openkill_core.lock" 2>/dev/null
   flock -x 872 2>/dev/null
}
del_lock() {
   flock -u 872 2>/dev/null
   rm -rf "/tmp/lock/openkill_core.lock" 2>/dev/null
}

set_lock || { LOG_ERROR "Unable to create OpenKill core lock"; exit 1; }
inc_job_counter
trap 'del_lock' EXIT INT TERM

CORE_TYPE="Meta"
META_API="https://api.github.com/repos/MetaCubeX/mihomo/releases/latest"
github_address_mod=$(uci_get_config "github_address_mod" || echo 0)
small_flash_memory=$(uci_get_config "small_flash_memory" || echo 0)
# `core_version` is a release selector, not an architecture.  Older builds
# reused that field for both values, which could produce asset names such as
# `mihomo-v1.19.30-v1.19.30.gz` after a manual core update.  Keep the target
# architecture in its own optional UCI field and always validate it.
CPU_MODEL=$(uci_get_config "core_arch" || echo 0)
DIRECT_CORE_URL=""
[ -n "$2" ] && echo "$2" | grep -qE '^https?://' && DIRECT_CORE_URL="$2"

detect_core_model() {
   case "$CPU_MODEL" in
      linux-amd64-v1|linux-amd64-v2|linux-386|linux-arm64|linux-armv7|linux-armv6|linux-armv5|linux-mips64le|linux-mipsle-hardfloat|linux-mips-hardfloat|linux-riscv64|linux-s390x|linux-loong64-abi2)
         return 0
         ;;
      *) CPU_MODEL="" ;;
   esac
   case "$(uname -m 2>/dev/null)" in
      x86_64|amd64) CPU_MODEL="linux-amd64-v1" ;;
      i[3-6]86) CPU_MODEL="linux-386" ;;
      aarch64|arm64) CPU_MODEL="linux-arm64" ;;
      armv7l|armv7*) CPU_MODEL="linux-armv7" ;;
      armv6l|armv6*) CPU_MODEL="linux-armv6" ;;
      armv5*) CPU_MODEL="linux-armv5" ;;
      mips64el) CPU_MODEL="linux-mips64le" ;;
      mipsel) CPU_MODEL="linux-mipsle-hardfloat" ;;
      mips) CPU_MODEL="linux-mips-hardfloat" ;;
      riscv64) CPU_MODEL="linux-riscv64" ;;
      s390x) CPU_MODEL="linux-s390x" ;;
      loongarch64) CPU_MODEL="linux-loong64-abi2" ;;
      *) LOG_ERROR "Unsupported CPU architecture: $(uname -m 2>/dev/null)"; return 1 ;;
   esac
   uci -q set openkill.config.core_arch="$CPU_MODEL"
   uci -q commit openkill
}
if ! detect_core_model; then dec_job_counter_and_restart "0"; exit 1; fi

if [ "$small_flash_memory" != "1" ]; then
   TARGET_CORE_PATH="/etc/openkill/core/clash_meta"
   mkdir -p /etc/openkill/core
else
   TARGET_CORE_PATH="/tmp/etc/openkill/core/clash_meta"
   mkdir -p /tmp/etc/openkill/core
fi

CORE_CV=""
if [ -x "$TARGET_CORE_PATH" ]; then
   CORE_CV=$($TARGET_CORE_PATH -v 2>/dev/null | sed -n 's/.*\(v[0-9][0-9.]*\).*/\1/p' | head -n 1)
fi
RELEASE_JSON="/tmp/openkill-mihomo-release.$$.json"
DOWNLOAD_FILE="/tmp/openkill-mihomo.$$.gz"
TMP_FILE="${TARGET_CORE_PATH}.new.$$"
CORE_LV=""
ASSET_URL=""
cleanup_core_tmp() { rm -f "$RELEASE_JSON" "$DOWNLOAD_FILE" "$TMP_FILE"; }
trap 'cleanup_core_tmp; del_lock' EXIT INT TERM

json_value() {
   ruby -rjson -e '
      begin
        d = JSON.parse(File.read(ARGV[0]))
        value = ARGV[1].split(".").inject(d) { |v, k| v.is_a?(Hash) ? v[k] : nil }
        puts(value.to_s) unless value.nil?
      rescue StandardError
        exit 1
      end
   ' "$RELEASE_JSON" "$1" 2>/dev/null
}
asset_url_from_release() {
   ruby -rjson -e '
      begin
        d = JSON.parse(File.read(ARGV[0]))
        a = (d["assets"] || []).find { |x| x["name"] == ARGV[1] }
        puts(a["browser_download_url"].to_s) if a
      rescue StandardError
        exit 1
      end
   ' "$RELEASE_JSON" "$1" 2>/dev/null
}

fetch_release() {
   local api_urls=""
   case "$github_address_mod" in
      0|"") ;;
      https://cdn.jsdelivr.net/|https://fastly.jsdelivr.net/|https://testingcf.jsdelivr.net/) ;;
      *) api_urls="$github_address_mod$META_API" ;;
   esac
   api_urls="$api_urls $META_API https://ghfast.top/$META_API https://github.dpik.top/$META_API https://gh-proxy.com/$META_API"
   for api in $api_urls; do
     rm -f "$RELEASE_JSON"
      # Keep each API fallback bounded; a filtered endpoint must not delay
      # the remaining official/mirror endpoints for several minutes.
      if curl -fsSL --connect-timeout 6 --max-time 20 --speed-time 8 --speed-limit 128 --retry 1 \
         -H 'Accept: application/vnd.github+json' -H 'User-Agent: OpenKill-installer' \
         "$api" -o "$RELEASE_JSON" 2>/dev/null; then
         CORE_LV=$(json_value tag_name)
         case "$CORE_LV" in v[0-9]*.[0-9]*) ;; *) CORE_LV="";; esac
         if [ -n "$CORE_LV" ]; then
            ASSET_NAME="mihomo-${CPU_MODEL}-${CORE_LV}.gz"
            ASSET_URL=$(asset_url_from_release "$ASSET_NAME")
            [ -n "$ASSET_URL" ] && return 0
         fi
      fi
   done
   return 1
}

download_core() {
  local url="$1"
  rm -f "$DOWNLOAD_FILE" "$TMP_FILE"
   # Core archives are large, but a stalled endpoint should fail fast and
   # let the next mirror take over.  A normal WAN link remains unaffected.
   OPENKILL_CURL_CONNECT_TIMEOUT=8 OPENKILL_CURL_MAX_TIME=90 \
   OPENKILL_CURL_SPEED_TIME=15 OPENKILL_CURL_SPEED_LIMIT=1024 \
   OPENKILL_CURL_RETRIES=0 SHOW_DOWNLOAD_PROGRESS=1 \
   DOWNLOAD_FILE_CURL "$url" "$DOWNLOAD_FILE" "$TARGET_CORE_PATH"
   [ "$?" -eq 0 ] || return 1
   gzip -t "$DOWNLOAD_FILE" >/dev/null 2>&1 || return 1
   gzip -dc "$DOWNLOAD_FILE" > "$TMP_FILE" 2>/dev/null || return 1
   chmod 4755 "$TMP_FILE" 2>/dev/null || return 1
   "$TMP_FILE" -v >/dev/null 2>&1 || return 1
   return 0
}

restart=0
if [ -n "$DIRECT_CORE_URL" ]; then
   CORE_LV="manual"
   LOG_TIP "【$CORE_TYPE】Downloading the manually supplied core..."
   download_core "$DIRECT_CORE_URL" || { LOG_ERROR "【$CORE_TYPE】Manual core validation failed"; dec_job_counter_and_restart "0"; exit 1; }
   restart=1
else
   if ! fetch_release; then
      LOG_ERROR "【$CORE_TYPE】Unable to resolve the latest official Mihomo release or architecture asset"
      dec_job_counter_and_restart "0"
      exit 1
   fi
   if [ "$CORE_CV" = "$CORE_LV" ] && [ -x "$TARGET_CORE_PATH" ]; then
      LOG_TIP "【$CORE_TYPE】Core $CORE_LV is already installed"
      dec_job_counter_and_restart "0"
      exit 0
   fi
   LOG_TIP "【$CORE_TYPE】Downloading official stable Mihomo $CORE_LV..."
   DOWNLOAD_URLS="$ASSET_URL"
   case "$github_address_mod" in
      0|"") ;;
      https://cdn.jsdelivr.net/|https://fastly.jsdelivr.net/|https://testingcf.jsdelivr.net/) DOWNLOAD_URLS="${github_address_mod}gh/MetaCubeX/mihomo@${CORE_LV}/${ASSET_NAME} $DOWNLOAD_URLS" ;;
      *) DOWNLOAD_URLS="$github_address_mod$ASSET_URL $DOWNLOAD_URLS" ;;
   esac
   DOWNLOAD_URLS="$DOWNLOAD_URLS https://ghfast.top/$ASSET_URL https://github.dpik.top/$ASSET_URL https://gh-proxy.com/$ASSET_URL"
  downloaded=0
   seen_urls=""
  for url in $DOWNLOAD_URLS; do
      case " $seen_urls " in *" $url "*) continue;; esac
      seen_urls="$seen_urls $url"
      if download_core "$url"; then downloaded=1; break; fi
   done
   if [ "$downloaded" -ne 1 ]; then
      LOG_ERROR "【$CORE_TYPE】Core download or validation failed; current core was kept"
      dec_job_counter_and_restart "0"
      exit 1
   fi
   restart=1
fi

if ! mv -f "$TMP_FILE" "$TARGET_CORE_PATH"; then
   LOG_ERROR "【$CORE_TYPE】Core installation failed; current core was kept"
   dec_job_counter_and_restart "0"
   exit 1
fi
chmod 4755 "$TARGET_CORE_PATH" 2>/dev/null
chown root:root "$TARGET_CORE_PATH" 2>/dev/null
uci -q set openkill.config.core_type="Meta"
uci -q commit openkill
LOG_TIP "【$CORE_TYPE】Core $CORE_LV installed successfully"
dec_job_counter_and_restart "$restart"
exit 0
