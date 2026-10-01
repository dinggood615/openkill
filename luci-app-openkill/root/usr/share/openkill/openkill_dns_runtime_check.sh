#!/bin/sh
# Bounded, read-only DNS runtime evidence check. It never changes firewall,
# resolver, YAML or UCI state and never places the controller secret in argv.
set -u

CONFIG_FILE="${1:-}"
STATE_FILE="${2:-/tmp/openkill-dns-privacy.state}"
[ -s "$CONFIG_FILE" ] || exit 2

umask 077
WORK="$(mktemp -d /tmp/openkill-dns-check.XXXXXX 2>/dev/null)" || exit 3
trap 'rm -rf "$WORK"' EXIT HUP INT TERM

context="$(ruby -ryaml -e '
begin
  v=YAML.load_file(ARGV.fetch(0)); c=v["external-controller"].to_s
  puts c; puts v["secret"].to_s
rescue Exception
  exit 1
end
' "$CONFIG_FILE" 2>/dev/null)" || exit 4
CONTROLLER="$(printf '%s\n' "$context" | sed -n '1p')"
SECRET="$(printf '%s\n' "$context" | sed -n '2p')"
[ -n "$CONTROLLER" ] || exit 5
case "$CONTROLLER" in
  0.0.0.0:*) CONTROLLER="127.0.0.1:${CONTROLLER#*:}" ;;
  \[::\]:*) CONTROLLER="[::1]:${CONTROLLER#*]:}" ;;
esac

profile_ok="$(ruby -ryaml -e '
begin
  v=YAML.load_file(ARGV.fetch(0)); d=v["dns"] || {}
  enc=lambda{|x| x.to_s.match?(/\A(?:https|tls|quic|h3):\/\//i)}
  ns=Array(d["nameserver"])+Array(d["fallback"])
  groups=Array(v["proxy-groups"]); name=ARGV.fetch(1)
  g=groups.find{|x| x.is_a?(Hash) && x["name"].to_s==name}
  members=Array(g && g["proxies"])
  concrete=members.any?{|m| Array(v["proxies"]).any?{|p| p.is_a?(Hash) && p["name"].to_s==m.to_s}}
  safe=members.none?{|m| %w[DIRECT REJECT GLOBAL COMPATIBLE PASS].include?(m.to_s)}
  ok=!ns.empty? && ns.all?{|x| enc.call(x) && x.to_s.end_with?("##{name}")} && concrete && safe && Array(d["default-nameserver"]).all?{|x| enc.call(x)} && Array(d["proxy-server-nameserver"]).all?{|x| enc.call(x)}
  puts(ok ? "1" : "0")
rescue Exception
  puts "0"
end
' "$CONFIG_FILE" "${OPENKILL_DNS_PRIVACY_GROUP:-OpenKill-DNS}" 2>/dev/null)"
[ "$profile_ok" = 1 ] || exit 6

URL="http://${CONTROLLER}/dns/query?name=openkill-dns-check-$(cut -d. -f1 /proc/uptime | tr -cd '0-9').example.com&type=A"
printf 'Authorization: Bearer %s\n' "$SECRET" > "$WORK/header"
http_code="$(curl --noproxy '*' --silent --show-error --connect-timeout 3 --max-time 8 \
  -H "@$WORK/header" -o "$WORK/body" -w '%{http_code}' "$URL" 2>"$WORK/curl.err")" || http_code=000
query_ok=0
if [ "$http_code" = 200 ] && grep -Eq '"Status"[[:space:]]*:[[:space:]]*0' "$WORK/body"; then
  query_ok=1
fi
[ "$query_ok" = 1 ] || exit 7

hash="$(sha256sum "$CONFIG_FILE" 2>/dev/null | awk '{print $1}')"
now="$(date +%s)"
tmp="${STATE_FILE}.$$"
printf 'mode=strict\nconfigured=1\neffective=1\nruntime_verified=1\nordinary_encrypted=1\nbootstrap_exception=0\nreason=runtime-query-and-profile-verified\nconfig_sha256=%s\nchecked_at=%s\n' "$hash" "$now" > "$tmp" || exit 8
mv "$tmp" "$STATE_FILE" || exit 9
exit 0
