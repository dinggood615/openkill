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
    # Let the triggering fw4 transaction and any rapid interface events settle.
    sleep 3
    if [ -f "$PENDING_FILE" ]; then
        rm -f "$PENDING_FILE"
        /etc/init.d/openkill reload "firewall-deferred" >/dev/null 2>&1 || true
    fi
    rmdir "$LOCK_DIR" 2>/dev/null || true
) </dev/null >/dev/null 2>&1 &

exit 0
