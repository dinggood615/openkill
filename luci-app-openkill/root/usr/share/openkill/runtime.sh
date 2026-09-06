#!/bin/sh
# Shared runtime helpers.  Keep process and controller detection in one place
# so LuCI, init and watchdog do not disagree about whether Mihomo is ready.

. /usr/share/openkill/uci.sh 2>/dev/null || true
. /usr/share/openkill/address.sh

openkill_core_pids() {
    local pid expected config args executable
    expected="$(readlink -f /etc/openkill/clash 2>/dev/null)"
    config="${CONFIG_FILE:-/etc/openkill/$(basename "$(uci_get_config config_path 2>/dev/null)")}"
    ubus call service list '{"name":"openkill"}' 2>/dev/null |
        jsonfilter -e '@.openkill.instances.openkill.pid' 2>/dev/null |
        while read -r pid; do
            case "$pid" in ''|*[!0-9]*) continue ;; esac
            executable="$(readlink -f "/proc/$pid/exe" 2>/dev/null)"
            [ -n "$expected" ] && [ "$executable" = "$expected" ] || continue
            args="$(tr '\000' '\n' < "/proc/$pid/cmdline" 2>/dev/null)"
            printf '%s\n' "$args" | grep -Fxq -- "$config" && printf '%s\n' "$pid"
        done
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
    local requested
    requested="$(uci_get_config "dashboard_bind_address" 2>/dev/null || echo lan)"
    openkill_local_address "$requested"
}

# Read the actual generated config, including user overrides. Cache within
# this process only and invalidate on file replacement/modification.
openkill_load_context() {
    local file stamp data
    file="${CONFIG_FILE:-/etc/openkill/$(basename "$(uci_get_config config_path 2>/dev/null)")}"
    [ -s "$file" ] || return 1
    stamp="$(stat -c '%i:%Y:%s' "$file" 2>/dev/null)"
    if [ -n "$stamp" ] && [ "${OPENKILL_CONTEXT_KEY:-}" = "$file:$stamp" ]; then return 0; fi
    data="$(ruby /usr/share/openkill/runtime_context.rb "$file" 2>/dev/null)" || return 1
    OPENKILL_API_ENDPOINT="$(printf '%s\n' "$data" | sed -n '1p')"
    OPENKILL_API_SECRET="$(printf '%s\n' "$data" | sed -n '2p')"
    OPENKILL_TUN_DEVICE="$(printf '%s\n' "$data" | sed -n '3p')"
    OPENKILL_TUN_TABLE="$(printf '%s\n' "$data" | sed -n '4p')"
    OPENKILL_DNS_ENDPOINT="$(printf '%s\n' "$data" | sed -n '5p')"
    OPENKILL_CONTEXT_KEY="$file:$stamp"
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
    local url secret code response body
    openkill_load_context || return 1
    url="$OPENKILL_API_ENDPOINT/version"
    secret="$OPENKILL_API_SECRET"
    if [ -n "$secret" ]; then
        response="$(curl --noproxy '*' -sS -m 3 --max-filesize 16384 -w '\n%{http_code}' -H "Authorization: Bearer $secret" "$url" 2>/dev/null)" || return 1
    else
        response="$(curl --noproxy '*' -sS -m 3 --max-filesize 16384 -w '\n%{http_code}' "$url" 2>/dev/null)" || return 1
    fi
    code="$(printf '%s\n' "$response" | tail -n 1)"
    body="$(printf '%s\n' "$response" | sed '$d')"
    [ "$code" = 200 ] && [ -n "$(printf '%s' "$body" | jsonfilter -e '@.version' 2>/dev/null)" ]
}

openkill_core_ready() {
    openkill_core_process_present && openkill_core_api_healthy
}

openkill_dns_listener_present() {
    local port="$1" table
    for table in /proc/net/udp /proc/net/udp6; do
        [ -r "$table" ] || continue
        if awk -v port="$port" 'BEGIN {p=sprintf(":%04X", port)} $2 ~ p"$" {found=1} END {exit !found}' "$table"; then
            return 0
        fi
    done
    return 1
}
