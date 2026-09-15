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

## Autonomous continuation

- At each restart read this guide and CURRENT.md, then inspect actual HEAD,
  working tree and CI. Recorded commit IDs are evidence, never a substitute
  for `git rev-parse HEAD`. Preserve unknown user changes.
- Execute the next local action, repair ordinary failures, run the appropriate
  gates, review the diff, and commit/push the bounded development change.
  Verify Development CI for that exact commit before recording CI=PASS.
- Update CURRENT.md with evidence, completed work and the next action before
  ending an iteration. A commit cannot contain its own hash: distinguish the
  observed baseline from the resulting HEAD resolved from Git.
- Continue local development until HUMAN_BLOCKER (missing decision/access),
  REAL_DEVICE_GATE (new device evidence required), or RELEASE_GATE (version
  change/publication required). Record the reason and exact resume condition.
  Ordinary test failures are repair work, not human blockers. Do not invent
  product scope to avoid a legitimate gate.
- This activation forbids device access, version changes and publication.
  Historical device approvals do not authorize this execution.
