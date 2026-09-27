#!/bin/sh
# Discover an official NaiveProxy OpenWrt asset for the local CPU family.
# The script is intentionally read-only: it never changes UCI, installs a
# component or starts a service.  Callers may use the returned URL and digest
# only after presenting the facts to the user.

umask 077

NAIVE_METADATA_CACHE="${OPENKILL_NAIVE_METADATA_CACHE:-/tmp/openkill-naive-metadata.json}"
NAIVE_METADATA_MAX_AGE="${OPENKILL_NAIVE_METADATA_MAX_AGE:-21600}"
NAIVE_METADATA_API="${OPENKILL_NAIVE_METADATA_API:-https://api.github.com/repos/klzgrad/naiveproxy/releases/latest}"
NAIVE_METADATA_CATALOG="${OPENKILL_NAIVE_METADATA_CATALOG:-/usr/share/openkill/naiveproxy-release-catalog.tsv}"

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
        package_arch=$(opkg print-architecture 2>/dev/null | awk '$2 != "all" && $2 != "noarch" {print $2; exit}')
    elif command -v apk >/dev/null 2>&1; then
        package_arch=$(apk --print-arch 2>/dev/null | sed -n '1p')
    else
        printf 'ok=0\nreason=package-manager-unavailable\narchitecture=%s\n' "$machine"
        return 0
    fi
    # Resolve the asset suffix from the package manager's exact architecture
    # first.  uname alone cannot distinguish, for example, Cortex-A53 from
    # Cortex-A72 or the armv7 ABI variants.  A generic suffix is accepted only
    # when the package manager reports a generic family explicitly.
    case "$package_arch" in
        x86_64)
            case "$machine" in x86_64|amd64) suffix=x86_64 ;; *) printf 'ok=0\nreason=package-architecture-mismatch\narchitecture=%s\npackage_arch=%s\n' "$machine" "$package_arch"; return 0 ;; esac
            ;;
        x86|i386|i486|i586|i686)
            case "$machine" in i386|i486|i586|i686|x86) suffix=x86 ;; *) printf 'ok=0\nreason=package-architecture-mismatch\narchitecture=%s\npackage_arch=%s\n' "$machine" "$package_arch"; return 0 ;; esac
            ;;
        aarch64|aarch64_generic)
            case "$machine" in aarch64|arm64) suffix=aarch64_generic ;; *) printf 'ok=0\nreason=package-architecture-mismatch\narchitecture=%s\npackage_arch=%s\n' "$machine" "$package_arch"; return 0 ;; esac
            ;;
        aarch64_cortex-a53|aarch64_cortex-a72|aarch64_cortex-a76)
            case "$machine" in aarch64|arm64) suffix="$package_arch" ;; *) printf 'ok=0\nreason=package-architecture-mismatch\narchitecture=%s\npackage_arch=%s\n' "$machine" "$package_arch"; return 0 ;; esac
            ;;
        arm_*)
            case "$machine" in armv5*|armv6*|armv7*|armhf) suffix="$package_arch" ;; *) printf 'ok=0\nreason=package-architecture-mismatch\narchitecture=%s\npackage_arch=%s\n' "$machine" "$package_arch"; return 0 ;; esac
            ;;
        mipsel_*)
            case "$machine" in mipsel) suffix="$package_arch" ;; *) printf 'ok=0\nreason=package-architecture-mismatch\narchitecture=%s\npackage_arch=%s\n' "$machine" "$package_arch"; return 0 ;; esac
            ;;
        riscv64)
            case "$machine" in riscv64) suffix=riscv64 ;; *) printf 'ok=0\nreason=package-architecture-mismatch\narchitecture=%s\npackage_arch=%s\n' "$machine" "$package_arch"; return 0 ;; esac
            ;;
        loongarch64)
            case "$machine" in loongarch64) suffix=loongarch64 ;; *) printf 'ok=0\nreason=package-architecture-mismatch\narchitecture=%s\npackage_arch=%s\n' "$machine" "$package_arch"; return 0 ;; esac
            ;;
        # The official release currently has no openwrt-mips64el asset.  Do
        # not guess a filename or silently use a linux-mips64 build.
        mips64el|mips64el_*) printf 'ok=0\nreason=no-compatible-openwrt-asset\narchitecture=%s\npackage_arch=%s\n' "$machine" "$package_arch"; return 0 ;;
        ''|all|noarch)
            printf 'ok=0\nreason=package-architecture-missing\narchitecture=%s\npackage_arch=%s\n' "$machine" "$package_arch"; return 0
            ;;
        *)
            printf 'ok=0\nreason=unsupported-package-architecture\narchitecture=%s\npackage_arch=%s\n' "$machine" "$package_arch"
            return 0
            ;;
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

# The API is preferred because it discovers a newer stable release.  A
# checked-in catalog is still useful on first boot when GitHub is blocked,
# rate-limited or temporarily unavailable.  Every row is copied from the
# official release API and carries its own size and SHA256; this is not a
# filename guess or an unverified mirror.
metadata_catalog() {
    local target="$1" row release row_target asset size digest url
    [ -r "$NAIVE_METADATA_CATALOG" ] || return 1
    row=$(awk -F '\t' -v wanted="$target" '
        $0 !~ /^#/ && NF >= 6 && $2 == wanted { print; exit }
    ' "$NAIVE_METADATA_CATALOG" 2>/dev/null || true)
    [ -n "$row" ] || return 1
    release=$(printf '%s\n' "$row" | cut -f1)
    row_target=$(printf '%s\n' "$row" | cut -f2)
    asset=$(printf '%s\n' "$row" | cut -f3)
    size=$(printf '%s\n' "$row" | cut -f4)
    digest=$(printf '%s\n' "$row" | cut -f5)
    url=$(printf '%s\n' "$row" | cut -f6)
    case "$release" in v?*[!0-9A-Za-z._-]*|'' ) return 1 ;; esac
    [ "$row_target" = "$target" ] || return 1
    case "$asset" in naiveproxy-*-openwrt-*.tar.xz) ;; *) return 1 ;; esac
    case "$size" in ''|*[!0-9]*) return 1 ;; esac
    case "$digest" in ''|*[!0-9a-fA-F]*) return 1 ;; esac
    [ "${#digest}" -eq 64 ] 2>/dev/null || return 1
    case "$url" in
        https://github.com/klzgrad/naiveproxy/releases/download/* ) ;;
        * ) return 1 ;;
    esac
    printf 'release=%s\nasset=%s\nurl=%s\nsha256=%s\nsize=%s\nsource=official-github-release-catalog\nchecked_at=%s\n' \
        "$release" "$asset" "$url" "$digest" "$size" "$(metadata_now)"
}

metadata_catalog_result() {
    local arch_info="$1" target="$2" fallback_reason="$3" row
    row=$(metadata_catalog "$target" 2>/dev/null || true)
    printf '%s\n' "$arch_info"
    if [ -n "$row" ]; then
        printf '%s\n' "$row"
        printf 'fallback_reason=%s\nok=1\nreason=ready-from-official-catalog\n' "$fallback_reason"
    else
        printf 'ok=0\nreason=%s\n' "$fallback_reason"
    fi
}

metadata_main() {
    local force="${1:-0}" now mtime age needs_fetch arch_info machine target tag asset url digest size
    arch_info=$(metadata_arch)
    if ! printf '%s\n' "$arch_info" | grep -q '^ok=1$'; then
        printf '%s\n' "$arch_info"
        return 0
    fi

    target=$(printf '%s\n' "$arch_info" | sed -n 's/^target=//p')

    # A catalog row lets a minimal OpenWrt image complete the component
    # install even when jsonfilter is not present yet.  The package normally
    # depends on jsonfilter; this branch is for recovery and first-boot
    # diagnostics, and still verifies a bound official digest before install.
    if ! command -v jsonfilter >/dev/null 2>&1; then
        metadata_catalog_result "$arch_info" "$target" jsonfilter-unavailable
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
        if ! metadata_fetch; then
            metadata_catalog_result "$arch_info" "$target" official-api-unavailable
            return 0
        fi
    fi

    machine=$(printf '%s\n' "$arch_info" | sed -n 's/^architecture=//p')
    target=$(printf '%s\n' "$arch_info" | sed -n 's/^target=//p')
    tag=$(metadata_value "$NAIVE_METADATA_CACHE" '@.tag_name' 2>/dev/null || true)
    [ -n "$tag" ] || {
        metadata_catalog_result "$arch_info" "$target" invalid-release-metadata
        return 0
    }
    case "$tag" in
        v?*[!0-9A-Za-z._-]* )
            metadata_catalog_result "$arch_info" "$target" invalid-release-tag
            return 0
            ;;
        v?*) ;;
        * )
            metadata_catalog_result "$arch_info" "$target" invalid-release-tag
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
    if [ -z "$url" ] || [ -z "$digest" ] || [ -z "$size" ]; then
        metadata_catalog_result "$arch_info" "$target" asset-or-digest-unavailable
    else
        printf '%s\n' "$arch_info"
        printf 'release=%s\nasset=%s\nurl=%s\nsha256=%s\nsize=%s\nsource=official-github-release-asset\nchecked_at=%s\n' \
            "$tag" "$asset" "$url" "$digest" "$size" "$(metadata_now)"
        printf 'ok=1\nreason=ready-to-review\n'
    fi
}

case "${1:-detect}" in
    detect) metadata_main 1 ;;
    cached) metadata_main 0 ;;
    *) printf 'ok=0\nreason=unsupported-operation\n' ;;
esac
