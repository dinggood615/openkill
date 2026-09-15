# Autonomous development workflow

The repository has three independent workflow classes.

## Development CI

`OpenKill Development CI` (`.github/workflows/validate.yml`) runs for pushes
and pull requests. It validates source metadata and runs the reusable runtime
and compatibility matrix. It has read-only contents permission and contains
no package publication step.

## RC build

`OpenKill RC Build (OpenWrt SDK Audit)` (`.github/workflows/build-openkill.yml`)
is manual and artifact-only. It builds the checked-out source with the
configured OpenWrt SDK, audits the resulting package, and never updates the
release or package branches.

## Formal release

`OpenKill Formal Release` (`.github/workflows/compile_new_ipk.yml`) is manual.
The operator must set both `release_gate=true` and `publish=true`. The gate
checks that Makefile, installer, and README versions agree and that the source
version is strictly newer than the published package channel before building
or publishing. A normal push cannot enter this workflow.

The source version is a release input, not a development cache-buster. Normal
development commits keep the current version. Version changes are reviewed
and shipped only through the formal release gate.

## Local commands

Use `sh scripts/preflight-openkill.sh` for a fast repository check,
`sh scripts/local-gate.sh` for the static local gate, and
`sh scripts/ci-gate.sh` to verify workflow separation. The full test matrix is
listed in `docs/testing/TEST_GATES.md`.
