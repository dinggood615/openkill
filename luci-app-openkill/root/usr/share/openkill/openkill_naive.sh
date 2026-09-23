#!/bin/sh
# Optional NaiveProxy bridge for OpenKill.
# This file is POSIX shell and never installs firewall rules or owns a
# transparent-proxy path. Each enabled node is a loopback SOCKS listener.

umask 077
NAIVE_ROOT="${OPENKILL_NAIVE_ROOT:-/etc/openkill/naive}"
NAIVE_BIN="${OPENKILL_NAIVE_BIN:-/etc/openkill/core/naive}"
NAIVE_RUNTIME="${OPENKILL_NAIVE_RUNTIME:-/tmp/openkill-naive}"
NAIVE_STATE="${OPENKILL_NAIVE_STATE:-/tmp/openkill-naive.state}"
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

naive_component_available() { [ -x "$NAIVE_BIN" ]; }

naive_json_prepare() {
    local sid="$1" server="$2" port="$3" user="$4" pass="$5" transport="$6" listen_port="$7"
    local encoded_user encoded_pass host proxy tmp
    naive_valid_id "$sid" || return 1
    naive_valid_host "$server" || return 1
    naive_valid_port "$port" || return 1
    naive_valid_port "$listen_port" || return 1
    case "$transport" in https|quic) ;; *) return 1 ;; esac
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
    for sid in $(uci -q show openkill 2>/dev/null | sed -n 's/^openkill\.\([^.=]*\)=servers$/\1/p'); do
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

naive_arch_ok() {
    local file="$1" machine class data b0 b1 em expected
    class=$(od -An -j4 -N1 -tu1 "$file" 2>/dev/null | tr -d ' ')
    data=$(od -An -j5 -N1 -tu1 "$file" 2>/dev/null | tr -d ' ')
    b0=$(od -An -j18 -N1 -tu1 "$file" 2>/dev/null | tr -d ' ')
    b1=$(od -An -j19 -N1 -tu1 "$file" 2>/dev/null | tr -d ' ')
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
    local url="$1" expected="$2" tmp actual size extract candidate
    case "$url" in https://github.com/klzgrad/naiveproxy/*|https://github.com/klzgrad/naiveproxy/releases/*|https://raw.githubusercontent.com/klzgrad/naiveproxy/*) ;; *) return 2 ;; esac
    case "$expected" in ''|*[!0-9A-Fa-f]*) return 2 ;; esac
    [ "${#expected}" -eq 64 ] || return 2
    mkdir -p "$NAIVE_ROOT" || return 1
    NAIVE_BIN="$NAIVE_CONFIGURED_BIN"
    mkdir -p "$(dirname "$NAIVE_BIN")" || return 1
    tmp="$NAIVE_ROOT/.download.$$"
    rm -f "$tmp"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --connect-timeout 10 --max-time 180 --max-filesize 209715200 "$url" -o "$tmp" || { rm -f "$tmp"; return 1; }
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$tmp" "$url" || { rm -f "$tmp"; return 1; }
    else rm -f "$tmp"; return 1; fi
    size=$(wc -c < "$tmp" 2>/dev/null || echo 0)
    [ "$size" -gt 0 ] && [ "$size" -le 209715200 ] || { rm -f "$tmp"; return 1; }
    actual=$(sha256sum "$tmp" 2>/dev/null | awk '{print tolower($1)}')
    [ "$actual" = "$(printf '%s' "$expected" | tr 'A-F' 'a-f')" ] || { rm -f "$tmp"; return 1; }
    if tar -tf "$tmp" >/dev/null 2>&1; then
        extract="$NAIVE_ROOT/.extract.$$"; rm -rf "$extract"; mkdir -p "$extract" || { rm -f "$tmp"; return 1; }
        if tar -tf "$tmp" | grep -Eq '(^/|(^|/)\.\.(\/|$))'; then rm -rf "$extract" "$tmp"; return 1; fi
        tar -xf "$tmp" -C "$extract" || { rm -rf "$extract" "$tmp"; return 1; }
        candidate=$(find "$extract" -type f -name naive -perm -u=x 2>/dev/null | head -n 1)
        [ -n "$candidate" ] || candidate=$(find "$extract" -type f -name naive 2>/dev/null | head -n 1)
        [ -n "$candidate" ] || { rm -rf "$extract" "$tmp"; return 1; }
        cp "$candidate" "$NAIVE_BIN.new" || { rm -rf "$extract" "$tmp"; return 1; }; rm -rf "$extract"
    else cp "$tmp" "$NAIVE_BIN.new" || { rm -f "$tmp"; return 1; }; fi
    rm -f "$tmp"; chmod 755 "$NAIVE_BIN.new" || return 1
    [ "$(dd if="$NAIVE_BIN.new" bs=4 count=1 2>/dev/null)" = "ELF" ] || { rm -f "$NAIVE_BIN.new"; return 1; }
    naive_arch_ok "$NAIVE_BIN.new" || { rm -f "$NAIVE_BIN.new"; return 1; }
    naive_binary_probe "$NAIVE_BIN.new" || { rm -f "$NAIVE_BIN.new"; return 1; }
    [ -x "$NAIVE_BIN" ] && mv -f "$NAIVE_BIN" "$NAIVE_BIN.previous" 2>/dev/null || true
    mv -f "$NAIVE_BIN.new" "$NAIVE_BIN" || return 1
    chown root:root "$NAIVE_BIN" 2>/dev/null || true; chmod 755 "$NAIVE_BIN"
}

case "${0##*/}" in
    openkill_naive.sh)
        case "$1" in
            prepare) naive_prepare_all ;;
            port) naive_port_for_section "$2" ;;
            status) [ -r "$NAIVE_STATE" ] && cat "$NAIVE_STATE" || printf '%s\n' 'state=not-started' 'reason=not-started' ;;
            install) naive_component_install "$2" "$3" ;;
            remove) rm -f "$NAIVE_CONFIGURED_BIN" "$NAIVE_CONFIGURED_BIN.previous"; naive_stop_configs ;;
            *) printf '%s\n' 'usage: openkill_naive.sh {prepare|port SID|status|install URL SHA256|remove}' >&2; exit 2 ;;
        esac
        ;;
esac
