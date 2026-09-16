#!/bin/sh
# Developer gate: no network, device access, package publication, or version bump.
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$ROOT_DIR"

sh scripts/preflight-openkill.sh
sh scripts/validate-openkill.sh
sh scripts/ci-gate.sh

if command -v python3 >/dev/null 2>&1; then
    python3 -m compileall -q scripts
fi

printf 'LOCAL_POLICY_GATE=PASS\n'
printf 'OpenKill local gate passed.\n'
