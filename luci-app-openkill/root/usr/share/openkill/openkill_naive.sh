#!/bin/sh
# Optional NaiveProxy bridge for OpenKill.
# This file is POSIX shell and never installs firewall rules or owns a
# transparent-proxy path. Each enabled node is a loopback SOCKS listener.

umask 077
# The helper is called both from the procd init script and directly by LuCI
# diagnostics.  Load OpenWrt's config helpers for the latter; without this,
# `prepare` silently returned before seeing anonymous `servers` sections.
[ -r /lib/functions.sh ] && . /lib/functions.sh
NAIVE_ROOT="${OPENKILL_NAIVE_ROOT:-/etc/openkill/naive}"
NAIVE_BIN="${OPENKILL_NAIVE_BIN:-/etc/openkill/core/naive}"
NAIVE_RUNTIME="${OPENKILL_NAIVE_RUNTIME:-/tmp/openkill-naive}"
NAIVE_STATE="${OPENKILL_NAIVE_STATE:-/tmp/openkill-naive.state}"
NAIVE_TASK_ROOT="${OPENKILL_NAIVE_TASK_ROOT:-/tmp/openkill-naive-tasks}"
NAIVE_TASK_LOCK="$NAIVE_TASK_ROOT/install.lock.d"
NAIVE_PORT_MAP="$NAIVE_ROOT/ports"
NAIVE_PORT_BASE="${OPENKILL_NAIVE_PORT_BASE:-11080}"
[ "$NAIVE_PORT_BASE" = 11080 ] && command -v uci >/dev/null 2>&1 && NAIVE_PORT_BASE="$(uci -q get openkill.config.naive_port_base 2>/dev/null || echo 11080)"
NAIVE_CONFIGURED_BIN="$NAIVE_BIN"
if [ "$NAIVE_BIN" = /etc/openkill/core/naive ] && command -v uci >/dev/null 2>&1; then
    naive_configured_path="$(uci -q get openkill.config.naive_component_path 2>/dev/null || true)"
    case "$naive_configured_path" in /etc/openkill/core/*) NAIVE_BIN="$naive_configured_path" ;; esac
fi
NAIVE_CONFIGURED_BIN="$NAIVE_BIN"
# Runtime detection may use a documented manual-install fallback, while
# install/remove continue to target only the configured OpenKill path.
if [ ! -x "$NAIVE_BIN" ]; then
    for naive_candidate in /etc/openkill/core/naiveproxy /usr/bin/naive /usr/bin/naiveproxy /usr/local/bin/naive; do
        if [ -x "$naive_candidate" ]; then
            NAIVE_BIN="$naive_candidate"
            break
        fi
    done
fi
NAIVE_PORT_LIMIT=100

naive_valid_id() {
    case "$1" in ''|*[!A-Za-z0-9_-]*) return 1 ;; esac
}

naive_valid_host() {
    case "$1" in ''|*[!A-Za-z0-9_.:\[\]-]*) return 1 ;; esac
}

naive_valid_port() {
    case "$1" in ''|*[!0-9]*) return 1 ;; esac
    [ "$1" -ge 1 ] 2>/dev/null && [ "$1" -le 65535 ] 2>/dev/null
}

naive_urlencode() {
    local value="$1" out="" i c hex length
    LC_ALL=C
    length=${#value}
    i=1
    while [ "$i" -le "$length" ]; do
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

naive_port_for_section() {
    local sid="$1" line port
    naive_valid_id "$sid" || return 1
    mkdir -p "$NAIVE_ROOT" 2>/dev/null || return 1
    touch "$NAIVE_PORT_MAP" 2>/dev/null || return 1
    line=$(grep -m1 "^${sid} " "$NAIVE_PORT_MAP" 2>/dev/null || true)
    if [ -n "$line" ]; then
        port=${line#* }
        naive_valid_port "$port" && printf '%s\n' "$port" && return 0
    fi
    port="$NAIVE_PORT_BASE"
    while [ "$port" -lt $((NAIVE_PORT_BASE + NAIVE_PORT_LIMIT)) ]; do
        if ! grep -q " $port$" "$NAIVE_PORT_MAP" 2>/dev/null; then
            printf '%s %s\n' "$sid" "$port" >> "$NAIVE_PORT_MAP" || return 1
            chmod 600 "$NAIVE_PORT_MAP" 2>/dev/null || true
            printf '%s\n' "$port"
            return 0
        fi
        port=$((port + 1))
    done
    return 1
}

# A file bit alone is insufficient on OpenWrt: an ELF can be present but use
# the wrong loader/libc.  The version probe is local and does not contact the
# VPS, so it is safe to use as the component availability boundary.
naive_component_available() { [ -x "$NAIVE_BIN" ] && naive_binary_probe "$NAIVE_BIN"; }

naive_port_listening() {
    local port="$1"
    naive_valid_port "$port" || return 1
    if command -v ss >/dev/null 2>&1; then
        ss -lnt 2>/dev/null | grep -qE "127[.]0[.]0[.]1:${port}[[:space:]]" && return 0
    fi
    if command -v netstat >/dev/null 2>&1; then
        netstat -lnt 2>/dev/null | grep -qE "127[.]0[.]0[.]1:${port}[[:space:]]" && return 0
    fi
    return 1
}

naive_all_ports_ready() {
    local sid _enabled _type port
    [ "${1:-0}" -gt 0 ] 2>/dev/null || return 1
    [ "${2:-0}" -eq "${1:-0}" ] 2>/dev/null || return 1
    command -v uci >/dev/null 2>&1 || return 1
    config_load openkill 2>/dev/null || return 1
    for sid in $(uci -q -X show openkill 2>/dev/null | sed -n 's/^openkill\.\([^.=]*\)=servers$/\1/p'); do
        config_get _enabled "$sid" enabled 0
        config_get _type "$sid" type ""
        [ "$_enabled" = 1 ] && [ "$_type" = naiveproxy ] || continue
        port=$(naive_port_for_section "$sid" 2>/dev/null || true)
        naive_port_listening "$port" || return 1
    done
    return 0
}

naive_state_value() {
    local name="$1" fallback="$2" state
    state=$(grep -m1 "^${name}=" "$NAIVE_STATE" 2>/dev/null || true)
    [ -n "$state" ] || { printf '%s\n' "$fallback"; return; }
    state=${state#*=}
    [ -n "$state" ] && printf '%s\n' "$state" || printf '%s\n' "$fallback"
}

naive_refresh_status() {
    local configured generated local_ready remote_verified state reason updated
    configured=$(naive_state_value configured 0)
    generated=$(naive_state_value generated 0)
    local_ready=$(naive_state_value local_ready 0)
    remote_verified=$(naive_state_value remote_verified 0)
    updated=$(date +%s)
    if naive_component_available; then
        if [ "$configured" -eq 0 ] 2>/dev/null; then
            configured=0; generated=0; state=disabled; reason=no-enabled-nodes
        elif [ "$generated" -lt "$configured" ] 2>/dev/null; then
            state=installed; reason=component-installed-needs-prepare
        else
            state=$(naive_state_value state prepared)
            reason=$(naive_state_value reason prepared)
        fi
        if naive_all_ports_ready "$configured" "$generated"; then
            local_ready=1
        else
            local_ready=0
        fi
        cat > "$NAIVE_STATE" <<EOF
configured=$configured
generated=$generated
component_installed=1
local_ready=$local_ready
remote_verified=$remote_verified
state=$state
reason=$reason
updated=$updated
EOF
    else
        cat > "$NAIVE_STATE" <<EOF
configured=$configured
generated=0
component_installed=0
local_ready=0
remote_verified=0
state=unavailable
reason=component-not-installed
updated=$updated
EOF
    fi
    chmod 600 "$NAIVE_STATE" 2>/dev/null || true
}

naive_json_prepare() {
    local sid="$1" server="$2" port="$3" user="$4" pass="$5" transport="$6" listen_port="$7"
    local encoded_user encoded_pass host proxy tmp
    naive_valid_id "$sid" || return 1
    naive_valid_host "$server" || return 1
    naive_valid_port "$port" || return 1
    naive_valid_port "$listen_port" || return 1
    # Older UCI imports used "tls" for the HTTPS transport.  Keep that
    # spelling compatible while emitting only protocols understood by the
    # NaiveProxy JSON schema.
    case "$transport" in
        tls|https) transport=https ;;
        quic) ;;
        *) return 1 ;;
    esac
    # Empty credentials produce a syntactically valid URL but an unusable
    # Naive connection.  Reject them before writing the protected config so
    # a malformed node cannot be reported as a local-ready bridge.
    [ -n "$user" ] && [ -n "$pass" ] || return 1
    encoded_user=$(naive_urlencode "$user") || return 1
    encoded_pass=$(naive_urlencode "$pass") || return 1
    host="$server"
    case "$host" in *:*|'['*) case "$host" in \[*\]) ;; *) host="[$host]" ;; esac ;; esac
    proxy="${transport}://${encoded_user}:${encoded_pass}@${host}:${port}"
    mkdir -p "$NAIVE_RUNTIME" || return 1
    tmp="$NAIVE_RUNTIME/${sid}.json.new"
    printf '{\n  "listen": "socks://127.0.0.1:%s",\n  "proxy": "%s"\n}\n' "$listen_port" "$proxy" > "$tmp" || return 1
    chmod 600 "$tmp" || return 1
    mv -f "$tmp" "$NAIVE_RUNTIME/${sid}.json" || return 1
}

naive_prepare_section() {
    local sid="$1" enabled type server port user pass transport listen_port
    config_get_bool enabled "$sid" enabled 0
    config_get type "$sid" type ""
    [ "$enabled" = 1 ] && [ "$type" = naiveproxy ] || return 0
    config_get server "$sid" server ""
    config_get port "$sid" port ""
    config_get naive_username "$sid" naive_username ""
    config_get naive_password "$sid" naive_password ""
    config_get naive_transport "$sid" naive_transport https
    listen_port=$(naive_port_for_section "$sid" 2>/dev/null || true)
    [ -n "$listen_port" ] || return 1
    naive_json_prepare "$sid" "$server" "$port" "$naive_username" "$naive_password" "$naive_transport" "$listen_port"
}

naive_prepare_all() {
    local configured=0 generated=0 reason=none sid
    mkdir -p "$NAIVE_RUNTIME" 2>/dev/null || true
    rm -f "$NAIVE_RUNTIME"/*.json.new 2>/dev/null || true
    if ! naive_component_available; then
        cat > "$NAIVE_STATE" <<EOF
configured=0
generated=0
component_installed=0
local_ready=0
remote_verified=0
state=unavailable
reason=component-not-installed
updated=$(date +%s)
EOF
        chmod 600 "$NAIVE_STATE" 2>/dev/null || true
        return 0
    fi
    config_load openkill 2>/dev/null || return 0
    # -X expands anonymous sections to stable cfg* IDs.  The default `uci
    # show` form returns @servers[N], which is rejected by naive_valid_id.
    for sid in $(uci -q -X show openkill 2>/dev/null | sed -n 's/^openkill\.\([^.=]*\)=servers$/\1/p'); do
        config_get _enabled "$sid" enabled 0
        config_get _type "$sid" type ""
        [ "$_enabled" = 1 ] && [ "$_type" = naiveproxy ] || continue
        configured=$((configured + 1))
        if naive_prepare_section "$sid"; then generated=$((generated + 1)); else reason=invalid-node; fi
    done
    if [ "$configured" -eq 0 ]; then reason=no-enabled-nodes; elif [ "$generated" -eq "$configured" ]; then reason=prepared; fi
    cat > "$NAIVE_STATE" <<EOF
configured=$configured
generated=$generated
component_installed=1
local_ready=0
remote_verified=0
state=$([ "$generated" -gt 0 ] && echo prepared || echo disabled)
reason=$reason
updated=$(date +%s)
EOF
    chmod 600 "$NAIVE_STATE" 2>/dev/null || true
}

naive_instance_name() { naive_valid_id "$1" || return 1; printf 'openkill-naive-%s\n' "$1"; }
naive_stop_configs() { rm -f "$NAIVE_RUNTIME"/*.json "$NAIVE_RUNTIME"/*.json.new "$NAIVE_STATE" 2>/dev/null || true; }

naive_read_byte() {
    local file="$1" offset="$2"
    if command -v od >/dev/null 2>&1; then
        od -An -j"$offset" -N1 -tu1 "$file" 2>/dev/null | tr -d ' '
    elif command -v hexdump >/dev/null 2>&1; then
        dd if="$file" bs=1 skip="$offset" count=1 2>/dev/null | hexdump -v -e '1/1 "%u"'
    else
        return 1
    fi
}

naive_arch_ok() {
    local file="$1" machine class data b0 b1 em expected
    class=$(naive_read_byte "$file" 4)
    data=$(naive_read_byte "$file" 5)
    b0=$(naive_read_byte "$file" 18)
    b1=$(naive_read_byte "$file" 19)
    [ -n "$class" ] && [ -n "$data" ] && [ -n "$b0" ] && [ -n "$b1" ] || return 1
    if [ "$data" = 1 ]; then em=$((b0 + b1 * 256)); else em=$((b1 + b0 * 256)); fi
    machine=$(uname -m 2>/dev/null || echo unknown)
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

naive_binary_probe() {
    # A version probe verifies the selected OpenWrt libc/loader combination
    # without opening a listener or contacting a remote server.
    "$1" --version >/dev/null 2>&1
}

naive_component_install() {
    local url="$1" expected="$2" tmp archive actual size extract candidate
    naive_task_stage validating
    case "$url" in https://github.com/klzgrad/naiveproxy/*|https://github.com/klzgrad/naiveproxy/releases/*|https://raw.githubusercontent.com/klzgrad/naiveproxy/*) ;; *) NAIVE_INSTALL_ERROR=untrusted-source; return 2 ;; esac
    case "$expected" in ''|*[!0-9A-Fa-f]*) NAIVE_INSTALL_ERROR=invalid-sha256; return 2 ;; esac
    [ "${#expected}" -eq 64 ] || { NAIVE_INSTALL_ERROR=invalid-sha256; return 2; }
    mkdir -p "$NAIVE_ROOT" || return 1
    NAIVE_BIN="$NAIVE_CONFIGURED_BIN"
    mkdir -p "$(dirname "$NAIVE_BIN")" || return 1
    tmp="$NAIVE_ROOT/.download.$$"
    rm -f "$tmp"
    naive_task_stage downloading
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --connect-timeout 10 --max-time 180 --max-filesize 209715200 "$url" -o "$tmp" || { NAIVE_INSTALL_ERROR=download-failed; rm -f "$tmp"; return 3; }
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$tmp" "$url" || { NAIVE_INSTALL_ERROR=download-failed; rm -f "$tmp"; return 3; }
    else NAIVE_INSTALL_ERROR=downloader-missing; rm -f "$tmp"; return 3; fi
    size=$(wc -c < "$tmp" 2>/dev/null || echo 0)
    [ "$size" -gt 0 ] && [ "$size" -le 209715200 ] || { NAIVE_INSTALL_ERROR=invalid-size; rm -f "$tmp"; return 4; }
    naive_task_stage verifying
    actual=$(sha256sum "$tmp" 2>/dev/null | awk '{print tolower($1)}')
    [ "$actual" = "$(printf '%s' "$expected" | tr 'A-F' 'a-f')" ] || { NAIVE_INSTALL_ERROR=digest-mismatch; rm -f "$tmp"; return 4; }
    archive="$tmp"
    case "$url" in
        *.tar.xz)
            # BusyBox tar on supported OpenWrt targets does not necessarily
            # include xz support.  Decode to a private temporary archive so
            # member validation and extraction use the same bytes.
            command -v xz >/dev/null 2>&1 || { NAIVE_INSTALL_ERROR=xz-missing; rm -f "$tmp"; return 5; }
            archive="$tmp.tar"
            xz -dc "$tmp" > "$archive" 2>/dev/null || { NAIVE_INSTALL_ERROR=decompress-failed; rm -f "$tmp" "$archive"; return 5; }
            ;;
    esac
    naive_task_stage extracting
    if tar -tf "$archive" >/dev/null 2>&1; then
        extract="$NAIVE_ROOT/.extract.$$"; rm -rf "$extract"; mkdir -p "$extract" || { rm -f "$tmp" "$archive"; return 1; }
        if tar -tf "$archive" | grep -Eq '(^/|(^|/)\.\.(\/|$))'; then NAIVE_INSTALL_ERROR=unsafe-archive; rm -rf "$extract" "$tmp" "$archive"; return 5; fi
        tar -xf "$archive" -C "$extract" || { NAIVE_INSTALL_ERROR=extract-failed; rm -rf "$extract" "$tmp" "$archive"; return 5; }
        candidate=$(find "$extract" -type f -name naive -perm -u=x 2>/dev/null | head -n 1)
        [ -n "$candidate" ] || candidate=$(find "$extract" -type f -name naive 2>/dev/null | head -n 1)
        [ -n "$candidate" ] || { NAIVE_INSTALL_ERROR=component-missing-in-archive; rm -rf "$extract" "$tmp" "$archive"; return 5; }
        cp "$candidate" "$NAIVE_BIN.new" || { NAIVE_INSTALL_ERROR=stage-copy-failed; rm -rf "$extract" "$tmp" "$archive"; return 5; }; rm -rf "$extract"
    else cp "$tmp" "$NAIVE_BIN.new" || { NAIVE_INSTALL_ERROR=stage-copy-failed; rm -f "$tmp" "$archive"; return 5; }; fi
    rm -f "$tmp" "$archive"; chmod 755 "$NAIVE_BIN.new" || return 1
    naive_task_stage probing
    [ "$(dd if="$NAIVE_BIN.new" bs=4 count=1 2>/dev/null)" = "ELF" ] || { NAIVE_INSTALL_ERROR=not-elf; rm -f "$NAIVE_BIN.new"; return 6; }
    naive_arch_ok "$NAIVE_BIN.new" || { NAIVE_INSTALL_ERROR=wrong-architecture; rm -f "$NAIVE_BIN.new"; return 6; }
    naive_binary_probe "$NAIVE_BIN.new" || { NAIVE_INSTALL_ERROR=loader-or-version-probe-failed; rm -f "$NAIVE_BIN.new"; return 6; }
    naive_task_stage replacing
    [ -x "$NAIVE_BIN" ] && mv -f "$NAIVE_BIN" "$NAIVE_BIN.previous" 2>/dev/null || true
    mv -f "$NAIVE_BIN.new" "$NAIVE_BIN" || { NAIVE_INSTALL_ERROR=replace-failed; return 7; }
    chown root:root "$NAIVE_BIN" 2>/dev/null || true; chmod 755 "$NAIVE_BIN"
}

NAIVE_TASK_ID="${OPENKILL_NAIVE_TASK_ID:-}"
NAIVE_INSTALL_ERROR=""
naive_task_file() { naive_valid_id "$1" || return 1; printf '%s/%s.state\n' "$NAIVE_TASK_ROOT" "$1"; }
naive_task_stage() {
    local stage="$1" file tmp
    NAIVE_INSTALL_STAGE="$stage"
    [ -n "$NAIVE_TASK_ID" ] || return 0
    file=$(naive_task_file "$NAIVE_TASK_ID") || return 0
    tmp="$file.new.$$"
    awk -F= -v stage="$stage" -v now="$(date +%s)" '
      BEGIN { OFS="=" }
      $1 == "stage" { print "stage", stage; seen=1; next }
      $1 == "updated" { print "updated", now; updated=1; next }
      { print }
      END { if (!seen) print "stage", stage; if (!updated) print "updated", now }
    ' "$file" > "$tmp" 2>/dev/null && mv -f "$tmp" "$file"
}
naive_task_write() {
    local id="$1" state="$2" stage="$3" error="$4" file tmp
    file=$(naive_task_file "$id") || return 1
    tmp="$file.new.$$"
    mkdir -p "$NAIVE_TASK_ROOT" || return 1
    printf 'task_id=%s\nstate=%s\nstage=%s\nerror=%s\nupdated=%s\n' "$id" "$state" "$stage" "$error" "$(date +%s)" > "$tmp" || return 1
    chmod 600 "$tmp" 2>/dev/null || true
    mv -f "$tmp" "$file"
}
naive_task_new_id() {
    local random
    random=$(head -c 4 /dev/urandom 2>/dev/null | hexdump -v -e '1/1 "%02x"' 2>/dev/null || true)
    [ -n "$random" ] || random="$$"
    printf 'task-%s-%s\n' "$(date +%s)" "$random"
}
naive_task_start() {
    local url="$1" expected="$2" id old state old_file
    mkdir -p "$NAIVE_TASK_ROOT" || return 1
    if [ -s "$NAIVE_TASK_LOCK/id" ] || [ -d "$NAIVE_TASK_LOCK" ]; then
        old=$(cat "$NAIVE_TASK_LOCK/id" 2>/dev/null || true)
        old_file=$(naive_task_file "$old" 2>/dev/null || true)
        state=$(grep -m1 '^state=' "$old_file" 2>/dev/null | cut -d= -f2- || true)
        case "$state" in queued|running) printf 'task_id=%s\nstate=%s\n' "$old" "$state"; return 0 ;; esac
        rm -rf "$NAIVE_TASK_LOCK"
    fi
    mkdir "$NAIVE_TASK_LOCK" 2>/dev/null || return 1
    id=$(naive_task_new_id)
    printf '%s\n' "$id" > "$NAIVE_TASK_LOCK/id" || { rmdir "$NAIVE_TASK_LOCK"; return 1; }
    chmod 600 "$NAIVE_TASK_LOCK/id" 2>/dev/null || true
    naive_task_write "$id" queued queued "" || { rm -rf "$NAIVE_TASK_LOCK"; return 1; }
    ( nohup env OPENKILL_NAIVE_TASK_ID="$id" OPENKILL_NAIVE_TASK_ROOT="$NAIVE_TASK_ROOT" "$0" install-worker "$id" "$url" "$expected" >> "$NAIVE_TASK_ROOT/$id.log" 2>&1 </dev/null ) >/dev/null 2>&1 &
    printf 'task_id=%s\nstate=queued\n' "$id"
}
naive_task_worker() {
    local id="$1" url="$2" expected="$3" rc error
    NAIVE_TASK_ID="$id"
    naive_task_write "$id" running starting "" || exit 1
    naive_task_stage starting
    naive_component_install "$url" "$expected"
    rc=$?
    if [ "$rc" -eq 0 ]; then
        naive_refresh_status
        naive_task_write "$id" succeeded completed ""
    else
        error=${NAIVE_INSTALL_ERROR:-install-failed}
        naive_task_write "$id" failed "${NAIVE_INSTALL_STAGE:-failed}" "$error"
    fi
    rm -rf "$NAIVE_TASK_LOCK"
    exit "$rc"
}
naive_task_status() {
    local id="$1" file
    file=$(naive_task_file "$id") || return 2
    [ -r "$file" ] || return 1
    cat "$file"
}

case "${0##*/}" in
    openkill_naive.sh)
        case "$1" in
            prepare) naive_prepare_all ;;
            port) naive_port_for_section "$2" ;;
            status) naive_refresh_status; cat "$NAIVE_STATE" ;;
            install) naive_component_install "$2" "$3"; rc=$?; [ "$rc" -eq 0 ] && naive_refresh_status; exit "$rc" ;;
            install-task) naive_task_start "$2" "$3" ;;
            install-worker) naive_task_worker "$2" "$3" "$4" ;;
            task-status) naive_task_status "$2" ;;
            remove) rm -f "$NAIVE_CONFIGURED_BIN" "$NAIVE_CONFIGURED_BIN.previous"; naive_stop_configs; naive_refresh_status ;;
            *) printf '%s\n' 'usage: openkill_naive.sh {prepare|port SID|status|install URL SHA256|install-task URL SHA256|task-status ID|remove}' >&2; exit 2 ;;
        esac
        ;;
esac
