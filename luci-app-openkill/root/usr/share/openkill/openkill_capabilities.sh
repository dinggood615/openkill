#!/bin/sh
# Probe optional Mihomo capabilities without starting a listener.  The result
# is cached in /tmp so LuCI does not execute a core test on every page render.

set -u

CACHE_DIR="/tmp/openkill"
CACHE_FILE="$CACHE_DIR/capabilities.env"
mkdir -p "$CACHE_DIR" 2>/dev/null || true

find_core() {
    for candidate in \
        /etc/openkill/clash \
        /etc/openkill/core/clash_meta \
        /tmp/etc/openkill/core/clash_meta \
        /usr/bin/mihomo \
        /usr/bin/clash; do
        if [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

CORE="$(find_core 2>/dev/null || true)"

core_fingerprint() {
    [ -n "$CORE" ] || return 0
    if stat -c '%Y:%s' "$CORE" 2>/dev/null; then
        return 0
    fi
    ls -ln "$CORE" 2>/dev/null | awk '{print $5 ":" $6 ":" $7 ":" $8}'
}

core_version() {
    [ -n "$CORE" ] || {
        printf '%s\n' "unavailable"
        return 0
    }
    # Mihomo prints a single version line for -v.  Keep only safe characters so
    # the value can be rendered by LuCI without allowing HTML/script injection.
    version="$($CORE -v 2>/dev/null | head -n 1 | tr -cd '[:alnum:]._+-')"
    [ -n "$version" ] || version="unknown"
    printf '%s\n' "$version"
}

probe() {
    name="$1"
    [ -n "$CORE" ] || {
        printf '%s\n' "unknown"
        return 0
    }

    probe_file="$CACHE_DIR/capability-${name}-$$.yaml"
    case "$name" in
        h2c)
            cat > "$probe_file" <<'EOF'
mixed-port: 65535
mode: rule
proxies:
  - name: capability
    type: vmess
    server: 127.0.0.1
    port: 443
    uuid: 00000000-0000-0000-0000-000000000001
    network: h2
    tls: false
EOF
            ;;
        shadowquic)
            cat > "$probe_file" <<'EOF'
mixed-port: 65535
mode: rule
proxies:
  - name: capability
    type: shadowquic
    server: 127.0.0.1
    port: 443
    username: capability
    password: capability
    quic-versions: [v2]
EOF
            ;;
        masque)
            cat > "$probe_file" <<'EOF'
mixed-port: 65535
mode: rule
proxies:
  - name: capability
    type: masque
    server: 127.0.0.1
    port: 443
    private-key: MHcCAQEEILI1eOtnbEIh89Fj4yNDuFR6UjayCKI3NdLl3DhetimWoAoGCCqGSM49AwEHoUQDQgAEgyXrE8v+hHsHy3ewSb3WcRjYgCrM9T9hiE0Uv6k2DZ1+4kefrDT9v1Q/8wdRigTf6t6gGNUV8W+IUMdrfUt+9g==
    public-key: MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEIaU7MToJm9NKp8YfGxR6r+/h4mcG7SxI8tsW8OR1A5tv/zCzVbCRRh2t87/kxnP6lAy0lkr7qYwu+ox+k3dr6w==
    ip: 172.16.0.2/32
    ipv6: fd00::2/128
    mtu: 1280
    udp: true
    ip-stack:
      mode: auto
      congestion-controller: cubic
    handshake-timeout: 1
    congestion-controller: bbr
EOF
            ;;
        amnezia_wg)
            cat > "$probe_file" <<'EOF'
mixed-port: 65535
mode: rule
proxies:
  - name: capability
    type: wireguard
    server: 127.0.0.1
    port: 443
    ip: 172.16.0.2/32
    private-key: eCtXsJZ27+4PbhDkHnB923tkUn2Gj59wZw5wFA75MnU=
    public-key: Cr8hWlKvtDt7nrvf+f0brNQQzabAqrjfBvas9pmowjo=
    amnezia-wg-option:
      jc: 5
EOF
            ;;
        anytls_metadata)
            cat > "$probe_file" <<'EOF'
mixed-port: 65535
mode: rule
proxies:
  - name: capability
    type: anytls
    server: 127.0.0.1
    port: 443
    password: capability
    client-metadata: "openkill-capability-probe"
EOF
            ;;
        zerotier)
            cat > "$probe_file" <<'EOF'
mixed-port: 65535
mode: rule
proxies:
  - name: capability
    type: zerotier
    network: "0123456789abcdef"
    udp: true
EOF
            ;;
        bbr3)
            cat > "$probe_file" <<'EOF'
mixed-port: 65535
mode: rule
proxies:
  - name: capability
    type: masque
    server: 127.0.0.1
    port: 443
    private-key: MHcCAQEEILI1eOtnbEIh89Fj4yNDuFR6UjayCKI3NdLl3DhetimWoAoGCCqGSM49AwEHoUQDQgAEgyXrE8v+hHsHy3ewSb3WcRjYgCrM9T9hiE0Uv6k2DZ1+4kefrDT9v1Q/8wdRigTf6t6gGNUV8W+IUMdrfUt+9g==
    public-key: MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEIaU7MToJm9NKp8YfGxR6r+/h4mcG7SxI8tsW8OR1A5tv/zCzVbCRRh2t87/kxnP6lAy0lkr7qYwu+ox+k3dr6w==
    ip: 172.16.0.2/32
    ip-stack:
      mode: mips
      congestion-controller: bbr3
EOF
            ;;
        *)
            printf '%s\n' "unknown"
            return 0
            ;;
    esac

    status=0
    output="$($CORE -t -d /etc/openkill -f "$probe_file" 2>&1)" || status=$?
    rm -f "$probe_file" 2>/dev/null || true
    # A semantic error (for example a deliberately incomplete endpoint) still
    # proves that the parser understands the field.  Only explicit unknown,
    # unsupported, or unmarshal errors mean that the capability is absent.
    if printf '%s\n' "$output" | grep -Eiq \
        'unknown field|field .* not found|unsupported.*(type|field)|cannot unmarshal|yaml: unmarshal|unknown proxy type'; then
        printf '%s\n' "0"
    elif [ "$status" -eq 0 ] || printf '%s\n' "$output" | grep -Eiq \
        'missing|required|invalid|must be|connect|network|endpoint|private.key|public.key'; then
        printf '%s\n' "1"
    else
        printf '%s\n' "0"
    fi
}

cache_current() {
    [ -s "$CACHE_FILE" ] || return 1
    cached_core="$(sed -n 's/^core_path=//p' "$CACHE_FILE" | head -n 1)"
    cached_fingerprint="$(sed -n 's/^core_fingerprint=//p' "$CACHE_FILE" | head -n 1)"
    [ "$cached_core" = "$CORE" ] || return 1
    [ "$cached_fingerprint" = "$(core_fingerprint)" ] || return 1
    return 0
}

refresh() {
    umask 077
    tmp_file="$CACHE_FILE.$$"
    core_ok=0
    [ -n "$CORE" ] && core_ok=1
    zerotier_service_ok=0
    if command -v zerotier-cli >/dev/null 2>&1 || [ -x /etc/init.d/zerotier ]; then
        zerotier_service_ok=1
    fi
    {
        printf 'core=%s\n' "$core_ok"
        printf 'core_path=%s\n' "$CORE"
        printf 'core_fingerprint=%s\n' "$(core_fingerprint)"
        printf 'core_version=%s\n' "$(core_version)"
        printf 'h2c=%s\n' "$(probe h2c)"
        printf 'shadowquic=%s\n' "$(probe shadowquic)"
        printf 'masque=%s\n' "$(probe masque)"
        printf 'amnezia_wg=%s\n' "$(probe amnezia_wg)"
        printf 'anytls_metadata=%s\n' "$(probe anytls_metadata)"
        printf 'bbr3=%s\n' "$(probe bbr3)"
        printf 'zerotier=%s\n' "$(probe zerotier)"
        printf 'zerotier_service=%s\n' "$zerotier_service_ok"
        printf 'generated_at=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null || date)"
    } > "$tmp_file" && mv -f "$tmp_file" "$CACHE_FILE"
}

ensure_cache() {
    if ! cache_current; then
        refresh
    fi
}

status_text() {
    case "$1" in
        1) printf '%s' "supported" ;;
        0) printf '%s' "not detected" ;;
        *) printf '%s' "unknown" ;;
    esac
}

case "${1:-summary}" in
    --refresh)
        refresh
        ;;
    --get)
        ensure_cache
        key="${2:-core}"
        sed -n "s/^${key}=//p" "$CACHE_FILE" | head -n 1
        ;;
    --summary|summary)
        ensure_cache
        core_ver="$(sed -n 's/^core_version=//p' "$CACHE_FILE" | head -n 1)"
        printf 'Mihomo core: %s\n' "$core_ver"
        for key in h2c shadowquic masque amnezia_wg anytls_metadata bbr3 zerotier; do
            value="$(sed -n "s/^${key}=//p" "$CACHE_FILE" | head -n 1)"
            printf '%s: %s\n' "$key" "$(status_text "$value")"
        done
        service_value="$(sed -n 's/^zerotier_service=//p' "$CACHE_FILE" | head -n 1)"
        [ -n "$service_value" ] && printf 'zerotier service: %s\n' "$(status_text "$service_value")"
        ;;
    *)
        printf 'Usage: %s [--refresh|--get KEY|--summary]\n' "$0" >&2
        exit 2
        ;;
esac
