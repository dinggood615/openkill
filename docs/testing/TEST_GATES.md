# Test gates

Tests are layered so a documentation or workflow change does not require a
device.

## Fast local gate

```sh
sh scripts/preflight-openkill.sh
sh scripts/validate-openkill.sh
sh scripts/ci-gate.sh
python3 -m compileall -q scripts
```

## Full local matrix

Run the Python programs matching `scripts/test-*.py` from a Windows host when
they launch the repository's WSL/BusyBox harnesses. The matrix covers runtime,
installer, core compatibility, classifier and semantic contracts, NFT IR and
syntax, renderer, parser fixtures, continuity, self-sufficiency, shadow
runtime, network, snapshot/FW4, stage D, and central wiring. Also run
`git diff --check` and the shell syntax checks in `validate-openkill.sh`.

Expected skips are limited to the documented Ruby-dependent cases. A new
skip, xfail, warning downgrade, or device access is a gate failure.

## CI gate

Development CI must pass before merge. RC builds are reviewed as artifacts.
Formal release CI must pass its version gate, runtime matrix, package audit,
and publication steps. A failed gate is analyzed and repaired in source before
retrying; no package or device hotfix is used to bypass it.
