# Current status

CURRENT_HEAD: `f70dee5e479d6a1f92270f6eed6934e2e1ae5001` (observed master HEAD before this status update)
VERSION: `2026-1129`
CURRENT_PHASE: `REVIEW_FIX_LOCAL_GATE_RC_DEVICE_STAGE_A`
CURRENT_STATUS: `Master-only implementation re-review and exact-commit CI are green; direct RC package build succeeds and its runner-compatible audit is being repaired before the authorized 192.168.1.103 device phase`
BLOCKER: `NONE_FOR_LOCAL_SCOPE` — the direct package build produced a matching IPK, while the RC audit failed because the runner has no rg binary; device installation remains gated on a completed audited RC IPK
DEVICE_STATE: `192.168.1.103` is Kwrt 25.12-SNAPSHOT x86/64 on VMware, dnsmasq 2.93 and firewall4 2025.03.17~b6e51575-r2 are present, PassWall is configured/enabled but its global runtime switch is `0` and no proxy listener is running; only read-only inspection and SSH public-key installation were performed
DEVICE_RETRY_READY: `YES_WITH_RC_IPK` (SSH BatchMode key access is ready; install only after package hash, backup and rollback checks)
NEXT_ACTION: `commit the runner-compatible RC audit, verify exact-commit Development CI, trigger the non-published RC IPK workflow from master, then begin the recorded device backup/install gate`
RESULTING_HEAD: resolve with `git rev-parse HEAD` after this status-only update; this status records the pre-commit observation above
CENTRAL_ACTIVE: `NOT_APPROVED`
CENTRAL_NFT_APPLY: `NOT_APPROVED`
REAL_PACKET_PATH: `NOT_TESTED`
DEVICE_INSTALL_AUTHORIZATION: `APPROVED_FOR_192.168.1.103_ONLY`
DEVICE_INSTALL_SCOPE: `backup, upload/install matching RC IPK, bounded OpenKill config/service tests, limited DNS/outbound observations; preserve PassWall and do not change WAN/VMware`
DEVICE_ROLLBACK_CONTRACT: `restore backed-up UCI/files, remove candidate package, restore service enable/runtime state, verify SSH; never use broad bypass or firewall reset`
IMPLEMENTATION_CONTRACTS_UNDER_REVIEW: `DNS listener split and dnsmasq stable section identity; legacy writer continuity; route-set IPv4/IPv6 atomicity and empty-set fail-closed behavior; Mihomo DNS parser/strict bootstrap; adblock DNS/core same-generation and allow/block priority; RustDesk scoped domains; status only after validate/apply`

## RC audit runner compatibility (2026-09-18)

- Observed master baseline before this status update is
  `f70dee5e479d6a1f92270f6eed6934e2e1ae5001`. Development CI run
  `35312752594` passed for that exact commit after the direct package Makefile
  boundary was added; the package build itself no longer expands the full
  kernel/module graph.
- RC run `35312882508` completed the direct build and produced exactly one
  `luci-app-openkill_2026-1129_all.ipk` under the SDK package feed, but its
  audit step exited 127 because the GitHub runner image does not provide
  `rg`. The complete log is retained at `D:\\openkill-rc-build6.log`.
- The pending bounded fix replaces only undeclared `rg` calls in the RC input,
  package and sensitive-content audits with recursive POSIX/GNU `grep` using
  equivalent file filters. It does not weaken metadata, conffile, stale
  reference, maintainer-script, CSS cache-buster or sensitive-content checks.
  The autonomous workflow test now asserts that this RC workflow has no `rg`
  dependency.
- Local evidence before committing this fix: workflow contract `10/10`,
  optimization/DNS/UCI focused suites pass, `git diff --check` passes and the
  WSL `scripts/local-gate.sh` passes. The resulting commit and its exact
  Development CI run must be recorded after Git resolves the new HEAD.

## Re-review and local behavior hardening (2026-09-18)

- Re-reviewed the actual `d481e444f87aa842a8893da81801ed71438d9689` source rather
  than relying on the earlier `b3fa5b6` report baseline. The nft and legacy
  region paths had separate flushes before loading the next set, and the nft
  path used hard-coded `/etc/openkill` files even when small-flash mode selected
  `/tmp`. Both are repaired. Existing sets now receive one checked nft batch or
  one ipset restore stream; a failed update returns an error without replacing
  an existing valid set. The initial missing-set case still fails closed.
- The adblock path now canonicalizes anti-AD text/Clash YAML domain payloads
  once, writes one local YAML rule-provider and one dnsmasq fragment from that
  generation, and records a source SHA-256 in `/tmp/openkill-adblock.state`.
  Allow-list domains are removed before both outputs are generated; user block
  entries are inserted before the provider. A misleading Mihomo `PASS` rule and
  the independent remote provider download were removed. MRS is not exposed as
  an effective format until the target core binary-provider ABI is verified.
  The generator now resolves the same generated dnsmasq `conf-dir` section ID
  used by the legacy writer before placing its fragment, so a second or
  reordered dnsmasq instance cannot silently receive the policy.
- Strict DNS now rejects `http://`, appends `#RULES` by structured suffix
  handling, applies the rule suffix to direct/policy resolvers, and aborts YAML
  replacement when no selectable proxy group exists. DNS bootstrap remains the
  documented direct node-resolution exception; no ordinary failure path adds
  WAN DNS or silently downgrades to plaintext.
- Added `scripts/test-openkill-optimization.py`, covering atomic update wiring,
  allow/provider semantics, strict-DNS guards and exact route validator fixtures
  for IPv4 `0/8/32`, IPv6 `::/0` and `/128`, malformed octets, and repeated
  compression. The validator fixtures pass under WSL and BusyBox `awk` on the
  authorized target (`busybox_v4=0 busybox_v6=0 bad4=1 bad6=1`). Changed
  production scripts also pass target `sh -n`.
- Focused UI/classifier suites remain green (`23/23`, `1/1`, `17/17`). The
  local policy gate passes after the repository's pre-existing CRLF typed
  semantic manifest is temporarily normalized in an isolated gate copy and
  restored byte-for-byte; the manifest itself is unchanged. No package or
  OpenKill service has been installed on the device yet.
- Pre-install backup completed on the authorized target only. Protected host
  directory: `D:\\openkill-device-backups\\20260918-preinstall-1619f31`; archive
  SHA-256: `0E49D13E3ED57D944EA09E7D4EB17778AEB710DE73D034480071A181CE0A227C`.
  The archive contains selected UCI/configuration and network baseline files;
  Dropbear host private keys were excluded. BatchMode SSH was rechecked after
  backup and PassWall remains enabled at the service layer with no OpenKill or
  Mihomo process present.
- The bounded implementation commits are `1619f315397d287cd0f7b8a8fd6ed6c7c0c22820`,
  `f3409c644e7053db4de53b2578f74f691fe8f939`, and the documentation status
  commits through `f883b70a5eff618168e1bb5aac4169435f7ddc65`. The disposable
  `codex/openkill-device-validation` branch was deleted locally and remotely;
  all delivery now uses `master`. Development CI run `35308100055` passed for
  exact commit `f65d4267d9ae0bbfe7aa046dc02d91b8ca2117f2`: static, v1.19.30,
  and latest compatibility jobs all succeeded. No device package installation
  has been attempted.

## RC package boundary repair (2026-09-18)

- Master-only delivery is confirmed: `codex/openkill-device-validation` was
  deleted locally and remotely; the only delivery branch is `master`.
- Development CI run `35309191407` passed for exact commit
  `770fee5373d3adf53afacbf7d9a3421b4321a51f` (static, v1.19.30 and latest).
  The first RC run `35308420431` and second run `35309306971` were canceled
  after fresh 25.12 SDK jobs expanded to Rust/LLVM host work (`3898` tasks)
  even with `CONFIG_USE_APK=`. Logs are retained outside the repository at
  `D:\\openkill-rc-build.log` and `D:\\openkill-rc-build2.log`.
- The RC workflow is now being narrowed to the known-good SDK boundary:
  serial `make CONFIG_USE_APK= package/luci-app-openkill/{clean,compile}`
  without top-level `-j`, followed by the existing IPK audit. This is a
  workflow-only change; it does not change production package dependencies.
- The next evidence required is a completed RC run that produces exactly one
  audited `luci-app-openkill_2026-1129_all.ipk` from the resulting master
  commit. Until that exists, no device upload or installation is allowed.

## Exact-commit DNS contract repair (2026-09-18)

- The first CI run for `f883b70` failed only in the static DNS contract suite.
  The production code had already moved to a stable `DNSMASQ_UCI` section and
  separate dnsmasq listener port, while the shadow UCI stub and lifecycle tests
  still asserted anonymous `@dnsmasq[0]` selectors and an old redirect
  placeholder. The fixture now models both selectors but returns the stable
  listener, and the source contracts assert the stable section variable.
- Local evidence after the repair: DNS intent `10/10`, UCI lifecycle `18/18`,
  optimization `PASS`, changed-script BusyBox/POSIX syntax checks, isolated
  LF local-gate `PASS`, and the full Development CI matrix `PASS` on
  `f65d4267d9ae0bbfe7aa046dc02d91b8ca2117f2`.
- This repair changes tests and the record-only harness only; production DNS
  ownership, stable-section mapping, and listener split are unchanged.

## Local optimization phase (2026-09-18)

- Phase: `PHASE_LOCAL_DNS_REGION_ADBLOCK_RUSTDESK_HARDENING`.
- Scope: local source changes only. The requested work covers stable dnsmasq
  section selection, safer IPv4/IPv6 region-pass handling, IPv6 transport
  matching, optional anti-AD Mihomo rule-provider integration, and a bounded
  RustDesk compatibility exception. No device, packet-path, CENTRAL_ACTIVE,
  or central nft operation is permitted in this phase.
- Contracts: preserve the existing DNS listener split (`dnsmasq :53` to
  Mihomo `127.0.0.1:7874`), the OpenKill/Mihomo ownership mutex, current Mark
  ABI, legacy writer continuity, and shadow read-only semantics. New adblock
  and RustDesk controls must fail closed and remain independent of DNS
  privacy and region bypass decisions.
- Implemented locally: stable dnsmasq instance identity; fail-closed and
  atomically validated IPv4/IPv6 route sets; fw4 nftset capability guard;
  extension-header-safe IPv6 protocol matching; split/strict encrypted DNS
  filtering; anti-AD DNS plus Mihomo provider rules with user exceptions;
  scoped RustDesk ID/relay domain rules; effective-state reporting in LuCI;
  and quick-start invalidation for the new generator.
- Evidence: shell syntax checks passed for all five changed production
  scripts; UI contract `23/23`, UI interaction `1/1`, classifier contract
  `17/17`, and `git diff --check` passed. `scripts/local-gate.sh` passed on
  the same source after temporarily normalizing the pre-existing CRLF copy of
  `shadow/semantic_model_v1.tsv`; the native Windows checkout otherwise fails
  its typed-manifest header check before evaluating this diff. The manifest
  was restored byte-for-byte and remains unmodified.
- Device and real RustDesk/DNS leak verification remain `NOT_RUN` until an
  explicitly approved device phase. Exact-commit Development CI is still
  pending because this local environment has not dispatched the workflow.
- Observed implementation baseline was `b3fa5b6fcdba4074b78e182516fa612a73652b7d`;
  resulting local implementation commit is
  `b3a3425c6495f7e42da1c683055a8fcfde5b6a4c`.
- Resume condition: after local gates, record the observed resulting HEAD and
  keep native takeover mappings, real DNS egress, anti-AD effectiveness and
  RustDesk relay/UDP behavior as device-validation items.

## Approved OpenWrt device phase (2026-09-18)

- Authorization: the user explicitly authorized testing the local OpenWrt
  router at `192.168.1.103` and requested direct SSH-key access. This phase is
  limited to that target; no other router or real device may be contacted.
- Initial scope: establish a dedicated local ed25519 key, install only its
  public key through the supplied administrator password, then perform
  read-only inventory, package/config inspection, service status, generated
  rule inspection, DNS listener/upstream inspection, and bounded synthetic
  configuration checks. The password must not be stored in the repository,
  command files, logs, or reports.
- Explicitly forbidden in this phase: `CENTRAL_ACTIVE`, central nft apply,
  packet-path tests, traffic capture, firewall/route/DNS mutation beyond the
  requested SSH public-key installation, package installation, service
  restart, WAN changes, and any broad bypass rule.
- Contracts under observation: DNS listener split and privacy modes, one
  transparent-proxy owner, Mark ABI, IPv4/IPv6 region-set generation and
  fail-closed behavior, adblock last-valid fallback, RustDesk scoped rules,
  and procd/legacy-writer continuity. Any mutation needed for a later test
  requires a separate explicit device step and rollback record.
- Resume condition: complete key setup and read-only preflight first; stop and
  record `HUMAN_BLOCKER` if SSH is unavailable or the supplied credentials do
  not authorize the requested key installation. Device effectiveness claims
  remain `NOT_VERIFIED` until an explicitly approved mutation/traffic phase.
- Key setup evidence: TCP/22 reachable from `192.168.1.125`; dedicated
  `openkill-192.168.1.103-ed25519` key created outside the repository with
  fingerprint `SHA256:f+jc02xQKTFS9LdSP7gtvkFF/X25W3mrEvqORuSFFjg`; Dropbear
  public-key authentication succeeded in `BatchMode` as root. The supplied
  password was used only for this one-time public-key installation and was not
  persisted.
- Local SSH convenience alias `openkill-103` now points to the dedicated key
  with `BatchMode yes`; a key-only alias connection was verified as root.
- Device read-only evidence: `/etc/openwrt_release` reports Kwrt
  `25.12-SNAPSHOT` x86/64 with Linux `6.12.103`; dnsmasq listens on LAN,
  WAN-side, Docker and IPv6 addresses; its active resolv file contains WAN
  resolver `192.168.10.2`; fw4 has only the dnsmasq UDP/53 redirect table and
  no OpenKill/Mihomo chains. The target has `dnsmasq-full` nftset support, but
  no OpenKill package, no Mihomo/Clash binary and no proxy listener.
- Device mutation record: only the dedicated public key was added for
  Dropbear access. No UCI value, route, firewall rule, package, service,
  DNS setting, or runtime process was changed by the inspection.
- Capability preflight: the target has `dnsmasq-full` nftset support, fw4/nft,
  `nft_tproxy`, `nft_socket`, `tun`, IPv4/IPv6 netfilter modules, curl/wget,
  about 789 MB free overlay space and about 978 MB RAM. These are readiness
  observations only; they do not prove OpenKill or Mihomo protocol behavior.
HOST_NETWORK_INCIDENT_CAUSE: `UNCONFIRMED`
HOST_NETWORK_SETTINGS_CHANGED_BY_THIS_WORK: `0`
TEST_PROCESS_CLEANUP: `PASS`
HOST_NETWORK_GUARD: `PASS` (the guard is fail-closed and the latest full and preflight runs saw no unexplained drift; the earlier listener-drift evidence remains historical and unattributed)
ENVIRONMENT_ERROR_CLASSIFICATION: `PASS` (required Core cases passed; `NFT_CLI_UNAVAILABLE` is explicit and bounded)
UI_STATIC_CONTRACT: `PASS`
UI_BROWSER_VALIDATION: `PASS` (local Chrome/Playwright preview at 1920/1366/768/390 CSS px, including upload mode, age-option placement, overwrite selection and editor race checks; evidence under `artifacts/test-evidence/ui-preview`)
UI_DEVICE_VALIDATION: `NOT_RUN`
UI_REFERENCE_ALIGNMENT: `PASS` (flowing two-column dashboard, full-width connectivity panel, two-column mobile metrics, truthful states and synchronized conditional panels)
IPV6_SOURCE_ROOT_CAUSE: `KNOWN_VMWARE_TEST_ENVIRONMENT_LIMITATION` (not a production defect conclusion)
CONTINUITY_CONTRACT_PRESERVED: `PASS`
WRITER_HASHES_UNCHANGED: `PASS`
FAST_GATE: `PASS` — `20260917T110207Z-2372` (18/18, no cache)
FULL_GATE: `PASS` — `20260917T110710Z-2724` (39/39; 1 explicit `NFT_CLI_UNAVAILABLE`)
DEVICE_PREFLIGHT: `PASS` — `20260917T112344Z-4584` (32/32; local readiness only, no device contact)
DEVICE_CANDIDATE_ID: `a07543025287565b341f77ce7eb1861ddf2136bd292eb5ee66c3fbfe6db03f54`
DEVICE_EVIDENCE: `artifacts/test-evidence/20260917T112344Z-4584`; latest full evidence is `artifacts/test-evidence/20260917T110710Z-2724`; historical R3B device evidence remains under `artifacts/test-evidence/r3b-device-f83d592f18b685fe62b9b94a4f907e5465ac13f3e1488a27b8bff5d1cd5ea763`
RESULTING_HEAD: resolve with `git rev-parse HEAD` after this status commit; the recorded `CURRENT_HEAD` is the pre-commit observation

IMPLEMENTED: R3C internal typed sidecar producer, canonical D2D fixture, typed ownership/DNS model, isolated staged execution, unified local gates, LuCI presentation and conditional-control fixes, T0/T1/T2 runtime-DNS continuity checks, multi-listener core-owned DNS socket selection, owned-process cleanup, and read-only host-network guarding
LOCAL_VERIFIED: focused UI/interaction suites, clean fast/full gates and clean device-preflight pass; the browser run executes production status/upload/editor coordinators at 1920/1366/768/390 CSS px with local mocks; WSL-only lifecycle changes and the explicit NFT CLI limitation are classified; the 1000-call continuity stress runs in private WSL `/tmp`; historical device cycles stopped fail-closed at IPv6 source continuity, which is deferred because `.102` is a VMware IPv6-limited test environment
DEVICE_VERIFIED: `NO` for the R3A/R3C candidate (`.102` runtime stayed healthy, but typed parity was NOT_RUN)
RELEASED: `YES` — `v2026-1129-ipk` points to `0ae5fb418514d609923a632a56250907d52a74bb`; IPK SHA256 `3017bd1569e1851105dbebceea306496fe8f7d2776aff88402bf4e1433e521d4`

The detailed phase records below are retained as historical evidence. The
single local gate runner and the hardening decisions are documented in
[`docs/dev/local-validation-hardening.md`](../dev/local-validation-hardening.md)
and [`docs/testing/TEST_GATES.md`](../testing/TEST_GATES.md).

The UI follow-up fixes stale stylesheet cache keys, the missing subscription
detail hook, status-page controls that did not recover after a later poll, and
runtime-state presentation that previously could retain a healthy-looking
chip after an incomplete or failed response. `scripts/test-ui-contract.py`
and `scripts/test-ui-preview.py` cover these source-level regressions. A local
Chrome/Playwright run exercised the production templates and CSS with mock
data; live LuCI backend and device rendering remain unverified.

The latest UI pass also covers the conditional controls that were still able
to drift after repeated interaction: dynamic CBI table tabs now update panel
visibility, selection and keyboard state together; subscription summaries keep
their base classes while toggling visibility; the overwrite editor binds its
delegated drag/touch handlers once across rerenders; and the upload editor
returns the age-encryption group to the correct mode after reset. The browser
evidence includes the production uploader/editor coordinators and an isolated
mock of these transitions. It remains local preview evidence, not live LuCI or
device validation.

## Historical execution records

## R3B self-contained typed candidate retry (blocked at device continuity)

- Phase: `PHASE_3E2D2D_R3B_RETRY_SELF_CONTAINED_TYPED_CANDIDATE`.
- The local candidate was bound to clean HEAD
  `45b94aee217c49395197a088d17f1f591c9648e6`, candidate ID
  `f83d592f18b685fe62b9b94a4f907e5465ac13f3e1488a27b8bff5d1cd5ea763`,
  and preflight evidence
  `artifacts/test-evidence/20260917T023225Z-24796`.  The staged set was
  exactly the observer, renderer, TUN template, and semantic manifest listed
  by that manifest; device-side hashes matched.  The installed 2026-1128
  observer remained unchanged.
- Only `openkill-test-102` (192.168.1.102) was contacted with
  BatchMode/IdentitiesOnly.  No .1, .101, or other device was accessed.  The
  existing runtime stayed healthy: OpenKill/procd running, one core, utun,
  IPv4/IPv6 ABI and table 354, dnsmasq :53, core UDP 7874, SSH, and the
  canonical config hash all remained valid.
- Three independent invocations of the staged automatic coordinator returned
  `STALE` (rc 6, reason `automatic-state-source`) before capture/parser or
  typed comparison.  The result was stable because the committed
  `/tmp/openkill-network.desired` and `/tmp/openkill-network.applied`
  files differ in `IPV6_PROXY_RULE`, `IPV6_TUN_ROUTE`, and
  `LOCALNETWORK6_PREFIXES`; the snapshot reports `LOCAL_IPV6_READY=1`.
  This is a source-convergence blocker, not evidence of a DNS semantic
  mismatch.  The 10-cycle gate was correctly not started.
- Post-run UCI, canonical config, installed production files, process state,
  routes/rules and service status remained unchanged.  Candidate telemetry,
  wrapper, lock and temporary directory were removed after the coordinator
  exited.  No package, UCI, nft, route, rule, reload, restart, central apply,
  or packet-path operation occurred.
- Evidence is retained under
  `artifacts/test-evidence/r3b-device-f83d592f18b685fe62b9b94a4f907e5465ac13f3e1488a27b8bff5d1cd5ea763`.
  The next action is to reconcile the stable desired/applied IPv6 source
  contract under a separately approved device maintenance step; do not rerun
  the typed comparator until continuity converges.

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

## Phase 3E.2D2D-R3B — device typed-shadow revalidation gate

On 2026-09-16 the R3B preflight used source baseline
`0708ba5480c6c4507b1eba7acdfc00e8fd67891a`, version `2026-1128`, with a
clean worktree and the D2C ancestor check passing. The R3A range contains only
the shadow observer, its semantic manifest, fixtures/tests, workflow wiring,
and documentation; legacy writers, DNS/network/firewall dataplane, init,
parser, renderer, installer, package, and version behavior are unchanged.
All local R3A gates passed (typed shadow 14/14, D2B 21/21, R2B 18/18,
canonical config 10/10, runtime shadow 11/11, self-sufficiency 23/23,
`local-gate.sh`, `ci-gate.sh`, validation, POSIX syntax, compileall, and
diff-check). The frozen writer hashes remain unchanged.

The only R3A runtime candidate files are
`luci-app-openkill/root/usr/share/openkill/openkill_nft_shadow.sh` (160557
bytes, SHA-256 `4de3738e953552c7acfa60d39f12c2341341dfd459bf76b46d1491ecd50367ff`)
and `luci-app-openkill/root/usr/share/openkill/shadow/semantic_model_v1.tsv`
(1453 bytes, SHA-256
`7bd6909cfcb08aee02cc6900fee6de358228d7d5b9fef15c634f19c69a4fdb50`). The
shell accepts a temporary manifest through
`OPENKILL_NFT_SHADOW_SEMANTIC_MANIFEST` or `OPENKILL_NFT_SHADOW_TEMPLATE_DIR`
and safely copies caller-provided typed files through
`OPENKILL_NFT_SHADOW_TYPED_ACTUAL_FILE` and
`OPENKILL_NFT_SHADOW_TYPED_DESIRED_FILE`.

The complete device staging path is nevertheless blocked. The production
tree has no sidecar producer: `openkill_shadow_capture_legacy_nft` and
`openkill_shadow_parse_nft_capture` emit legacy capture/intent, and
`openkill_shadow_run_renderer` emits CURRENT nft payload, but no production
caller emits `OPENKILL_SHADOW_TYPED_INTENT_V1=1` actual/desired files from
that same coherent cycle. `openkill_shadow_compare_nft` requires both typed
files and returns `MODEL_GAP` when either is absent. The checked-in typed TSVs
are sanitized local fixtures only; staging them would not be live `.102`
evidence. R3B therefore stopped before SSH or any device write:
`CANDIDATE_STAGING_ENTRYPOINT_BLOCKER`, `R3A_CANDIDATE_REAL_DEVICE=NOT_RUN`,
and `DEVICE_TYPED_*_PARITY=INSUFFICIENT_EVIDENCE`. No device or router was
accessed and no package, service, UCI, dataplane, config, or central write
occurred.

`NEXT=R3B_LOCAL_TYPED_SIDECAR_PRODUCER_INTEGRATION` (local only: add and
validate a formal sidecar producer or an equivalent existing production
caller before another device run). `CENTRAL_ACTIVE=NOT_APPROVED`,
`CENTRAL_NFT_APPLY=NOT_APPROVED`, and `REAL_PACKET_PATH=NOT_TESTED` remain
unchanged.

## Phase 3E.2D2D-R3C — self-contained typed sidecar producer integration

Observed locally on 2026-09-16 from baseline
`f710e572c1e9524feae8f4919b9a93ad64422a38`, version `2026-1128`, with no
device or router access.  The D2C commit remains an ancestor.  The R3C scope
is limited to the production shadow observer, its semantic manifest, sanitized
automatic-state fixture, local producer tests, CI suite wiring, and this
documentation; legacy writers, DNS/network/firewall dataplane behavior,
renderer, parser, init, installer, package, and version behavior are unchanged.

R3B's blocker was reproduced locally: the typed comparator accepted prepared
sidecars, but the automatic coordinator had no producer and returned
`MODEL_GAP` when those files were absent.  R3C adds a self-contained producer
inside the same private coordinator cycle.  After coherent T0/T1 capture and
parser output, the formal inventory and CURRENT renderer run; the coordinator
then emits independent `OPENKILL_SHADOW_TYPED_SIDECAR_V1` actual and desired
files and feeds them directly to the existing typed comparator.  The actual
side uses parsed legacy intent and snapshot-frozen scalar fields.  The desired
side uses CURRENT renderer output for firewall DNS targets plus renderer input,
templates, and explicit manifest contract records for desired objects and the
remaining DNS layers.  No producer step performs a live UCI, ubus, nft, ip,
DNS, or Mihomo reread after the snapshot.  D2A inventory classification runs
before typed projection, so required absence remains fail-closed while
conditional, inactive, optional, and out-of-scope absences remain explicit
diagnostic evidence.

The sidecars carry schema, model, side, cycle, and continuity metadata and are
bounded mode-0600 files in the private temporary directory.  Missing or
ambiguous sources, duplicate rows, or unknown ownership return the additive
`MODEL_GAP` result (exit 12); present semantic differences remain the existing
`MISMATCH` result.  WAN safety rows remain in full observation and are excluded
from CURRENT-owned equality by formal `LEGACY_ONLY_SAFETY` metadata.  The
independent firewall/listener/upstream/Mihomo/loop/scope fields preserve the
D2C `53` versus `7874` distinction.  External sidecars remain available only
for explicit fixture/development calls; automatic production mode rejects
them even when a legacy override variable is supplied.  The device runtime
remains POSIX shell/BusyBox-only.

Local evidence: automatic no-sidecar replay is `MATCH` with
`DNS_PARITY=MATCH`, one stable actual/desired/DNS hash pair, and retained WAN
observation; renderer mutation and actual-state mutation are independently
detected as `MISMATCH`; missing actual or desired DNS sources are `MODEL_GAP`;
the minimal staged observer/manifest simulation is `MATCH`.  The dedicated
producer suite passes 13/13, including automatic rejection of externally
supplied sidecars with and without a legacy override; the explicit typed suite
passes 14/14, self-sufficiency 23/23, continuity 11/11, BusyBox normalization
7/7, runtime shadow 11/11, and context adapter 15/15.  The broader local
matrix passes: NFT IR 16/16, NFT syntax 18/18 (`nft` CLI unavailable, so the
syntax matrix is explicitly not run), device parser 7/7, network 65/65,
snapshot/FW4 6/6, Stage D 7/7, runtime 28/28 with two existing skips,
installer 11/11 with one existing skip, core validation, BusyBox renderer
13/13, and autonomous workflow 8/8.  `local-gate`, `ci-gate`, POSIX syntax,
compileall, and diff-check pass.  `NEW_UNEXPLAINED_SKIP=0`.  No version,
package, release, tag, device, central apply, or packet-path operation is part
of R3C.

`R3B=PARTIAL` remains a historical device gate because the installed release
has not been tested with this candidate.  `R3C=PASS`:
`AUTO_TYPED_PRODUCTION_PATH=READY`, `SELF_CONTAINED_STAGING=READY`,
`LOCAL_R3_REPLAY=MATCH`, and `DEVICE_RETRY_READY=YES`.
`NEXT=PHASE_3E2D2D_R3B_RETRY_SELF_CONTAINED_TYPED_CANDIDATE`.
`CENTRAL_ACTIVE=NOT_APPROVED`, `CENTRAL_NFT_APPLY=NOT_APPROVED`, and
`REAL_PACKET_PATH=NOT_TESTED` remain unchanged.

## Local validation hardening work package (completed)

Observed on 2026-09-16 from `28811e56d04b77963e5e5b8b6254b4dc741b8aac`,
version `2026-1128`, with no device or router access.  The D2C commit
`566fa82f0b814710b290c4bbd7e2385b689bd616` remains an ancestor.  The local
changes are limited to the shadow observer's read-only DNS provenance capture,
staged observer tests, the unified test runner, gate naming, evidence
documentation, and CURRENT status; legacy writers, dataplane behavior, init,
renderer, parser, network, firewall, installer, package, version, release and
central-apply behavior were not changed.

The observer now treats `OPENKILL_DNS_ENDPOINT` as readiness/configuration
intent only.  Automatic actual `MIHOMO_DNS_LISTENER` evidence comes from a
supported-core-owned UDP `netstat` socket, joined to the actual dnsmasq
upstream port when Mihomo has multiple listeners; the returned endpoint is
still taken from the socket row.  DNS sources are frozen at T0 and re-sampled
only at the T1/T2 continuity boundaries, while the producer/comparator never
performs a live reread.  Missing or ambiguous sources remain a typed
`MODEL_GAP`/stale cycle.  The staged regression copies the observer, renderer,
semantic manifest and TUN template into a private directory, verifies the
observer hash through a separate wrapper without modifying candidate bytes,
records all candidate paths/hashes and runs five automatic cycles without
external typed sidecars.  The runner source contains no repository helper,
renderer or template fallback.

The single `scripts/openkill-test-gates.py` executor provides `fast`, `full`,
and `device-preflight` modes.  It selects Windows/WSL per case, captures every
return code, records explicit environment-limited results, binds cache keys to
source/test/fixture/interpreter inputs, and writes machine-readable evidence
bundles.  The candidate manifest's minimal staging set is the observer,
renderer, `shadow/semantic_model_v1.tsv`, and `shadow/input_tun_v1.tsv`; its
candidate ID is
`caaf4a28865dce66150758e4b2dc3ca347bbc5620ae8fefe5984084aafbb7c40` and the
canonical config remains
`scripts/fixtures/3e2-safe.yaml` with SHA-256
`9cd8d91750758823776df9c982c1e15f0baa1a72baa1792fa2f82c0df4d24a6e`.

Evidence is complete for the current worktree: fast run
`20260916T140505Z-2412` passed; full run `20260916T140752Z-19340` passed with
32 PASS and one documented `NOT_RUN_ENVIRONMENT` (`NFT_CLI_UNAVAILABLE`);
device-preflight run `20260916T142142Z-21440` passed with 25 PASS and the same
single environment result.  The staged observer test is 16/16, the R2B UCI
lifecycle test is 18/18, and the candidate manifest reports staged execution,
internal typed sidecars, no repository fallback, `DEVICE_ACCESS=0`,
`CENTRAL_APPLY=0`, and `PACKET_TEST=0`.  The candidate ID is
`caaf4a28865dce66150758e4b2dc3ca347bbc5620ae8fefe5984084aafbb7c40`; its
runner source hash is
`b570de29a31207a3a2cefb3c8a75bfcb07334a254ff1cf4172aab11edc44974a`.
The WSL Ruby-dependent cases declare `RUBY_UNAVAILABLE` explicitly.  The
eight frozen writer hashes are unchanged and `NEW_UNEXPLAINED_SKIP=0`.

This proves local readiness only.  `DEVICE_RETRY_READY=YES` means the exact
candidate may be considered for an explicitly approved `.102` phase; it does
not claim device verification, package release, central apply, or packet-path
validation.  `NEXT=PHASE_3E2D2D_R3B_RETRY_SELF_CONTAINED_TYPED_CANDIDATE`.
