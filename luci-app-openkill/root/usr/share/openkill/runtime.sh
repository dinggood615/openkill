#!/bin/sh
# Shared runtime helpers.  Keep process and controller detection in one place
# so LuCI, init and watchdog do not disagree about whether Mihomo is ready.

. /usr/share/openkill/uci.sh 2>/dev/null || true

openkill_core_pids() {
    local name pids
    for name in clash mihomo clash_meta; do
        pids="$(pidof "$name" 2>/dev/null || true)"
        [ -n "$pids" ] && printf '%s\n' "$pids"
    done | awk '{$1=$1; print}' | tr '\n' ' ' | sed 's/[[:space:]]*$//'
}

openkill_core_process_present() {
    [ -n "$(openkill_core_pids)" ]
}

openkill_controller_port() {
    local port
    port="$(uci_get_config "cn_port" 2>/dev/null || true)"
    case "$port" in
        ''|*[!0-9]*) port=9090 ;;
    esac
    [ "$port" -ge 1 ] 2>/dev/null && [ "$port" -le 65535 ] 2>/dev/null || port=9090
    printf '%s' "$port"
}

openkill_controller_host() {
    local requested host
    requested="$(uci_get_config "dashboard_bind_address" 2>/dev/null || echo lan)"
    case "$requested" in
        lan)
            host="$(uci -q get network.lan.ipaddr 2>/dev/null | awk -F/ '{print $1}')"
            [ -n "$host" ] || host=127.0.0.1
            ;;
        0.0.0.0) host=127.0.0.1 ;;
        \[*\]) host="${requested#\[}"; host="${host%\]}" ;;
        *) host="$requested" ;;
    esac
    printf '%s' "$host"
}

openkill_controller_url() {
    local host port
    host="$(openkill_controller_host)"
    port="$(openkill_controller_port)"
    case "$host" in
        *:*) printf 'http://[%s]:%s' "$host" "$port" ;;
        *) printf 'http://%s:%s' "$host" "$port" ;;
    esac
}

openkill_core_api_healthy() {
    local url secret code
    url="$(openkill_controller_url)/version"
    secret="$(uci_get_config "dashboard_password" 2>/dev/null || true)"
    if [ -n "$secret" ]; then
        code="$(curl -k -sS -m 3 -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $secret" "$url" 2>/dev/null || true)"
    else
        code="$(curl -k -sS -m 3 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
    fi
    [ "$code" = 200 ]
}

openkill_core_ready() {
    openkill_core_api_healthy
}
