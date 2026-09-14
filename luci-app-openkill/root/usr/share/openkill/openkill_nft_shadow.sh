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
         openkill_shadow_auto_node_file=/tmp/openkill-node4.desired
         [ "$openkill_shadow_auto_key" = NODE6_ENDPOINTS ] && openkill_shadow_auto_node_file=/tmp/openkill-node6.desired
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
      GENERATION) openkill_shadow_auto_value=${OPENKILL_NFT_SHADOW_GENERATION:-} ;;
      IPV6_READY) openkill_shadow_auto_value=${OPENKILL_IPV6_READY:-} ;;
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

openkill_shadow_auto_owner()
{
   openkill_shadow_auto_field OWNER TUN_OWNER || return 1
   openkill_shadow_auto_owner_value=$(printf '%s' "$openkill_shadow_auto_field_value" | tr '[:lower:]' '[:upper:]')
   case "$openkill_shadow_auto_owner_value" in OPENKILL|MIHOMO|DISABLED|UNKNOWN) ;; *) return 1 ;; esac
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
   if openkill_shadow_auto_source_path >/dev/null 2>&1; then
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
            openkill_shadow_auto_unsupported_value=$(printf '%s' "$openkill_shadow_auto_value" | tr '[:lower:]' '[:upper:]')
            case "$openkill_shadow_auto_unsupported_value" in
               1|YES|TRUE|ACTIVE|UNSUPPORTED|REQUIRED)
                  return "$OPENKILL_NFT_SHADOW_RC_UNSUPPORTED"
               ;;
            esac
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
   openkill_shadow_auto_run_mode=$(printf '%s' "$openkill_shadow_auto_field_value" | tr '[:lower:]' '[:upper:]')
   case "$openkill_shadow_auto_run_mode" in TUN|TPROXY|REDIRECT) ;; *) return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP" ;; esac
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
   openkill_shadow_auto_field GENERATION || {
      openkill_shadow_auto_generation_file=${OPENKILL_NFT_SHADOW_GENERATION_FILE:-/tmp/openkill-network-reconcile/generation}
      openkill_shadow_safe_path "$openkill_shadow_auto_generation_file" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      [ -r "$openkill_shadow_auto_generation_file" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      openkill_shadow_auto_field_value=$(sed -n '1p' "$openkill_shadow_auto_generation_file") || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   }
   openkill_shadow_auto_generation=$openkill_shadow_auto_field_value
   openkill_shadow_safe_value "$openkill_shadow_auto_generation" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"

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
      if command "$openkill_shadow_capture_nft" list chain inet fw4 "$openkill_shadow_capture_chain" > "$openkill_shadow_capture_one" 2>/dev/null; then
         printf 'OBJECT\tchain\t%s\n' "$openkill_shadow_capture_chain" >> "$openkill_shadow_capture_tmp"
         cat "$openkill_shadow_capture_one" >> "$openkill_shadow_capture_tmp"
         printf 'OBJECT_END\n' >> "$openkill_shadow_capture_tmp"
         [ -z "$openkill_shadow_capture_trace" ] || printf 'chain %s rc=0\n' "$openkill_shadow_capture_chain" >> "$openkill_shadow_capture_trace"
      else
         printf 'MISSING\tchain\t%s\n' "$openkill_shadow_capture_chain" >> "$openkill_shadow_capture_tmp"
         [ -z "$openkill_shadow_capture_trace" ] || printf 'chain %s rc=1\n' "$openkill_shadow_capture_chain" >> "$openkill_shadow_capture_trace"
      fi
      rm -f "$openkill_shadow_capture_one"
   done
   for openkill_shadow_capture_set in $openkill_shadow_capture_set_list; do
      openkill_shadow_capture_name_ok "$openkill_shadow_capture_set" || { rm -f "$openkill_shadow_capture_tmp"; return "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"; }
      openkill_shadow_capture_any=1
      openkill_shadow_capture_one=${openkill_shadow_capture_output}.one.$$
      if command "$openkill_shadow_capture_nft" list set inet fw4 "$openkill_shadow_capture_set" > "$openkill_shadow_capture_one" 2>/dev/null; then
         printf 'OBJECT\tset\t%s\n' "$openkill_shadow_capture_set" >> "$openkill_shadow_capture_tmp"
         cat "$openkill_shadow_capture_one" >> "$openkill_shadow_capture_tmp"
         printf 'OBJECT_END\n' >> "$openkill_shadow_capture_tmp"
         [ -z "$openkill_shadow_capture_trace" ] || printf 'set %s rc=0\n' "$openkill_shadow_capture_set" >> "$openkill_shadow_capture_trace"
      else
         printf 'MISSING\tset\t%s\n' "$openkill_shadow_capture_set" >> "$openkill_shadow_capture_tmp"
         [ -z "$openkill_shadow_capture_trace" ] || printf 'set %s rc=1\n' "$openkill_shadow_capture_set" >> "$openkill_shadow_capture_trace"
      fi
      rm -f "$openkill_shadow_capture_one"
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
   # surfaced as CAPTURE_UNSUPPORTED instead of being dropped.
   awk -v OFS='\t' '
      function trim(s) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", s); return s }
      function owned(n) { return n == "nat_output" || n ~ /^openkill/ }
      function base(n) { return n == "dstnat" || n == "mangle_prerouting" || n == "mangle_output" || n == "output" || n == "srcnat" || n == "input" || n == "forward" }
      function known_rule(s) {
         return s ~ /(^|[[:space:]])return([[:space:]]|$)/ ||
                s ~ /(^|[[:space:]])jump[[:space:]]+openkill[_A-Za-z0-9]*([[:space:]]|$)/ ||
                s ~ /meta[[:space:]]+mark[[:space:]]+set[[:space:]]+0x[0-9A-Fa-f]+/ ||
                s ~ /(^|[[:space:]])tproxy([[:space:]]|$)/ ||
                s ~ /(^|[[:space:]])redirect([[:space:]]|$)/ ||
                s ~ /(^|[[:space:]])accept([[:space:]]|$)/ ||
                (s ~ /(^|[[:space:]])counter([[:space:]]|$)/ &&
                 s ~ /(meta[[:space:]]|ip[46]?[[:space:]]|tcp[[:space:]]|udp[[:space:]]|ether[[:space:]]|iifname[[:space:]]|oifname[[:space:]])/)
      }
      function clean_rule(s) {
         s=trim(s)
         sub(/[[:space:]]+#?[[:space:]]*handle[[:space:]]+[0-9]+[[:space:]]*$/, "", s)
         sub(/[[:space:]]+counter[[:space:]]+packets[[:space:]]+[0-9]+[[:space:]]+bytes[[:space:]]+[0-9]+/, "", s)
         sub(/[[:space:]]+comment[[:space:]]+"[^"]*"/, "", s)
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
            if (owned(chain) && match(line, /type[[:space:]]+nat[[:space:]]+hook[[:space:]]+output[[:space:]]+priority[[:space:]]+-?[0-9]+/)) {
               openkill_hook=substr(line, RSTART, RLENGTH)
               sub(/^.*priority[[:space:]]+/, "", openkill_hook)
               print "HOOK", chain, "nat", "output", openkill_hook
            }
            next
         }
         if (owned(chain) && match(line, /^type[[:space:]]+nat[[:space:]]+hook[[:space:]]+output[[:space:]]+priority[[:space:]]+-?[0-9]+/)) {
            openkill_hook=substr(line, RSTART, RLENGTH)
            sub(/^.*priority[[:space:]]+/, "", openkill_hook)
            print "HOOK", chain, "nat", "output", openkill_hook
            next
         }
         line=clean_rule(line)
         if (line == "") next
         if (base(chain) && line !~ /(^|[[:space:]])jump[[:space:]]+openkill[_A-Za-z0-9]*/) next
         if (owned(chain) && !known_rule(line)) { print "UNKNOWN_OWNED_RULE", chain, line; unknown=1; next }
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
   openkill_shadow_input_file=$openkill_shadow_auto_prepare_dir/auto-input.tsv
   openkill_shadow_safe_path "$openkill_shadow_input_file" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   openkill_shadow_build_auto_input "$openkill_shadow_input_file"
   openkill_shadow_auto_prepare_rc=$?
   [ "$openkill_shadow_auto_prepare_rc" -eq 0 ] || return "$openkill_shadow_auto_prepare_rc"
   openkill_shadow_auto_field GENERATION >/dev/null 2>&1
   if [ "$?" -eq 0 ]; then
      openkill_shadow_generation=$openkill_shadow_auto_field_value
      openkill_shadow_generation_file=$openkill_shadow_auto_prepare_dir/auto-generation
      # Keep the canonical source visible for the end-of-run race check.  The
      # temporary copy is still used for the first read so the comparison has
      # a stable G1 snapshot; the source is read again before publishing.
      openkill_shadow_auto_generation_source_file=${openkill_shadow_auto_source_file:-}
      printf '%s\n' "$openkill_shadow_generation" > "$openkill_shadow_generation_file" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
   else
      openkill_shadow_generation_file=${OPENKILL_NFT_SHADOW_GENERATION_FILE:-/tmp/openkill-network-reconcile/generation}
      openkill_shadow_safe_path "$openkill_shadow_generation_file" || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      [ -r "$openkill_shadow_generation_file" ] || return "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      openkill_shadow_generation=
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
      printf 'generation=%s\n' "$openkill_shadow_generation_value"
      printf 'reason=%s\n' "$openkill_shadow_reason_value"
      printf 'mismatch_count=%s\n' "$openkill_shadow_mismatch_value"
   ) > "$openkill_shadow_tmp" && mv -f "$openkill_shadow_tmp" "$openkill_shadow_dir/status" || {
      rm -f "$openkill_shadow_tmp"
      return 1
   }
   # Keep a bounded dedupe key for mismatch diagnostics.  This is telemetry,
   # never applied state, and contains no addresses, domains, or credentials.
   case "$openkill_shadow_status_value" in
      MISMATCH|COMPARE_ERROR|RENDER_ERROR|INPUT_ERROR|SOURCE_DRIFT|STALE|UNSUPPORTED_CURRENT_STATE)
         printf '%s\n' "$openkill_shadow_status_value:$openkill_shadow_old_value:$openkill_shadow_new_value:$openkill_shadow_generation_value" > "$openkill_shadow_dir/last_mismatch.tmp.$$" &&
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
      openkill_shadow_log_key="$openkill_shadow_log_status:$openkill_shadow_log_old:$openkill_shadow_log_new:${openkill_shadow_generation_for_log:--}"
      if [ -r "$openkill_shadow_log_dir/last_mismatch" ] &&
         [ "$(sed -n '1p' "$openkill_shadow_log_dir/last_mismatch" 2>/dev/null)" = "$openkill_shadow_log_key" ]; then
         return 0
      fi
      LOG_WARN "OpenKill shadow ${openkill_shadow_log_status} old=$(openkill_shadow_short_hash "$openkill_shadow_log_old") new=$(openkill_shadow_short_hash "$openkill_shadow_log_new") reason=${openkill_shadow_log_reason}"
   fi
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
      function owned_chain(name) { return name == "nat_output" || name ~ /^openkill/ }
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
            if (owned_chain(name)) old_chain[name]=1
            if (owned_chain(name) && match(line, /type[[:space:]]+nat[[:space:]]+hook[[:space:]]+output[[:space:]]+priority[[:space:]]+-?[0-9]+/)) {
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
         openkill_shadow_log_bounded "$openkill_shadow_auto_status" - - automatic-state-source || true
         openkill_shadow_publish "$openkill_shadow_auto_status" - - - automatic-state-source || true
         exit "$openkill_shadow_auto_prepare_rc"
      fi
   fi
   openkill_shadow_generation_for_log=$(openkill_shadow_read_generation 2>/dev/null) || {
      if [ "${openkill_shadow_auto_mode:-0}" -eq 1 ]; then
         openkill_shadow_publish INPUT_SOURCE_GAP - - - generation-unavailable || true
         exit "$OPENKILL_NFT_SHADOW_RC_SOURCE_GAP"
      fi
      openkill_shadow_publish INPUT_ERROR - - - generation-unavailable || true
      exit "$OPENKILL_NFT_SHADOW_RC_INPUT"
   }

   # Do not rerun a successful comparison for an unchanged generation unless
   # an internal test explicitly requests it.  Mismatch statuses remain
   # visible and are deduplicated by the bounded telemetry key.
   if [ "${OPENKILL_NFT_SHADOW_FORCE:-0}" != 1 ] &&
      [ -r "$openkill_shadow_telemetry_dir/status" ] &&
      grep -Eq '^status=MATCH$' "$openkill_shadow_telemetry_dir/status" &&
      grep -Fq "generation=$openkill_shadow_generation_for_log" "$openkill_shadow_telemetry_dir/status"; then
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
      # A required object that disappeared during a bounded read is not an
      # empty object.  Partial capture can never produce a false MATCH.
      if grep -Eq '^MISSING[[:space:]]' "$openkill_shadow_capture_intent"; then
         openkill_shadow_publish CAPTURE_ERROR - - "$openkill_shadow_generation_for_log" required-object-missing || true
         exit "$OPENKILL_NFT_SHADOW_RC_CAPTURE_ERROR"
      fi
      openkill_shadow_old_intent_file=$openkill_shadow_capture_payload
      openkill_shadow_old_intent_hash=
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

   if [ "${openkill_shadow_auto_mode:-0}" -eq 1 ]; then
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
   if [ "$openkill_shadow_compare_rc" -eq "$OPENKILL_NFT_SHADOW_RC_MATCH" ]; then
      openkill_shadow_publish MATCH "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" semantic-equivalent 0 || true
      exit 0
   fi
   openkill_shadow_log_bounded MISMATCH "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" semantic-intent-diff
   openkill_shadow_publish MISMATCH "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" semantic-intent-diff 1 || true
   exit "$OPENKILL_NFT_SHADOW_RC_MISMATCH"
)
