#!/bin/sh
# OpenVPN compatibility is deliberately a small, opt-in transport exception.
# It never owns OpenVPN itself and never turns tunnel traffic or DNS into a
# bypass implicitly.  The init script supplies the nft/ipset transaction
# helpers after sourcing this file.

OPENKILL_OPENVPN_STATE=/tmp/openkill-openvpn.state
OPENKILL_OPENVPN_DIR=/tmp/openkill-openvpn
OPENKILL_OPENVPN_ROLE=router-client
OPENKILL_OPENVPN_APPLIED=0
OPENKILL_OPENVPN_clear=0
OPENKILL_OPENVPN_PROTOCOL_FAMILY=all
OPENKILL_OPENVPN_PROTOCOL_BASE=udp

openkill_openvpn_bool()
{
   case "$(uci_get_config "$1" 2>/dev/null || true)" in
      1|true|on|yes) printf '1' ;;
      *) printf '0' ;;
   esac
}

openkill_openvpn_valid_port()
{
   case "$1" in
      ''|*[!0-9]*) return 1 ;;
   esac
   [ "${#1}" -le 5 ] || return 1
   [ "$1" -ge 1 ] 2>/dev/null && [ "$1" -le 65535 ] 2>/dev/null
}

openkill_openvpn_valid_ipv4()
{
   local value part count octet
   value="$1"
   case "$value" in ''|*[!0-9.]*) return 1 ;; esac
   count=$(printf '%s\n' "$value" | awk -F. '{print NF}')
   [ "$count" = 4 ] || return 1
   for part in $(printf '%s\n' "$value" | tr '.' ' '); do
      case "$part" in ''|*[!0-9]*) return 1 ;; esac
      # Reject leading signs and octets outside the IPv4 range.  Leading
      # zeroes are accepted because nft/ipset canonicalize the value.
      octet=$(awk -v x="$part" 'BEGIN { if ((x + 0) <= 255) print (x + 0); else exit 1 }') || return 1
      [ "$octet" -le 255 ] || return 1
   done
}

openkill_openvpn_valid_ipv6()
{
   local value marker compressed groups group nonempty
   value="$1"
   case "$value" in ''|*[!0-9A-Fa-f:]*) return 1 ;; esac
   case "$value" in *:*) ;; *) return 1 ;; esac
   case "$value" in *:::*) return 1 ;; esac
   marker="$value"
   # Exactly one :: is permitted. A single colon is not compression.
   case "$marker" in *::*::* ) return 1 ;; esac
   if [ "${marker#*::}" != "$marker" ]; then
      compressed="$marker"
      groups=$(printf '%s\n' "$compressed" | awk -F: '{print NF}')
      nonempty=0
      OLDIFS="$IFS"; IFS=:
      set -- $compressed
      IFS="$OLDIFS"
      for group in "$@"; do
         [ -n "$group" ] || continue
         case "$group" in *[!0-9A-Fa-f]*|?????*) return 1 ;; esac
         nonempty=$((nonempty + 1))
      done
      [ "$nonempty" -lt 8 ] || return 1
      return 0
   fi
   case "$value" in :*|*:) return 1 ;; esac
   groups=$(printf '%s\n' "$value" | awk -F: '{print NF}')
   [ "$groups" = 8 ] || return 1
   OLDIFS="$IFS"; IFS=:
   set -- $value
   IFS="$OLDIFS"
   for group in "$@"; do
      case "$group" in ''|*[!0-9A-Fa-f]*|?????*) return 1 ;; esac
   done
}

openkill_openvpn_valid_host()
{
   case "$1" in
      ''|.*|*.|*[!A-Za-z0-9_.-]*) return 1 ;;
   esac
   return 0
}

openkill_openvpn_write_state()
{
   local tmp key value
   tmp="${OPENKILL_OPENVPN_STATE}.$$"
   : > "$tmp" || return 1
   for key in requested generated applied retained role protocol protocol_family ports endpoint4 endpoint6 client4 client6 reason updated; do
      eval "value=\${OPENKILL_OPENVPN_${key}:-}"
      printf '%s=%s\n' "$key" "$value" >> "$tmp"
   done
   mv -f "$tmp" "$OPENKILL_OPENVPN_STATE"
}

openkill_openvpn_use_last_valid()
{
   local endpoint_count client_count previous_role previous_protocol
   previous_role=$(sed -n 's/^role=//p' "$OPENKILL_OPENVPN_STATE" 2>/dev/null | head -1)
   previous_protocol=$(sed -n 's/^protocol=//p' "$OPENKILL_OPENVPN_STATE" 2>/dev/null | head -1)
   [ "$previous_role" = "$OPENKILL_OPENVPN_role" ] || return 1
   [ "$previous_protocol" = "$OPENKILL_OPENVPN_protocol" ] || return 1
   [ -r "$OPENKILL_OPENVPN_DIR/endpoints4.new" ] || return 1
   [ -r "$OPENKILL_OPENVPN_DIR/endpoints6.new" ] || return 1
   [ -r "$OPENKILL_OPENVPN_DIR/clients4.new" ] || return 1
   [ -r "$OPENKILL_OPENVPN_DIR/clients6.new" ] || return 1
   [ -r "$OPENKILL_OPENVPN_DIR/ports.new" ] || return 1
   endpoint_count=$(cat "$OPENKILL_OPENVPN_DIR/endpoints4.new" "$OPENKILL_OPENVPN_DIR/endpoints6.new" 2>/dev/null | sed '/^[[:space:]]*$/d' | wc -l)
   [ "$endpoint_count" -gt 0 ] || return 1
   [ -s "$OPENKILL_OPENVPN_DIR/ports.new" ] || return 1
   if [ "$OPENKILL_OPENVPN_ROLE" = lan-client ]; then
      client_count=$(cat "$OPENKILL_OPENVPN_DIR/clients4.new" "$OPENKILL_OPENVPN_DIR/clients6.new" 2>/dev/null | sed '/^[[:space:]]*$/d' | wc -l)
      [ "$client_count" -gt 0 ] || return 1
   fi
   OPENKILL_OPENVPN_generated=1
   OPENKILL_OPENVPN_retained=1
   OPENKILL_OPENVPN_endpoint4=$(sed '/^[[:space:]]*$/d' "$OPENKILL_OPENVPN_DIR/endpoints4.new" | wc -l)
   OPENKILL_OPENVPN_endpoint6=$(sed '/^[[:space:]]*$/d' "$OPENKILL_OPENVPN_DIR/endpoints6.new" | wc -l)
   OPENKILL_OPENVPN_client4=$(sed '/^[[:space:]]*$/d' "$OPENKILL_OPENVPN_DIR/clients4.new" | wc -l)
   OPENKILL_OPENVPN_client6=$(sed '/^[[:space:]]*$/d' "$OPENKILL_OPENVPN_DIR/clients6.new" | wc -l)
   OPENKILL_OPENVPN_ports=$(tr '\n' ',' < "$OPENKILL_OPENVPN_DIR/ports.new" | sed 's/,$//')
   OPENKILL_OPENVPN_reason=invalid-retained-last-valid
   return 0
}

openkill_openvpn_resolve_host()
{
   local host output
   host="$1"
   if command -v getent >/dev/null 2>&1; then
      getent ahosts "$host" 2>/dev/null | awk '{print $1}'
   elif command -v nslookup >/dev/null 2>&1; then
      output=$(nslookup "$host" 2>/dev/null || true)
      printf '%s\n' "$output" | awk '/^Address([0-9]+)?:[[:space:]]/ {print $NF} /^Address:[[:space:]]/ {print $2}'
   fi
}

openkill_openvpn_prepare()
{
   local enabled transport role protocol ports ip host resolved value
   local v4_tmp v6_tmp clients4_tmp clients6_tmp ports_tmp endpoint_count client_count
   OPENKILL_OPENVPN_DIR=${OPENKILL_OPENVPN_DIR:-/tmp/openkill-openvpn}
   mkdir -p "$OPENKILL_OPENVPN_DIR" || return 1
   v4_tmp="$OPENKILL_OPENVPN_DIR/endpoints4.candidate.$$"
   v6_tmp="$OPENKILL_OPENVPN_DIR/endpoints6.candidate.$$"
   clients4_tmp="$OPENKILL_OPENVPN_DIR/clients4.candidate.$$"
   clients6_tmp="$OPENKILL_OPENVPN_DIR/clients6.candidate.$$"
   ports_tmp="$OPENKILL_OPENVPN_DIR/ports.candidate.$$"
   : > "$v4_tmp"; : > "$v6_tmp"; : > "$clients4_tmp"; : > "$clients6_tmp"; : > "$ports_tmp"

   enabled=$(openkill_openvpn_bool openvpn_compatibility)
   transport=$(openkill_openvpn_bool openvpn_transport_bypass)
   role=$(uci_get_config openvpn_role 2>/dev/null || echo router-client)
   protocol=$(uci_get_config openvpn_transport_protocol 2>/dev/null || echo udp)
   case "$role" in router-client|lan-client|server) ;; *) role=router-client ;; esac
   case "$protocol" in
      tcp|udp) OPENKILL_OPENVPN_PROTOCOL_BASE="$protocol"; OPENKILL_OPENVPN_PROTOCOL_FAMILY=all ;;
      tcp4|udp4) OPENKILL_OPENVPN_PROTOCOL_BASE="${protocol%4}"; OPENKILL_OPENVPN_PROTOCOL_FAMILY=4 ;;
      tcp6|udp6) OPENKILL_OPENVPN_PROTOCOL_BASE="${protocol%6}"; OPENKILL_OPENVPN_PROTOCOL_FAMILY=6 ;;
      tcp-client|tcp-server) OPENKILL_OPENVPN_PROTOCOL_BASE=tcp; OPENKILL_OPENVPN_PROTOCOL_FAMILY=all ;;
      *) protocol=invalid; OPENKILL_OPENVPN_PROTOCOL_BASE=invalid; OPENKILL_OPENVPN_PROTOCOL_FAMILY=all ;;
   esac
   OPENKILL_OPENVPN_ROLE="$role"
   OPENKILL_OPENVPN_requested="$enabled"
   OPENKILL_OPENVPN_generated=0
   OPENKILL_OPENVPN_applied=0
   OPENKILL_OPENVPN_retained=0
   OPENKILL_OPENVPN_clear=0
   OPENKILL_OPENVPN_role="$role"
   OPENKILL_OPENVPN_protocol="$protocol"
   OPENKILL_OPENVPN_protocol_family="${OPENKILL_OPENVPN_PROTOCOL_FAMILY:-all}"
   OPENKILL_OPENVPN_ports=""
   OPENKILL_OPENVPN_endpoint4=0
   OPENKILL_OPENVPN_endpoint6=0
   OPENKILL_OPENVPN_client4=0
   OPENKILL_OPENVPN_client6=0
   OPENKILL_OPENVPN_updated="$(date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null || echo unknown)"
   OPENKILL_OPENVPN_reason=disabled

   if [ "$enabled" != 1 ] || [ "$transport" != 1 ]; then
      OPENKILL_OPENVPN_clear=1
      : > "$OPENKILL_OPENVPN_DIR/endpoints4.next"
      : > "$OPENKILL_OPENVPN_DIR/endpoints6.next"
      : > "$OPENKILL_OPENVPN_DIR/clients4.next"
      : > "$OPENKILL_OPENVPN_DIR/clients6.next"
      : > "$OPENKILL_OPENVPN_DIR/ports.next"
      openkill_openvpn_write_state || true
      rm -f "$v4_tmp" "$v6_tmp" "$clients4_tmp" "$clients6_tmp" "$ports_tmp"
      return 0
   fi
   if [ "$role" = server ]; then
      OPENKILL_OPENVPN_reason=server-role-no-transport
      openkill_openvpn_write_state || true
      rm -f "$v4_tmp" "$v6_tmp" "$clients4_tmp" "$clients6_tmp" "$ports_tmp"
      return 0
   fi
   if [ "$protocol" = invalid ]; then
      OPENKILL_OPENVPN_reason=invalid-protocol
      openkill_openvpn_use_last_valid || true
      openkill_openvpn_write_state || true
      rm -f "$v4_tmp" "$v6_tmp" "$clients4_tmp" "$clients6_tmp" "$ports_tmp"
      return 0
   fi

   for ports in $(uci_get_config openvpn_server_ports 2>/dev/null || true); do
      openkill_openvpn_valid_port "$ports" || continue
      printf '%s\n' "$ports" >> "$ports_tmp"
   done
   if ! sort -un "$ports_tmp" -o "$ports_tmp" 2>/dev/null; then
      sort -u "$ports_tmp" > "$ports_tmp.sort" 2>/dev/null && mv -f "$ports_tmp.sort" "$ports_tmp"
   fi
   [ -s "$ports_tmp" ] || {
      OPENKILL_OPENVPN_reason=missing-valid-port
      openkill_openvpn_use_last_valid || true
      openkill_openvpn_write_state || true
      rm -f "$v4_tmp" "$v6_tmp" "$clients4_tmp" "$clients6_tmp" "$ports_tmp"
      return 0
   }

   for ip in $(uci_get_config openvpn_server_ips 2>/dev/null || true); do
      if openkill_openvpn_valid_ipv4 "$ip"; then printf '%s\n' "$ip" >> "$v4_tmp"; continue; fi
      if openkill_openvpn_valid_ipv6 "$ip"; then printf '%s\n' "$ip" >> "$v6_tmp"; continue; fi
   done
   for host in $(uci_get_config openvpn_server_domains 2>/dev/null || true); do
      openkill_openvpn_valid_host "$host" || continue
      openkill_openvpn_resolve_host "$host" | while IFS= read -r resolved; do
         if openkill_openvpn_valid_ipv4 "$resolved"; then printf '%s\n' "$resolved" >> "$v4_tmp"; fi
         if openkill_openvpn_valid_ipv6 "$resolved"; then printf '%s\n' "$resolved" >> "$v6_tmp"; fi
      done
   done
   sort -u "$v4_tmp" -o "$v4_tmp" 2>/dev/null || true
   sort -u "$v6_tmp" -o "$v6_tmp" 2>/dev/null || true
   endpoint_count=$(cat "$v4_tmp" "$v6_tmp" 2>/dev/null | sed '/^[[:space:]]*$/d' | wc -l)
   [ "$endpoint_count" -gt 0 ] || {
      OPENKILL_OPENVPN_reason=endpoint-resolution-failed
      openkill_openvpn_use_last_valid || true
      openkill_openvpn_write_state || true
      rm -f "$v4_tmp" "$v6_tmp" "$clients4_tmp" "$clients6_tmp" "$ports_tmp"
      return 0
   }

   if [ "$role" = lan-client ]; then
      for ip in $(uci_get_config openvpn_client_ips 2>/dev/null || true); do
         if openkill_openvpn_valid_ipv4 "$ip"; then printf '%s\n' "$ip" >> "$clients4_tmp"; fi
         if openkill_openvpn_valid_ipv6 "$ip"; then printf '%s\n' "$ip" >> "$clients6_tmp"; fi
      done
      sort -u "$clients4_tmp" -o "$clients4_tmp" 2>/dev/null || true
      sort -u "$clients6_tmp" -o "$clients6_tmp" 2>/dev/null || true
      client_count=$(cat "$clients4_tmp" "$clients6_tmp" 2>/dev/null | sed '/^[[:space:]]*$/d' | wc -l)
      [ "$client_count" -gt 0 ] || {
         OPENKILL_OPENVPN_reason=missing-client-scope
         openkill_openvpn_use_last_valid || true
         openkill_openvpn_write_state || true
         rm -f "$v4_tmp" "$v6_tmp" "$clients4_tmp" "$clients6_tmp" "$ports_tmp"
         return 0
      }
   fi

   OPENKILL_OPENVPN_generated=1
   OPENKILL_OPENVPN_endpoint4=$(sed '/^[[:space:]]*$/d' "$v4_tmp" | wc -l)
   OPENKILL_OPENVPN_endpoint6=$(sed '/^[[:space:]]*$/d' "$v6_tmp" | wc -l)
   OPENKILL_OPENVPN_client4=$(sed '/^[[:space:]]*$/d' "$clients4_tmp" | wc -l)
   OPENKILL_OPENVPN_client6=$(sed '/^[[:space:]]*$/d' "$clients6_tmp" | wc -l)
   OPENKILL_OPENVPN_ports=$(tr '\n' ',' < "$ports_tmp" | sed 's/,$//')
   OPENKILL_OPENVPN_reason=generated
   # These files are staged only. The init script applies all four sets in
   # checked nft/ipset operations and promotes them after every set succeeds.
   mv -f "$v4_tmp" "$OPENKILL_OPENVPN_DIR/endpoints4.next"
   mv -f "$v6_tmp" "$OPENKILL_OPENVPN_DIR/endpoints6.next"
   mv -f "$clients4_tmp" "$OPENKILL_OPENVPN_DIR/clients4.next"
   mv -f "$clients6_tmp" "$OPENKILL_OPENVPN_DIR/clients6.next"
   mv -f "$ports_tmp" "$OPENKILL_OPENVPN_DIR/ports.next"
   openkill_openvpn_write_state || true
   return 0
}

openkill_openvpn_apply_set()
{
   local family set_name source batch
   family="$1"; set_name="$2"; source="$3"
   [ -r "$source" ] || return 1
   if [ -n "$FW4" ] && command -v nft >/dev/null 2>&1; then
      batch="/tmp/openkill-${set_name}.batch.$$"
      {
         printf 'flush set inet fw4 %s\n' "$set_name"
         while IFS= read -r value; do
            [ -n "$value" ] && printf 'add element inet fw4 %s { %s }\n' "$set_name" "$value"
         done < "$source"
      } > "$batch" || { rm -f "$batch"; return 1; }
      openkill_validate_nft_batch "$batch" && nft -f "$batch" >/dev/null 2>&1
      local rc=$?
      rm -f "$batch"
      return "$rc"
   fi
   command -v ipset >/dev/null 2>&1 || return 1
   # ipset restore keeps its flush and additions in one restore stream. The
   # caller supplies a pre-created, family-correct set.
   batch="/tmp/openkill-${set_name}.restore.$$"
   {
      printf 'flush %s\n' "$set_name"
      while IFS= read -r value; do
         [ -n "$value" ] && printf 'add %s %s\n' "$set_name" "$value"
      done < "$source"
   } > "$batch" || { rm -f "$batch"; return 1; }
   ipset restore < "$batch" >/dev/null 2>&1
   local rc=$?
   rm -f "$batch"
   return "$rc"
}

openkill_openvpn_cleanup_temp_ipsets()
{
   local value
   for value in "$@"; do
      ipset destroy "$value" >/dev/null 2>&1 || true
   done
}

openkill_openvpn_apply_runtime()
{
   local batch source4 source6 clients4 clients6 ports value rc
   local temp4 temp6 tempc4 tempc6 tempp temp
   if [ "${OPENKILL_OPENVPN_retained:-0}" = 1 ]; then
      source4="$OPENKILL_OPENVPN_DIR/endpoints4.new"
      source6="$OPENKILL_OPENVPN_DIR/endpoints6.new"
      clients4="$OPENKILL_OPENVPN_DIR/clients4.new"
      clients6="$OPENKILL_OPENVPN_DIR/clients6.new"
      ports="$OPENKILL_OPENVPN_DIR/ports.new"
   else
      source4="$OPENKILL_OPENVPN_DIR/endpoints4.next"
      source6="$OPENKILL_OPENVPN_DIR/endpoints6.next"
      clients4="$OPENKILL_OPENVPN_DIR/clients4.next"
      clients6="$OPENKILL_OPENVPN_DIR/clients6.next"
      ports="$OPENKILL_OPENVPN_DIR/ports.next"
   fi
   [ "$OPENKILL_OPENVPN_generated" = 1 ] || [ "$OPENKILL_OPENVPN_clear" = 1 ] || return 0
   [ -r "$source4" ] && [ -r "$source6" ] && [ -r "$clients4" ] && [ -r "$clients6" ] && [ -r "$ports" ] || return 1
   if [ -n "$FW4" ] && command -v nft >/dev/null 2>&1; then
      batch="/tmp/openkill-openvpn-all.batch.$$"
      {
         for value in openkill_openvpn_endpoints4 openkill_openvpn_endpoints6 openkill_openvpn_clients4 openkill_openvpn_clients6 openkill_openvpn_ports; do
            printf 'flush set inet fw4 %s\n' "$value"
         done
         while IFS= read -r value; do [ -n "$value" ] && printf 'add element inet fw4 openkill_openvpn_endpoints4 { %s }\n' "$value"; done < "$source4"
         while IFS= read -r value; do [ -n "$value" ] && printf 'add element inet fw4 openkill_openvpn_endpoints6 { %s }\n' "$value"; done < "$source6"
         while IFS= read -r value; do [ -n "$value" ] && printf 'add element inet fw4 openkill_openvpn_clients4 { %s }\n' "$value"; done < "$clients4"
         while IFS= read -r value; do [ -n "$value" ] && printf 'add element inet fw4 openkill_openvpn_clients6 { %s }\n' "$value"; done < "$clients6"
         while IFS= read -r value; do [ -n "$value" ] && printf 'add element inet fw4 openkill_openvpn_ports { %s }\n' "$value"; done < "$ports"
      } > "$batch" || { rm -f "$batch"; return 1; }
      openkill_validate_nft_batch "$batch" && nft -f "$batch" >/dev/null 2>&1
      rc=$?
      rm -f "$batch"
   else
      command -v ipset >/dev/null 2>&1 || return 1
      # ipset restore applies commands one by one; flushing the live sets
      # first would leave a partial or empty bypass after a bad element. Load
      # complete temporary sets, then swap each one into place. A failed load
      # therefore leaves every live set untouched.
      temp4="okov4n.$$"; temp6="okov6n.$$"
      tempc4="okoc4n.$$"; tempc6="okoc6n.$$"; tempp="okopn.$$"
      openkill_openvpn_cleanup_temp_ipsets "$temp4" "$temp6" "$tempc4" "$tempc6" "$tempp"
      ipset create "$temp4" hash:ip family inet hashsize 64 maxelem 4096 || return 1
      ipset create "$temp6" hash:ip family inet6 hashsize 64 maxelem 4096 || { openkill_openvpn_cleanup_temp_ipsets "$temp4"; return 1; }
      ipset create "$tempc4" hash:ip family inet hashsize 64 maxelem 4096 || { openkill_openvpn_cleanup_temp_ipsets "$temp4" "$temp6"; return 1; }
      ipset create "$tempc6" hash:ip family inet6 hashsize 64 maxelem 4096 || { openkill_openvpn_cleanup_temp_ipsets "$temp4" "$temp6" "$tempc4"; return 1; }
      ipset create "$tempp" bitmap:port range 1-65535 || { openkill_openvpn_cleanup_temp_ipsets "$temp4" "$temp6" "$tempc4" "$tempc6"; return 1; }
      while IFS= read -r value; do
         [ -n "$value" ] || continue
         ipset add "$temp4" "$value" || { openkill_openvpn_cleanup_temp_ipsets "$temp4" "$temp6" "$tempc4" "$tempc6" "$tempp"; return 1; }
      done < "$source4"
      while IFS= read -r value; do
         [ -n "$value" ] || continue
         ipset add "$temp6" "$value" || { openkill_openvpn_cleanup_temp_ipsets "$temp4" "$temp6" "$tempc4" "$tempc6" "$tempp"; return 1; }
      done < "$source6"
      while IFS= read -r value; do
         [ -n "$value" ] || continue
         ipset add "$tempc4" "$value" || { openkill_openvpn_cleanup_temp_ipsets "$temp4" "$temp6" "$tempc4" "$tempc6" "$tempp"; return 1; }
      done < "$clients4"
      while IFS= read -r value; do
         [ -n "$value" ] || continue
         ipset add "$tempc6" "$value" || { openkill_openvpn_cleanup_temp_ipsets "$temp4" "$temp6" "$tempc4" "$tempc6" "$tempp"; return 1; }
      done < "$clients6"
      while IFS= read -r value; do
         [ -n "$value" ] || continue
         ipset add "$tempp" "$value" || { openkill_openvpn_cleanup_temp_ipsets "$temp4" "$temp6" "$tempc4" "$tempc6" "$tempp"; return 1; }
      done < "$ports"
      ipset swap "$temp4" openkill_openvpn_endpoints4 && \
      ipset swap "$temp6" openkill_openvpn_endpoints6 && \
      ipset swap "$tempc4" openkill_openvpn_clients4 && \
      ipset swap "$tempc6" openkill_openvpn_clients6 && \
      ipset swap "$tempp" openkill_openvpn_ports
      rc=$?
      # After a successful swap the temporary names refer to the old sets;
      # after a failed swap they are safe to remove as best effort cleanup.
      openkill_openvpn_cleanup_temp_ipsets "$temp4" "$temp6" "$tempc4" "$tempc6" "$tempp"
   fi
    if [ "$rc" -ne 0 ]; then
       # A failed candidate transaction must leave the old runtime sets and
       # their rules usable. Reuse the last promoted generation when it still
       # matches the same role/protocol; the caller receives failure so the
       # UI can report that the requested update was not applied.
       if [ "${OPENKILL_OPENVPN_retained:-0}" != 1 ] && openkill_openvpn_use_last_valid; then
          OPENKILL_OPENVPN_APPLIED=1
          openkill_openvpn_mark_applied
       fi
       return 1
    fi
    if [ "${OPENKILL_OPENVPN_retained:-0}" != 1 ]; then
       mv -f "$source4" "$OPENKILL_OPENVPN_DIR/endpoints4.new" || return 1
       mv -f "$source6" "$OPENKILL_OPENVPN_DIR/endpoints6.new" || return 1
       mv -f "$clients4" "$OPENKILL_OPENVPN_DIR/clients4.new" || return 1
       mv -f "$clients6" "$OPENKILL_OPENVPN_DIR/clients6.new" || return 1
       mv -f "$ports" "$OPENKILL_OPENVPN_DIR/ports.new" || return 1
    fi
   if [ "$OPENKILL_OPENVPN_generated" = 1 ]; then
      OPENKILL_OPENVPN_APPLIED=1
      openkill_openvpn_mark_applied
   else
      OPENKILL_OPENVPN_APPLIED=0
      OPENKILL_OPENVPN_applied=0
      OPENKILL_OPENVPN_reason=disabled
      openkill_openvpn_write_state || true
   fi
   return 0
}

openkill_openvpn_mark_applied()
{
   OPENKILL_OPENVPN_applied=1
   if [ "${OPENKILL_OPENVPN_retained:-0}" = 1 ]; then
      OPENKILL_OPENVPN_reason=applied-last-valid
   else
      OPENKILL_OPENVPN_reason=applied
   fi
   openkill_openvpn_write_state || true
}

openkill_openvpn_mark_unsupported()
{
   OPENKILL_OPENVPN_requested=$(openkill_openvpn_bool openvpn_compatibility)
   OPENKILL_OPENVPN_role=$(uci_get_config openvpn_role 2>/dev/null || echo router-client)
   OPENKILL_OPENVPN_protocol=$(uci_get_config openvpn_transport_protocol 2>/dev/null || echo udp)
   OPENKILL_OPENVPN_protocol_family=all
   OPENKILL_OPENVPN_generated=0
   OPENKILL_OPENVPN_applied=0
   OPENKILL_OPENVPN_reason="$1"
   openkill_openvpn_write_state || true
}

openkill_openvpn_add_nft_rules()
{
   local chain family target clientset rule l4proto
   [ "$OPENKILL_OPENVPN_APPLIED" = 1 ] || return 0
   [ "$OPENKILL_OPENVPN_ROLE" = server ] && return 0
   [ -n "$FW4" ] || return 0
   case "${OPENKILL_OPENVPN_PROTOCOL_BASE:-}" in
      tcp|udp) l4proto="$OPENKILL_OPENVPN_PROTOCOL_BASE" ;;
      *) return 0 ;;
   esac
   for chain in openkill openkill_mangle openkill_mangle_output openkill_output; do
      nft list chain inet fw4 "$chain" >/dev/null 2>&1 || continue
      for family in 4 6; do
         case "${OPENKILL_OPENVPN_PROTOCOL_FAMILY:-all}" in
            4) [ "$family" = 4 ] || continue ;;
            6) [ "$family" = 6 ] || continue ;;
         esac
         if [ "$family" = 4 ]; then target=openkill_openvpn_endpoints4; clientset=openkill_openvpn_clients4; else target=openkill_openvpn_endpoints6; clientset=openkill_openvpn_clients6; fi
         if [ "$OPENKILL_OPENVPN_ROLE" = lan-client ]; then
            [ "$family" = 4 ] && [ "$OPENKILL_OPENVPN_client4" -gt 0 ] || [ "$family" = 6 ] && [ "$OPENKILL_OPENVPN_client6" -gt 0 ] || continue
            if [ "$family" = 4 ]; then
               rule="insert rule inet fw4 $chain position 0 meta l4proto $l4proto ip saddr @${clientset} ip daddr @${target} th dport @openkill_openvpn_ports counter return comment \"OpenKill OpenVPN Scoped Transport\""
            else
               rule="insert rule inet fw4 $chain position 0 meta l4proto $l4proto ip6 saddr @${clientset} ip6 daddr @${target} th dport @openkill_openvpn_ports counter return comment \"OpenKill OpenVPN Scoped Transport\""
            fi
         else
            if [ "$family" = 4 ]; then
               rule="insert rule inet fw4 $chain position 0 meta l4proto $l4proto ip daddr @${target} th dport @openkill_openvpn_ports counter return comment \"OpenKill OpenVPN Scoped Transport\""
            else
               rule="insert rule inet fw4 $chain position 0 meta l4proto $l4proto ip6 daddr @${target} th dport @openkill_openvpn_ports counter return comment \"OpenKill OpenVPN Scoped Transport\""
            fi
         fi
         nft "$rule" 2>/dev/null || true
      done
   done
}

openkill_openvpn_add_legacy_rules()
{
   local table chain family rule families proto iptables_bin
   [ "$OPENKILL_OPENVPN_APPLIED" = 1 ] || return 0
   [ "$OPENKILL_OPENVPN_ROLE" = server ] && return 0
   [ -z "$FW4" ] || return 0
   case "${OPENKILL_OPENVPN_PROTOCOL_BASE:-}" in
      tcp|udp) proto="$OPENKILL_OPENVPN_PROTOCOL_BASE" ;;
      *) return 0 ;;
   esac
   for table in nat mangle; do
      for chain in openkill openkill_output; do
         case "${OPENKILL_OPENVPN_PROTOCOL_FAMILY:-all}" in
            4) families="4" ;;
            6) families="6" ;;
            *) families="4 6" ;;
         esac
         if [ "$OPENKILL_OPENVPN_ROLE" = lan-client ]; then
            for family in $families; do
               if [ "$family" = 4 ]; then iptables_bin=iptables; else iptables_bin=ip6tables; fi
               rule="-p $proto -m set --match-set openkill_openvpn_clients${family} src -m set --match-set openkill_openvpn_endpoints${family} dst -m set --match-set openkill_openvpn_ports dst -m comment --comment OpenKill-OpenVPN-Scoped -j RETURN"
               $iptables_bin -t "$table" -nL "$chain" >/dev/null 2>&1 && $iptables_bin -t "$table" -I "$chain" 1 $rule 2>/dev/null || true
            done
         else
            for family in $families; do
               if [ "$family" = 4 ]; then iptables_bin=iptables; else iptables_bin=ip6tables; fi
               rule="-p $proto -m set --match-set openkill_openvpn_endpoints${family} dst -m set --match-set openkill_openvpn_ports dst -m comment --comment OpenKill-OpenVPN-Scoped -j RETURN"
               $iptables_bin -t "$table" -nL "$chain" >/dev/null 2>&1 && $iptables_bin -t "$table" -I "$chain" 1 $rule 2>/dev/null || true
            done
         fi
      done
   done
}
