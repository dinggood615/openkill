#!/bin/sh
# Independent, low-frequency observer. procd owns process respawn; maintenance
# work cannot block this loop. Persistent API failures are recorded, not hidden.
. /usr/share/openkill/runtime.sh
. /usr/share/openkill/log.sh
failures=0
while :; do
    token=$(cat /tmp/openkill-start.token 2>/dev/null)
    ready=$(cat /tmp/openkill-ready.token 2>/dev/null)
    if [ -n "$token" ] && [ "$ready" = "$token" ]; then
        if openkill_core_process_present && openkill_core_api_healthy; then
            failures=0
        else
            failures=$((failures + 1))
            if [ "$failures" -eq 3 ]; then
                LOG_ERROR "OpenKill runtime health failed for three checks; inspect controller and core logs."
            fi
        fi
    else
        failures=0
    fi
    sleep 60
done
