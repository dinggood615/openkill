#!/bin/sh
# Independent NaiveProxy bridge.
#
# This library deliberately has no UCI dependency and never reads or writes
# /etc/config/openkill.  Nodes are user-owned JSON files under
# /etc/naiveproxy/nodes; OpenKill only consumes the redacted manifest produced
# by the commands below.

umask 077

NP_ROOT="${NAIVEPROXY_ROOT:-/etc/naiveproxy}"
NP_NODE_DIR="${NAIVEPROXY_NODE_DIR:-$NP_ROOT/nodes}"
NP_RUN="${NAIVEPROXY_RUN:-/var/run/naiveproxy}"
NP_CONFIG_DIR="$NP_RUN/config"
NP_STATE_DIR="$NP_RUN/state"
NP_PORT_MAP="$NP_ROOT/ports"
NP_BIN="${NAIVEPROXY_BIN:-$NP_ROOT/naive}"
NP_TARGET="${NAIVEPROXY_HEALTH_TARGET:-https://www.gstatic.com/generate_204}"
NP_TIMEOUT="${NAIVEPROXY_HEALTH_TIMEOUT:-8}"
NP_PORT_BASE="${NAIVEPROXY_PORT_BASE:-11080}"
NP_PORT_LIMIT=100
NP_HEALTH_LOCK="$NP_RUN/health.lock"

np_safe() { printf '%s' "$1" | tr '\r\n|=' '    ' | cut -c1-160; }
np_valid_id() { case "$1" in ''|*[!A-Za-z0-9_-]*) return 1 ;; esac; }
np_valid_port() { case "$1" in ''|*[!0-9]*) return 1 ;; esac; [ "$1" -ge 1 ] 2>/dev/null && [ "$1" -le 65535 ] 2>/dev/null; }
np_enabled() { case "$1" in 1|true|yes|on) return 0 ;; esac; return 1; }

np_dirs() {
    mkdir -p "$NP_NODE_DIR" "$NP_CONFIG_DIR" "$NP_STATE_DIR" || return 1
    chmod 700 "$NP_ROOT" "$NP_NODE_DIR" "$NP_RUN" "$NP_CONFIG_DIR" "$NP_STATE_DIR" 2>/dev/null || true
}

np_json() {
    command -v jsonfilter >/dev/null 2>&1 || return 1
    jsonfilter -i "$1" -e "@.$2" 2>/dev/null
}

np_node_file() {
    np_valid_id "$1" || return 1
    printf '%s/%s.json\n' "$NP_NODE_DIR" "$1"
}

np_node_value() {
    local file="$1" key="$2" value
    value=$(np_json "$file" "$key" 2>/dev/null || true)
    np_safe "$value"
}

np_ids() {
    np_dirs >/dev/null 2>&1 || return 1
    for file in "$NP_NODE_DIR"/*.json; do
        [ -f "$file" ] || continue
        id=${file##*/}; id=${id%.json}
        np_valid_id "$id" && printf '%s\n' "$id"
    done
}

np_urlencode() {
    local value="$1" out="" i c hex length
    LC_ALL=C
    length=${#value}; i=1
    while [ "$i" -le "$length" ]; do
        c=$(printf '%s' "$value" | cut -b "$i")
        case "$c" in
            [A-Za-z0-9._~-]) out="${out}${c}" ;;
            *) hex=$(printf '%s' "$c" | od -An -tx1 2>/dev/null | tr -d ' \n\r'); [ -n "$hex" ] || return 1; out="${out}%${hex}" ;;
        esac
        i=$((i + 1))
    done
    printf '%s' "$out"
}

np_port() {
    local id="$1" line port
    np_valid_id "$id" || return 1
    np_dirs || return 1
    touch "$NP_PORT_MAP" || return 1
    chmod 600 "$NP_PORT_MAP" 2>/dev/null || true
    line=$(grep -m1 "^${id} " "$NP_PORT_MAP" 2>/dev/null || true)
    if [ -n "$line" ]; then
        port=${line#* }
        np_valid_port "$port" && printf '%s\n' "$port" && return 0
    fi
    port="$NP_PORT_BASE"
    while [ "$port" -lt $((NP_PORT_BASE + NP_PORT_LIMIT)) ]; do
        if ! grep -q " $port$" "$NP_PORT_MAP" 2>/dev/null; then
            printf '%s %s\n' "$id" "$port" >> "$NP_PORT_MAP" || return 1
            printf '%s\n' "$port"
            return 0
        fi
        port=$((port + 1))
    done
    return 1
}

np_probe_component() {
    [ -x "$NP_BIN" ] || return 1
    "$NP_BIN" --version >/dev/null 2>&1
}

np_health_begin() {
    np_dirs || return 1
    mkdir "$NP_HEALTH_LOCK" 2>/dev/null || return 1
    printf '%s\n' "$$" > "$NP_HEALTH_LOCK/pid"
}

np_health_end() { rm -rf "$NP_HEALTH_LOCK" 2>/dev/null || true; }

np_listener() {
    local port="$1"
    np_valid_port "$port" || return 1
    if command -v ss >/dev/null 2>&1; then
        ss -lnt 2>/dev/null | grep -qE "127[.]0[.]0[.]1:${port}[[:space:]]" && return 0
    fi
    if command -v netstat >/dev/null 2>&1; then
        netstat -lnt 2>/dev/null | grep -qE "127[.]0[.]0[.]1:${port}[[:space:]]" && return 0
    fi
    return 1
}

np_pid_for_config() {
    local config="$1" proc cmd
    for proc in /proc/[0-9]*; do
        [ -r "$proc/cmdline" ] || continue
        cmd=$(tr '\000' ' ' < "$proc/cmdline" 2>/dev/null || true)
        case "$cmd" in *"$config"*) printf '%s\n' "${proc##*/}"; return 0 ;; esac
    done
    return 1
}

np_prepare() {
    local id="$1" file port server remote_port user pass transport host eu ep config tmp
    file=$(np_node_file "$id") || return 1
    [ -r "$file" ] || return 1
    port=$(np_port "$id") || return 1
    server=$(np_node_value "$file" server); remote_port=$(np_node_value "$file" port)
    user=$(np_json "$file" username 2>/dev/null || true); pass=$(np_json "$file" password 2>/dev/null || true)
    transport=$(np_node_value "$file" transport); [ -n "$transport" ] || transport=https
    np_valid_port "$remote_port" || return 1
    [ -n "$server" ] && [ -n "$user" ] && [ -n "$pass" ] || return 1
    case "$transport" in tls|https) transport=https ;; quic) ;; *) return 1 ;; esac
    eu=$(np_urlencode "$user") || return 1; ep=$(np_urlencode "$pass") || return 1
    host="$server"
    case "$host" in *:*|'['*) case "$host" in \[*\]) ;; *) host="[$host]" ;; esac ;; esac
    config="$NP_CONFIG_DIR/$id.json"; tmp="$config.new.$$"
    printf '{\n  "listen": "socks://127.0.0.1:%s",\n  "proxy": "%s://%s:%s@%s:%s"\n}\n' \
        "$port" "$transport" "$eu" "$ep" "$host" "$remote_port" > "$tmp" || return 1
    chmod 600 "$tmp" || return 1
    mv -f "$tmp" "$config" || return 1
    printf '%s\n' "$config"
}

np_health_one() {
    local id="$1" file port output code seconds now old_fail status reason latency state
    file=$(np_node_file "$id") || return 1
    [ -r "$file" ] || return 1
    port=$(np_port "$id") || return 1
    now=$(date +%s); old_fail=$(sed -n 's/^fail_count=//p' "$NP_STATE_DIR/health.$id" 2>/dev/null | head -n1)
    case "$old_fail" in ''|*[!0-9]*) old_fail=0 ;; esac
    if ! np_enabled "$(np_node_value "$file" enabled)"; then status=disabled; reason=node-disabled; latency=unknown
    elif ! np_probe_component; then status=component-missing; reason=component-not-executable; latency=unknown
    elif ! np_prepare "$id" >/dev/null; then status=config-invalid; reason=node-config-invalid; latency=unknown
    elif ! np_listener "$port"; then status=local-not-ready; reason=loopback-listener-not-ready; latency=unknown
    elif ! command -v curl >/dev/null 2>&1; then status=probe-failed; reason=curl-missing; latency=unknown
    else
        output=$(curl --proxy "socks5h://127.0.0.1:${port}" --noproxy '' --connect-timeout 3 --max-time "$NP_TIMEOUT" --max-redirs 0 --proto '=https' -sS -o /dev/null -w '%{http_code}\t%{time_total}' "$NP_TARGET" 2>/dev/null || true)
        code=$(printf '%s' "$output" | cut -f1); seconds=$(printf '%s' "$output" | cut -f2)
        case "$code" in
            2??) latency=$(awk -v s="$seconds" 'BEGIN { if (s !~ /^[0-9.]+$/) exit 1; printf "%d", s * 1000 + 0.5 }' 2>/dev/null || true); status=available; reason=probe-ok ;;
            401|407) latency=unknown; status=probe-failed; reason=remote-auth-failed ;;
            *) latency=unknown; status=probe-failed; reason=https-probe-failed ;;
        esac
    fi
    case "$status" in available) old_fail=0 ;; disabled) ;; *) old_fail=$((old_fail + 1)) ;; esac
    [ -n "$latency" ] || latency=unknown
    {
        printf 'status=%s\n' "$status"; printf 'latency_ms=%s\n' "$latency"; printf 'checked_at=%s\n' "$now"
        printf 'fail_count=%s\n' "$old_fail"; printf 'reason=%s\n' "$reason"; printf 'expires_at=%s\n' "$((now + 900))"
    } > "$NP_STATE_DIR/health.$id.new.$$" || return 1
    chmod 600 "$NP_STATE_DIR/health.$id.new.$$"; mv -f "$NP_STATE_DIR/health.$id.new.$$" "$NP_STATE_DIR/health.$id"
}

np_health_all() {
    local id
    np_health_begin || return 2
    for id in $(np_ids); do np_health_one "$id" || true; done
    np_health_end
    np_manifest
}

np_manifest() {
    local now id file name enabled port config pid health_status latency checked expires reason state
    np_dirs || return 1; now=$(date +%s)
    {
        printf 'version=1\nmode=standalone\nupdated=%s\ncomponent=%s\n' "$now" "$NP_BIN"
        if np_probe_component; then printf 'component_status=available\n'; else printf 'component_status=unavailable\n'; fi
        for id in $(np_ids); do
            file=$(np_node_file "$id") || continue; name=$(np_node_value "$file" name); [ -n "$name" ] || name="$id"
            enabled=$(np_node_value "$file" enabled); port=$(np_port "$id" 2>/dev/null || true); config="$NP_CONFIG_DIR/$id.json"
            pid=$(np_pid_for_config "$config" 2>/dev/null || true); health_status=$(sed -n 's/^status=//p' "$NP_STATE_DIR/health.$id" 2>/dev/null | head -n1); latency=$(sed -n 's/^latency_ms=//p' "$NP_STATE_DIR/health.$id" 2>/dev/null | head -n1); checked=$(sed -n 's/^checked_at=//p' "$NP_STATE_DIR/health.$id" 2>/dev/null | head -n1); expires=$(sed -n 's/^expires_at=//p' "$NP_STATE_DIR/health.$id" 2>/dev/null | head -n1); reason=$(sed -n 's/^reason=//p' "$NP_STATE_DIR/health.$id" 2>/dev/null | head -n1)
            case "$expires" in ''|*[!0-9]*) ;; *) [ "$expires" -le "$now" ] && [ "$health_status" = available ] && health_status=expired ;; esac
            state=stopped; [ -n "$pid" ] && np_listener "$port" && state=running
            printf 'node.%s.name=%s\nnode.%s.enabled=%s\nnode.%s.port=%s\nnode.%s.pid=%s\nnode.%s.state=%s\nnode.%s.local_ready=%s\nnode.%s.health=%s\nnode.%s.latency_ms=%s\nnode.%s.checked_at=%s\nnode.%s.expires_at=%s\nnode.%s.reason=%s\n' \
                "$id" "$(np_safe "$name")" "$id" "$(np_safe "$enabled")" "$id" "$(np_safe "$port")" "$id" "$(np_safe "$pid")" "$id" "$state" "$id" "$( [ "$state" = running ] && printf 1 || printf 0 )" "$id" "$(np_safe "${health_status:-unknown}")" "$id" "$(np_safe "${latency:-unknown}")" "$id" "$(np_safe "${checked:-unknown}")" "$id" "$(np_safe "${expires:-unknown}")" "$id" "$(np_safe "${reason:-not-tested}")"
        done
    } > "$NP_RUN/manifest.new.$$" || return 1
    chmod 600 "$NP_RUN/manifest.new.$$"; mv -f "$NP_RUN/manifest.new.$$" "$NP_RUN/manifest"
    np_yaml > "$NP_RUN/snippets.yaml.new.$$" || return 1
    chmod 600 "$NP_RUN/snippets.yaml.new.$$"; mv -f "$NP_RUN/snippets.yaml.new.$$" "$NP_RUN/snippets.yaml"
}

np_yaml_quote() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/[[:cntrl:]]/ /g'; }
np_yaml() {
    local id file name port enabled first=1
    for id in $(np_ids); do
        file=$(np_node_file "$id") || continue; enabled=$(np_node_value "$file" enabled); np_enabled "$enabled" || continue
        name=$(np_node_value "$file" name); [ -n "$name" ] || name="$id"; port=$(np_port "$id" 2>/dev/null || true); np_valid_port "$port" || continue
        [ "$first" -eq 1 ] || printf '\n'; first=0
        printf -- '- name: "%s"\n  type: socks5\n  server: "127.0.0.1"\n  port: %s\n  udp: false\n' "$(np_yaml_quote "$name")" "$port"
    done
}

np_dispatch() {
    np_dirs || exit 1
    case "${1:-status}" in
        component) np_probe_component; exit $? ;;
        prepare) np_prepare "$2" >/dev/null; exit $? ;;
        port) np_port "$2"; exit $? ;;
        health)
            if [ "${2:-all}" = all ]; then np_health_all; exit $?; fi
            np_health_begin || exit 2
            np_health_one "$2"; rc=$?
            np_health_end
            [ "$rc" -eq 0 ] && np_manifest
            exit "$rc"
            ;;
        yaml) np_yaml; exit $? ;;
        manifest|status) np_manifest && cat "$NP_RUN/manifest"; exit $? ;;
        *) echo "usage: $0 {component|prepare ID|port ID|health [ID|all]|yaml|manifest|status}" >&2; exit 2 ;;
    esac
}

if [ "${NAIVEPROXY_STANDALONE_LIB:-0}" != 1 ]; then np_dispatch "$@"; fi
