#!/bin/sh
# Fast repository preflight used before local gates and CI handoff.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
require_clean=0
if [ "${1:-}" = "--require-clean" ]; then
    require_clean=1
elif [ "${1:-}" != "" ]; then
    echo "Usage: $0 [--require-clean]" >&2
    exit 2
fi

cd "$ROOT_DIR"
[ -d .git ] || { echo 'preflight: not a git worktree' >&2; exit 1; }
head=$(git rev-parse HEAD)
[ -n "$head" ] || { echo 'preflight: HEAD is unavailable' >&2; exit 1; }
git diff --check
if [ "$require_clean" -eq 1 ] && [ -n "$(git status --porcelain)" ]; then
    echo 'preflight: working tree is not clean' >&2
    git status --short >&2
    exit 1
fi

pkg_version=$(sed -n 's/^PKG_VERSION:=//p' luci-app-openkill/Makefile | head -n 1)
project_version=$(sed -n 's/^PROJECT_VERSION="\([^"]*\)"/\1/p' scripts/install-openkill.sh | head -n 1)
readme_version=$(sed -n 's/^当前版本：`\([^`]*\)`.*/\1/p' README.md | head -n 1)
[ -n "$pkg_version" ] && [ "$pkg_version" = "$project_version" ] && [ "$pkg_version" = "$readme_version" ] || {
    echo 'preflight: version metadata is inconsistent' >&2
    exit 1
}
case "$pkg_version" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]) ;;
    *) echo "preflight: invalid version $pkg_version" >&2; exit 1 ;;
esac

printf 'OpenKill preflight passed (HEAD %s, version %s).\n' "$head" "$pkg_version"
