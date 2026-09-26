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

# Install the independently-owned component without touching OpenKill UCI or
# any node file.  The caller supplies the already-bound official URL, digest
# and (when available) release-asset size.  Every failure happens before the
# existing executable is moved, so an update cannot strand a working bridge.
NP_INSTALL_ERROR=""
np_install_error() { NP_INSTALL_ERROR="$1"; return 1; }

np_read_byte() {
    local file="$1" offset="$2"
    if command -v od >/dev/null 2>&1; then
        od -An -j"$offset" -N1 -tu1 "$file" 2>/dev/null | tr -d ' '
    elif command -v hexdump >/dev/null 2>&1; then
        dd if="$file" bs=1 skip="$offset" count=1 2>/dev/null | hexdump -v -e '1/1 "%u"'
    else
        return 1
    fi
}

np_elf_arch_ok() {
    local file="$1" machine class data b0 b1 em expected
    class=$(np_read_byte "$file" 4); data=$(np_read_byte "$file" 5)
    b0=$(np_read_byte "$file" 18); b1=$(np_read_byte "$file" 19)
    [ -n "$class" ] && [ -n "$data" ] && [ -n "$b0" ] && [ -n "$b1" ] || return 1
    if [ "$data" = 1 ]; then em=$((b0 + b1 * 256)); else em=$((b1 + b0 * 256)); fi
    machine=$(uname -m 2>/dev/null || printf 'unknown')
    case "$machine" in
        x86_64|amd64) expected=62; [ "$class" = 2 ] || return 1 ;;
        aarch64|arm64) expected=183; [ "$class" = 2 ] || return 1 ;;
        armv7*|armhf) expected=40; [ "$class" = 1 ] || return 1 ;;
        mips|mipsel) expected=8; [ "$class" = 1 ] || return 1 ;;
        mips64*|mips64el) expected=8; [ "$class" = 2 ] || return 1 ;;
        *) return 1 ;;
    esac
    [ "$em" -eq "$expected" ]
}

np_component_install() {
    local url="$1" expected="$2" expected_size="${3:-}" tmp archive extract candidate size actual magic previous
    NP_INSTALL_ERROR=""
    case "$url" in
        https://github.com/klzgrad/naiveproxy/releases/download/*) ;;
        *) np_install_error untrusted-source; return 2 ;;
    esac
    case "$expected" in ''|*[!0-9A-Fa-f]*) np_install_error invalid-sha256; return 2 ;; esac
    [ "${#expected}" -eq 64 ] || { np_install_error invalid-sha256; return 2; }
    case "$expected_size" in ''|*[!0-9]*) expected_size= ;; esac
    np_dirs || { np_install_error runtime-directory-failed; return 1; }
    command -v sha256sum >/dev/null 2>&1 || { np_install_error sha256sum-missing; return 3; }
    command -v tar >/dev/null 2>&1 || { np_install_error tar-missing; return 3; }
    tmp="$NP_ROOT/.component-download.$$"; archive="$tmp"; extract="$NP_ROOT/.component-extract.$$"
    rm -f "$tmp" "$tmp.tar"; rm -rf "$extract"
    if command -v curl >/dev/null 2>&1; then
        curl -fL --connect-timeout 10 --max-time 300 --max-filesize 209715200 \
            --proto '=https' -H 'User-Agent: OpenKill-NaiveProxy-Installer' "$url" -o "$tmp" \
            || { rm -f "$tmp"; np_install_error download-failed; return 4; }
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$tmp" "$url" || { rm -f "$tmp"; np_install_error download-failed; return 4; }
    else
        np_install_error downloader-missing; return 3
    fi
    size=$(wc -c < "$tmp" 2>/dev/null || printf '0')
    [ "$size" -gt 0 ] 2>/dev/null && [ "$size" -le 209715200 ] 2>/dev/null || { rm -f "$tmp"; np_install_error invalid-size; return 5; }
    [ -z "$expected_size" ] || [ "$size" -eq "$expected_size" ] 2>/dev/null || { rm -f "$tmp"; np_install_error size-mismatch; return 5; }
    actual=$(sha256sum "$tmp" 2>/dev/null | awk '{print tolower($1)}')
    [ "$actual" = "$(printf '%s' "$expected" | tr 'A-F' 'a-f')" ] || { rm -f "$tmp"; np_install_error digest-mismatch; return 5; }
    magic=$(od -An -tx1 -N4 "$tmp" 2>/dev/null | tr -d ' \n\r')
    if [ "$magic" = 7f454c46 ]; then
        candidate="$tmp"
    else
        case "$url" in *.tar.xz) ;; *) rm -f "$tmp"; np_install_error unsupported-asset; return 6 ;; esac
        command -v xz >/dev/null 2>&1 || { rm -f "$tmp"; np_install_error xz-missing; return 6; }
        archive="$tmp.tar"
        xz -dc "$tmp" > "$archive" 2>/dev/null || { rm -f "$tmp" "$archive"; np_install_error decompress-failed; return 6; }
        tar -tf "$archive" >/dev/null 2>&1 || { rm -f "$tmp" "$archive"; np_install_error invalid-archive; return 6; }
        if tar -tf "$archive" | grep -Eq '(^/|(^|/)\.\.(\/|$))' || tar -tvf "$archive" 2>/dev/null | grep -Eq '(^l| -> )'; then
            rm -f "$tmp" "$archive"; np_install_error unsafe-archive; return 6
        fi
        mkdir -p "$extract" || { rm -f "$tmp" "$archive"; np_install_error extract-directory-failed; return 6; }
        tar -xf "$archive" -C "$extract" || { rm -rf "$extract" "$tmp" "$archive"; np_install_error extract-failed; return 6; }
        candidate=$(find "$extract" -type f -name naive -perm -u=x 2>/dev/null | head -n 1)
        [ -n "$candidate" ] || candidate=$(find "$extract" -type f -name naive 2>/dev/null | head -n 1)
        [ -n "$candidate" ] || { rm -rf "$extract" "$tmp" "$archive"; np_install_error component-missing-in-archive; return 6; }
    fi
    cp "$candidate" "$NP_BIN.new" || { rm -rf "$extract" "$tmp" "$archive"; np_install_error stage-copy-failed; return 7; }
    rm -rf "$extract"; rm -f "$tmp" "$archive"; chmod 755 "$NP_BIN.new" || { rm -f "$NP_BIN.new"; np_install_error permission-failed; return 7; }
    magic=$(od -An -tx1 -N4 "$NP_BIN.new" 2>/dev/null | tr -d ' \n\r')
    [ "$magic" = 7f454c46 ] || { rm -f "$NP_BIN.new"; np_install_error not-elf; return 8; }
    np_elf_arch_ok "$NP_BIN.new" || { rm -f "$NP_BIN.new"; np_install_error wrong-architecture; return 8; }
    "$NP_BIN.new" --version >/dev/null 2>&1 || { rm -f "$NP_BIN.new"; np_install_error loader-or-version-probe-failed; return 8; }
    {
        printf 'sha256=%s\n' "$actual"
        printf 'size=%s\n' "$size"
        printf 'url=%s\n' "$url"
        printf 'asset=%s\n' "${url##*/}"
        case "${url##*/}" in
            naiveproxy-v*-openwrt-*) printf 'version=%s\n' "$(printf '%s' "${url##*/}" | sed 's/^naiveproxy-\(v[^-]*\)-openwrt-.*/\1/')" ;;
            *) printf 'version=unknown\n' ;;
        esac
        printf 'installed_at=%s\n' "$(date +%s)"
    } > "$NP_ROOT/component.meta.new.$$" || { rm -f "$NP_BIN.new" "$NP_ROOT/component.meta.new.$$"; np_install_error metadata-write-failed; return 10; }
    chmod 600 "$NP_ROOT/component.meta.new.$$" || { rm -f "$NP_BIN.new" "$NP_ROOT/component.meta.new.$$"; np_install_error metadata-permission-failed; return 10; }
    previous="$NP_BIN.previous"
    rm -f "$previous"
    if [ -e "$NP_BIN" ]; then mv -f "$NP_BIN" "$previous" || { rm -f "$NP_BIN.new" "$NP_ROOT/component.meta.new.$$"; np_install_error preserve-old-failed; return 9; }; fi
    if ! mv -f "$NP_BIN.new" "$NP_BIN"; then
        [ -e "$previous" ] && mv -f "$previous" "$NP_BIN" || true
        rm -f "$NP_ROOT/component.meta.new.$$"
        np_install_error replace-failed; return 9
    fi
    chown root:root "$NP_BIN" 2>/dev/null || true; chmod 755 "$NP_BIN"
    if ! mv -f "$NP_ROOT/component.meta.new.$$" "$NP_ROOT/component.meta"; then
        rm -f "$NP_BIN"
        [ -e "$previous" ] && mv -f "$previous" "$NP_BIN" || true
        np_install_error metadata-replace-failed; return 10
    fi
    return 0
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
    local now id file name enabled port config pid health_status latency checked expires reason state component_version
    np_dirs || return 1; now=$(date +%s)
    component_version=$(sed -n 's/^version=//p' "$NP_ROOT/component.meta" 2>/dev/null | head -n1)
    [ -n "$component_version" ] || component_version=unknown
    {
        printf 'version=1\nmode=standalone\nupdated=%s\ncomponent=%s\ncomponent_version=%s\n' "$now" "$NP_BIN" "$(np_safe "$component_version")"
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

# Read a small key=value request from stdin.  Credentials never appear in the
# command line; the request is consumed by this service and discarded after
# the operation.  Newlines are rejected because node JSON is line-oriented.
np_control_read() {
    NP_CTL_action=""; NP_CTL_id=""; NP_CTL_name=""; NP_CTL_server=""
    NP_CTL_port=""; NP_CTL_username=""; NP_CTL_password=""
    NP_CTL_transport="https"; NP_CTL_enabled="1"
    local line key value cr
    cr=$(printf '\r')
    while IFS= read -r line; do
        case "$line" in *"$cr") line=${line%?} ;; esac
        key=${line%%=*}; value=${line#*=}
        case "$key" in
            action|operation) NP_CTL_action="$value" ;; id) NP_CTL_id="$value" ;;
            name) NP_CTL_name="$value" ;; server) NP_CTL_server="$value" ;;
            port) NP_CTL_port="$value" ;; username) NP_CTL_username="$value" ;;
            password) NP_CTL_password="$value" ;; transport) NP_CTL_transport="$value" ;;
            enabled) NP_CTL_enabled="$value" ;;
        esac
    done
    [ -n "$NP_CTL_action" ] || return 1
}

np_json_quote() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/[[:cntrl:]]/ /g'
}

np_make_id() {
    local seed="$1" value
    value=$(printf '%s' "$seed" | cksum 2>/dev/null | awk '{print $1}')
    [ -n "$value" ] || value=1
    printf 'node-%s' "$value"
}

np_node_matches() {
    local id file server port username
    for id in $(np_ids); do
        file=$(np_node_file "$id") || continue
        server=$(np_node_value "$file" server); port=$(np_node_value "$file" port)
        username=$(np_node_value "$file" username)
        [ "$server" = "$NP_CTL_server" ] && [ "$port" = "$NP_CTL_port" ] && [ "$username" = "$NP_CTL_username" ] && printf '%s\n' "$id" && return 0
    done
    return 1
}

np_control_add() {
    local id file tmp duplicate
    [ -n "$NP_CTL_name" ] && [ -n "$NP_CTL_server" ] && [ -n "$NP_CTL_username" ] && [ -n "$NP_CTL_password" ] || return 10
    np_valid_port "$NP_CTL_port" || return 11
    case "$NP_CTL_transport" in tls|https) NP_CTL_transport=https ;; quic) ;; *) return 12 ;; esac
    duplicate=$(np_node_matches 2>/dev/null || true)
    [ -z "$duplicate" ] || { printf 'duplicate_id=%s\n' "$duplicate"; return 13; }
    id="$NP_CTL_id"
    np_valid_id "$id" || id=$(np_make_id "$NP_CTL_server|$NP_CTL_port|$NP_CTL_username")
    np_valid_id "$id" || return 14
    file=$(np_node_file "$id") || return 14
    [ ! -e "$file" ] || return 13
    tmp="$file.new.$$"
    printf '{"name":"%s","server":"%s","port":%s,"username":"%s","password":"%s","transport":"%s","enabled":"%s"}\n' \
        "$(np_json_quote "$NP_CTL_name")" "$(np_json_quote "$NP_CTL_server")" "$NP_CTL_port" \
        "$(np_json_quote "$NP_CTL_username")" "$(np_json_quote "$NP_CTL_password")" \
        "$NP_CTL_transport" "$(np_json_quote "$NP_CTL_enabled")" > "$tmp" || return 15
    chmod 600 "$tmp" || return 15
    mv -f "$tmp" "$file" || return 15
    np_port "$id" >/dev/null || return 16
    np_manifest >/dev/null || return 17
    printf 'id=%s\n' "$id"
}

np_control_remove() {
    local file
    np_valid_id "$NP_CTL_id" || return 20
    file=$(np_node_file "$NP_CTL_id") || return 20
    [ -f "$file" ] || return 21
    rm -f "$file" "$NP_CONFIG_DIR/$NP_CTL_id.json" "$NP_STATE_DIR/health.$NP_CTL_id" || return 22
    np_manifest >/dev/null || return 23
}

np_control() {
    np_control_read || return 30
    case "$NP_CTL_action" in
        add|import) np_control_add ;;
        remove) np_control_remove ;;
        start) /etc/init.d/naiveproxy-bridge start >/dev/null 2>&1; rc=$?; np_manifest >/dev/null 2>&1 || true; return "$rc" ;;
        stop) /etc/init.d/naiveproxy-bridge stop >/dev/null 2>&1; rc=$?; np_manifest >/dev/null 2>&1 || true; return "$rc" ;;
        health)
            if [ -n "$NP_CTL_id" ]; then
                np_health_begin || return 31
                np_health_one "$NP_CTL_id"; rc=$?
                np_health_end
                [ "$rc" -eq 0 ] && np_manifest >/dev/null 2>&1 || true
                return "$rc"
            fi
            np_health_all; return $? ;;
        *) return 32 ;;
    esac
}

np_dispatch() {
    np_dirs || exit 1
    case "${1:-status}" in
        component) np_probe_component; exit $? ;;
        install) np_component_install "$2" "$3" "${4:-}"; rc=$?; [ "$rc" -eq 0 ] && np_manifest >/dev/null 2>&1 || true; exit "$rc" ;;
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
        control) np_control; exit $? ;;
        yaml) np_yaml; exit $? ;;
        manifest|status) np_manifest && cat "$NP_RUN/manifest"; exit $? ;;
        *) echo "usage: $0 {component|install URL SHA256 [SIZE]|prepare ID|port ID|health [ID|all]|yaml|manifest|status|control}" >&2; exit 2 ;;
    esac
}

if [ "${NAIVEPROXY_STANDALONE_LIB:-0}" != 1 ]; then np_dispatch "$@"; fi
