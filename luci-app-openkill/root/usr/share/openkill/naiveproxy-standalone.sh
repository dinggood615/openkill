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
NP_COMPONENT_LOCK="$NP_RUN/component.lock"
NP_PORT_LOCK="$NP_RUN/ports.lock"
NP_CONTROL_RESULT="${NAIVEPROXY_CONTROL_RESULT:-$NP_RUN/control.result}"

np_safe() { printf '%s' "$1" | tr '\r\n|=' '    ' | cut -c1-160; }
np_valid_id() { case "$1" in ''|*[!A-Za-z0-9_-]*) return 1 ;; esac; }
np_valid_port() { case "$1" in ''|*[!0-9]*) return 1 ;; esac; [ "$1" -ge 1 ] 2>/dev/null && [ "$1" -le 65535 ] 2>/dev/null; }
np_enabled() { case "$1" in 1|true|yes|on) return 0 ;; esac; return 1; }
np_valid_text() { [ -n "$1" ] && [ "${#1}" -le "$2" ] 2>/dev/null && ! printf '%s' "$1" | grep -q '[[:cntrl:]]'; }
np_valid_server() {
    case "$1" in ''|*' '*|*'/'*|*'@'*|*'['*']'*'['*) return 1 ;; esac
    np_valid_text "$1" 253
}

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
            *) hex=$(printf '%s' "$c" | np_hex_stdin) || return 1; [ -n "$hex" ] || return 1; out="${out}%${hex}" ;;
        esac
        i=$((i + 1))
    done
    printf '%s' "$out"
}

np_urldecode() {
    # Share-link userinfo and fragments use URI encoding.  A literal '+' is
    # data in these components; application/x-www-form-urlencoded's plus-to-
    # space rule applies only to query fields and must not change credentials.
    # BusyBox printf implements %b; decode only well-formed %HH bytes and
    # leave literal backslashes untouched by first escaping them.
    printf '%b' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/%/\\\\x/g')"
}

np_valid_encoded() {
    # Reject malformed percent escapes before BusyBox printf interprets them.
    # A malformed escape must never be silently retained as a credential or
    # node name.  Literal control characters are rejected by the caller too.
    case "$1" in *%*)
        printf '%s' "$1" | grep -Eq '%[^0-9A-Fa-f]|%[0-9A-Fa-f]?$' && return 1
    esac
    ! printf '%s' "$1" | grep -q '[[:cntrl:]]'
}

np_validate_query() {
    local query="$1" old_ifs pair key value seen=""
    [ -z "$query" ] && return 0
    case "$query" in '&'*|*'&'|*'&&'*) return 1 ;; esac
    old_ifs=$IFS; IFS='&'; set -- $query; IFS=$old_ifs
    for pair do
        key=${pair%%=*}
        [ "$pair" != "$key" ] || return 1
        value=${pair#*=}
        case "$key" in
            security) [ "$value" = tls ] || return 1 ;;
            type) [ "$value" = tcp ] || return 1 ;;
            headerType) [ "$value" = none ] || return 1 ;;
            *) return 1 ;;
        esac
        case "$seen" in *"|$key|"*) return 1 ;; esac
        seen="${seen}|${key}|"
    done
}

np_port() {
    local id="$1" line port tmp
    np_valid_id "$id" || return 1
    np_dirs || return 1
    np_port_lock_begin || return 1
    touch "$NP_PORT_MAP" || { np_port_lock_end; return 1; }
    chmod 600 "$NP_PORT_MAP" 2>/dev/null || true
    line=$(grep -m1 "^${id} " "$NP_PORT_MAP" 2>/dev/null || true)
    if [ -n "$line" ]; then
        port=${line#* }
        if np_valid_port "$port"; then
            np_port_lock_end
            printf '%s\n' "$port"
            return 0
        fi
    fi
    port="$NP_PORT_BASE"
    while [ "$port" -lt $((NP_PORT_BASE + NP_PORT_LIMIT)) ]; do
        # The map is only a persistence record.  A stale record or another
        # daemon may already own a port, so reserve only ports that are absent
        # from both the map and the live listener table.
        if ! grep -q " $port$" "$NP_PORT_MAP" 2>/dev/null && ! np_listener "$port"; then
            tmp="$NP_PORT_MAP.new.$$"
            awk -v id="$id" '$1 != id {print}' "$NP_PORT_MAP" > "$tmp" || {
                rm -f "$tmp"; np_port_lock_end; return 1;
            }
            printf '%s %s\n' "$id" "$port" >> "$tmp" || {
                rm -f "$tmp"; np_port_lock_end; return 1;
            }
            chmod 600 "$tmp" 2>/dev/null || true
            mv -f "$tmp" "$NP_PORT_MAP" || {
                rm -f "$tmp"; np_port_lock_end; return 1;
            }
            np_port_lock_end
            printf '%s\n' "$port"
            return 0
        fi
        port=$((port + 1))
    done
    np_port_lock_end
    return 1
}

np_port_lock_begin() {
    local owner attempts=0
    np_dirs || return 1
    while [ "$attempts" -lt 5 ]; do
        if mkdir "$NP_PORT_LOCK" 2>/dev/null; then
            printf '%s\n' "$$" > "$NP_PORT_LOCK/pid" 2>/dev/null || true
            chmod 700 "$NP_PORT_LOCK" 2>/dev/null || true
            return 0
        fi
        owner=$(sed -n '1p' "$NP_PORT_LOCK/pid" 2>/dev/null || true)
        case "$owner" in
            ''|*[!0-9]*) rm -f "$NP_PORT_LOCK/pid" 2>/dev/null || true; rmdir "$NP_PORT_LOCK" 2>/dev/null || true ;;
            *)
                if ! kill -0 "$owner" 2>/dev/null; then
                    rm -f "$NP_PORT_LOCK/pid" 2>/dev/null || true
                    rmdir "$NP_PORT_LOCK" 2>/dev/null || true
                fi
                ;;
        esac
        attempts=$((attempts + 1))
        [ "$attempts" -lt 5 ] && sleep 1
    done
    return 1
}

np_port_lock_end() {
    rm -f "$NP_PORT_LOCK/pid" 2>/dev/null || true
    rmdir "$NP_PORT_LOCK" 2>/dev/null || true
}

np_mapped_port() {
    local id="$1" line port
    np_valid_id "$id" || return 1
    np_dirs || return 1
    [ -r "$NP_PORT_MAP" ] || return 1
    line=$(grep -m1 "^${id} " "$NP_PORT_MAP" 2>/dev/null || true)
    [ -n "$line" ] || return 1
    port=${line#* }
    np_valid_port "$port" || return 1
    printf '%s\n' "$port"
}

np_probe_component() {
    NP_PROBE_REASON=""
    if [ ! -e "$NP_BIN" ]; then NP_PROBE_REASON=component-missing; return 1; fi
    if [ ! -x "$NP_BIN" ]; then NP_PROBE_REASON=component-not-executable; return 1; fi
    # A component that exists but belongs to another target must not be
    # reported as a generic launch failure.  Check the ELF header before the
    # loader has a chance to reject it.  Minimal images can lack an od-like
    # reader, in which case the version probe below remains the evidence.
    if np_hex_file "$NP_BIN" 0 4 >/dev/null 2>&1; then
        if [ "$(np_hex_file "$NP_BIN" 0 4 2>/dev/null || true)" != 7f454c46 ]; then
            # Only the offline fixture opts into this branch.  Production
            # component installation rejects non-ELF payloads before this
            # probe is reached, so a shell stub can never become a router
            # component by setting this environment variable.
            [ "${NAIVEPROXY_TEST_ALLOW_NON_ELF:-0}" = 1 ] || {
                NP_PROBE_REASON=component-not-elf
                return 1
            }
        elif ! np_elf_arch_ok "$NP_BIN"; then
            NP_PROBE_REASON=component-architecture-mismatch
            return 1
        fi
    fi
    if ! "$NP_BIN" --version >/dev/null 2>&1; then NP_PROBE_REASON=loader-or-version-probe-failed; return 1; fi
    NP_PROBE_REASON=available
    return 0
}

np_cached_component_valid() {
    local expected actual asset version
    [ -x "$NP_BIN" ] || return 1
    expected=$(sed -n 's/^binary_sha256=//p' "$NP_ROOT/component.meta" 2>/dev/null | head -n1)
    case "$expected" in
        '' )
            # Older metadata recorded the official archive digest in sha256;
            # it must never be compared with the extracted executable.  Keep
            # the already verified official asset/version binding and run a
            # clean, bounded version probe before procd readiness takes over.
            asset=$(sed -n 's/^asset=//p' "$NP_ROOT/component.meta" 2>/dev/null | head -n1)
            version=$(sed -n 's/^version=//p' "$NP_ROOT/component.meta" 2>/dev/null | head -n1)
            [ -n "$asset" ] && [ -n "$version" ] && [ "$version" != unknown ] || return 1
            # Legacy metadata predates binary_sha256.  The package installer
            # already validated the official archive/version; do not rerun
            # the official binary from a LuCI worker just to prove a cached
            # component, because that context can trigger a false loader trap.
            # Architecture/ELF and executable checks remain local evidence;
            # procd readiness is the final runtime proof.
            np_hex_file "$NP_BIN" 0 4 >/dev/null 2>&1 || return 1
            [ "$(np_hex_file "$NP_BIN" 0 4 2>/dev/null || true)" = 7f454c46 ] || return 1
            np_elf_arch_ok "$NP_BIN" || return 1
            ;;
        *[!0-9A-Fa-f]* ) return 1 ;;
        * )
            [ "${#expected}" -eq 64 ] || return 1
            command -v sha256sum >/dev/null 2>&1 || return 1
            actual=$(sha256sum "$NP_BIN" 2>/dev/null | awk '{print tolower($1)}')
            [ "$actual" = "$(printf '%s' "$expected" | tr 'A-F' 'a-f')" ]
            ;;
    esac
}

# Refresh only the component evidence in an existing manifest.  This is used
# by read-only status polling after a reboot: the node table, port map,
# generated configs and health results are deliberately left untouched.  A
# previous manifest may say "component-missing" even though the protected
# executable and its verified metadata survived the reboot.
np_component_status_refresh() {
    local status reason tmp manifest
    np_dirs || return 1
    manifest="$NP_RUN/manifest"
    if [ ! -r "$manifest" ]; then
        if np_cached_component_valid; then
            status=available; reason=available
        elif [ ! -e "$NP_BIN" ]; then
            status=unavailable; reason=component-missing
        elif [ ! -x "$NP_BIN" ]; then
            status=unavailable; reason=component-not-executable
        else
            status=unavailable; reason=component-unverified
        fi
        NP_COMPONENT_STATUS_OVERRIDE="$status" NP_COMPONENT_STATUS_REASON="$reason" np_manifest || return 1
        cat "$manifest"
        return 0
    fi
    if np_cached_component_valid; then
        status=available; reason=available
    elif [ ! -e "$NP_BIN" ]; then
        status=unavailable; reason=component-missing
    elif [ ! -x "$NP_BIN" ]; then
        status=unavailable; reason=component-not-executable
    else
        status=unavailable; reason=component-unverified
    fi
    tmp="$manifest.component.new.$$"
    awk -v status="$status" -v reason="$reason" '
        BEGIN { status_seen=0; reason_seen=0 }
        /^component_status=/ { print "component_status=" status; status_seen=1; next }
        /^component_reason=/ { print "component_reason=" reason; reason_seen=1; next }
        { print }
        END {
            if (!status_seen) print "component_status=" status
            if (!reason_seen) print "component_reason=" reason
        }
    ' "$manifest" > "$tmp" || { rm -f "$tmp"; return 1; }
    chmod 600 "$tmp" 2>/dev/null || true
    mv -f "$tmp" "$manifest" || { rm -f "$tmp"; return 1; }
    cat "$manifest"
}

# Install the independently-owned component without touching OpenKill UCI or
# any node file.  The caller supplies the already-bound official URL, digest
# and (when available) release-asset size.  Every failure happens before the
# existing executable is moved, so an update cannot strand a working bridge.
NP_INSTALL_ERROR=""
np_install_error() { NP_INSTALL_ERROR="$1"; return 1; }

np_hex_stdin() {
    local value
    if command -v od >/dev/null 2>&1; then
        value=$(od -An -tx1 2>/dev/null) || value=
        [ -n "$value" ] && { printf '%s' "$value" | tr -d ' \n\r'; return 0; }
    fi
    if command -v hexdump >/dev/null 2>&1; then
        value=$(hexdump -v -e '1/1 "%02x"' 2>/dev/null) || value=
        [ -n "$value" ] && { printf '%s' "$value"; return 0; }
    fi
    if command -v busybox >/dev/null 2>&1; then
        value=$(busybox od -An -tx1 2>/dev/null) || value=
        [ -n "$value" ] && { printf '%s' "$value" | tr -d ' \n\r'; return 0; }
        value=$(busybox hexdump -v -e '1/1 "%02x"' 2>/dev/null) || value=
        [ -n "$value" ] && { printf '%s' "$value"; return 0; }
    fi
    return 1
}

np_hex_file() {
    local file="$1" offset="$2" count="$3" value
    if command -v od >/dev/null 2>&1; then
        value=$(od -An -j"$offset" -N"$count" -tx1 "$file" 2>/dev/null) || value=
        [ -n "$value" ] && { printf '%s' "$value" | tr -d ' \n\r'; return 0; }
    fi
    if command -v hexdump >/dev/null 2>&1; then
        value=$(dd if="$file" bs=1 skip="$offset" count="$count" 2>/dev/null | hexdump -v -e '1/1 "%02x"') || value=
        [ -n "$value" ] && { printf '%s' "$value"; return 0; }
    fi
    if command -v busybox >/dev/null 2>&1; then
        value=$(busybox od -An -j"$offset" -N"$count" -tx1 "$file" 2>/dev/null) || value=
        [ -n "$value" ] && { printf '%s' "$value" | tr -d ' \n\r'; return 0; }
        value=$(dd if="$file" bs=1 skip="$offset" count="$count" 2>/dev/null | busybox hexdump -v -e '1/1 "%02x"') || value=
        [ -n "$value" ] && { printf '%s' "$value"; return 0; }
    fi
    return 1
}

np_read_byte() {
    local hex
    hex=$(np_hex_file "$1" "$2" 1) || return 1
    [ -n "$hex" ] || return 1
    printf '%d\n' "0x$hex"
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
    local url="$1" expected="$2" expected_size="${3:-}" tmp archive extract candidate size actual binary_sha256 magic previous
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
    magic=$(np_hex_file "$tmp" 0 4) || { rm -f "$tmp"; np_install_error byte-reader-missing; return 8; }
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
    magic=$(np_hex_file "$NP_BIN.new" 0 4) || { rm -f "$NP_BIN.new"; np_install_error byte-reader-missing; return 8; }
    [ "$magic" = 7f454c46 ] || { rm -f "$NP_BIN.new"; np_install_error not-elf; return 8; }
    np_elf_arch_ok "$NP_BIN.new" || { rm -f "$NP_BIN.new"; np_install_error wrong-architecture; return 8; }
    "$NP_BIN.new" --version >/dev/null 2>&1 || { rm -f "$NP_BIN.new"; np_install_error loader-or-version-probe-failed; return 8; }
    binary_sha256=$(sha256sum "$NP_BIN.new" 2>/dev/null | awk '{print tolower($1)}')
    case "$binary_sha256" in ''|*[!0-9a-f]*) rm -f "$NP_BIN.new"; np_install_error binary-digest-failed; return 8 ;; esac
    {
        printf 'sha256=%s\n' "$actual"
        printf 'binary_sha256=%s\n' "$binary_sha256"
        printf 'size=%s\n' "$size"
        printf 'url=%s\n' "$url"
        printf 'asset=%s\n' "${url##*/}"
        case "${url##*/}" in
            naiveproxy-v*-openwrt-*) printf 'version=%s\n' "$(printf '%s' "${url##*/}" | sed 's/^naiveproxy-\(v.*\)-openwrt-.*/\1/')" ;;
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
        ss -lnt 2>/dev/null | grep -qE ":${port}[[:space:]]" && return 0
    fi
    if command -v netstat >/dev/null 2>&1; then
        netstat -lnt 2>/dev/null | grep -qE ":${port}[[:space:]]" && return 0
    fi
    return 1
}

np_listener_owner() {
    # Return success only when the listener can be tied to the generated
    # configuration.  BusyBox ss may omit process information; in that case
    # retain the listener result and let the caller report ownership as
    # unknown rather than claiming a different process is NaiveProxy.
    local id="$1" port="$2" config pid line
    config=$(np_node_file "$id" 2>/dev/null || true)
    [ -n "$config" ] || return 2
    pid=$(np_pid_for_config "$NP_CONFIG_DIR/$id.json" 2>/dev/null || true)
    if [ -n "$pid" ] && np_listener "$port" && np_socket_owned_by_pid "$pid" "$port"; then
        printf 'verified\n'
        return 0
    fi
    if command -v ss >/dev/null 2>&1; then
        line=$(ss -lntp 2>/dev/null | grep -E "127[.]0[.]0[.]1:${port}[[:space:]]" | head -n1 || true)
        case "$line" in *"pid="*) printf 'external-or-unmatched\n'; return 1 ;; esac
    fi
    printf 'unknown\n'
    return 2
}

np_pid_for_config() {
    local config="$1" proc cmd
    case "$(uname -s 2>/dev/null || true)" in Linux*) ;; *) return 1 ;; esac
    for proc in /proc/[0-9]*; do
        [ -r "$proc/cmdline" ] || continue
        cmd=$(tr '\000' ' ' < "$proc/cmdline" 2>/dev/null || true)
        case "$cmd" in *"$config"*) printf '%s\n' "${proc##*/}"; return 0 ;; esac
    done
    return 1
}

np_socket_owned_by_pid() {
    local pid="$1" port="$2" hex proto inode fd target
    case "$(uname -s 2>/dev/null || true)" in Linux*) ;; *) return 1 ;; esac
    np_valid_port "$port" || return 1
    hex=$(printf '%04X' "$port" 2>/dev/null) || return 1
    for proto in /proc/net/tcp /proc/net/tcp6; do
        [ -r "$proto" ] || continue
        inode=$(awk -v p=":$hex" '$4 == "0A" && $2 ~ p "$" {print $10; exit}' "$proto" 2>/dev/null || true)
        [ -n "$inode" ] || continue
        for fd in /proc/$pid/fd/*; do
            [ -e "$fd" ] || continue
            target=$(readlink "$fd" 2>/dev/null || true)
            [ "$target" = "socket:[$inode]" ] && return 0
        done
    done
    return 1
}

np_wait_for_ready() {
    local id="$1" attempts=0 port pid owner
    port=$(np_port "$id" 2>/dev/null) || return 1
    while [ "$attempts" -lt 8 ]; do
        pid=$(np_pid_for_config "$NP_CONFIG_DIR/$id.json" 2>/dev/null || true)
        if [ -n "$pid" ] && np_listener "$port"; then
            owner=$(np_listener_owner "$id" "$port" 2>/dev/null || true)
            case "$owner" in
                verified) return 0 ;;
                external-or-unmatched) return 1 ;;
            esac
        fi
        attempts=$((attempts + 1))
        sleep 1
    done
    return 1
}

np_public_resolver_ip() {
    # Mihomo Fake-IP DNS can return 198.18.0.0/15 for an upstream hostname.
    # Resolve the Naive endpoint through a bounded direct DNS query only while
    # preparing its runtime config; this does not change the device resolver.
    local server="$1" resolver answer
    case "$server" in
        ''|*[!A-Za-z0-9.-]*) return 1 ;;
    esac
    command -v nslookup >/dev/null 2>&1 || return 1
    for resolver in 1.1.1.1 8.8.8.8 223.5.5.5; do
        if command -v timeout >/dev/null 2>&1; then
            answer=$(timeout 3 nslookup "$server" "$resolver" 2>/dev/null | awk '/^Name:/{seen=1; next} seen && /^Address:/{print $2; exit}')
        else
            answer=$(nslookup "$server" "$resolver" 2>/dev/null | awk '/^Name:/{seen=1; next} seen && /^Address:/{print $2; exit}')
        fi
        case "$answer" in
            ''|198.18.*|198.19.*) continue ;;
            *.*|*:*) printf '%s\n' "$answer"; return 0 ;;
        esac
    done
    return 1
}

np_prepare() {
    local id="$1" file port server remote_port user pass transport host eu ep config tmp resolver_ip resolver_rule
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
    resolver_ip=$(np_public_resolver_ip "$server" 2>/dev/null || true)
    resolver_rule=""
    [ -n "$resolver_ip" ] && resolver_rule=$(np_json_quote "MAP $server $resolver_ip")
    if [ -n "$resolver_rule" ]; then
        printf '{\n  "listen": "socks://127.0.0.1:%s",\n  "proxy": "%s://%s:%s@%s:%s",\n  "host-resolver-rules": "%s"\n}\n' \
            "$port" "$transport" "$eu" "$ep" "$host" "$remote_port" "$resolver_rule" > "$tmp" || return 1
    else
        printf '{\n  "listen": "socks://127.0.0.1:%s",\n  "proxy": "%s://%s:%s@%s:%s"\n}\n' \
            "$port" "$transport" "$eu" "$ep" "$host" "$remote_port" > "$tmp" || return 1
    fi
    chmod 600 "$tmp" || return 1
    mv -f "$tmp" "$config" || return 1
    printf '%s\n' "$config"
}

np_config_ready() {
    local id="$1" config listen proxy
    config="$NP_CONFIG_DIR/$id.json"
    [ -r "$config" ] || return 1
    listen=$(np_json "$config" listen 2>/dev/null || true)
    proxy=$(np_json "$config" proxy 2>/dev/null || true)
    case "$listen" in socks://127.0.0.1:*) ;; *) return 1 ;; esac
    case "$proxy" in https://*|quic://*) ;; *) return 1 ;; esac
    return 0
}

np_health_one() {
    local id="$1" file port output code seconds now old_fail status reason latency state owner
    file=$(np_node_file "$id") || return 1
    [ -r "$file" ] || return 1
    # Health is observational.  It must never create a port mapping or a
    # runtime config as a side effect of a status/test request.
    port=$(np_mapped_port "$id" 2>/dev/null || true)
    now=$(date +%s); old_fail=$(sed -n 's/^fail_count=//p' "$NP_STATE_DIR/health.$id" 2>/dev/null | head -n1)
    case "$old_fail" in ''|*[!0-9]*) old_fail=0 ;; esac
    if ! np_enabled "$(np_node_value "$file" enabled)"; then status=disabled; reason=node-disabled; latency=unknown
    elif ! np_cached_component_valid && ! np_probe_component; then
        reason=${NP_PROBE_REASON:-component-unavailable}
        case "$reason" in component-missing) status=component-missing ;; *) status=component-unavailable ;; esac
        latency=unknown
    elif ! np_valid_port "$port"; then
        status=config-invalid; reason=port-unassigned; latency=unknown
    elif ! np_config_ready "$id"; then status=config-invalid; reason=node-config-not-applied; latency=unknown
    elif ! np_listener "$port"; then status=local-not-ready; reason=loopback-listener-not-ready; latency=unknown
    else
        owner=$(np_listener_owner "$id" "$port" 2>/dev/null || true)
        if [ "$owner" = external-or-unmatched ]; then
            status=local-not-ready; reason=port-owned-by-other-process; latency=unknown
        elif [ "$owner" != verified ]; then
            status=local-not-ready; reason=listener-ownership-unverified; latency=unknown
        elif ! command -v curl >/dev/null 2>&1; then
            status=probe-failed; reason=curl-missing; latency=unknown
        else
            output=$(curl --proxy "socks5h://127.0.0.1:${port}" --noproxy '' --connect-timeout 3 --max-time "$NP_TIMEOUT" --max-redirs 0 --proto '=https' -sS -o /dev/null -w '%{http_code}\t%{time_total}' "$NP_TARGET" 2>/dev/null || true)
            code=$(printf '%s' "$output" | cut -f1); seconds=$(printf '%s' "$output" | cut -f2)
            case "$code" in
                2??) latency=$(awk -v s="$seconds" 'BEGIN { if (s !~ /^[0-9.]+$/) exit 1; printf "%d", s * 1000 + 0.5 }' 2>/dev/null || true); status=available; reason=probe-ok ;;
                401|407) latency=unknown; status=probe-failed; reason=remote-auth-failed ;;
                *) latency=unknown; status=probe-failed; reason=https-probe-failed ;;
            esac
        fi
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
    local now id file name enabled port config pid health_status latency checked expires reason state component_version component_reason component_asset component_machine generation running_generation pending_apply transport listener_owner manifest_component_status manifest_component_reason
    np_dirs || return 1; now=$(date +%s)
    component_version=$(sed -n 's/^version=//p' "$NP_ROOT/component.meta" 2>/dev/null | head -n1)
    [ -n "$component_version" ] || component_version=unknown
    component_asset=$(sed -n 's/^asset=//p' "$NP_ROOT/component.meta" 2>/dev/null | head -n1)
    [ -n "$component_asset" ] || component_asset=unknown
    component_machine=$(uname -m 2>/dev/null || printf unknown)
    manifest_component_status=${NP_COMPONENT_STATUS_OVERRIDE:-}
    manifest_component_reason=${NP_COMPONENT_STATUS_REASON:-}
    [ -n "$manifest_component_status" ] && [ -n "$manifest_component_reason" ] || {
        [ "$manifest_component_status" = available ] && manifest_component_reason=available
    }
    if [ -z "$manifest_component_status" ] && [ "${NP_FORCE_COMPONENT_PROBE:-0}" != 1 ] && [ -r "$NP_RUN/manifest" ]; then
        manifest_component_status=$(sed -n 's/^component_status=//p' "$NP_RUN/manifest" 2>/dev/null | head -n1)
        manifest_component_reason=$(sed -n 's/^component_reason=//p' "$NP_RUN/manifest" 2>/dev/null | head -n1)
    fi
    if [ -z "$manifest_component_status" ]; then
        if np_probe_component; then manifest_component_status=available; manifest_component_reason=available
        else manifest_component_status=unavailable; manifest_component_reason=${NP_PROBE_REASON:-unavailable}; fi
    fi
    {
        printf 'version=1\nmode=standalone\nupdated=%s\ncomponent=%s\ncomponent_version=%s\ncomponent_asset=%s\ncomponent_machine=%s\n' "$now" "$NP_BIN" "$(np_safe "$component_version")" "$(np_safe "$component_asset")" "$(np_safe "$component_machine")"
        printf 'component_status=%s\ncomponent_reason=%s\n' "$(np_safe "$manifest_component_status")" "$(np_safe "$manifest_component_reason")"
        for id in $(np_ids); do
            file=$(np_node_file "$id") || continue; name=$(np_node_value "$file" name); [ -n "$name" ] || name="$id"
            enabled=$(np_node_value "$file" enabled); port=$(np_mapped_port "$id" 2>/dev/null || true); config="$NP_CONFIG_DIR/$id.json"
            transport=$(np_node_value "$file" transport); [ -n "$transport" ] || transport=https
            generation=$(np_node_generation "$file")
            pid=$(np_pid_for_config "$config" 2>/dev/null || true); health_status=$(sed -n 's/^status=//p' "$NP_STATE_DIR/health.$id" 2>/dev/null | head -n1); latency=$(sed -n 's/^latency_ms=//p' "$NP_STATE_DIR/health.$id" 2>/dev/null | head -n1); checked=$(sed -n 's/^checked_at=//p' "$NP_STATE_DIR/health.$id" 2>/dev/null | head -n1); expires=$(sed -n 's/^expires_at=//p' "$NP_STATE_DIR/health.$id" 2>/dev/null | head -n1); reason=$(sed -n 's/^reason=//p' "$NP_STATE_DIR/health.$id" 2>/dev/null | head -n1)
            case "$expires" in ''|*[!0-9]*) ;; *) [ "$expires" -le "$now" ] && [ "$health_status" = available ] && health_status=expired ;; esac
            state=stopped; listener_owner=not-listening
            if np_listener "$port"; then
                listener_owner=$(np_listener_owner "$id" "$port" 2>/dev/null || true)
                [ -n "$listener_owner" ] || listener_owner=unknown
                case "$listener_owner" in
                    external-or-unmatched) state=conflict ;;
                    *) [ -n "$pid" ] && state=running ;;
                esac
            fi
            running_generation=$(sed -n 's/^generation=//p' "$NP_STATE_DIR/instance.$id" 2>/dev/null | head -n1)
            pending_apply=0
            [ "$state" = running ] && [ "$running_generation" != "$generation" ] && pending_apply=1
            printf 'node.%s.name=%s\nnode.%s.enabled=%s\nnode.%s.transport=%s\nnode.%s.port=%s\nnode.%s.pid=%s\nnode.%s.state=%s\nnode.%s.listener_owner=%s\nnode.%s.local_ready=%s\nnode.%s.health=%s\nnode.%s.latency_ms=%s\nnode.%s.checked_at=%s\nnode.%s.expires_at=%s\nnode.%s.reason=%s\nnode.%s.generation=%s\nnode.%s.pending_apply=%s\n' \
                "$id" "$(np_safe "$name")" "$id" "$(np_safe "$enabled")" "$id" "$(np_safe "$transport")" "$id" "$(np_safe "$port")" "$id" "$(np_safe "$pid")" "$id" "$state" "$id" "$(np_safe "$listener_owner")" "$id" "$( [ "$state" = running ] && printf 1 || printf 0 )" "$id" "$(np_safe "${health_status:-unknown}")" "$id" "$(np_safe "${latency:-unknown}")" "$id" "$(np_safe "${checked:-unknown}")" "$id" "$(np_safe "${expires:-unknown}")" "$id" "$(np_safe "${reason:-not-tested}")" "$id" "$(np_safe "$generation")" "$id" "$pending_apply"
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
        name=$(np_node_value "$file" name); [ -n "$name" ] || name="$id"; port=$(np_mapped_port "$id" 2>/dev/null || true); np_valid_port "$port" || continue
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
    NP_CTL_transport="https"; NP_CTL_enabled="1"; NP_CTL_share=""
    NP_CTL_generation=""; NP_CTL_password_mode="replace"
    NP_CTL_RESULT_ID=""; NP_CTL_RESULT_REASON=""; NP_CTL_RESULT_ASSET=""
    NP_CTL_RESULT_VERSION=""; NP_CTL_RESULT_TASK_ID=""; NP_CTL_RESULT_NODE_NAME=""; NP_CTL_RESULT_NODE_SERVER=""
    NP_CTL_RESULT_NODE_PORT=""; NP_CTL_RESULT_NODE_USERNAME=""; NP_CTL_RESULT_NODE_TRANSPORT=""
    NP_CTL_RESULT_NODE_ENABLED=""; NP_CTL_RESULT_NODE_GENERATION=""; NP_CTL_RESULT_PASSWORD_SET=""
    local line key value cr
    cr=$(printf '\r')
    np_control_read_stream() {
        while IFS= read -r line; do
        case "$line" in *"$cr") line=${line%?} ;; esac
        key=${line%%=*}; value=${line#*=}
        case "$key" in
            action|operation) NP_CTL_action="$value" ;; id) NP_CTL_id="$value" ;;
            name) NP_CTL_name="$value" ;; server) NP_CTL_server="$value" ;;
            port) NP_CTL_port="$value" ;; username) NP_CTL_username="$value" ;;
            password) NP_CTL_password="$value" ;; transport) NP_CTL_transport="$value" ;;
            enabled) NP_CTL_enabled="$value" ;; share) NP_CTL_share="$value" ;;
            generation) NP_CTL_generation="$value" ;; password_mode) NP_CTL_password_mode="$value" ;;
        esac
        done
    }
    # LuCI invokes the bridge with stdin attached to /dev/null so the
    # official Naive process never inherits a request pipe.  The standalone
    # command-line form continues to accept stdin for compatibility.
    if [ -n "${NAIVEPROXY_CONTROL_REQUEST:-}" ] && [ -r "$NAIVEPROXY_CONTROL_REQUEST" ]; then
        np_control_read_stream < "$NAIVEPROXY_CONTROL_REQUEST"
    else
        np_control_read_stream
    fi
    [ -n "$NP_CTL_action" ] || return 1
}

# The service parses an import itself.  The browser preview is convenience
# only; accepting client-filled credentials would make the link importer
# ambiguous.  The scheme is the sole transport mapping: query hints from
# other clients are accepted only when their documented HTTPS semantics agree.
np_import_link() {
    local raw="$NP_CTL_share" normalized authority fragment query userpass hostport host port user scheme
    printf '%s' "$raw" | grep -q '[[:cntrl:]]' && return 44
    case "$raw" in naive+https://*) scheme=https; normalized=${raw#naive+https://} ;;
        naive+quic://*) scheme=quic; normalized=${raw#naive+quic://} ;;
        naiveproxy://*) scheme=https; normalized=${raw#naiveproxy://} ;;
        *) return 40 ;;
    esac
    fragment=${normalized#*#}; [ "$fragment" = "$normalized" ] && fragment=""
    normalized=${normalized%%#*}; query=${normalized#*\?}; [ "$query" = "$normalized" ] && query=""
    authority=${normalized%%\?*}
    userpass=${authority%@*}; [ "$userpass" != "$authority" ] || return 41
    hostport=${authority#*@}; [ -n "$hostport" ] || return 41
    user=${userpass%%:*}; NP_CTL_password=${userpass#*:}; [ "$NP_CTL_password" != "$userpass" ] || return 41
    np_valid_encoded "$user" && np_valid_encoded "$NP_CTL_password" || return 41
    case "$hostport" in
        \[*\]:*) host=${hostport%%]*}; host=${host#\[}; port=${hostport##*:} ;;
        \[*\]) host=${hostport#\[}; host=${host%\]}; port=443 ;;
        *:*:*) return 42 ;;
        *:*) host=${hostport%:*}; port=${hostport##*:} ;;
        *) host="$hostport"; port=443 ;;
    esac
    np_valid_encoded "$fragment" && np_valid_encoded "$host" || return 42
    np_validate_query "$query" || return 43
    np_valid_port "$port" || return 42
    NP_CTL_name=$(np_urldecode "${fragment:-$host}"); NP_CTL_server=$(np_urldecode "$host"); NP_CTL_port=$port
    NP_CTL_username=$(np_urldecode "$user"); NP_CTL_password=$(np_urldecode "$NP_CTL_password"); NP_CTL_transport="$scheme"
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

np_node_generation() {
    local file="$1" value
    value=$(np_json "$file" generation 2>/dev/null || true)
    case "$value" in ''|*[!0-9]*) printf '1\n' ;; *) printf '%s\n' "$value" ;; esac
}

np_node_matches() {
    local id file server port username
    for id in $(np_ids); do
        file=$(np_node_file "$id") || continue
        server=$(np_node_value "$file" server); port=$(np_node_value "$file" port)
        username=$(np_node_value "$file" username)
        [ "$id" != "$NP_CTL_id" ] && [ "$server" = "$NP_CTL_server" ] && [ "$port" = "$NP_CTL_port" ] && [ "$username" = "$NP_CTL_username" ] && printf '%s\n' "$id" && return 0
    done
    return 1
}

np_write_node() {
    local id="$1" generation="$2" password="$3" file tmp
    file=$(np_node_file "$id") || return 14
    tmp="$file.new.$$"
    printf '{"name":"%s","server":"%s","port":%s,"username":"%s","password":"%s","transport":"%s","enabled":"%s","generation":%s}\n' \
        "$(np_json_quote "$NP_CTL_name")" "$(np_json_quote "$NP_CTL_server")" "$NP_CTL_port" \
        "$(np_json_quote "$NP_CTL_username")" "$(np_json_quote "$password")" \
        "$NP_CTL_transport" "$(np_json_quote "$NP_CTL_enabled")" "$generation" > "$tmp" || return 15
    chmod 600 "$tmp" || return 15
    mv -f "$tmp" "$file" || return 15
    np_port "$id" >/dev/null || return 16
    rm -f "$NP_STATE_DIR/health.$id" || return 15
    NP_CTL_RESULT_ID="$id"
    NP_CTL_RESULT_NODE_GENERATION="$generation"
}

np_control_add() {
    local id file duplicate
    [ -n "$NP_CTL_name" ] && [ -n "$NP_CTL_server" ] && [ -n "$NP_CTL_username" ] && [ -n "$NP_CTL_password" ] || return 10
    np_valid_text "$NP_CTL_name" 120 && np_valid_server "$NP_CTL_server" && np_valid_text "$NP_CTL_username" 512 && np_valid_text "$NP_CTL_password" 1024 || return 10
    np_valid_port "$NP_CTL_port" || return 11
    case "$NP_CTL_transport" in tls|https) NP_CTL_transport=https ;; quic) ;; *) return 12 ;; esac
    duplicate=$(np_node_matches 2>/dev/null || true)
    [ -z "$duplicate" ] || { printf 'duplicate_id=%s\n' "$duplicate"; return 13; }
    id="$NP_CTL_id"
    np_valid_id "$id" || id=$(np_make_id "$NP_CTL_server|$NP_CTL_port|$NP_CTL_username")
    np_valid_id "$id" || return 14
    file=$(np_node_file "$id") || return 14
    [ ! -e "$file" ] || return 13
    np_write_node "$id" 1 "$NP_CTL_password" || return $?
    np_manifest >/dev/null || return 17
    printf 'id=%s\n' "$id"
}

np_control_get() {
    local file generation password
    np_valid_id "$NP_CTL_id" || return 20
    file=$(np_node_file "$NP_CTL_id") || return 20
    [ -r "$file" ] || return 21
    generation=$(np_node_generation "$file")
    password=$(np_json "$file" password 2>/dev/null || true)
    [ -n "$password" ] || return 10
    NP_CTL_RESULT_ID="$NP_CTL_id"
    NP_CTL_RESULT_NODE_NAME=$(np_json "$file" name 2>/dev/null || true)
    NP_CTL_RESULT_NODE_SERVER=$(np_json "$file" server 2>/dev/null || true)
    NP_CTL_RESULT_NODE_PORT=$(np_json "$file" port 2>/dev/null || true)
    NP_CTL_RESULT_NODE_USERNAME=$(np_json "$file" username 2>/dev/null || true)
    NP_CTL_RESULT_NODE_TRANSPORT=$(np_json "$file" transport 2>/dev/null || true)
    NP_CTL_RESULT_NODE_ENABLED=$(np_json "$file" enabled 2>/dev/null || true)
    NP_CTL_RESULT_NODE_GENERATION="$generation"
    NP_CTL_RESULT_PASSWORD_SET=1
    return 0
}

np_control_edit() {
    local file current_generation password duplicate next_generation
    np_valid_id "$NP_CTL_id" || return 20
    file=$(np_node_file "$NP_CTL_id") || return 20
    [ -r "$file" ] || return 21
    current_generation=$(np_node_generation "$file")
    [ "$NP_CTL_generation" = "$current_generation" ] || return 24
    [ -n "$NP_CTL_name" ] && [ -n "$NP_CTL_server" ] && [ -n "$NP_CTL_username" ] || return 10
    np_valid_text "$NP_CTL_name" 120 && np_valid_server "$NP_CTL_server" && np_valid_text "$NP_CTL_username" 512 || return 10
    np_valid_port "$NP_CTL_port" || return 11
    case "$NP_CTL_transport" in tls|https) NP_CTL_transport=https ;; quic) ;; *) return 12 ;; esac
    case "$NP_CTL_password_mode" in
        retain) password=$(np_json "$file" password 2>/dev/null || true); [ -n "$password" ] || return 10 ;;
        replace) password="$NP_CTL_password"; [ -n "$password" ] && np_valid_text "$password" 1024 || return 10 ;;
        *) return 10 ;;
    esac
    duplicate=$(np_node_matches 2>/dev/null || true)
    [ -z "$duplicate" ] || { printf 'duplicate_id=%s\n' "$duplicate"; return 13; }
    next_generation=$((current_generation + 1))
    np_write_node "$NP_CTL_id" "$next_generation" "$password" || return $?
    np_manifest >/dev/null || return 17
    printf 'id=%s\n' "$NP_CTL_id"
}

np_control_remove() {
    local file
    np_valid_id "$NP_CTL_id" || return 20
    file=$(np_node_file "$NP_CTL_id") || return 20
    [ -f "$file" ] || return 21
    rm -f "$file" "$NP_CONFIG_DIR/$NP_CTL_id.json" "$NP_STATE_DIR/health.$NP_CTL_id" "$NP_STATE_DIR/instance.$NP_CTL_id" || return 22
    np_manifest >/dev/null || return 23
}

# Explicit upgrade cleanup for retired OpenKill-owned Naive settings.  It is
# idempotent and intentionally never imports credentials into this service.
# The protected backup is local recovery material, not a status/log payload.
np_legacy_cleanup() {
    local backup_dir backup option value section found=0
    command -v uci >/dev/null 2>&1 || return 50
    backup_dir="$NP_ROOT/legacy-backups"; mkdir -p "$backup_dir" || return 51
    chmod 700 "$backup_dir" 2>/dev/null || true
    backup="$backup_dir/openkill-naive.$(date +%s).backup"
    : > "$backup" || return 51; chmod 600 "$backup" || return 51
    for option in naive_enabled naive_auto_start naive_bridge_mode naive_component_path naive_component_url naive_component_sha256 naive_health_enabled naive_health_interval naive_health_timeout naive_port_base; do
        value=$(uci -q get "openkill.config.$option" 2>/dev/null || true)
        if [ -n "$value" ]; then printf 'openkill.config.%s=%s\n' "$option" "$value" >> "$backup" || return 51; found=1; fi
    done
    for section in $(uci -q show openkill 2>/dev/null | sed -n "s/^openkill\.\([^.=]*\)=servers$/\1/p"); do
        [ "$(uci -q get "openkill.$section.type" 2>/dev/null || true)" = naiveproxy ] || continue
        uci -q show "openkill.$section" >> "$backup" || return 51
        found=1
    done
    [ "$found" -eq 1 ] || { rm -f "$backup"; return 0; }
    for option in naive_enabled naive_auto_start naive_bridge_mode naive_component_path naive_component_url naive_component_sha256 naive_health_enabled naive_health_interval naive_health_timeout naive_port_base; do
        uci -q delete "openkill.config.$option" >/dev/null 2>&1 || true
    done
    for section in $(uci -q show openkill 2>/dev/null | sed -n "s/^openkill\.\([^.=]*\)=servers$/\1/p"); do
        [ "$(uci -q get "openkill.$section.type" 2>/dev/null || true)" = naiveproxy ] && uci -q delete "openkill.$section" || true
    done
    uci -q commit openkill || return 52
    printf 'legacy_backup=%s\n' "$backup"
}

np_control_result() {
    local rc="$1" stage="$2" tmp
    np_dirs >/dev/null 2>&1 || return 0
    tmp="$NP_CONTROL_RESULT.new.$$"
    {
        printf 'stage=%s\n' "$(np_safe "$stage")"
        printf 'rc=%s\n' "$rc"
        [ -n "$NP_CTL_RESULT_ID" ] && printf 'id=%s\n' "$(np_safe "$NP_CTL_RESULT_ID")"
        [ -n "$NP_CTL_RESULT_REASON" ] && printf 'reason=%s\n' "$(np_safe "$NP_CTL_RESULT_REASON")"
        [ -n "$NP_CTL_RESULT_ASSET" ] && printf 'asset=%s\n' "$(np_safe "$NP_CTL_RESULT_ASSET")"
        [ -n "$NP_CTL_RESULT_VERSION" ] && printf 'candidate_version=%s\n' "$(np_safe "$NP_CTL_RESULT_VERSION")"
        [ -n "$NP_CTL_RESULT_TASK_ID" ] && printf 'task_id=%s\n' "$(np_safe "$NP_CTL_RESULT_TASK_ID")"
        [ -n "$NP_CTL_RESULT_NODE_NAME" ] && printf 'node_name=%s\n' "$(np_urlencode "$NP_CTL_RESULT_NODE_NAME")"
        [ -n "$NP_CTL_RESULT_NODE_SERVER" ] && printf 'node_server=%s\n' "$(np_urlencode "$NP_CTL_RESULT_NODE_SERVER")"
        [ -n "$NP_CTL_RESULT_NODE_PORT" ] && printf 'node_port=%s\n' "$(np_safe "$NP_CTL_RESULT_NODE_PORT")"
        [ -n "$NP_CTL_RESULT_NODE_USERNAME" ] && printf 'node_username=%s\n' "$(np_urlencode "$NP_CTL_RESULT_NODE_USERNAME")"
        [ -n "$NP_CTL_RESULT_NODE_TRANSPORT" ] && printf 'node_transport=%s\n' "$(np_safe "$NP_CTL_RESULT_NODE_TRANSPORT")"
        [ -n "$NP_CTL_RESULT_NODE_ENABLED" ] && printf 'node_enabled=%s\n' "$(np_safe "$NP_CTL_RESULT_NODE_ENABLED")"
        [ -n "$NP_CTL_RESULT_NODE_GENERATION" ] && printf 'node_generation=%s\n' "$(np_safe "$NP_CTL_RESULT_NODE_GENERATION")"
        [ -n "$NP_CTL_RESULT_PASSWORD_SET" ] && printf 'password_set=1\n'
		# Optional fields above deliberately return false when absent.  The
		# result write itself is still successful and must be atomically moved,
		# otherwise a valid import can return success without its control result.
		:
    } > "$tmp" || return 0
    chmod 600 "$tmp" 2>/dev/null || true
    mv -f "$tmp" "$NP_CONTROL_RESULT" 2>/dev/null || true
    return "$rc"
}

np_component_lock_begin() {
    local owner
    np_dirs || return 1
    if mkdir "$NP_COMPONENT_LOCK" 2>/dev/null; then
        printf '%s\n' "$$" > "$NP_COMPONENT_LOCK/pid" 2>/dev/null || true
        chmod 700 "$NP_COMPONENT_LOCK" 2>/dev/null || true
        return 0
    fi
    owner=$(sed -n '1p' "$NP_COMPONENT_LOCK/pid" 2>/dev/null || true)
    case "$owner" in
        ''|*[!0-9]*) return 1 ;;
        *) kill -0 "$owner" 2>/dev/null && return 1 ;;
    esac
    # A crashed owner cannot complete an atomic replacement.  Reclaim only
    # that demonstrably stale lock; a live install is never interrupted.
    rm -f "$NP_COMPONENT_LOCK/pid" 2>/dev/null || true
    rmdir "$NP_COMPONENT_LOCK" 2>/dev/null || return 1
    mkdir "$NP_COMPONENT_LOCK" 2>/dev/null || return 1
    printf '%s\n' "$$" > "$NP_COMPONENT_LOCK/pid" 2>/dev/null || true
    chmod 700 "$NP_COMPONENT_LOCK" 2>/dev/null || true
}

np_component_lock_end() {
    rm -f "$NP_COMPONENT_LOCK/pid" 2>/dev/null || true
    rmdir "$NP_COMPONENT_LOCK" 2>/dev/null || true
}

np_control_component_metadata() {
    local metadata output ok reason
    metadata=/usr/share/openkill/naiveproxy-component-metadata.sh
    [ -r "$metadata" ] || { NP_CTL_RESULT_REASON=metadata-resolver-missing; return 33; }
    output=$(sh "$metadata" detect 2>/dev/null) || { NP_CTL_RESULT_REASON=metadata-lookup-failed; return 34; }
    NP_CTL_METADATA_OUTPUT="$output"
    ok=$(printf '%s\n' "$output" | sed -n 's/^ok=//p' | sed -n '1p')
    reason=$(printf '%s\n' "$output" | sed -n 's/^reason=//p' | sed -n '1p')
    NP_CTL_RESULT_REASON=${reason:-metadata-unavailable}
    NP_CTL_RESULT_ASSET=$(printf '%s\n' "$output" | sed -n 's/^asset=//p' | sed -n '1p')
    NP_CTL_RESULT_VERSION=$(printf '%s\n' "$output" | sed -n 's/^release=//p' | sed -n '1p')
    [ "$ok" = 1 ] || return 35
    return 0
}

np_control_install_component() {
    local output update_url update_sha update_size rc
    NP_CTL_RESULT_TASK_ID="component-install-$$"
    np_component_lock_begin || { NP_CTL_RESULT_REASON=component-task-busy; return 39; }
    np_control_component_metadata
    rc=$?
    if [ "$rc" -ne 0 ]; then np_component_lock_end; return "$rc"; fi
    output=${NP_CTL_METADATA_OUTPUT:-}
    update_url=$(printf '%s\n' "$output" | sed -n 's/^url=//p' | sed -n '1p')
    update_sha=$(printf '%s\n' "$output" | sed -n 's/^sha256=//p' | sed -n '1p')
    update_size=$(printf '%s\n' "$output" | sed -n 's/^size=//p' | sed -n '1p')
    [ -n "$update_url" ] && [ -n "$update_sha" ] && [ -n "$update_size" ] || { NP_CTL_RESULT_REASON=metadata-incomplete; np_component_lock_end; return 36; }
    if np_component_install "$update_url" "$update_sha" "$update_size"; then
        NP_CTL_RESULT_REASON=component-installed
        NP_COMPONENT_STATUS_OVERRIDE=available np_manifest >/dev/null 2>&1 || true
        np_component_lock_end
        return 0
    fi
    NP_CTL_RESULT_REASON=${NP_INSTALL_ERROR:-component-install-failed}
    np_component_lock_end
    return 37
}

np_control() {
    local rc stage enabled_found start_id start_file
    np_control_read || return 30
    rm -f "$NP_CONTROL_RESULT" 2>/dev/null || true
    case "$NP_CTL_action" in
        add)
            np_control_add; rc=$?
            [ "$rc" -eq 0 ] && stage=accepted || stage=node-save-failed
            np_control_result "$rc" "$stage"; return "$rc" ;;
        import)
            np_import_link; rc=$?
            if [ "$rc" -ne 0 ]; then np_control_result "$rc" import-parse-failed; return "$rc"; fi
            np_control_add; rc=$?
            [ "$rc" -eq 0 ] && stage=accepted || stage=node-save-failed
            np_control_result "$rc" "$stage"; return "$rc" ;;
        get)
            np_control_get; rc=$?
            [ "$rc" -eq 0 ] && stage=node-read || stage=node-read-failed
            np_control_result "$rc" "$stage"; return "$rc" ;;
        edit)
            np_control_edit; rc=$?
            case "$rc" in 0) stage=node-saved ;; 24) stage=node-edit-conflict ;; *) stage=node-save-failed ;; esac
            np_control_result "$rc" "$stage"; return "$rc" ;;
        remove)
            np_control_remove; rc=$?
            [ "$rc" -eq 0 ] && stage=node-removed || stage=node-remove-failed
            np_control_result "$rc" "$stage"; return "$rc" ;;
        start)
            rc=0
            if [ -n "$NP_CTL_id" ]; then
                # Do not let the one-shot control request become the
                # official binary's inherited stdin through rc.common/procd.
                /etc/init.d/naiveproxy-bridge start_node "$NP_CTL_id" </dev/null >/dev/null 2>&1
                rc=$?
            else
                enabled_found=0
                for start_id in $(np_ids); do
                    start_file=$(np_node_file "$start_id" 2>/dev/null || true)
                    if np_enabled "$(np_node_value "$start_file" enabled)"; then
                        enabled_found=1
                        # Use the targeted incremental path for every node.
                        # The rc.common `start` transaction uses procd's
                        # default `set` close action, which can discard the
                        # existing instance table and is not safe for a
                        # LuCI-triggered multi-node start.
                        # Do not let the one-shot control request become the
                        # official binary's inherited stdin through procd.
                        /etc/init.d/naiveproxy-bridge start_node "$start_id" </dev/null >/dev/null 2>&1 || rc=1
                    fi
                done
                if [ "$enabled_found" -eq 1 ]; then
                    :
                else
                    rc=38; stage=no-enabled-node
                    np_control_result "$rc" "$stage"; return "$rc"
                fi
            fi
            np_manifest >/dev/null 2>&1 || true
            [ "$rc" -eq 0 ] && stage=service-started || stage=service-start-failed
            [ "$rc" -eq 0 ] || NP_CTL_RESULT_REASON="start-node-returned-$rc"
            np_control_result "$rc" "$stage"; return "$rc" ;;
        stop)
            if [ -n "$NP_CTL_id" ]; then
                /etc/init.d/naiveproxy-bridge stop_node "$NP_CTL_id" </dev/null >/dev/null 2>&1
            else
                /etc/init.d/naiveproxy-bridge stop </dev/null >/dev/null 2>&1
            fi
            rc=$?; np_manifest >/dev/null 2>&1 || true
            [ "$rc" -eq 0 ] && stage=service-stopped || stage=service-stop-failed
            [ "$rc" -eq 0 ] || NP_CTL_RESULT_REASON="stop-node-returned-$rc"
            np_control_result "$rc" "$stage"; return "$rc" ;;
        health)
            if [ -n "$NP_CTL_id" ]; then
                np_health_begin || return 31
                np_health_one "$NP_CTL_id"; rc=$?
                np_health_end
                [ "$rc" -eq 0 ] && np_manifest >/dev/null 2>&1 || true
                [ "$rc" -eq 0 ] && stage=node-health-checked || stage=node-health-failed
                np_control_result "$rc" "$stage"; return "$rc"
            fi
            np_health_all; rc=$?
            [ "$rc" -eq 0 ] && stage=all-health-checked || stage=health-busy
            np_control_result "$rc" "$stage"; return "$rc" ;;
        component)
            np_control_component_metadata; rc=$?
            [ "$rc" -eq 0 ] && stage=component-candidate-ready || stage=component-candidate-unavailable
            np_control_result "$rc" "$stage"; return "$rc" ;;
        install|update)
            np_control_install_component; rc=$?
            case "$rc" in 0) stage=component-installed ;; 39) stage=component-task-busy ;; *) stage=component-install-failed ;; esac
            np_control_result "$rc" "$stage"; return "$rc" ;;
        legacy_cleanup)
            np_legacy_cleanup; rc=$?
            [ "$rc" -eq 0 ] && stage=legacy-cleanup-complete || stage=legacy-cleanup-failed
            np_control_result "$rc" "$stage"; return "$rc" ;;
        *) return 32 ;;
    esac
}

np_dispatch() {
    np_dirs || exit 1
    case "${1:-status}" in
        component) np_probe_component; exit $? ;;
        component-status) np_component_status_refresh; exit $? ;;
        install)
            np_component_install "$2" "$3" "${4:-}"
            rc=$?
            if [ "$rc" -eq 0 ]; then
                np_manifest >/dev/null 2>&1 || true
            else
                # The installer consumes this redacted stage name; never
                # echo the URL, credentials or generated node JSON here.
                printf 'reason=%s\n' "${NP_INSTALL_ERROR:-component-install-failed}" >&2
            fi
            exit "$rc"
            ;;
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
