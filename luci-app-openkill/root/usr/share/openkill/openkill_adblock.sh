#!/bin/sh
# Generate the DNS and Mihomo anti-AD views from one validated domain list.
# The two consumers therefore share a generation and an allow/block policy;
# neither view downloads an independent rule set.
. /usr/share/openkill/log.sh
. /usr/share/openkill/openkill_curl.sh
. /usr/share/openkill/uci.sh

mode="$(uci_get_config adblock_mode 2>/dev/null || echo off)"
state_file=/tmp/openkill-adblock.state
provider_dir=/etc/openkill/rule_provider
provider_file="$provider_dir/openkill-anti-ad.yaml"

DNSMASQ_SECTION="$(uci -q -X show dhcp 2>/dev/null | sed -n 's/^dhcp\.\([^.=]*\)=dnsmasq$/\1/p' | head -n 1)"
[ -n "$DNSMASQ_SECTION" ] || DNSMASQ_SECTION="@dnsmasq[0]"
DNSMASQ_UCI="dhcp.${DNSMASQ_SECTION}"
DEFAULT_DNSMASQ_CFGID="$(uci -q show "$DNSMASQ_UCI" | awk 'NR==1 {split($0, conf, /[.=]/); print conf[2]}')"
if [ -f "/tmp/etc/dnsmasq.conf.$DEFAULT_DNSMASQ_CFGID" ]; then
   conf_dir="$(awk -F '=' '/^conf-dir=/ {print $2}' "/tmp/etc/dnsmasq.conf.$DEFAULT_DNSMASQ_CFGID")"
else
   conf_dir=""
fi
[ -n "$conf_dir" ] || conf_dir="$(uci -q get "$DNSMASQ_UCI.confdir" 2>/dev/null)"
[ -n "$conf_dir" ] || conf_dir=/tmp/dnsmasq.d
conf_dir=${conf_dir%/}
conf_file="$conf_dir/dnsmasq_openkill_adblock.conf"

case "$mode" in
   standard|enhanced) ;;
   *)
      rm -f "$conf_file" "$provider_file" "$state_file"
      exit 0
      ;;
esac

cache_dir=/etc/openkill/cache
cache_file="$cache_dir/anti-ad-domains.txt"
raw_file="${cache_file}.raw.$$"
normalized_file="${cache_file}.normalized.$$"
allow_file=/etc/openkill/custom/openkill_adblock_allow.list
block_file=/etc/openkill/custom/openkill_adblock_block.list
policy_allow="/tmp/openkill-adblock-allow.$$"
policy_block="/tmp/openkill-adblock-block.$$"
tmp_conf="${conf_file}.new.$$"
tmp_provider="${provider_file}.new.$$"
cleanup() { rm -f "$raw_file" "$normalized_file" "$policy_allow" "$policy_block" "$tmp_conf" "$tmp_provider"; }
trap cleanup 0 1 2 3 15

url="$(uci_get_config adblock_rule_url 2>/dev/null || true)"
[ -n "$url" ] || url="$(uci_get_config adblock_dns_url 2>/dev/null || true)"
[ -n "$url" ] || url=https://anti-ad.net/anti-ad-domains.txt
case "$url" in https://*) ;; *) LOG_WARN "Adblock URL is not HTTPS; keeping the last valid list."; url="" ;; esac

mkdir -p "$cache_dir" "$conf_dir" "$provider_dir" 2>/dev/null || exit 1
refresh=1
if [ -s "$cache_file" ]; then
   now=$(date +%s 2>/dev/null || echo 0)
   interval="$(uci_get_config adblock_update_interval 2>/dev/null || echo 86400)"
   case "$interval" in ''|*[!0-9]*|0) interval=86400 ;; esac
   mtime=$(date -r "$cache_file" +%s 2>/dev/null || echo 0)
   [ "$mtime" -gt 0 ] && [ $((now - mtime)) -lt "$interval" ] && refresh=0
fi

# Convert anti-AD text, Clash YAML domain payloads and hosts-style entries to
# the one canonical domain format consumed by both generated backends.
normalize_domains() {
   awk -v quote="'" '
      function emit(value) {
         gsub(/["`;,]/, "", value); gsub(quote, "", value)
         sub(/^\+\./, "", value); sub(/^\|\|/, "", value); sub(/\^.*$/, "", value)
         gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
         value=tolower(value)
         if (value ~ /^([a-z0-9_-]+\.)+[a-z]{2,}$/) print value
      }
      !/^[[:space:]]*#/ && !/^[[:space:]]*$/ {
         line=$0; sub(/[[:space:]]+#.*/, "", line)
         gsub(/^[[:space:]]*-[[:space:]]*/, "", line)
         sub(/^[[:space:]]*(domain|host)[[:space:]]*:[[:space:]]*/, "", line)
         gsub(/[[:space:]]+/, " ", line)
         field_count=split(line, fields, /[[:space:]]+/)
         for (i=1; i<=field_count; i++) {
            value=fields[i]
            if (value ~ /^https?:\/\// || value == "payload:" || value == "domain:") continue
            emit(value)
         }
      }
   ' "$1" | sort -u
}

if [ "$refresh" -eq 1 ] && [ -n "$url" ]; then
   if DOWNLOAD_FILE_CURL "$url" "$raw_file" "$cache_file" >/dev/null 2>&1 &&
      ! grep -Eiq '<html|<!doctype|^[[:space:]]*error([[:space:]]|$)' "$raw_file" 2>/dev/null &&
      normalize_domains "$raw_file" > "$normalized_file" 2>/dev/null &&
      [ "$(wc -l < "$normalized_file" 2>/dev/null || echo 0)" -ge 10 ]; then
      mv -f "$normalized_file" "$cache_file"
   else
      rm -f "$normalized_file"
      LOG_WARN "Adblock list validation failed; keeping the last valid list."
   fi
fi

[ -s "$cache_file" ] || {
   rm -f "$conf_file" "$provider_file"
   printf '%s\n' "mode=$mode" "effective=0" "provider_effective=0" "reason=no-valid-list" > "$state_file"
   exit 0
}

# Build the same allow/block sets for dnsmasq and the core. RustDesk domains
# are only added here when its scoped compatibility switch is enabled; this
# prevents the ad filter from being the reason its control service is hidden.
cat "$allow_file" 2>/dev/null > "$policy_allow" || :
if [ "$(uci_get_config rustdesk_compatibility 2>/dev/null || echo 0)" = 1 ]; then
   for domain in $(uci_get_config rustdesk_server_domains 2>/dev/null); do
      printf '%s\n' "$domain" >> "$policy_allow"
   done
fi
cat "$block_file" 2>/dev/null > "$policy_block" || :

awk -v allow="$policy_allow" -v block="$policy_block" '
   function read_list(file, target, line) {
      while ((getline line < file) > 0) { gsub(/[[:space:]]/, "", line); line=tolower(line); if (line ~ /^([a-z0-9_-]+\.)+[a-z]{2,}$/) target[line]=1 }
      close(file)
   }
   function under(domain, parent) {
      return domain == parent || (length(domain) > length(parent) && substr(domain, length(domain) - length(parent), length(parent) + 1) == "." parent)
   }
   function listed(domain, set, key) {
      for (key in set) if (under(domain, key)) return 1
      return 0
   }
   BEGIN { read_list(allow, ok); read_list(block, deny) }
   { domain=tolower($0); if (domain ~ /^([a-z0-9_-]+\.)+[a-z]{2,}$/ && !listed(domain, ok) && !listed(domain, deny) && !seen[domain]) { print "local=/" domain "/"; seen[domain]=1 } }
' "$cache_file" > "$tmp_conf" || exit 1
awk '!/^([[:space:]]*#|[[:space:]]*$)/ { gsub(/[[:space:]]/, "", $0); if ($0 ~ /^([A-Za-z0-9_-]+\.)+[A-Za-z]{2,}$/) print "local=/" tolower($0) "/" }' "$policy_block" | sort -u >> "$tmp_conf"

if [ -s "$tmp_conf" ]; then
   mv -f "$tmp_conf" "$conf_file"
else
   rm -f "$conf_file"
fi

{
   printf 'payload:\n'
   awk -v allow="$policy_allow" -v block="$policy_block" '
      function read_list(file, target, line) {
         while ((getline line < file) > 0) { gsub(/[[:space:]]/, "", line); line=tolower(line); if (line ~ /^([a-z0-9_-]+\.)+[a-z]{2,}$/) target[line]=1 }
         close(file)
      }
      function under(domain, parent) {
         return domain == parent || (length(domain) > length(parent) && substr(domain, length(domain) - length(parent), length(parent) + 1) == "." parent)
      }
      function listed(domain, set, key) {
         for (key in set) if (under(domain, key)) return 1
         return 0
      }
      BEGIN { read_list(allow, ok); read_list(block, deny) }
      { domain=tolower($0); if (domain ~ /^([a-z0-9_-]+\.)+[a-z]{2,}$/ && !listed(domain, ok) && !listed(domain, deny)) printf "  - %s\n", domain }
   ' "$cache_file"
} > "$tmp_provider" || exit 1
mv -f "$tmp_provider" "$provider_file"
chmod 0644 "$provider_file" "$conf_file" 2>/dev/null || true

source_hash="$(sha256sum "$cache_file" 2>/dev/null | awk '{print $1}')"
printf '%s\n' "mode=$mode" "effective=1" "provider_effective=1" "domains=$(wc -l < "$cache_file" 2>/dev/null || echo 0)" "source_sha256=$source_hash" "updated=$(date +%s 2>/dev/null || echo 0)" > "$state_file"
exit 0
