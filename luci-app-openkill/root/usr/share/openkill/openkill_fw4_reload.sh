#!/bin/sh
# Called by fw4's include hook.  Interface creation/removal invokes fw4 reload;
# modifying nftables synchronously inside that same reload races fw4 and can
# leave OpenKill without DNS or transparent-proxy rules.  Coalesce events and
# restore OpenKill rules only after fw4 has finished its own transaction.

LOCK_DIR="${OPENKILL_FW4_LOCK_DIR:-/tmp/lock/openkill-fw4-reload.lock}"
NETWORK_STATE_DIR="${OPENKILL_FW4_STATE_DIR:-/tmp/openkill-network-reconcile}"
PENDING_FILE="$NETWORK_STATE_DIR/pending"
OPENKILL_INIT_SERVICE="${OPENKILL_FW4_INIT_SERVICE:-/etc/init.d/openkill}"
OPENKILL_NETWORK_HELPER="${OPENKILL_NETWORK_HELPER:-/usr/share/openkill/openkill_network.sh}"
OPENKILL_START_TOKEN_FILE="${OPENKILL_START_TOKEN_FILE:-/tmp/openkill-start.token}"
OPENKILL_READY_TOKEN_FILE="${OPENKILL_READY_TOKEN_FILE:-/tmp/openkill-ready.token}"
SETTLE_DELAY="${OPENKILL_FW4_SETTLE_DELAY:-3}"
RETRY_DELAY="${OPENKILL_FW4_RETRY_DELAY:-2}"
PENDING_DELAY="${OPENKILL_FW4_PENDING_DELAY:-1}"

[ -r "$OPENKILL_NETWORK_HELPER" ] && . "$OPENKILL_NETWORK_HELPER"

[ -x "$OPENKILL_INIT_SERVICE" ] || exit 0
mkdir -p "$(dirname "$LOCK_DIR")" "$NETWORK_STATE_DIR" 2>/dev/null || exit 0
if [ -n "$(command -v openkill_request_network_reconcile 2>/dev/null)" ]; then
    openkill_request_network_reconcile "$NETWORK_STATE_DIR" fw4-reload ||
        openkill_reconcile_request_pending "$PENDING_FILE" 2>/dev/null || : > "$PENDING_FILE"
else
    : > "$PENDING_FILE"
fi
mkdir "$LOCK_DIR" 2>/dev/null || exit 0

(
    # fw4 invokes this hook while rc.common may hold its lifecycle lock on
    # fd 1000.  The worker has its own mkdir lock and must never inherit the
    # service lock into a background process.
    # BusyBox ash and bash accept closing the rc.common descriptor directly.
    # Debian dash treats a multi-digit redirection as a command name and exits
    # the worker, so probe the shell syntax in a child before applying it here.
    if (eval 'exec 1000>&-') 2>/dev/null; then
        eval 'exec 1000>&-'
    fi
    # Let the triggering fw4 transaction and any rapid interface events settle.
    sleep "$SETTLE_DELAY"
    passes=0
    while [ -f "$PENDING_FILE" ] && [ "$passes" -lt 3 ]; do
        rm -f "$PENDING_FILE"
        # A fresh OpenKill start creates this token before it prepares the fw4
        # include.  Do not let that include's own reload interrupt the start
        # that created it; it would remove just-installed DNS/TUN rules before
        # readiness can inspect them.
        if [ -s "$OPENKILL_START_TOKEN_FILE" ] && [ ! -s "$OPENKILL_READY_TOKEN_FILE" ]; then
            rmdir "$LOCK_DIR" 2>/dev/null || true
            exit 0
        fi
        # fw4 may still be settling after an interface transaction. Retry the
        # lightweight rule reconcile a bounded number of times; never leave a
        # previously enabled service stopped merely because one reload raced.
        reload_ok=0
        for attempt in 1 2 3; do
            "$OPENKILL_INIT_SERVICE" reload "firewall-deferred" >/dev/null 2>&1 && {
                reload_ok=1
                break
            }
            sleep "$RETRY_DELAY"
        done
        [ "$reload_ok" -eq 1 ] ||
            openkill_reconcile_request_pending "$PENDING_FILE" 2>/dev/null || : > "$PENDING_FILE"
        if [ "$(uci -q get openkill.config.enable 2>/dev/null)" = "1" ] &&
           ! ubus call service list '{"name":"openkill"}' 2>/dev/null |
             jsonfilter -e '@.openkill.instances.*.running' | grep -q 'true'; then
            # Let procd remain the sole process owner. start is safe here
            # because the running-state check prevents duplicate instances.
            "$OPENKILL_INIT_SERVICE" start >/dev/null 2>&1 || true
        fi
        passes=$((passes + 1))
        [ -f "$PENDING_FILE" ] && sleep "$PENDING_DELAY"
    done
    rmdir "$LOCK_DIR" 2>/dev/null || true
) </dev/null >/dev/null 2>&1 &

exit 0
