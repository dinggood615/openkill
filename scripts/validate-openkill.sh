#!/bin/sh
# Static validation for the OpenKill source and package metadata.
# This script is intentionally dependency-light so it can run in CI and on a
# developer workstation without an OpenWrt SDK or a router.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
fail() { printf 'validate-openkill: %s\n' "$*" >&2; exit 1; }
need_file() { [ -f "$ROOT_DIR/$1" ] || fail "missing file: $1"; }

for file in \
  luci-app-openkill/Makefile \
  scripts/install-openkill.sh \
  scripts/check-openkill-i18n.sh \
  luci-app-openkill/root/etc/init.d/openkill \
  luci-app-openkill/root/usr/share/openkill/openkill_core.sh \
  luci-app-openkill/root/usr/share/openkill/openkill_update.sh \
  luci-app-openkill/root/usr/share/openkill/openkill_watchdog.sh \
  luci-app-openkill/root/usr/share/openkill/openkill_watchdog_stream.sh \
  luci-app-openkill/root/usr/share/openkill/openkill_validate.sh \
  luci-app-openkill/root/usr/share/openkill/openkill_semantic_check.sh \
  luci-app-openkill/root/usr/share/openkill/openkill_capabilities.sh \
  luci-app-openkill/root/usr/share/openkill/openkill_zerotier.sh \
  luci-app-openkill/root/usr/share/openkill/runtime.sh \
  luci-app-openkill/root/usr/share/openkill/openkill_config_normalize.sh \
  luci-app-openkill/root/usr/share/openkill/dependencies.conf \
  luci-app-openkill/root/usr/share/openkill/yml_proxys_get.sh \
  luci-app-openkill/root/usr/share/openkill/yml_proxys_set.sh \
  luci-app-openkill/luasrc/model/cbi/openkill/settings.lua \
  luci-app-openkill/luasrc/model/cbi/openkill/servers-config.lua \
  luci-app-openkill/luasrc/view/openkill/server_url.htm \
  luci-app-openkill/root/usr/share/openkill/res/default.yaml \
  README.md; do
  need_file "$file"
done

for file in \
  "$ROOT_DIR/scripts/install-openkill.sh" \
  "$ROOT_DIR/scripts/check-openkill-i18n.sh" \
  "$ROOT_DIR/luci-app-openkill/root/etc/init.d/openkill" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_core.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_update.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_watchdog.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_watchdog_stream.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_validate.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_semantic_check.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_capabilities.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_zerotier.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/runtime.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_config_normalize.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/yml_proxys_get.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/yml_proxys_set.sh" \
  "$ROOT_DIR/luci-app-openkill/root/etc/uci-defaults/luci-openkill"; do
  sh -n "$file" || fail "shell syntax error: ${file#$ROOT_DIR/}"
done

sh "$ROOT_DIR/scripts/check-openkill-i18n.sh" >/dev/null || fail 'Chinese UI catalog validation failed'

pkg_version=$(sed -n 's/^PKG_VERSION:=//p' "$ROOT_DIR/luci-app-openkill/Makefile" | head -n 1)
project_version=$(sed -n 's/^PROJECT_VERSION="\([^"]*\)"/\1/p' "$ROOT_DIR/scripts/install-openkill.sh" | head -n 1)
readme_version=$(sed -n 's/^当前版本：`\([^`]*\)`.*/\1/p' "$ROOT_DIR/README.md" | head -n 1)
case "$pkg_version" in 2026-[0-9][0-9][0-9][0-9]) ;; *) fail "invalid package version: $pkg_version" ;; esac
[ "$pkg_version" = "$project_version" ] || fail "installer/package version mismatch"
[ "$pkg_version" = "$readme_version" ] || fail "README/package version mismatch"

# The old Smart fork and generated core branch must not be part of the active
# download path.  Keep this check scoped to runtime/distribution files so
# historical notes do not block a release.
for file in \
  "$ROOT_DIR/scripts/install-openkill.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_core.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_update.sh"; do
  if grep -Eiq 'vernesong/OpenClash|vernesong/mihomo|mihomo-oix|refs/heads/core' "$file"; then
    fail "legacy upstream/core path remains in ${file#$ROOT_DIR/}"
  fi
done
if grep -Eq '^[[:space:]]*\+ruby-json([[:space:]]|$)' "$ROOT_DIR/luci-app-openkill/Makefile"; then
  fail 'ruby-json is still a hard package dependency'
fi

for file in \
  "$ROOT_DIR/luci-app-openkill/root/etc/init.d/openkill" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_watchdog.sh" \
  "$ROOT_DIR/luci-app-openkill/luasrc/controller/openkill.lua"; do
  if grep -Fq 'pidof clash' "$file"; then
    fail "legacy clash-only health check remains in ${file#$ROOT_DIR/}"
  fi
done

grep -Fq 'openkill_core_ready' "$ROOT_DIR/luci-app-openkill/luasrc/controller/openkill.lua" \
  || fail 'controller API readiness check is missing'
grep -Fq 'openkill_config_normalize.sh' "$ROOT_DIR/luci-app-openkill/root/etc/init.d/openkill" \
  || fail 'UCI normalization hook is missing'
grep -Fq 'OPENKILL_REQUIRED_COMMON' "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/dependencies.conf" \
  || fail 'dependency manifest is missing'

# Feed routing and Mihomo delivery must remain both ABI-safe and verifiable.
if ! grep -Fq 'dl.openwrt.ai must remain unchanged' "$ROOT_DIR/scripts/install-openkill.sh"; then
  fail 'installer may rewrite vendor firmware feeds'
fi
if ! grep -Fq 'sha256sum "$PARTIAL_FILE"' \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_core.sh"; then
  fail 'official Mihomo archive SHA256 verification is missing'
fi
if grep -Fq 'MetaCubeX/mihomo@${CORE_LV}' \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_core.sh"; then
  fail 'invalid jsDelivr-style Mihomo release asset path remains'
fi

for needle in \
  'feature_h2c' 'feature_shadowquic' 'feature_masque' 'feature_amnezia_wg' \
  'feature_anytls_metadata' 'feature_bbr3' 'feature_zerotier' \
  'openkill_capabilities.sh' 'openkill_zerotier.sh' 'shadowquic' \
  'amnezia-wg-option' 'client-metadata' 'ip-stack' 'type: zerotier' \
  'zerotier_network' 'zerotier_orbit'; do
  if ! grep -Fq "$needle" \
    "$ROOT_DIR/luci-app-openkill/root/etc/config/openkill" \
    "$ROOT_DIR/luci-app-openkill/luasrc/model/cbi/openkill/settings.lua" \
    "$ROOT_DIR/luci-app-openkill/luasrc/model/cbi/openkill/servers-config.lua" \
    "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/yml_proxys_get.sh" \
    "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/yml_proxys_set.sh"; then
    fail "optional capability marker is missing: $needle"
  fi
done

for needle in 'exportShadowQUIC' 'parseShadowQUIC' 'shadowquic_quic_versions'; do
  grep -Fq "$needle" "$ROOT_DIR/luci-app-openkill/luasrc/view/openkill/server_url.htm" \
    || fail "ShadowQUIC URL support is missing: $needle"
done

# The generated default config keeps external-ui under /usr/share/openkill.
# Both the standalone preflight and the procd service must grant Mihomo the
# same path allow-list, otherwise startup is rejected before listeners open.
if ! grep -Fq 'SAFE_PATHS="/usr/share/openkill:/etc/ssl:/tmp"' \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_validate.sh"; then
  fail 'Mihomo preflight SAFE_PATHS allow-list is missing'
fi
if ! grep -Fq 'procd_set_param env SAFE_PATHS=/usr/share/openkill:/etc/ssl:/tmp' \
  "$ROOT_DIR/luci-app-openkill/root/etc/init.d/openkill"; then
  fail 'OpenKill service SAFE_PATHS allow-list is missing'
fi

# The shipped template must not expose a controller, wildcard CORS policy,
# sample credentials, or an active named pipe before UCI has been applied.
if grep -Eq "^[[:space:]]*(allow-lan:[[:space:]]*true|bind-address:[[:space:]]*[\"']?\\*|external-controller:[[:space:]]*0\\.0\\.0\\.0|external-controller-pipe:)" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/res/default.yaml"; then
  fail 'unsafe active controller defaults remain in default.yaml'
fi
if grep -Fq '    - "*"' "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/res/default.yaml" || \
   grep -Fq 'username:password' "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/res/default.yaml"; then
  fail 'wildcard CORS or sample credentials remain in default.yaml'
fi
for needle in 'dashboard_bind_address' 'dns_listen_address' 'tun_auto_route' 'tun_auto_redirect' \
  'tun_auto_detect_interface' 'tun_strict_route' 'tun_endpoint_independent_nat' 'Config transaction aborted'; do
  grep -Fq "$needle" \
    "$ROOT_DIR/luci-app-openkill/root/etc/config/openkill" \
    "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/yml_change.sh" \
    "$ROOT_DIR/luci-app-openkill/luasrc/model/cbi/openkill/settings.lua" \
    || fail "stability/network control is missing: $needle"
done

if command -v ruby >/dev/null 2>&1; then
  ruby -ryaml -e 'YAML.load_file(ARGV[0]); exit 0' \
    "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/res/default.yaml" \
    || fail 'default.yaml is not valid YAML'
fi

printf 'OpenKill validation passed (%s).\n' "$pkg_version"
