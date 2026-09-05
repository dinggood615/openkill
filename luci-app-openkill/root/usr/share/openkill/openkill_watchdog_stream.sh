#!/bin/sh
# Optional streaming-unlock checks run outside the core health loop.  A
# timestamp and lock make the task cheap when it is disabled and prevent
# overlapping Lua probes after a reload.
. /usr/share/openkill/log.sh
. /usr/share/openkill/uci.sh

LOCK_DIR="/tmp/openkill-watchdog-stream.lock"
STATE_FILE="/tmp/openkill-watchdog-stream.last"
mkdir "$LOCK_DIR" 2>/dev/null || exit 0
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT INT TERM

[ "$(uci_get_config "stream_auto_select" || echo 0)" = "1" ] || exit 0
[ "$(uci_get_config "router_self_proxy" || echo 1)" = "1" ] || exit 0

interval="$(uci_get_config "stream_auto_select_interval" || echo 30)"
case "$interval" in
   ''|*[!0-9]*|0) interval=30 ;;
esac
now=$(date +%s 2>/dev/null || echo 0)
last=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
case "$last" in ''|*[!0-9]*) last=0 ;; esac
[ "$now" -ge "$last" ] && [ "$((now - last))" -lt "$((interval * 60))" ] && exit 0
printf '%s\n' "$now" > "$STATE_FILE"

run_probe() {
   label="$1"
   option="$2"
   value="$(uci_get_config "$option" || echo 0)"
   [ "$value" = "1" ] || return 0
   LOG_INFO "[$label] Start auto-select unlock proxy..."
   /usr/share/openkill/openkill_streaming_unlock.lua "$label" >> /tmp/openkill.log 2>&1
}

run_probe "Netflix" stream_auto_select_netflix
run_probe "Disney Plus" stream_auto_select_disney
run_probe "Google Not CN" stream_auto_select_google_not_cn
run_probe "YouTube Premium" stream_auto_select_ytb
run_probe "Amazon Prime Video" stream_auto_select_prime_video
run_probe "HBO Max" stream_auto_select_hbo_max
run_probe "TVB Anywhere+" stream_auto_select_tvb_anywhere
run_probe "DAZN" stream_auto_select_dazn
run_probe "Paramount Plus" stream_auto_select_paramount_plus
run_probe "Discovery Plus" stream_auto_select_discovery_plus
run_probe "Bilibili" stream_auto_select_bilibili
run_probe "OpenAI" stream_auto_select_openai
run_probe "Claude" stream_auto_select_claude
run_probe "Gemini" stream_auto_select_gemini
