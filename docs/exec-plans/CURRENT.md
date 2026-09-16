# Current execution plan: authorized local delivery and GitHub release

## R2C device baseline checkpoint (blocked before writes)

- Phase: `PHASE_3E2D2D_R2C_DEVICE_BASELINE_HOLD_WITH_SEMANTIC_UCI_GATE`.
- Observed local HEAD: `2592088787a8f2fce87e20e80a355d0dfec4d69c`; the working
  tree was clean and `566fa82` remains an ancestor.  The delta from
  `455f463` is limited to the R2B lifecycle test, its documentation, the
  execution-plan/test-gate records, and CI registration; no runtime, package,
  DNS, renderer, init, network, firewall, or installer source changed.
- `preflight-openkill.sh`, `local-gate.sh`, `ci-gate.sh`, and
  `test-uci-lifecycle.py` passed (18/18).  No product semantic drift was
  found after D2C.
- The only device contact was the authorized `openkill-test-102` alias using
  BatchMode/IdentitiesOnly.  Read-only evidence matched the required clean
  stopped baseline: package `2026-1128`, OpenKill inactive, Mihomo 0, no TUN,
  no OpenKill pref-1888/table-354 state, no 7874 listener, the configured
  target `/etc/openkill/config/3e2-safe.yaml` absent, shadow unset, and the
  existing UCI path/hash intact.  Key production file hashes matched the
  current 2026-1128 source.
- The R2C hard configuration gate cannot be satisfied from the project
  source: no approved `3e2-safe.yaml`, generator output, tracked-history file,
  or project-generated copy matching
  `e894c2f7918038080ca05baa1311c8d7336e2a1497ce3324b767238fe7c76b05` exists.
  The device's leftover generated `/etc/openkill/3e2-safe.yaml` is a different
  hash and is not an approved, secret-free candidate; it was not reused.
- Result: `CONFIG_RECONSTRUCTION_DRIFT`.  The run stopped before transfer,
  package installation, configuration materialization, service start, UCI,
  nft, route, rule, DNS, network, or reboot writes.  The next resume requires
  an exact approved candidate (or a committed deterministic generator) and a
  re-run of the local hash/validation gates before any device write.

## R2B local UCI lifecycle checkpoint (observed before this change)

- Phase: `PHASE_3E2D2D_R2B_LOCAL_STARTUP_UCI_MUTATION_CONTRACT_RECONCILIATION`.
- Observed starting HEAD: `455f46309e30b7931cc2598bb16bfef5fc7ae688`;
  working tree clean; `566fa82` remains an ancestor. Devices were not accessed.
- The R2A whole-file running hash gate was too strong.  The checked-in start
  path intentionally records reversible dnsmasq backups, runtime/fallback
  metadata, a transient failure marker, one-shot overwrite state and the
  firewall include; the DHCP package receives the corresponding dnsmasq
  redirect.  Formal stop restores the reversible fields, converges lifecycle
  markers to their inactive value and intentionally retains resolver backup
  metadata, which is the convergence boundary.
- A field-level contract is now covered by `scripts/test-uci-lifecycle.py` and
  `docs/dev/phase-3e2d2d-r2b-uci-lifecycle.md`.  The full local matrix and
  Development CI include that focused suite.  The contract keeps user fields and a
  target-present `config_path` unchanged, requires exact OpenKill/DHCP runtime
  deltas, rejects unclassified writes, and requires stop convergence.
- Local verification for this checkpoint: `scripts/test-uci-lifecycle.py`
  passes 18/18; `test-autonomous-workflow.py`, the Development CI static suite,
  WSL runtime/installer/network/snapshot/Stage-D/core suites, `local-gate.sh`,
  and `git diff --check` also pass.  Shell-dependent suites report their
  expected Windows entry-point failures when invoked directly and pass through
  their WSL entry points.  No production behavior, version, release, or device
  state is changed.

### R2B next action

After the local gates pass, commit only this lifecycle contract/test/documentation
change.  `R2A_CAUSE=VALIDATION_GATE_MODEL_DEFECT`; no production UCI lifecycle
defect is currently evidenced.  The next authorized phase is
`R2C_DEVICE_BASELINE_HOLD_WITH_SEMANTIC_UCI_GATE`, which requires a separately
approved device run; this phase does not perform it.

## Final delivery checkpoint (observed before this documentation commit)

- Release candidate source: `c1e6cb1c55e7166040cc231f3a2c152e7cb14a1d`.
- Source version: `2026-1128`; reviewed notes: `docs/release/notes/2026-1128.md`.
- Exact-commit Development CI: run `34981702407` passed.
- Formal Release workflow: run `34981791062` passed with
  `release_gate=true`, `publish=true`, and `build_apk=false`.
- Published tag: `v2026-1128-ipk`, targeting the release-candidate commit.
- Published asset: `luci-app-openkill_2026-1128_all.ipk`, SHA-256
  `0581360bf8d88cbf2d49b8dae1c59b3cec5be44108f1fa6fca79c4e32e1ebedd`.
- Package channel `package:master/version` reports `v2026-1128`, and
  `master/latest-ipk.json` points to the same commit, asset and digest.
- Historical `v2026-1127-ipk` and its asset remain present and unchanged.
- Release transport requires version-specific reviewed notes and preserves
  existing tags/releases; development pushes do not publish.
- Device validation remains pending and was not accessed; CENTRAL_ACTIVE,
  central apply and packet-path testing remain forbidden/pending.

The resulting documentation checkpoint must be verified from Git after commit;
the commit hash is intentionally not predicted here.

## Current authorization and acceptance

The user authorized continuing unfinished local development through an explicit
RELEASE_GATE and GitHub publication. This supersedes the historical stop at
RELEASE_GATE below. Devices remain forbidden. Do not enable CENTRAL_ACTIVE,
apply central output, run packet tests, force push, delete tags/releases, or
overwrite unknown work. Device-dependent product work is deferred, not passed.

Observed starting HEAD: de9e27b09436e8441c6668e73d391d12e320df02; clean master.
Exact-commit Development CI passed: run 34977615717.

## Bounded delivery work

1. Audit post-D2C contracts and release transport. D2C local DNS reconciliation
   is already implemented; do not invent another DNS behavior change.
2. Fix release transport: preserve existing releases/tags and require reviewed
   version-specific notes before publication. Test missing-note failure before
   any external mutation and retained manual release gates.
3. Run the full local fixture matrix with supported Windows/WSL entry points,
   the local gate, and exact-commit Development CI; repair failures.
4. At RELEASE_GATE, select the next unused source version, update the three
   version authorities, and disclose unverified device behavior in notes.
5. Commit/push, verify exact-commit CI, explicitly dispatch the formal IPK
   release, verify downloaded asset SHA256 and package channel source identity.
6. Record outcome and stop after verified delivery. No automatic Phase 4.

## Remaining device-only gaps

Post-D2C actual-device semantic parity remains PENDING. Local frozen fixtures
cannot close it. TUN BC-04 remains the documented CURRENT behavior; Access
and TPROXY device coverage remain NOT_OBSERVED. REAL_PACKET_PATH=NOT_TESTED.
The release retains legacy writer authority and default-off shadow. These
limitations are mandatory release notes, not evidence of device readiness.

## Historical checkpoints (authorization below has been superseded)

# Current execution plan: post-D2C autonomous activation

## Active checkpoint

- Observed local and remote HEAD at activation: `43c1c45e32c63a9a62b3701caca8b7c33471bdaf`.
- Branch: `master`; clean at activation; origin verified through GitHub API.
- Resolve current HEAD with `git rev-parse HEAD` at every restart. The observed
  hash above is a baseline, not a claim that later checkpoint commits are stale.
- Migration: PASS. AUTONOMOUS_ACTIVATION=PASS.
- Current phase: post-D2C local/CI closure; executor STOPPED_AT_REAL_DEVICE_GATE.
- Latest verified implementation HEAD: `6f98a0966a339796b58b9e047d577f931a0db74d`.
- Development CI: PASS, run 34977442249 for that exact implementation HEAD.
- This documentation checkpoint is a descendant commit. Resolve its actual
  HEAD from Git and check its own CI on restart; do not recursively rewrite
  this file just to embed its own commit hash.
- Baseline Development CI: PASS, run 34974224074 for the observed hash.
- Branch protection: absent (GitHub API); this executor must enforce gates
  before pushing. Repository-side enforcement remains a known limitation.
- Version before this release gate: `2026-1127`; the authorized release candidate
  is `2026-1128`. No device access or Phase 4 writer handoff is authorized.

## Next autonomous action

REAL_DEVICE_GATE: post-D2C real-device semantic revalidation is required
before advancing the product toward Phase 4. No device access is authorized
in this execution. Local fixtures do not prove current device parity.

On restart, read AGENTS.md and this file, inspect HEAD/worktree and verify
Development CI for that exact HEAD. Repair any ordinary CI regression locally.
If CI is green and no new local work item exists, retain this gate and stop;
do not invent feature scope or repeatedly commit unchanged status.

Resume product development only when the user explicitly authorizes the
post-D2C device phase with a target and scope, or supplies a concrete local
work item. Central apply/packet-path work and RELEASE_GATE remain separate.
No unattended executor or recurring wakeup is claimed to be running while
this gate is active. Repository restart instructions are persisted and the
first autonomous local iteration and its CI repair have been completed.

## Activation implementation

- Development, RC and formal Release triggers/permissions inspected. Only
  the manual formal workflow can publish OpenKill packages; it requires both
  release inputs. No workflow has been dispatched by this activation.
- Development CI now runs the local gate and ten additional portable contract
  suites. Windows/WSL-specific regressions remain a required local matrix.
- Ordinary failures repaired: document Linux entry points for installer,
  runtime, network, snapshot and Stage D; isolate Stage D from host fw4 state
  with a record-only nft CLI, verifying check-only calls, error propagation
  and destructive-batch rejection. Production semantics remain unchanged.
- Core compatibility passed locally for v1.19.30 and latest resolved v1.19.31
  (8 TUN configuration cases per core; loopback API/auth, proxy and DNS smoke).
- No live router, central apply, version change or publication was performed.

## Historical migration baseline

- Repository: `D:\openkill`
- Branch: `master`
- HEAD: `1a9678bc99745fe6183fac92e0ad4995e36c384e`
- Working tree: clean at migration start
- Remote: `origin` → `https://github.com/dinggood615/openkill.git`
- Source version: `2026-1127`
- Historical release: `v2026-1127-ipk` (published by the former push-triggered
  workflow; retained as incident evidence)

The repository did not previously contain a project `AGENTS.md` or a
`docs/exec-plans/CURRENT.md`; this file establishes the missing source of
truth for autonomous work.

## Frozen product evidence

The local 3E.2D chain is complete through D2C: continuity and coherent
snapshot, BusyBox normalization and byte preflight, Mark ABI mapping, CURRENT
renderer, bounded parser, conditional inventory classification, ownership
projection, and DNS field reconciliation. The historical device target was
`.102`; this recovery performs no device access.

- D2A: required absence fails closed; conditional/inactive absence reaches the
  comparator.
- D2B: legacy-only WAN safety remains observed but out of CURRENT-owned parity;
  DNS fields are typed and 53 is never equated to 7874.
- D2C: the checked-in mode-1 contract is firewall/dnsmasq `:53` forwarding to
  Mihomo `127.0.0.1:7874`; direct mode-2 remains separate.
- Known gaps: device revalidation after D2C, documented TUN BC-04 behavior,
  access overlap not observed, TPROXY not observed, and no central apply or
  packet-path approval.

## CI recovery

The old compile workflow ran on every `master` push. Its first run after the
D2C commit failed because source `2026-1126` equaled the already published
channel version. The source was advanced to `2026-1127`, the package rebuilt,
and the release succeeded. This exposed the process defect: development pushes
could publish. The migration changes make development CI, manual RC build,
and manual formal release independent.

Latest known CI before this recovery: development validation, runtime matrix,
package compilation, publication, and cache cleanup all passed for
`1a9678b`; the published IPK digest was
`07723684b420b0f5c949f519cca06f91f115184d21ee6ae0354bf41494905b15`.

## Historical migration work items (completed)

1. Add the repository agent guide and execution-plan source of truth.
2. Separate development CI, artifact-only RC builds, and formal releases.
3. Add dependency-light preflight, local-gate, and CI-separation helpers.
4. Run the full local matrix and inspect the final diff.
5. Commit only these migration changes, push them, and verify development CI.

Do not bump the version, publish a release, access a device, continue Phase 4,
or change product semantics as part of this plan.

## Recovery result

The migration work is limited to workflow, documentation, and dependency-light
local gates. `OpenKill Development CI` is the only push/PR path; the RC build
is manual and artifact-only; the formal release is manual and requires both
release inputs. The source version remains `2026-1127` and no release was
published by this recovery.

The local gate, workflow contract tests, shell/YAML/version validation, core
compatibility matrix, installer, runtime, renderer, parser, shadow,
continuity, network, snapshot/FW4, Stage D, classifier, semantic, NFT IR, and
central-wiring suites pass under their supported Windows/WSL entry points.
The nft syntax suite also passes its explicit unavailable-tool contract when
the host cannot execute `nft`; no package was installed to change that result.
The only expected local skips are the existing Ruby-dependent tests.

No device or router was accessed. The historical `v2026-1127-ipk` publication
remains retained as incident evidence; this recovery does not delete, alter,
or republish it.

## Local activation result

- FULL_LOCAL_GATE=PASS: 343 tests across 22 fixture suites, with the three
  existing Ruby-dependent skips (installer 1, runtime 2); both core smoke
  matrices also passed. Per-suite logs remain local under `work/*.log`.
- The Windows nft-syntax suite passed its unavailable-CLI contract; it did
  not perform real parsing there. The shell-renderer suite passed its WSL
  check-only nft matrix. Neither result is live-device validation.
- Workflow/source gate and diff whitespace review passed. Source version
  remains 2026-1127. Implementation commits are pushed and exact-commit CI passed as recorded above.

## CI repair iteration

Activation commit `ee282e36b59b26df778c26ae38757ca8b71bc341` reached CI
run 34977232002. Its new network suite exposed a fixture dependency on the
runner's DNS servers. The repair supplies a documentation-range resolver and
stubs nslookup/resolveip so the existing getent fallback and timeout-preserves-
old-state assertions run deterministically without live DNS. This changes
only the test environment. The repaired commit passed CI run 34977442249; the gate can close.

## Closure evidence

- Implementation commits: `ee282e3` (activation and Stage D isolation),
  `6f98a09` (DNS fixture isolation); both pushed to origin/master.
- Passing run: https://github.com/dinggood615/openkill/actions/runs/34977442249
- Working tree was clean before this documentation-only checkpoint.
- REAL_DEVICE_VALIDATION=PENDING; RELEASE_GATE=NOT_REQUESTED.
- No version bump, package publication, tag change or real-device access.
