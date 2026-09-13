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
   if [ -z "$openkill_shadow_state_file" ] && [ -z "${OPENKILL_NFT_SHADOW_INPUT_FILE:-}" ]; then
      openkill_shadow_state_file=$OPENKILL_NFT_SHADOW_STATE_DEFAULT
   fi
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

   openkill_shadow_load_state "$openkill_shadow_state_file" || {
      openkill_shadow_publish INPUT_ERROR - - - state-unavailable || true
      exit "$OPENKILL_NFT_SHADOW_RC_INPUT"
   }
   openkill_shadow_generation_for_log=$(openkill_shadow_read_generation 2>/dev/null) || {
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

   if [ -r "$openkill_shadow_old_normalized" ]; then
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
   if [ "$openkill_shadow_compare_rc" -eq "$OPENKILL_NFT_SHADOW_RC_MATCH" ]; then
      openkill_shadow_publish MATCH "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" semantic-equivalent 0 || true
      exit 0
   fi
   openkill_shadow_log_bounded MISMATCH "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" semantic-intent-diff
   openkill_shadow_publish MISMATCH "$openkill_shadow_old_hash_for_log" "$openkill_shadow_new_hash_for_log" "$openkill_shadow_generation_for_log" semantic-intent-diff 1 || true
   exit "$OPENKILL_NFT_SHADOW_RC_MISMATCH"
)
