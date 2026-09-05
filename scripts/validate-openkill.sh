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
  luci-app-openkill/root/etc/init.d/openkill \
  luci-app-openkill/root/usr/share/openkill/openkill_core.sh \
  luci-app-openkill/root/usr/share/openkill/openkill_update.sh \
  luci-app-openkill/root/usr/share/openkill/openkill_watchdog.sh \
  luci-app-openkill/root/usr/share/openkill/openkill_watchdog_stream.sh \
  luci-app-openkill/root/usr/share/openkill/openkill_validate.sh \
  luci-app-openkill/root/usr/share/openkill/res/default.yaml \
  README.md; do
  need_file "$file"
done

for file in \
  "$ROOT_DIR/scripts/install-openkill.sh" \
  "$ROOT_DIR/luci-app-openkill/root/etc/init.d/openkill" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_core.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_update.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_watchdog.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_watchdog_stream.sh" \
  "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/openkill_validate.sh"; do
  sh -n "$file" || fail "shell syntax error: ${file#$ROOT_DIR/}"
done

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

if command -v ruby >/dev/null 2>&1; then
  ruby -ryaml -e 'YAML.load_file(ARGV[0]); exit 0' \
    "$ROOT_DIR/luci-app-openkill/root/usr/share/openkill/res/default.yaml" \
    || fail 'default.yaml is not valid YAML'
fi

printf 'OpenKill validation passed (%s).\n' "$pkg_version"
