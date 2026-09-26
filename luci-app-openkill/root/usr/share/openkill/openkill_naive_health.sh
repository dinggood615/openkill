#!/bin/sh
# Bounded, credential-free NaiveProxy health probes.
# Automatic mode asks Mihomo to test the exact generated SOCKS5 node. Manual
# mode tests only the matching loopback SOCKS5 listener. No probe is allowed
# to use a direct connection or to persist a response body.

umask 077
[ -r "${OPENKILL_LIB_FUNCTIONS:-/lib/functions.sh}" ] && . "${OPENKILL_LIB_FUNCTIONS:-/lib/functions.sh}"
[ -r "${OPENKILL_NAIVE_HELPER:-/usr/share/openkill/openkill_naive.sh}" ] && . "${OPENKILL_NAIVE_HELPER:-/usr/share/openkill/openkill_naive.sh}"
[ -r /usr/share/openkill/runtime.sh ] && . /usr/share/openkill/runtime.sh

HEALTH_STATE="${OPENKILL_NAIVE_HEALTH_STATE:-/tmp/openkill-naive-health.state}"
HEALTH_TMP="${HEALTH_STATE}.new.$$"
HEALTH_LOCK="${OPENKILL_NAIVE_HEALTH_LOCK:-/tmp/openkill-naive-health.lock.d}"
HEALTH_TASK_ROOT="${OPENKILL_NAIVE_HEALTH_TASK_ROOT:-/tmp/openkill-naive-health-tasks}"
HEALTH_TASK_LOCK="$HEALTH_TASK_ROOT/run.lock.d"
HEALTH_TARGET="https://www.gstatic.com/generate_204"
HEALTH_DEFAULT_TIMEOUT=8
HEALTH_MAX_AGE=900
HEALTH_SCOPE="all"
HEALTH_SID=""
HEALTH_NOW=""
HEALTH_ENABLED=0
HEALTH_AVAILABLE=0
HEALTH_FAILED=0
HEALTH_EXPIRED=0

health_valid_id() {
    case "$1" in ''|*[!A-Za-z0-9_-]*) return 1 ;; esac
}

health_safe() {
    printf '%s' "$1" | tr '\r\n|=' '    ' | cut -c1-160
}

health_previous() {
    local sid="$1" key="$2"
    health_valid_id "$sid" || return 0
    grep -m1 "^node\.${sid}\.${key}=" "$HEALTH_STATE" 2>/dev/null | cut -d= -f2-
}

health_append_node() {
    local sid="$1" key="$2" value
    value=$(health_safe "$3")
    printf 'node.%s.%s=%s\n' "$sid" "$key" "$value" >> "$HEALTH_TMP"
}

health_urlencode() {
    local value="$1" out="" i c hex
    LC_ALL=C
    i=1
    while [ "$i" -le "${#value}" ]; do
        c=$(printf '%s' "$value" | cut -b "$i")
        case "$c" in
            [A-Za-z0-9._~-]) out="${out}${c}" ;;
            *)
                hex=$(printf '%s' "$c" | od -An -tx1 2>/dev/null | tr -d ' \n\r')
                [ -n "$hex" ] || return 1
                out="${out}%${hex}"
                ;;
        esac
        i=$((i + 1))
    done
    printf '%s' "$out"
}

health_group_marker() {
    [ -n "$1" ] || return 0
    if [ -n "${HEALTH_GROUPS:-}" ]; then
        HEALTH_GROUPS="${HEALTH_GROUPS},$1"
    else
        HEALTH_GROUPS="$1"
    fi
}

health_final_yaml_state() {
    local name="$1" config_path group
    HEALTH_FINAL_YAML=unknown
    config_path=$(uci -q get openkill.config.config_path 2>/dev/null || true)
    [ -n "$config_path" ] && [ -r "$config_path" ] || { HEALTH_FINAL_YAML=not-found; return 0; }
    if ! grep -Fq -- "name: \"$name\"" "$config_path" 2>/dev/null; then
        HEALTH_FINAL_YAML=node-missing
        return 0
    fi
    if [ -z "${HEALTH_GROUPS:-}" ]; then
        HEALTH_FINAL_YAML=node-without-group
        return 0
    fi
    for group in $(printf '%s' "$HEALTH_GROUPS" | tr ',' ' '); do
        [ -n "$group" ] || continue
        grep -Fq -- "- \"$name\"" "$config_path" 2>/dev/null && { HEALTH_FINAL_YAML=loaded-candidate; return 0; }
    done
    HEALTH_FINAL_YAML=node-without-group-reference
}

health_procd_state() {
    local sid="$1" instance response state file
    HEALTH_PROCD=unknown
    command -v ubus >/dev/null 2>&1 || return 0
    instance=$(naive_instance_name "$sid" 2>/dev/null || true)
    [ -n "$instance" ] || return 0
    file="/tmp/openkill-naive-health-ubus.$$"
    response=$(ubus -S call service list '{"name":"openkill"}' 2>/dev/null | cut -c1-16384 || true)
    printf '%s' "$response" > "$file"
    chmod 600 "$file" 2>/dev/null || true
    state=$(jsonfilter -i "$file" -e "@.openkill.instances['$instance'].running" 2>/dev/null || true)
    rm -f "$file"
    case "$state" in
        true|1) HEALTH_PROCD=running ;;
        false|0) HEALTH_PROCD=stopped ;;
        *) HEALTH_PROCD=unknown ;;
    esac
}

health_timeout() {
    local timeout
    timeout=$(uci -q get openkill.config.naive_health_timeout 2>/dev/null || true)
    case "$timeout" in 3|5|8|10|15) printf '%s' "$timeout" ;; *) printf '%s' "$HEALTH_DEFAULT_TIMEOUT" ;; esac
}

health_interval() {
    local interval
    interval=$(uci -q get openkill.config.naive_health_interval 2>/dev/null || true)
    case "$interval" in 300|600|900|1800) printf '%s' "$interval" ;; *) printf '300' ;; esac
}

health_api_setup() {
    HEALTH_API_BASE=""
    HEALTH_API_SECRET=""
    if command -v openkill_load_context >/dev/null 2>&1; then
        openkill_load_context >/dev/null 2>&1 || true
        HEALTH_API_BASE="${OPENKILL_API_ENDPOINT:-}"
        HEALTH_API_SECRET="${OPENKILL_API_SECRET:-}"
    fi
    case "$HEALTH_API_BASE" in
        http://*|https://*) ;;
        *)
            local port
            port=$(uci -q get openkill.config.cn_port 2>/dev/null || echo 9090)
            case "$port" in ''|*[!0-9]*) port=9090 ;; esac
            HEALTH_API_BASE="http://127.0.0.1:${port}"
            ;;
    esac
    HEALTH_API_BASE="${HEALTH_API_BASE%/}"
}

health_api_request() {
    local url="$1" output="$2" timeout="$3"
    HEALTH_HTTP_CODE=000
    if [ -n "$HEALTH_API_SECRET" ]; then
        HEALTH_HTTP_CODE=$(curl --noproxy '*' -sS -m "$timeout" --max-filesize 16384 \
            -H "Authorization: Bearer $HEALTH_API_SECRET" "$url" -o "$output" -w '%{http_code}' 2>/dev/null) || HEALTH_HTTP_CODE=000
    else
        HEALTH_HTTP_CODE=$(curl --noproxy '*' -sS -m "$timeout" --max-filesize 16384 \
            "$url" -o "$output" -w '%{http_code}' 2>/dev/null) || HEALTH_HTTP_CODE=000
    fi
    case "$HEALTH_HTTP_CODE" in 2??) return 0 ;; *) return 1 ;; esac
}

health_mihomo_probe() {
    local name="$1" encoded response delay timeout
    timeout=$(health_timeout)
    health_api_setup
    encoded=$(health_urlencode "$name" 2>/dev/null || true)
    [ -n "$encoded" ] || { HEALTH_STATUS=mihomo-name-invalid; HEALTH_STAGE=mihomo; return; }
    response="/tmp/openkill-naive-health.$$"
    : > "$response" 2>/dev/null || { HEALTH_STATUS=probe-storage-failed; HEALTH_STAGE=probe; return; }
    chmod 600 "$response" 2>/dev/null || true
    # Probe the exact node first. This prevents a missing Mihomo node from
    # being reported as a generic remote timeout.
    health_api_request "$HEALTH_API_BASE/proxies/$encoded" "$response" "$timeout" || true
    case "$HEALTH_HTTP_CODE" in
        401|403) HEALTH_STATUS=mihomo-auth-failed; HEALTH_STAGE=mihomo; rm -f "$response"; return ;;
        404) HEALTH_STATUS=mihomo-not-loaded; HEALTH_STAGE=mihomo; rm -f "$response"; return ;;
        2??) ;;
        *) HEALTH_STATUS=mihomo-unreachable; HEALTH_STAGE=mihomo; rm -f "$response"; return ;;
    esac
    : > "$response"
    if [ -n "$HEALTH_API_SECRET" ]; then
        HEALTH_HTTP_CODE=$(curl --noproxy '*' -sS -m "$timeout" --max-filesize 16384 \
            -H "Authorization: Bearer $HEALTH_API_SECRET" -G \
            --data-urlencode "url=$HEALTH_TARGET" --data-urlencode "timeout=$((timeout * 1000))" \
            "$HEALTH_API_BASE/proxies/$encoded/delay" -o "$response" -w '%{http_code}' 2>/dev/null) || HEALTH_HTTP_CODE=000
    else
        HEALTH_HTTP_CODE=$(curl --noproxy '*' -sS -m "$timeout" --max-filesize 16384 -G \
            --data-urlencode "url=$HEALTH_TARGET" --data-urlencode "timeout=$((timeout * 1000))" \
            "$HEALTH_API_BASE/proxies/$encoded/delay" -o "$response" -w '%{http_code}' 2>/dev/null) || HEALTH_HTTP_CODE=000
    fi
    if [ "$HEALTH_HTTP_CODE" = 401 ] || [ "$HEALTH_HTTP_CODE" = 403 ]; then
        HEALTH_STATUS=mihomo-auth-failed; HEALTH_STAGE=mihomo; rm -f "$response"; return
    fi
    case "$HEALTH_HTTP_CODE" in
        404) HEALTH_STATUS=mihomo-not-loaded; HEALTH_STAGE=mihomo-delay; rm -f "$response"; return ;;
        2??) ;;
        *) HEALTH_STATUS=mihomo-probe-failed; HEALTH_STAGE=mihomo-delay; rm -f "$response"; return ;;
    esac
    delay=$(jsonfilter -i "$response" -e '@.delay' 2>/dev/null || true)
    rm -f "$response"
    case "$delay" in ''|*[!0-9]*) HEALTH_STATUS=mihomo-probe-failed; HEALTH_STAGE=mihomo-delay ;; *)
        [ "$delay" -gt 0 ] 2>/dev/null || { HEALTH_STATUS=mihomo-probe-failed; HEALTH_STAGE=mihomo-delay; return; }
        HEALTH_STATUS=available; HEALTH_STAGE=remote; HEALTH_LATENCY="$delay"; HEALTH_PATH=mihomo-delay ;;
    esac
}

health_socks_probe() {
    local port="$1" timeout output code seconds
    timeout=$(health_timeout)
    output=$(curl --proxy "socks5h://127.0.0.1:${port}" --noproxy '' \
        --connect-timeout 3 --max-time "$timeout" --max-redirs 0 --proto '=https' \
        -sS -o /dev/null -w '%{http_code}\t%{time_total}' "$HEALTH_TARGET" 2>/dev/null || true)
    code=$(printf '%s' "$output" | cut -f1)
    seconds=$(printf '%s' "$output" | cut -f2)
    case "$code" in 2??)
        # A self-managed YAML profile proves only that the helper's loopback
        # SOCKS5 chain can reach the restricted HTTPS target.  It does not
        # prove that Mihomo loaded or selected this node.
        HEALTH_STATUS=loopback-available; HEALTH_STAGE=remote; HEALTH_PATH=loopback-socks
        HEALTH_LATENCY=$(awk -v s="$seconds" 'BEGIN { if (s !~ /^[0-9.]+$/) exit 1; printf "%d", s * 1000 + 0.5 }' 2>/dev/null || true)
        [ -n "$HEALTH_LATENCY" ] || { HEALTH_STATUS=probe-failed; HEALTH_STAGE=remote; }
        ;;
        401|407) HEALTH_STATUS=remote-auth-failed; HEALTH_STAGE=remote ;;
        *) HEALTH_STATUS=probe-failed; HEALTH_STAGE=remote ;;
    esac
}

health_copy_node() {
    local sid="$1" key value
    for key in status latency_ms checked_at failure_stage reason path mihomo final_yaml groups procd local_port config_generation fail_count last_success recovery; do
        value=$(health_previous "$sid" "$key")
        [ -n "$value" ] || value=unknown
        health_append_node "$sid" "$key" "$value"
    done
    case "$(health_previous "$sid" status)" in available|loopback-available) HEALTH_AVAILABLE=$((HEALTH_AVAILABLE + 1)) ;; esac
    case "$(health_previous "$sid" status)" in disabled|available|unknown|'') ;; *) HEALTH_FAILED=$((HEALTH_FAILED + 1)) ;; esac
}

health_node() {
    local sid="$1" enabled type name server port user pass transport listen config_file generation old_generation old_fail last_success mode
    config_get enabled "$sid" enabled 0
    config_get type "$sid" type ""
    [ "$type" = naiveproxy ] || return 0
    config_get name "$sid" name "$sid"
    config_get server "$sid" server ""
    config_get port "$sid" port ""
    config_get user "$sid" naive_username ""
    config_get pass "$sid" naive_password ""
    config_get transport "$sid" naive_transport https
    HEALTH_GROUPS=""
    config_list_foreach "$sid" groups health_group_marker
    mode=$(uci -q get openkill.config.naive_bridge_mode 2>/dev/null || echo auto)
    listen=$(naive_port_for_section "$sid" 2>/dev/null || true)
    config_file="${NAIVE_RUNTIME:-/tmp/openkill-naive}/${sid}.json"
    generation=$(stat -c '%Y:%s' "$config_file" 2>/dev/null || echo missing)
    old_generation=$(health_previous "$sid" config_generation)
    old_fail=$(health_previous "$sid" fail_count)
    last_success=$(health_previous "$sid" last_success)
    case "$old_fail" in ''|*[!0-9]*) old_fail=0 ;; esac
    if [ "$old_generation" != "$generation" ]; then old_fail=0; last_success=; fi

    HEALTH_STATUS=unknown; HEALTH_STAGE=unknown; HEALTH_REASON=not-verified
    HEALTH_PATH=none; HEALTH_LATENCY=; HEALTH_MIHOMO=not-tested; HEALTH_FINAL_YAML=not-tested; HEALTH_PROCD=unknown
    if [ "$enabled" != 1 ]; then
        HEALTH_STATUS=disabled; HEALTH_STAGE=none; HEALTH_REASON=node-disabled
    elif ! naive_component_available; then
        HEALTH_STATUS=component-missing; HEALTH_STAGE=component; HEALTH_REASON=component-not-installed
    elif [ -z "$name" ] || [ -z "$server" ] || ! naive_valid_port "$port" || [ -z "$user" ] || [ -z "$pass" ]; then
        HEALTH_STATUS=config-incomplete; HEALTH_STAGE=config; HEALTH_REASON=missing-node-field
    elif ! naive_valid_port "$listen"; then
        HEALTH_STATUS=port-failed; HEALTH_STAGE=local; HEALTH_REASON=loopback-port-unavailable
    elif [ ! -r "$config_file" ] || [ "$(stat -c '%a' "$config_file" 2>/dev/null || echo 0)" != 600 ]; then
        HEALTH_STATUS=config-not-ready; HEALTH_STAGE=local; HEALTH_REASON=protected-config-not-ready
    elif ! naive_port_listening "$listen"; then
        health_procd_state "$sid"
        HEALTH_STATUS=local-not-ready; HEALTH_STAGE=local; HEALTH_REASON=loopback-listener-not-ready
    elif [ "$mode" = manual ]; then
        health_procd_state "$sid"
        HEALTH_MIHOMO=not-tested
        health_socks_probe "$listen"
    else
        health_procd_state "$sid"
        health_final_yaml_state "$name"
        HEALTH_MIHOMO="$HEALTH_FINAL_YAML"
        case "$HEALTH_FINAL_YAML" in
            node-missing|not-found) HEALTH_STATUS=final-yaml-missing; HEALTH_STAGE=final-yaml; HEALTH_REASON=final-yaml-missing-node ;;
            node-without-group) HEALTH_STATUS=no-strategy-group; HEALTH_STAGE=final-yaml; HEALTH_REASON=no-strategy-group ;;
            node-without-group-reference) HEALTH_STATUS=no-strategy-group; HEALTH_STAGE=final-yaml; HEALTH_REASON=final-yaml-missing-group-reference ;;
            *) health_mihomo_probe "$name"; HEALTH_MIHOMO="$HEALTH_STATUS" ;;
        esac
    fi

    if [ "$HEALTH_STATUS" = available ] || [ "$HEALTH_STATUS" = loopback-available ]; then
        HEALTH_REASON=remote-probe-ok
    elif [ "$HEALTH_REASON" = not-verified ] && [ -n "$HEALTH_STATUS" ] && [ "$HEALTH_STATUS" != unknown ]; then
        HEALTH_REASON="$HEALTH_STATUS"
    fi

    if [ "$HEALTH_STATUS" = available ] || [ "$HEALTH_STATUS" = loopback-available ]; then
        HEALTH_AVAILABLE=$((HEALTH_AVAILABLE + 1)); old_fail=0; last_success="$HEALTH_NOW"
    elif [ "$HEALTH_STATUS" != disabled ] && [ "$HEALTH_STATUS" != unknown ]; then
        old_fail=$((old_fail + 1)); HEALTH_FAILED=$((HEALTH_FAILED + 1))
    fi
    health_append_node "$sid" status "$HEALTH_STATUS"
    health_append_node "$sid" latency_ms "${HEALTH_LATENCY:-unknown}"
    health_append_node "$sid" checked_at "$HEALTH_NOW"
    health_append_node "$sid" failure_stage "$HEALTH_STAGE"
    health_append_node "$sid" reason "$HEALTH_REASON"
    health_append_node "$sid" path "${HEALTH_PATH:-none}"
    health_append_node "$sid" mihomo "$HEALTH_MIHOMO"
    health_append_node "$sid" final_yaml "${HEALTH_FINAL_YAML:-unknown}"
    health_append_node "$sid" groups "${HEALTH_GROUPS:-}"
    health_append_node "$sid" procd "${HEALTH_PROCD:-unknown}"
    health_append_node "$sid" local_port "${listen:-unknown}"
    health_append_node "$sid" config_generation "$generation"
    health_append_node "$sid" fail_count "$old_fail"
    health_append_node "$sid" last_success "${last_success:-unknown}"
    health_append_node "$sid" recovery procd-respawn
}

health_run() {
    local scope="$1" target_sid="$2" sid type enabled previous_updated interval
    [ -d "$HEALTH_LOCK" ] && return 2
    mkdir "$HEALTH_LOCK" 2>/dev/null || return 2
    trap 'rm -f "$HEALTH_TMP"; rmdir "$HEALTH_LOCK" 2>/dev/null || true' EXIT INT TERM
    HEALTH_NOW=$(date +%s)
    HEALTH_ENABLED=0; HEALTH_AVAILABLE=0; HEALTH_FAILED=0; HEALTH_EXPIRED=0
    : > "$HEALTH_TMP" || return 1
    printf 'version=1\nupdated=%s\nmode=%s\ntarget=restricted-https\ntimeout=%s\ninterval=%s\n' \
        "$HEALTH_NOW" "$(uci -q get openkill.config.naive_bridge_mode 2>/dev/null || echo auto)" \
        "$(health_timeout)" "$(health_interval)" >> "$HEALTH_TMP"
    config_load openkill 2>/dev/null || return 1
    for sid in $(uci -q -X show openkill 2>/dev/null | sed -n 's/^openkill\.\([^.=]*\)=servers$/\1/p'); do
        config_get type "$sid" type ""
        [ "$type" = naiveproxy ] || continue
        config_get enabled "$sid" enabled 0
        [ "$enabled" = 1 ] && HEALTH_ENABLED=$((HEALTH_ENABLED + 1))
        if [ "$scope" = one ] && [ "$sid" != "$target_sid" ]; then
            health_copy_node "$sid"
        else
            health_node "$sid"
        fi
    done
    interval=$(health_interval)
    printf 'summary.enabled=%s\nsummary.available=%s\nsummary.failed=%s\nsummary.expired=%s\nexpires_at=%s\n' \
        "$HEALTH_ENABLED" "$HEALTH_AVAILABLE" "$HEALTH_FAILED" "$HEALTH_EXPIRED" "$((HEALTH_NOW + interval * 2))" >> "$HEALTH_TMP"
    chmod 600 "$HEALTH_TMP" 2>/dev/null || true
    mv -f "$HEALTH_TMP" "$HEALTH_STATE" || return 1
    trap - EXIT INT TERM
    rmdir "$HEALTH_LOCK" 2>/dev/null || true
}

health_task_valid_id() { case "$1" in task-[A-Za-z0-9-]*) return 0 ;; *) return 1 ;; esac; }
health_task_file() { health_task_valid_id "$1" || return 1; printf '%s/%s.state\n' "$HEALTH_TASK_ROOT" "$1"; }
health_task_write() {
    local id="$1" state="$2" stage="$3" error="$4" file tmp
    file=$(health_task_file "$id") || return 1
    tmp="$file.new.$$"; mkdir -p "$HEALTH_TASK_ROOT" || return 1
    printf 'task_id=%s\nstate=%s\nstage=%s\nerror=%s\nupdated=%s\n' "$id" "$state" "$stage" "$error" "$(date +%s)" > "$tmp" || return 1
    chmod 600 "$tmp"; mv -f "$tmp" "$file"
}
health_task_new_id() { printf 'task-%s-%s\n' "$(date +%s)" "$$"; }
health_task_start() {
    local scope="$1" sid="$2" id old state
    mkdir -p "$HEALTH_TASK_ROOT" || return 1
    if [ -s "$HEALTH_TASK_LOCK/id" ]; then
        old=$(cat "$HEALTH_TASK_LOCK/id" 2>/dev/null || true)
        state=$(grep -m1 '^state=' "$(health_task_file "$old" 2>/dev/null)" 2>/dev/null | cut -d= -f2-)
        case "$state" in queued|running) printf 'task_id=%s\nstate=%s\n' "$old" "$state"; return 0 ;; esac
        rm -rf "$HEALTH_TASK_LOCK"
    fi
    mkdir "$HEALTH_TASK_LOCK" 2>/dev/null || return 1
    id=$(health_task_new_id); printf '%s\n' "$id" > "$HEALTH_TASK_LOCK/id"; chmod 600 "$HEALTH_TASK_LOCK/id"
    health_task_write "$id" queued queued ""
    (nohup env OPENKILL_NAIVE_HEALTH_TASK_ID="$id" "$0" task-worker "$id" "$scope" "$sid" >/dev/null 2>&1 </dev/null) &
    printf 'task_id=%s\nstate=queued\n' "$id"
}
health_task_worker() {
    local id="$1" scope="$2" sid="$3" rc
    health_task_write "$id" running probing ""
    health_run "$scope" "$sid"; rc=$?
    if [ "$rc" -eq 0 ]; then health_task_write "$id" succeeded completed ""; else health_task_write "$id" failed failed health-run-failed; fi
    rm -rf "$HEALTH_TASK_LOCK"; exit "$rc"
}

case "$1" in
    run) health_run all "" ;;
    run-one) health_run one "$2" ;;
    status) [ -r "$HEALTH_STATE" ] && cat "$HEALTH_STATE" ;;
    scheduled)
        [ "$(uci -q get openkill.config.naive_health_enabled 2>/dev/null || echo 0)" = 1 ] || exit 0
        last=$(grep -m1 '^updated=' "$HEALTH_STATE" 2>/dev/null | cut -d= -f2-)
        now=$(date +%s); interval=$(health_interval)
        case "$last" in ''|*[!0-9]*) last=0 ;; esac
        [ $((now - last)) -ge "$interval" ] || exit 0
        health_run all ""
        ;;
    task-start) health_task_start "${2:-all}" "${3:-}" ;;
    task-worker) health_task_worker "$2" "${3:-all}" "${4:-}" ;;
    task-status) file=$(health_task_file "$2") || exit 2; [ -r "$file" ] || exit 1; cat "$file" ;;
    *) printf '%s\n' 'usage: openkill_naive_health.sh {run|run-one SID|scheduled|task-start all|task-status ID}' >&2; exit 2 ;;
esac
