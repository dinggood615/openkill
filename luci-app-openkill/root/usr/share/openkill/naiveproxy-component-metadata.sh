#!/bin/sh
# Discover an official NaiveProxy OpenWrt asset for the local CPU family.
# The script is intentionally read-only: it never changes UCI, installs a
# component or starts a service.  Callers may use the returned URL and digest
# only after presenting the facts to the user.

umask 077

NAIVE_METADATA_CACHE="${OPENKILL_NAIVE_METADATA_CACHE:-/tmp/openkill-naive-metadata.json}"
NAIVE_METADATA_MAX_AGE="${OPENKILL_NAIVE_METADATA_MAX_AGE:-21600}"
NAIVE_METADATA_API="${OPENKILL_NAIVE_METADATA_API:-https://api.github.com/repos/klzgrad/naiveproxy/releases/latest}"

metadata_now() {
    date +%s 2>/dev/null || printf '0\n'
}

metadata_arch() {
    local machine suffix distro_arch distro_target package_arch
    machine=$(uname -m 2>/dev/null || printf 'unknown')
    distro_arch=
    distro_target=
    if [ -r /etc/openwrt_release ]; then
        distro_arch=$(sed -n "s/^DISTRIB_ARCH=['\"]\([^'\"]*\)['\"].*/\1/p" /etc/openwrt_release | sed -n '1p')
        distro_target=$(sed -n "s/^DISTRIB_TARGET=['\"]\([^'\"]*\)['\"].*/\1/p" /etc/openwrt_release | sed -n '1p')
    fi
    if command -v opkg >/dev/null 2>&1; then
        package_arch=$(opkg print-architecture 2>/dev/null | awk '$2 != "all" {print $2; exit}')
    elif command -v apk >/dev/null 2>&1; then
        package_arch=$(apk --print-arch 2>/dev/null | sed -n '1p')
    else
        printf 'ok=0\nreason=package-manager-unavailable\narchitecture=%s\n' "$machine"
        return 0
    fi
    case "$machine" in
        x86_64|amd64) suffix=x86_64 ;;
        i386|i486|i586|i686|x86) suffix=x86 ;;
        aarch64|arm64) suffix=aarch64_generic ;;
        armv7*|armhf) suffix=arm_cortex-a7 ;;
        armv6*) suffix=arm_arm1176jzf-s_vfp ;;
        armv5*) suffix=arm_arm926ej-s ;;
        mipsel) suffix=mipsel_24kc ;;
        # The official release currently has no openwrt-mips64el asset.  Do
        # not guess a filename or silently use a linux-mips64 build.
        mips64el) printf 'ok=0\nreason=no-compatible-openwrt-asset\narchitecture=%s\n' "$machine"; return 0 ;;
        riscv64) suffix=riscv64 ;;
        loongarch64) suffix=loongarch64 ;;
        *)
            printf 'ok=0\nreason=unsupported-architecture\narchitecture=%s\n' "$machine"
            return 0
            ;;
    esac
    case "$machine:$package_arch" in
        x86_64:*x86_64*|amd64:*x86_64*|aarch64:*aarch64*|arm64:*aarch64*|riscv64:*riscv64*|loongarch64:*loongarch64*) ;;
        armv7*:*arm*|armhf:*arm*|armv6*:*arm*|armv5*:*arm*|mipsel:*mipsel*) ;;
        *) printf 'ok=0\nreason=package-architecture-mismatch\narchitecture=%s\npackage_arch=%s\n' "$machine" "$package_arch"; return 0 ;;
    esac
    printf 'ok=1\narchitecture=%s\npackage_arch=%s\ndistrib_arch=%s\ndistrib_target=%s\ntarget=%s\n' \
        "$machine" "$package_arch" "$distro_arch" "$distro_target" "$suffix"
}

metadata_value() {
    local file="$1" expression="$2" value
    command -v jsonfilter >/dev/null 2>&1 || return 1
    value=$(jsonfilter -i "$file" -e "$expression" 2>/dev/null | sed -n '1p' | tr -d '\r\n')
    [ -n "$value" ] || return 1
    printf '%s\n' "$value"
}

metadata_fetch() {
    local tmp="$NAIVE_METADATA_CACHE.new.$$" size
    rm -f "$tmp"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --connect-timeout 10 --max-time 45 --max-filesize 2097152 \
            -H 'Accept: application/vnd.github+json' \
            -H 'User-Agent: OpenKill-NaiveProxy-Metadata' \
            "$NAIVE_METADATA_API" -o "$tmp" || { rm -f "$tmp"; return 1; }
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$tmp" "$NAIVE_METADATA_API" || { rm -f "$tmp"; return 1; }
    else
        return 1
    fi
    size=$(wc -c < "$tmp" 2>/dev/null || printf '0')
    [ "$size" -gt 0 ] 2>/dev/null && [ "$size" -le 2097152 ] 2>/dev/null || {
        rm -f "$tmp"
        return 1
    }
    metadata_value "$tmp" '@.tag_name' >/dev/null || {
        rm -f "$tmp"
        return 1
    }
    mv -f "$tmp" "$NAIVE_METADATA_CACHE" || {
        rm -f "$tmp"
        return 1
    }
    chmod 600 "$NAIVE_METADATA_CACHE" 2>/dev/null || true
}

metadata_main() {
    local force="${1:-0}" now mtime age needs_fetch arch_info machine target tag asset url digest size
    arch_info=$(metadata_arch)
    if ! printf '%s\n' "$arch_info" | grep -q '^ok=1$'; then
        printf '%s\n' "$arch_info"
        return 0
    fi

    if ! command -v jsonfilter >/dev/null 2>&1; then
        printf '%s\n' "$arch_info"
        printf 'ok=0\nreason=jsonfilter-unavailable\n'
        return 0
    fi

    needs_fetch=1
    if [ "$force" != 1 ] && [ -s "$NAIVE_METADATA_CACHE" ]; then
        now=$(metadata_now)
        mtime=$(stat -c %Y "$NAIVE_METADATA_CACHE" 2>/dev/null || stat -f %m "$NAIVE_METADATA_CACHE" 2>/dev/null || printf '0')
        age=$((now - mtime))
        if [ "$age" -ge 0 ] 2>/dev/null && [ "$age" -le "$NAIVE_METADATA_MAX_AGE" ] 2>/dev/null; then
            needs_fetch=0
        fi
    fi
    if [ "$force" = 1 ] || [ "$needs_fetch" -eq 1 ]; then
        metadata_fetch || {
            printf '%s\n' "$arch_info"
            printf 'ok=0\nreason=official-api-unavailable\n'
            return 0
        }
    fi

    machine=$(printf '%s\n' "$arch_info" | sed -n 's/^architecture=//p')
    target=$(printf '%s\n' "$arch_info" | sed -n 's/^target=//p')
    tag=$(metadata_value "$NAIVE_METADATA_CACHE" '@.tag_name' 2>/dev/null || true)
    [ -n "$tag" ] || {
        printf '%s\n' "$arch_info"
        printf 'ok=0\nreason=invalid-release-metadata\n'
        return 0
    }
    case "$tag" in
        v?*[!0-9A-Za-z._-]* )
            printf '%s\n' "$arch_info"
            printf 'ok=0\nreason=invalid-release-tag\n'
            return 0
            ;;
        v?*) ;;
        * )
            printf '%s\n' "$arch_info"
            printf 'ok=0\nreason=invalid-release-tag\n'
            return 0
            ;;
    esac
    asset="naiveproxy-${tag}-openwrt-${target}.tar.xz"
    url=$(jsonfilter -i "$NAIVE_METADATA_CACHE" -e "@.assets[@.name='$asset'].browser_download_url" 2>/dev/null | sed -n '1p' | tr -d '\r\n')
    digest=$(jsonfilter -i "$NAIVE_METADATA_CACHE" -e "@.assets[@.name='$asset'].digest" 2>/dev/null | sed -n '1p' | sed 's/^sha256://' | tr -d '\r\n')
    size=$(jsonfilter -i "$NAIVE_METADATA_CACHE" -e "@.assets[@.name='$asset'].size" 2>/dev/null | sed -n '1p' | tr -d '\r\n')
    case "$url" in https://github.com/klzgrad/naiveproxy/releases/download/*) ;; *) url= ;; esac
    case "$digest" in ''|*[!0-9a-fA-F]*) digest= ;; esac
    [ "${#digest}" -eq 64 ] 2>/dev/null || digest=
    case "$size" in ''|*[!0-9]*) size= ;; esac
    printf '%s\n' "$arch_info"
    printf 'release=%s\nasset=%s\nurl=%s\nsha256=%s\nsize=%s\nsource=official-github-release-asset\nchecked_at=%s\n' \
        "$tag" "$asset" "$url" "$digest" "$size" "$(metadata_now)"
    if [ -z "$url" ] || [ -z "$digest" ] || [ -z "$size" ]; then
        printf 'ok=0\nreason=asset-or-digest-unavailable\n'
    else
        printf 'ok=1\nreason=ready-to-review\n'
    fi
}

case "${1:-detect}" in
    detect) metadata_main 1 ;;
    cached) metadata_main 0 ;;
    *) printf 'ok=0\nreason=unsupported-operation\n' ;;
esac
