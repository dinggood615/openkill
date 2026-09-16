#!/bin/sh
# Assert the development/RC/release workflow separation.
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$ROOT_DIR"
fail() { echo "ci-gate: $*" >&2; exit 1; }

need() { [ -f "$1" ] || fail "missing workflow or gate: $1"; }
need .github/workflows/validate.yml
need .github/workflows/build-openkill.yml
need .github/workflows/compile_new_ipk.yml
need scripts/check-version-bump.sh
need scripts/publish-package.sh

# Development CI is push/PR driven and must never publish.
grep -Fq 'name: OpenKill Development CI' .github/workflows/validate.yml || fail 'development CI name missing'
grep -Fq 'pull_request:' .github/workflows/validate.yml || fail 'development CI pull_request trigger missing'
grep -Fq 'push:' .github/workflows/validate.yml || fail 'development CI push trigger missing'
if grep -Eq 'publish-package\.sh|release_gate' .github/workflows/validate.yml; then
    fail 'development CI contains release behavior'
fi

# RC build is opt-in and artifact-only.
grep -Fq 'name: OpenKill RC Build' .github/workflows/build-openkill.yml || fail 'RC workflow name missing'
grep -Fq 'workflow_dispatch:' .github/workflows/build-openkill.yml || fail 'RC workflow is not manual'
if grep -Fq 'publish-package.sh' .github/workflows/build-openkill.yml; then
    fail 'RC workflow publishes a release'
fi

# Formal release is manual, explicitly gated, and owns the version comparison.
grep -Fq 'name: OpenKill Formal Release' .github/workflows/compile_new_ipk.yml || fail 'release workflow name missing'
grep -Fq 'workflow_dispatch:' .github/workflows/compile_new_ipk.yml || fail 'release workflow is not manual'
if grep -Eq '^  push:|^    branches:' .github/workflows/compile_new_ipk.yml; then
    fail 'formal release still has a push trigger'
fi
grep -Fq 'release_gate:' .github/workflows/compile_new_ipk.yml || fail 'release_gate input missing'
grep -Fq 'Require explicit release gate' .github/workflows/compile_new_ipk.yml || fail 'release gate step missing'
grep -Fq 'check-version-bump.sh' .github/workflows/compile_new_ipk.yml || fail 'version bump gate missing'
grep -Fq 'inputs.release_gate == true && inputs.publish == true' .github/workflows/compile_new_ipk.yml || fail 'publish is not release-gated'

git diff --check
printf 'CI_WORKFLOW_SEPARATION_GATE=PASS\n'
printf 'OpenKill CI workflow separation passed.\n'
