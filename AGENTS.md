# OpenKill agent guide

This repository is the source of truth for OpenKill. Read the current
execution plan in `docs/exec-plans/CURRENT.md` before changing code.

## Boundaries

- Keep production changes POSIX `/bin/sh`, OpenWrt and BusyBox compatible.
- Do not access routers or real devices unless a plan explicitly authorizes a
  device phase. Local fixtures and the checked-in source are the default.
- Never enable `CENTRAL_ACTIVE`, apply central nft state, or run packet-path
  tests as part of ordinary development.
- Do not change legacy writers, DNS behavior, ABI constants, parser grammar,
  or continuity semantics without a plan that names the affected contract.

## Workflow

- Development pushes and pull requests run `OpenKill Development CI` only.
- Candidate artifacts use the manual `OpenKill RC Build` workflow and are not
  published.
- Releases use the manual `OpenKill Formal Release` workflow with both
  `release_gate` and `publish` enabled. Only that gate may advance the source
  version or publish a package.
- Run `sh scripts/local-gate.sh` before committing. Review `git diff` and
  `git diff --check`, then commit only the requested scope.

Prefer small, explainable commits. Record unresolved gaps in the current plan
instead of hiding them in tests or adding ad-hoc equivalence rules.
