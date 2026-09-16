# Test gates

Tests are layered so a documentation or workflow change does not require a
device.

## Fast local gate

```sh
sh scripts/preflight-openkill.sh
sh scripts/validate-openkill.sh
sh scripts/ci-gate.sh
python3 -m compileall -q scripts
python3 scripts/verify_3e2_safe_config.py
python3 scripts/test-3e2-safe-config.py
```

## Full local matrix

Use Windows Python for the fixture suites that launch WSL/BusyBox.
Run `test-installer.py`, `test-runtime.py`, `test-network-model.py`,
`test-snapshot-fw4.py`, `test-stage-d.py` and `test-core.py` inside WSL
instead: these need Linux paths, shell executables or the Linux core binary.
For example, from PowerShell in the repository:

```powershell
python scripts/test-shadow-continuity.py
wsl --cd /mnt/d/openkill --exec python3 scripts/test-stage-d.py
wsl --cd /mnt/d/openkill --exec python3 scripts/test-core.py --release v1.19.30
wsl --cd /mnt/d/openkill --exec python3 scripts/test-core.py --release latest
```

Run every `scripts/test-*.py` suite with the corresponding entry point;
any nonzero exit fails the gate. Do not run the entire matrix with Windows
Python: a discovered bash executable alone does not make Windows paths and
CRLF scripts compatible with Linux. The matrix covers runtime,
installer, core compatibility, classifier and semantic contracts, NFT IR and
syntax, renderer, parser fixtures, continuity, self-sufficiency, shadow
runtime, network, snapshot/FW4, stage D, and central wiring. Also run
`test-uci-lifecycle.py`, `test-3e2-safe-config.py`, `git diff --check` and the
shell syntax checks in `validate-openkill.sh`.  The canonical D2D fixture and
its verifier are documented in
`docs/dev/phase-3e2d2d-r2d-canonical-config.md`; an approved Mihomo binary can
be supplied with `--mihomo <path> --require-mihomo` for the additional `-t`
check.  This is a local asset check and never contacts a device.

Expected skips are limited to the documented Ruby-dependent cases. A new
skip, xfail, warning downgrade, or device access is a gate failure.

## CI gate

Development CI must pass before merge. RC builds are reviewed as artifacts.
Formal release CI must pass its version gate, runtime matrix, package audit,
and publication steps. A failed gate is analyzed and repaired in source before
retrying; no package or device hotfix is used to bypass it.

## Activated development coverage

Development CI runs `local-gate.sh` and the autonomous-workflow,
classifier-contract, dataplane-semantic-spec, nft-ir, shadow-context-adapter,
shadow-semantic-model, dns-current-intent, network-model, snapshot-fw4 and
stage-d, and uci-lifecycle Python suites. Its existing
runtime/installer and two-core compatibility matrix remains required.
The full Windows/WSL fixture matrix is still a local gate; several harnesses
invoke `wsl.exe` directly and must not be silently skipped on Linux CI.

Stage D uses a record-only nft CLI fixture to assert check-only arguments,
error propagation, and rejection of destructive batches before CLI invocation.
It does not require or inspect a host fw4 table. Actual nft parsing remains
covered separately by the renderer/syntax suites and device validation.
