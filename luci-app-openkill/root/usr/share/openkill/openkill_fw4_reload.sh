#!/bin/sh
# Called by fw4's include hook.  Interface creation/removal invokes fw4 reload;
# modifying nftables synchronously inside that same reload races fw4 and can
# leave OpenKill without DNS or transparent-proxy rules.  Coalesce events and
# restore OpenKill rules only after fw4 has finished its own transaction.

LOCK_DIR="/tmp/lock/openkill-fw4-reload.lock"
PENDING_FILE="/tmp/openkill-fw4-reload.pending"

[ -x /etc/init.d/openkill ] || exit 0
mkdir -p /tmp/lock 2>/dev/null || exit 0
touch "$PENDING_FILE"
mkdir "$LOCK_DIR" 2>/dev/null || exit 0

(
    # fw4 invokes this hook while rc.common may hold its lifecycle lock on
    # fd 1000.  The worker has its own mkdir lock and must never inherit the
    # service lock into a background process.
    exec 1000>&-
    # Let the triggering fw4 transaction and any rapid interface events settle.
    sleep 3
    passes=0
    while [ -f "$PENDING_FILE" ] && [ "$passes" -lt 3 ]; do
        rm -f "$PENDING_FILE"
        # A fresh OpenKill start creates this token before it prepares the fw4
        # include.  Do not let that include's own reload interrupt the start
        # that created it; it would remove just-installed DNS/TUN rules before
        # readiness can inspect them.
        if [ -s /tmp/openkill-start.token ] && [ ! -s /tmp/openkill-ready.token ]; then
            rmdir "$LOCK_DIR" 2>/dev/null || true
            exit 0
        fi
        # fw4 may still be settling after an interface transaction. Retry the
        # lightweight rule reconcile a bounded number of times; never leave a
        # previously enabled service stopped merely because one reload raced.
        for attempt in 1 2 3; do
            /etc/init.d/openkill reload "firewall-deferred" >/dev/null 2>&1 && break
            sleep 2
        done
        if [ "$(uci -q get openkill.config.enable 2>/dev/null)" = "1" ] &&
           ! ubus call service list '{"name":"openkill"}' 2>/dev/null |
             jsonfilter -e '@.openkill.instances.*.running' | grep -q 'true'; then
            # Let procd remain the sole process owner. start is safe here
            # because the running-state check prevents duplicate instances.
            /etc/init.d/openkill start >/dev/null 2>&1 || true
        fi
        passes=$((passes + 1))
        [ -f "$PENDING_FILE" ] && sleep 1
    done
    rmdir "$LOCK_DIR" 2>/dev/null || true
) </dev/null >/dev/null 2>&1 &

exit 0
