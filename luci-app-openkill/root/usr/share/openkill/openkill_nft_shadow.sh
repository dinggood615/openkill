#!/bin/sh
# OpenKill CURRENT-profile runtime shadow coordinator.
#
# The coordinator is deliberately separate from the renderer.  It consumes a
# normalized, line-oriented state bundle prepared by the control plane, invokes
# the pure shell renderer, and compares canonical intent only.  It never invokes
# a dataplane or discovery command.  The caller
# must explicitly opt in with OPENKILL_NFT_SHADOW=1; the default is disabled.

OPENKILL_NFT_SHADOW_PROTOCOL_VERSION=1
OPENKILL_NFT_SHADOW_COMPARE_SCHEMA_VERSION=1
OPENKILL_NFT_SHADOW_STATE_SCHEMA_VERSION=1
OPENKILL_NFT_SHADOW_RENDERER_VERSION=1
OPENKILL_NFT_SHADOW_DEFAULT=0
OPENKILL_NFT_SHADOW_RENDERER_DEFAULT=/usr/share/openkill/openkill_nft_renderer.sh
OPENKILL_NFT_SHADOW_STATE_DEFAULT=/tmp/openkill-shadow/state
OPENKILL_NFT_SHADOW_TELEMETRY_DEFAULT=/tmp/openkill-shadow
OPENKILL_NFT_SHADOW_MAX_PAYLOAD_BYTES=262144
OPENKILL_NFT_SHADOW_TIMEOUT_DEFAULT=10

# Additive 3E.1 schemas.  The original bundle protocol remains supported for
# CI and for older callers; the automatic path below is selected only when no
# explicit INPUT_FILE/OLD_INTENT_FILE bundle is supplied.
OPENKILL_NFT_SHADOW_AUTO_STATE_VERSION=1
OPENKILL_NFT_SHADOW_LEGACY_INTENT_VERSION=1
OPENKILL_NFT_SHADOW_CAPTURE_VERSION=1
# The bounded capture inventory is a schema, not a list of exceptions.  Its
# rows are sourced from the CURRENT renderer templates below; these two
# existing fw4 base-chain groups are the parser's explicit capture contract.
OPENKILL_NFT_SHADOW_INVENTORY_SCHEMA_VERSION=1
OPENKILL_NFT_SHADOW_REQUIRED_BASE_CHAINS="dstnat mangle_prerouting mangle_output output srcnat input forward"
OPENKILL_NFT_SHADOW_REQUIRED_SET_IDS="LOCAL_V4 LOCAL_V6 NODE_ENDPOINT_V4 NODE_ENDPOINT_V6 CHINA_PASS_V4 CHINA_PASS_V6 CHINA_V4 CHINA_V6 SERVICE_PORTS"
OPENKILL_NFT_SHADOW_OUT_OF_SCOPE_SET_IDS="WAN_HOST_V4 WAN_HOST_V6"
# The file under /tmp/openkill-network-reconcile is a development helper
# token, not a production lifecycle ABI.  Runtime shadow continuity is based
# on this content-derived token instead.
OPENKILL_NFT_SHADOW_CONTINUITY_TOKEN_VERSION=1
OPENKILL_NFT_SHADOW_CONTINUITY_TOKEN_SCHEMA="SHADOW_CONTINUITY_TOKEN_V1"

# Stable status/exit vocabulary for callers and tests.  A non-zero result is
# intentionally safe to ignore at the production callsite; old writer return
# values are never replaced by this observer.
OPENKILL_NFT_SHADOW_RC_MATCH=0
OPENKILL_NFT_SHADOW_RC_MISMATCH=1
OPENKILL_NFT_SHADOW_RC_UNSUPPORTED=2
OPENKILL_NFT_SHADOW_RC_INPUT=3
OPENKILL_NFT_SHADOW_RC_RENDER=4
OPENKILL_NFT_SHADOW_RC_SOURCE_DRIFT=5
OPENKILL_NFT_SHADOW_RC_STALE=6
OPENKILL_NFT_SHADOW_RC_COMPARE=7
OPENKILL_NFT_SHADOW_RC_CAPTURE_UNAVAILABLE=8
OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR=9
OPENKILL_NFT_SHADOW_RC_CAPTURE_UNSUPPORTED=10
OPENKILL_NFT_SHADOW_RC_SOURCE_GAP=11
# Additive semantic-model result.  The legacy numeric meanings above are
# frozen; MODEL_GAP is deliberately a new value so an incomplete ownership or
# typed-DNS source can never be mistaken for either MATCH or MISMATCH.
OPENKILL_NFT_SHADOW_RC_MODEL_GAP=12
OPENKILL_NFT_SHADOW_SEMANTIC_MODEL_VERSION=1
OPENKILL_NFT_SHADOW_OWNERSHIP_MODEL_VERSION=1
OPENKILL_NFT_SHADOW_DNS_MODEL_VERSION=1
OPENKILL_NFT_SHADOW_SEMANTIC_MANIFEST_DEFAULT=/usr/share/openkill/shadow/semantic_model_v1.tsv
# Automatic production cycles produce typed sidecars from their private
# snapshot by default.  The explicit zero value is retained only for the
# pre-R3C raw-fixture compatibility path; real callers never need to set it.
OPENKILL_NFT_SHADOW_AUTO_TYPED_DEFAULT=1
# External typed sidecars are a fixture/development interface.  Automatic
# production cycles are always internal-only.

openkill_shadow_enabled()
{
   [ "${OPENKILL_NFT_SHADOW:-$OPENKILL_NFT_SHADOW_DEFAULT}" = 1 ]
}

openkill_shadow_safe_value()
{
   # State values are data, never shell fragments.  Reject line/control
   # delimiters before any value is used as a path or a diagnostic field.
   case "$1" in *[![:print:]]*) return 1 ;; esac
   return 0
}

# BusyBox tr does not implement the POSIX character-class transliteration
# used by some host implementations consistently.  Shadow enums are finite,
# so normalize them with exact POSIX shell patterns and reject every unknown
# value instead of applying a broad case conversion.
openkill_shadow_normalize_owner()
{
   case "$1" in
      [Oo][Pp][Ee][Nn][Kk][Ii][Ll][Ll]) printf '%s\n' OPENKILL ;;
      [Mm][Ii][Hh][Oo][Mm][Oo]) printf '%s\n' MIHOMO ;;
      [Dd][Ii][Ss][Aa][Bb][Ll][Ee][Dd]) printf '%s\n' DISABLED ;;
      [Uu][Nn][Kk][Nn][Oo][Ww][Nn]) printf '%s\n' UNKNOWN ;;
      *) return 1 ;;
   esac
}

openkill_shadow_normalize_run_mode()
{
   case "$1" in
      [Tt][Uu][Nn]) printf '%s\n' TUN ;;
      [Tt][Pp][Rr][Oo][Xx][Yy]) printf '%s\n' TPROXY ;;
      [Rr][Ee][Dd][Ii][Rr][Ee][Cc][Tt]) printf '%s\n' REDIRECT ;;
      *) return 1 ;;
   esac
}

openkill_shadow_is_unsupported_true()
{
   case "$1" in
      1|[Yy][Ee][Ss]|[Tt][Rr][Uu][Ee]|[Aa][Cc][Tt][Ii][Vv][Ee]|[Uu][Nn][Ss][Uu][Pp][Pp][Oo][Rr][Tt][Ee][Dd]|[Rr][Ee][Qq][Uu][Ii][Rr][Ee][Dd])
         return 0
         ;;
      *) return 1 ;;
   esac
}

openkill_shadow_state_value()
{
   openkill_shadow_key=$1
   openkill_shadow_state=$2
   [ -r "$openkill_shadow_state" ] || return 1
   while IFS='=' read -r openkill_shadow_state_key openkill_shadow_state_value; do
      [ "$openkill_shadow_state_key" = "$openkill_shadow_key" ] || continue
      openkill_shadow_safe_value "$openkill_shadow_state_value" || return 1
      printf '%s\n' "$openkill_shadow_state_value"
      return 0
   done < "$openkill_shadow_state"
   return 1
}

openkill_shadow_load_state()
{
   openkill_shadow_state_file=$1
   [ -z "$openkill_shadow_state_file" ] || openkill_shadow_safe_value "$openkill_shadow_state_file" || return 1
   openkill_shadow_input_file=${OPENKILL_NFT_SHADOW_INPUT_FILE:-}
   openkill_shadow_old_intent_file=${OPENKILL_NFT_SHADOW_OLD_INTENT_FILE:-}
   openkill_shadow_old_intent_hash=${OPENKILL_NFT_SHADOW_OLD_INTENT_HASH:-}
   openkill_shadow_generation=${OPENKILL_NFT_SHADOW_GENERATION:-}
   openkill_shadow_generation_file=${OPENKILL_NFT_SHADOW_GENERATION_FILE:-}
   openkill_shadow_source_hash_file=${OPENKILL_NFT_SHADOW_SOURCE_HASH_FILE:-}
   openkill_shadow_baseline_hash_file=${OPENKILL_NFT_SHADOW_BASELINE_HASH_FILE:-}
   openkill_shadow_source_hash=${OPENKILL_NFT_SHADOW_SOURCE_HASH:-}
   openkill_shadow_baseline_hash=${OPENKILL_NFT_SHADOW_BASELINE_HASH:-}

   if [ -n "$openkill_shadow_state_file" ]; then
      [ -r "$openkill_shadow_state_file" ] || return 1
      [ "$(sed -n '1p' "$openkill_shadow_state_file")" = "OPENKILL_SHADOW_STATE_V1=$OPENKILL_NFT_SHADOW_STATE_SCHEMA_VERSION" ] || return 1
      while IFS='=' read -r openkill_shadow_state_key openkill_shadow_state_value; do
         case "$openkill_shadow_state_key" in
            ''|OPENKILL_SHADOW_STATE_V1) continue ;;
            INPUT_FILE) openkill_shadow_input_file=$openkill_shadow_state_value ;;
            OLD_INTENT_FILE) openkill_shadow_old_intent_file=$openkill_shadow_state_value ;;
            OLD_INTENT_HASH) openkill_shadow_old_intent_hash=$openkill_shadow_state_value ;;
            GENERATION) openkill_shadow_generation=$openkill_shadow_state_value ;;
            GENERATION_FILE) openkill_shadow_generation_file=$openkill_shadow_state_value ;;
            SOURCE_HASH_FILE) openkill_shadow_source_hash_file=$openkill_shadow_state_value ;;
            BASELINE_HASH_FILE) openkill_shadow_baseline_hash_file=$openkill_shadow_state_value ;;
            SOURCE_HASH) openkill_shadow_source_hash=$openkill_shadow_state_value ;;
            BASELINE_HASH) openkill_shadow_baseline_hash=$openkill_shadow_state_value ;;
            *) return 1 ;;
         esac
         openkill_shadow_safe_value "$openkill_shadow_state_value" || return 1
      done < "$openkill_shadow_state_file"
   fi

   [ -n "$openkill_shadow_input_file" ] || return 1
   openkill_shadow_safe_value "$openkill_shadow_input_file" || return 1
   if [ -n "$openkill_shadow_old_intent_file" ]; then
      openkill_shadow_safe_value "$openkill_shadow_old_intent_file" || return 1
   fi
   if [ -n "$openkill_shadow_generation_file" ]; then
      openkill_shadow_safe_value "$openkill_shadow_generation_file" || return 1
   fi
   for openkill_shadow_state_scalar in \
      "$openkill_shadow_old_intent_hash" \
      "$openkill_shadow_generation" \
      "$openkill_shadow_source_hash" \
      "$openkill_shadow_baseline_hash"; do
      openkill_shadow_safe_value "$openkill_shadow_state_scalar" || return 1
   done
   return 0
}

openkill_shadow_read_generation()
{
   if [ -n "${openkill_shadow_generation_file:-}" ]; then
      [ -r "$openkill_shadow_generation_file" ] || return 1
      openkill_shadow_generation_value=$(sed -n '1p' "$openkill_shadow_generation_file") || return 1
   else
      openkill_shadow_generation_value=${openkill_shadow_generation:-}
   fi
   [ -n "$openkill_shadow_generation_value" ] || return 1
   openkill_shadow_safe_value "$openkill_shadow_generation_value" || return 1
   printf '%s\n' "$openkill_shadow_generation_value"
}

openkill_shadow_build_input()
{
   # This is the production input boundary.  The coordinator accepts only a
   # pre-normalized SHELL_RENDERER_INPUT_V1 file from the control plane; it
   # does not rediscover state or interpret policy.
   openkill_shadow_input_source=$1
   openkill_shadow_input_output=$2
   [ -r "$openkill_shadow_input_source" ] || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
   [ -n "$openkill_shadow_input_output" ] || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
   openkill_shadow_input_size=$(wc -c < "$openkill_shadow_input_source") || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
   [ "$openkill_shadow_input_size" -le "$OPENKILL_NFT_SHADOW_MAX_PAYLOAD_BYTES" ] || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
   openkill_shadow_header=$(sed -n '1p' "$openkill_shadow_input_source") || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
   [ "$openkill_shadow_header" = 'SHELL_RENDERER_INPUT_V1	1' ] || return "$OPENKILL_NFT_SHADOW_RC_UNSUPPORTED"
   openkill_shadow_profile=$(awk -F '\t' '$1 == "META" && $2 == "profile" { print $3; exit }' "$openkill_shadow_input_source") || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
   [ "$openkill_shadow_profile" = current ] || return "$OPENKILL_NFT_SHADOW_RC_UNSUPPORTED"
   # A target/development marker must never enter a production shadow call.
   if grep -Eq '(^|[[:space:]])(target|development-preview)([[:space:]]|$)' "$openkill_shadow_input_source"; then
      return "$OPENKILL_NFT_SHADOW_RC_UNSUPPORTED"
   fi
   cp "$openkill_shadow_input_source" "$openkill_shadow_input_output" || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
   return 0
}

# 3E.1 automatic state producer ------------------------------------------------
#
# The runtime shadow may be invoked from an existing init/reconcile shell where
# the old writer has already committed its applied state.  This producer reads
# only those committed, normalized files (or an explicitly supplied
# line-oriented fixture) and turns them into the existing
# SHELL_RENDERER_INPUT_V1 protocol.  It never invokes discovery utilities and
# it never decides a packet policy.

openkill_shadow_safe_path()
{
   openkill_shadow_path_value=$1
   openkill_shadow_safe_value "$openkill_shadow_path_value" || return 1
   case "$openkill_shadow_path_value" in
      /*) ;;
      *) return 1 ;;
   esac
   case "$openkill_shadow_path_value" in
      *..*) return 1 ;;
   esac
   # State/template paths are supplied by the control plane, so refuse a
   # symlink at the final path.  This keeps a fixture or stale environment
   # variable from redirecting the observer into an unrelated file.
   [ ! -L "$openkill_shadow_path_value" ] || return 1
   return 0
}

openkill_shadow_auto_source_path()
{
   openkill_shadow_auto_source_file=${OPENKILL_NFT_SHADOW_SOURCE_FILE:-${OPENKILL_NFT_SHADOW_AUTO_STATE_FILE:-${OPENKILL_NFT_SHADOW_STATE_SOURCE:-}}}
   if [ -n "$openkill_shadow_auto_source_file" ]; then
      openkill_shadow_safe_path "$openkill_shadow_auto_source_file" || return 1
      [ -r "$openkill_shadow_auto_source_file" ] || return 1
      printf '%s\n' "$openkill_shadow_auto_source_file"
      return 0
   fi
   return 1
}

openkill_shadow_auto_lookup_file()
{
   openkill_shadow_auto_lookup_key=$1
   openkill_shadow_auto_lookup_file_name=$2
   [ -r "$openkill_shadow_auto_lookup_file_name" ] || return 1
   openkill_shadow_safe_path "$openkill_shadow_auto_lookup_file_name" || return 1
   openkill_shadow_auto_lookup_result=$(awk -F '=' -v key="$openkill_shadow_auto_lookup_key" '
      $1 == key {
         value=substr($0, index($0, "=") + 1)
         if (found && value != first) bad=1
         if (!found) first=value
         found=1
      }
      END {
         if (bad) exit 2
         if (found) print first
         else exit 1
      }
   ' "$openkill_shadow_auto_lookup_file_name")
   openkill_shadow_auto_lookup_rc=$?
   [ "$openkill_shadow_auto_lookup_rc" -eq 0 ] || return "$openkill_shadow_auto_lookup_rc"
   openkill_shadow_safe_value "$openkill_shadow_auto_lookup_result" || return 1
   printf '%s\n' "$openkill_shadow_auto_lookup_result"
}

openkill_shadow_auto_lookup()
{
   # Result is returned in openkill_shadow_auto_value.  A value found twice
   # with different bytes is an INPUT_SOURCE_GAP; it is never resolved by
   # choosing whichever file happened to be read last.
   openkill_shadow_auto_key=$1
   openkill_shadow_auto_value=
   openkill_shadow_auto_lookup_status=1
   openkill_shadow_auto_source_path_value=${openkill_shadow_auto_source_file:-}
   if [ -n "$openkill_shadow_auto_source_path_value" ]; then
      openkill_shadow_auto_value=$(openkill_shadow_auto_lookup_file "$openkill_shadow_auto_key" "$openkill_shadow_auto_source_path_value")
      openkill_shadow_auto_lookup_status=$?
      case "$openkill_shadow_auto_lookup_status" in
         0) return 0 ;;
         1) return 1 ;;
         *) return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP" ;;
      esac
   fi

   # The committed desired/applied file is the primary normalized network
   # source.  Snapshot and endpoint files are only field-specific fallbacks.
   openkill_shadow_auto_primary_file=${OPENKILL_NETWORK_DESIRED:-}
   [ -r "$openkill_shadow_auto_primary_file" ] || openkill_shadow_auto_primary_file=${OPENKILL_NETWORK_APPLIED_FILE:-/tmp/openkill-network.applied}
   case "$openkill_shadow_auto_key" in
      NODE4_ENDPOINTS|NODE6_ENDPOINTS)
         openkill_shadow_auto_node_file=${OPENKILL_NFT_SHADOW_NODE4_FILE:-/tmp/openkill-node4.desired}
         [ "$openkill_shadow_auto_key" = NODE6_ENDPOINTS ] && openkill_shadow_auto_node_file=${OPENKILL_NFT_SHADOW_NODE6_FILE:-/tmp/openkill-node6.desired}
         openkill_shadow_safe_path "$openkill_shadow_auto_node_file" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
         if [ -r "$openkill_shadow_auto_node_file" ]; then
            openkill_shadow_auto_value=$(tr '\n' ' ' < "$openkill_shadow_auto_node_file" | awk '{$1=$1; print}')
            openkill_shadow_safe_value "$openkill_shadow_auto_value" || return 1
            return 0
         fi
         ;;
   esac
   if [ -r "$openkill_shadow_auto_primary_file" ]; then
      openkill_shadow_auto_value=$(openkill_shadow_auto_lookup_file "$openkill_shadow_auto_key" "$openkill_shadow_auto_primary_file")
      openkill_shadow_auto_lookup_status=$?
      case "$openkill_shadow_auto_lookup_status" in
         0) return 0 ;;
         2) return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP" ;;
      esac
   fi
   openkill_shadow_auto_snapshot_file=${OPENKILL_NETWORK_SNAPSHOT:-/tmp/openkill-network.snapshot}
   if [ -r "$openkill_shadow_auto_snapshot_file" ]; then
      openkill_shadow_auto_value=$(openkill_shadow_auto_lookup_file "$openkill_shadow_auto_key" "$openkill_shadow_auto_snapshot_file")
      openkill_shadow_auto_lookup_status=$?
      case "$openkill_shadow_auto_lookup_status" in
         0) return 0 ;;
         2) return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP" ;;
      esac
   fi

   # These are already populated by get_config()/the network reconcile.  No
   # indirect expansion or arbitrary shell text is used here.
   case "$openkill_shadow_auto_key" in
      OWNER|TUN_OWNER) openkill_shadow_auto_value=${tun_owner:-${OPENKILL_TUN_OWNER:-}} ;;
      RUN_MODE) openkill_shadow_auto_value=${OPENKILL_RUN_MODE:-};
         [ -n "$openkill_shadow_auto_value" ] || {
            # `en_mode_tun=1` is the native TUN path.  The production
            # `*-mix` value is 2 and still uses the redirect/TProxy firewall
            # branches, so it must not be mistaken for pure TUN.  When no
            # explicit normalized mode is available, enable_udp_proxy is the
            # existing execution-contract discriminator for those branches.
            case "${en_mode_tun:-}" in
               1) openkill_shadow_auto_value=TUN ;;
               2|'')
                  [ "${enable_udp_proxy:-0}" = 1 ] && openkill_shadow_auto_value=TPROXY
                  [ -n "$openkill_shadow_auto_value" ] || openkill_shadow_auto_value=REDIRECT
                  ;;
               *) return 1 ;;
            esac
         } ;;
      ROUTER_SELF_PROXY) openkill_shadow_auto_value=${router_self_proxy:-${OPENKILL_ROUTER_SELF_PROXY:-}} ;;
      REDIRECT_PORT|PROXY_PORT) openkill_shadow_auto_value=${proxy_port:-${OPENKILL_PROXY_PORT:-}} ;;
      TPROXY_PORT) openkill_shadow_auto_value=${tproxy_port:-${OPENKILL_TPROXY_PORT:-}} ;;
      DNS_PORT) openkill_shadow_auto_value=${dns_port:-${DNSPORT:-${OPENKILL_DNS_PORT:-}}} ;;
      MARK|OPENKILL_FWMARK) openkill_shadow_auto_value=${OPENKILL_FWMARK:-${PROXY_FWMARK:-}} ;;
      MASK|OPENKILL_FWMASK) openkill_shadow_auto_value=${OPENKILL_FWMASK:-} ;;
      ROUTE_TABLE|OPENKILL_ROUTE_TABLE) openkill_shadow_auto_value=${OPENKILL_ROUTE_TABLE:-${PROXY_ROUTE_TABLE:-}} ;;
      RULE_PREF|OPENKILL_RULE_PREF) openkill_shadow_auto_value=${OPENKILL_RULE_PREF:-} ;;
      IPV6_READY) openkill_shadow_auto_value=${OPENKILL_IPV6_READY:-} ;;
      DNSMASQ_LISTEN_TARGET|DNSMASQ_LISTEN) openkill_shadow_auto_value=${OPENKILL_DNSMASQ_LISTEN_TARGET:-${DNSMASQ_LISTEN_TARGET:-${dnsmasq_listen_target:-}}} ;;
      DNSMASQ_UPSTREAM_TARGET|DNSMASQ_UPSTREAM) openkill_shadow_auto_value=${OPENKILL_DNSMASQ_UPSTREAM_TARGET:-${DNSMASQ_UPSTREAM_TARGET:-${dnsmasq_upstream_target:-}}} ;;
      MIHOMO_DNS_LISTENER|MIHOMO_LISTENER) openkill_shadow_auto_value=${OPENKILL_MIHOMO_DNS_LISTENER:-${MIHOMO_DNS_LISTENER:-${mihomo_dns_listener:-}}} ;;
      DNS_LOOP_PREVENTION) openkill_shadow_auto_value=${OPENKILL_DNS_LOOP_PREVENTION:-${DNS_LOOP_PREVENTION:-${dns_loop_prevention:-}}} ;;
      DNS_SCOPE_IPV4) openkill_shadow_auto_value=${OPENKILL_DNS_SCOPE_IPV4:-${DNS_SCOPE_IPV4:-${dns_scope_ipv4:-}}} ;;
      DNS_SCOPE_IPV6) openkill_shadow_auto_value=${OPENKILL_DNS_SCOPE_IPV6:-${DNS_SCOPE_IPV6:-${dns_scope_ipv6:-}}} ;;
      *) openkill_shadow_auto_value= ;;
   esac
   [ -n "$openkill_shadow_auto_value" ] || return 1
   openkill_shadow_safe_value "$openkill_shadow_auto_value" || return 1
   return 0
}

openkill_shadow_auto_field()
{
   openkill_shadow_auto_field_value=
   openkill_shadow_auto_field_status=1
   openkill_shadow_auto_field_seen=0
   openkill_shadow_auto_field_first=
   for openkill_shadow_auto_alias in "$@"; do
      openkill_shadow_auto_field_value=
      openkill_shadow_auto_lookup "$openkill_shadow_auto_alias"
      openkill_shadow_auto_field_status=$?
      case "$openkill_shadow_auto_field_status" in
         0)
            # A canonical source is authoritative.  When more than one alias
            # is present, all aliases must carry the same value; selecting the
            # first one would silently create two sources of truth.
            if [ "$openkill_shadow_auto_field_seen" -eq 0 ]; then
               openkill_shadow_auto_field_first=$openkill_shadow_auto_value
               openkill_shadow_auto_field_seen=1
            elif [ "$openkill_shadow_auto_field_first" != "$openkill_shadow_auto_value" ]; then
               return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
            fi
            openkill_shadow_auto_field_value=$openkill_shadow_auto_field_first
            ;;
         "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP") return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP" ;;
      esac
   done
   [ "$openkill_shadow_auto_field_seen" -eq 1 ] || return 1
   openkill_shadow_auto_field_value=$openkill_shadow_auto_field_first
   return 0
}

openkill_shadow_auto_list()
{
   openkill_shadow_auto_list_input=$1
   [ -n "$openkill_shadow_auto_list_input" ] || { printf '%s\n' -; return 0; }
   openkill_shadow_safe_value "$openkill_shadow_auto_list_input" || return 1
   case "$openkill_shadow_auto_list_input" in
      *';'*|*'`'*|*'$('*|*'"'*|*"'"*|*'\\'*) return 1 ;;
   esac
   printf '%s\n' "$openkill_shadow_auto_list_input" | tr ',' ' ' |
      awk '{ for (i=1; i<=NF; i++) if ($i != "") print $i }' |
      LC_ALL=C sort -u |
      awk 'BEGIN { first=1 } { if (!first) printf ","; printf "%s", $0; first=0 } END { if (first) print "-"; else print "" }'
}

# 3E.2D0A continuity contract -------------------------------------------------
#
# `/tmp/openkill-network-reconcile/generation` was created by a development
# helper and is not part of the production lifecycle.  The automatic shadow
# path therefore derives a token from the same committed files and normalized
# shell values that its producer consumes.  The source list and its order are
# fixed here so the token is deterministic and does not become a second
# classifier or a timestamp/PID based generation counter.

openkill_shadow_continuity_state_key()
{
   case "$1" in
      OWNER|TUN_OWNER|RUN_MODE|ROUTER_SELF_PROXY|REDIRECT_PORT|PROXY_PORT|TPROXY_PORT|DNS_PORT|DNSMASQ_LISTEN_TARGET|DNSMASQ_LISTEN|DNSMASQ_UPSTREAM_TARGET|DNSMASQ_UPSTREAM|MIHOMO_DNS_LISTENER|MIHOMO_LISTENER|DNS_LOOP_PREVENTION|DNS_SCOPE_IPV4|DNS_SCOPE_IPV6|MARK|OPENKILL_FWMARK|MASK|OPENKILL_FWMASK|ROUTE_TABLE|OPENKILL_ROUTE_TABLE|RULE_PREF|OPENKILL_RULE_PREF|IPV6_READY|BC01_UNSUPPORTED|BC_01_UNSUPPORTED|CURRENT_UNDEFINED|EXPLICIT_POLICY_CURRENT_UNDEFINED|CURRENT_ACCESS_DENY|BC07_UNSUPPORTED|BC_07_UNSUPPORTED|ACCESS_DENY_REQUIRED|ACCESS4_ALLOW|LAN_AC_WHITE_V4|USER_DIRECT_V4|ACCESS4_BYPASS|ACCESS4_DENY|LAN_AC_BLACK_V4|ACCESS6_ALLOW|LAN_AC_WHITE_V6|USER_DIRECT_V6|ACCESS6_BYPASS|ACCESS6_DENY|LAN_AC_BLACK_V6|CHINA_PASS4|CHINA_PASS6|CHINA4|CHINA6|COMMON_PORTS|SERVICE_PORTS|DELEGATED6|PD6|DELEGATED_IPV6_PREFIXES|FAKE_IP4|FAKEIP4|FAKE_IP6|FAKEIP6|LAN4|LAN_IPV4_PREFIXES|LAN6|LAN_IPV6_PREFIXES|LOCAL4|LOCAL_V4|LOCALNETWORK4|LOCALNETWORK4_PREFIXES|INTERNAL_IPV4_PREFIXES|LOCAL6|LOCAL_V6|LOCALNETWORK6|LOCALNETWORK6_PREFIXES|INTERNAL_IPV6_PREFIXES|NODE4|NODE4_ENDPOINTS|NODE6|NODE6_ENDPOINTS|SERVICE_PORTS|USER_DIRECT4|USER_DIRECT_V4|USER_DIRECT6|USER_PROXY4|USER_PROXY6|WAN4|WAN_HOST4|WAN4_HOST|WAN4_HOST_ADDRESSES|WAN4_ADDRESSES|WAN6|WAN_HOST6|WAN6_HOST|WAN6_HOST_ADDRESSES|WAN6_ADDRESSES|WAN_AC_BLACK_PORTS|WAN_AC_BLACK_V4|WAN_AC_BLACK_V6|OPENKILL_NFT_SHADOW_AUTO_STATE_V1|OPENKILL_SHADOW_SOURCE_V1|SHELL_RENDERER_STATE_V1)
         return 0
      ;;
   esac
   return 1
}

openkill_shadow_continuity_list_key()
{
   case "$1" in
      ACCESS4_ALLOW|LAN_AC_WHITE_V4|USER_DIRECT_V4|ACCESS4_BYPASS|ACCESS4_DENY|LAN_AC_BLACK_V4|ACCESS6_ALLOW|LAN_AC_WHITE_V6|USER_DIRECT_V6|ACCESS6_BYPASS|ACCESS6_DENY|LAN_AC_BLACK_V6|CHINA_PASS4|CHINA_PASS6|CHINA4|CHINA6|COMMON_PORTS|SERVICE_PORTS|DELEGATED6|PD6|DELEGATED_IPV6_PREFIXES|FAKE_IP4|FAKEIP4|FAKE_IP6|FAKEIP6|LAN4|LAN_IPV4_PREFIXES|LAN6|LAN_IPV6_PREFIXES|LOCAL4|LOCAL_V4|LOCALNETWORK4|LOCALNETWORK4_PREFIXES|INTERNAL_IPV4_PREFIXES|LOCAL6|LOCAL_V6|LOCALNETWORK6|LOCALNETWORK6_PREFIXES|INTERNAL_IPV6_PREFIXES|NODE4|NODE4_ENDPOINTS|NODE6|NODE6_ENDPOINTS|SERVICE_PORTS|USER_DIRECT4|USER_DIRECT_V6|USER_DIRECT6|USER_PROXY4|USER_PROXY6|WAN4|WAN_HOST4|WAN4_HOST|WAN4_HOST_ADDRESSES|WAN4_ADDRESSES|WAN6|WAN_HOST6|WAN6_HOST|WAN6_HOST_ADDRESSES|WAN6_ADDRESSES|WAN_AC_BLACK_PORTS|WAN_AC_BLACK_V4|WAN_AC_BLACK_V6)
         return 0
      ;;
   esac
   return 1
}

openkill_shadow_continuity_canonicalize_file()
{
   openkill_shadow_continuity_input=$1
   openkill_shadow_continuity_output=$2
   [ -r "$openkill_shadow_continuity_input" ] || return 1
   openkill_shadow_safe_path "$openkill_shadow_continuity_input" || return 1
   openkill_shadow_safe_path "$openkill_shadow_continuity_output" || return 1
   openkill_shadow_continuity_header=$(sed -n '1p' "$openkill_shadow_continuity_input") || return 1
   case "$openkill_shadow_continuity_header" in
      OPENKILL_NFT_SHADOW_AUTO_STATE_V1=1|OPENKILL_SHADOW_SOURCE_V1=1|SHELL_RENDERER_STATE_V1=1|SNAPSHOT_VERSION=1|OPENKILL_SHADOW_RUNTIME_DNS_V1=1) ;;
      OPENKILL_NFT_SHADOW_AUTO_STATE_V1=*|OPENKILL_SHADOW_SOURCE_V1=*|SHELL_RENDERER_STATE_V1=*|SNAPSHOT_VERSION=*|*_VERSION=*|*_V[0-9]*=*) return 1 ;;
   esac
   # Keep this one-pass and shell-portable: repeated per-line command
   # substitutions made the continuity read needlessly expensive on ash. The
   # allow-list is the producer's field surface; unknown keys do not become a
   # second source of truth. List values are canonicalized in awk so set
   # element order cannot change the token.
   openkill_shadow_continuity_raw=${openkill_shadow_continuity_output}.raw.$$
   openkill_shadow_safe_path "$openkill_shadow_continuity_raw" || return 1
   awk -F '=' -v listkeys='|ACCESS4_ALLOW|LAN_AC_WHITE_V4|USER_DIRECT_V4|ACCESS4_BYPASS|ACCESS4_DENY|LAN_AC_BLACK_V4|ACCESS6_ALLOW|LAN_AC_WHITE_V6|USER_DIRECT_V6|USER_DIRECT6|ACCESS6_BYPASS|ACCESS6_DENY|LAN_AC_BLACK_V6|CHINA_PASS4|CHINA_PASS6|CHINA4|CHINA6|COMMON_PORTS|SERVICE_PORTS|DELEGATED6|PD6|DELEGATED_IPV6_PREFIXES|FAKE_IP4|FAKEIP4|FAKE_IP6|FAKEIP6|LAN4|LAN_IPV4_PREFIXES|LAN6|LAN_IPV6_PREFIXES|LOCAL4|LOCAL_V4|LOCALNETWORK4|LOCALNETWORK4_PREFIXES|INTERNAL_IPV4_PREFIXES|LOCAL6|LOCAL_V6|LOCALNETWORK6|LOCALNETWORK6_PREFIXES|INTERNAL_IPV6_PREFIXES|NODE4|NODE4_ENDPOINTS|NODE6|NODE6_ENDPOINTS|USER_DIRECT4|USER_DIRECT_V6|USER_DIRECT6|USER_PROXY4|USER_PROXY6|WAN4|WAN_HOST4|WAN4_HOST|WAN4_HOST_ADDRESSES|WAN4_ADDRESSES|WAN6|WAN_HOST6|WAN6_HOST|WAN6_HOST_ADDRESSES|WAN6_ADDRESSES|WAN_AC_BLACK_PORTS|WAN_AC_BLACK_V4|WAN_AC_BLACK_V6|' '
      function allowed(k) {
         return index("|OWNER|TUN_OWNER|RUN_MODE|ROUTER_SELF_PROXY|REDIRECT_PORT|PROXY_PORT|TPROXY_PORT|DNS_PORT|DNSMASQ_LISTEN_TARGET|DNSMASQ_UPSTREAM_TARGET|MIHOMO_DNS_LISTENER|DNSMASQ_LISTEN_SOURCE|DNSMASQ_UPSTREAM_SOURCE|MIHOMO_DNS_LISTENER_SOURCE|MARK|OPENKILL_FWMARK|MASK|OPENKILL_FWMASK|ROUTE_TABLE|OPENKILL_ROUTE_TABLE|RULE_PREF|OPENKILL_RULE_PREF|IPV6_READY|BC01_UNSUPPORTED|BC_01_UNSUPPORTED|CURRENT_UNDEFINED|EXPLICIT_POLICY_CURRENT_UNDEFINED|CURRENT_ACCESS_DENY|BC07_UNSUPPORTED|BC_07_UNSUPPORTED|ACCESS_DENY_REQUIRED|ACCESS4_ALLOW|LAN_AC_WHITE_V4|USER_DIRECT_V4|ACCESS4_BYPASS|ACCESS4_DENY|LAN_AC_BLACK_V4|ACCESS6_ALLOW|LAN_AC_WHITE_V6|USER_DIRECT_V6|USER_DIRECT6|ACCESS6_BYPASS|ACCESS6_DENY|LAN_AC_BLACK_V6|CHINA_PASS4|CHINA_PASS6|CHINA4|CHINA6|COMMON_PORTS|SERVICE_PORTS|DELEGATED6|PD6|DELEGATED_IPV6_PREFIXES|FAKE_IP4|FAKEIP4|FAKE_IP6|FAKEIP6|LAN4|LAN_IPV4_PREFIXES|LAN6|LAN_IPV6_PREFIXES|LOCAL4|LOCAL_V4|LOCALNETWORK4|LOCALNETWORK4_PREFIXES|INTERNAL_IPV4_PREFIXES|LOCAL6|LOCAL_V6|LOCALNETWORK6|LOCALNETWORK6_PREFIXES|INTERNAL_IPV6_PREFIXES|NODE4|NODE4_ENDPOINTS|NODE6|NODE6_ENDPOINTS|USER_DIRECT4|USER_DIRECT_V4|USER_DIRECT6|USER_PROXY4|USER_PROXY6|WAN4|WAN_HOST4|WAN4_HOST|WAN4_HOST_ADDRESSES|WAN4_ADDRESSES|WAN6|WAN_HOST6|WAN6_HOST|WAN6_HOST_ADDRESSES|WAN6_ADDRESSES|WAN_AC_BLACK_PORTS|WAN_AC_BLACK_V4|WAN_AC_BLACK_V6|OPENKILL_NFT_SHADOW_AUTO_STATE_V1|OPENKILL_SHADOW_SOURCE_V1|SHELL_RENDERER_STATE_V1|", "|" k "|") > 0
      }
      function islist(k) { return index(listkeys, "|" k "|") > 0 }
      function listcanon(v, a,n,i,j,t,out) {
         gsub(/[[:space:],]+/, " ", v); gsub(/^ +| +$/, "", v)
         if (v == "") return "-"
         n=split(v,a,/ +/)
         for (i=1; i<=n; i++) { t=a[i]; j=i; while (j>1 && a[j-1] > t) { a[j]=a[j-1]; j-- } a[j]=t }
         out=""; t=""
         for (i=1; i<=n; i++) if (a[i] != t) { if (out != "") out=out ","; out=out a[i]; t=a[i] }
         return out
      }
      { sub(/\r$/, "") }
      /^[A-Z0-9_]+=/{ key=$1; value=substr($0,index($0,"=")+1); if (allowed(key)) { if (islist(key)) value=listcanon(value); print key "=" value } }
   ' "$openkill_shadow_continuity_input" > "$openkill_shadow_continuity_raw"
   openkill_shadow_continuity_awk_rc=$?
   if [ "$openkill_shadow_continuity_awk_rc" -ne 0 ]; then
      rm -f "$openkill_shadow_continuity_raw" "$openkill_shadow_continuity_output"
      return 1
   fi
   LC_ALL=C sort -u "$openkill_shadow_continuity_raw" > "$openkill_shadow_continuity_output"
   openkill_shadow_continuity_sort_rc=$?
   rm -f "$openkill_shadow_continuity_raw"
   [ "$openkill_shadow_continuity_sort_rc" -eq 0 ] || { rm -f "$openkill_shadow_continuity_output"; return 1; }
   [ -s "$openkill_shadow_continuity_output" ] || { rm -f "$openkill_shadow_continuity_output"; return 1; }
   return 0
}

openkill_shadow_continuity_canonicalize_node_file()
{
   openkill_shadow_continuity_input=$1
   openkill_shadow_continuity_output=$2
   [ -r "$openkill_shadow_continuity_input" ] || return 1
   openkill_shadow_safe_path "$openkill_shadow_continuity_input" || return 1
   openkill_shadow_safe_path "$openkill_shadow_continuity_output" || return 1
   openkill_shadow_continuity_node_value=$(tr '\n' ' ' < "$openkill_shadow_continuity_input" | awk '{$1=$1; print}') || return 1
   openkill_shadow_continuity_node_value=$(openkill_shadow_auto_list "$openkill_shadow_continuity_node_value") || return 1
   printf 'NODE_LIST=%s\n' "$openkill_shadow_continuity_node_value" > "$openkill_shadow_continuity_output" || return 1
   return 0
}

openkill_shadow_continuity_shell_scalars()
{
   openkill_shadow_continuity_scalars_output=$1
   openkill_shadow_safe_path "$openkill_shadow_continuity_scalars_output" || return 1
   : > "$openkill_shadow_continuity_scalars_output" || return 1
   for openkill_shadow_continuity_scalar_value in \
      "${tun_owner:-${OPENKILL_TUN_OWNER:-}}" "${OPENKILL_TUN_OWNER:-}" \
      "${OPENKILL_RUN_MODE:-}" "${en_mode_tun:-}" "${enable_udp_proxy:-}" \
      "${router_self_proxy:-}" "${OPENKILL_ROUTER_SELF_PROXY:-}" \
      "${proxy_port:-}" "${OPENKILL_PROXY_PORT:-}" "${tproxy_port:-}" "${OPENKILL_TPROXY_PORT:-}" \
      "${dns_port:-${DNSPORT:-}}" "${OPENKILL_DNS_PORT:-}" \
      "${OPENKILL_DNSMASQ_LISTEN_TARGET:-${DNSMASQ_LISTEN_TARGET:-${dnsmasq_listen_target:-}}}" \
      "${OPENKILL_DNSMASQ_UPSTREAM_TARGET:-${DNSMASQ_UPSTREAM_TARGET:-${dnsmasq_upstream_target:-}}}" \
      "${OPENKILL_MIHOMO_DNS_LISTENER:-${MIHOMO_DNS_LISTENER:-${mihomo_dns_listener:-}}}" \
      "${OPENKILL_DNS_LOOP_PREVENTION:-${DNS_LOOP_PREVENTION:-${dns_loop_prevention:-}}}" \
      "${OPENKILL_DNS_SCOPE_IPV4:-${DNS_SCOPE_IPV4:-${dns_scope_ipv4:-}}}" \
      "${OPENKILL_DNS_SCOPE_IPV6:-${DNS_SCOPE_IPV6:-${dns_scope_ipv6:-}}}" \
      "${OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_LISTEN_TARGET:-}" \
      "${OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_UPSTREAM_TARGET:-}" \
      "${OPENKILL_NFT_SHADOW_FROZEN_MIHOMO_DNS_LISTENER:-}" \
      "${OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_LISTEN_SOURCE:-}" \
      "${OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_UPSTREAM_SOURCE:-}" \
      "${OPENKILL_NFT_SHADOW_FROZEN_MIHOMO_DNS_SOURCE:-}" \
      "${OPENKILL_FWMARK:-${PROXY_FWMARK:-}}" "${OPENKILL_FWMARK:-}" "${OPENKILL_FWMASK:-}" \
      "${OPENKILL_ROUTE_TABLE:-${PROXY_ROUTE_TABLE:-}}" "${OPENKILL_ROUTE_TABLE:-}" \
      "${OPENKILL_RULE_PREF:-}" "${OPENKILL_IPV6_READY:-}" \
      "${BC01_UNSUPPORTED:-}" "${CURRENT_UNDEFINED:-}" "${BC07_UNSUPPORTED:-}" "${ACCESS_DENY_REQUIRED:-}"; do
      openkill_shadow_safe_value "$openkill_shadow_continuity_scalar_value" || return 1
   done
   {
      printf 'OWNER=%s\n' "${tun_owner:-${OPENKILL_TUN_OWNER:-}}"
      printf 'OPENKILL_TUN_OWNER=%s\n' "${OPENKILL_TUN_OWNER:-}"
      printf 'RUN_MODE=%s\n' "${OPENKILL_RUN_MODE:-}"
      printf 'EN_MODE_TUN=%s\n' "${en_mode_tun:-}"
      printf 'ENABLE_UDP_PROXY=%s\n' "${enable_udp_proxy:-}"
      printf 'ROUTER_SELF_PROXY=%s\n' "${router_self_proxy:-}"
      printf 'OPENKILL_ROUTER_SELF_PROXY=%s\n' "${OPENKILL_ROUTER_SELF_PROXY:-}"
      printf 'REDIRECT_PORT=%s\n' "${proxy_port:-}"
      printf 'OPENKILL_PROXY_PORT=%s\n' "${OPENKILL_PROXY_PORT:-}"
      printf 'TPROXY_PORT=%s\n' "${tproxy_port:-}"
      printf 'OPENKILL_TPROXY_PORT=%s\n' "${OPENKILL_TPROXY_PORT:-}"
      printf 'DNS_PORT=%s\n' "${dns_port:-${DNSPORT:-}}"
      printf 'OPENKILL_DNS_PORT=%s\n' "${OPENKILL_DNS_PORT:-}"
      printf 'DNSMASQ_LISTEN_TARGET=%s\n' "${OPENKILL_DNSMASQ_LISTEN_TARGET:-${DNSMASQ_LISTEN_TARGET:-${dnsmasq_listen_target:-}}}"
      printf 'DNSMASQ_UPSTREAM_TARGET=%s\n' "${OPENKILL_DNSMASQ_UPSTREAM_TARGET:-${DNSMASQ_UPSTREAM_TARGET:-${dnsmasq_upstream_target:-}}}"
      printf 'MIHOMO_DNS_LISTENER=%s\n' "${OPENKILL_MIHOMO_DNS_LISTENER:-${MIHOMO_DNS_LISTENER:-${mihomo_dns_listener:-}}}"
      printf 'DNS_LOOP_PREVENTION=%s\n' "${OPENKILL_DNS_LOOP_PREVENTION:-${DNS_LOOP_PREVENTION:-${dns_loop_prevention:-}}}"
      printf 'DNS_SCOPE_IPV4=%s\n' "${OPENKILL_DNS_SCOPE_IPV4:-${DNS_SCOPE_IPV4:-${dns_scope_ipv4:-}}}"
      printf 'DNS_SCOPE_IPV6=%s\n' "${OPENKILL_DNS_SCOPE_IPV6:-${DNS_SCOPE_IPV6:-${dns_scope_ipv6:-}}}"
      printf 'FROZEN_DNSMASQ_LISTEN_TARGET=%s\n' "${OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_LISTEN_TARGET:-}"
      printf 'FROZEN_DNSMASQ_UPSTREAM_TARGET=%s\n' "${OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_UPSTREAM_TARGET:-}"
      printf 'FROZEN_MIHOMO_DNS_LISTENER=%s\n' "${OPENKILL_NFT_SHADOW_FROZEN_MIHOMO_DNS_LISTENER:-}"
      printf 'FROZEN_DNSMASQ_LISTEN_SOURCE=%s\n' "${OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_LISTEN_SOURCE:-}"
      printf 'FROZEN_DNSMASQ_UPSTREAM_SOURCE=%s\n' "${OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_UPSTREAM_SOURCE:-}"
      printf 'FROZEN_MIHOMO_DNS_SOURCE=%s\n' "${OPENKILL_NFT_SHADOW_FROZEN_MIHOMO_DNS_SOURCE:-}"
      printf 'MARK=%s\n' "${OPENKILL_FWMARK:-${PROXY_FWMARK:-}}"
      printf 'OPENKILL_FWMARK=%s\n' "${OPENKILL_FWMARK:-}"
      printf 'MASK=%s\n' "${OPENKILL_FWMASK:-}"
      printf 'OPENKILL_FWMASK=%s\n' "${OPENKILL_FWMASK:-}"
      printf 'ROUTE_TABLE=%s\n' "${OPENKILL_ROUTE_TABLE:-${PROXY_ROUTE_TABLE:-}}"
      printf 'OPENKILL_ROUTE_TABLE=%s\n' "${OPENKILL_ROUTE_TABLE:-}"
      printf 'RULE_PREF=%s\n' "${OPENKILL_RULE_PREF:-}"
      printf 'OPENKILL_RULE_PREF=%s\n' "${OPENKILL_RULE_PREF:-}"
      printf 'IPV6_READY=%s\n' "${OPENKILL_IPV6_READY:-}"
      printf 'BC01_UNSUPPORTED=%s\n' "${BC01_UNSUPPORTED:-}"
      printf 'CURRENT_UNDEFINED=%s\n' "${CURRENT_UNDEFINED:-}"
      printf 'BC07_UNSUPPORTED=%s\n' "${BC07_UNSUPPORTED:-}"
      printf 'ACCESS_DENY_REQUIRED=%s\n' "${ACCESS_DENY_REQUIRED:-}"
   } >> "$openkill_shadow_continuity_scalars_output" || return 1
   return 0
}

openkill_shadow_continuity_add_file()
{
   openkill_shadow_continuity_id=$1
   openkill_shadow_continuity_path=$2
   openkill_shadow_continuity_required=$3
   openkill_shadow_continuity_kind=$4
   openkill_shadow_continuity_work=$5
   openkill_shadow_continuity_components=$6
   if [ -z "$openkill_shadow_continuity_path" ]; then
      [ "$openkill_shadow_continuity_required" = 1 ] && return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      printf '%s\tABSENT_ALLOWED\t-\n' "$openkill_shadow_continuity_id" >> "$openkill_shadow_continuity_components"
      return 0
   fi
   openkill_shadow_safe_path "$openkill_shadow_continuity_path" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   if [ ! -r "$openkill_shadow_continuity_path" ]; then
      [ "$openkill_shadow_continuity_required" = 1 ] && return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      printf '%s\tABSENT_ALLOWED\t-\n' "$openkill_shadow_continuity_id" >> "$openkill_shadow_continuity_components"
      return 0
   fi
   openkill_shadow_continuity_size=$(wc -c < "$openkill_shadow_continuity_path") || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   [ "$openkill_shadow_continuity_size" -le "$OPENKILL_NFT_SHADOW_MAX_PAYLOAD_BYTES" ] || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
   openkill_shadow_continuity_canonical=$openkill_shadow_continuity_work/$openkill_shadow_continuity_id.canonical
   case "$openkill_shadow_continuity_kind" in
      node) openkill_shadow_continuity_canonicalize_node_file "$openkill_shadow_continuity_path" "$openkill_shadow_continuity_canonical" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP" ;;
      state) openkill_shadow_continuity_canonicalize_file "$openkill_shadow_continuity_path" "$openkill_shadow_continuity_canonical" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP" ;;
      *) return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP" ;;
   esac
   openkill_shadow_continuity_hash=$(openkill_shadow_hash_file "$openkill_shadow_continuity_canonical" 2>/dev/null) || return "$OPENKILL_NFT_SHADOW_RC_COMPARE"
   openkill_shadow_valid_hash "$openkill_shadow_continuity_hash" || return "$OPENKILL_NFT_SHADOW_RC_COMPARE"
   printf '%s\tPRESENT\t%s\n' "$openkill_shadow_continuity_id" "$openkill_shadow_continuity_hash" >> "$openkill_shadow_continuity_components"
   return 0
}

openkill_shadow_auto_continuity_token()
{
   # Arguments: output token file, work directory, desired, applied, snapshot,
   # node4, node6, optional runtime DNS evidence.  The caller supplies the
   # original live paths explicitly so the final T2 read cannot accidentally
   # inspect the private snapshot.  Runtime DNS is optional for the legacy
   # token API, but required by the automatic production path.
   openkill_shadow_continuity_token_output_file=$1
   openkill_shadow_continuity_work=$2
   openkill_shadow_continuity_desired=$3
   openkill_shadow_continuity_applied=$4
   openkill_shadow_continuity_snapshot=$5
   openkill_shadow_continuity_node4=$6
   openkill_shadow_continuity_node6=$7
   openkill_shadow_continuity_runtime_dns=${8:-}
   [ -n "$openkill_shadow_continuity_token_output_file" ] && [ -n "$openkill_shadow_continuity_work" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_safe_path "$openkill_shadow_continuity_token_output_file" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_safe_path "$openkill_shadow_continuity_work" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   # All continuity material is transient and may contain hashes of sensitive
   # control-plane state.  The coordinator runs in a subshell, so tightening
   # the umask here cannot alter the caller's production umask.
   umask 077
   mkdir -p "$openkill_shadow_continuity_work" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   chmod 700 "$openkill_shadow_continuity_work" 2>/dev/null || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_continuity_components=$openkill_shadow_continuity_work/components
   openkill_shadow_safe_path "$openkill_shadow_continuity_components" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   : > "$openkill_shadow_continuity_components" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   printf '%s=%s\n' "$OPENKILL_NFT_SHADOW_CONTINUITY_TOKEN_SCHEMA" "$OPENKILL_NFT_SHADOW_CONTINUITY_TOKEN_VERSION" >> "$openkill_shadow_continuity_components"
   printf 'profile\tPRESENT\tcurrent\n' >> "$openkill_shadow_continuity_components"
   openkill_shadow_continuity_add_file desired "$openkill_shadow_continuity_desired" 0 state "$openkill_shadow_continuity_work" "$openkill_shadow_continuity_components" || return $?
   openkill_shadow_continuity_add_file applied "$openkill_shadow_continuity_applied" 1 state "$openkill_shadow_continuity_work" "$openkill_shadow_continuity_components" || return $?
   openkill_shadow_continuity_add_file snapshot "$openkill_shadow_continuity_snapshot" 0 state "$openkill_shadow_continuity_work" "$openkill_shadow_continuity_components" || return $?
   openkill_shadow_continuity_add_file node4 "$openkill_shadow_continuity_node4" 0 node "$openkill_shadow_continuity_work" "$openkill_shadow_continuity_components" || return $?
   openkill_shadow_continuity_add_file node6 "$openkill_shadow_continuity_node6" 0 node "$openkill_shadow_continuity_work" "$openkill_shadow_continuity_components" || return $?
   if [ -n "$openkill_shadow_continuity_runtime_dns" ]; then
      openkill_shadow_continuity_add_file runtime_dns "$openkill_shadow_continuity_runtime_dns" 1 state "$openkill_shadow_continuity_work" "$openkill_shadow_continuity_components" || return $?
   fi
   openkill_shadow_continuity_scalars=$openkill_shadow_continuity_work/scalars
   openkill_shadow_continuity_shell_scalars "$openkill_shadow_continuity_scalars" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_continuity_scalar_hash=$(openkill_shadow_hash_file "$openkill_shadow_continuity_scalars" 2>/dev/null) || return "$OPENKILL_NFT_SHADOW_RC_COMPARE"
   openkill_shadow_valid_hash "$openkill_shadow_continuity_scalar_hash" || return "$OPENKILL_NFT_SHADOW_RC_COMPARE"
   printf 'shell_scalars\tPRESENT\t%s\n' "$openkill_shadow_continuity_scalar_hash" >> "$openkill_shadow_continuity_components"
   # Components are emitted in fixed source order above.  Do not sort this
   # file: changing source enumeration order in a caller must not change V1.
   openkill_shadow_continuity_token=$(openkill_shadow_hash_file "$openkill_shadow_continuity_components" 2>/dev/null) || return "$OPENKILL_NFT_SHADOW_RC_COMPARE"
   openkill_shadow_valid_hash "$openkill_shadow_continuity_token" || return "$OPENKILL_NFT_SHADOW_RC_COMPARE"
   openkill_shadow_continuity_token_tmp=${openkill_shadow_continuity_token_output_file}.tmp.$$
   openkill_shadow_safe_path "$openkill_shadow_continuity_token_tmp" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   printf '%s\n' "$openkill_shadow_continuity_token" > "$openkill_shadow_continuity_token_tmp" || {
      rm -f "$openkill_shadow_continuity_token_tmp"
      return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   }
   mv -f "$openkill_shadow_continuity_token_tmp" "$openkill_shadow_continuity_token_output_file" || {
      rm -f "$openkill_shadow_continuity_token_tmp"
      return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   }
   printf '%s\n' "$openkill_shadow_continuity_token"
   return 0
}

openkill_shadow_continuity_token()
{
   openkill_shadow_auto_continuity_token "$@"
}

openkill_shadow_auto_continuity_copy()
{
   openkill_shadow_continuity_copy_source=$1
   openkill_shadow_continuity_copy_target=$2
   [ -n "$openkill_shadow_continuity_copy_source" ] && [ -n "$openkill_shadow_continuity_copy_target" ] || return 1
   openkill_shadow_safe_path "$openkill_shadow_continuity_copy_source" || return 1
   openkill_shadow_safe_path "$openkill_shadow_continuity_copy_target" || return 1
   [ -r "$openkill_shadow_continuity_copy_source" ] || return 1
   openkill_shadow_continuity_copy_tmp=${openkill_shadow_continuity_copy_target}.tmp.$$
   openkill_shadow_safe_path "$openkill_shadow_continuity_copy_tmp" || return 1
   cp "$openkill_shadow_continuity_copy_source" "$openkill_shadow_continuity_copy_tmp" || { rm -f "$openkill_shadow_continuity_copy_tmp"; return 1; }
   chmod 600 "$openkill_shadow_continuity_copy_tmp" 2>/dev/null || { rm -f "$openkill_shadow_continuity_copy_tmp"; return 1; }
   mv -f "$openkill_shadow_continuity_copy_tmp" "$openkill_shadow_continuity_copy_target" || { rm -f "$openkill_shadow_continuity_copy_tmp"; return 1; }
   return 0
}

openkill_shadow_continuity_copy_matches()
{
   # Verify that the private copy is exactly one of the source components
   # hashed for T0.  T0/T1 catches ordinary updates; this additional check
   # closes an update-and-revert window during the copy itself.
   openkill_shadow_continuity_match_id=$1
   openkill_shadow_continuity_match_source=$2
   openkill_shadow_continuity_match_kind=$3
   openkill_shadow_continuity_match_copy=$4
   openkill_shadow_continuity_match_components=$5
   [ -r "$openkill_shadow_continuity_match_copy" ] || return 1
   openkill_shadow_safe_path "$openkill_shadow_continuity_match_copy" || return 1
   openkill_shadow_safe_path "$openkill_shadow_continuity_match_components" || return 1
   openkill_shadow_continuity_match_expected=$(awk -F '\t' -v id="$openkill_shadow_continuity_match_id" '$1 == id && $2 == "PRESENT" { print $3; exit }' "$openkill_shadow_continuity_match_components") || return 1
   openkill_shadow_valid_hash "$openkill_shadow_continuity_match_expected" || return 1
   openkill_shadow_continuity_match_canonical=${openkill_shadow_continuity_match_copy}.canonical.$$
   openkill_shadow_safe_path "$openkill_shadow_continuity_match_canonical" || return 1
   case "$openkill_shadow_continuity_match_kind" in
      node) openkill_shadow_continuity_canonicalize_node_file "$openkill_shadow_continuity_match_copy" "$openkill_shadow_continuity_match_canonical" || { rm -f "$openkill_shadow_continuity_match_canonical"; return 1; } ;;
      state) openkill_shadow_continuity_canonicalize_file "$openkill_shadow_continuity_match_copy" "$openkill_shadow_continuity_match_canonical" || { rm -f "$openkill_shadow_continuity_match_canonical"; return 1; } ;;
      *) rm -f "$openkill_shadow_continuity_match_canonical"; return 1 ;;
   esac
   openkill_shadow_continuity_match_actual=$(openkill_shadow_hash_file "$openkill_shadow_continuity_match_canonical" 2>/dev/null) || {
      rm -f "$openkill_shadow_continuity_match_canonical"
      return 1
   }
   rm -f "$openkill_shadow_continuity_match_canonical"
   [ "$openkill_shadow_continuity_match_actual" = "$openkill_shadow_continuity_match_expected" ]
}

# Freeze runtime DNS evidence before T0.  The automatic producer must never
# discover a missing typed value after the coherent snapshot has been sealed.
# The automatic observer must use live, snapshot-bound evidence.  DNSPORT and
# OPENKILL_DNS_ENDPOINT are configuration/readiness intent supplied by init;
# they are never accepted as evidence of a Mihomo listener.  A missing live
# source is a source gap and is reported as MODEL_GAP by the typed producer.
openkill_shadow_capture_runtime_dns()
{
   openkill_shadow_runtime_dns_state_dir=$1
   [ -n "$openkill_shadow_runtime_dns_state_dir" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_safe_path "$openkill_shadow_runtime_dns_state_dir" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"

   openkill_shadow_runtime_dns_listener=
   openkill_shadow_runtime_dns_upstream=
   openkill_shadow_runtime_dns_mihomo=
   openkill_shadow_runtime_dns_listener_source=
   openkill_shadow_runtime_dns_upstream_source=
   openkill_shadow_runtime_dns_mihomo_source=

   # The dnsmasq UCI port is authoritative when present.  DNSPORT is the
   # already-captured listener selected by the legacy writer; netstat is a
   # bounded read-only fallback for a default (unset) UCI port.
   openkill_shadow_runtime_dns_has_uci=0
   if command -v uci >/dev/null 2>&1; then
      openkill_shadow_runtime_dns_has_uci=1
      [ -n "$openkill_shadow_runtime_dns_listener" ] ||
         openkill_shadow_runtime_dns_listener=$(uci -q get dhcp.@dnsmasq[0].port 2>/dev/null || true)
      [ -n "$openkill_shadow_runtime_dns_upstream" ] ||
         openkill_shadow_runtime_dns_upstream=$(uci -q get dhcp.@dnsmasq[0].server 2>/dev/null || true)
      [ -z "$openkill_shadow_runtime_dns_listener" ] || openkill_shadow_runtime_dns_listener_source=uci-dnsmasq-port
      [ -z "$openkill_shadow_runtime_dns_upstream" ] || openkill_shadow_runtime_dns_upstream_source=uci-dnsmasq-server
   fi

   # A committed state file is useful in a local harness that deliberately
   # omits UCI, but it is never allowed to mask an actual device UCI source.
   # Production therefore observes dnsmasq from UCI/netstat, while fixture-only
   # continuity runs can still freeze their checked-in state values.
   if [ "$openkill_shadow_runtime_dns_has_uci" -eq 0 ]; then
      for openkill_shadow_runtime_dns_state_file in \
         "${OPENKILL_NETWORK_DESIRED:-}" \
         "${OPENKILL_NETWORK_APPLIED_FILE:-}" \
         "${OPENKILL_NETWORK_SNAPSHOT:-}"; do
         [ -r "$openkill_shadow_runtime_dns_state_file" ] || continue
         for openkill_shadow_runtime_dns_state_pair in \
            'DNSMASQ_LISTEN_TARGET DNSMASQ_LISTEN' \
            'DNSMASQ_UPSTREAM_TARGET DNSMASQ_UPSTREAM' \
            'MIHOMO_DNS_LISTENER MIHOMO_LISTENER'; do
            set -- $openkill_shadow_runtime_dns_state_pair
            openkill_shadow_runtime_dns_state_value=
            openkill_shadow_auto_lookup_file "$1" "$openkill_shadow_runtime_dns_state_file" >/dev/null 2>&1
            openkill_shadow_runtime_dns_state_rc=$?
            [ "$openkill_shadow_runtime_dns_state_rc" -eq 0 ] || continue
            openkill_shadow_runtime_dns_state_value=$openkill_shadow_auto_lookup_result
            case "$1" in
               DNSMASQ_LISTEN_TARGET)
                  [ -z "$openkill_shadow_runtime_dns_listener" ] || [ "$openkill_shadow_runtime_dns_listener" = "$openkill_shadow_runtime_dns_state_value" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
                  openkill_shadow_runtime_dns_listener=$openkill_shadow_runtime_dns_state_value
                  openkill_shadow_runtime_dns_listener_source=fixture-committed-dnsmasq
                  ;;
               DNSMASQ_UPSTREAM_TARGET)
                  [ -z "$openkill_shadow_runtime_dns_upstream" ] || [ "$openkill_shadow_runtime_dns_upstream" = "$openkill_shadow_runtime_dns_state_value" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
                  openkill_shadow_runtime_dns_upstream=$openkill_shadow_runtime_dns_state_value
                  openkill_shadow_runtime_dns_upstream_source=fixture-committed-dnsmasq
                  ;;
               MIHOMO_DNS_LISTENER)
                  [ -z "$openkill_shadow_runtime_dns_mihomo" ] || [ "$openkill_shadow_runtime_dns_mihomo" = "$openkill_shadow_runtime_dns_state_value" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
                  openkill_shadow_runtime_dns_mihomo=$openkill_shadow_runtime_dns_state_value
                  openkill_shadow_runtime_dns_mihomo_source=fixture-committed-runtime
                  ;;
            esac
         done
      done
   fi
   if [ -z "$openkill_shadow_runtime_dns_listener" ]; then
      openkill_shadow_runtime_dns_listener=${DNSPORT:-}
      [ -z "$openkill_shadow_runtime_dns_listener" ] || openkill_shadow_runtime_dns_listener_source=committed-dnsmasq-port
   fi
   if [ -z "$openkill_shadow_runtime_dns_listener" ]; then
      openkill_shadow_runtime_dns_listener=${OPENKILL_DNSMASQ_LISTEN_TARGET:-${DNSMASQ_LISTEN_TARGET:-${dnsmasq_listen_target:-}}}
      [ -z "$openkill_shadow_runtime_dns_listener" ] || openkill_shadow_runtime_dns_listener_source=committed-dnsmasq-port
   fi
   if [ -z "$openkill_shadow_runtime_dns_listener" ] && command -v netstat >/dev/null 2>&1; then
      openkill_shadow_runtime_dns_listener=$(netstat -nlp 2>/dev/null |
         awk '/dnsmasq([[:space:]]|$)/ && $4 ~ /:[0-9]+$/ { value=$4; sub(/^.*:/, "", value); if (value ~ /^[0-9]+$/ && !(value in seen)) { seen[value]=1; count++ } } END { if (count == 1) for (value in seen) print value; else if (count > 1) exit 2 }')
      openkill_shadow_runtime_dns_listener_rc=$?
      [ "$openkill_shadow_runtime_dns_listener_rc" -eq 0 ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      [ -z "$openkill_shadow_runtime_dns_listener" ] || openkill_shadow_runtime_dns_listener_source=netstat-dnsmasq
   fi

   # A list of upstream servers is not silently collapsed.  The current
   # contract has one local endpoint; multiple/ambiguous values remain a
   # source gap until a typed list representation is formally added.
   openkill_shadow_runtime_dns_upstream=$(printf '%s\n' "$openkill_shadow_runtime_dns_upstream" |
      awk '{ gsub(/[[:space:]]+/, " "); sub(/^ +/, ""); sub(/ +$/, ""); print }')
   if [ -z "$openkill_shadow_runtime_dns_upstream" ]; then
      if [ "$openkill_shadow_runtime_dns_has_uci" -eq 0 ]; then
         openkill_shadow_runtime_dns_upstream=${OPENKILL_DNSMASQ_UPSTREAM_TARGET:-${DNSMASQ_UPSTREAM_TARGET:-${dnsmasq_upstream_target:-}}}
         [ -z "$openkill_shadow_runtime_dns_upstream" ] || openkill_shadow_runtime_dns_upstream_source=committed-dnsmasq
      fi
   fi
   case "$openkill_shadow_runtime_dns_upstream" in
      *\ *|*','*|*';'*) return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP" ;;
   esac

   # OPENKILL_DNS_ENDPOINT and its aliases describe desired/readiness intent,
   # not a live socket.  Mihomo commonly exposes an API or proxy TCP port in
   # addition to DNS.  Use the process-owned UDP listener as the DNS evidence:
   # a DNS socket must be observable as UDP, while unrelated TCP listeners are
   # ignored.  Core names are restricted to the binaries OpenKill supports;
   # an unknown process name, multiple UDP ports, or no UDP evidence is a
   # source gap.  The selected endpoint is still the socket address emitted by
   # netstat, never a value inferred from configuration intent.
   if [ -z "$openkill_shadow_runtime_dns_mihomo" ] && command -v netstat >/dev/null 2>&1; then
      openkill_shadow_runtime_dns_mihomo=$(netstat -nlp 2>/dev/null |
         awk '
            function core_process(value, name) {
               name=value
               sub(/^.*\//, "", name)
               return name ~ /^(mihomo|clash|clash_meta|clash-meta)([-_.].*)?$/
            }
            $1 ~ /^udp/ && $4 ~ /:[0-9]+$/ && core_process($NF) {
               value=$4
               if (!(value in seen)) { seen[value]=1; count++ }
            }
            END {
               if (count == 1) for (value in seen) print value
               else if (count > 1) exit 2
            }')
      openkill_shadow_runtime_dns_mihomo_rc=$?
      [ "$openkill_shadow_runtime_dns_mihomo_rc" -eq 0 ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      [ -z "$openkill_shadow_runtime_dns_mihomo" ] || openkill_shadow_runtime_dns_mihomo_source=netstat-mihomo-udp
   fi

   for openkill_shadow_runtime_dns_value in \
      "$openkill_shadow_runtime_dns_listener" \
      "$openkill_shadow_runtime_dns_upstream" \
      "$openkill_shadow_runtime_dns_mihomo"; do
      openkill_shadow_safe_value "$openkill_shadow_runtime_dns_value" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   done
   [ -n "$openkill_shadow_runtime_dns_listener_source" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   [ -n "$openkill_shadow_runtime_dns_upstream_source" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   [ -n "$openkill_shadow_runtime_dns_mihomo_source" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   for openkill_shadow_runtime_dns_source in \
      "$openkill_shadow_runtime_dns_listener_source" \
      "$openkill_shadow_runtime_dns_upstream_source" \
      "$openkill_shadow_runtime_dns_mihomo_source"; do
      openkill_shadow_safe_value "$openkill_shadow_runtime_dns_source" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   done
   case "$openkill_shadow_runtime_dns_listener" in ''|*[!0-9]*) return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP" ;; esac
   [ "$openkill_shadow_runtime_dns_listener" -ge 1 ] 2>/dev/null &&
      [ "$openkill_shadow_runtime_dns_listener" -le 65535 ] 2>/dev/null ||
      return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   case "$openkill_shadow_runtime_dns_upstream" in
      ''|*[!A-Za-z0-9.:#_\[\]-]*) return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP" ;;
   esac
   case "$openkill_shadow_runtime_dns_mihomo" in
      ''|*[!A-Za-z0-9.:#_\[\]-]*) return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP" ;;
   esac

   # Keep the frozen values in a private, bounded artifact for diagnostics and
   # make the shell variables explicit inputs to the continuity token.  The
   # producer reads these values only after T0 from this private snapshot.
   openkill_shadow_runtime_dns_file=$openkill_shadow_runtime_dns_state_dir/runtime-dns
   openkill_shadow_safe_path "$openkill_shadow_runtime_dns_file" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   umask 077
   {
      printf 'OPENKILL_SHADOW_RUNTIME_DNS_V1=1\n'
      printf 'DNSMASQ_LISTEN_TARGET=%s\n' "$openkill_shadow_runtime_dns_listener"
      printf 'DNSMASQ_UPSTREAM_TARGET=%s\n' "$openkill_shadow_runtime_dns_upstream"
      printf 'MIHOMO_DNS_LISTENER=%s\n' "$openkill_shadow_runtime_dns_mihomo"
      printf 'DNSMASQ_LISTEN_SOURCE=%s\n' "$openkill_shadow_runtime_dns_listener_source"
      printf 'DNSMASQ_UPSTREAM_SOURCE=%s\n' "$openkill_shadow_runtime_dns_upstream_source"
      printf 'MIHOMO_DNS_LISTENER_SOURCE=%s\n' "$openkill_shadow_runtime_dns_mihomo_source"
   } > "$openkill_shadow_runtime_dns_file" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   chmod 600 "$openkill_shadow_runtime_dns_file" 2>/dev/null || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"

   OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_LISTEN_TARGET=$openkill_shadow_runtime_dns_listener
   OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_UPSTREAM_TARGET=$openkill_shadow_runtime_dns_upstream
   OPENKILL_NFT_SHADOW_FROZEN_MIHOMO_DNS_LISTENER=$openkill_shadow_runtime_dns_mihomo
   OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_LISTEN_SOURCE=$openkill_shadow_runtime_dns_listener_source
   OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_UPSTREAM_SOURCE=$openkill_shadow_runtime_dns_upstream_source
   OPENKILL_NFT_SHADOW_FROZEN_MIHOMO_DNS_SOURCE=$openkill_shadow_runtime_dns_mihomo_source
   return 0
}

openkill_shadow_auto_continuity_dns_check()
{
   # Re-sample live DNS sources only at a continuity boundary.  The typed
   # producer never calls this helper: it consumes the T0 runtime-dns copy.
   # A missing source is a fail-closed source gap; a changed source makes the
   # whole cycle stale rather than mixing observations from different times.
   openkill_shadow_dns_check_expected=$1
   openkill_shadow_dns_check_root=$2
   openkill_shadow_dns_check_label=$3
   [ -r "$openkill_shadow_dns_check_expected" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_safe_path "$openkill_shadow_dns_check_expected" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_safe_path "$openkill_shadow_dns_check_root" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_safe_value "$openkill_shadow_dns_check_label" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_dns_check_dir=$openkill_shadow_dns_check_root/dns-$openkill_shadow_dns_check_label
   openkill_shadow_safe_path "$openkill_shadow_dns_check_dir" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   rm -rf "$openkill_shadow_dns_check_dir"
   mkdir -p "$openkill_shadow_dns_check_dir" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   chmod 700 "$openkill_shadow_dns_check_dir" 2>/dev/null || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   (
      openkill_shadow_capture_runtime_dns "$openkill_shadow_dns_check_dir"
   )
   openkill_shadow_dns_check_rc=$?
   [ "$openkill_shadow_dns_check_rc" -eq 0 ] || {
      rm -rf "$openkill_shadow_dns_check_dir"
      return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   }
   openkill_shadow_dns_check_actual=$openkill_shadow_dns_check_dir/runtime-dns
   openkill_shadow_safe_path "$openkill_shadow_dns_check_actual" || {
      rm -rf "$openkill_shadow_dns_check_dir"
      return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   }
   if ! cmp -s "$openkill_shadow_dns_check_expected" "$openkill_shadow_dns_check_actual"; then
      rm -rf "$openkill_shadow_dns_check_dir"
      return "$OPENKILL_NFT_SHADOW_RC_STALE"
   fi
   return 0
}

openkill_shadow_auto_continuity_snapshot()
{
   openkill_shadow_continuity_root=$1
   [ -n "$openkill_shadow_continuity_root" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_safe_path "$openkill_shadow_continuity_root" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_continuity_state_dir=$openkill_shadow_continuity_root/auto-state
   openkill_shadow_safe_path "$openkill_shadow_continuity_state_dir" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   mkdir -p "$openkill_shadow_continuity_state_dir" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   chmod 700 "$openkill_shadow_continuity_state_dir" 2>/dev/null || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"

   openkill_shadow_continuity_live_desired=${OPENKILL_NETWORK_DESIRED:-}
   openkill_shadow_continuity_live_applied=${OPENKILL_NETWORK_APPLIED_FILE:-/tmp/openkill-network.applied}
   openkill_shadow_continuity_live_snapshot=${OPENKILL_NETWORK_SNAPSHOT:-/tmp/openkill-network.snapshot}
   openkill_shadow_continuity_live_node4=${OPENKILL_NFT_SHADOW_NODE4_FILE:-/tmp/openkill-node4.desired}
   openkill_shadow_continuity_live_node6=${OPENKILL_NFT_SHADOW_NODE6_FILE:-/tmp/openkill-node6.desired}
   [ -n "$openkill_shadow_continuity_live_applied" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_safe_path "$openkill_shadow_continuity_live_applied" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_safe_path "$openkill_shadow_continuity_live_snapshot" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_safe_path "$openkill_shadow_continuity_live_node4" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_safe_path "$openkill_shadow_continuity_live_node6" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   if [ -n "$openkill_shadow_continuity_live_desired" ]; then
      openkill_shadow_safe_path "$openkill_shadow_continuity_live_desired" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   fi

   # Freeze all runtime DNS values before calculating T0.  This keeps the
   # actual typed sidecar coupled to the same coherent cycle as the committed
   # network sources and prevents any comparator-stage live reread.
   openkill_shadow_capture_runtime_dns "$openkill_shadow_continuity_state_dir" || return $?

   openkill_shadow_continuity_t0_work=$openkill_shadow_continuity_state_dir/t0
   openkill_shadow_continuity_t1_work=$openkill_shadow_continuity_state_dir/t1
   openkill_shadow_continuity_t0=$openkill_shadow_continuity_state_dir/t0.token
   openkill_shadow_continuity_t1=$openkill_shadow_continuity_state_dir/t1.token
   openkill_shadow_auto_continuity_token "$openkill_shadow_continuity_t0" "$openkill_shadow_continuity_t0_work" \
      "$openkill_shadow_continuity_live_desired" "$openkill_shadow_continuity_live_applied" \
      "$openkill_shadow_continuity_live_snapshot" "$openkill_shadow_continuity_live_node4" "$openkill_shadow_continuity_live_node6" \
      "$openkill_shadow_continuity_state_dir/runtime-dns" > "$openkill_shadow_continuity_state_dir/t0.stdout" || return $?
   chmod 600 "$openkill_shadow_continuity_state_dir/t0.stdout" 2>/dev/null || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_continuity_t0_value=$(sed -n '1p' "$openkill_shadow_continuity_t0") || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"

   openkill_shadow_continuity_copy_dir=$openkill_shadow_continuity_state_dir/copy
   mkdir -p "$openkill_shadow_continuity_copy_dir" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   chmod 700 "$openkill_shadow_continuity_copy_dir" 2>/dev/null || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_continuity_applied_copy=$openkill_shadow_continuity_copy_dir/applied
   openkill_shadow_auto_continuity_copy "$openkill_shadow_continuity_live_applied" "$openkill_shadow_continuity_applied_copy" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   if [ -n "$openkill_shadow_continuity_live_desired" ] && [ -r "$openkill_shadow_continuity_live_desired" ]; then
      openkill_shadow_continuity_desired_copy=$openkill_shadow_continuity_copy_dir/desired
      openkill_shadow_auto_continuity_copy "$openkill_shadow_continuity_live_desired" "$openkill_shadow_continuity_desired_copy" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   else
      openkill_shadow_continuity_desired_copy=
   fi
   if [ -r "$openkill_shadow_continuity_live_snapshot" ]; then
      openkill_shadow_continuity_snapshot_copy=$openkill_shadow_continuity_copy_dir/snapshot
      openkill_shadow_auto_continuity_copy "$openkill_shadow_continuity_live_snapshot" "$openkill_shadow_continuity_snapshot_copy" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   else
      openkill_shadow_continuity_snapshot_copy=
   fi
   if [ -r "$openkill_shadow_continuity_live_node4" ]; then
      openkill_shadow_continuity_node4_copy=$openkill_shadow_continuity_copy_dir/node4
      openkill_shadow_auto_continuity_copy "$openkill_shadow_continuity_live_node4" "$openkill_shadow_continuity_node4_copy" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   else
      openkill_shadow_continuity_node4_copy=
   fi
   if [ -r "$openkill_shadow_continuity_live_node6" ]; then
      openkill_shadow_continuity_node6_copy=$openkill_shadow_continuity_copy_dir/node6
      openkill_shadow_auto_continuity_copy "$openkill_shadow_continuity_live_node6" "$openkill_shadow_continuity_node6_copy" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
    else
       openkill_shadow_continuity_node6_copy=
    fi

    openkill_shadow_continuity_copy_matches applied "$openkill_shadow_continuity_live_applied" state "$openkill_shadow_continuity_applied_copy" "$openkill_shadow_continuity_t0_work/components" || return "$OPENKILL_NFT_SHADOW_RC_STALE"
    if [ -n "$openkill_shadow_continuity_desired_copy" ]; then
       openkill_shadow_continuity_copy_matches desired "$openkill_shadow_continuity_live_desired" state "$openkill_shadow_continuity_desired_copy" "$openkill_shadow_continuity_t0_work/components" || return "$OPENKILL_NFT_SHADOW_RC_STALE"
    fi
    if [ -n "$openkill_shadow_continuity_snapshot_copy" ]; then
       openkill_shadow_continuity_copy_matches snapshot "$openkill_shadow_continuity_live_snapshot" state "$openkill_shadow_continuity_snapshot_copy" "$openkill_shadow_continuity_t0_work/components" || return "$OPENKILL_NFT_SHADOW_RC_STALE"
    fi
    if [ -n "$openkill_shadow_continuity_node4_copy" ]; then
       openkill_shadow_continuity_copy_matches node4 "$openkill_shadow_continuity_live_node4" node "$openkill_shadow_continuity_node4_copy" "$openkill_shadow_continuity_t0_work/components" || return "$OPENKILL_NFT_SHADOW_RC_STALE"
    fi
    if [ -n "$openkill_shadow_continuity_node6_copy" ]; then
       openkill_shadow_continuity_copy_matches node6 "$openkill_shadow_continuity_live_node6" node "$openkill_shadow_continuity_node6_copy" "$openkill_shadow_continuity_t0_work/components" || return "$OPENKILL_NFT_SHADOW_RC_STALE"
    fi

   # T1 is a continuity boundary for runtime DNS as well as committed state.
   # The check runs in a subshell so the T0-frozen DNS scalars remain the only
   # values available to the producer.
   openkill_shadow_auto_continuity_dns_check \
      "$openkill_shadow_continuity_state_dir/runtime-dns" \
      "$openkill_shadow_continuity_state_dir" t1 || return $?

   # Explicitly opt-in test hooks are used only to exercise the race contract;
   # production never sets them and no arbitrary command is executed.
   if [ "${OPENKILL_NFT_SHADOW_TEST_HOOK:-0}" = 1 ] && [ -n "${OPENKILL_NFT_SHADOW_TEST_AFTER_COPY_FILE:-}" ]; then
      openkill_shadow_safe_path "$OPENKILL_NFT_SHADOW_TEST_AFTER_COPY_FILE" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      # Keep the fixture syntactically valid while adding a distinct
      # committed-state record.  The duplicate key is intentional: the
      # canonicalizer includes both values, so an update cannot be hidden by
      # replacing the whole source with malformed test text.
      printf '%s\n' "${OPENKILL_NFT_SHADOW_TEST_AFTER_COPY_VALUE:-MARK=0x163}" >> "$OPENKILL_NFT_SHADOW_TEST_AFTER_COPY_FILE" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   fi

   openkill_shadow_auto_continuity_token "$openkill_shadow_continuity_t1" "$openkill_shadow_continuity_t1_work" \
      "$openkill_shadow_continuity_live_desired" "$openkill_shadow_continuity_live_applied" \
      "$openkill_shadow_continuity_live_snapshot" "$openkill_shadow_continuity_live_node4" "$openkill_shadow_continuity_live_node6" \
      "$openkill_shadow_continuity_state_dir/dns-t1/runtime-dns" > "$openkill_shadow_continuity_state_dir/t1.stdout" || return $?
   chmod 600 "$openkill_shadow_continuity_state_dir/t1.stdout" 2>/dev/null || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_continuity_t1_value=$(sed -n '1p' "$openkill_shadow_continuity_t1") || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   [ "$openkill_shadow_continuity_t0_value" = "$openkill_shadow_continuity_t1_value" ] || return "$OPENKILL_NFT_SHADOW_RC_STALE"

   if [ -n "$openkill_shadow_continuity_desired_copy" ] && ! cmp -s "$openkill_shadow_continuity_desired_copy" "$openkill_shadow_continuity_applied_copy"; then
      return "$OPENKILL_NFT_SHADOW_RC_STALE"
   fi

   # Force all subsequent producer reads to the private copies.  The original
   # paths remain saved above for the final live T2 token calculation.
   if [ -n "$openkill_shadow_continuity_desired_copy" ]; then OPENKILL_NETWORK_DESIRED=$openkill_shadow_continuity_desired_copy; else OPENKILL_NETWORK_DESIRED=; fi
   OPENKILL_NETWORK_APPLIED_FILE=$openkill_shadow_continuity_applied_copy
   if [ -n "$openkill_shadow_continuity_snapshot_copy" ]; then OPENKILL_NETWORK_SNAPSHOT=$openkill_shadow_continuity_snapshot_copy; else OPENKILL_NETWORK_SNAPSHOT=$openkill_shadow_continuity_state_dir/no-snapshot; fi
   if [ -n "$openkill_shadow_continuity_node4_copy" ]; then OPENKILL_NFT_SHADOW_NODE4_FILE=$openkill_shadow_continuity_node4_copy; else OPENKILL_NFT_SHADOW_NODE4_FILE=$openkill_shadow_continuity_state_dir/no-node4; fi
   if [ -n "$openkill_shadow_continuity_node6_copy" ]; then OPENKILL_NFT_SHADOW_NODE6_FILE=$openkill_shadow_continuity_node6_copy; else OPENKILL_NFT_SHADOW_NODE6_FILE=$openkill_shadow_continuity_state_dir/no-node6; fi
   openkill_shadow_continuity_token_value=$openkill_shadow_continuity_t1_value
   openkill_shadow_continuity_token_t0=$openkill_shadow_continuity_t0_value
   openkill_shadow_continuity_token_t1=$openkill_shadow_continuity_t1_value
   return 0
}

openkill_shadow_auto_owner()
{
   openkill_shadow_auto_field OWNER TUN_OWNER || return 1
   openkill_shadow_auto_owner_value=$(openkill_shadow_normalize_owner "$openkill_shadow_auto_field_value") || return 1
   printf '%s\n' "$openkill_shadow_auto_owner_value"
}

openkill_shadow_auto_template()
{
   openkill_shadow_auto_template_mode=$1
   openkill_shadow_auto_template_dir=${OPENKILL_NFT_SHADOW_TEMPLATE_DIR:-/usr/share/openkill/shadow}
   openkill_shadow_safe_path "$openkill_shadow_auto_template_dir" || return 1
   case "$openkill_shadow_auto_template_mode" in
      TUN) openkill_shadow_auto_template_name=input_tun_v1.tsv ;;
      TPROXY) openkill_shadow_auto_template_name=input_tproxy_v1.tsv ;;
      REDIRECT) openkill_shadow_auto_template_name=input_redirect_v1.tsv ;;
      *) return 1 ;;
   esac
   openkill_shadow_auto_template_path=$openkill_shadow_auto_template_dir/$openkill_shadow_auto_template_name
   openkill_shadow_safe_path "$openkill_shadow_auto_template_path" || return 1
   [ -r "$openkill_shadow_auto_template_path" ] || return 1
   printf '%s\n' "$openkill_shadow_auto_template_path"
}

openkill_shadow_build_auto_input()
{
   openkill_shadow_auto_output=$1
   [ -n "$openkill_shadow_auto_output" ] || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
   openkill_shadow_safe_path "$openkill_shadow_auto_output" || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
   openkill_shadow_auto_source_file=
   openkill_shadow_auto_source_requested=${OPENKILL_NFT_SHADOW_SOURCE_FILE:-${OPENKILL_NFT_SHADOW_AUTO_STATE_FILE:-${OPENKILL_NFT_SHADOW_STATE_SOURCE:-}}}
   if [ -n "$openkill_shadow_auto_source_requested" ]; then
      openkill_shadow_auto_source_file=$(openkill_shadow_auto_source_path) || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      openkill_shadow_auto_header=$(sed -n '1p' "$openkill_shadow_auto_source_file") || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      case "$openkill_shadow_auto_header" in
         OPENKILL_NFT_SHADOW_AUTO_STATE_V1=1|OPENKILL_SHADOW_SOURCE_V1=1|SHELL_RENDERER_STATE_V1=1) ;;
         *) return "$OPENKILL_NFT_SHADOW_RC_UNSUPPORTED" ;;
      esac
   fi
   # Unsupported CURRENT facts must be rejected before a renderer input is
   # constructed.  These flags are facts emitted by the upstream semantic
   # state; they are never inferred from ordinary ACCESS*_DENY set contents.
   for openkill_shadow_auto_unsupported_key in \
      BC01_UNSUPPORTED BC_01_UNSUPPORTED CURRENT_UNDEFINED \
      EXPLICIT_POLICY_CURRENT_UNDEFINED CURRENT_ACCESS_DENY \
      BC07_UNSUPPORTED BC_07_UNSUPPORTED ACCESS_DENY_REQUIRED; do
      openkill_shadow_auto_lookup "$openkill_shadow_auto_unsupported_key"
      openkill_shadow_auto_unsupported_rc=$?
      case "$openkill_shadow_auto_unsupported_rc" in
         0)
            openkill_shadow_is_unsupported_true "$openkill_shadow_auto_value" &&
               return "$OPENKILL_NFT_SHADOW_RC_UNSUPPORTED"
         ;;
         "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP") return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP" ;;
      esac
   done
   openkill_shadow_auto_owner_value=$(openkill_shadow_auto_owner 2>/dev/null || true)
   [ -n "$openkill_shadow_auto_owner_value" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   # MIHOMO/DISABLED are an explicit no-owner path.  Emit only the protocol
   # header and owner so the coordinator can publish DISABLED without reading
   # a set, invoking nft, or inventing listener defaults.
   case "$openkill_shadow_auto_owner_value" in
      MIHOMO|DISABLED)
         {
            printf 'SHELL_RENDERER_INPUT_V1\t1\n'
            printf 'META\tprofile\tcurrent\nMETA\towner\t%s\n' "$openkill_shadow_auto_owner_value"
         } > "$openkill_shadow_auto_output" || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
         return 0
      ;;
      UNKNOWN) return "$OPENKILL_NFT_SHADOW_RC_INPUT" ;;
   esac

   openkill_shadow_auto_field RUN_MODE || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_auto_run_mode=$(openkill_shadow_normalize_run_mode "$openkill_shadow_auto_field_value") || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_auto_field REDIRECT_PORT PROXY_PORT || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_auto_redirect_port=$openkill_shadow_auto_field_value
   openkill_shadow_auto_field TPROXY_PORT || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_auto_tproxy_port=$openkill_shadow_auto_field_value
   openkill_shadow_auto_field DNS_PORT || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_auto_dns_port=$openkill_shadow_auto_field_value
   openkill_shadow_auto_field ROUTER_SELF_PROXY || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_auto_router_self=$openkill_shadow_auto_field_value
   openkill_shadow_auto_field MARK OPENKILL_FWMARK || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_auto_mark=$openkill_shadow_auto_field_value
   openkill_shadow_auto_field MASK OPENKILL_FWMASK || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_auto_mask=$openkill_shadow_auto_field_value
   openkill_shadow_auto_field ROUTE_TABLE OPENKILL_ROUTE_TABLE || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_auto_table=$openkill_shadow_auto_field_value
   openkill_shadow_auto_field RULE_PREF OPENKILL_RULE_PREF || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_auto_pref=$openkill_shadow_auto_field_value
   # GENERATION is retained only for explicit development fixtures.  The
   # production automatic path receives its content-derived continuity token
   # from openkill_shadow_auto_continuity_snapshot and never consults the
   # legacy /tmp/openkill-network-reconcile/generation helper file.
   openkill_shadow_auto_generation=
   if [ -n "${openkill_shadow_auto_source_file:-}" ]; then
      openkill_shadow_auto_field GENERATION
      openkill_shadow_auto_generation_rc=$?
      if [ "$openkill_shadow_auto_generation_rc" -eq 0 ]; then
         openkill_shadow_auto_generation=$openkill_shadow_auto_field_value
      elif [ -n "${OPENKILL_NFT_SHADOW_GENERATION_FILE:-}" ]; then
         openkill_shadow_auto_generation_file=$OPENKILL_NFT_SHADOW_GENERATION_FILE
         openkill_shadow_safe_path "$openkill_shadow_auto_generation_file" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
         [ -r "$openkill_shadow_auto_generation_file" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
         openkill_shadow_auto_generation=$(sed -n '1p' "$openkill_shadow_auto_generation_file") || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      else
         return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      fi
      openkill_shadow_safe_value "$openkill_shadow_auto_generation" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   elif [ -n "${openkill_shadow_continuity_token_value:-}" ]; then
      openkill_shadow_auto_generation=$openkill_shadow_continuity_token_value
   fi

   openkill_shadow_auto_template_file=$(openkill_shadow_auto_template "$openkill_shadow_auto_run_mode") || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
   [ "$(sed -n '1p' "$openkill_shadow_auto_template_file")" = 'SHELL_RENDERER_INPUT_V1	1' ] || return "$OPENKILL_NFT_SHADOW_RC_UNSUPPORTED"

   # Build all dynamic sets from the same normalized source.  Missing optional
   # sets become empty ("-"); required scalar values above never receive a
   # development default.
   openkill_shadow_auto_set_value()
   {
      openkill_shadow_auto_set_key=$1; shift
      openkill_shadow_auto_field "$@" 2>/dev/null || openkill_shadow_auto_field_value=
      openkill_shadow_auto_set_value_result=$(openkill_shadow_auto_list "$openkill_shadow_auto_field_value") || return 1
      printf '%s\n' "$openkill_shadow_auto_set_value_result"
   }
   auto_access4_allow=$(openkill_shadow_auto_set_value ACCESS4_ALLOW ACCESS4_ALLOW LAN_AC_WHITE_V4 USER_DIRECT_V4 || true)
   auto_access4_bypass=$(openkill_shadow_auto_set_value ACCESS4_BYPASS ACCESS4_BYPASS || true)
   auto_access4_deny=$(openkill_shadow_auto_set_value ACCESS4_DENY ACCESS4_DENY LAN_AC_BLACK_V4 || true)
   auto_access6_allow=$(openkill_shadow_auto_set_value ACCESS6_ALLOW ACCESS6_ALLOW LAN_AC_WHITE_V6 USER_DIRECT_V6 || true)
   auto_access6_bypass=$(openkill_shadow_auto_set_value ACCESS6_BYPASS ACCESS6_BYPASS || true)
   auto_access6_deny=$(openkill_shadow_auto_set_value ACCESS6_DENY ACCESS6_DENY LAN_AC_BLACK_V6 || true)
   auto_china_pass4=$(openkill_shadow_auto_set_value CHINA_PASS4 CHINA_PASS4 || true)
   auto_china_pass6=$(openkill_shadow_auto_set_value CHINA_PASS6 CHINA_PASS6 || true)
   auto_china4=$(openkill_shadow_auto_set_value CHINA4 CHINA4 || true)
   auto_china6=$(openkill_shadow_auto_set_value CHINA6 CHINA6 || true)
   auto_common_ports=$(openkill_shadow_auto_set_value COMMON_PORTS COMMON_PORTS SERVICE_PORTS || true)
   auto_delegated6=$(openkill_shadow_auto_set_value DELEGATED6 DELEGATED6 PD6 DELEGATED_IPV6_PREFIXES || true)
   auto_fake4=$(openkill_shadow_auto_set_value FAKE_IP4 FAKEIP4 FAKE_IP4 || true)
   auto_fake6=$(openkill_shadow_auto_set_value FAKE_IP6 FAKEIP6 FAKE_IP6 || true)
   auto_lan4=$(openkill_shadow_auto_set_value LAN4 LAN4 LAN_IPV4_PREFIXES || true)
   auto_lan6=$(openkill_shadow_auto_set_value LAN6 LAN6 LAN_IPV6_PREFIXES || true)
   auto_local4=$(openkill_shadow_auto_set_value LOCAL4 LOCAL4 LOCAL_V4 LOCALNETWORK4 LOCALNETWORK4_PREFIXES INTERNAL_IPV4_PREFIXES || true)
   auto_local6=$(openkill_shadow_auto_set_value LOCAL6 LOCAL6 LOCAL_V6 LOCALNETWORK6 LOCALNETWORK6_PREFIXES INTERNAL_IPV6_PREFIXES || true)
   auto_node4=$(openkill_shadow_auto_set_value NODE4 NODE4 NODE4_ENDPOINTS || true)
   auto_node6=$(openkill_shadow_auto_set_value NODE6 NODE6 NODE6_ENDPOINTS || true)
   auto_service=$(openkill_shadow_auto_set_value SERVICE_PORTS SERVICE_PORTS || true)
   auto_ud4=$(openkill_shadow_auto_set_value USER_DIRECT4 USER_DIRECT4 || true)
   auto_ud6=$(openkill_shadow_auto_set_value USER_DIRECT6 USER_DIRECT6 || true)
   auto_up4=$(openkill_shadow_auto_set_value USER_PROXY4 USER_PROXY4 || true)
   auto_up6=$(openkill_shadow_auto_set_value USER_PROXY6 USER_PROXY6 || true)
   auto_wan4=$(openkill_shadow_auto_set_value WAN4 WAN4 WAN_HOST4 WAN4_HOST WAN4_HOST_ADDRESSES WAN4_ADDRESSES || true)
   auto_wan6=$(openkill_shadow_auto_set_value WAN6 WAN6 WAN_HOST6 WAN6_HOST WAN6_HOST_ADDRESSES WAN6_ADDRESSES || true)
   auto_black_ports=$(openkill_shadow_auto_set_value WAN_AC_BLACK_PORTS WAN_AC_BLACK_PORTS || true)
   auto_black4=$(openkill_shadow_auto_set_value WAN_AC_BLACK_V4 WAN_AC_BLACK_V4 || true)
   auto_black6=$(openkill_shadow_auto_set_value WAN_AC_BLACK_V6 WAN_AC_BLACK_V6 || true)

   awk -F '\t' -v OFS='\t' \
      -v owner="$openkill_shadow_auto_owner_value" -v mode="$openkill_shadow_auto_run_mode" \
      -v redirect="$openkill_shadow_auto_redirect_port" -v tproxy="$openkill_shadow_auto_tproxy_port" \
      -v dns="$openkill_shadow_auto_dns_port" -v self="$openkill_shadow_auto_router_self" \
      -v mark="$openkill_shadow_auto_mark" -v mask="$openkill_shadow_auto_mask" \
      -v table="$openkill_shadow_auto_table" -v pref="$openkill_shadow_auto_pref" \
      -v a4a="$auto_access4_allow" -v a4b="$auto_access4_bypass" -v a4d="$auto_access4_deny" \
      -v a6a="$auto_access6_allow" -v a6b="$auto_access6_bypass" -v a6d="$auto_access6_deny" \
      -v cp4="$auto_china_pass4" -v cp6="$auto_china_pass6" -v c4="$auto_china4" -v c6="$auto_china6" \
      -v ports="$auto_common_ports" -v d6="$auto_delegated6" -v f4="$auto_fake4" -v f6="$auto_fake6" \
      -v l4="$auto_lan4" -v l6="$auto_lan6" -v loc4="$auto_local4" -v loc6="$auto_local6" \
      -v n4="$auto_node4" -v n6="$auto_node6" -v svc="$auto_service" \
      -v ud4="$auto_ud4" -v ud6="$auto_ud6" -v up4="$auto_up4" -v up6="$auto_up6" \
      -v w4="$auto_wan4" -v w6="$auto_wan6" -v bp="$auto_black_ports" -v b4="$auto_black4" -v b6="$auto_black6" '
      $1 == "META" {
         if ($2 == "owner") $3=owner
         else if ($2 == "run_mode") $3=mode
         else if ($2 == "redirect_port") $3=redirect
         else if ($2 == "tproxy_port") $3=tproxy
         else if ($2 == "dns_port") $3=dns
         else if ($2 == "router_self_proxy") $3=self
         else if ($2 == "mark") $3=mark
         else if ($2 == "mask") $3=mask
         else if ($2 == "route_table") $3=table
         else if ($2 == "rule_pref") $3=pref
      }
      $1 == "SET" {
         if ($2 == "ACCESS_V4_ALLOW") $7=a4a
         else if ($2 == "ACCESS_V4_BYPASS") $7=a4b
         else if ($2 == "ACCESS_V4_DENY") $7=a4d
         else if ($2 == "ACCESS_V6_ALLOW") $7=a6a
         else if ($2 == "ACCESS_V6_BYPASS") $7=a6b
         else if ($2 == "ACCESS_V6_DENY") $7=a6d
         else if ($2 == "CHINA_PASS_V4") $7=cp4
         else if ($2 == "CHINA_PASS_V6") $7=cp6
         else if ($2 == "CHINA_V4") $7=c4
         else if ($2 == "CHINA_V6") $7=c6
         else if ($2 == "COMMON_PORTS") $7=ports
         else if ($2 == "DELEGATED_V6") $7=d6
         else if ($2 == "FAKEIP_V4") $7=f4
         else if ($2 == "FAKEIP_V6") $7=f6
         else if ($2 == "LAN_V4") $7=l4
         else if ($2 == "LAN_V6") $7=l6
         else if ($2 == "LOCAL_V4") $7=loc4
         else if ($2 == "LOCAL_V6") $7=loc6
         else if ($2 == "NODE_ENDPOINT_V4") $7=n4
         else if ($2 == "NODE_ENDPOINT_V6") $7=n6
         else if ($2 == "SERVICE_PORTS") $7=svc
         else if ($2 == "USER_DIRECT_V4") $7=ud4
         else if ($2 == "USER_DIRECT_V6") $7=ud6
         else if ($2 == "USER_PROXY_V4") $7=up4
         else if ($2 == "USER_PROXY_V6") $7=up6
         else if ($2 == "WAN_AC_BLACK_PORTS") $7=bp
         else if ($2 == "WAN_AC_BLACK_V4") $7=b4
         else if ($2 == "WAN_AC_BLACK_V6") $7=b6
         else if ($2 == "WAN_HOST_V4") $7=w4
         else if ($2 == "WAN_HOST_V6") $7=w6
      }
      { print }
   ' "$openkill_shadow_auto_template_file" > "$openkill_shadow_auto_output" || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
   openkill_shadow_safe_value "$openkill_shadow_auto_output" || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
   return 0
}

# Friendly aliases make the producer a stable API for local fixtures while
# retaining the concise name used by the coordinator.
openkill_shadow_build_renderer_input()
{
   openkill_shadow_build_auto_input "$@"
}

openkill_shadow_auto_state_producer()
{
   openkill_shadow_build_auto_input "$@"
}

# 3E.1 bounded legacy capture --------------------------------------------------
#
# Only the read-only `list chain`/`list set` forms are constructed here.  The
# inventory is deliberately finite and may be narrowed by the caller for a
# test fixture.  A missing object is recorded, never silently treated as an
# empty object.

openkill_shadow_capture_name_ok()
{
   openkill_shadow_capture_name_value=$1
   case "$openkill_shadow_capture_name_value" in
      ''|*[!A-Za-z0-9_]*|[0-9]*) return 1 ;;
   esac
   return 0
}

# `nft list <object>` uses a non-zero result for both an absent object and a
# failed command.  Treat only the well-known object-absence diagnostics as
# MISSING.  Any other diagnostic, including a quiet rc=1, is a capture failure
# and therefore remains fail-closed.  This keeps permission, syntax, and
# executable failures from being reclassified as optional state.
openkill_shadow_capture_absence_error()
{
   openkill_shadow_capture_error_file=$1
   [ -r "$openkill_shadow_capture_error_file" ] || return 1
   [ -s "$openkill_shadow_capture_error_file" ] || return 1
   grep -Eqi 'no such file or directory|does not exist|object[[:space:]]+[^[:space:]]+[[:space:]]+not found|could not process rule.*no such' "$openkill_shadow_capture_error_file" || return 1
   grep -Eqi 'syntax|parse[[:space:]]+error|permission|not permitted|operation not permitted|invalid|unexpected|unknown command' "$openkill_shadow_capture_error_file" && return 1
   return 0
}

openkill_shadow_capture_legacy_nft()
{
   openkill_shadow_capture_output=$1
   [ -n "$openkill_shadow_capture_output" ] || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   openkill_shadow_safe_path "$openkill_shadow_capture_output" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   openkill_shadow_capture_nft=${OPENKILL_NFT_SHADOW_NFT_BIN:-${OPENKILL_NFT_SHADOW_CAPTURE_NFT_BIN:-nft}}
   openkill_shadow_safe_value "$openkill_shadow_capture_nft" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   # Test harnesses may provide a recorded `nft list` transcript.  This hook
   # is intentionally explicit and never selected by a production default.
   if [ -n "${OPENKILL_NFT_SHADOW_CAPTURE_FIXTURE:-}" ]; then
      openkill_shadow_safe_path "$OPENKILL_NFT_SHADOW_CAPTURE_FIXTURE" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
      [ -r "$OPENKILL_NFT_SHADOW_CAPTURE_FIXTURE" ] || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
      cp "$OPENKILL_NFT_SHADOW_CAPTURE_FIXTURE" "$openkill_shadow_capture_output" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
      if [ -n "${OPENKILL_NFT_SHADOW_CAPTURE_TRACE:-}" ]; then
         openkill_shadow_safe_path "$OPENKILL_NFT_SHADOW_CAPTURE_TRACE" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
         printf 'fixture rc=0\n' > "$OPENKILL_NFT_SHADOW_CAPTURE_TRACE"
      fi
      return 0
   fi
   if ! command -v "$openkill_shadow_capture_nft" >/dev/null 2>&1 && [ ! -x "$openkill_shadow_capture_nft" ]; then
      return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_UNAVAILABLE"
   fi
   openkill_shadow_capture_chain_list=${OPENKILL_NFT_SHADOW_CAPTURE_CHAINS:-"dstnat mangle_prerouting mangle_output output srcnat input forward nat_output openkill openkill_v6 openkill_mangle openkill_mangle_v6 openkill_output openkill_output_v6 openkill_mangle_output openkill_mangle_output_v6 openkill_post openkill_post_v6 openkill_dns_hijack openkill_dns_hijack_v6 openkill_dns_redirect openkill_dns_redirect_v6 openkill_upnp openkill_wan_input openkill_wan6_input"}
   openkill_shadow_capture_set_list=${OPENKILL_NFT_SHADOW_CAPTURE_SETS:-"localnetwork localnetwork6 openkill_node4 openkill_node6 china_ip_route china_ip6_route china_ip_route_pass china_ip6_route_pass openkill_access4_allow openkill_access4_bypass openkill_access4_deny openkill_access6_allow openkill_access6_bypass openkill_access6_deny openkill_service_ports common_ports openkill_fakeip4 openkill_fakeip6 openkill_lan4 openkill_lan6 openkill_delegated6 openkill_wan_host4 openkill_wan_host6"}
   openkill_shadow_safe_value "$openkill_shadow_capture_chain_list" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   openkill_shadow_safe_value "$openkill_shadow_capture_set_list" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   openkill_shadow_capture_tmp=${openkill_shadow_capture_output}.tmp.$$
   openkill_shadow_safe_path "$openkill_shadow_capture_tmp" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   : > "$openkill_shadow_capture_tmp" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   printf 'LEGACY_RUNTIME_CAPTURE_V1=%s\n' "$OPENKILL_NFT_SHADOW_CAPTURE_VERSION" >> "$openkill_shadow_capture_tmp"
   openkill_shadow_capture_trace=${OPENKILL_NFT_SHADOW_CAPTURE_TRACE:-}
   [ -z "$openkill_shadow_capture_trace" ] || {
      openkill_shadow_safe_path "$openkill_shadow_capture_trace" || { rm -f "$openkill_shadow_capture_tmp"; return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"; }
      : > "$openkill_shadow_capture_trace" || { rm -f "$openkill_shadow_capture_tmp"; return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"; }
   }
   openkill_shadow_capture_any=0
   for openkill_shadow_capture_chain in $openkill_shadow_capture_chain_list; do
      openkill_shadow_capture_name_ok "$openkill_shadow_capture_chain" || { rm -f "$openkill_shadow_capture_tmp"; return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"; }
      openkill_shadow_capture_any=1
      openkill_shadow_capture_one=${openkill_shadow_capture_output}.one.$$
      openkill_shadow_capture_error=${openkill_shadow_capture_output}.error.$$
      if command "$openkill_shadow_capture_nft" list chain inet fw4 "$openkill_shadow_capture_chain" > "$openkill_shadow_capture_one" 2> "$openkill_shadow_capture_error"; then
         printf 'OBJECT\tchain\t%s\n' "$openkill_shadow_capture_chain" >> "$openkill_shadow_capture_tmp"
         cat "$openkill_shadow_capture_one" >> "$openkill_shadow_capture_tmp"
         printf 'OBJECT_END\n' >> "$openkill_shadow_capture_tmp"
         [ -z "$openkill_shadow_capture_trace" ] || printf 'chain %s rc=0\n' "$openkill_shadow_capture_chain" >> "$openkill_shadow_capture_trace"
      else
         openkill_shadow_capture_rc=$?
         if [ "$openkill_shadow_capture_rc" -eq 1 ] && openkill_shadow_capture_absence_error "$openkill_shadow_capture_error"; then
            printf 'MISSING\tchain\t%s\n' "$openkill_shadow_capture_chain" >> "$openkill_shadow_capture_tmp"
            [ -z "$openkill_shadow_capture_trace" ] || printf 'chain %s rc=1 missing\n' "$openkill_shadow_capture_chain" >> "$openkill_shadow_capture_trace"
         else
            [ -z "$openkill_shadow_capture_trace" ] || printf 'chain %s rc=%s command-error\n' "$openkill_shadow_capture_chain" "$openkill_shadow_capture_rc" >> "$openkill_shadow_capture_trace"
            rm -f "$openkill_shadow_capture_tmp" "$openkill_shadow_capture_one" "$openkill_shadow_capture_error"
            return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
         fi
      fi
      rm -f "$openkill_shadow_capture_one" "$openkill_shadow_capture_error"
   done
   for openkill_shadow_capture_set in $openkill_shadow_capture_set_list; do
      openkill_shadow_capture_name_ok "$openkill_shadow_capture_set" || { rm -f "$openkill_shadow_capture_tmp"; return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"; }
      openkill_shadow_capture_any=1
      openkill_shadow_capture_one=${openkill_shadow_capture_output}.one.$$
      openkill_shadow_capture_error=${openkill_shadow_capture_output}.error.$$
      if command "$openkill_shadow_capture_nft" list set inet fw4 "$openkill_shadow_capture_set" > "$openkill_shadow_capture_one" 2> "$openkill_shadow_capture_error"; then
         printf 'OBJECT\tset\t%s\n' "$openkill_shadow_capture_set" >> "$openkill_shadow_capture_tmp"
         cat "$openkill_shadow_capture_one" >> "$openkill_shadow_capture_tmp"
         printf 'OBJECT_END\n' >> "$openkill_shadow_capture_tmp"
         [ -z "$openkill_shadow_capture_trace" ] || printf 'set %s rc=0\n' "$openkill_shadow_capture_set" >> "$openkill_shadow_capture_trace"
      else
         openkill_shadow_capture_rc=$?
         if [ "$openkill_shadow_capture_rc" -eq 1 ] && openkill_shadow_capture_absence_error "$openkill_shadow_capture_error"; then
            printf 'MISSING\tset\t%s\n' "$openkill_shadow_capture_set" >> "$openkill_shadow_capture_tmp"
            [ -z "$openkill_shadow_capture_trace" ] || printf 'set %s rc=1 missing\n' "$openkill_shadow_capture_set" >> "$openkill_shadow_capture_trace"
         else
            [ -z "$openkill_shadow_capture_trace" ] || printf 'set %s rc=%s command-error\n' "$openkill_shadow_capture_set" "$openkill_shadow_capture_rc" >> "$openkill_shadow_capture_trace"
            rm -f "$openkill_shadow_capture_tmp" "$openkill_shadow_capture_one" "$openkill_shadow_capture_error"
            return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
         fi
      fi
      rm -f "$openkill_shadow_capture_one" "$openkill_shadow_capture_error"
   done
   [ "$openkill_shadow_capture_any" -eq 1 ] || { rm -f "$openkill_shadow_capture_tmp"; return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"; }
   mv -f "$openkill_shadow_capture_tmp" "$openkill_shadow_capture_output" || { rm -f "$openkill_shadow_capture_tmp"; return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"; }
   return 0
}

openkill_shadow_parse_nft_capture()
{
   openkill_shadow_capture_input=$1
   openkill_shadow_intent_output=$2
   openkill_shadow_payload_output=$3
   [ -r "$openkill_shadow_capture_input" ] && [ -n "$openkill_shadow_intent_output" ] && [ -n "$openkill_shadow_payload_output" ] || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   openkill_shadow_safe_path "$openkill_shadow_capture_input" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   openkill_shadow_safe_path "$openkill_shadow_intent_output" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   openkill_shadow_safe_path "$openkill_shadow_payload_output" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   openkill_shadow_parse_tmp=${openkill_shadow_intent_output}.parse.$$
   openkill_shadow_safe_path "$openkill_shadow_parse_tmp" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   # This is intentionally a finite parser for the nft list forms emitted by
   # the current OpenKill inventory.  It does not claim to parse arbitrary nft
   # grammar.  Owned-chain expressions outside the known action vocabulary are
   # surfaced as CAPTURE_UNSUPPORTED instead of being dropped.  The three
   # device forms accepted here are deliberately narrow: fw4's symbolic
   # `filter -1` priority for nat_output, the current IPv4 WAN multiport
   # reject, and its IPv6 icmpv6 port-unreachable counterpart.
   awk -v OFS='\t' '
      function trim(s) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", s); return s }
      # This is only the finite syntax vocabulary needed to reject malformed
      # legacy captures.  It is deliberately not an ownership decision; the
      # typed comparator joins rows to formal inventory metadata later.
      function capture_syntax_scope(n) { return n == "nat_output" || n ~ /^openkill/ }
      function base(n) { return n == "dstnat" || n == "mangle_prerouting" || n == "mangle_output" || n == "output" || n == "srcnat" || n == "input" || n == "forward" }
      function valid_port_list(v, n, i, p) {
         v=trim(v)
         # A service multiport is a mathematical set.  Keep the accepted
         # grammar finite so malformed commas and non-port expressions fail
         # closed instead of being mistaken for a generic reject rule.
         if (v !~ /^[0-9]+([[:space:]]*,[[:space:]]*[0-9]+)*$/) return 0
         n=split(v, p, /[[:space:]]*,[[:space:]]*/)
         for (i=1; i<=n; i++) if (p[i] !~ /^[0-9]+$/ || (p[i]+0) < 1 || (p[i]+0) > 65535) return 0
         return n > 0
      }
      function valid_multiport(s, expr, body) {
         if (!match(s, /(^|[[:space:]])(th|tcp|udp)[[:space:]]+dport[[:space:]]*\{[^{}]*\}/)) return 0
         expr=substr(s, RSTART, RLENGTH)
         body=expr
         sub(/^.*\{/, "", body)
         sub(/\}.*$/, "", body)
         return valid_port_list(body)
      }
      function canonicalize_multiport(s, expr, body, prefix, n, i, j, v, t, joined) {
         # Canonicalize only a validated numeric dport set.  Other finite nft
         # forms (named sets, ranges, concatenations) remain untouched and are
         # judged by known_rule as before.
         if (match(s, /(^|[[:space:]])(th|tcp|udp)[[:space:]]+dport[[:space:]]*\{[^{}]*\}/)) {
            expr=substr(s, RSTART, RLENGTH)
            body=expr
            sub(/^.*\{/, "", body)
            sub(/\}.*$/, "", body)
            if (!valid_port_list(body)) return s
            n=split(trim(body), p, /[[:space:]]*,[[:space:]]*/)
            for (i=1; i<=n; i++) {
               v=p[i]+0
               j=i
               while (j > 1 && (p[j-1]+0) > v) { p[j]=p[j-1]; j-- }
               p[j]=v
            }
            # Deduplicate after numeric insertion sort.
            joined=""
            last=""
            for (i=1; i<=n; i++) if (p[i] != last) { if (joined != "") joined=joined ", "; joined=joined p[i]; last=p[i] }
            prefix=expr
            sub(/[[:space:]]*\{[^{}]*\}$/, "", prefix)
            s=substr(s, 1, RSTART-1) prefix " { " joined " }" substr(s, RSTART+RLENGTH)
         }
         return s
      }
      function valid_ipv6_proto_set(s) {
         return s ~ /(^|[[:space:]])ip6[[:space:]]+nexthdr[[:space:]]*\{[[:space:]]*(tcp[[:space:]]*,[[:space:]]*udp|udp[[:space:]]*,[[:space:]]*tcp)[[:space:]]*\}/
      }
      function known_reject(s, chain) {
         if (!valid_multiport(s)) return 0
         if (chain == "openkill_wan_input") {
            # The frozen v4 inventory has no IPv6 qualifier.  Rejecting an
            # ip6/meta-ipv6 expression here prevents a family collapse from
            # being accepted simply because the terminal verdict is `reject`.
            if (s ~ /(^|[[:space:]])ip6([[:space:]]|$)/ ||
                s ~ /(^|[[:space:]])meta[[:space:]]+nfproto[[:space:]]+ipv6([[:space:]]|$)/ ||
                s ~ /(^|[[:space:]])meta[[:space:]]+l4proto[[:space:]]+sctp([[:space:]]|$)/) return 0
            return s ~ /(^|[[:space:]])reject[[:space:]]*$/ && s !~ /reject[[:space:]]+with/
         }
         if (chain == "openkill_wan6_input")
            return valid_ipv6_proto_set(s) && s ~ /(^|[[:space:]])reject[[:space:]]+with[[:space:]]+icmpv6[[:space:]]+port-unreachable[[:space:]]*$/
         return 0
      }
      function known_rule(s, chain) {
         # Reject forms must be decided before the older counter vocabulary;
         # this prevents an unsupported reject subtype or malformed multiport
         # from being accepted merely because it contains a counter/match.
         if (s ~ /(^|[[:space:]])reject([[:space:]]|$)/) return known_reject(s, chain)
         return s ~ /(^|[[:space:]])return([[:space:]]|$)/ ||
                s ~ /(^|[[:space:]])jump[[:space:]]+openkill[_A-Za-z0-9]*([[:space:]]|$)/ ||
                s ~ /meta[[:space:]]+mark[[:space:]]+set[[:space:]]+0x[0-9A-Fa-f]+/ ||
                s ~ /(^|[[:space:]])tproxy([[:space:]]|$)/ ||
                s ~ /(^|[[:space:]])redirect([[:space:]]|$)/ ||
                s ~ /(^|[[:space:]])accept([[:space:]]|$)/ ||
                (s ~ /(^|[[:space:]])counter([[:space:]]|$)/ &&
                 s ~ /(meta[[:space:]]|ip[46]?[[:space:]]|tcp[[:space:]]|udp[[:space:]]|ether[[:space:]]|iifname[[:space:]]|oifname[[:space:]])/)
      }
      function valid_hook_declaration(s, chain, p) {
         s=trim(s)
         hook_priority=""
         # `filter - 1`, `filter -1`, `filter-1`, and numeric `-1` are the
         # only accepted spellings of the current output hook.  Policy is
         # validated when present; accept is the nft default and remains
         # represented by the existing V1 HOOK record.
         if (chain != "nat_output") return 0
         if (s ~ /^type[[:space:]]+nat[[:space:]]+hook[[:space:]]+output[[:space:]]+priority[[:space:]]+(filter[[:space:]]*-[[:space:]]*1|-[[:space:]]*1)[[:space:]]*;([[:space:]]*policy[[:space:]]+accept[[:space:]]*;?)?[[:space:]]*$/) {
            hook_priority="-1"
            return 1
         }
         return 0
      }
      function clean_rule(s) {
         s=trim(s)
         sub(/[[:space:]]+#?[[:space:]]*handle[[:space:]]+[0-9]+[[:space:]]*$/, "", s)
         sub(/[[:space:]]+counter[[:space:]]+packets[[:space:]]+[0-9]+[[:space:]]+bytes[[:space:]]+[0-9]+/, "", s)
         sub(/[[:space:]]+comment[[:space:]]+"[^"]*"/, "", s)
         s=canonicalize_multiport(s)
         return trim(s)
      }
      function finish_set(  body,name,type,flags,elems,x,n,i,v) {
         body=set_body
         name=set_name
         type=""; flags=""; elems=""
         if (match(body, /type[[:space:]]+[^[:space:];}]+/)) { type=substr(body, RSTART, RLENGTH); sub(/^type[[:space:]]+/, "", type) }
         if (match(body, /flags[[:space:]]+[^;}]*/)) { flags=substr(body, RSTART, RLENGTH); sub(/^flags[[:space:]]+/, "", flags); gsub(/[[:space:]]+/, ",", flags) }
         if (flags ~ /interval/) flags="interval"
         if (match(body, /elements[[:space:]]*=[[:space:]]*\{[^}]*\}/)) {
            elems=substr(body, RSTART, RLENGTH); sub(/^.*\{/, "", elems); sub(/\}.*$/, "", elems); gsub(/[[:space:]]+/, " ", elems); gsub(/^ +| +$/, "", elems); gsub(/[[:space:]]*,[[:space:]]*/, ",", elems)
         }
         print "SET", name, type, (flags == "" ? "-" : flags), (elems == "" ? "-" : elems)
         set_body=""; set_name=""; mode=""
      }
      BEGIN { print "LEGACY_RUNTIME_INTENT_V1=1"; mode=""; order=0; unknown=0 }
      /^LEGACY_RUNTIME_CAPTURE_V1=/ { next }
      /^MISSING\t/ { print; next }
      /^OBJECT\tchain\t/ { mode="chain"; chain=$3; sub(/\r$/, "", chain); order=0; print "CHAIN", chain; next }
      /^OBJECT\tset\t/ { mode="set"; set_name=$3; sub(/\r$/, "", set_name); set_body=""; next }
      /^OBJECT_END\r?$/ { if (mode == "set") finish_set(); mode=""; chain=""; next }
      {
         line=trim($0)
         sub(/\r$/, "", line)
         if (mode == "set") {
            if (line != "" && line !~ /^table[[:space:]]/ && line !~ /^set[[:space:]]/) set_body=set_body " " line
            next
         }
         if (mode != "chain" || line == "" || line ~ /^table[[:space:]]/ || line == "}") next
         if (line ~ /^chain[[:space:]]/) {
            # Preserve the one currently-owned hooked chain declaration.  FW4
            # base-chain declarations are never captured as owned objects.
            if (capture_syntax_scope(chain)) {
               openkill_declaration=line
               sub(/^.*\{[[:space:]]*/, "", openkill_declaration)
               sub(/[[:space:]]*\}[[:space:]]*$/, "", openkill_declaration)
               if (openkill_declaration ~ /^type[[:space:]]+nat[[:space:]]+hook/) {
                  if (valid_hook_declaration(openkill_declaration, chain)) {
                     print "HOOK", chain, "nat", "output", hook_priority
                  } else {
                     print "UNKNOWN_OWNED_RULE", chain, openkill_declaration
                     unknown=1
                  }
               }
            }
            next
         }
         if (capture_syntax_scope(chain) && line ~ /^type[[:space:]]+nat[[:space:]]+hook/) {
            if (valid_hook_declaration(line, chain)) {
               print "HOOK", chain, "nat", "output", hook_priority
            } else {
               print "UNKNOWN_OWNED_RULE", chain, line
               unknown=1
            }
            next
         }
         line=clean_rule(line)
         if (line == "") next
         if (base(chain) && line !~ /(^|[[:space:]])jump[[:space:]]+openkill[_A-Za-z0-9]*/) next
         if (capture_syntax_scope(chain) && !known_rule(line, chain)) { print "UNKNOWN_OWNED_RULE", chain, line; unknown=1; next }
         order++
         print "RULE", chain, order, line
         if (base(chain) && line ~ /(^|[[:space:]])jump[[:space:]]+openkill[_A-Za-z0-9]*/) print "ATTACH", chain, order, line
      }
      END { if (mode == "set") finish_set(); if (unknown) exit 20 }
   ' "$openkill_shadow_capture_input" > "$openkill_shadow_parse_tmp"
   openkill_shadow_parse_rc=$?
   if [ "$openkill_shadow_parse_rc" -eq 20 ]; then
      mv -f "$openkill_shadow_parse_tmp" "$openkill_shadow_intent_output" 2>/dev/null || rm -f "$openkill_shadow_parse_tmp"
      return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_UNSUPPORTED"
   fi
   [ "$openkill_shadow_parse_rc" -eq 0 ] || { rm -f "$openkill_shadow_parse_tmp"; return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"; }
   mv -f "$openkill_shadow_parse_tmp" "$openkill_shadow_intent_output" || { rm -f "$openkill_shadow_parse_tmp"; return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"; }
   : > "$openkill_shadow_payload_output" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   printf '# LEGACY_RUNTIME_INTENT_V1=%s\n' "$OPENKILL_NFT_SHADOW_LEGACY_INTENT_VERSION" >> "$openkill_shadow_payload_output"
   while IFS='	' read -r openkill_shadow_intent_kind openkill_shadow_intent_a openkill_shadow_intent_b openkill_shadow_intent_c openkill_shadow_intent_d; do
      case "$openkill_shadow_intent_kind" in
         CHAIN)
            # nat_output is emitted by the HOOK record below with its exact
            # current hook declaration; avoid a duplicate unhooked declaration.
            [ "$openkill_shadow_intent_a" = nat_output ] || printf 'add chain inet fw4 %s { }\n' "$openkill_shadow_intent_a" >> "$openkill_shadow_payload_output"
            ;;
         HOOK) printf 'add chain inet fw4 %s { type %s hook %s priority %s; }\n' "$openkill_shadow_intent_a" "$openkill_shadow_intent_b" "$openkill_shadow_intent_c" "$openkill_shadow_intent_d" >> "$openkill_shadow_payload_output" ;;
         SET)
            openkill_shadow_set_elements=$(openkill_shadow_auto_list "$openkill_shadow_intent_d" 2>/dev/null) || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
            if [ "$openkill_shadow_set_elements" = - ]; then
               printf 'add set inet fw4 %s { type %s; }\n' "$openkill_shadow_intent_a" "$openkill_shadow_intent_b" >> "$openkill_shadow_payload_output"
            else
               openkill_shadow_set_elements_spaced=$(printf '%s' "$openkill_shadow_set_elements" | sed 's/,/, /g')
               if [ "$openkill_shadow_intent_c" = - ]; then
                  printf 'add set inet fw4 %s { type %s; elements = { %s }; }\n' "$openkill_shadow_intent_a" "$openkill_shadow_intent_b" "$openkill_shadow_set_elements_spaced" >> "$openkill_shadow_payload_output"
               else
                  printf 'add set inet fw4 %s { type %s; flags %s; elements = { %s }; }\n' "$openkill_shadow_intent_a" "$openkill_shadow_intent_b" "$openkill_shadow_intent_c" "$openkill_shadow_set_elements_spaced" >> "$openkill_shadow_payload_output"
               fi
            fi
            ;;
         RULE) printf 'add rule inet fw4 %s %s\n' "$openkill_shadow_intent_a" "$openkill_shadow_intent_c" >> "$openkill_shadow_payload_output" ;;
      esac
   done < "$openkill_shadow_intent_output"
   return 0
}

# The renderer templates are the authoritative CURRENT inventory schema.  A
# capture can therefore report a missing object without making the coordinator
# guess from a device-specific name list.  The chain required bit is the
# seventh template field; the required set IDs below are the stable core rows
# in that same schema.  Rows present only in another mode are INACTIVE_MODE.
openkill_shadow_inventory_template()
{
   openkill_shadow_inventory_template_mode=$1
   openkill_shadow_inventory_template_dir=${OPENKILL_NFT_SHADOW_TEMPLATE_DIR:-/usr/share/openkill/shadow}
   openkill_shadow_safe_path "$openkill_shadow_inventory_template_dir" || return 1
   case "$openkill_shadow_inventory_template_mode" in
      TUN) openkill_shadow_inventory_template_name=input_tun_v1.tsv ;;
      TPROXY) openkill_shadow_inventory_template_name=input_tproxy_v1.tsv ;;
      REDIRECT) openkill_shadow_inventory_template_name=input_redirect_v1.tsv ;;
      *) return 1 ;;
   esac
   openkill_shadow_inventory_template_path_value=$openkill_shadow_inventory_template_dir/$openkill_shadow_inventory_template_name
   openkill_shadow_safe_path "$openkill_shadow_inventory_template_path_value" || return 1
   [ -r "$openkill_shadow_inventory_template_path_value" ] || return 1
   printf '%s\n' "$openkill_shadow_inventory_template_path_value"
}

openkill_shadow_inventory_class()
{
   openkill_shadow_inventory_kind=$1
   openkill_shadow_inventory_name=$2
   openkill_shadow_inventory_mode=$3
   case "$openkill_shadow_inventory_kind" in
      chain) openkill_shadow_inventory_template_kind=CHAIN ;;
      set) openkill_shadow_inventory_template_kind=SET ;;
      *) printf '%s\n' UNKNOWN; return 0 ;;
   esac
   openkill_shadow_capture_name_ok "$openkill_shadow_inventory_name" || { printf '%s\n' UNKNOWN; return 0; }

   # These are the existing fw4 base-chain rows described by the capture
   # contract.  They are outside the renderer templates but remain required
   # attachment points for a complete bounded read.
   if [ "$openkill_shadow_inventory_kind" = chain ]; then
      for openkill_shadow_inventory_base in $OPENKILL_NFT_SHADOW_REQUIRED_BASE_CHAINS; do
         [ "$openkill_shadow_inventory_name" = "$openkill_shadow_inventory_base" ] || continue
         printf '%s\n' REQUIRED_CURRENT
         return 0
      done
   fi

   openkill_shadow_inventory_active_template=$(openkill_shadow_inventory_template "$openkill_shadow_inventory_mode" 2>/dev/null) || {
      printf '%s\n' UNKNOWN
      return 0
   }
   openkill_shadow_inventory_row=$(awk -F '\t' -v kind="$openkill_shadow_inventory_template_kind" -v name="$openkill_shadow_inventory_name" '$1 == kind && $3 == name { print; exit }' "$openkill_shadow_inventory_active_template")
   if [ -n "$openkill_shadow_inventory_row" ]; then
      openkill_shadow_inventory_id=$(printf '%s\n' "$openkill_shadow_inventory_row" | awk -F '\t' '{ print $2 }')
      openkill_shadow_inventory_category=$(printf '%s\n' "$openkill_shadow_inventory_row" | awk -F '\t' '{ print $5 }')
      openkill_shadow_inventory_required=$(printf '%s\n' "$openkill_shadow_inventory_row" | awk -F '\t' '{ print $7 }')
      openkill_shadow_inventory_mode_specific=1
      for openkill_shadow_inventory_other_mode in TUN TPROXY REDIRECT; do
         [ "$openkill_shadow_inventory_other_mode" = "$openkill_shadow_inventory_mode" ] && continue
         openkill_shadow_inventory_other_template=$(openkill_shadow_inventory_template "$openkill_shadow_inventory_other_mode" 2>/dev/null) || continue
         openkill_shadow_inventory_other_row=$(awk -F '\t' -v kind="$openkill_shadow_inventory_template_kind" -v name="$openkill_shadow_inventory_name" '$1 == kind && $3 == name { print; exit }' "$openkill_shadow_inventory_other_template")
         [ -n "$openkill_shadow_inventory_other_row" ] || continue
         openkill_shadow_inventory_mode_specific=0
         break
      done
      if [ "$openkill_shadow_inventory_kind" = chain ]; then
         if [ "$openkill_shadow_inventory_category" = UPNP ]; then
            printf '%s\n' OPTIONAL_OBSERVATION
         elif [ "$openkill_shadow_inventory_required" = 1 ] || [ "$openkill_shadow_inventory_mode_specific" -eq 1 ]; then
            printf '%s\n' REQUIRED_CURRENT
         else
            printf '%s\n' CONDITIONAL_CURRENT
         fi
         return 0
      fi
      for openkill_shadow_inventory_required_id in $OPENKILL_NFT_SHADOW_REQUIRED_SET_IDS; do
         [ "$openkill_shadow_inventory_id" = "$openkill_shadow_inventory_required_id" ] || continue
         printf '%s\n' REQUIRED_CURRENT
         return 0
      done
      for openkill_shadow_inventory_out_of_scope_id in $OPENKILL_NFT_SHADOW_OUT_OF_SCOPE_SET_IDS; do
         [ "$openkill_shadow_inventory_id" = "$openkill_shadow_inventory_out_of_scope_id" ] || continue
         printf '%s\n' OUT_OF_SCOPE
         return 0
      done
      printf '%s\n' CONDITIONAL_CURRENT
      return 0
   fi

   # A valid row in another mode is a known inactive-mode object, not an
   # unknown object and not a required absence for the current mode.
   for openkill_shadow_inventory_other_mode in TUN TPROXY REDIRECT; do
      [ "$openkill_shadow_inventory_other_mode" = "$openkill_shadow_inventory_mode" ] && continue
      openkill_shadow_inventory_other_template=$(openkill_shadow_inventory_template "$openkill_shadow_inventory_other_mode" 2>/dev/null) || continue
      openkill_shadow_inventory_other_row=$(awk -F '\t' -v kind="$openkill_shadow_inventory_template_kind" -v name="$openkill_shadow_inventory_name" '$1 == kind && $3 == name { print; exit }' "$openkill_shadow_inventory_other_template")
      [ -n "$openkill_shadow_inventory_other_row" ] || continue
      printf '%s\n' INACTIVE_MODE
      return 0
   done
   printf '%s\n' UNKNOWN
   return 0
}

openkill_shadow_classify_inventory_missing()
{
   openkill_shadow_inventory_intent_file=$1
   openkill_shadow_inventory_input_file=$2
   openkill_shadow_required_missing_count=0
   openkill_shadow_conditional_missing_count=0
   openkill_shadow_inactive_missing_count=0
   openkill_shadow_optional_missing_count=0
   openkill_shadow_out_of_scope_missing_count=0
   openkill_shadow_unknown_count=0
   openkill_shadow_inventory_missing_count=0
   openkill_shadow_inventory_missing_summary=
   openkill_shadow_inventory_error_reason=
   [ -r "$openkill_shadow_inventory_intent_file" ] && [ -r "$openkill_shadow_inventory_input_file" ] || {
      openkill_shadow_inventory_error_reason=inventory-input-unavailable
      return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   }
   openkill_shadow_safe_path "$openkill_shadow_inventory_intent_file" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   openkill_shadow_safe_path "$openkill_shadow_inventory_input_file" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   openkill_shadow_inventory_mode_raw=$(awk -F '\t' '$1 == "META" && $2 == "run_mode" { print $3; exit }' "$openkill_shadow_inventory_input_file") || openkill_shadow_inventory_mode_raw=
   openkill_shadow_inventory_mode=$(openkill_shadow_normalize_run_mode "$openkill_shadow_inventory_mode_raw" 2>/dev/null) || {
      openkill_shadow_inventory_error_reason=inventory-mode-unknown
      return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   }
   openkill_shadow_inventory_seen=${openkill_shadow_inventory_intent_file}.seen.$$
   openkill_shadow_safe_path "$openkill_shadow_inventory_seen" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   : > "$openkill_shadow_inventory_seen" || return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   while IFS='	' read -r openkill_shadow_inventory_marker openkill_shadow_inventory_kind openkill_shadow_inventory_name openkill_shadow_inventory_extra; do
      [ "$openkill_shadow_inventory_marker" = MISSING ] || continue
      openkill_shadow_inventory_missing_count=$((openkill_shadow_inventory_missing_count + 1))
      if [ -n "$openkill_shadow_inventory_extra" ] || [ -z "$openkill_shadow_inventory_kind" ] || [ -z "$openkill_shadow_inventory_name" ] ||
         ! openkill_shadow_capture_name_ok "$openkill_shadow_inventory_name"; then
         openkill_shadow_unknown_count=$((openkill_shadow_unknown_count + 1))
         openkill_shadow_inventory_error_reason=inventory-record-invalid
         continue
      fi
      case "$openkill_shadow_inventory_kind" in chain|set) ;; *)
         openkill_shadow_unknown_count=$((openkill_shadow_unknown_count + 1))
         openkill_shadow_inventory_error_reason=inventory-kind-unknown
         continue
      esac
      openkill_shadow_inventory_key=$openkill_shadow_inventory_kind:$openkill_shadow_inventory_name
      if grep -Fqx "$openkill_shadow_inventory_key" "$openkill_shadow_inventory_seen"; then
         openkill_shadow_unknown_count=$((openkill_shadow_unknown_count + 1))
         openkill_shadow_inventory_error_reason=inventory-duplicate-entry
         continue
      fi
      printf '%s\n' "$openkill_shadow_inventory_key" >> "$openkill_shadow_inventory_seen" || {
         rm -f "$openkill_shadow_inventory_seen"
         openkill_shadow_inventory_error_reason=inventory-seen-write-failed
         return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
      }
      openkill_shadow_inventory_class_value=$(openkill_shadow_inventory_class "$openkill_shadow_inventory_kind" "$openkill_shadow_inventory_name" "$openkill_shadow_inventory_mode") || openkill_shadow_inventory_class_value=UNKNOWN
      case "$openkill_shadow_inventory_class_value" in
         REQUIRED_CURRENT) openkill_shadow_required_missing_count=$((openkill_shadow_required_missing_count + 1)) ;;
         CONDITIONAL_CURRENT) openkill_shadow_conditional_missing_count=$((openkill_shadow_conditional_missing_count + 1)) ;;
         INACTIVE_MODE) openkill_shadow_inactive_missing_count=$((openkill_shadow_inactive_missing_count + 1)) ;;
         OPTIONAL_OBSERVATION) openkill_shadow_optional_missing_count=$((openkill_shadow_optional_missing_count + 1)) ;;
         OUT_OF_SCOPE) openkill_shadow_out_of_scope_missing_count=$((openkill_shadow_out_of_scope_missing_count + 1)) ;;
         *) openkill_shadow_unknown_count=$((openkill_shadow_unknown_count + 1)); openkill_shadow_inventory_error_reason=inventory-object-unknown ;;
      esac
   done < "$openkill_shadow_inventory_intent_file"
   rm -f "$openkill_shadow_inventory_seen"
   openkill_shadow_inventory_missing_summary="required=$openkill_shadow_required_missing_count conditional=$openkill_shadow_conditional_missing_count inactive=$openkill_shadow_inactive_missing_count optional=$openkill_shadow_optional_missing_count out_of_scope=$openkill_shadow_out_of_scope_missing_count unknown=$openkill_shadow_unknown_count"
   if [ "$openkill_shadow_required_missing_count" -gt 0 ]; then
      openkill_shadow_inventory_error_reason=required-current-missing
      return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   fi
   if [ "$openkill_shadow_unknown_count" -gt 0 ]; then
      [ -n "$openkill_shadow_inventory_error_reason" ] || openkill_shadow_inventory_error_reason=inventory-object-unknown
      return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
   fi
   return 0
}

openkill_shadow_capture_legacy_intent()
{
   openkill_shadow_capture_legacy_nft "$1"
}

openkill_shadow_auto_prepare()
{
   openkill_shadow_auto_prepare_dir=$1
   [ -n "$openkill_shadow_auto_prepare_dir" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_safe_path "$openkill_shadow_auto_prepare_dir" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_auto_generation_source_file=
   openkill_shadow_auto_continuity_mode=0
   openkill_shadow_auto_generation_fixture=0
   openkill_shadow_auto_source_file=
   openkill_shadow_auto_source_requested=${OPENKILL_NFT_SHADOW_SOURCE_FILE:-${OPENKILL_NFT_SHADOW_AUTO_STATE_FILE:-${OPENKILL_NFT_SHADOW_STATE_SOURCE:-}}}
   if [ -n "$openkill_shadow_auto_source_requested" ]; then
      openkill_shadow_auto_source_file=$(openkill_shadow_auto_source_path) || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      openkill_shadow_auto_generation_fixture=1
   else
      # Production automatic mode snapshots the live committed sources before
      # building input.  This is the only path that may create a continuity
      # token; no generation file is read or written here.
      openkill_shadow_auto_continuity_snapshot "$openkill_shadow_auto_prepare_dir"
      openkill_shadow_auto_snapshot_rc=$?
      [ "$openkill_shadow_auto_snapshot_rc" -eq 0 ] || return "$openkill_shadow_auto_snapshot_rc"
      openkill_shadow_auto_continuity_mode=1
   fi
   openkill_shadow_input_file=$openkill_shadow_auto_prepare_dir/auto-input.tsv
   openkill_shadow_safe_path "$openkill_shadow_input_file" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_build_auto_input "$openkill_shadow_input_file"
   openkill_shadow_auto_prepare_rc=$?
   [ "$openkill_shadow_auto_prepare_rc" -eq 0 ] || return "$openkill_shadow_auto_prepare_rc"
   if [ "$openkill_shadow_auto_generation_fixture" -eq 1 ] && [ -z "$openkill_shadow_auto_generation" ]; then
      openkill_shadow_auto_field GENERATION >/dev/null 2>&1
      openkill_shadow_auto_generation_rc=$?
      [ "$openkill_shadow_auto_generation_rc" -eq 0 ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      openkill_shadow_auto_generation=$openkill_shadow_auto_field_value
   fi
   if [ "$openkill_shadow_auto_generation_fixture" -eq 1 ] && [ -n "$openkill_shadow_auto_generation" ]; then
      openkill_shadow_generation=$openkill_shadow_auto_generation
      openkill_shadow_generation_file=$openkill_shadow_auto_prepare_dir/auto-generation
      # Keep the canonical source visible for the end-of-run race check.  The
      # temporary copy is still used for the first read so the comparison has
      # a stable G1 snapshot; the source is read again before publishing.
      openkill_shadow_auto_generation_source_file=${openkill_shadow_auto_source_file:-}
      printf '%s\n' "$openkill_shadow_generation" > "$openkill_shadow_generation_file" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   elif [ "$openkill_shadow_auto_continuity_mode" -eq 1 ]; then
      openkill_shadow_generation=$openkill_shadow_continuity_token_value
      openkill_shadow_safe_value "$openkill_shadow_generation" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      openkill_shadow_generation_file=
   fi
   return 0
}

openkill_shadow_hash_file()
{
   openkill_shadow_hash_input=$1
   [ -r "$openkill_shadow_hash_input" ] || return 1
   if command -v sha256sum >/dev/null 2>&1; then
      sha256sum "$openkill_shadow_hash_input" | awk 'NR == 1 { print $1; exit }'
      return 0
   fi
   return 1
}

openkill_shadow_normalize_payload()
{
   openkill_shadow_payload_input=$1
   openkill_shadow_payload_output=$2
   [ -r "$openkill_shadow_payload_input" ] || return 1
   # Comments carry traceability only.  Declarations are order-independent in
   # nft, while rule/attachment order is packet-semantic.  Canonicalize the
   # former by name and retain the latter's relative order so an imperative
   # legacy capture compares equal to a declarative renderer without masking a
   # precedence change.
   awk '
      /^#/ { next }
      {
         line=$0
         sub(/[[:space:]]+comment[[:space:]]+".*"[[:space:]]*$/, "", line)
         sub(/[[:space:]]+counter[[:space:]]+packets[[:space:]]+[0-9]+[[:space:]]+bytes[[:space:]]+[0-9]+/, "", line)
         gsub(/(^|[[:space:]])counter([[:space:]]|$)/, " ", line)
         gsub(/[[:space:]]+/, " ", line)
         sub(/^ /, "", line)
         sub(/ $/, "", line)
         if (line == "") next
         if (line ~ /^add chain /) { print "00\t" line; next }
         if (line ~ /^add set /) { print "01\t" line; next }
         # Rules in different chains have no shared packet order.  Group by
         # their logical chain, then preserve the recorded order inside each
         # chain; this models the final state of imperative add/insert output
         # while remaining independent of object serialization order.
         chain=$5
         chain_order[chain]++
         printf "02\t%s\t%010d\t%s\n", chain, chain_order[chain], line
      }
   ' "$openkill_shadow_payload_input" |
      LC_ALL=C sort |
      awk -F '\t' '{ if ($1 == "00" || $1 == "01") print $2; else print $4 }' > "$openkill_shadow_payload_output"
}

openkill_shadow_valid_hash()
{
   case "$1" in
      ''|*[!0-9A-Fa-f]*) return 1 ;;
   esac
   [ "${#1}" -eq 64 ]
}

openkill_shadow_source_drift_ok()
{
   # A migration-time baseline may be supplied as exact files or as hashes.
   # If no baseline is installed, the observer has no claim about drift; an
   # explicit but mismatching baseline always fails closed.
   if [ -n "${openkill_shadow_source_hash_file:-}" ] || [ -n "${openkill_shadow_baseline_hash_file:-}" ]; then
      [ -r "${openkill_shadow_source_hash_file:-}" ] && [ -r "${openkill_shadow_baseline_hash_file:-}" ] || return 1
      cmp -s "$openkill_shadow_source_hash_file" "$openkill_shadow_baseline_hash_file"
      return $?
   fi
   if [ -n "${openkill_shadow_source_hash:-}" ] || [ -n "${openkill_shadow_baseline_hash:-}" ]; then
      openkill_shadow_valid_hash "$openkill_shadow_source_hash" || return 1
      openkill_shadow_valid_hash "$openkill_shadow_baseline_hash" || return 1
      [ "$openkill_shadow_source_hash" = "$openkill_shadow_baseline_hash" ]
      return $?
   fi
   return 0
}

openkill_shadow_short_hash()
{
   case "$1" in
      '') printf '%s' '-' ;;
      *) printf '%.12s' "$1" ;;
   esac
}

openkill_shadow_generation_telemetry_value()
{
   # Preserve the original explicit-bundle wire value.  Only the automatic
   # path uses the short content-derived token in the legacy generation field;
   # the additive continuity_token field makes that interpretation explicit.
   if [ -n "${openkill_shadow_continuity_token_value:-}" ]; then
      openkill_shadow_short_hash "$1"
   else
      printf '%s' "$1"
   fi
}

openkill_shadow_publish()
{
   openkill_shadow_status_value=$1
   openkill_shadow_old_value=${2:--}
   openkill_shadow_new_value=${3:--}
   openkill_shadow_generation_value=${4:--}
   openkill_shadow_reason_value=${5:--}
   openkill_shadow_mismatch_value=${6:-0}
   openkill_shadow_dir=${OPENKILL_NFT_SHADOW_TELEMETRY_DIR:-$OPENKILL_NFT_SHADOW_TELEMETRY_DEFAULT}
   [ -n "$openkill_shadow_dir" ] || return 1
   ( umask 077; mkdir -p "$openkill_shadow_dir" ) 2>/dev/null || return 1
   chmod 700 "$openkill_shadow_dir" 2>/dev/null || return 1
   openkill_shadow_tmp=$(mktemp "$openkill_shadow_dir/.status.XXXXXX" 2>/dev/null) || return 1
   (
      umask 077
      printf 'OPENKILL_NFT_SHADOW_TELEMETRY_V1=1\n'
      printf 'protocol_version=%s\n' "$OPENKILL_NFT_SHADOW_PROTOCOL_VERSION"
      printf 'compare_schema_version=%s\n' "$OPENKILL_NFT_SHADOW_COMPARE_SCHEMA_VERSION"
      printf 'profile=current\n'
      printf 'renderer_version=%s\n' "$OPENKILL_NFT_SHADOW_RENDERER_VERSION"
      printf 'status=%s\n' "$openkill_shadow_status_value"
      printf 'old_hash=%s\n' "$(openkill_shadow_short_hash "$openkill_shadow_old_value")"
      printf 'new_hash=%s\n' "$(openkill_shadow_short_hash "$openkill_shadow_new_value")"
      printf 'generation=%s\n' "$(openkill_shadow_generation_telemetry_value "$openkill_shadow_generation_value")"
      # `generation=` remains for wire compatibility with the 3E protocol.
      # In automatic mode it carries the short continuity token; the explicit
      # field below makes that meaning unambiguous for new consumers.
      if [ -n "${openkill_shadow_continuity_token_value:-}" ]; then
         printf 'continuity_token=%s\n' "$(openkill_shadow_short_hash "$openkill_shadow_continuity_token_value")"
      fi
      printf 'reason=%s\n' "$openkill_shadow_reason_value"
      printf 'mismatch_count=%s\n' "$openkill_shadow_mismatch_value"
      # Additive inventory diagnostics.  These are counts only; no object
      # names or captured payload enter telemetry.
      printf 'inventory_schema_version=%s\n' "$OPENKILL_NFT_SHADOW_INVENTORY_SCHEMA_VERSION"
      printf 'inventory_missing_count=%s\n' "${openkill_shadow_inventory_missing_count:-0}"
      printf 'inventory_missing_summary=%s\n' "${openkill_shadow_inventory_missing_summary:-required=0 conditional=0 inactive=0 optional=0 out_of_scope=0 unknown=0}"
      printf 'required_missing_count=%s\n' "${openkill_shadow_required_missing_count:-0}"
      printf 'conditional_missing_count=%s\n' "${openkill_shadow_conditional_missing_count:-0}"
      printf 'inactive_missing_count=%s\n' "${openkill_shadow_inactive_missing_count:-0}"
      printf 'optional_missing_count=%s\n' "${openkill_shadow_optional_missing_count:-0}"
      printf 'out_of_scope_missing_count=%s\n' "${openkill_shadow_out_of_scope_missing_count:-0}"
      printf 'unknown_missing_count=%s\n' "${openkill_shadow_unknown_count:-0}"
      # Typed semantic fields are additive telemetry.  Hashes are shortened
      # and counts are bounded; no object names, addresses, endpoints, or
      # captured rule text enter this file.
      printf 'comparison_model_version=%s\n' "$OPENKILL_NFT_SHADOW_SEMANTIC_MODEL_VERSION"
      printf 'ownership_model_version=%s\n' "$OPENKILL_NFT_SHADOW_OWNERSHIP_MODEL_VERSION"
      printf 'dns_model_version=%s\n' "$OPENKILL_NFT_SHADOW_DNS_MODEL_VERSION"
      printf 'actual_owned_hash=%s\n' "$(openkill_shadow_short_hash "${openkill_shadow_typed_actual_owned_hash:-}")"
      printf 'desired_owned_hash=%s\n' "$(openkill_shadow_short_hash "${openkill_shadow_typed_desired_owned_hash:-}")"
      printf 'actual_full_observation_hash=%s\n' "$(openkill_shadow_short_hash "${openkill_shadow_typed_actual_full_hash:-}")"
      printf 'desired_full_observation_hash=%s\n' "$(openkill_shadow_short_hash "${openkill_shadow_typed_desired_full_hash:-}")"
      printf 'dns_actual_hash=%s\n' "$(openkill_shadow_short_hash "${openkill_shadow_typed_dns_actual_hash:-}")"
      printf 'dns_desired_hash=%s\n' "$(openkill_shadow_short_hash "${openkill_shadow_typed_dns_desired_hash:-}")"
      printf 'model_gap_count=%s\n' "${openkill_shadow_typed_model_gap_count:-0}"
      printf 'out_of_scope_observed_count=%s\n' "${openkill_shadow_typed_out_of_scope_count:-0}"
      printf 'unknown_count=%s\n' "${openkill_shadow_typed_unknown_count:-0}"
      printf 'dns_parity=%s\n' "${openkill_shadow_typed_dns_parity:-NOT_RUN}"
   ) > "$openkill_shadow_tmp" && mv -f "$openkill_shadow_tmp" "$openkill_shadow_dir/status" || {
      rm -f "$openkill_shadow_tmp"
      return 1
   }
   # Keep a bounded dedupe key for mismatch diagnostics.  This is telemetry,
   # never applied state, and contains no addresses, domains, or credentials.
   case "$openkill_shadow_status_value" in
      MISMATCH|MODEL_GAP|COMPARE_ERROR|RENDER_ERROR|INPUT_ERROR|SOURCE_DRIFT|STALE|UNSUPPORTED_CURRENT_STATE)
         printf '%s\n' "$openkill_shadow_status_value:$openkill_shadow_old_value:$openkill_shadow_new_value:$(openkill_shadow_generation_telemetry_value "$openkill_shadow_generation_value")" > "$openkill_shadow_dir/last_mismatch.tmp.$$" &&
            mv -f "$openkill_shadow_dir/last_mismatch.tmp.$$" "$openkill_shadow_dir/last_mismatch" || true
      ;;
   esac
   return 0
}

openkill_shadow_log_bounded()
{
   # LOG_* are supplied by the existing process.  Keep the message short and
   # never include the payload or any normalized set contents.
   openkill_shadow_log_status=$1
   openkill_shadow_log_old=$2
   openkill_shadow_log_new=$3
   openkill_shadow_log_reason=$4
   if command -v LOG_WARN >/dev/null 2>&1; then
      openkill_shadow_log_dir=${OPENKILL_NFT_SHADOW_TELEMETRY_DIR:-$OPENKILL_NFT_SHADOW_TELEMETRY_DEFAULT}
      openkill_shadow_log_key="$openkill_shadow_log_status:$openkill_shadow_log_old:$openkill_shadow_log_new:$(openkill_shadow_generation_telemetry_value "${openkill_shadow_generation_for_log:--}")"
      if [ -r "$openkill_shadow_log_dir/last_mismatch" ] &&
         [ "$(sed -n '1p' "$openkill_shadow_log_dir/last_mismatch" 2>/dev/null)" = "$openkill_shadow_log_key" ]; then
         return 0
      fi
      LOG_WARN "OpenKill shadow ${openkill_shadow_log_status} old=$(openkill_shadow_short_hash "$openkill_shadow_log_old") new=$(openkill_shadow_short_hash "$openkill_shadow_log_new") reason=${openkill_shadow_log_reason}"
   fi
}

# 3E.2D2D-R3A typed semantic projection --------------------------------------
#
# The automatic comparator historically compared physical nft declarations.
# R3A keeps that path for older callers, but adds an explicit semantic bundle
# path for the production coordinator.  R3C produces that bundle internally
# from the completed capture/parser and CURRENT renderer; the explicit files
# remain a fixture/development compatibility path.  The bundle is bounded,
# never a live read, and never interpreted as shell code.  Logical identity and
# ownership class come from the formal inventory projection.  Physical names
# are retained for observation only.

openkill_shadow_typed_manifest_path()
{
   openkill_shadow_typed_manifest_value=${OPENKILL_NFT_SHADOW_SEMANTIC_MANIFEST:-}
   if [ -z "$openkill_shadow_typed_manifest_value" ]; then
      if [ -n "${OPENKILL_NFT_SHADOW_TEMPLATE_DIR:-}" ]; then
         openkill_shadow_typed_manifest_value=$OPENKILL_NFT_SHADOW_TEMPLATE_DIR/semantic_model_v1.tsv
      else
         openkill_shadow_typed_manifest_value=$OPENKILL_NFT_SHADOW_SEMANTIC_MANIFEST_DEFAULT
      fi
   fi
   openkill_shadow_safe_path "$openkill_shadow_typed_manifest_value" || return 1
   [ -r "$openkill_shadow_typed_manifest_value" ] || return 1
   printf '%s\n' "$openkill_shadow_typed_manifest_value"
}

openkill_shadow_typed_prepare_file()
{
   openkill_shadow_typed_source=$1
   openkill_shadow_typed_destination=$2
   [ -n "$openkill_shadow_typed_source" ] && [ -n "$openkill_shadow_typed_destination" ] || return 1
   openkill_shadow_safe_path "$openkill_shadow_typed_source" || return 1
   openkill_shadow_safe_path "$openkill_shadow_typed_destination" || return 1
   [ -r "$openkill_shadow_typed_source" ] || return 1
   openkill_shadow_typed_size=$(wc -c < "$openkill_shadow_typed_source") || return 1
   [ "$openkill_shadow_typed_size" -le "$OPENKILL_NFT_SHADOW_MAX_PAYLOAD_BYTES" ] || return 1
   cp "$openkill_shadow_typed_source" "$openkill_shadow_typed_destination" || return 1
   [ "$(sed -n '1p' "$openkill_shadow_typed_destination")" = 'OPENKILL_SHADOW_TYPED_INTENT_V1=1' ] || return 1
   return 0
}

# R3C automatic typed-sidecar producer ---------------------------------------
#
# Automatic production cycles must not depend on a caller-created semantic
# bundle.  These helpers consume only the already frozen renderer input and
# parsed legacy intent.  They deliberately use small, line-oriented AWK
# programs so the device path remains POSIX/BusyBox compatible and never
# invokes a second discovery read.

openkill_shadow_typed_manifest_expected()
{
   openkill_shadow_typed_manifest_input=$1
   openkill_shadow_typed_manifest_output=$2
   [ -r "$openkill_shadow_typed_manifest_input" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_safe_path "$openkill_shadow_typed_manifest_input" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_safe_path "$openkill_shadow_typed_manifest_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   awk -F '	' -v OFS='	' -v output="$openkill_shadow_typed_manifest_output" '
      function valid_token(v) { return v != "" && v !~ /[\r\n\t]/ }
      function valid_value(field, value) {
         if (!valid_token(value)) return 0
         if (field == "DNSMASQ_LISTEN_TARGET") return value ~ /^[0-9]+$/ && value >= 1 && value <= 65535
         if (field == "DNSMASQ_UPSTREAM_TARGET") return value ~ /^[A-Za-z0-9.:#_\[\]-]+$/
         if (field == "MIHOMO_DNS_LISTENER") return value ~ /^[A-Za-z0-9.:#_\[\]-]+$/
         if (field == "DNS_LOOP_PREVENTION") return value == "skgid_exempt=65534"
         if (field == "DNS_SCOPE_IPV4" || field == "DNS_SCOPE_IPV6") return value == "lan=true,router=true"
         return 0
      }
      BEGIN { fields="DNSMASQ_LISTEN_TARGET DNSMASQ_UPSTREAM_TARGET MIHOMO_DNS_LISTENER DNS_LOOP_PREVENTION DNS_SCOPE_IPV4 DNS_SCOPE_IPV6" }
      FNR == 1 { if ($0 != "OPENKILL_SHADOW_SEMANTIC_MANIFEST_V1=1") bad=1; next }
      $0 ~ /^[[:space:]]*$/ || $0 ~ /^#/ { next }
      $1 == "DNS_EXPECTED" && NF == 4 {
         if ($2 !~ /^(DNSMASQ_LISTEN_TARGET|DNSMASQ_UPSTREAM_TARGET|MIHOMO_DNS_LISTENER|DNS_LOOP_PREVENTION|DNS_SCOPE_IPV4|DNS_SCOPE_IPV6)$/ || !valid_value($2, $3) || !valid_token($4)) { bad=1; next }
         if ($2 in value) { bad=1; next }
         value[$2]=$3; source[$2]=$4; next
      }
      END {
         count=split(fields, wanted, " ")
         for (i=1; i<=count; i++) if (!(wanted[i] in value)) bad=1
         if (bad) exit 2
         for (i=1; i<=count; i++) print wanted[i], value[wanted[i]], source[wanted[i]] > output
      }
   ' "$openkill_shadow_typed_manifest_input"
   openkill_shadow_typed_manifest_rc=$?
   [ "$openkill_shadow_typed_manifest_rc" -eq 0 ] || {
      rm -f "$openkill_shadow_typed_manifest_output"
      return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   }
   [ -s "$openkill_shadow_typed_manifest_output" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   return 0
}

openkill_shadow_typed_dns_firewall_ports()
{
   openkill_shadow_typed_dns_input=$1
   openkill_shadow_typed_dns_output=$2
   openkill_shadow_typed_dns_metadata=${3:-}
   [ -r "$openkill_shadow_typed_dns_input" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_safe_path "$openkill_shadow_typed_dns_input" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_safe_path "$openkill_shadow_typed_dns_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   if [ -n "$openkill_shadow_typed_dns_metadata" ]; then
      openkill_shadow_safe_path "$openkill_shadow_typed_dns_metadata" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      [ -r "$openkill_shadow_typed_dns_metadata" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   fi
   awk -F '	' -v OFS='	' -v output="$openkill_shadow_typed_dns_output" -v metadata="$openkill_shadow_typed_dns_metadata" '
      function canon(v) { gsub(/[[:space:]]+/, " ", v); sub(/^ +/, "", v); sub(/ +$/, "", v); return v }
      function add(role, value) {
         if (value !~ /^[0-9]+$/ || value < 1 || value > 65535) { bad=1; return }
         if (role in seen && ports[role] != value) bad=1
         seen[role]=1; ports[role]=sprintf("%d", value)
      }
      function role_for(chain, family, role) {
         if (!(chain in meta_role)) return ""
         family=meta_family[chain]; role=meta_role[chain]
         if (role == "PREROUTING_MANGLE" && family == "IPv4") return "LAN4"
         if (role == "PREROUTING_MANGLE" && family == "IPv6") return "LAN6"
         if (role == "OUTPUT_MANGLE" && family == "IPv4") return "ROUTER4"
         if (role == "OUTPUT_MANGLE" && family == "IPv6") return "ROUTER6"
         return ""
      }
      function inspect(chain, expression, match_text, port_text, value, role) {
         role=role_for(chain)
         if (role == "") return
          # The legacy/current writers use both `openkill_dns_hijack*` for
          # LAN interception and `openkill_dns_redirect*` for router-origin
          # interception.  Match the typed DNS action family, rather than a
          # single physical spelling, while keeping the formal chain metadata
          # authoritative for the LAN/router/family role.
          if (expression !~ /jump[[:space:]]+openkill_dns(_|[[:space:]])/) return
          if (role == "LAN4") chain_seen["LAN4"]=1
          if (role == "LAN6") chain_seen["LAN6"]=1
          if (role == "ROUTER4") chain_seen["ROUTER4"]=1
          if (role == "ROUTER6") chain_seen["ROUTER6"]=1
         match_text=expression
         if (!match(match_text, /dport[[:space:]]+[0-9]+/)) { bad=1; return }
         port_text=substr(match_text, RSTART, RLENGTH)
         sub(/^.*[[:space:]]/, "", port_text)
         value=port_text + 0
         add(role, value)
      }
      BEGIN {
         if (metadata != "") {
            while ((getline metadata_line < metadata) > 0) {
               metadata_count=split(metadata_line, metadata_fields, "\t")
               if (metadata_fields[1] == "CHAIN" && metadata_count == 10) {
                  meta_family[metadata_fields[3]]=metadata_fields[4]
                  meta_role[metadata_fields[3]]=metadata_fields[6]
               }
            }
            close(metadata)
         }
      }
      {
          if ($1 == "CHAIN" && NF >= 2) {
             # Chain declarations alone do not prove DNS interception.  Scope
             # is marked only after a typed DNS jump rule is observed.
         }
         else if ($1 == "RULE" && NF >= 12) inspect($5, canon($7 " " $9))
         else if ($1 == "RULE" && NF >= 4) inspect($2, canon($4))
         # The desired side is rendered before the typed sidecar is built.
         # Consume only the renderer bounded `add rule inet fw4 ...` form;
         # this keeps desired DNS provenance tied to CURRENT renderer output
         # without rereading live state or accepting a caller-provided sidecar.
         else if ($0 ~ /^add[[:space:]]+rule[[:space:]]+inet[[:space:]]+fw4[[:space:]]+/) {
            raw=substr($0, 1)
            sub(/^add[[:space:]]+rule[[:space:]]+inet[[:space:]]+fw4[[:space:]]+/, "", raw)
             split(raw, raw_fields, /[[:space:]]+/)
             raw_chain=raw_fields[1]
             role=role_for(raw_chain)
             sub(/^[^[:space:]]+[[:space:]]+/, "", raw)
            inspect(raw_chain, canon(raw))
         }
      }
       END {
          # The target is a typed LAN/router value while family coverage is a
          # separate scope field.  If one family is absent but the other
          # family supplies the same LAN/router target, preserve the target and
          # let the scope comparison report a real semantic mismatch.  A
          # completely absent LAN or router source remains a model gap.
          if (!("LAN4" in seen) && !("LAN6" in seen)) bad=1
          if (!("ROUTER4" in seen) && !("ROUTER6" in seen)) bad=1
          if ("LAN4" in ports && "LAN6" in ports && ports["LAN4"] != ports["LAN6"]) bad=1
          if ("ROUTER4" in ports && "ROUTER6" in ports && ports["ROUTER4"] != ports["ROUTER6"]) bad=1
          if (!("LAN4" in chain_seen) && !("LAN6" in chain_seen) && !("ROUTER4" in chain_seen) && !("ROUTER6" in chain_seen)) bad=1
          if (bad) exit 2
          print "DNS_FIREWALL_LAN_TARGET", ("LAN4" in ports ? ports["LAN4"] : ports["LAN6"]) > output
          print "DNS_FIREWALL_ROUTER_TARGET", ("ROUTER4" in ports ? ports["ROUTER4"] : ports["ROUTER6"]) > output
         print "DNS_SCOPE_IPV4", ("LAN4" in chain_seen ? "lan=true" : "lan=false") "," ("ROUTER4" in chain_seen ? "router=true" : "router=false") > output
         print "DNS_SCOPE_IPV6", ("LAN6" in chain_seen ? "lan=true" : "lan=false") "," ("ROUTER6" in chain_seen ? "router=true" : "router=false") > output
      }
   ' "$openkill_shadow_typed_dns_input"
   openkill_shadow_typed_dns_rc=$?
   [ "$openkill_shadow_typed_dns_rc" -eq 0 ] || {
      rm -f "$openkill_shadow_typed_dns_output"
      return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   }
   return 0
}

openkill_shadow_typed_dns_loop_prevention()
{
   openkill_shadow_typed_loop_input=$1
   openkill_shadow_typed_loop_output=$2
   openkill_shadow_typed_loop_metadata=${3:-}
   [ -r "$openkill_shadow_typed_loop_input" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_safe_path "$openkill_shadow_typed_loop_input" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_safe_path "$openkill_shadow_typed_loop_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   if [ -n "$openkill_shadow_typed_loop_metadata" ]; then
      openkill_shadow_safe_path "$openkill_shadow_typed_loop_metadata" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      [ -r "$openkill_shadow_typed_loop_metadata" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   fi
   awk -F '	' -v OFS='	' -v output="$openkill_shadow_typed_loop_output" -v metadata="$openkill_shadow_typed_loop_metadata" '
      function canon(v) { gsub(/[[:space:]]+/, " ", v); sub(/^ +/, "", v); sub(/ +$/, "", v); return v }
      function relevant(chain) {
         return chain in meta_role && (meta_role[chain] == "PREROUTING_MANGLE" || meta_role[chain] == "OUTPUT_MANGLE")
      }
      function inspect(chain, expression, value, match_text) {
         if (!relevant(chain)) return
         if (!(chain in chain_seen)) chain_seen_count++
         chain_seen[chain]=1
         match_text=canon(expression)
         if (match_text !~ /(^|[[:space:]])(meta[[:space:]]+)?skgid([[:space:]]+|[[:space:]]+!=[[:space:]]+|[[:space:]]+==[[:space:]]+)[0-9]+/) return
         if (!match(match_text, /skgid([[:space:]]+|[[:space:]]+!=[[:space:]]+|[[:space:]]+==[[:space:]]+)[0-9]+/)) { bad=1; return }
         value=substr(match_text, RSTART, RLENGTH)
         sub(/^.*skgid[[:space:]]+/, "", value)
         sub(/^!=[[:space:]]+/, "", value)
         sub(/^==[[:space:]]+/, "", value)
         if (value !~ /^[0-9]+$/) { bad=1; return }
         if (seen_value && loop_value != value) bad=1
         loop_value=value; seen_value=1
      }
      BEGIN {
         if (metadata != "") {
            while ((getline metadata_line < metadata) > 0) {
               metadata_count=split(metadata_line, metadata_fields, "\t")
               if (metadata_fields[1] == "CHAIN" && metadata_count == 10) {
                  meta_role[metadata_fields[3]]=metadata_fields[6]
               }
            }
            close(metadata)
         }
      }
      {
         if ($1 == "RULE" && NF >= 12) inspect($5, canon($7 " " $9))
         else if ($1 == "RULE" && NF >= 4) inspect($2, canon($4))
         else if ($0 ~ /^add[[:space:]]+rule[[:space:]]+inet[[:space:]]+fw4[[:space:]]+/) {
            raw=substr($0, 1)
            sub(/^add[[:space:]]+rule[[:space:]]+inet[[:space:]]+fw4[[:space:]]+/, "", raw)
            split(raw, raw_fields, /[[:space:]]+/)
            raw_chain=raw_fields[1]
            sub(/^[^[:space:]]+[[:space:]]+/, "", raw)
            inspect(raw_chain, canon(raw))
         }
      }
      END {
         if (!seen_value) {
            if (chain_seen_count == 0) bad=1
            else loop_value="missing"
         }
         if (bad) exit 2
         print "DNS_LOOP_PREVENTION", "skgid_exempt=" loop_value > output
      }
   ' "$openkill_shadow_typed_loop_input"
   openkill_shadow_typed_loop_rc=$?
   [ "$openkill_shadow_typed_loop_rc" -eq 0 ] || {
      rm -f "$openkill_shadow_typed_loop_output"
      return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   }
   return 0
}

openkill_shadow_typed_emit_objects()
{
   openkill_shadow_typed_emit_side=$1
   openkill_shadow_typed_emit_template=$2
   openkill_shadow_typed_emit_intent=$3
   openkill_shadow_typed_emit_manifest=$4
   openkill_shadow_typed_emit_output=$5
   [ -r "$openkill_shadow_typed_emit_template" ] && [ -r "$openkill_shadow_typed_emit_manifest" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   [ -r "$openkill_shadow_typed_emit_intent" ] || [ "$openkill_shadow_typed_emit_side" = DESIRED ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   for openkill_shadow_typed_emit_path in "$openkill_shadow_typed_emit_template" "$openkill_shadow_typed_emit_manifest" "$openkill_shadow_typed_emit_intent" "$openkill_shadow_typed_emit_output"; do
      [ -n "$openkill_shadow_typed_emit_path" ] || continue
      openkill_shadow_safe_path "$openkill_shadow_typed_emit_path" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   done
   awk -F '	' -v OFS='	' \
      -v side="$openkill_shadow_typed_emit_side" \
      -v manifest_file="$openkill_shadow_typed_emit_manifest" \
      -v template_file="$openkill_shadow_typed_emit_template" \
      -v intent_file="$openkill_shadow_typed_emit_intent" \
      -v output="$openkill_shadow_typed_emit_output" '
      function canon(v) { gsub(/[[:space:]]+/, " ", v); sub(/^ +/, "", v); sub(/ +$/, "", v); return v }
      function listcanon(v, a, n, i, j, t, out, last) {
         v=canon(v); gsub(/,/, " ", v); if (v == "" || v == "-") return "-"
         n=split(v, a, /[[:space:]]+/)
         for (i=1; i<=n; i++) { t=a[i]; j=i; while (j > 1 && a[j-1] > t) { a[j]=a[j-1]; j-- } a[j]=t }
         out=""; last=""
         for (i=1; i<=n; i++) if (a[i] != "" && a[i] != last) { if (out != "") out=out ","; out=out a[i]; last=a[i] }
         return out == "" ? "-" : out
      }
      function inventory_class(type, physical, component, key) {
         key=type SUBSEP physical
         if (key in inv_owner) { current_component=inv_component[key]; return inv_owner[key] }
         current_component=component
         if (component == "UPNP") return "OPTIONAL_OBSERVATION"
         if (component == "WAN_INPUT") return "LEGACY_ONLY_SAFETY"
         if (component !~ /^(ACCESS|CHINA|DNS|LOCAL|NODE|PROXY_ACTION|SERVICE|TOPOLOGY)$/) return "UNKNOWN"
         return "CURRENT_OWNED"
      }
      function emit(type, logical, physical, component, owner, state, semantic) {
         if (owner == "") { bad=1; return }
         print "OBJECT", type, logical, physical, component, owner, state, canon(semantic) >> output
      }
      function template_chain(logical, physical, family, component, role, base, ctype, hook, priority) {
         chain_n++; chain_logical[chain_n]=logical; chain_physical[chain_n]=physical; chain_family[chain_n]=family; chain_component[chain_n]=component; chain_role[chain_n]=role; chain_base[chain_n]=base; chain_type[chain_n]=ctype; chain_hook[chain_n]=hook; chain_priority[chain_n]=priority
         chain_by_physical[physical]=chain_n
      }
      function template_set(logical, physical, family, etype, flags, elements, component) {
         set_n++; set_logical[set_n]=logical; set_physical[set_n]=physical; set_family[set_n]=family; set_etype[set_n]=etype; set_flags[set_n]=flags; set_elements[set_n]=elements; set_component[set_n]=component
         set_by_physical[physical]=set_n
      }
      function template_rule(logical, component, family, chain, order, match_text, action_type, action_expr, reason, decision, gap) {
         rule_n++; rule_logical[rule_n]=logical; rule_component[rule_n]=component; rule_family[rule_n]=family; rule_chain[rule_n]=chain; rule_order[rule_n]=order; rule_match[rule_n]=canon(match_text); rule_action_type[rule_n]=action_type; rule_action[rule_n]=canon(action_expr); rule_reason[rule_n]=reason; rule_decision[rule_n]=decision; rule_gap[rule_n]=gap
         rule_expression[rule_n]=canon(rule_match[rule_n] " " rule_action[rule_n])
      }
      function is_base(chain) { return chain == "dstnat" || chain == "mangle_prerouting" || chain == "mangle_output" || chain == "output" || chain == "srcnat" || chain == "input" || chain == "forward" }
      function actual_rule_add(chain, order, expression) { actual_rule_n++; actual_chain[actual_rule_n]=chain; actual_order[actual_rule_n]=order; actual_expression[actual_rule_n]=canon(expression) }
      function actual_find(chain, expression, i) {
         for (i=1; i<=actual_rule_n; i++) if (!actual_used[i] && actual_chain[i] == chain && actual_expression[i] == expression) { actual_used[i]=1; return i }
         return 0
      }
       function canonical_hook(value) {
          value=canon(value)
          if (value == "prerouting") return "PREROUTING"
          if (value == "input") return "INPUT"
          if (value == "forward") return "FORWARD"
          if (value == "output") return "OUTPUT"
          if (value == "postrouting") return "POSTROUTING"
          return value
       }
       function object_semantic_chain(i, hook_value, priority_value) {
          hook_value=canonical_hook(chain_hook[i]); priority_value=chain_priority[i]
          if (chain_physical[i] in actual_hook) hook_value=actual_hook[chain_physical[i]]
          if (chain_physical[i] in actual_priority) priority_value=actual_priority[chain_physical[i]]
          hook_value=canonical_hook(hook_value)
          return "family=" chain_family[i] ";component=" chain_component[i] ";role=" chain_role[i] ";base=" chain_base[i] ";type=" chain_type[i] ";hook=" (hook_value == "" ? "-" : hook_value) ";priority=" (priority_value == "" ? "-" : priority_value)
      }
      function object_semantic_set(i, elements) {
         elements=set_elements[i]; if (set_physical[i] in actual_set_elements) elements=actual_set_elements[set_physical[i]]
         return "family=" set_family[i] ";element_type=" set_etype[i] ";flags=" (set_flags[i] == "" ? "-" : set_flags[i]) ";elements=" listcanon(elements)
      }
      FILENAME == manifest_file {
         if ($1 == "INVENTORY" && NF == 5) { key=$2 SUBSEP $3; if (key in inv_owner) bad=1; inv_owner[key]=$4; inv_component[key]=$5 }
         next
      }
      FILENAME == template_file {
         if ($1 == "CHAIN" && NF == 10) template_chain($2,$3,$4,$5,$6,$7,$8,$9,$10)
         else if ($1 == "SET" && NF == 8) template_set($2,$3,$4,$5,$6,$7,$8)
         else if ($1 == "RULE" && NF == 12) template_rule($2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
         next
      }
      FILENAME == intent_file {
         if ($1 == "CHAIN" && NF >= 2) actual_chain_present[$2]=1
          else if ($1 == "HOOK" && NF >= 5) { actual_hook[$2]=$4; actual_priority[$2]=$5 }
         else if ($1 == "SET" && NF >= 5) { actual_set_present[$2]=1; actual_set_elements[$2]=listcanon($5) }
         else if ($1 == "RULE" && NF >= 4) { if (!is_base($2) && $2 != "nat_output") actual_rule_add($2,$3,$4) }
         next
      }
      END {
         if (bad) exit 2
         if (side == "DESIRED") {
            for (i=1; i<=chain_n; i++) { owner=inventory_class("chain",chain_physical[i],chain_component[i]); emit("chain",chain_logical[i],chain_physical[i],current_component,owner,"ACTIVE",object_semantic_chain(i)) }
            for (i=1; i<=set_n; i++) { owner=inventory_class("set",set_physical[i],set_component[i]); emit("set",set_logical[i],set_physical[i],current_component,owner,"ACTIVE",object_semantic_set(i)) }
            for (i=1; i<=rule_n; i++) emit("rule",rule_logical[i],"current_" rule_logical[i],rule_component[i],"CURRENT_OWNED","ACTIVE","family=" rule_family[i] ";chain=" rule_chain[i] ";match=" rule_match[i] ";action=" rule_action[i] ";reason=" rule_reason[i] ";decision=" rule_decision[i] ";gap=" rule_gap[i])
         } else {
            for (i=1; i<=chain_n; i++) if (chain_physical[i] in actual_chain_present) { owner=inventory_class("chain",chain_physical[i],chain_component[i]); emit("chain",chain_logical[i],chain_physical[i],current_component,owner,"ACTIVE",object_semantic_chain(i)) }
            for (i=1; i<=set_n; i++) if (set_physical[i] in actual_set_present) { owner=inventory_class("set",set_physical[i],set_component[i]); emit("set",set_logical[i],set_physical[i],current_component,owner,"ACTIVE",object_semantic_set(i)) }
            for (i=1; i<=rule_n; i++) {
               j=actual_find(rule_chain[i],rule_expression[i])
               if (j > 0) emit("rule",rule_logical[i],rule_chain[i] "_rule_" actual_order[j],rule_component[i],"CURRENT_OWNED","ACTIVE","family=" rule_family[i] ";chain=" rule_chain[i] ";match=" rule_match[i] ";action=" rule_action[i] ";reason=" rule_reason[i] ";decision=" rule_decision[i] ";gap=" rule_gap[i])
            }
            for (j=1; j<=actual_rule_n; j++) if (!actual_used[j]) {
               if (actual_expression[j] ~ /(^|[[:space:]])jump[[:space:]]+openkill_upnp([[:space:]]|$)/) continue
               if (!(actual_chain[j] in chain_by_physical)) { bad=1; continue }
               emit("rule","UNMATCHED_RULE_" actual_chain[j] "_" actual_order[j],actual_chain[j] "_rule_" actual_order[j],"TOPOLOGY","CURRENT_OWNED","ACTIVE","chain=" actual_chain[j] ";expression=" actual_expression[j])
            }
         }
         if (bad) exit 2
      }
   ' "$openkill_shadow_typed_emit_manifest" "$openkill_shadow_typed_emit_template" "$openkill_shadow_typed_emit_intent" >> "$openkill_shadow_typed_emit_output"
   openkill_shadow_typed_emit_rc=$?
   [ "$openkill_shadow_typed_emit_rc" -eq 0 ] || {
      rm -f "$openkill_shadow_typed_emit_output"
      return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   }
   return 0
}

openkill_shadow_typed_sidecar_init()
{
   openkill_shadow_typed_sidecar_side=$1
   openkill_shadow_typed_sidecar_identity=$2
   openkill_shadow_typed_sidecar_output=$3
   [ "$openkill_shadow_typed_sidecar_side" = ACTUAL ] || [ "$openkill_shadow_typed_sidecar_side" = DESIRED ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_safe_value "$openkill_shadow_typed_sidecar_identity" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_safe_path "$openkill_shadow_typed_sidecar_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   umask 077
   {
      printf 'OPENKILL_SHADOW_TYPED_INTENT_V1=1\n'
      printf 'META\tschema_version\tOPENKILL_SHADOW_TYPED_SIDECAR_V1\n'
      printf 'META\tside\t%s\n' "$openkill_shadow_typed_sidecar_side"
      printf 'META\tcycle_identity\t%s\n' "$openkill_shadow_typed_sidecar_identity"
      printf 'META\tcontinuity_identity\t%s\n' "$openkill_shadow_typed_sidecar_identity"
      printf 'META\tmodel_version\t%s\n' "$OPENKILL_NFT_SHADOW_SEMANTIC_MODEL_VERSION"
      printf 'META\townership_model_version\t%s\n' "$OPENKILL_NFT_SHADOW_OWNERSHIP_MODEL_VERSION"
      printf 'META\tdns_model_version\t%s\n' "$OPENKILL_NFT_SHADOW_DNS_MODEL_VERSION"
   } > "$openkill_shadow_typed_sidecar_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   chmod 600 "$openkill_shadow_typed_sidecar_output" 2>/dev/null || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   return 0
}

openkill_shadow_typed_auto_produce()
{
   openkill_shadow_typed_actual_intent=$1
   openkill_shadow_typed_desired_input=$2
   openkill_shadow_typed_rendered_payload=$3
   openkill_shadow_typed_actual_output=$4
   openkill_shadow_typed_desired_output=$5
   [ -r "$openkill_shadow_typed_actual_intent" ] && [ -r "$openkill_shadow_typed_desired_input" ] && [ -r "$openkill_shadow_typed_rendered_payload" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   for openkill_shadow_typed_producer_path in "$openkill_shadow_typed_actual_intent" "$openkill_shadow_typed_desired_input" "$openkill_shadow_typed_rendered_payload" "$openkill_shadow_typed_actual_output" "$openkill_shadow_typed_desired_output"; do
      openkill_shadow_safe_path "$openkill_shadow_typed_producer_path" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   done
   openkill_shadow_typed_manifest=$(openkill_shadow_typed_manifest_path 2>/dev/null) || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_work=${openkill_shadow_tmp_dir:-${openkill_shadow_typed_actual_output%/*}}
   openkill_shadow_safe_path "$openkill_shadow_typed_work" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_defaults=$openkill_shadow_typed_work/typed-dns-defaults
   openkill_shadow_typed_actual_ports=$openkill_shadow_typed_work/typed-dns-actual
   openkill_shadow_typed_desired_ports=$openkill_shadow_typed_work/typed-dns-desired
   openkill_shadow_typed_actual_loop_file=$openkill_shadow_typed_work/typed-loop-actual
   openkill_shadow_typed_desired_loop_file=$openkill_shadow_typed_work/typed-loop-desired
   openkill_shadow_typed_empty_intent=$openkill_shadow_typed_work/typed-empty-intent
   for openkill_shadow_typed_tmp in "$openkill_shadow_typed_defaults" "$openkill_shadow_typed_actual_ports" "$openkill_shadow_typed_desired_ports" "$openkill_shadow_typed_actual_loop_file" "$openkill_shadow_typed_desired_loop_file" "$openkill_shadow_typed_empty_intent"; do
      openkill_shadow_safe_path "$openkill_shadow_typed_tmp" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      rm -f "$openkill_shadow_typed_tmp"
   done
   openkill_shadow_typed_manifest_expected "$openkill_shadow_typed_manifest" "$openkill_shadow_typed_defaults" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_dns_firewall_ports "$openkill_shadow_typed_actual_intent" "$openkill_shadow_typed_actual_ports" "$openkill_shadow_typed_desired_input" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_dns_firewall_ports "$openkill_shadow_typed_rendered_payload" "$openkill_shadow_typed_desired_ports" "$openkill_shadow_typed_desired_input" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_dns_loop_prevention "$openkill_shadow_typed_actual_intent" "$openkill_shadow_typed_actual_loop_file" "$openkill_shadow_typed_desired_input" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_dns_loop_prevention "$openkill_shadow_typed_rendered_payload" "$openkill_shadow_typed_desired_loop_file" "$openkill_shadow_typed_desired_input" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_actual_firewall_lan=$(awk -F '	' '$1 == "DNS_FIREWALL_LAN_TARGET" { print $2; exit }' "$openkill_shadow_typed_actual_ports") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_actual_firewall_router=$(awk -F '	' '$1 == "DNS_FIREWALL_ROUTER_TARGET" { print $2; exit }' "$openkill_shadow_typed_actual_ports") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_desired_firewall_lan=$(awk -F '	' '$1 == "DNS_FIREWALL_LAN_TARGET" { print $2; exit }' "$openkill_shadow_typed_desired_ports") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_desired_firewall_router=$(awk -F '	' '$1 == "DNS_FIREWALL_ROUTER_TARGET" { print $2; exit }' "$openkill_shadow_typed_desired_ports") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_actual_dnsmasq_listen=
   openkill_shadow_typed_actual_dnsmasq_upstream=
   openkill_shadow_typed_actual_mihomo_listener=
   if [ "${openkill_shadow_auto_continuity_mode:-0}" -eq 1 ]; then
      # In the production automatic path these values were frozen before T0
      # by openkill_shadow_capture_runtime_dns.  Reading the shell scalars is
      # therefore a read from the coherent snapshot, not a comparator-stage
      # UCI/netstat/Mihomo reread.
      openkill_shadow_typed_actual_dnsmasq_listen=${OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_LISTEN_TARGET:-}
      openkill_shadow_typed_actual_dnsmasq_upstream=${OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_UPSTREAM_TARGET:-}
      openkill_shadow_typed_actual_mihomo_listener=${OPENKILL_NFT_SHADOW_FROZEN_MIHOMO_DNS_LISTENER:-}
      openkill_shadow_typed_actual_dnsmasq_listen_source=${OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_LISTEN_SOURCE:-snapshot-dnsmasq}
      openkill_shadow_typed_actual_dnsmasq_upstream_source=${OPENKILL_NFT_SHADOW_FROZEN_DNSMASQ_UPSTREAM_SOURCE:-snapshot-dnsmasq}
      openkill_shadow_typed_actual_mihomo_source=${OPENKILL_NFT_SHADOW_FROZEN_MIHOMO_DNS_SOURCE:-snapshot-mihomo}
   else
      # Explicit source fixtures retain the established local test contract;
      # they are never the automatic device source.
      openkill_shadow_auto_field DNSMASQ_LISTEN_TARGET DNSMASQ_LISTEN || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      openkill_shadow_typed_actual_dnsmasq_listen=$openkill_shadow_auto_field_value
      openkill_shadow_typed_actual_dnsmasq_listen_source=fixture-runtime-dnsmasq
      openkill_shadow_auto_field DNSMASQ_UPSTREAM_TARGET DNSMASQ_UPSTREAM || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      openkill_shadow_typed_actual_dnsmasq_upstream=$openkill_shadow_auto_field_value
      openkill_shadow_typed_actual_dnsmasq_upstream_source=fixture-runtime-dnsmasq
      openkill_shadow_auto_field MIHOMO_DNS_LISTENER MIHOMO_LISTENER || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      openkill_shadow_typed_actual_mihomo_listener=$openkill_shadow_auto_field_value
      openkill_shadow_typed_actual_mihomo_source=fixture-runtime-mihomo
   fi
   openkill_shadow_typed_actual_loop=$(awk -F '	' '$1 == "DNS_LOOP_PREVENTION" { print $2; exit }' "$openkill_shadow_typed_actual_loop_file") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_actual_scope4=$(awk -F '	' '$1 == "DNS_SCOPE_IPV4" { print $2; exit }' "$openkill_shadow_typed_actual_ports") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_actual_scope6=$(awk -F '	' '$1 == "DNS_SCOPE_IPV6" { print $2; exit }' "$openkill_shadow_typed_actual_ports") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_desired_dnsmasq_listen=$(awk -F '	' '$1 == "DNSMASQ_LISTEN_TARGET" { print $2; exit }' "$openkill_shadow_typed_defaults") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_desired_dnsmasq_upstream=$(awk -F '	' '$1 == "DNSMASQ_UPSTREAM_TARGET" { print $2; exit }' "$openkill_shadow_typed_defaults") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_desired_mihomo_listener=$(awk -F '	' '$1 == "MIHOMO_DNS_LISTENER" { print $2; exit }' "$openkill_shadow_typed_defaults") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_desired_loop=$(awk -F '	' '$1 == "DNS_LOOP_PREVENTION" { print $2; exit }' "$openkill_shadow_typed_desired_loop_file") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_desired_scope4=$(awk -F '	' '$1 == "DNS_SCOPE_IPV4" { print $2; exit }' "$openkill_shadow_typed_desired_ports") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_desired_scope6=$(awk -F '	' '$1 == "DNS_SCOPE_IPV6" { print $2; exit }' "$openkill_shadow_typed_desired_ports") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   [ -n "$openkill_shadow_typed_actual_dnsmasq_listen" ] && [ -n "$openkill_shadow_typed_actual_dnsmasq_upstream" ] && [ -n "$openkill_shadow_typed_actual_mihomo_listener" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   [ -n "$openkill_shadow_typed_actual_loop" ] && [ -n "$openkill_shadow_typed_actual_scope4" ] && [ -n "$openkill_shadow_typed_actual_scope6" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   [ -n "$openkill_shadow_typed_desired_loop" ] && [ -n "$openkill_shadow_typed_desired_scope4" ] && [ -n "$openkill_shadow_typed_desired_scope6" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_identity=${openkill_shadow_continuity_token_value:-${openkill_shadow_generation_for_log:-}}
   [ -n "$openkill_shadow_typed_identity" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_sidecar_init ACTUAL "$openkill_shadow_typed_identity" "$openkill_shadow_typed_actual_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_sidecar_init DESIRED "$openkill_shadow_typed_identity" "$openkill_shadow_typed_desired_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_emit_objects ACTUAL "$openkill_shadow_typed_desired_input" "$openkill_shadow_typed_actual_intent" "$openkill_shadow_typed_manifest" "$openkill_shadow_typed_actual_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   : > "$openkill_shadow_typed_empty_intent" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   chmod 600 "$openkill_shadow_typed_empty_intent" 2>/dev/null || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_emit_objects DESIRED "$openkill_shadow_typed_desired_input" "$openkill_shadow_typed_empty_intent" "$openkill_shadow_typed_manifest" "$openkill_shadow_typed_desired_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   {
      printf 'DNS\tDNS_FIREWALL_LAN_TARGET\t%s\tCURRENT_OWNED\tlegacy-capture\tACTIVE\n' "$openkill_shadow_typed_actual_firewall_lan"
      printf 'DNS\tDNS_FIREWALL_ROUTER_TARGET\t%s\tCURRENT_OWNED\tlegacy-capture\tACTIVE\n' "$openkill_shadow_typed_actual_firewall_router"
      printf 'DNS\tDNSMASQ_LISTEN_TARGET\t%s\tCURRENT_OWNED\t%s\tACTIVE\n' "$openkill_shadow_typed_actual_dnsmasq_listen" "$openkill_shadow_typed_actual_dnsmasq_listen_source"
      printf 'DNS\tDNSMASQ_UPSTREAM_TARGET\t%s\tCURRENT_OWNED\t%s\tACTIVE\n' "$openkill_shadow_typed_actual_dnsmasq_upstream" "$openkill_shadow_typed_actual_dnsmasq_upstream_source"
      printf 'DNS\tMIHOMO_DNS_LISTENER\t%s\tCURRENT_OWNED\t%s\tACTIVE\n' "$openkill_shadow_typed_actual_mihomo_listener" "$openkill_shadow_typed_actual_mihomo_source"
      printf 'DNS\tDNS_LOOP_PREVENTION\t%s\tCURRENT_OWNED\tcommitted-dns-scope\tACTIVE\n' "$openkill_shadow_typed_actual_loop"
      printf 'DNS\tDNS_SCOPE_IPV4\t%s\tCURRENT_OWNED\tcommitted-dns-scope\tACTIVE\n' "$openkill_shadow_typed_actual_scope4"
      printf 'DNS\tDNS_SCOPE_IPV6\t%s\tCURRENT_OWNED\tcommitted-dns-scope\tACTIVE\n' "$openkill_shadow_typed_actual_scope6"
   } >> "$openkill_shadow_typed_actual_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   {
      printf 'DNS\tDNS_FIREWALL_LAN_TARGET\t%s\tCURRENT_OWNED\tcurrent-renderer\tACTIVE\n' "$openkill_shadow_typed_desired_firewall_lan"
      printf 'DNS\tDNS_FIREWALL_ROUTER_TARGET\t%s\tCURRENT_OWNED\tcurrent-renderer\tACTIVE\n' "$openkill_shadow_typed_desired_firewall_router"
      printf 'DNS\tDNSMASQ_LISTEN_TARGET\t%s\tCURRENT_OWNED\tcurrent-contract-dnsmasq\tACTIVE\n' "$openkill_shadow_typed_desired_dnsmasq_listen"
      printf 'DNS\tDNSMASQ_UPSTREAM_TARGET\t%s\tCURRENT_OWNED\tcurrent-contract-dnsmasq\tACTIVE\n' "$openkill_shadow_typed_desired_dnsmasq_upstream"
      printf 'DNS\tMIHOMO_DNS_LISTENER\t%s\tCURRENT_OWNED\tcurrent-contract-mihomo\tACTIVE\n' "$openkill_shadow_typed_desired_mihomo_listener"
      printf 'DNS\tDNS_LOOP_PREVENTION\t%s\tCURRENT_OWNED\tcurrent-contract-nft\tACTIVE\n' "$openkill_shadow_typed_desired_loop"
      printf 'DNS\tDNS_SCOPE_IPV4\t%s\tCURRENT_OWNED\tcurrent-contract-scope\tACTIVE\n' "$openkill_shadow_typed_desired_scope4"
      printf 'DNS\tDNS_SCOPE_IPV6\t%s\tCURRENT_OWNED\tcurrent-contract-scope\tACTIVE\n' "$openkill_shadow_typed_desired_scope6"
   } >> "$openkill_shadow_typed_desired_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   for openkill_shadow_typed_final in "$openkill_shadow_typed_actual_output" "$openkill_shadow_typed_desired_output"; do
      openkill_shadow_typed_size=$(wc -c < "$openkill_shadow_typed_final") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      [ "$openkill_shadow_typed_size" -le "$OPENKILL_NFT_SHADOW_MAX_PAYLOAD_BYTES" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      chmod 600 "$openkill_shadow_typed_final" 2>/dev/null || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   done
   return 0
}

openkill_shadow_compare_typed_intent()
{
   openkill_shadow_typed_actual=$1
   openkill_shadow_typed_desired=$2
   openkill_shadow_typed_parent=${3:-${openkill_shadow_tmp_dir:-}}
   openkill_shadow_typed_actual_owned_hash=
   openkill_shadow_typed_desired_owned_hash=
   openkill_shadow_typed_actual_full_hash=
   openkill_shadow_typed_desired_full_hash=
   openkill_shadow_typed_dns_actual_hash=
   openkill_shadow_typed_dns_desired_hash=
   openkill_shadow_typed_model_gap_count=0
   openkill_shadow_typed_mismatch_count=0
   openkill_shadow_typed_out_of_scope_count=0
   openkill_shadow_typed_unknown_count=0
   openkill_shadow_typed_dns_parity=MODEL_GAP
   openkill_shadow_typed_status=MODEL_GAP
   openkill_shadow_typed_reason=typed-input-unavailable
   [ -n "$openkill_shadow_typed_parent" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_safe_path "$openkill_shadow_typed_parent" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   [ -d "$openkill_shadow_typed_parent" ] || mkdir -p "$openkill_shadow_typed_parent" 2>/dev/null || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_work=$openkill_shadow_typed_parent/typed-semantic
   openkill_shadow_safe_path "$openkill_shadow_typed_work" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   mkdir "$openkill_shadow_typed_work" 2>/dev/null || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_typed_manifest=$(openkill_shadow_typed_manifest_path 2>/dev/null) || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_safe_path "$openkill_shadow_typed_manifest" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_safe_path "$openkill_shadow_typed_actual" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   openkill_shadow_safe_path "$openkill_shadow_typed_desired" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   [ -r "$openkill_shadow_typed_manifest" ] && [ -r "$openkill_shadow_typed_actual" ] && [ -r "$openkill_shadow_typed_desired" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   for openkill_shadow_typed_input in "$openkill_shadow_typed_manifest" "$openkill_shadow_typed_actual" "$openkill_shadow_typed_desired"; do
      openkill_shadow_typed_size=$(wc -c < "$openkill_shadow_typed_input") || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      [ "$openkill_shadow_typed_size" -le "$OPENKILL_NFT_SHADOW_MAX_PAYLOAD_BYTES" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   done
   openkill_shadow_typed_summary=$openkill_shadow_typed_work/summary
   openkill_shadow_typed_actual_full=$openkill_shadow_typed_work/actual.full
   openkill_shadow_typed_desired_full=$openkill_shadow_typed_work/desired.full
   openkill_shadow_typed_actual_owned=$openkill_shadow_typed_work/actual.owned
   openkill_shadow_typed_desired_owned=$openkill_shadow_typed_work/desired.owned
   for openkill_shadow_typed_output in "$openkill_shadow_typed_summary" "$openkill_shadow_typed_actual_full" "$openkill_shadow_typed_desired_full" "$openkill_shadow_typed_actual_owned" "$openkill_shadow_typed_desired_owned"; do
      openkill_shadow_safe_path "$openkill_shadow_typed_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      : > "$openkill_shadow_typed_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   done

   # The manifest defines the accepted ownership vocabulary and the eight
   # typed DNS fields.  The sidecars contain the formal inventory projection
   # and captured/renderer semantic values.  AWK is used only as a bounded,
   # line-oriented parser so this remains POSIX/BusyBox compatible.
   awk -F '\t' \
      -v OFS='\t' \
      -v manifest_file="$openkill_shadow_typed_manifest" \
      -v actual_file="$openkill_shadow_typed_actual" \
      -v desired_file="$openkill_shadow_typed_desired" \
      -v summary_file="$openkill_shadow_typed_summary" \
      -v actual_full_file="$openkill_shadow_typed_actual_full" \
      -v desired_full_file="$openkill_shadow_typed_desired_full" \
      -v actual_owned_file="$openkill_shadow_typed_actual_owned" \
      -v desired_owned_file="$openkill_shadow_typed_desired_owned" '
      function gap(reason) {
         model_gap++
         if (gap_reason == "") gap_reason=reason
      }
      function valid_token(value) {
         return value != "" && value !~ /[\r\n\t]/
      }
      function valid_class(value) { return value in class_allowed }
      function comparable(value) {
         return value == "CURRENT_OWNED" || value == "CONDITIONAL_CURRENT"
      }
      function noncomparable(value) {
         return value == "LEGACY_ONLY_SAFETY" || value == "FW4_BASE" ||
                value == "INACTIVE_MODE" || value == "OPTIONAL_OBSERVATION" ||
                value == "OUT_OF_SCOPE"
      }
      function canonical(value) {
         gsub(/[[:space:]]+/, " ", value)
         sub(/^ +/, "", value)
         sub(/ +$/, "", value)
         return value
      }
      function dns_value(field, value, number) {
         value=canonical(value)
         if (value == "" || value == "-") return ""
         if (field == "DNS_FIREWALL_LAN_TARGET" ||
             field == "DNS_FIREWALL_ROUTER_TARGET" ||
             field == "DNSMASQ_LISTEN_TARGET") {
            if (value !~ /^[0-9]+$/) return ""
            number=value + 0
            if (number < 1 || number > 65535) return ""
            return sprintf("%d", number)
         }
         if (field == "DNSMASQ_UPSTREAM_TARGET" || field == "MIHOMO_DNS_LISTENER") {
            gsub(/[[:space:]]+/, "", value)
            if (value !~ /^[A-Za-z0-9.:#_\[\]-]+$/) return ""
            return value
         }
         if (field == "DNS_LOOP_PREVENTION" || field == "DNS_SCOPE_IPV4" || field == "DNS_SCOPE_IPV6")
            return value
         return ""
      }
      function record_object(side, type, logical, physical, component, owner, state, semantic, key) {
         if (type !~ /^(chain|set|attachment|rule)$/ || !valid_token(logical) ||
             !valid_token(physical) || !valid_token(component) ||
             !valid_class(owner) || state !~ /^(ACTIVE|INACTIVE)$/ ||
             !valid_token(semantic)) {
            gap("object-record-invalid")
            return
         }
         key=type SUBSEP physical
         if (key in inventory_expected_owner) {
            if (owner != inventory_expected_owner[key] || component != inventory_expected_component[key]) {
               gap("inventory-ownership-conflict")
            }
         }
         if (owner == "UNKNOWN") {
            unknown++
            gap("unknown-ownership")
         }
         key=type SUBSEP logical
         if (side == 1) {
            if (key in actual_object) { gap("duplicate-object"); return }
            actual_object[key]=1
            actual_type[key]=type; actual_logical[key]=logical; actual_physical[key]=physical
            actual_component[key]=component; actual_owner[key]=owner; actual_state[key]=state; actual_semantic[key]=canonical(semantic)
            print "OBJECT", type, logical, physical, component, owner, state, canonical(semantic) >> actual_full_file
            if (comparable(owner) && state == "ACTIVE") print "OBJECT", type, logical, component, owner, canonical(semantic) >> actual_owned_file
         } else {
            if (key in desired_object) { gap("duplicate-object"); return }
            desired_object[key]=1
            desired_type[key]=type; desired_logical[key]=logical; desired_physical[key]=physical
            desired_component[key]=component; desired_owner[key]=owner; desired_state[key]=state; desired_semantic[key]=canonical(semantic)
            print "OBJECT", type, logical, physical, component, owner, state, canonical(semantic) >> desired_full_file
            if (comparable(owner) && state == "ACTIVE") print "OBJECT", type, logical, component, owner, canonical(semantic) >> desired_owned_file
         }
      }
      function record_dns(side, field, value, owner, source, state, canonical_value) {
         if (!(field in dns_expected)) { dns_model_gap++; gap("unknown-dns-field"); unknown++; return }
         if (!valid_class(owner) || owner == "UNKNOWN") { dns_model_gap++; gap("unknown-dns-ownership"); unknown++; return }
         if (owner != dns_expected_owner[field]) { dns_model_gap++; gap("dns-ownership-conflict"); return }
         if (state != "ACTIVE" || !valid_token(source) || source == "-") { dns_model_gap++; gap("dns-source-missing"); return }
         canonical_value=dns_value(field, value)
         if (canonical_value == "") { dns_model_gap++; gap("dns-value-invalid"); return }
         if (side == 1) {
            if (field in actual_dns) { dns_model_gap++; gap("duplicate-dns-field"); return }
            actual_dns[field]=1; actual_dns_value[field]=canonical_value; actual_dns_owner[field]=owner; actual_dns_state[field]=state
            print "DNS", field, canonical_value, owner, state >> actual_full_file
            if (comparable(owner)) print "DNS", field, canonical_value, owner, state >> actual_owned_file
         } else {
            if (field in desired_dns) { dns_model_gap++; gap("duplicate-dns-field"); return }
            desired_dns[field]=1; desired_dns_value[field]=canonical_value; desired_dns_owner[field]=owner; desired_dns_state[field]=state
            print "DNS", field, canonical_value, owner, state >> desired_full_file
            if (comparable(owner)) print "DNS", field, canonical_value, owner, state >> desired_owned_file
         }
      }
      FILENAME == manifest_file {
         if (FNR == 1) {
            if ($0 != "OPENKILL_SHADOW_SEMANTIC_MANIFEST_V1=1") gap("manifest-header")
            next
         }
         if ($0 ~ /^[[:space:]]*$/ || $0 ~ /^#/) next
         if ($1 == "MODEL_VERSION" && NF == 2) { if ($2 != "1") gap("model-version"); next }
         if ($1 == "OWNERSHIP_CLASS" && NF == 2) { if ($2 in class_allowed) gap("duplicate-class"); class_allowed[$2]=1; next }
          if ($1 == "DNS_FIELD" && NF == 3) { if ($2 in dns_expected) gap("duplicate-dns-manifest"); dns_expected[$2]=1; dns_expected_owner[$2]=$3; next }
          if ($1 == "DNS_EXPECTED" && NF == 4 && ($2 in dns_expected) && valid_token($3) && valid_token($4)) {
             if ($2 in dns_expected_value) gap("duplicate-dns-expected")
             else { dns_expected_value[$2]=dns_value($2, $3); dns_expected_source[$2]=$4; if (dns_expected_value[$2] == "") gap("dns-expected-invalid") }
             next
          }
         if ($1 == "INVENTORY" && NF == 5 && $2 ~ /^(chain|set|attachment|rule)$/ && valid_token($3) && valid_class($4) && valid_token($5)) {
            inventory_key=$2 SUBSEP $3
            if (inventory_key in inventory_expected_owner) gap("duplicate-inventory")
            inventory_expected_owner[inventory_key]=$4
            inventory_expected_component[inventory_key]=$5
            next
         }
         gap("manifest-record-invalid")
         next
      }
      FILENAME == actual_file || FILENAME == desired_file {
         side=(FILENAME == actual_file ? 1 : 2)
         if (FNR == 1) {
            if ($0 != "OPENKILL_SHADOW_TYPED_INTENT_V1=1") gap("typed-header")
            next
         }
         if ($0 ~ /^[[:space:]]*$/ || $0 ~ /^#/) next
          if ($1 == "META") {
             if (NF != 3 || ($2 != "mode" && $2 != "model_version" && $2 != "schema_version" && $2 != "side" && $2 != "cycle_identity" && $2 != "continuity_identity" && $2 != "ownership_model_version" && $2 != "dns_model_version") || !valid_token($3)) gap("meta-record-invalid")
             else {
                meta_key=side SUBSEP $2
                if (meta_key in meta_value) gap("duplicate-meta-record")
                meta_value[meta_key]=$3
                if ($2 == "schema_version" || $2 == "side" || $2 == "cycle_identity" || $2 == "continuity_identity" || $2 == "ownership_model_version" || $2 == "dns_model_version") metadata_seen=1
             }
             next
          }
         if ($1 == "OBJECT") {
            if (NF != 8) { gap("object-record-width"); next }
            record_object(side, $2, $3, $4, $5, $6, $7, $8)
            next
         }
         if ($1 == "DNS") {
            if (NF != 6) { gap("dns-record-width"); next }
            record_dns(side, $2, $3, $4, $5, $6)
            next
         }
         gap("typed-record-invalid")
         next
      }
      END {
          if (metadata_seen) {
             # ``side`` is intentionally different between the two files;
             # compare the cycle/model identity fields across both sidecars
             # and validate the side labels separately below.
             required_meta="schema_version cycle_identity continuity_identity model_version ownership_model_version dns_model_version"
             meta_count=split(required_meta, meta_keys, " ")
             for (m=1; m<=meta_count; m++) {
                key=meta_keys[m]
                if (!(1 SUBSEP key in meta_value) || !(2 SUBSEP key in meta_value)) gap("metadata-missing")
                else if (meta_value[1 SUBSEP key] != meta_value[2 SUBSEP key]) gap("metadata-mismatch")
             }
             if ((1 SUBSEP "side" in meta_value && meta_value[1 SUBSEP "side"] != "ACTUAL") || (2 SUBSEP "side" in meta_value && meta_value[2 SUBSEP "side"] != "DESIRED") || !(1 SUBSEP "side" in meta_value) || !(2 SUBSEP "side" in meta_value)) gap("metadata-side-invalid")
          }
          dns_manifest_count=0
         for (field in dns_expected) {
            dns_manifest_count++
            if (!(field in actual_dns)) { dns_model_gap++; gap("dns-actual-missing") }
            if (!(field in desired_dns)) { dns_model_gap++; gap("dns-desired-missing") }
            if ((field in actual_dns) && (field in desired_dns)) {
               if (actual_dns_owner[field] != desired_dns_owner[field]) { dns_model_gap++; gap("dns-ownership-conflict") }
               else if (actual_dns_value[field] != desired_dns_value[field]) { mismatch++; dns_mismatch++ }
            }
         }
         if (dns_manifest_count != 8) { dns_model_gap++; gap("dns-manifest-incomplete") }
         for (key in actual_object) {
            if (!(key in desired_object)) {
               if (comparable(actual_owner[key]) && actual_state[key] == "ACTIVE") mismatch++
               else if (noncomparable(actual_owner[key])) out_of_scope++
               else gap("actual-object-ownership-unknown")
               continue
            }
            if (actual_owner[key] != desired_owner[key]) { gap("object-ownership-conflict"); continue }
            if (!valid_class(actual_owner[key])) { gap("object-class-invalid"); continue }
            if (actual_owner[key] == "UNKNOWN") { gap("unknown-ownership"); unknown++; continue }
            if (comparable(actual_owner[key])) {
               if (actual_state[key] != desired_state[key] || actual_component[key] != desired_component[key] || actual_semantic[key] != desired_semantic[key]) mismatch++
            } else out_of_scope++
         }
         for (key in desired_object) if (!(key in actual_object)) {
            if (comparable(desired_owner[key]) && desired_state[key] == "ACTIVE") mismatch++
         }
         if (model_gap > 0) result="MODEL_GAP"
         else if (mismatch > 0) result="MISMATCH"
         else result="MATCH"
         if (dns_model_gap > 0) dns_result="MODEL_GAP"
         else if (dns_mismatch > 0) dns_result="MISMATCH"
         else dns_result="MATCH"
         print "RESULT", result > summary_file
         print "DNS_RESULT", dns_result >> summary_file
         print "MISMATCH_COUNT", mismatch >> summary_file
         print "DNS_MISMATCH_COUNT", dns_mismatch >> summary_file
         print "MODEL_GAP_COUNT", model_gap >> summary_file
         print "OUT_OF_SCOPE_COUNT", out_of_scope >> summary_file
         print "UNKNOWN_COUNT", unknown >> summary_file
         print "REASON", (gap_reason == "" ? (mismatch > 0 ? "typed-semantic-diff" : "semantic-equivalent") : gap_reason) >> summary_file
      }
   ' "$openkill_shadow_typed_manifest" "$openkill_shadow_typed_actual" "$openkill_shadow_typed_desired" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"

   openkill_shadow_typed_result=$(awk -F '\t' '$1 == "RESULT" { print $2; exit }' "$openkill_shadow_typed_summary" 2>/dev/null || true)
   openkill_shadow_typed_dns_parity=$(awk -F '\t' '$1 == "DNS_RESULT" { print $2; exit }' "$openkill_shadow_typed_summary" 2>/dev/null || true)
   openkill_shadow_typed_mismatch_count=$(awk -F '\t' '$1 == "MISMATCH_COUNT" { print $2; exit }' "$openkill_shadow_typed_summary" 2>/dev/null || true)
   openkill_shadow_typed_model_gap_count=$(awk -F '\t' '$1 == "MODEL_GAP_COUNT" { print $2; exit }' "$openkill_shadow_typed_summary" 2>/dev/null || true)
   openkill_shadow_typed_out_of_scope_count=$(awk -F '\t' '$1 == "OUT_OF_SCOPE_COUNT" { print $2; exit }' "$openkill_shadow_typed_summary" 2>/dev/null || true)
   openkill_shadow_typed_unknown_count=$(awk -F '\t' '$1 == "UNKNOWN_COUNT" { print $2; exit }' "$openkill_shadow_typed_summary" 2>/dev/null || true)
   openkill_shadow_typed_reason=$(awk -F '\t' '$1 == "REASON" { print $2; exit }' "$openkill_shadow_typed_summary" 2>/dev/null || true)
   [ -n "$openkill_shadow_typed_result" ] || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   for openkill_shadow_typed_sort_pair in \
      "$openkill_shadow_typed_actual_full:$openkill_shadow_typed_work/actual.full.sorted" \
      "$openkill_shadow_typed_desired_full:$openkill_shadow_typed_work/desired.full.sorted" \
      "$openkill_shadow_typed_actual_owned:$openkill_shadow_typed_work/actual.owned.sorted" \
      "$openkill_shadow_typed_desired_owned:$openkill_shadow_typed_work/desired.owned.sorted"; do
      openkill_shadow_typed_sort_input=${openkill_shadow_typed_sort_pair%%:*}
      openkill_shadow_typed_sort_output=${openkill_shadow_typed_sort_pair#*:}
      openkill_shadow_safe_path "$openkill_shadow_typed_sort_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      LC_ALL=C sort "$openkill_shadow_typed_sort_input" > "$openkill_shadow_typed_sort_output" || return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   done
   openkill_shadow_typed_actual_owned_hash=$(openkill_shadow_hash_file "$openkill_shadow_typed_work/actual.owned.sorted" 2>/dev/null || true)
   openkill_shadow_typed_desired_owned_hash=$(openkill_shadow_hash_file "$openkill_shadow_typed_work/desired.owned.sorted" 2>/dev/null || true)
   openkill_shadow_typed_actual_full_hash=$(openkill_shadow_hash_file "$openkill_shadow_typed_work/actual.full.sorted" 2>/dev/null || true)
   openkill_shadow_typed_desired_full_hash=$(openkill_shadow_hash_file "$openkill_shadow_typed_work/desired.full.sorted" 2>/dev/null || true)
   openkill_shadow_typed_dns_actual_hash=$(awk -F '\t' '$1 == "DNS" { print; }' "$openkill_shadow_typed_actual_full" | LC_ALL=C sort | sha256sum 2>/dev/null | awk 'NR == 1 { print $1; exit }')
   openkill_shadow_typed_dns_desired_hash=$(awk -F '\t' '$1 == "DNS" { print; }' "$openkill_shadow_typed_desired_full" | LC_ALL=C sort | sha256sum 2>/dev/null | awk 'NR == 1 { print $1; exit }')
   case "$openkill_shadow_typed_result" in
      MATCH) openkill_shadow_typed_status=MATCH; return "$OPENKILL_NFT_SHADOW_RC_MATCH" ;;
      MISMATCH) openkill_shadow_typed_status=MISMATCH; return "$OPENKILL_NFT_SHADOW_RC_MISMATCH" ;;
      MODEL_GAP) openkill_shadow_typed_status=MODEL_GAP; return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP" ;;
      *) openkill_shadow_typed_status=MODEL_GAP; openkill_shadow_typed_reason=typed-result-invalid; return "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP" ;;
   esac
}

openkill_shadow_compare_auto_intent()
{
   # Compare the legacy runtime projection against the central desired batch.
   # The old writer is imperative and often omits an always-present empty-set
   # rule; therefore this is a directional semantic check: every captured old
   # object/action must be represented by the new desired state, while named
   # structural additions remain harmless.  Rule order is checked per chain.
   openkill_shadow_auto_old=$1
   openkill_shadow_auto_new=$2
   [ -r "$openkill_shadow_auto_old" ] && [ -r "$openkill_shadow_auto_new" ] || return 1
   awk '
      function canon(s) {
         gsub(/[[:space:]]+/, " ", s)
         gsub(/^ +| +$/, "", s)
         sub(/[[:space:]]+comment[[:space:]]+".*$/, "", s)
         gsub(/meta nfproto (ipv4|ipv6) /, "", s)
         gsub(/skgid == /, "meta skgid ", s)
         gsub(/(^| )counter( |$)/, " ", s)
         gsub(/(^| )mark set /, " meta mark set ", s)
         gsub(/(^| )ip protocol /, " meta l4proto ", s)
         gsub(/  +/, " ", s)
         gsub(/^ +| +$/, "", s)
         return s
      }
      # Backward-compatible raw fallback for pre-R3A callers.  Production
      # typed calls use formal ownership rows; this helper is never the typed
      # policy and physical names are not projected into CURRENT parity.
      function capture_raw_scope(name) { return name == "nat_output" || name ~ /^openkill/ }
      function add_new_rule(chain,s) { new_count[chain]++; new_rule[chain,new_count[chain]]=canon(s) }
      function add_old_rule(chain,s) { old_count[chain]++; old_rule[chain,old_count[chain]]=canon(s) }
      function set_elements(s,  x) {
         x=s
         if (x !~ /elements[[:space:]]*=[[:space:]]*\{/) return ""
         sub(/^.*elements[[:space:]]*=[[:space:]]*\{/, "", x)
         sub(/\}.*$/, "", x)
         gsub(/[[:space:]]+/, " ", x)
         gsub(/[[:space:]]*,[[:space:]]*/, ",", x)
         gsub(/^ +| +$/, "", x)
         return x
      }
      function same_set(a,b,  aa,bb,i,n,m,k) {
         n=split(a,aa,","); m=split(b,bb,",")
         delete left; delete right
         for (i=1; i<=n; i++) if (aa[i] != "") left[aa[i]]++
         for (i=1; i<=m; i++) if (bb[i] != "") right[bb[i]]++
         for (k in left) if (left[k] != right[k]) return 0
         for (k in right) if (right[k] != left[k]) return 0
         return 1
      }
      FNR==NR {
         line=$0
         if (line ~ /^add set /) {
            name=$5; new_set[name]=set_elements(line); next
         }
         if (line ~ /^add chain /) { new_chain[$5]=line; next }
         if (line ~ /^add rule /) { add_new_rule($5, substr(line, index(line,$6))); next }
         next
      }
      {
         line=$0
         if (line ~ /^add set /) { name=$5; old_set[name]=set_elements(line); old_set_seen[name]=1; next }
         if (line ~ /^add chain /) {
            name=$5
            if (capture_raw_scope(name)) old_chain[name]=1
            if (capture_raw_scope(name) && match(line, /type[[:space:]]+nat[[:space:]]+hook[[:space:]]+output[[:space:]]+priority[[:space:]]+-?[0-9]+/)) {
               old_hook[name]=line
               old_hook_priority[name]=substr(line, RSTART, RLENGTH)
               sub(/^.*priority[[:space:]]+/, "", old_hook_priority[name])
            }
            next
         }
         if (line ~ /^add rule /) { add_old_rule($5, substr(line, index(line,$6))); next }
      }
      END {
         for (name in old_chain) if (!(name in new_chain)) bad=1
         for (name in old_hook) if (old_hook_priority[name] != "-1" || !(name in new_chain) || new_chain[name] !~ /type nat hook output priority[[:space:]]+-1/) bad=1
         for (name in old_set_seen) if (!(name in new_set) || !same_set(old_set[name], new_set[name])) bad=1
         for (chain in old_count) {
            cursor=1
            for (i=1; i<=old_count[chain]; i++) {
               found=0
               for (j=cursor; j<=new_count[chain]; j++) if (old_rule[chain,i] == new_rule[chain,j]) { found=1; cursor=j+1; break }
               if (!found) bad=1
            }
         }
         exit bad ? 1 : 0
      }
   ' "$openkill_shadow_auto_new" "$openkill_shadow_auto_old"
}

openkill_shadow_run_renderer()
{
   openkill_shadow_renderer=${OPENKILL_NFT_SHADOW_RENDERER:-$OPENKILL_NFT_SHADOW_RENDERER_DEFAULT}
   openkill_shadow_renderer_input=$1
   openkill_shadow_renderer_output=$2
   openkill_shadow_safe_value "$openkill_shadow_renderer" || return "$OPENKILL_NFT_SHADOW_RC_INPUT"
   [ -r "$openkill_shadow_renderer" ] || return "$OPENKILL_NFT_SHADOW_RC_RENDER"
   openkill_shadow_timeout=${OPENKILL_NFT_SHADOW_TIMEOUT:-$OPENKILL_NFT_SHADOW_TIMEOUT_DEFAULT}
   case "$openkill_shadow_timeout" in ''|*[!0-9]*) return 124 ;; esac
   [ "$openkill_shadow_timeout" -ge 1 ] 2>/dev/null && [ "$openkill_shadow_timeout" -le 60 ] 2>/dev/null || return 124
   # Close the historical rc.common lock descriptor in the child only.  The
   # caller keeps its own descriptor and lock untouched.  BusyBox
   # ash accepts the numeric descriptor syntax; Debian dash treats it as a
   # command and exits, so probe the child shell in a separate process and
   # omit the close operation when that syntax is unavailable.
   command -v timeout >/dev/null 2>&1 || return 124
   openkill_shadow_close_fd=0
   if sh -c 'exec 1000>&-' >/dev/null 2>&1; then
      openkill_shadow_close_fd=1
   fi
   if [ "$openkill_shadow_close_fd" -eq 1 ]; then
      openkill_shadow_child='exec 1000>&-; exec sh "$1" "$2" "$3"'
      timeout "$openkill_shadow_timeout" sh -c "$openkill_shadow_child" sh \
         "$openkill_shadow_renderer" \
         "$openkill_shadow_renderer_input" "$openkill_shadow_renderer_output"
   else
      timeout "$openkill_shadow_timeout" sh "$openkill_shadow_renderer" \
         "$openkill_shadow_renderer_input" "$openkill_shadow_renderer_output"
   fi
}

openkill_shadow_compare_nft()
(
   openkill_shadow_enabled || exit 0

   openkill_shadow_state_file=${OPENKILL_NFT_SHADOW_STATE_FILE-}
   openkill_shadow_explicit_bundle=0
   [ -n "$openkill_shadow_state_file" ] && openkill_shadow_explicit_bundle=1
   [ -n "${OPENKILL_NFT_SHADOW_INPUT_FILE:-}" ] && openkill_shadow_explicit_bundle=1
   # An absent bundle is the normal 3E.1 runtime path.  Do not fall back to a
   # stale /tmp/openkill-shadow/state file left by an earlier test invocation.
   openkill_shadow_telemetry_dir=${OPENKILL_NFT_SHADOW_TELEMETRY_DIR:-$OPENKILL_NFT_SHADOW_TELEMETRY_DEFAULT}
   openkill_shadow_safe_value "$openkill_shadow_telemetry_dir" || exit "$OPENKILL_NFT_SHADOW_RC_INPUT"
   openkill_shadow_old_hash_for_log=-
   openkill_shadow_new_hash_for_log=-
   openkill_shadow_generation_for_log=-
   openkill_shadow_continuity_token_value=
   openkill_shadow_auto_continuity_mode=0
   openkill_shadow_inventory_missing_count=0
   openkill_shadow_required_missing_count=0
   openkill_shadow_conditional_missing_count=0
   openkill_shadow_inactive_missing_count=0
   openkill_shadow_optional_missing_count=0
   openkill_shadow_out_of_scope_missing_count=0
   openkill_shadow_unknown_count=0
   openkill_shadow_typed_actual_owned_hash=
   openkill_shadow_typed_desired_owned_hash=
   openkill_shadow_typed_dns_actual_hash=
   openkill_shadow_typed_dns_desired_hash=
   openkill_shadow_typed_model_gap_count=0
   openkill_shadow_typed_mismatch_count=0
   openkill_shadow_typed_out_of_scope_count=0
   openkill_shadow_typed_unknown_count=0
   openkill_shadow_typed_dns_parity=NOT_RUN
   openkill_shadow_typed_status=NOT_RUN
   openkill_shadow_typed_requested=0
   openkill_shadow_typed_auto=0
   [ -n "${OPENKILL_NFT_SHADOW_TYPED_ACTUAL_FILE:-}" ] && openkill_shadow_typed_requested=1
   [ -n "${OPENKILL_NFT_SHADOW_TYPED_DESIRED_FILE:-}" ] && openkill_shadow_typed_requested=1
   openkill_shadow_tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/openkill-shadow.XXXXXX" 2>/dev/null) || {
      openkill_shadow_publish INPUT_ERROR - - - temp-directory-failed || true
      exit "$OPENKILL_NFT_SHADOW_RC_INPUT"
   }
   trap 'rm -rf "$openkill_shadow_tmp_dir"' EXIT HUP INT TERM

   if [ "$openkill_shadow_explicit_bundle" -eq 1 ]; then
      openkill_shadow_load_state "$openkill_shadow_state_file" || {
         openkill_shadow_publish INPUT_ERROR - - - state-unavailable || true
         exit "$OPENKILL_NFT_SHADOW_RC_INPUT"
      }
   else
      openkill_shadow_auto_mode=1
      openkill_shadow_auto_prepare "$openkill_shadow_tmp_dir"
      openkill_shadow_auto_prepare_rc=$?
      if [ "$openkill_shadow_auto_prepare_rc" -ne 0 ]; then
         openkill_shadow_auto_status=INPUT_SOURCE_GAP
         [ "$openkill_shadow_auto_prepare_rc" -eq "$OPENKILL_NFT_SHADOW_RC_INPUT" ] && openkill_shadow_auto_status=INPUT_ERROR
         [ "$openkill_shadow_auto_prepare_rc" -eq "$OPENKILL_NFT_SHADOW_RC_UNSUPPORTED" ] && openkill_shadow_auto_status=UNSUPPORTED_CURRENT_STATE
         [ "$openkill_shadow_auto_prepare_rc" -eq "$OPENKILL_NFT_SHADOW_RC_STALE" ] && openkill_shadow_auto_status=STALE
         [ "$openkill_shadow_auto_prepare_rc" -eq "$OPENKILL_NFT_SHADOW_RC_COMPARE" ] && openkill_shadow_auto_status=COMPARE_ERROR
         openkill_shadow_log_bounded "$openkill_shadow_auto_status" - - automatic-state-source || true
         openkill_shadow_publish "$openkill_shadow_auto_status" - - - automatic-state-source || true
         exit "$openkill_shadow_auto_prepare_rc"
      fi
   fi
   # Automatic production mode is self-contained.  Explicit sidecars are an
   # additive fixture/development interface for explicit-bundle invocations;
   # an automatic cycle must never accept caller-provided evidence.
   if [ "${openkill_shadow_auto_mode:-0}" -eq 1 ] &&
      { [ -n "${OPENKILL_NFT_SHADOW_TYPED_ACTUAL_FILE:-}" ] || [ -n "${OPENKILL_NFT_SHADOW_TYPED_DESIRED_FILE:-}" ]; }; then
      openkill_shadow_publish MODEL_GAP - - "$openkill_shadow_generation_for_log" external-typed-sidecar-disallowed || true
      exit "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   fi
   if [ "${openkill_shadow_auto_mode:-0}" -eq 1 ] &&
      [ -z "${OPENKILL_NFT_SHADOW_TYPED_ACTUAL_FILE:-}" ] &&
      [ -z "${OPENKILL_NFT_SHADOW_TYPED_DESIRED_FILE:-}" ] &&
      [ "${OPENKILL_NFT_SHADOW_AUTO_TYPED:-$OPENKILL_NFT_SHADOW_AUTO_TYPED_DEFAULT}" = 1 ]; then
      openkill_shadow_typed_requested=1
      openkill_shadow_typed_auto=1
   fi
   if [ "${openkill_shadow_auto_mode:-0}" -eq 1 ] && [ "${openkill_shadow_auto_continuity_mode:-0}" -eq 1 ]; then
      openkill_shadow_generation_for_log=${openkill_shadow_continuity_token_value:-}
      [ -n "$openkill_shadow_generation_for_log" ] || {
         openkill_shadow_publish INPUT_SOURCE_GAP - - - continuity-token-unavailable || true
         exit "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      }
   else
      openkill_shadow_generation_for_log=$(openkill_shadow_read_generation 2>/dev/null) || {
         if [ "${openkill_shadow_auto_mode:-0}" -eq 1 ]; then
            openkill_shadow_publish INPUT_SOURCE_GAP - - - generation-unavailable || true
            exit "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
         fi
         openkill_shadow_publish INPUT_ERROR - - - generation-unavailable || true
         exit "$OPENKILL_NFT_SHADOW_RC_INPUT"
      }
   fi

   # Do not rerun a successful comparison for an unchanged generation unless
   # an internal test explicitly requests it.  Mismatch statuses remain
   # visible and are deduplicated by the bounded telemetry key.
   if [ "${OPENKILL_NFT_SHADOW_FORCE:-0}" != 1 ] &&
      [ -r "$openkill_shadow_telemetry_dir/status" ] &&
      grep -Eq '^status=MATCH$' "$openkill_shadow_telemetry_dir/status" &&
       grep -Fq "generation=$(openkill_shadow_generation_telemetry_value "$openkill_shadow_generation_for_log")" "$openkill_shadow_telemetry_dir/status"; then
      exit 0
   fi

   if ! openkill_shadow_source_drift_ok; then
      openkill_shadow_log_bounded SOURCE_DRIFT - - source-hash-mismatch
      openkill_shadow_publish SOURCE_DRIFT - - "$openkill_shadow_generation_for_log" source-hash-mismatch || true
      exit "$OPENKILL_NFT_SHADOW_RC_SOURCE_DRIFT"
   fi

   openkill_shadow_input_tmp="$openkill_shadow_tmp_dir/input.tsv"
   openkill_shadow_build_input "$openkill_shadow_input_file" "$openkill_shadow_input_tmp"
   openkill_shadow_input_rc=$?
   if [ "$openkill_shadow_input_rc" -ne 0 ]; then
      openkill_shadow_input_status=INPUT_ERROR
      [ "$openkill_shadow_input_rc" -eq "$OPENKILL_NFT_SHADOW_RC_UNSUPPORTED" ] && openkill_shadow_input_status=UNSUPPORTED_CURRENT_STATE
      openkill_shadow_log_bounded "$openkill_shadow_input_status" - - input-boundary
      openkill_shadow_publish "$openkill_shadow_input_status" - - "$openkill_shadow_generation_for_log" input-boundary || true
      exit "$openkill_shadow_input_rc"
   fi

   openkill_shadow_owner=$(awk -F '\t' '$1 == "META" && $2 == "owner" { print $3; exit }' "$openkill_shadow_input_tmp") || true
   case "$openkill_shadow_owner" in
      MIHOMO|DISABLED)
         openkill_shadow_publish DISABLED - - "$openkill_shadow_generation_for_log" owner-not-openkill || true
         exit 0
      ;;
      OPENKILL) ;;
      *)
         openkill_shadow_publish INPUT_ERROR - - "$openkill_shadow_generation_for_log" owner-unknown || true
         exit "$OPENKILL_NFT_SHADOW_RC_INPUT"
      ;;
   esac

   if [ "${openkill_shadow_auto_mode:-0}" -eq 1 ]; then
      openkill_shadow_capture_raw="$openkill_shadow_tmp_dir/legacy.capture"
      openkill_shadow_capture_intent="$openkill_shadow_tmp_dir/legacy.intent"
      openkill_shadow_capture_payload="$openkill_shadow_tmp_dir/legacy.nft"
      openkill_shadow_capture_legacy_nft "$openkill_shadow_capture_raw"
      openkill_shadow_capture_rc=$?
      case "$openkill_shadow_capture_rc" in
         "$OPENKILL_NFT_SHADOW_RC_CAPTURE_UNAVAILABLE") openkill_shadow_capture_status=CAPTURE_UNAVAILABLE ;;
         "$OPENKILL_NFT_SHADOW_RC_CAPTURE_UNSUPPORTED") openkill_shadow_capture_status=CAPTURE_UNSUPPORTED ;;
         0) openkill_shadow_capture_status= ;;
         *) openkill_shadow_capture_status=CAPTURE_ERROR ;;
      esac
      if [ -n "$openkill_shadow_capture_status" ]; then
         openkill_shadow_log_bounded "$openkill_shadow_capture_status" - - legacy-capture || true
         openkill_shadow_publish "$openkill_shadow_capture_status" - - "$openkill_shadow_generation_for_log" legacy-capture || true
         exit "$openkill_shadow_capture_rc"
      fi
      openkill_shadow_parse_nft_capture "$openkill_shadow_capture_raw" "$openkill_shadow_capture_intent" "$openkill_shadow_capture_payload"
      openkill_shadow_parse_rc=$?
      case "$openkill_shadow_parse_rc" in
         "$OPENKILL_NFT_SHADOW_RC_CAPTURE_UNSUPPORTED") openkill_shadow_capture_status=CAPTURE_UNSUPPORTED ;;
         0) openkill_shadow_capture_status= ;;
         *) openkill_shadow_capture_status=CAPTURE_ERROR ;;
      esac
      if [ -n "$openkill_shadow_capture_status" ]; then
         openkill_shadow_log_bounded "$openkill_shadow_capture_status" - - legacy-parse || true
         openkill_shadow_publish "$openkill_shadow_capture_status" - - "$openkill_shadow_generation_for_log" legacy-parse || true
         exit "$openkill_shadow_parse_rc"
      fi
      # Missing records are classified from the formal CURRENT inventory
      # schema.  Only REQUIRED_CURRENT (or an unknown/duplicate record) is a
      # capture failure; conditional, inactive, optional, and out-of-scope
      # absences remain bounded diagnostic evidence and may reach compare.
      openkill_shadow_classify_inventory_missing "$openkill_shadow_capture_intent" "$openkill_shadow_input_tmp"
      openkill_shadow_inventory_classify_rc=$?
      if [ "$openkill_shadow_inventory_classify_rc" -ne 0 ]; then
         openkill_shadow_publish CAPTURE_ERROR - - "$openkill_shadow_generation_for_log" "${openkill_shadow_inventory_error_reason:-inventory-classification}" || true
         exit "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
      fi
      openkill_shadow_old_intent_file=$openkill_shadow_capture_payload
      openkill_shadow_old_intent_hash=
   fi

    # Explicit typed bundles are copied into the private cycle directory before
    # rendering/comparison.  Automatic mode instead creates both sidecars from
    # the frozen capture/input after the renderer succeeds; no caller-provided
    # sidecar is accepted as the production automatic source.
    if [ "$openkill_shadow_typed_requested" -eq 1 ] && [ "$openkill_shadow_typed_auto" -eq 0 ]; then
      [ -n "${OPENKILL_NFT_SHADOW_TYPED_ACTUAL_FILE:-}" ] &&
         [ -n "${OPENKILL_NFT_SHADOW_TYPED_DESIRED_FILE:-}" ] || {
         openkill_shadow_publish MODEL_GAP - - "$openkill_shadow_generation_for_log" typed-input-pair-missing || true
         exit "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      }
      openkill_shadow_typed_actual_file=$openkill_shadow_tmp_dir/typed-actual.tsv
      openkill_shadow_typed_desired_file=$openkill_shadow_tmp_dir/typed-desired.tsv
      openkill_shadow_typed_prepare_file "$OPENKILL_NFT_SHADOW_TYPED_ACTUAL_FILE" "$openkill_shadow_typed_actual_file" || {
         openkill_shadow_publish MODEL_GAP - - "$openkill_shadow_generation_for_log" typed-actual-unavailable || true
         exit "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      }
      openkill_shadow_typed_prepare_file "$OPENKILL_NFT_SHADOW_TYPED_DESIRED_FILE" "$openkill_shadow_typed_desired_file" || {
         openkill_shadow_publish MODEL_GAP - - "$openkill_shadow_generation_for_log" typed-desired-unavailable || true
         exit "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      }
   fi

   openkill_shadow_new_payload="$openkill_shadow_tmp_dir/new.nft"
   openkill_shadow_run_renderer "$openkill_shadow_input_tmp" "$openkill_shadow_new_payload"
   openkill_shadow_render_rc=$?
   if [ "$openkill_shadow_render_rc" -ne 0 ]; then
      openkill_shadow_render_status=RENDER_ERROR
      [ "$openkill_shadow_render_rc" -eq "$OPENKILL_NFT_SHADOW_RC_INPUT" ] && openkill_shadow_render_status=INPUT_ERROR
      [ "$openkill_shadow_render_rc" -eq 65 ] && openkill_shadow_render_status=UNSUPPORTED_CURRENT_STATE
      [ "$openkill_shadow_render_rc" -eq 66 ] && openkill_shadow_render_status=UNSUPPORTED_CURRENT_STATE
      if [ "$openkill_shadow_render_rc" -eq 124 ] || [ "$openkill_shadow_render_rc" -eq 137 ]; then
         openkill_shadow_render_status=COMPARE_ERROR
      fi
      openkill_shadow_log_bounded "$openkill_shadow_render_status" - - renderer-failed
      openkill_shadow_publish "$openkill_shadow_render_status" - - "$openkill_shadow_generation_for_log" renderer-failed || true
      [ "$openkill_shadow_render_status" = INPUT_ERROR ] && exit "$OPENKILL_NFT_SHADOW_RC_INPUT"
      [ "$openkill_shadow_render_status" = COMPARE_ERROR ] && exit "$OPENKILL_NFT_SHADOW_RC_COMPARE"
      [ "$openkill_shadow_render_status" = UNSUPPORTED_CURRENT_STATE ] && exit "$OPENKILL_NFT_SHADOW_RC_UNSUPPORTED"
      exit "$OPENKILL_NFT_SHADOW_RC_RENDER"
   fi
   [ -r "$openkill_shadow_new_payload" ] || {
      openkill_shadow_publish RENDER_ERROR - - "$openkill_shadow_generation_for_log" renderer-output-missing || true
      exit "$OPENKILL_NFT_SHADOW_RC_RENDER"
   }
   openkill_shadow_new_size=$(wc -c < "$openkill_shadow_new_payload") || openkill_shadow_new_size=0
    [ "$openkill_shadow_new_size" -le "$OPENKILL_NFT_SHADOW_MAX_PAYLOAD_BYTES" ] || {
      openkill_shadow_publish RENDER_ERROR - - "$openkill_shadow_generation_for_log" payload-too-large || true
      exit "$OPENKILL_NFT_SHADOW_RC_RENDER"
   }
   if [ "$openkill_shadow_typed_auto" -eq 1 ]; then
      openkill_shadow_typed_actual_file=$openkill_shadow_tmp_dir/typed-actual.tsv
      openkill_shadow_typed_desired_file=$openkill_shadow_tmp_dir/typed-desired.tsv
      openkill_shadow_typed_auto_produce "$openkill_shadow_capture_intent" "$openkill_shadow_input_tmp" "$openkill_shadow_new_payload" "$openkill_shadow_typed_actual_file" "$openkill_shadow_typed_desired_file" || {
         openkill_shadow_typed_reason=typed-sidecar-producer-gap
         openkill_shadow_log_bounded MODEL_GAP - - "$openkill_shadow_typed_reason"
         openkill_shadow_publish MODEL_GAP - - "$openkill_shadow_generation_for_log" "$openkill_shadow_typed_reason" || true
         exit "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
      }
   fi
   openkill_shadow_new_normalized="$openkill_shadow_tmp_dir/new.normalized"
   openkill_shadow_normalize_payload "$openkill_shadow_new_payload" "$openkill_shadow_new_normalized" || {
      openkill_shadow_publish COMPARE_ERROR - - "$openkill_shadow_generation_for_log" new-normalization-failed || true
      exit "$OPENKILL_NFT_SHADOW_RC_COMPARE"
   }
   openkill_shadow_new_hash=$(openkill_shadow_hash_file "$openkill_shadow_new_normalized" 2>/dev/null || true)
   openkill_shadow_new_hash_for_log=${openkill_shadow_new_hash:--}

   openkill_shadow_old_normalized="$openkill_shadow_tmp_dir/old.normalized"
   if [ -n "$openkill_shadow_old_intent_file" ] && [ -r "$openkill_shadow_old_intent_file" ]; then
      openkill_shadow_old_size=$(wc -c < "$openkill_shadow_old_intent_file") || openkill_shadow_old_size=$((OPENKILL_NFT_SHADOW_MAX_PAYLOAD_BYTES + 1))
      [ "$openkill_shadow_old_size" -le "$OPENKILL_NFT_SHADOW_MAX_PAYLOAD_BYTES" ] || {
         openkill_shadow_publish INPUT_ERROR - "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" old-payload-too-large || true
         exit "$OPENKILL_NFT_SHADOW_RC_INPUT"
      }
      openkill_shadow_normalize_payload "$openkill_shadow_old_intent_file" "$openkill_shadow_old_normalized" || {
         openkill_shadow_publish INPUT_ERROR - "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" old-normalization-failed || true
         exit "$OPENKILL_NFT_SHADOW_RC_INPUT"
      }
      openkill_shadow_old_hash_from_file=$(openkill_shadow_hash_file "$openkill_shadow_old_normalized" 2>/dev/null || true)
      if [ -n "$openkill_shadow_old_intent_hash" ] && [ -n "$openkill_shadow_old_hash_from_file" ] &&
         [ "$openkill_shadow_old_intent_hash" != "$openkill_shadow_old_hash_from_file" ]; then
         openkill_shadow_publish INPUT_ERROR "$openkill_shadow_old_hash_from_file" "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" old-hash-invalid || true
         exit "$OPENKILL_NFT_SHADOW_RC_INPUT"
      fi
      openkill_shadow_old_intent_hash=${openkill_shadow_old_hash_from_file:-$openkill_shadow_old_intent_hash}
   fi
   if [ -n "$openkill_shadow_old_intent_hash" ] && [ ! -r "$openkill_shadow_old_intent_file" ]; then
      openkill_shadow_valid_hash "$openkill_shadow_old_intent_hash" || {
         openkill_shadow_log_bounded INPUT_ERROR - "$openkill_shadow_new_hash_for_log" invalid-old-hash
         openkill_shadow_publish INPUT_ERROR - "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" invalid-old-hash || true
         exit "$OPENKILL_NFT_SHADOW_RC_INPUT"
      }
   fi
   openkill_shadow_old_hash_for_log=${openkill_shadow_old_intent_hash:--}
   if [ -z "$openkill_shadow_old_intent_hash" ]; then
      openkill_shadow_publish INPUT_ERROR - "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" old-intent-missing || true
      exit "$OPENKILL_NFT_SHADOW_RC_INPUT"
   fi

   if [ "$openkill_shadow_typed_requested" -eq 1 ]; then
      openkill_shadow_compare_typed_intent "$openkill_shadow_typed_actual_file" "$openkill_shadow_typed_desired_file" "$openkill_shadow_tmp_dir"
      openkill_shadow_compare_rc=$?
   elif [ "${openkill_shadow_auto_mode:-0}" -eq 1 ]; then
      if openkill_shadow_compare_auto_intent "$openkill_shadow_old_intent_file" "$openkill_shadow_new_payload"; then
         openkill_shadow_compare_rc=$OPENKILL_NFT_SHADOW_RC_MATCH
      else
         openkill_shadow_compare_rc=$OPENKILL_NFT_SHADOW_RC_MISMATCH
      fi
   elif [ -r "$openkill_shadow_old_normalized" ]; then
      if ! cmp -s "$openkill_shadow_old_normalized" "$openkill_shadow_new_normalized"; then
         openkill_shadow_compare_rc=$OPENKILL_NFT_SHADOW_RC_MISMATCH
      else
         openkill_shadow_compare_rc=$OPENKILL_NFT_SHADOW_RC_MATCH
      fi
   elif [ -n "$openkill_shadow_new_hash" ]; then
      [ "$openkill_shadow_old_intent_hash" = "$openkill_shadow_new_hash" ] && openkill_shadow_compare_rc=$OPENKILL_NFT_SHADOW_RC_MATCH || openkill_shadow_compare_rc=$OPENKILL_NFT_SHADOW_RC_MISMATCH
   else
      openkill_shadow_publish COMPARE_ERROR "$openkill_shadow_old_hash_for_log" - "$openkill_shadow_generation_for_log" hash-tool-unavailable || true
      exit "$OPENKILL_NFT_SHADOW_RC_COMPARE"
   fi

   if [ "${openkill_shadow_auto_mode:-0}" -eq 1 ] && [ "${openkill_shadow_auto_continuity_mode:-0}" -eq 1 ]; then
      # T2 is always computed from the original live paths.  The renderer and
      # capture consumed only the private snapshot above; any committed-state
      # or runtime-DNS change during those operations wins over a provisional
      # MATCH.  DNS is re-sampled only at this boundary and never by the
      # typed producer/comparator.
      openkill_shadow_auto_continuity_dns_check \
         "$openkill_shadow_continuity_state_dir/runtime-dns" \
         "$openkill_shadow_continuity_state_dir" t2 || {
            openkill_shadow_log_bounded STALE "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" continuity-dns-changed
            openkill_shadow_publish STALE "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" continuity-dns-changed || true
            exit "$OPENKILL_NFT_SHADOW_RC_STALE"
         }
      openkill_shadow_continuity_t2_work=$openkill_shadow_tmp_dir/t2
      openkill_shadow_continuity_t2_file=$openkill_shadow_tmp_dir/t2.token
      openkill_shadow_auto_continuity_token "$openkill_shadow_continuity_t2_file" "$openkill_shadow_continuity_t2_work" \
         "$openkill_shadow_continuity_live_desired" "$openkill_shadow_continuity_live_applied" \
         "$openkill_shadow_continuity_live_snapshot" "$openkill_shadow_continuity_live_node4" "$openkill_shadow_continuity_live_node6" \
         "$openkill_shadow_continuity_state_dir/dns-t2/runtime-dns" > "$openkill_shadow_tmp_dir/t2.stdout" 2>/dev/null || {
            openkill_shadow_log_bounded STALE "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" continuity-token-unavailable
            openkill_shadow_publish STALE "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" continuity-token-unavailable || true
            exit "$OPENKILL_NFT_SHADOW_RC_STALE"
         }
      openkill_shadow_continuity_t2_value=$(sed -n '1p' "$openkill_shadow_continuity_t2_file" 2>/dev/null || true)
      if [ -z "$openkill_shadow_continuity_t2_value" ] || [ "$openkill_shadow_continuity_t2_value" != "$openkill_shadow_generation_for_log" ]; then
         openkill_shadow_log_bounded STALE "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" continuity-token-changed
         openkill_shadow_publish STALE "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" continuity-token-changed || true
         exit "$OPENKILL_NFT_SHADOW_RC_STALE"
      fi
   else
      openkill_shadow_generation_after=$(openkill_shadow_read_generation 2>/dev/null || true)
      if [ -z "$openkill_shadow_generation_after" ] || [ "$openkill_shadow_generation_after" != "$openkill_shadow_generation_for_log" ]; then
         openkill_shadow_log_bounded STALE "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" generation-changed
         openkill_shadow_publish STALE "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" generation-changed || true
         exit "$OPENKILL_NFT_SHADOW_RC_STALE"
      fi
      # When an explicit canonical source supplied GENERATION, compare that
      # source as well as the temporary G1 copy.  This closes the race where a
      # fixture/control-plane writer changes its source after auto_prepare; a
      # test renderer may also mutate the temporary copy to model the same race.
      if [ "${openkill_shadow_auto_mode:-0}" -eq 1 ]; then
         openkill_shadow_generation_source_after=
         if [ -n "${openkill_shadow_auto_generation_source_file:-}" ]; then
            openkill_shadow_auto_lookup_result=
            if openkill_shadow_auto_lookup_file GENERATION "$openkill_shadow_auto_generation_source_file" >/dev/null 2>&1; then
               openkill_shadow_generation_source_after=$openkill_shadow_auto_lookup_result
            fi
            if [ -z "$openkill_shadow_generation_source_after" ] || [ "$openkill_shadow_generation_source_after" != "$openkill_shadow_generation_for_log" ]; then
               openkill_shadow_log_bounded STALE "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" source-generation-changed
               openkill_shadow_publish STALE "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" source-generation-changed || true
               exit "$OPENKILL_NFT_SHADOW_RC_STALE"
            fi
         fi
         if [ -n "${openkill_shadow_generation_file:-}" ] && [ -r "$openkill_shadow_generation_file" ]; then
            openkill_shadow_generation_temp_after=$(sed -n '1p' "$openkill_shadow_generation_file" 2>/dev/null || true)
            if [ -z "$openkill_shadow_generation_temp_after" ] || [ "$openkill_shadow_generation_temp_after" != "$openkill_shadow_generation_for_log" ]; then
               openkill_shadow_log_bounded STALE "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" temp-generation-changed
               openkill_shadow_publish STALE "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" temp-generation-changed || true
               exit "$OPENKILL_NFT_SHADOW_RC_STALE"
            fi
         fi
      fi
   fi
   if [ "$openkill_shadow_compare_rc" -eq "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP" ]; then
      openkill_shadow_log_bounded MODEL_GAP "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" "${openkill_shadow_typed_reason:-semantic-model-incomplete}"
      # Keep mismatch_count about semantic differences; model gaps have their
      # own bounded model_gap_count telemetry field.
      openkill_shadow_publish MODEL_GAP "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" "${openkill_shadow_typed_reason:-semantic-model-incomplete}" "${openkill_shadow_typed_mismatch_count:-0}" || true
      exit "$OPENKILL_NFT_SHADOW_RC_MODEL_GAP"
   fi
   if [ "$openkill_shadow_compare_rc" -eq "$OPENKILL_NFT_SHADOW_RC_MATCH" ]; then
      openkill_shadow_publish MATCH "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" semantic-equivalent 0 || true
      exit 0
   fi
   openkill_shadow_log_bounded MISMATCH "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" semantic-intent-diff
   openkill_shadow_publish MISMATCH "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" semantic-intent-diff "${openkill_shadow_typed_mismatch_count:-1}" || true
   exit "$OPENKILL_NFT_SHADOW_RC_MISMATCH"
)
