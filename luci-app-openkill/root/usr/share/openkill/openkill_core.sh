#!/bin/bash
# OpenKill official Mihomo (Meta) core installer.
# The core is resolved from MetaCubeX/mihomo's latest stable release so a
# package can install a working core even when package CI is still running.
. /lib/functions.sh
. /usr/share/openkill/log.sh
. /usr/share/openkill/uci.sh
. /usr/share/openkill/openkill_ps.sh

report_tip() {
   LOG_TIP "$1"
   if [ -t 1 ]; then printf '    %s\n' "$1"; fi
   return 0
}
report_error() {
   LOG_ERROR "$1"
   if [ -t 2 ]; then printf 'Error: %s\n' "$1" >&2; fi
   return 0
}

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

set_lock || { report_error "Unable to create OpenKill core lock"; exit 1; }
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
      *) report_error "Unsupported CPU architecture: $(uname -m 2>/dev/null)"; return 1 ;;
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
PROBE_FILE="/tmp/openkill-mihomo-probe.$$.bin"
SCORE_FILE="/tmp/openkill-mihomo-scores.$$.txt"
CORE_LV=""
ASSET_URL=""
ASSET_SHA256=""
ASSET_SIZE=""
RELEASE_SOURCE=""
ORDERED_DOWNLOAD_URLS=""
FASTEST_CORE_URL=""
FASTEST_CORE_TIME=""
cleanup_core_tmp() {
   rm -f "$RELEASE_JSON" "$DOWNLOAD_FILE" "$TMP_FILE" "$PROBE_FILE" \
      "$SCORE_FILE" "${SCORE_FILE}.sorted"
}
trap 'cleanup_core_tmp; del_lock' EXIT INT TERM

json_value() {
   if command -v jsonfilter >/dev/null 2>&1; then
      jsonfilter -i "$RELEASE_JSON" -e "@.$1" 2>/dev/null
      return $?
   fi
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
asset_info_from_release() {
   if command -v jsonfilter >/dev/null 2>&1; then
      asset_name="$1"
      asset_url=$(jsonfilter -i "$RELEASE_JSON" -e "@.assets[@.name='$asset_name'].browser_download_url" 2>/dev/null | sed -n '1p')
      asset_digest=$(jsonfilter -i "$RELEASE_JSON" -e "@.assets[@.name='$asset_name'].digest" 2>/dev/null | sed -n '1p' | sed 's/^sha256://')
      asset_size=$(jsonfilter -i "$RELEASE_JSON" -e "@.assets[@.name='$asset_name'].size" 2>/dev/null | sed -n '1p')
      case "$asset_url" in https://*) ;; *) return 1;; esac
      case "$asset_digest" in [0-9a-f][0-9a-f]*) ;; *) return 1;; esac
      [ -n "$asset_size" ] || return 1
      printf '%s\n%s\n%s\n' "$asset_url" "$asset_digest" "$asset_size"
      return 0
   fi
   ruby -rjson -e '
      begin
        d = JSON.parse(File.read(ARGV[0]))
        a = (d["assets"] || []).find { |x| x["name"] == ARGV[1] }
        abort unless a
        url = a["browser_download_url"].to_s
        digest = a["digest"].to_s.sub(/^sha256:/, "")
        abort unless url.start_with?("https://") && digest.match?(/\A[0-9a-f]{64}\z/)
        puts url
        puts digest
        puts a["size"].to_i
      rescue StandardError
        exit 1
      end
   ' "$RELEASE_JSON" "$1" 2>/dev/null
}

append_url_once() {
   candidate_url="$1"
   case " $CORE_CANDIDATES " in *" $candidate_url "*) ;; *) CORE_CANDIDATES="$CORE_CANDIDATES $candidate_url";; esac
}

proxy_url() {
   proxy_base="${1%/}"
   printf '%s/%s\n' "$proxy_base" "$2"
}

fetch_release() {
   local api_urls="" api seen_api release_info
   # The direct official API is the authority for the tag and SHA-256 digest.
   # A user-configured accelerator and bounded transport fallbacks are used only
   # when direct GitHub is unavailable.
   api_urls="$META_API"
   case "$github_address_mod" in
      0|""|https://cdn.jsdelivr.net/|https://fastly.jsdelivr.net/|https://testingcf.jsdelivr.net/) ;;
      *) api_urls="$api_urls $(proxy_url "$github_address_mod" "$META_API")" ;;
   esac
   api_urls="$api_urls https://ghfast.top/$META_API https://github.dpik.top/$META_API https://gh-proxy.com/$META_API"
   seen_api=""
   for api in $api_urls; do
      case " $seen_api " in *" $api "*) continue;; esac
      seen_api="$seen_api $api"
      rm -f "$RELEASE_JSON"
      report_tip "【$CORE_TYPE】Checking release metadata: $api"
      if curl -fsSL --connect-timeout 4 --max-time 10 --speed-time 6 --speed-limit 128 --retry 0 \
         -H 'Accept: application/vnd.github+json' -H 'User-Agent: OpenKill-installer' \
         "$api" -o "$RELEASE_JSON" 2>/dev/null; then
         CORE_LV=$(json_value tag_name)
         case "$CORE_LV" in v[0-9]*.[0-9]*) ;; *) CORE_LV="";; esac
         if [ -n "$CORE_LV" ]; then
            ASSET_NAME="mihomo-${CPU_MODEL}-${CORE_LV}.gz"
            release_info=$(asset_info_from_release "$ASSET_NAME") || release_info=""
            if [ -n "$release_info" ]; then
               ASSET_URL=$(printf '%s\n' "$release_info" | sed -n '1p')
               ASSET_SHA256=$(printf '%s\n' "$release_info" | sed -n '2p')
               ASSET_SIZE=$(printf '%s\n' "$release_info" | sed -n '3p')
               case "$ASSET_SHA256" in [0-9a-f][0-9a-f]*) RELEASE_SOURCE="$api"; return 0;; esac
            fi
         fi
      fi
   done
   return 1
}

probe_core_url() {
   probe_url="$1"
   rm -f "$PROBE_FILE"
   probe_result=$(curl -fL -sS --range 0-4095 --max-filesize 8192 \
      --connect-timeout 4 --max-time 8 --speed-time 4 --speed-limit 128 \
      -o "$PROBE_FILE" -w '%{http_code} %{time_starttransfer}' "$probe_url" 2>/dev/null) || {
      rm -f "$PROBE_FILE"
      return 1
   }
   probe_code=$(printf '%s\n' "$probe_result" | awk '{print $1}')
   probe_time=$(printf '%s\n' "$probe_result" | awk '{print $2}')
   case "$probe_code" in 200|206) ;; *) rm -f "$PROBE_FILE"; return 1;; esac
   probe_magic=$(dd if="$PROBE_FILE" bs=1 count=2 2>/dev/null | od -An -tx1 | tr -d '[:space:]')
   rm -f "$PROBE_FILE"
   [ "$probe_magic" = "1f8b" ] || return 1
   printf '%s\n' "$probe_time"
}

rank_core_sources() {
   sorted_score_file="${SCORE_FILE}.sorted"
   : > "$SCORE_FILE"
   CORE_CANDIDATES=""
   append_url_once "$ASSET_URL"
   case "$github_address_mod" in
      0|""|https://cdn.jsdelivr.net/|https://fastly.jsdelivr.net/|https://testingcf.jsdelivr.net/) ;;
      *) append_url_once "$(proxy_url "$github_address_mod" "$ASSET_URL")" ;;
   esac
   # GitHub Release files are not repository files, so jsDelivr must not be
   # used here. These are transport-only fallbacks for the verified asset.
   append_url_once "https://ghfast.top/$ASSET_URL"
   append_url_once "https://github.dpik.top/$ASSET_URL"
   append_url_once "https://gh-proxy.com/$ASSET_URL"
   for core_url in $CORE_CANDIDATES; do
      report_tip "【$CORE_TYPE】Testing core download source: $core_url"
      if core_score=$(probe_core_url "$core_url"); then
         printf '%s %s\n' "$core_score" "$core_url" >> "$SCORE_FILE"
      fi
   done
   ORDERED_DOWNLOAD_URLS=""
   if [ -s "$SCORE_FILE" ]; then
      sort -n "$SCORE_FILE" > "$sorted_score_file"
      FASTEST_CORE_TIME=$(awk 'NR==1 {print $1}' "$sorted_score_file")
      FASTEST_CORE_URL=$(awk 'NR==1 {print $2}' "$sorted_score_file")
      while IFS=' ' read -r core_score core_url; do
         ORDERED_DOWNLOAD_URLS="$ORDERED_DOWNLOAD_URLS $core_url"
      done < "$sorted_score_file"
   fi
   for core_url in $CORE_CANDIDATES; do
      case " $ORDERED_DOWNLOAD_URLS " in *" $core_url "*) ;; *) ORDERED_DOWNLOAD_URLS="$ORDERED_DOWNLOAD_URLS $core_url";; esac
   done
   rm -f "$SCORE_FILE" "$sorted_score_file"
   [ -z "$FASTEST_CORE_URL" ] || report_tip "【$CORE_TYPE】Selected fastest valid core source (${FASTEST_CORE_TIME}s): $FASTEST_CORE_URL"
}

download_core() {
   core_url="$1"
   PARTIAL_FILE="/tmp/openkill-mihomo-${CPU_MODEL}-${CORE_LV}.gz.part"
   rm -f "$DOWNLOAD_FILE" "$TMP_FILE"
   if [ -s "$PARTIAL_FILE" ]; then
      report_tip "【$CORE_TYPE】Resuming interrupted download from $(basename "$PARTIAL_FILE")"
      curl -fL -# -C - --connect-timeout 8 --max-time 300 --speed-time 30 --speed-limit 512 --retry 0 \
         "$core_url" -o "$PARTIAL_FILE" || return 1
   else
      curl -fL -# --connect-timeout 8 --max-time 300 --speed-time 30 --speed-limit 512 --retry 0 \
         "$core_url" -o "$PARTIAL_FILE" || return 1
   fi
   if [ -n "$ASSET_SHA256" ]; then
      actual_sha256=$(sha256sum "$PARTIAL_FILE" 2>/dev/null | awk '{print $1}')
      if [ "$actual_sha256" != "$ASSET_SHA256" ]; then
         report_error "【$CORE_TYPE】SHA256 verification failed for $core_url"
         rm -f "$PARTIAL_FILE"
         return 1
      fi
   else
      report_tip "【$CORE_TYPE】Manual core has no release digest; validating archive and executable only"
   fi
   mv -f "$PARTIAL_FILE" "$DOWNLOAD_FILE" || return 1
   gzip -t "$DOWNLOAD_FILE" >/dev/null 2>&1 || return 1
   gzip -dc "$DOWNLOAD_FILE" > "$TMP_FILE" 2>/dev/null || return 1
   chmod 4755 "$TMP_FILE" 2>/dev/null || return 1
   "$TMP_FILE" -v >/dev/null 2>&1 || return 1
   return 0
}

restart=0
if [ -n "$DIRECT_CORE_URL" ]; then
   CORE_LV="manual"
   report_tip "【$CORE_TYPE】Downloading the manually supplied core..."
   download_core "$DIRECT_CORE_URL" || { report_error "【$CORE_TYPE】Manual core validation failed"; dec_job_counter_and_restart "0"; exit 1; }
   restart=1
else
   if ! fetch_release; then
      report_error "【$CORE_TYPE】Unable to resolve the latest official Mihomo release or architecture asset"
      dec_job_counter_and_restart "0"
      exit 1
   fi
   if [ "$CORE_CV" = "$CORE_LV" ] && [ -x "$TARGET_CORE_PATH" ]; then
      report_tip "【$CORE_TYPE】Core $CORE_LV is already installed"
      dec_job_counter_and_restart "0"
      exit 0
   fi
    report_tip "【$CORE_TYPE】Official release metadata: $RELEASE_SOURCE"
    report_tip "【$CORE_TYPE】Downloading official stable Mihomo $CORE_LV (${ASSET_SIZE:-unknown} bytes)..."
    rank_core_sources
    downloaded=0
    for url in $ORDERED_DOWNLOAD_URLS; do
       if download_core "$url"; then
          downloaded=1
          break
       fi
       report_tip "【$CORE_TYPE】Source failed or did not pass validation; trying the next source"
    done
   if [ "$downloaded" -ne 1 ]; then
      report_error "【$CORE_TYPE】Core download or validation failed; current core was kept"
      dec_job_counter_and_restart "0"
      exit 1
   fi
   restart=1
fi

# Validate the candidate against the effective runtime configuration before
# replacing a working core. On first install no runtime file exists yet.
active_config="/etc/openkill/$(basename "$(uci_get_config config_path 2>/dev/null)")"
if [ -f "$active_config" ] && [ -s "$active_config" ]; then
   if ! /usr/share/openkill/openkill_validate.sh "$active_config" "$TMP_FILE" /etc/openkill; then
      report_error "Candidate core rejected the active configuration; installed core was kept"
      dec_job_counter_and_restart "0"
      exit 1
   fi
fi
if [ -s "$TARGET_CORE_PATH" ]; then
   cp -p "$TARGET_CORE_PATH" "$TARGET_CORE_PATH.previous" || {
      report_error "Cannot preserve previous core; update cancelled"
      dec_job_counter_and_restart "0"
      exit 1
   }
fi
if ! mv -f "$TMP_FILE" "$TARGET_CORE_PATH"; then
   report_error "【$CORE_TYPE】Core installation failed; current core was kept"
   dec_job_counter_and_restart "0"
   exit 1
fi
chmod 4755 "$TARGET_CORE_PATH" 2>/dev/null
chown root:root "$TARGET_CORE_PATH" 2>/dev/null
uci -q set openkill.config.core_type="Meta"
uci -q commit openkill
report_tip "【$CORE_TYPE】Core $CORE_LV installed successfully"
dec_job_counter_and_restart "$restart"
exit 0
