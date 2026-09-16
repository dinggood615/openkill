# Current execution plan: authorized local delivery and GitHub release

## R2C canonical device baseline hold (completed)

- Phase: `PHASE_3E2D2D_R2C_RESUME_WITH_CANONICAL_CONFIG`.
- Observed HEAD before and after the device run: `b8a7313a8b50afacc695d600db1a2916abddce73`; the working tree was clean and
  `566fa82` remains an ancestor.  The local chain from `455f463` through this
  checkpoint remains limited to tests, fixtures, documentation and CI; no
  production runtime, DNS, renderer, network, firewall, installer or package
  behavior changed.
- Local preflight, canonical verification, the 10-read config test, R2B's
  18/18 UCI lifecycle test, `local-gate.sh`, `ci-gate.sh`, and `git diff --check`
  passed.  The canonical source is `scripts/fixtures/3e2-safe.yaml`, 818
  bytes, SHA-256
  `9cd8d91750758823776df9c982c1e15f0baa1a72baa1792fa2f82c0df4d24a6e`.
- The only device contacted was the authorized `openkill-test-102` alias
  (192.168.1.102) with BatchMode/IdentitiesOnly.  No `.1`, `.101`, or other
  router was accessed.  The device already had package `2026-1128`; no package
  installation or UCI path write was performed.  Key production file hashes
  matched the verified 1128 package/source.
- The device began in the expected clean stopped state.  The canonical file
  was copied to `/etc/openkill/config/3e2-safe.yaml` with root ownership and
  mode 0600; device and local hashes matched.  `config_path`, `enable`,
  `dns_port`, TUN ownership/flags and other user fields stayed unchanged.
- A 300-second watchdog whose only rollback action was the formal OpenKill
  stop was armed before startup.  One controlled start reached OpenKill/procd
  running, one Mihomo process, `utun`, mark ABI `0x162/0xffffffff`, policy
  preference `1888`, table `354`, dnsmasq `:53` and Mihomo `127.0.0.1:7874`.
  A fresh SSH connection passed; the watchdog was cancelled immediately with
  rc 0, its process disappeared, no rollback marker was written, and the
  cancellation marker was present.
- The field-level UCI contract matched R2B exactly: lifecycle markers and
  dnsmasq relay/cache/AAAA state were the only expected runtime deltas;
  network UCI and `openkill-opkg` stayed unchanged, `last_start_failed` was
  absent, and no unknown delta was observed.  IPv6 main/default and
  source-specific route counts/hashes stayed stable with no NAT66 signal.
  Three 15-second read-only samples passed with identical runtime values;
  shadow remained OFF and no comparator, packet test, central apply, restart,
  or manual nft/ip/UCI operation was run.
- Success state is intentionally retained for the next phase: OpenKill is
  RUNNING, Mihomo=1, `utun` and ABI/DNS state are present, SSH is reachable,
  and the canonical config remains installed.  The next authorized action is
  `PHASE_3E2D2D_R3_PRODUCTION_SHADOW_DNS_SEMANTIC_REVALIDATION`; do not stop
  this baseline before that phase.

## R2D canonical D2D test-config provenance checkpoint (local-only)

- Phase: `PHASE_3E2D2D_R2D_CANONICAL_D2D_TEST_CONFIG_PROVENANCE_RECOVERY`.
- Observed starting HEAD: `0c2e01fd9bd298205c96d92a2f5f10f744232ed4`; the working
  tree was clean and `566fa82` remains an ancestor.  The audited commits after
  the D2C implementation contain only workflow, test, documentation, and
  release metadata changes; no production runtime, DNS, renderer, network,
  firewall, installer, parser, or ABI behavior changed.
- Device access was zero.  The earlier `.102` evidence remains frozen input;
  this recovery did not connect to `.102`, `.1`, `.101`, or any other router.
- The old R2A/R2C candidate bytes and SHA-256
  `e894c2f7918038080ca05baa1311c8d7336e2a1497ce3324b767238fe7c76b05` were
  searched for in the repository, reachable history, dangling project Git
  objects, and project test/build artifacts and were not found.  No hash
  chasing was performed, so `BYTE_EQUIVALENCE_TO_R2A=UNKNOWN`.
- A new canonical, deterministic, direct-only fixture is now persisted at
  `scripts/fixtures/3e2-safe.yaml`.  Its SHA-256 is
  `9cd8d91750758823776df9c982c1e15f0baa1a72baa1792fa2f82c0df4d24a6e`.
  `scripts/verify_3e2_safe_config.py` checks duplicate keys, binary NULs,
  sensitive/provider material, YAML structure, the frozen D2C DNS/Mark ABI
  contract, and optional Mihomo `-t` validation.  The focused regression
  `scripts/test-3e2-safe-config.py` passes 10/10 and proves one byte/semantic
  identity across ten reads.
- The fixture's semantic contract is equivalent to the frozen R2A candidate:
  TUN `utun`/`system`, OpenKill-owned `auto-route=false` and
  `auto-redirect=false`, IPv4/IPv6 and fake-IP DNS enabled, mode-1 firewall
  and dnsmasq listener `:53`, dnsmasq upstream `127.0.0.1#7874`, Mihomo
  listener `127.0.0.1:7874`, `MATCH,DIRECT`, and Mark ABI `0x162`,
  `0xffffffff`, table `354`, preference `1888`.  `53` and `7874` remain
  distinct semantic fields.  The fixture contains no credentials,
  subscriptions, tokens, private endpoints, or external provider URLs.
- The verifier passed YAML/duplicate-key/secret/semantic checks on Windows;
  official Mihomo v1.19.30 and the current latest v1.19.31 both passed `-t`
  through the existing WSL compatibility path.  The direct Windows
  invocation reports `NOT_AVAILABLE` for a Linux binary, as expected.  CI now
  installs its existing YAML test dependency and runs the verifier plus the
  focused suite.
- No production files, package version, release metadata, writer hashes, or
  device state changed.  The R2D commit is limited to the fixture, verifier,
  focused tests, CI registration, and documentation.  The prior R2C blocker
  is now specifically `CONFIG_PROVENANCE_PERSISTENCE_GAP`, not a claim that a
  human secret source is required.

### R2D result and next action

Local R2D gates and the full fixture matrix pass; the bounded change is ready
for commit.  On success, `CONFIG_SOURCE=CANONICAL_PROJECT_FIXTURE`,
`CONFIG_PROVENANCE=PERSISTED`, and `DEVICE_R2C_RESUME_READY=YES`; the next
authorized action is `PHASE_3E2D2D_R2C_RESUME_WITH_CANONICAL_CONFIG`, which is
the first phase allowed to access `.102`.  It must use this fixture and must
not rewrite production semantics.  No device or release action is taken in
R2D.

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

## Phase 3E.2D2D-R3 — production shadow DNS semantic revalidation

Observed on 2026-09-16. The source baseline was `1f9b3ef78cce76b47993b2339aa96751412de90e`, version `2026-1128`, with a clean worktree. The D2C commit `566fa82f0b814710b290c4bbd7e2385b689bd616` is an ancestor. The complete chain from `455f46309e30b7931cc2598bb16bfef5fc7ae688` to this baseline contains only workflow, fixture, test, and documentation changes; production runtime, init, renderer, parser, network, firewall, shadow wiring, installer, package, and version semantics are unchanged.

Only `openkill-test-102` (`192.168.1.102`) was accessed. No other router or device was connected, read, or modified. The existing R2C baseline remained running throughout: package `2026-1128`, OpenKill/procd running, one `/etc/openkill/clash` core process, `utun`, rules `1888: fwmark 0x162 lookup 354` for IPv4 and IPv6, one route in table 354 for each family, dnsmasq on `:53`, core listener `127.0.0.1:7874`, and canonical fixture SHA-256 `9cd8d91750758823776df9c982c1e15f0baa1a72baa1792fa2f82c0df4d24a6e`. Shadow remained disabled in persistent state and the canonical configuration hash was unchanged after the run.

The approved production entrypoint was `/usr/share/openkill/openkill_nft_shadow.sh:openkill_shadow_compare_nft`, reached through the init `openkill_shadow_stable_boundary`. It was activated only with an ephemeral `OPENKILL_NFT_SHADOW=1` environment and the existing read-only state/scalar inputs; no UCI, service, network, nft, route, rule, DNS, package, or central-apply operation was used. The coordinator performed its normal continuity snapshot, bounded capture (25 chains and 23 sets), parser, inventory classification, CURRENT renderer, directional compare, T2 continuity check, and bounded telemetry publication.

The first formal cycle returned `MISMATCH` (`rc=1`), not a capture, parse, stale, or command error. Four more independent official coordinator cycles produced the same result: 5/5 `MISMATCH`, 0 capture/parser errors, 0 stale results, 0 unknown syntax, and stable continuity identity `8f995a094bcf`. Inventory evidence retained all 24 absences as `required=0`, `conditional=22`, `inactive=0`, `optional=0`, `out_of_scope=2`, `unknown=0`; D2A classification therefore passed. Because the first cycle was not a complete MATCH, the 10-cycle success gate was not run.

The frozen typed DNS facts are still the D2C contract: actual and desired firewall LAN/router targets are `53`, dnsmasq listen is `53`, dnsmasq upstream is `127.0.0.1#7874`, and the core listener is `127.0.0.1:7874`; `53` and `7874` remain distinct fields. IPv4/IPv6 DNS scope is LAN plus router, SKGID loop prevention is `!=65534`, and the mark ABI is `0x162/0xffffffff`, table `354`, preference `1888`. The raw production result cannot publish these typed fields because its shell comparator still compares normalized chain/rule subsequences.

Bounded diagnostics attributed the stable mismatch to the production comparator model, with no device fix attempted:

- `WAN_SAFETY`: the actual-only `openkill_wan_input` and `openkill_wan6_input` reject rules are formally `OUT_OF_SCOPE_LEGACY_OBJECT`, but the shell comparator's `owned_chain()` treats every `openkill*` chain as owned.
- `DNS`: the actual `nat_output` IPv4/IPv6 `skgid != 65534` redirects to `:53` are physically consistent with the typed mode-1 path, while the CURRENT renderer expresses the path through the DNS jump/redirect topology; the shell comparator has no typed DNS or chain-transitive model.
- `POLICY_TOPOLOGY`/`OTHER`: additional legacy imperative spellings (mark formatting, protocol normalization, fake-IP/set references, and related chain forms) are stable raw topology differences, not evidence of a device renderer failure.

Accordingly, the phase result is `PARTIAL`: `FRAMEWORK=PASS`, `CURRENT_OWNED_PARITY=MISMATCH` for the official production path, and `DNS_PARITY=COMPARATOR_MODEL_GAP` for the typed interpretation. The device result is `DEVICE_SEMANTIC_MISMATCH` pending a local production-shadow ownership/DNS model integration. No 53/7874 equivalence, whitelist, fixture rewrite, parser change, renderer change, ownership deletion, or device hotfix was introduced.

Post-shadow health stayed PASS. All production-write counters were zero: nft configuration, routes, rules, UCI, network/firewall/fw4 reloads, dnsmasq/core/OpenKill restarts, package/config writes, central apply, and packet tests. Only bounded shadow temporary/telemetry files were created and then removed; no shadow process, lock, or temporary directory remained. The eight frozen writer hashes are unchanged. Canonical verification, the 10-case config suite, the 18-case UCI lifecycle suite, `local-gate.sh`, `ci-gate.sh`, `validate-openkill.sh`, and the focused production-shadow suite passed in their supported local environments. Linux-only or real-nft checks that cannot run under this Windows/WSL host remain environment-limited and are not treated as device evidence; no new unexplained skip was added.

`NEXT=PHASE_3E2D2D-R3A_LOCAL_PRODUCTION_SHADOW_OWNERSHIP_DNS_MODEL_RECONCILIATION` (local only; resolve the typed ownership/DNS projection before another device run). `CENTRAL_ACTIVE=NOT_APPROVED`, `CENTRAL_NFT_APPLY=NOT_APPROVED`, and `REAL_PACKET_PATH=NOT_TESTED` remain unchanged.

## Phase 3E.2D2D-R3A — local production shadow ownership/DNS model reconciliation

Observed on 2026-09-16 from baseline `34eebdca4d7f036cfe63c3931a6a0fee7951a55c`, version `2026-1128`, with a clean worktree before the R3A change. The D2C commit `566fa82f0b814710b290c4bbd7e2385b689bd616` remains an ancestor. No device or router was accessed in this phase.

R3's stable `MISMATCH` was reproduced as a comparator model gap. The old automatic shell comparator selected `nat_output` and every physical chain beginning with `openkill` through `owned_chain()`. That syntax scope was useful for bounded parsing but was being used as policy, so the legacy-only `openkill_wan_input` and `openkill_wan6_input` safety objects entered CURRENT equality. The same path compared raw chain/rule topology and had no independent DNS projection, even though the frozen actual and D2C desired DNS facts agree. This is `R3_CAUSE=PRODUCTION_COMPARATOR_MODEL_GAP`, not a device DNS defect.

R3A adds an additive, bounded typed path to `openkill_nft_shadow.sh`. The production shell reads the checked-in `shadow/semantic_model_v1.tsv` vocabulary and two line-oriented `OPENKILL_SHADOW_TYPED_INTENT_V1=1` sidecars produced from the completed capture/inventory and CURRENT renderer projections. Logical IDs, component, ownership class, active state, and semantic payload are compared; physical names are retained for full observation only. `CURRENT_OWNED` and active `CONDITIONAL_CURRENT` enter equality. `LEGACY_ONLY_SAFETY`, `FW4_BASE`, `INACTIVE_MODE`, `OPTIONAL_OBSERVATION`, and `OUT_OF_SCOPE` remain observed and hashed but are excluded from CURRENT-owned equality. `UNKNOWN`, invalid or duplicate rows, and missing typed DNS sources return the additive `MODEL_GAP` status (`rc=12`); the existing MATCH/MISMATCH/STALE/capture/render result numbers are unchanged.

The typed DNS projection keeps these fields independent: firewall LAN target, firewall router target, dnsmasq listen target, dnsmasq upstream target, Mihomo listener, loop prevention, IPv4 scope, and IPv6 scope. The D2C mode-1 values are firewall/listen `53`, upstream `127.0.0.1#7874`, and Mihomo `127.0.0.1:7874`; mode-2 direct behavior remains represented separately. No `53 == 7874` or transitive service equivalence was added. Each field carries a source description and owner, and a missing source is `MODEL_GAP` rather than an inferred value.

The shell path emits bounded model/version fields, short full-observation/current-owned/DNS hashes, parity, and counts only. It remains POSIX `/bin/sh` and BusyBox compatible with no Python, jq, Ruby, or other new runtime dependency. `openkill_shadow_semantic_model.py` is a development oracle only; differential tests compare its result with the shell path. The old raw automatic and explicit-bundle paths remain available for existing callers, while the typed production caller must provide both formal sidecars from the same coherent snapshot cycle.

Local evidence: the production coordinator replay with the sanitized R3/D2C fixture is `FRAMEWORK=PASS`, `CURRENT_OWNED_PARITY=MATCH`, `DNS_PARITY=MATCH`, `MODEL_GAP=NONE`; WAN safety observation is retained. The 14-case production typed-shadow suite passes; five positive shell cycles are stable (`MATCH=5/5`, one actual-owned hash, one desired-owned hash, one DNS hash pair), and the negative matrix is stable for three repetitions and distinguishes MISMATCH from MODEL_GAP. The Python oracle and shell result agree. D2A required/conditional absence behavior, D2B ownership projection, D2C DNS fields, R2B UCI lifecycle, canonical config, parser, renderer, IR, syntax, continuity, auto-state, BusyBox, network, snapshot/FW4, Stage D, runtime, installer, Core compatibility, local-gate, ci-gate, compileall, and diff-check pass in their supported local environments. Existing Ruby-dependent tests remain the only expected host skips; no new unexplained skip was introduced. `nft-c` was exercised where available and remains an environment-specific check in suites that cannot invoke it on this host.

Production impact is limited to the shadow observer/comparator and its additive manifest/telemetry: `PRODUCTION_SHADOW_OBSERVER_CHANGED=YES`, `PRODUCTION_LEGACY_WRITER_CHANGED=NO`, `DNS_WRITER_CHANGED=NO`, `ROUTING_WRITER_CHANGED=NO`, `FIREWALL_WRITER_CHANGED=NO`, `DATAPLANE_WRITE_BEHAVIOR_CHANGED=NO`, and `CENTRAL_WRITE_CALLSITE=0`. The eight frozen writer hashes remain unchanged. No version, package, release, tag, or workflow publication changed.

`PHASE_3E2D2D-R3A=PASS`; `LOCAL_R3_REPLAY=MATCH`; `PRODUCTION_TYPED_OWNERSHIP=READY`; `PRODUCTION_TYPED_DNS=READY`; `DEVICE_REVALIDATION_READY=YES`. The device phases remain partial until a separately approved device run consumes typed sidecars. `NEXT=PHASE_3E2D2D-R3B_DEVICE_PRODUCTION_SHADOW_TYPED_REVALIDATION`. `CENTRAL_ACTIVE=NOT_APPROVED`, `CENTRAL_NFT_APPLY=NOT_APPROVED`, and `REAL_PACKET_PATH=NOT_TESTED` remain unchanged.
