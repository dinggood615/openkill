#!/bin/sh
# Build a small dnsmasq domain block list for the optional anti-AD profile.
# The Mihomo rule provider is added by yml_change.sh for traffic-level
# enforcement; this file covers clients that are fast-pathed around the core.
# `local=/domain/` prevents dnsmasq from forwarding A, AAAA, CNAME, HTTPS and
# SVCB queries for a blocked name; it deliberately returns no synthetic IP.
. /usr/share/openkill/log.sh
. /usr/share/openkill/openkill_curl.sh
. /usr/share/openkill/uci.sh

mode="$(uci_get_config adblock_mode 2>/dev/null || echo off)"
state_file=/tmp/openkill-adblock.state
case "$mode" in standard|enhanced) ;; *)
   DNSMASQ_SECTION="$(uci -q show dhcp 2>/dev/null | sed -n 's/^dhcp\.\([^.=]*\)=dnsmasq$/\1/p' | head -n 1)"
   [ -n "$DNSMASQ_SECTION" ] || DNSMASQ_SECTION="@dnsmasq[0]"
   DNSMASQ_UCI="dhcp.${DNSMASQ_SECTION}"
   conf_dir="$(uci -q get "$DNSMASQ_UCI.confdir" 2>/dev/null)"
   [ -n "$conf_dir" ] || conf_dir=/tmp/dnsmasq.d
   rm -f "${conf_dir%/}/dnsmasq_openkill_adblock.conf"
   rm -f "$state_file"
   exit 0
   ;;
esac

cache_dir=/etc/openkill/cache
cache_file="$cache_dir/anti-ad-domains.txt"
DNSMASQ_SECTION="$(uci -q show dhcp 2>/dev/null | sed -n 's/^dhcp\.\([^.=]*\)=dnsmasq$/\1/p' | head -n 1)"
[ -n "$DNSMASQ_SECTION" ] || DNSMASQ_SECTION="@dnsmasq[0]"
DNSMASQ_UCI="dhcp.${DNSMASQ_SECTION}"
conf_dir="$(uci -q get "$DNSMASQ_UCI.confdir" 2>/dev/null)"
[ -n "$conf_dir" ] || conf_dir=/tmp/dnsmasq.d
conf_dir=${conf_dir%/}
conf_file="$conf_dir/dnsmasq_openkill_adblock.conf"
interval="$(uci_get_config adblock_update_interval 2>/dev/null || echo 86400)"
case "$interval" in ''|*[!0-9]*|0) interval=86400 ;; esac
url="$(uci_get_config adblock_dns_url 2>/dev/null || echo https://anti-ad.net/anti-ad-domains.txt)"
case "$url" in https://*) ;; *) LOG_WARN "Adblock URL is not HTTPS; keeping the last valid list."; url="" ;; esac

mkdir -p "$cache_dir" "$conf_dir" 2>/dev/null || exit 1
refresh=1
if [ -s "$cache_file" ]; then
   now=$(date +%s 2>/dev/null || echo 0)
   mtime=$(date -r "$cache_file" +%s 2>/dev/null || echo 0)
   [ "$mtime" -gt 0 ] && [ $((now - mtime)) -lt "$interval" ] && refresh=0
fi

if [ "$refresh" -eq 1 ] && [ -n "$url" ]; then
   tmp="${cache_file}.download.$$"
   if DOWNLOAD_FILE_CURL "$url" "$tmp" "$cache_file" >/dev/null 2>&1; then
      valid_count=$(awk '!/^([[:space:]]*#|[[:space:]]*$)/ && $0 ~ /^([A-Za-z0-9_*-]+\.)+[A-Za-z]{2,}$/ { count++ } END { print count + 0 }' "$tmp" 2>/dev/null)
      if [ "${valid_count:-0}" -ge 10 ] && ! grep -Eiq '<html|<!doctype|^error' "$tmp" 2>/dev/null; then
         mv -f "$tmp" "$cache_file"
      else
         rm -f "$tmp"
         LOG_WARN "Adblock list validation failed; keeping the last valid list."
      fi
   else
      rm -f "$tmp"
      LOG_WARN "Adblock list download failed; keeping the last valid list."
   fi
fi

[ -s "$cache_file" ] || { rm -f "$conf_file"; printf '%s\n' "mode=$mode" "effective=0" "reason=no-valid-list" > "$state_file"; exit 0; }

allow_file=/etc/openkill/custom/openkill_adblock_allow.list
block_file=/etc/openkill/custom/openkill_adblock_block.list
tmp_conf="${conf_file}.new.$$"
{
   awk -v allow="$allow_file" -v block="$block_file" '
      BEGIN {
         while ((getline line < allow) > 0) { gsub(/[[:space:]]/, "", line); if (line ~ /^([A-Za-z0-9_-]+\.)+[A-Za-z]{2,}$/) ok[line]=1 }
         close(allow)
         while ((getline line < block) > 0) { gsub(/[[:space:]]/, "", line); if (line ~ /^([A-Za-z0-9_-]+\.)+[A-Za-z]{2,}$/) deny[line]=1 }
         close(block)
      }
      !/^([[:space:]]*#|[[:space:]]*$)/ {
         gsub(/[[:space:]]/, "", $0)
         if ($0 ~ /^([A-Za-z0-9_-]+\.)+[A-Za-z]{2,}$/ && !ok[$0] && !seen[$0] && !deny[$0]) {
            print "local=/" $0 "/"
            seen[$0]=1
         }
      }
   ' "$cache_file"
   if [ -s "$block_file" ]; then
      awk '!/^([[:space:]]*#|[[:space:]]*$)/ { gsub(/[[:space:]]/, "", $0); if ($0 ~ /^([A-Za-z0-9_-]+\.)+[A-Za-z]{2,}$/) print "local=/" $0 "/" }' "$block_file"
   fi
} > "$tmp_conf" || { rm -f "$tmp_conf"; exit 1; }

if [ -s "$tmp_conf" ]; then
   mv -f "$tmp_conf" "$conf_file"
   printf '%s\n' "mode=$mode" "effective=1" "domains=$(wc -l < "$conf_file" 2>/dev/null || echo 0)" "updated=$(date +%s 2>/dev/null || echo 0)" > "$state_file"
else
   rm -f "$tmp_conf" "$conf_file"
   printf '%s\n' "mode=$mode" "effective=0" "reason=empty-render" > "$state_file"
fi
exit 0
