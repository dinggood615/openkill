# Current status

## 2026-1161 release preparation (2026-09-26)

- Source implementation is on master commit `8adb826` and its exact
  Development CI run passed (`36239900863`). The next release increments the
  package and installer metadata to `2026-1161`.
- The release scope is limited to the VPN policy layout and independent
  NaiveProxy control card already recorded below. No device or VPS test is
  authorized in this iteration; browser rendering is also pending.
- Next action: run local gates on the versioned source, push the release
  preparation commit, verify its exact Development CI, then run the RC Build
  and Formal Release gates. Record their links and package hashes here.

## NaiveProxy controls and VPN policy layout (2026-09-26)

- Scope: move the existing device and bypass-router compatibility fields into
  the `VPN 访问策略` card while preserving their UCI names, defaults, depends
  rules and network semantics. Keep the independent NaiveProxy bridge as a
  separate equal-width card in the compatibility page.
- Service contract: add only a permission-checked local control boundary for
  `naiveproxy-bridge`. Start, stop, node import and health actions remain owned
  by the standalone service; OpenKill must not write Naive credentials to UCI,
  pass secrets in command arguments, modify the selected YAML, or restart
  Mihomo. Responses contain redacted identifiers and state only.
- UI contract: the card exposes service state, add/import actions, per-node
  test latency, refresh and diagnostics. Existing read-only status and manual
  SOCKS5 YAML ownership remain authoritative. Device and VPS tests are outside
  this iteration unless a later plan explicitly authorizes them.
- Failure contract: invalid sessions, malformed requests, duplicate tasks,
  missing component, port conflicts and probe failures must return a specific
  redacted stage. Remote failures never trigger unrelated restarts or DIRECT.

## NaiveProxy standalone bridge and manual YAML ownership (2026-09-26)

- Scope: split NaiveProxy component/node ownership from OpenKill. The new
  standalone bridge owns `/etc/naiveproxy`, procd instances, loopback SOCKS5
  listeners and per-node HTTPS health results. OpenKill becomes a read-only
  status view and a credential-free YAML snippet generator; it must not write
  Naive credentials, auto-start helpers, inject proxy entries or rewrite the
  user's YAML.
- Config contract: standalone node JSON is mode 600 under `/etc/naiveproxy`;
  runtime state is sanitized and bounded under `/var/run/naiveproxy`. The
  OpenKill UCI and selected YAML remain user-owned. Legacy OpenKill Naive data
  is migration evidence only and is never silently deleted or copied.
- Lifecycle contract: one stable node ID maps to one loopback port and one
  procd instance. Manual start/stop is authoritative; local process/listener
  failures may trigger bounded per-instance recovery, while remote probe
  failures never restart unrelated services or fall back to DIRECT.
- Health contract: probes use the matching SOCKS5 listener and a fixed HTTPS
  allowlist with bounded timeout/size/redirects. Displayed delay is HTTPS
  request elapsed time, not ping, UDP or full Mihomo routing verification.
- Verification boundary: local fixtures must prove independent lifecycle,
  credential redaction, YAML non-rewrite and status expiry. Device and remote
  VPS tests remain forbidden unless a later CURRENT section explicitly
  authorizes them.
- Implementation evidence (working tree): added the independent
  `naiveproxy-bridge` procd service and `naiveproxy-standalone.sh` library;
  node JSON and runtime state stay under `/etc/naiveproxy` and
  `/var/run/naiveproxy`, while OpenKill reads only the redacted manifest and
  generated credential-free SOCKS5 snippets. Legacy OpenKill Naive routes now
  redirect or expose read-only status, and the OpenKill init script no longer
  starts, stops, probes or injects Naive nodes.
- Local checks completed: standalone fixture (component probe, protected
  config, loopback probe, HTTPS timing, expiry fields and YAML redaction),
  standalone integration contract, UI contract/interactions, optimization
  checks, POSIX syntax and `sh scripts/local-gate.sh`. Device, browser and
  remote VPS behavior remain unverified by plan.

## OpenKill startup preflight and NaiveProxy compatibility repair (2026-09-26)

- Scope: diagnose the reported startup abort before Mihomo launch, make the
  generated controller listener deterministic and valid, preserve strict DNS
  privacy fail-closed behavior with an actionable selectable-group diagnostic,
  and verify the NaiveProxy helper's VPS-facing configuration without changing
  the NaiveProxy protocol or the user's YAML ownership.
- Startup contract: `dashboard_bind_address` and `cn_port` are normalized by
  the same address/port helpers used by runtime API probes before YAML
  generation. Invalid legacy values fall back to loopback/9090 and are
  recorded as a repair reason; a generated invalid `external-controller`
  never replaces the last-good profile. Strict DNS still refuses a profile
  with no selectable proxy group, but reports the missing group and preserves
  the active configuration.
- NaiveProxy contract: one protected JSON configuration and one loopback
  SOCKS5 listener per enabled stable node; only supported `https`/`quic`
  transports are emitted, credentials stay out of logs and YAML snippets, and
  a helper/remote failure never becomes `DIRECT`. The component path and ELF
  probe remain authoritative; no device-specific binary or node data is added
  to the repository.
- Device phase: the latest user request explicitly authorizes **read-only**
  diagnostics on the test host `192.168.1.103` via the existing SSH alias.
  The phase is limited to version/path/UCI/log/process/listener inspection and
  redacted generated-config checks. It must not write UCI, restart services,
  install packages, enable `CENTRAL_ACTIVE`, apply central nft state, or run
  packet-path tests. If the host is unreachable, local evidence remains the
  source of truth and the gap is recorded.
- Verification: add regression fixtures for malformed controller values,
  strict-DNS missing groups, Naive URL/config generation and credential
  redaction; run the local gate and exact-commit Development CI before RC and
  Formal Release.

### Current evidence (before implementation commit)

- Source baseline observed at `474c50e1fef0f3888e504cb2e4fc214fd902ce08`; the
  worktree retains only this startup/Naive repair plus this plan update.
- Read-only test-host inspection is authorized for this iteration. The host
  reports `luci-app-openkill 2026-1158`, an executable x86_64 NaiveProxy
  `150.0.7871.63` at `/etc/openkill/core/naive`, and no running OpenKill or
  Naive instance. Its selected YAML contains an empty `proxy-groups:` and its
  UCI has no `groups` sections while `dns_privacy_mode` is `strict`; this is the
  direct cause of the startup transaction abort. The same logs contain helper
  `SIGTRAP` exits, which remain a separate runtime/remote compatibility fault;
  no packet-path or remote probe was run.
- Local changes now normalize the controller bind/port before generation,
  return a non-zero status for a failed YAML transaction, preserve the active
  profile, and record a specific startup failure reason. Strict DNS accepts
  only a real selectable proxy, provider, or include-all group and reports the
  required repair. Naive status requires a local version probe, rejects empty
  credentials, maps legacy `tls` to HTTPS, and reports a stopped helper as a
  local lifecycle failure.
- Local evidence so far: `scripts/test-runtime.py` (31 tests, 3 environment
  skips), `scripts/test-naiveproxy-integration.py`,
  `scripts/test-naiveproxy-health.py`, `scripts/test-openkill-optimization.py`,
  POSIX syntax checks, `git diff --check`, and `sh scripts/local-gate.sh` all
  pass. The Windows host emits harmless WSL/GBK reader warnings for the
  optimization fixture; the process exits successfully. Device reinstallation
  and remote VPS connectivity remain pending and are not claimed here.

### 2026-1159 delivery evidence

- Implementation commit `c22e3d36efcc799dd7e3c1b0c6fb251d3013838d` contains the
  startup transaction, listener validation, strict-DNS diagnostics and
  NaiveProxy component/lifecycle fixes. Version metadata and release notes were
  prepared in `6b20f976fe67f66f165a7ac22e5fe27e8d1a2e45`; both commits are on
  `master` and the version commit is the published source.
- The exact version commit's Development CI passed: [run
  36233800250](https://github.com/dinggood615/openkill/actions/runs/36233800250).
  The source gate and local gate passed for `2026-1159`; `git diff --check` was
  clean.
- RC Build from the exact version commit passed: [run
  36233919434](https://github.com/dinggood615/openkill/actions/runs/36233919434).
  The candidate IPK is `luci-app-openkill_2026-1159_all.ipk`, 7,706,023 bytes,
  SHA-256
  `6965957aacc645a8880877f2840daf2e1db14bc964c3593f94d773fec17dd0ef`.
  Its audit artifact digest is
  `sha256:7fbba5bd71d73321f1a25347e1c4af69f240f3211e0ca162d68f011b79088771`;
  metadata, conffile preservation, maintainer-script deletion, stale-reference
  and sensitive-content checks passed under `D:\\openkill-cache\\rc-2026-1159`.
- Formal Release passed with `release_gate=true` and `publish=true`: [run
  36234170503](https://github.com/dinggood615/openkill/actions/runs/36234170503).
  Published [v2026-1159-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1159-ipk)
  from source `6b20f976fe67f66f165a7ac22e5fe27e8d1a2e45`. The public release
  asset `luci-app-openkill_2026-1159_all.ipk` is 9,246,266 bytes with SHA-256
  `2758a19fbec1b581a5f7c4d0e42c2804ad4a87ca97d542e0a3b2f895b552a2d3`.
  The formal workflow artifact digest is
  `sha256:5b02a8e48199ce06765a6992dc422bf45c52a9292f087e6e92d7eefe02ec5e85`;
  the package control record is version `2026-1159`, architecture `all`, and
  preserves `/etc/config/openkill`. The downloaded release audit is retained
  under `D:\\openkill-cache\\formal-2026-1159`.
- The authorized device phase was read-only. It confirmed OpenKill `2026-1158`,
  an executable `/etc/openkill/core/naive` reporting `150.0.7871.63`, strict
  DNS with no selectable proxy group, no running helper, and historical
  NaiveProxy `SIGTRAP` exits. No UCI/config write, restart, package install,
  packet-path test, central nft change or remote VPS authentication was done.
  The strict-DNS failure must be repaired by adding a real selectable proxy
  group (including the generated SOCKS5 name) or intentionally changing the
  privacy mode; it must not silently fall back to `DIRECT`. The SIGTRAP remains
  a separate device/runtime compatibility issue and is not claimed fixed by this
  release.
- Rollback is the retained `v2026-1158-ipk` package/tag after backing up the
  device configuration and preserving the user's existing nodes and YAML. No
  credentials, private node values or complete share links are recorded here.

## NaiveProxy manual health diagnosis and compact compatibility card (2026-09-26)

- Scope: clarify the screenshot state where `final-yaml-missing-node` appears
  while the helper is in manual YAML mode, and reduce the NaiveProxy card's
  default UI without changing node credentials, DNS, routing, firewall, YAML
  ownership or the helper protocol. The final-YAML result remains read-only
  context; it must never turn a successful loopback probe into a failure.
- Health contract: the primary status is the bounded probe through that node's
  `127.0.0.1` SOCKS5 listener. Mihomo/YAML membership is shown as a separate
  diagnostic and remains expected to be missing until the user copies the
  credential-free snippet into the selected YAML and adds its name to a
  strategy group. No direct fallback is allowed.
- UI contract: keep component status, version/architecture, install, node
  management, loopback YAML and per-node testing available; move URL, digest,
  asset metadata, removal and detailed Mihomo diagnostics behind accessible
  details. Remove duplicate default controls and the redundant Mihomo table
  column while preserving the full row diagnostic.
- Boundary: the current plan and AGENTS.md forbid device and packet-path
  access in this iteration. Local fixtures will reproduce a missing-final-YAML
  case and prove it does not suppress loopback health; device/remote causes
  remain pending a separately authorized plan.

### 2026-1158 delivery evidence

- Diagnosis: in manual YAML mode, `final-yaml-missing-node` is an independent
  Mihomo/YAML membership diagnostic. It means the credential-free loopback
  snippet has not been copied into the selected YAML and strategy group. The
  screenshot's `探测失败` remains the separate bounded loopback HTTPS probe
  result; the exact helper, credential or remote cause requires a device phase
  and is not inferred from the YAML diagnostic.
- Fix commit `929e27301ae8bc181396292e890d3d825947d46f` keeps the loopback
  probe authoritative, preserves the separate Mihomo detail, moves component
  metadata and maintenance actions behind accessible details, shortens the
  default controls, removes the duplicate Mihomo table column and adds a
  no-horizontal-scroll mobile card layout. Its exact Development CI passed as
  run `36230543078`:
  https://github.com/dinggood615/openkill/actions/runs/36230543078
- Version commit `f1109692182c91f93b5181bb2286f5bfc8c7fdcb` advances the source
  metadata and release notes to `2026-1158`. Its exact Development CI passed as
  run `36230738478`:
  https://github.com/dinggood615/openkill/actions/runs/36230738478
- RC Build run `36230857780` passed from `f110969` and produced
  `luci-app-openkill_2026-1158_all.ipk` (7,703,994 bytes), SHA256
  `c0fd65f5fb4f755b9f6f7f0378c7ae80f76de33c37abcc875d55676e4482fbc7`.
  The artifact digest is
  `sha256:26b5631318ea8f737e0ee02ceff0dae2839a91b401e76f84829c0536c8781b81`;
  the downloaded audit is retained under
  `D:\\openkill-cache\\rc-2026-1158`.
- Formal Release run `36231157068` passed with `release_gate=true` and
  `publish=true` from `f110969`:
  https://github.com/dinggood615/openkill/actions/runs/36231157068
  Published release:
  https://github.com/dinggood615/openkill/releases/tag/v2026-1158-ipk
  contains `luci-app-openkill_2026-1158_all.ipk` (9,245,110 bytes), SHA256
  `dc68ef2a978f6f5227396073e215a5274b094436150c64cc913fb8f88ed31753`.
  The formal artifact digest is
  `sha256:71f02df3fdc35edbe927f86423cc7f6c5d3427c45626d9afd9ab213b82dc922d`;
  the downloaded package and extracted audit are retained under
  `D:\\openkill-cache\\formal-2026-1158`.
- Package audit confirmed version `2026-1158`, architecture `all`, the
  `/etc/config/openkill` conffile, root-owned executable helper scripts, the
  final `oc.css` and health script, and no private-node markers. Local health,
  integration/UI contract, interaction/preview, POSIX syntax, local-gate and
  diff checks passed. The browser preview was inspected; Playwright is not
  available on this workstation, so a complete automated viewport matrix is
  not claimed.
- Device, packet-path and real Naive endpoint tests remain pending because
  AGENTS.md and this iteration's plan forbid device access. No CENTRAL_ACTIVE,
  central nft, WAN, gateway, DNS, IPv6 or TUN change was made. Rollback is the
  retained `v2026-1157-ipk` package plus the user's existing configuration and
  manual YAML backups.

## NaiveProxy manual YAML mode and shared OpenKill theme (2026-09-26)

- Scope: move the NaiveProxy contract to manual YAML ownership, keep the
  helper responsible only for protected per-node configuration and loopback
  SOCKS5 listeners, add per-node health evidence and bounded local recovery,
  and unify the OpenKill page surfaces and theme tokens. This supersedes the
  previous automatic bridge *injection* contract for new applications while
  retaining the legacy UCI value for migration visibility.
- Contract: the UI no longer offers automatic Mihomo injection. An enabled
  NaiveProxy node is prepared and supervised independently; the generated
  credential-free SOCKS5 snippet is the only Mihomo hand-off. Existing YAML
  and user strategy groups are preserved. If a legacy `auto` value is found,
  the page reports that manual migration is required and does not rewrite the
  user's YAML or silently fall back to DIRECT.
- Lifecycle: each stable node ID owns one 127.0.0.1 TCP SOCKS5 port, a mode-
  600 helper JSON file and one procd instance. Port ownership, PID and
  configuration generation are checked before reporting local readiness.
  Recovery is limited to the affected instance with cooling and bounded
  retries; a remote probe failure never restarts the whole proxy or changes a
  policy selection.
- Health: probes use the matching loopback SOCKS5 path with a fixed HTTPS
  target/strict redirect and size limits. Results are per node, expire after
  bounded time, and expose auxiliary-chain evidence separately from any
  read-only Mihomo/YAML diagnostic. Credentials and response bodies are not
  persisted.
- UI: OpenKill pages share scoped light/dark surface variables, card borders,
  controls and spacing. No DNS, IPv6, TUN, firewall, legacy-writer parser or
  ABI semantics are changed. Temporary artifacts remain under
  `D:\openkill-cache` and no device or packet-path test is part of this local
  iteration.
- Verification gate: update the manual-mode fixtures, health and UI contract
  tests, run POSIX checks, `scripts/local-gate.sh` and `git diff --check`,
  then verify the exact Development CI commit before RC/Formal Release.

## NaiveProxy automatic bridge diagnostics (2026-09-26)

- Scope: repair the automatic Mihomo bridge path without changing NaiveProxy,
  DNS, routing, firewall, legacy parser or ABI semantics. The change covers
  generator failure reporting, bridge-node presence checks and strategy-group
  diagnostics. Credentials and private node data remain outside logs, tests,
  reports and package artifacts.
- Contract: an enabled NaiveProxy node in automatic mode must either produce a
  credential-free `type: socks5` entry and an explicit strategy-group
  reference, or record a redacted, stage-specific reason. It must never be
  silently omitted or replaced with DIRECT. Manual mode continues to expose
  only the loopback snippet for user-managed YAML.
- Verification: exercise component/path, node validation, helper readiness,
  final YAML and group-reference states with offline fixtures; run the Naive
  integration suite, POSIX checks, local-gate and diff review before any
  release. Device and remote endpoint tests remain separate evidence.

## NaiveProxy per-node health checks (2026-09-26)

- Scope: add credential-free per-node health state, bounded HTTPS probes and
  latency display inside the compatibility card. Automatic mode tests the
  exact Mihomo SOCKS5 node through its controller delay endpoint; self-managed
  YAML mode tests only the matching loopback SOCKS5 entry and reports Mihomo
  integration separately. No DNS, routing, firewall, parser or ABI behavior
  changes are included.
- Contract: every result is bound to a stable UCI node ID and current helper
  port/config generation. Missing component, listener, Mihomo node, strategy
  reference, timeout and HTTP/TLS errors are distinct states. A failed probe
  never falls back to DIRECT. Procd remains responsible for bounded local
  process respawn; health checks do not restart all OpenKill services.
- Scheduling: manual single/all-node tasks use one deduplicated backend job;
  optional periodic checks run from the existing cron boundary at a bounded
  interval (default 300 seconds), with atomic mode-600 state and expiry.
  Probe targets, redirect policy, response size and timeouts are restricted;
  credentials and response bodies are never persisted.
- Verification boundary: use offline fixtures and a local fake controller or
  SOCKS endpoint for behavior tests. No packet-path test or device/remote
  endpoint claim is made until a separately authorized device phase supplies
  evidence.

### 2026-1156 delivery evidence

- Implementation commit `348ac4bbf4c07f25adf9f06c84ebf96b722bc3a5` adds the
  stable-ID per-node health state, exact Mihomo delay checks, self-managed
  loopback probes, bounded task scheduling, expiry and credential-free UI
  diagnostics. Local health, NaiveProxy integration, UI contract/interaction/
  preview, import behavior, POSIX and CSS-pruning checks passed. The local
  `verify_3e2_safe_config.py` helper could not start because this workstation
  lacks PyYAML; the Development/RC workflows install that dependency and their
  semantic gates passed.
- Development CI for the implementation commit passed as run
  `36216779897`:
  https://github.com/dinggood615/openkill/actions/runs/36216779897
- Version preparation commit `533b460fa1212bebbe4ac7a049efe7b5caad54b6`
  advances the source metadata and release notes to `2026-1156`. Its exact
  Development CI passed as run `36217481855`:
  https://github.com/dinggood615/openkill/actions/runs/36217481855
- An initial RC Build run `36216937032` passed from the implementation
  commit `348ac4b` and was retained as a pre-version smoke artifact. The
  final-version RC Build run `36217990716` passed from `26314f2` (the
  documentation-only child of the formal source commit) and produced
  `luci-app-openkill_2026-1156_all.ipk` with SHA256
  `f9ce6831c86fe30b0010992920689ac6fe736dfd59772d0cbab12e95965d5818`.
  Its artifact ZIP is cached under
  `D:\openkill-cache\rc-36217990716` with digest
  `ea9edc510469832af945ada3375c0566b2cd89fefe7b141c8ce20d561b4be137`.
  The final candidate audit confirmed the health script is root-owned mode
  0755, the controller/view and final CSS are present, and package metadata
  reports version `2026-1156`.
- Formal Release run `36217561587` passed with `release_gate=true` and
  `publish=true` from `533b460`. Published release:
  https://github.com/dinggood615/openkill/releases/tag/v2026-1156-ipk
  targets commit `533b460fa1212bebbe4ac7a049efe7b5caad54b6` and contains
  `luci-app-openkill_2026-1156_all.ipk` with SHA256
  `e41ce2899fccb8d22dce1fb29867f5345e14238f919189a7eafeec8e615d2012`.
  The formal artifact is cached under
  `D:\openkill-cache\formal-2026-1156-artifact`; the previous release remains
  available for rollback.
- Verification boundary: no router/device, packet-path or real Naive remote
  endpoint test was run in this iteration. The fixture proves one exact
  Mihomo node can report a 42 ms delay while an independently failing node is
  reported as `mihomo-not-loaded`; it does not prove remote authentication,
  UDP, IPv6, streaming or permanent availability. Device and remote status
  remain pending a separately authorized phase.

### 2026-1157 delivery evidence

- Manual-YAML implementation commit `dfb48dbb37d666c7e443de9451eb28c6d9b3b767`
  removes new automatic Mihomo injection, preserves the legacy bridge value for
  migration reporting, keeps one protected helper instance and loopback port
  per stable node, and adds credential-free per-node probe state. The scoped
  light/dark OpenKill surface tokens are included in the final CSS. Existing
  YAML, subscriptions, strategy groups and non-Naive protocol writers remain
  outside this change.
- The exact implementation Development CI passed as run
  `36221193378`:
  https://github.com/dinggood615/openkill/actions/runs/36221193378
- Version preparation commit `2bf2321c201f67f1e91d8f8333f3c52441db465e`
  advances the source metadata and release notes to `2026-1157`. Its exact
  Development CI passed as run `36221357063`:
  https://github.com/dinggood615/openkill/actions/runs/36221357063
- The matching RC Build passed from the version commit as run `36221457511`:
  https://github.com/dinggood615/openkill/actions/runs/36221457511
  It produced `luci-app-openkill_2026-1157_all.ipk` with SHA256
  `1693212c5b19ffb7c2ea44a6f1b4a937caf703faf63a585c37de28dca59501e2`.
  The RC audit confirmed package metadata, conffile preservation, maintainer
  script safety, ownership/mode checks, stale-reference checks and the absence
  of credentials or test-machine data. The downloaded RC archive is retained
  under `D:\openkill-cache\rc-2026-1157`.
- Formal Release completed with `release_gate=true` and `publish=true` as run
  `36221712197`:
  https://github.com/dinggood615/openkill/actions/runs/36221712197
  Published release:
  https://github.com/dinggood615/openkill/releases/tag/v2026-1157-ipk
  targets the version commit and contains
  `luci-app-openkill_2026-1157_all.ipk`. The published package SHA256 is
  `954a40f3f3cf6c90ca0e57b7473b453e2b5ae4c028ad0658d76684cd0f2f74fb`.
  The RC and formal package hashes are recorded separately because the formal
  workflow rebuilds the release asset; each hash was checked against its own
  downloaded package and release checksum.
- Local evidence: NaiveProxy integration, per-node health fixtures, UI contract,
  interaction and preview tests, POSIX/BusyBox syntax checks,
  `scripts/local-gate.sh`, and `git diff --check` passed. The fixture covers
  manual-mode markers, loopback `socks5h` probing, stale-task cleanup, bounded
  state and credential absence. A local browser preview loaded the final CSS
  and showed the unified surface and aligned status cards at the desktop
  viewport; the Playwright browser runner is unavailable in this workstation,
  so the full automated multi-viewport matrix is not claimed.
- Device and remote evidence: no device, packet-path, WAN, central nft or real
  Naive authentication test was run, in accordance with the current plan and
  AGENTS.md. The release therefore does not claim remote connectivity, UDP,
  IPv6, streaming, or permanent availability. A later authorized device phase
  must re-detect the component, add a node without exposing its credentials,
  copy the generated loopback YAML, and verify the helper and probe state.
- Rollback: install the retained `v2026-1156-ipk` package and restore the
  pre-change OpenKill configuration backup before reapplying any user-managed
  YAML. Do not remove or overwrite existing release tags or assets.

### Post-release evidence update

- Evidence commit `15cc1fecf877cab0fe03651aec2fe863da669ac7` was pushed to
  `master` after the formal release to record the RC, package, browser and
  verification boundary. Its exact Development CI passed as run `36222180876`:
  https://github.com/dinggood615/openkill/actions/runs/36222180876

### 2026-1155 delivery evidence

- Source fix commit: `dcc16b54fe7a31819dbe319594eefbbdb8b6da76`;
  Development CI run `36208543045` passed:
  https://github.com/dinggood615/openkill/actions/runs/36208543045
- Version commit: `6dbd34e7ce612ad8d23db24c9b0b78f4a182a66e` (`2026-1155`);
  Development CI run `36209437647` passed:
  https://github.com/dinggood615/openkill/actions/runs/36209437647
- RC Build run `36209058686` passed from the source-fix commit. The audited
  2026-1154 candidate was retained in `D:\openkill-cache\rc-2026-1154-auto-bridge`;
  IPK SHA256 was
  `fc6072120f9ac400fa62573f8186644a6fed051c7d2df1af55c4ab3c024a4ed2`.
- Formal Release run `36209617084` passed with `release_gate=true` and
  `publish=true` from `6dbd34e`. The official release is
  https://github.com/dinggood615/openkill/releases/tag/v2026-1155-ipk and its
  package `luci-app-openkill_2026-1155_all.ipk` has SHA256
  `4393c86752319c9b73413edc432be3913048c23934da014dad6c2082fc1cd20d`.
  The published tag targets `6dbd34e7ce612ad8d23db24c9b0b78f4a182a66e`;
  the previous release and rollback asset remain intact.
- Local evidence: Naive integration, UI contract/interaction/preview tests,
  POSIX syntax checks, `scripts/local-gate.sh`, `git diff --check`, and final
  package marker inspection passed. The formal package contains the diagnostic
  state endpoint, generator stage checks, and UI status hook.
- This release has no new device or remote-endpoint run. The earlier device
  evidence below remains separate; automatic-mode internet connectivity for
  this exact release is therefore device-pending rather than claimed as fixed.

## NaiveProxy node editor runtime error (2026-09-25)

- Device phase is authorized for the supplied NaiveProxy node on
  `192.168.1.103`. The reported Add/Import actions reach the existing server
  editor, but LuCI renders `openkill/tblsection` before the editor loads.
- Scope of this fix is limited to the edit-link renderer and its regression
  contract. It must preserve the selected YAML query, stable UCI server IDs,
  node credentials and the existing add/import/manage routes. No DNS, routing,
  firewall, legacy writer, parser or bridge lifecycle behavior is changed.
- Root-cause hypothesis to verify on the device: `self.extedit:format(section)`
  interprets percent-encoded `file=` bytes such as `%2F` as extra format
  directives, producing `bad argument #2 to 'format'`. The implementation will
  replace only the explicit `%s` route placeholder and leave encoded query
  bytes untouched, then exercise add, import and manage URLs.
- Before device changes, take a protected configuration/package backup. The
  follow-up release must distinguish template rendering, form save, local
  SOCKS5 readiness and remote authentication; credentials remain off output,
  logs, reports and commits.

## NaiveProxy device node validation (2026-09-25)

- Device phase authorized by the user for `192.168.1.103` after the 2026-1149
  installation. Scope is a protected backup, redacted component/state checks,
  importing one supplied NaiveProxy node, applying the helper bridge, and
  checking the local SOCKS5 readiness and remote authentication result.
- Credentials must be sent only through the protected UCI/Naive runtime files;
  they must not appear in command output, logs, status JSON, generated YAML,
  reports or commits. Do not enable `CENTRAL_ACTIVE`, apply central nft state,
  alter WAN/default gateway, or run broad packet-path tests. Restore the backup
  if the node import or service lifecycle fails.
- Resume condition: after device evidence, repair any reproducible source
  defect locally, run all gates, publish a new version only if code changes
  are required, and record the redacted device result separately from local
  and remote endpoint validation.

### Device evidence and fixes (2026-09-25)

- Rechecked the authorized target with `ssh -o BatchMode=yes openkill-103`.
  It is Kwrt 25.12-SNAPSHOT x86_64 with OpenKill `2026-1149`; `curl`,
  `jsonfilter`, `xz` and `xz-utils` are installed.  The configured binary
  `/etc/openkill/core/naive` is executable and reports `150.0.7871.63`.
- A protected device backup was created before configuration changes at
  `/tmp/openkill-naive-backup-20260925-200732.tgz` (SHA256
  `dfb54e988cb60990d80125e9d6e13b6609969c39d1cc1085f125778e680cdf81`).
  A second protected code backup is at
  `/tmp/openkill-naive-code-backup-20260925-201140.tgz` (SHA256
  `aa949db502764af83da435ce12dc3f7f491192e9d527499b5e3e1502176a32ed`).
- Root cause 1: anonymous UCI `servers` sections were enumerated with plain
  `uci show`, yielding `@servers[0]`; the Naive helper rejected that as an
  invalid stable ID, so it reported `no-enabled-nodes` and generated no
  bridge.  The helper and init loops now use `uci -X show`.
- Root cause 2: direct helper status/prepare calls did not load
  `/lib/functions.sh`, so `config_load` failed silently outside the init
  process.  The helper now loads the OpenWrt config functions when available.
  It also reports `local_ready=1` only after every generated loopback port is
  listening.
- Root cause 3: this device's OpenWrt Naive build fails authenticated TLS when
  procd launches it as root with the `nogroup` group (`broken pipe` and
  `net_error -100`).  The Naive instance now stays in the root group; the
  change is limited to the helper process and does not alter transparent
  interception ownership.
- The supplied node was imported into one stable UCI `servers` section with
  credentials retained only in protected device configuration.  The source
  YAML was then updated with a credential-free `127.0.0.1:11080` SOCKS5
  bridge and its name was added to the existing streaming group.  The final
  active YAML contains the bridge; no credentials were written to YAML.
- Device result after the fixes: OpenKill `running`; helper state is
  `configured=1`, `generated=1`, `component_installed=1`, `local_ready=1`,
  `remote_verified=0`; the loopback listener accepted a proxied request to a
  fixed HTTPS test endpoint and returned HTTP 204.  This proves local
  process/bridge and one TCP remote request, not UDP, IPv6, streaming unlock
  or general LAN packet-path behavior.
- One temporary test invocation exposed a legacy writer hazard: running
  `yml_proxys_set.sh` while UCI has no imported groups can replace the YAML
  proxy/group arrays and make strict DNS refuse startup.  The backed-up YAML
  was restored before the final device restart, then the bridge was added
  while preserving the existing groups.  A follow-up local contract is needed
  before changing that legacy writer; no broad writer change is included in
  this device fix.
- Next action: commit the bounded stable-ID, standalone-helper, listener-state
  and root-group fixes; run gates and exact-commit CI, then use the formal
  release gate for the next version.  Device remote verification remains
  limited to the single redacted TCP probe above.

### 2026-1150 delivery and candidate-device verification (2026-09-25)

- Bounded source commit `6f02e095e523219b6312375b3703dcaa3e10f858` contains
  the stable anonymous-UCI enumeration, standalone config-helper loading,
  loopback listener readiness and device-specific root-group lifecycle fixes.
  Local NaiveProxy/UI/installer tests, POSIX checks, `local-gate` and
  `git diff --check` passed before push.
- Exact Development CI passed for that commit:
  [run 36135974228](https://github.com/dinggood615/openkill/actions/runs/36135974228).
  RC Build passed:
  [run 36136111931](https://github.com/dinggood615/openkill/actions/runs/36136111931).
  Candidate `luci-app-openkill_2026-1150_all.ipk` SHA256 is
  `0d5474c490f728247b389ebbb6757db30c8a733cd8dfc0041a9db51bfbf4d84f`.
- Formal Release passed with `release_gate=true` and `publish=true`:
  [run 36136659284](https://github.com/dinggood615/openkill/actions/runs/36136659284).
  Published [v2026-1150-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1150-ipk)
  from the same commit.  Formal IPK
  `luci-app-openkill_2026-1150_all.ipk` SHA256 is
  `49f2971a6366d770f0c96dc29f74d03d3c9c240deec60bf45a9a6061b4c74c01`;
  previous v2026-1149 remains available for rollback.
- Before installation, the device backup was created at
  `/tmp/openkill-naive-postrelease-backup-20260925-2052.tgz` with SHA256
  `bb50eecb2a9eb7d2f4e058c9cca9ea8338f84ee5615c50c1ed52c4f378a95e48`.
  The uploaded package hash matched the formal asset before `opkg` upgraded
  OpenKill to 2026-1150.  The service is `running`; the component reports
  `naive 150.0.7871.63`; the helper state is
  `configured=1/generated=1/component_installed=1/local_ready=1` with
  `remote_verified=0`.  The active and selected YAML each retain the
  credential-free loopback bridge and its streaming-group reference.  A
  fixed TCP SOCKS5 probe returned HTTP 204; UDP, IPv6, streaming unlock and
  broad LAN packet-path behavior remain unverified.
- The package-manager upgrade emitted a transient `ubus service delete`
  message while stopping the old service, but the installed package and
  service recovered and the post-install checks above passed.  The protected
  backup is the rollback path; reinstall v2026-1149 and restore that backup
  only if a configuration rollback is needed.

## NaiveProxy inline node workflow (2026-09-25)

- Scope: keep the existing server editor as the single UCI owner, but open
  its add/import/manage routes inside an accessible modal on the Compatibility
  & Auxiliary page. Move `naive_bridge_mode` into the NaiveProxy card layout
  so it is no longer rendered under the generic Other Settings card.
- Contract: the modal preserves the current selected YAML file and existing
  stable server IDs; saving, importing, enabling and deleting continue through
  the existing CBI editor. No duplicate node schema or credential endpoint is
  introduced. Closing the modal refreshes component and bridge status.
- Validation: assert that the card owns `naive_bridge_mode`, the page uses
  in-page modal buttons instead of top-level navigation links, and the legacy
  editor routes remain available. Run local UI/Naive tests and gates. Device
  and remote endpoint validation remain outside this local step.
- Implementation commit `3b6b44b2a015de89a42bfc3677e56c81252c02cc` adds the
  accessible in-page node-editor modal, keeps the existing CBI editor as the
  single credential/UCI owner, and moves `naive_bridge_mode` into the
  NaiveProxy card. Its exact Development CI passed
  ([36127049657](https://github.com/dinggood615/openkill/actions/runs/36127049657)).
- Version commit `e5f27d0b9588d2bd062ae234c620e82058b6c42a` prepared
  2026-1149 and its exact Development CI passed
  ([36127247152](https://github.com/dinggood615/openkill/actions/runs/36127247152)).
  The RC Build passed ([36127402062](https://github.com/dinggood615/openkill/actions/runs/36127402062));
  the audited candidate IPK SHA256 is
  `71e9ec0531fcad677ab3fa992a2e37fbf41723617657915944d3e4fbc7f2bc28`.
- Formal Release passed with `release_gate=true` and `publish=true`
  ([36127769222](https://github.com/dinggood615/openkill/actions/runs/36127769222)).
  [v2026-1149-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1149-ipk)
  is published from the version commit; its formal IPK SHA256 is
  `e70a905cd91cf07fedc58fca74da6f61c9d74f566d715dc392506a9cb3dfd5c4`.
  The previous 2026-1148 release remains available for rollback. Device,
  browser rendering and remote Naive endpoint validation were not performed
  in this local-only step.

## NaiveProxy automatic versus self-managed YAML mode (2026-09-25)

- Scope: add an explicit bridge mode to the existing NaiveProxy integration.
  `auto` writes credential-free loopback SOCKS5 entries into the generated
  Mihomo profile; `manual` keeps the helper and status lifecycle but only
  exposes the generated loopback snippet for a user-managed YAML file.
  Installation, DNS, routing, legacy writers, parser grammar and ABI remain
  unchanged.
- Contract: the mode is normalized to `auto` when absent or invalid. The
  generator checks the mode before injecting a bridge, while the diagnostic
  endpoint reports the same mode and continues to expose no credentials.
  Manual mode never silently becomes DIRECT and does not stop the helper.
- Validation: add integration assertions for UCI default, normalization, UI,
  generator guard and endpoint response; run local tests and gates. No device
  or packet-path validation is authorized in this local step.
- Implementation commit `abc5cab9f1023a1b3ed552d7647b35c92d5decd9` adds the
  normalized `naive_bridge_mode` field, the compatibility-page selector, the
  generator guard and mode-aware credential-free bridge status. Its exact
  Development CI passed ([36117294535](https://github.com/dinggood615/openkill/actions/runs/36117294535)).
- Version commit `6238417bc97747e1582a7659c95733f0f605eb47` prepared
  2026-1148 and its exact Development CI passed
  ([36117509671](https://github.com/dinggood615/openkill/actions/runs/36117509671)).
  The RC Build passed ([36117683662](https://github.com/dinggood615/openkill/actions/runs/36117683662));
  the audited candidate IPK SHA256 is
  `4bfe67cb58a8c7ec04fd522131a73a5c2a1e1b9475ad89b13a5fb1e05d6062c`.
- Formal Release passed with `release_gate=true` and `publish=true`
  ([36118327110](https://github.com/dinggood615/openkill/actions/runs/36118327110)).
  [v2026-1148-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1148-ipk)
  is published from the version commit; its formal IPK SHA256 is
  `559e722c090912cd7c454da13476bfb17541463ba670301c11e4d0ee1d1aa31f`.
  The previous 2026-1147 release remains available for rollback. Device and
  remote Naive endpoint validation were not performed in this local-only step.

## NaiveProxy page installation task flow (2026-09-23)

- Scope: fix the NaiveProxy component installation request chain and expose
  truthful progress. The change affects only metadata-to-install UI wiring,
  the NaiveProxy helper task state, and its LuCI endpoint; it does not change
  DNS, transparent interception, node credentials, legacy writers, or ABI.
- Contract: metadata detection remains read-only and returns a complete result
  to the caller. Installation is a single locked background task with a
  random task identifier, stage/result state, bounded log text, and polling.
  A second install request returns the existing task instead of starting a
  duplicate download. A failed replacement preserves the previous component.
- Device gate: the authorized SSH target currently timed out during the first
  recheck; package/path/dependency evidence must be refreshed before any
  device change. No device configuration or packet-path test is permitted in
  this local implementation step.
- Next action: implement the task contract, add offline behavior tests, run
  local-gate, then push the bounded change and verify its exact Development CI
  before RC and Formal Release.
- Recheck evidence: SSH access is available again. The device is running
  OpenKill 2026-1141 with `xz`, `xz-utils`, `jsonfilter`, and `curl` present;
  URL and SHA256 fields are configured, but `/etc/openkill/core/naive` is
  absent and the state file reports `component_installed=0`. The recent
  install log records a `Trace/breakpoint trap` while probing `naive.new`.
  The same configured asset and digest install successfully in an isolated
  `/tmp` directory and reports `naive 150.0.7871.63`, so the failure is in the
  synchronous request/probe path or its target attempt, not missing xz or an
  invalid digest. A protected pre-change backup is at
  `D:\openkill-device-backup-20260923-naive-task\openkill-naive-task.tgz`
  (SHA256 `ea3e089b354dcb30d1dd77af7e5a1a376e9a120556e6628a11f8a6b4c2adc43d`).
- Implementation commit `fab25321e11b3519283df033ef4a1d59da044f01` is on
  `master`; its exact Development CI passed
  ([35855847226](https://github.com/dinggood615/openkill/actions/runs/35855847226)).
  The 2026-1141 RC audit also passed
  ([35856086037](https://github.com/dinggood615/openkill/actions/runs/35856086037));
  the audited IPK SHA256 is
  `06b300390d72bf9a79f8744d3a0ce153001b86372cdb1f36fd937e468c3e6cbb`.
  Version metadata and release notes for 2026-1142 are prepared; the next
  action is its exact Development CI, Formal Release, and device candidate
  installation.
- 2026-1142 metadata commit `a219b1f848d4a16051d69563c8448d8f65b99e3b`
  passed exact Development CI
  ([35856793818](https://github.com/dinggood615/openkill/actions/runs/35856793818)).
  Formal Release passed with both gates enabled
  ([35857008078](https://github.com/dinggood615/openkill/actions/runs/35857008078));
  [v2026-1142-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1142-ipk)
  is published. The downloaded formal package is 9,226,016 bytes with SHA256
  `f6a65639935a5b336161cf80a0102b954c3a423e449d86c5c4937a2f23e1cc48`, and
  its packaged helper contains the task and polling commands.
- Device evidence after the protected backup: OpenKill 2026-1142 installed,
  the configured URL and digest remained present, and the real device task
  completed `queued → succeeded/completed`. The installed component is
  root-owned, executable, and reports `naive 150.0.7871.63`; the refreshed
  state reports `component_installed=1`, `state=disabled`,
  `reason=no-enabled-nodes`, `local_ready=0`, `remote_verified=0`. The
  OpenKill service is currently inactive because its selected `openkill`
  configuration file is absent; start attempts record `Config Not Found`.
  No node was enabled and no packet-path or remote-authentication test ran.
  The pre-install backup remains at
  `D:\openkill-device-backup-20260923-naive-task\openkill-naive-task.tgz`.
  The follow-up evidence commit `23f3a2365d0255ba1d9877a410bb45b6d7e2645f`
  also passed exact Development CI
  ([35857677654](https://github.com/dinggood615/openkill/actions/runs/35857677654)).

## Settings navigation and network card layout (2026-09-23)

- Scope: presentation-only changes to the LuCI settings navigation, card
  grouping, and responsive CSS. DNS, IPv6, TUN, access-control, traffic
  routing, UCI field names, legacy writers, parser behavior, ABI constants,
  and continuity semantics remain unchanged.
- Navigation contract: the compatibility tab keeps the existing stable key
  and UCI ownership, moves between Network & Routing and Rules &
  Subscriptions, and is labelled “兼容与辅助”. The former tab label and
  `/naive` bookmark redirect remain accepted for migration.
- Visibility contract: System Maintenance is visible by default and its
  maintenance card is expanded; the user-facing “隐藏高级设置” toggle is
  removed without deleting or renaming maintenance fields.
- Network layout contract: DNS & Local Resolution pairs with IPv6 & TUN;
  LAN/WAN Access pairs with Traffic Routing. Desktop rows stretch to their
  tallest card, while narrow viewports use one column. No fixed heights or
  network-policy changes are permitted.
- Implementation evidence: `settings.lua` now orders Network & Routing,
  Compatibility & Auxiliary, and Rules & Subscriptions in that sequence;
  `settings_theme.htm` accepts both compatibility labels for tab resolution,
  removes the advanced-settings toolbar control, keeps System Maintenance
  visible, and keeps its card expanded. Network DNS no longer promotes the
  entire card to a full-width row, so IPv6/TUN and LAN/WAN pair with the next
  cards in the shared two-column grid. `oc.css` keeps the static maintenance
  heading visually consistent with the other cards.
- Local evidence: WSL `test-installer.py` (11 tests, one environment skip),
  `test-ui-contract.py` (25 tests), `test-ui-preview.py` (2 tests),
  `git diff --check`, and `scripts/local-gate.sh` pass. The standalone browser
  probe reports `PLAYWRIGHT_UNAVAILABLE` on this host; no rendered screenshot
  is claimed from that unavailable dependency. No device or packet-path test
  was used.
- Delivery status: presentation commit
  `7ec43075375a8a69ec57a60bff8e88c89b2729a8` is on `master`. Its exact
  Development CI passed ([35847220504](https://github.com/dinggood615/openkill/actions/runs/35847220504));
  the clean jsDelivr check passed ([35847220219](https://github.com/dinggood615/openkill/actions/runs/35847220219)).
  The 2026-1140 RC Build passed ([35847382643](https://github.com/dinggood615/openkill/actions/runs/35847382643));
  its audited package SHA256 is
  `4ddba320ab058ca84a99d5012447a4dd40665a48c43b76ec569bfaf48cc3ef3f`.
  Version metadata and release notes for 2026-1141 were prepared in commit
  `7100fa8b43bf448a4cace58f28b58ca189a2e935`; its exact Development CI
  passed ([35848107679](https://github.com/dinggood615/openkill/actions/runs/35848107679)).
  Formal Release initially hit a transient upstream 403 while refreshing
  third-party resources ([35848293474](https://github.com/dinggood615/openkill/actions/runs/35848293474));
  the authorized retry passed with `release_gate=true` and `publish=true`
  ([35848616900](https://github.com/dinggood615/openkill/actions/runs/35848616900)).
  The formal package is published as
  [v2026-1141-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1141-ipk)
  and the package-channel asset
  `luci-app-openkill_2026-1141_all.ipk` has SHA256
  `e24c2d1922673402994fa5acc93853cd5a7b55f08f21af1bcad9ac3b0dbbe5f3`.
  The package channel manifest points to commit `7100fa8b43bf448a4cace58f28b58ca189a2e935`.
  A post-release RC audit from the current master evidence commit also passed
  ([35849483187](https://github.com/dinggood615/openkill/actions/runs/35849483187));
  its 25.12 SDK package SHA256 is
  `1600bb2f23ef3d0085271d9d9c26e2d52b94aa0c63361f15f32cb7837483318d`,
  with package metadata, conffile, deletion, stale-reference and sensitive
  content audits all OK.

## NaiveProxy installer archive compatibility (2026-09-23)

- Device recheck found the configured official x86_64 asset downloads
  successfully and matches the configured SHA256, but the Kwrt image has
  BusyBox `tar` without xz support and has no `xz` executable. The installer
  therefore failed while reading the `.tar.xz` archive before extracting the
  `naive` ELF. The OpenKill package did not previously declare an xz runtime
  dependency, so the UI surfaced only a generic install failure.
- Contract: the package now depends on OpenWrt `xz`; the installer decodes
  `.tar.xz` into a private temporary archive, validates member paths, extracts
  only the expected executable, then applies the existing ELF, architecture,
  loader/version probe and atomic replacement checks. Download and digest
  semantics remain unchanged, and decompressor absence is a hard failure that
  preserves the previous component.
- Device evidence before the fix: package `2026-1137` was installed and
  `naive_enabled=1`, but all approved component paths were absent and the
  helper reported `component_installed=0`, `reason=component-not-installed`.
  A direct download measured 3,397,604 bytes and matched the configured digest;
  BusyBox reported `tar: invalid tar magic` for the xz archive. The first
  2026-1138 candidate added xz and extracted the archive, but then exposed a
  second BusyBox gap: `od` is absent although `hexdump` is available, so the
  ELF architecture probe rejected the valid binary. No node credentials or
  packet-path tests were used. The corrected helper was then run in an
  isolated device directory and completed the full install path successfully,
  producing an executable whose version probe returned `150.0.7871.63`.
- A follow-up device check after installing the binary found a stale-state
  defect: the file and version probe succeeded, but `/tmp/openkill-naive.state`
  still contained the pre-install `component_installed=0` record because the
  helper's `status` action only printed the old file. This could make the UI
  report “组件未安装” after a valid manual or page-driven installation.
- The helper now refreshes the state file from the configured executable on
  every `status`, refreshes it after successful `install`, and records a
  separate `component-installed-needs-prepare` state when enabled nodes still
  require generation. Missing binaries reset only the component availability
  fields; node configuration is retained. This keeps installation, local
  entry readiness and remote verification independent.
- Local evidence after the change: `NAIVEPROXY_INTEGRATION_CONTRACT=PASS`,
  POSIX syntax, `git diff --check`, and `scripts/local-gate.sh` pass. The
  device's manually installed component remains executable at the configured
  path and reports `naive 150.0.7871.63`; its previous stale state will be
  refreshed by the updated helper.
- Delivery evidence for this fix: status-refresh commit
  `6fad2ba7ebce25fc0484a7c4517895c4d120fb9c` reached `master` and its exact
  Development CI passed ([35829223609](https://github.com/dinggood615/openkill/actions/runs/35829223609)).
  The version metadata commit `5f773dd42e0f84c50f2a3641b399b11a5344013b`
  prepared 2026-1140 and its exact Development CI passed
  ([35829445974](https://github.com/dinggood615/openkill/actions/runs/35829445974)).
- The 2026-1140 RC Build passed ([35829622739](https://github.com/dinggood615/openkill/actions/runs/35829622739));
  `luci-app-openkill_2026-1140_all.ipk` is 7,652,311 bytes with SHA256
  `c12f4724e22ab6b5fb610224c067712849322b935310e2aace98b49edbdb187d`.
  The RC audit reported package metadata, conffile preservation, maintainer
  script deletion, stale-reference and sensitive-content checks as OK.
- The authorized device was upgraded from 2026-1139 to 2026-1140 after an
  upload SHA256 match. It remains enabled and running; the configured
  `/etc/openkill/core/naive` is root-owned, executable, and reports
  `150.0.7871.63`. The updated helper reports
  `component_installed=1`, `configured=0`, `generated=0`,
  `state=disabled`, `reason=no-enabled-nodes`, `local_ready=0` and
  `remote_verified=0`. The protected `/etc/config/openkill` hash stayed
  `0bf7be81c9f5d8b959722978e8ee40c66392a2a5ee3165b2f14ed229a0dca52c`; no
  node was enabled and no packet-path or remote-authentication test ran.
- Formal Release #162 passed with both release gate and publish enabled
  ([35830055217](https://github.com/dinggood615/openkill/actions/runs/35830055217))
  and published [v2026-1140-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1140-ipk).
  The downloaded formal asset `luci-app-openkill_2026-1140_all.ipk` is
  9,224,693 bytes with SHA256
  `281bfe4204fe3744a27740c8842168a26908e29055f5e966e970f9d8cc8b8e907`;
  its packaged helper contains the xz decoder, BusyBox hexdump fallback and
  status refresh fix. The formal asset is retained separately from the
  25.12 RC package used for device validation.
- Classification: component installation and truthful status refresh are
  repaired and device-verified; share-link parsing and isolated bridge
  generation remain locally verified; a real Naive node's remote login,
  local SOCKS5 readiness and business traffic remain device-unverified.
- Next action: keep the 2026-1140 release and rollback package, and only
  begin a new versioned batch when a separately scoped defect or feature is
  authorized.

## NaiveProxy device detection and share-link import (2026-09-23)

- Device phase is authorized for `192.168.1.103` with a protected backup at
  `D:\openkill-device-backup-20260923\openkill-naive-backup.tgz`. The first
  read-only check found OpenKill `2026-1136` installed and its Mihomo process
  running, but no executable at the configured `/etc/openkill/core/naive` or
  the approved fallback locations. `naive_enabled=0`; no Naive helper was
  started and no packet-path test was performed.
- Detection contract: distinguish the OpenKill package, the NaiveProxy
  executable, node configuration, generated bridge, local listener and remote
  authentication. A missing executable must not be represented as a stale
  status-file failure, and a locally installed binary must still be marked
  unverified until its executable/version probe succeeds.
- Import contract: reuse the existing server URL importer and add only
  `naive+https://`, `naive+quic://`, and `naiveproxy://` forms. Parse with the
  existing structured URL helper, decode credentials once, map only supported
  transport fields, warn about unknown parameters, and never log or return
  credentials. Stable UCI section identity and the existing loopback SOCKS5
  bridge remain authoritative; generated Mihomo entries keep `udp: false`.
- Persistence contract: importing fills the current node editor and requires
  the normal CBI save/apply. It must not enable the helper, install a binary,
  select DIRECT, or overwrite a user policy automatically. Component
  installation remains explicit and uses the existing HTTPS/digest/ELF/
  loader/atomic replacement checks.
- Device evidence: the authorized candidate install upgraded the device from
  OpenKill `2026-1136` to `2026-1137`; the protected `/etc/config/openkill`
  hash remained unchanged, the service stayed enabled/running, and the
  configured/fallback Naive paths were absent. The helper therefore reports
  `component_installed=0`, `state=unavailable`,
  `reason=component-not-installed`; this is the expected distinction between
  the OpenKill package and the optional NaiveProxy binary. No node process or
  remote authentication was started.
- Local evidence: `NAIVEPROXY_IMPORT_BEHAVIOR=PASS`, the NaiveProxy contract,
  UI contract, UI preview, POSIX syntax checks, `git diff --check` and the
  local gate pass. The importer accepts the supported share-link schemes,
  maps IPv4/IPv6, TLS/TCP/QUIC and percent-encoded credentials, and escapes
  parameter warnings before rendering them.
- Delivery evidence: status wording commit
  `c331488644ce56e0791163bbf02135e8ae9b761e` is on `master` and its exact
  Development CI passed ([35823101717](https://github.com/dinggood615/openkill/actions/runs/35823101717)).
  The final 2026-1137 RC Build passed ([35823202127](https://github.com/dinggood615/openkill/actions/runs/35823202127)).
  Formal Release passed with the release gate and publish enabled
  ([35823541381](https://github.com/dinggood615/openkill/actions/runs/35823541381));
  it published [v2026-1137-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1137-ipk).
  The formal package `luci-app-openkill_2026-1137_all.ipk` has SHA256
  `941bbc21a9fdfc79ab91828dd65ed474384a6a28ea06c5cae0f8edcdc7ceed9e`.
  The package audit confirms version 2026-1137 and includes the status view,
  compatibility view and share-link importer. The device was upgraded to
  2026-1137 with its OpenKill configuration hash unchanged; no optional Naive
  binary or remote authentication was started.
  The follow-up evidence commit `39b9964c6902d89f165bd86e3e421322f213c722`
  is now the master tip and its exact Development CI also passed
  ([35824176728](https://github.com/dinggood615/openkill/actions/runs/35824176728)).
- Next action: if the optional NaiveProxy binary is installed on the device,
  use the new re-detect action, import a node through the existing editor,
  and separately verify the loopback bridge and remote authentication. Those
  runtime and packet-path checks remain device-scoped and are not claimed by
  this release.

## NaiveProxy compatibility unified entry and installation flow (2026-09-23)

- Rechecked baseline `452a950610a326c9bbd305845974b0fd83cc2e63` with a clean
  worktree before this change. Device access and packet-path tests remain out
  of scope for this local iteration.
- Navigation contract: the legacy `/naive` route remains a bookmark redirect,
  but no longer has a LuCI menu title. Compatibility settings is the only
  visible owner of `naive_*` fields.
- Settings/UI contract: OpenVPN exact compatibility and the NaiveProxy helper
  are ordinary cards in the same responsive two-column grid. The cards stretch
  within their active desktop row and collapse to one column on narrow layouts;
  no fixed-height or placeholder layout is introduced.
- Metadata contract: discovery is draft-only and never commits UCI. URL and
  SHA256 are treated as an inseparable asset pair; automatic fill only occurs
  when both fields are empty, preserving manual values and preventing a mixed
  URL/digest installation.
- Component contract: the compatibility card provides explicit detect, refresh,
  automatic match-and-install, install-current and remove actions. Installation
  continues through the existing HTTPS allow-list, digest/size/archive/ELF/
  loader checks and atomic replacement boundary.
- Node/bridge contract: the compatibility card links to the existing NaiveProxy
  node editor and strategy-group manager. Existing stable-section-ID port
  allocation and loopback-only SOCKS5 generation remain the source of truth;
  no native `type: naiveproxy` is sent to Mihomo and UDP remains disabled until
  separately verified.
- Local evidence: NaiveProxy integration contract, UI contract, UI preview,
  extracted JavaScript syntax check, `git diff --check`, POSIX metadata/helper
  syntax and `scripts/local-gate.sh` pass. Browser rendering, actual component
  installation, remote authentication and device behavior remain unverified.
- Delivery evidence: implementation commit
  `cdf2b6b011f26f1d520dba0a5d411c7de68f1898` and version commit
  `ba7684eadaf87aabb12beddafa758abf83054ff3` were pushed to `master`.
  Development CI passed for the implementation commit
  ([35818160394](https://github.com/dinggood615/openkill/actions/runs/35818160394))
  and the version commit
  ([35818333176](https://github.com/dinggood615/openkill/actions/runs/35818333176)).
  RC Build run 59 succeeded
  ([35818559036](https://github.com/dinggood615/openkill/actions/runs/35818559036));
  its audited candidate was `luci-app-openkill_2026-1136_all.ipk` with SHA256
  `519a0b9c42e8026c193fcff5b757078ef1f273afe0961099953e8d8a1f977292`.
  Formal Release run 160 succeeded with `release_gate=true` and
  `publish=true`
  ([35818895168](https://github.com/dinggood615/openkill/actions/runs/35818895168));
  it published `v2026-1136-ipk` and
  `luci-app-openkill_2026-1136_all.ipk` with SHA256
  `0cc3278d006027c7e67a68ee4ae3b067cb96123a9c8c1b62728df5262e3bc8ac`.
  No device installation, browser rendering or remote NaiveProxy
  authentication was performed; keep `v2026-1135-ipk` as the rollback point.

## NaiveProxy compatibility settings and metadata discovery (2026-09-23)

- Scope: move the existing NaiveProxy component controls and status actions
  into the Plugin Settings compatibility tab. The old dedicated route remains
  as a redirect so bookmarks do not create a second UCI editor.
- Settings contract: one set of `naive_*` fields is rendered by the
  compatibility CBI model. Component metadata discovery is an explicit user
  action; it may fill only empty URL/SHA256 fields and never enables nodes,
  installs a binary or restarts OpenKill implicitly.
- Metadata contract: query the official `klzgrad/naiveproxy` latest release
  API, map a detected OpenWrt CPU family to an `openwrt-*` asset, and require
  the GitHub asset `digest` before presenting an installable suggestion.
  Unknown architectures, missing digests, API errors and stale data remain
  visible as unavailable or pending verification; the source URL is never
  guessed and a source archive is never treated as an executable.
- Lifecycle contract: the existing HTTPS allow-list, size limit, archive
  traversal check, ELF architecture check, loader/version probe and atomic
  replacement remain the installation boundary. Metadata lookup only returns
  URL, digest, size, release and architecture facts. Manual values are
  preserved unless the user explicitly requests replacement.
- UI contract: the compatibility tab owns the NaiveProxy settings card and
  status/metadata controls. Desktop cards share the current two-column grid;
  long URLs, SHA256 values and errors wrap inside the card and narrow layouts
  collapse naturally. Existing Mihomo, DNS, adblock, region, RustDesk and
  OpenVPN contracts are unchanged.
- Validation plan: offline metadata parser fixtures, LuCI controller/CBI
  contract checks, final CSS/template preview, POSIX syntax and local-gate;
  no device or remote NaiveProxy session is required for this UI change.
- Working-tree validation from baseline `54726821a62d27983c200bfe531cd08457f24d7b`:
  `test-naiveproxy-integration.py`, `test-ui-contract.py`,
  `test-ui-preview.py`, JavaScript syntax check, metadata shell syntax and
  `scripts/local-gate.sh` pass. A WSL fixture run matched the official latest
  x86_64 asset and GitHub digest; unknown/missing parser paths remain
  fail-closed. No device or remote NaiveProxy session was used.
- Delivery evidence: implementation commit `b98bd34db2ccc9707976d1cb29b9423ba4ad2333`
  passed Development CI
  ([35812016741](https://github.com/dinggood615/openkill/actions/runs/35812016741));
  version/release commit `27257f5c0c28068a93ec5945b81e1a7fd09acb44` passed
  Development CI
  ([35812222147](https://github.com/dinggood615/openkill/actions/runs/35812222147)).
  RC Build
  ([35812353895](https://github.com/dinggood615/openkill/actions/runs/35812353895))
  produced `luci-app-openkill_2026-1134_all.ipk`, SHA256
  `a428acb1ba44ef9233ab02abff12583aa92fe42766fd58854fb105c13df2dc8`.
  Formal Release with both gates enabled succeeded
  ([35812770176](https://github.com/dinggood615/openkill/actions/runs/35812770176));
  published tag `v2026-1134-ipk` and package SHA256
  `6d7e61a77024722b33566651d0a62de5825341148ff916f2ddbe48738b340a2a`. No
  device installation or remote
  NaiveProxy authentication was performed; retain `v2026-1133-ipk` for rollback.

## NaiveProxy metadata tag validation follow-up (2026-09-23)

- The metadata reader now rejects release tags containing characters outside
  the safe release-name alphabet before interpolating an asset selector into
  `jsonfilter`. A malformed upstream tag therefore remains unavailable and
  cannot alter the selector expression.
- `test-naiveproxy-integration.py`, WSL POSIX syntax and `git diff --check`
  pass for this follow-up. Because this is a post-release production fix, it
  must be versioned as `2026-1135` and pass the same Development CI, RC audit
  and Formal Release gates; `v2026-1134-ipk` remains a rollback point.
- Delivery evidence: fix commit `e83415783f028f46fcbc63d243836f0b28f7bf40`
  and version commit `e4408a3f5cb477fcc1bfd7695e4c2bd2a3e7bb56` passed
  Development CI
  ([35813424031](https://github.com/dinggood615/openkill/actions/runs/35813424031)).
  RC Build
  ([35813533691](https://github.com/dinggood615/openkill/actions/runs/35813533691))
  produced `luci-app-openkill_2026-1135_all.ipk`, SHA256
  `c523565482e38538ef2260091fc8edca26d52f0d35b2d2f5e12b9240ef3d2e3f`.
  Formal Release with both gates enabled succeeded
  ([35814129021](https://github.com/dinggood615/openkill/actions/runs/35814129021));
  [v2026-1135-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1135-ipk)
  points to the version commit and its downloaded package SHA256 is
  `8abbfdd89bd0f572bd0bfb8a68e54e7ad90d76f29fa6bc5cf4e40dddb55e09a0`.
  No device installation or remote NaiveProxy authentication was performed.

## Optional NaiveProxy bridge integration (2026-09-23)

- Scope: add an opt-in official NaiveProxy helper process that exposes one
  loopback SOCKS5 listener per stable OpenKill server section. Mihomo remains
  the only transparent-takeover core; NaiveProxy never owns TUN/TPROXY/REDIRECT
  or firewall state.
- Configuration contract: UCI server section -> validated helper JSON (mode
  0600) -> loopback SOCKS5 -> generated Mihomo `type: socks5` proxy. The UCI
  section ID, not the display name, is the stable node identity and port-map
  key. Credentials never enter command-line arguments or logs.
- Lifecycle contract: component disabled or absent means no helper instance;
  configured nodes may be saved but are reported unavailable. Preparation and
  core config validation precede application. Each state distinguishes
  configured, generated, local-listener-ready, remote-unverified and failed;
  failure never silently becomes DIRECT. Stop/remove only cleans OpenKill's
  own helper files and instances.
- Component contract: installation is optional, HTTPS-only, size/digest
  checked, staged and atomically activated with the previous binary retained
  for rollback. Architecture/libc support is explicit; no invented release
  asset or unverified package is accepted.
- Network contract: bootstrap resolution follows the existing DNS/privacy
  policy with an explicit no-loop exception when required. The bridge emits
  `udp: false` until UDP forwarding is separately verified. Fake-IP values are
  not sent as ordinary real addresses to the helper. The procd instance uses
  the existing `nogroup` (GID 65534) owner return contract so helper OUTPUT is
  excluded from OpenKill's own transparent rules; no broad port or firewall
  bypass is added.
- UI contract: reuse the existing node editor, component/settings patterns and
  status cards. NaiveProxy is shown as an optional component with responsive
  two-column forms and conservative lifecycle wording; existing users remain
  disabled by default. Legacy writers, DNS policy, category order, parser
  grammar, ABI and continuity behavior remain unchanged unless a reproduced
  bridge defect requires an explicit amendment here.
- Implementation evidence in the current working tree: `servers-config.lua`
  exposes a NaiveProxy node type and isolated credential/transport fields;
  `openkill_naive.sh` validates official HTTPS artifacts, ELF architecture,
  digest, safe extraction and 0600 JSON; `yml_proxys_set.sh` emits only a
  loopback `socks5` node with `udp: false`; the init script registers one
  procd instance per stable section ID and cleans only its own state.
- UI evidence: a dedicated NaiveProxy CBI page provides component fields and
  status/install/remove actions; the runtime dashboard card reports installed,
  configured, generated, local-ready and remote-unverified states. Existing
  DNS, adblock, OpenVPN and RustDesk state cards retain their independent
  semantics.
- Local checks completed: `scripts/test-naiveproxy-integration.py`, UI contract
  (25 tests), UI preview (2 tests), POSIX `sh -n` for the helper/generator/init,
  ELF architecture fixture, Python compileall and `scripts/local-gate.sh` all
  pass. No Naive binary, remote server or device packet path was used; remote
  connection and package installation remain unverified.
- Resulting source commit `a71acf5fddabd652334e2d1f3a1bb6e1e0bfc4e2` is on
  `master`; its Development CI run `35807220865`
  (https://github.com/dinggood615/openkill/actions/runs/35807220865) completed
  successfully. No RC or Formal Release was dispatched in this local-only
  iteration because the optional binary, remote Naive server and device phase
  were not available for the required runtime evidence.
- A follow-up source fix gates generated Naive nodes on `naive_auto_start` and
  probes the staged binary with both ELF architecture and `--version` loader
  checks before activation. Commit `02e0343861b1e186f2b39adc3a7c7a0a47faba19`
  is on `master`; Development CI run `35807460581`
  (https://github.com/dinggood615/openkill/actions/runs/35807460581) passed.
- The anti-loop contract is confirmed against the existing OpenKill owner rule:
  helper instances run in `nogroup` (GID 65534), which the fw4 and legacy
  OUTPUT chains already return before interception. Commit
  `100744b67216c9100649340be106920fc63b9326` is on `master`; Development CI
  run `35807708689`
  (https://github.com/dinggood615/openkill/actions/runs/35807708689) passed.
- Release preparation advanced the synchronized source metadata to
  `2026-1133` and added version-specific NaiveProxy notes. Commit
  `ed4486d0bcb23bca7e738e5191c7c5fd2f6e8b33` is on `master`; its exact
  Development CI run `35808776516`
  (https://github.com/dinggood615/openkill/actions/runs/35808776516) passed.
  Formal Release run `35808885468`
  (https://github.com/dinggood615/openkill/actions/runs/35808885468)
  completed successfully with `release_gate=true` and `publish=true`.
  Tag/release `v2026-1133-ipk`
  (https://github.com/dinggood615/openkill/releases/tag/v2026-1133-ipk)
  points to that source commit and publishes
  `luci-app-openkill_2026-1133_all.ipk` (9,215,921 bytes, SHA256
  `E5899857D6BD3A33465F147BE62FE4A53ECC7513C426D240A9D675644D4CBBC5`).
  Existing `2026-1132` release assets remain available for rollback. No
  device installation or live NaiveProxy server test was performed in this
  local-only iteration; those runtime paths remain unverified.


## Dashboard lower-right alignment and status evidence recheck (2026-09-19)

- Baseline rechecked before changes: master `e4a61dd5113776bdde3b8d9f8db30803de5c0b98`; working tree clean; device `192.168.1.103` reports OpenKill `2026-1131`, core `RUNNING/READY`.
- Scope for this iteration is limited to the runtime dashboard layout and status evidence. DNS, adblock routing policy, region bypass, RustDesk/OpenVPN policy, startup recovery, legacy writers, parser grammar, ABI and continuity contracts remain unchanged.
- Observed layout defect: `status.htm` promotes the legacy columns into independent `.dashboard-primary-column` and `.dashboard-secondary-column` grids. The secondary metrics row is four columns by two rows, so its intrinsic height ends before the primary configuration card and leaves an unowned lower-right area.
- Layout contract: keep the existing controls and event IDs, use one shared two-column content grid, render the eight real metrics as two columns by four rows on desktop, stretch only the existing metric rows to the shared content height, and let narrow layouts collapse naturally without fixed-height placeholders or negative offsets.
- Observed status defect: the controller exposes only `adblock_dns_effective`; the state file also contains `provider_effective`, but the page cannot distinguish generated state, DNS/Core loading evidence, and actual interception verification. The adblock contract will expose both backend fields and render conservative wording when loading or verification is unknown.
- OpenVPN status wording will keep transport bypass independent: a configured compatibility switch with transport bypass disabled must state that bypass is disabled, rather than implying an applied rule.
- Planned evidence: local UI contract/preview tests, final CSS/template inspection, headless browser screenshots at supported desktop/narrow viewports, device resource/hash and status recheck after candidate install, exact-commit Development CI, RC artifact audit, and Formal Release gate.
- Local evidence completed: UI contract 25/25, UI preview 2/2, OpenVPN compatibility contract PASS, optimization test PASS, `scripts/local-gate.sh` PASS, and `git diff --check` PASS. The optimization test emits a known Windows GBK reader traceback while its isolated assertions still return `OPENKILL_OPTIMIZATION_TEST=PASS`.
- Source commit `6b82790525b1b84233428bd8a859b42b0b06c5d7` was pushed to `master`; Development CI run `35447260582` completed successfully. RC workflow run `35447349836` completed successfully from the same commit.
- RC package `luci-app-openkill_2026-1132_all.ipk` was audited (package metadata/conffile/script/sensitive-content checks passed), SHA256 `65a22e7f9960a479AC4F6B673F42276DF6C8B2D86453B93775B1D78799BC897`, with root:root ownership and executable OpenKill shell scripts.
- Device backup before RC install: `D:\openkill-device-backups\20260919-2200-rc-2026-1132\openkill-before-2026-1132.tgz`, SHA256 `465743453391D1452A53B9F4380755D29F4A9632DD9F44EF3D2C0153D71166E9`. Candidate upload hash matched; device now reports package `2026-1132`, init service enabled/running, Mihomo process present after restart, adblock `state=generated` with DNS/Core loading and interception verification explicitly `unknown/0`, and OpenVPN `reason=disabled` with `applied=0`.
- Candidate resource hashes on the device match the RC package for the final CSS, status view, controller and adblock generator. Live authenticated LuCI browser rendering and external DNS/RustDesk/OpenVPN traffic remain device-pending; no packet-path or CENTRAL_ACTIVE test was run.
- Formal Release run `35447816238` completed successfully with `release_gate=true` and `publish=true`. GitHub tag/release `v2026-1132-ipk` points to source `157085aff8ed6ee0ba4391af26babc6fac6aa626`; the published asset is `luci-app-openkill_2026-1132_all.ipk`, 9,185,972 bytes, SHA256 `1AB2858146BCD15CDB83BD26155FE4E897F9B05B4A35ACBC17B92A733F372B20`.
- Formal device backup before the final asset: `D:\openkill-device-backups\20260919-2215-formal-2026-1132\openkill-before-formal-2026-1132.tgz`, SHA256 `9678C3F8E704F202AE82683365E244E192885473A70D9F763DDE43D6DA723694`. The formal asset upload hash matched; device remains on package `2026-1132`, service running after install, Mihomo process present, final CSS hash matches the formal package, and the user configuration remains preserved.

## Runtime dashboard/layout recheck (2026-09-19)

- Rechecked `master` at the current observed HEAD before this iteration and
  confirmed the working tree is clean. The authorized device is reachable;
  `luci-app-openkill` is installed at `2026-1130`, the OpenKill init service is
  enabled and running, Mihomo is listening on the configured controller/DNS
  sockets, and the health/watchdog processes are present. Historical startup
  failures are not treated as current evidence.
- The device log review found no new OpenKill/Mihomo error in the bounded
  recent window. Older stop artifacts contain an expected `ubus service delete
  ... Not found` message from an already-absent transient object; this remains
  a lifecycle/logging item to reproduce against the current source before
  changing it. Sensitive configuration and credentials are not copied into
  this plan.
- This iteration changes only page presentation and state evidence plumbing:
  runtime dashboard DOM/grid grouping, settings-card row stretching for the
  Network & Routing tab, and any narrowly reproduced log/status defect. DNS,
  legacy writers, category priority, parser grammar, ABI, and recovery
  contracts remain unchanged unless a reproduced defect requires an explicit
  contract update here.
- Layout contract: the top Running Status, Control Panel and Mix Proxy cards
  share one three-column equal-width grid; the content/configuration and
  metrics areas use one bounded two-column grid; settings cards remain
  content-sized and stretch only within their active row, including when
  conditional fields are revealed. The page remains scoped to OpenKill and
  responsive at 1920/1366/1200/768/390 CSS px and 100%/125% zoom.
- State contract: requested, generated, applied, verified, failed and unknown
  remain independent for DNS privacy, adblock, OpenVPN and RustDesk. A state
  file, process, HTTP 200 or saved UCI value never proves network validation.
- Browser-capable local evidence: the production preview was served over a
  local HTTP origin and rendered through installed headless Chrome. At the
  1920 CSS-px capture the three top cards are equal-width and aligned, the
  content/configuration and metrics columns share a two-column boundary, and
  DNS/adblock/OpenVPN/RustDesk cards are visible. The 768 capture naturally
  uses two columns; the 390 capture has no document horizontal overflow in
  the available desktop emulation. Playwright remains unavailable, so this is
  Chrome-headless evidence rather than a Playwright run.
- Device log root cause: the configured adblock source returned HTTP 404;
  the existing script correctly failed closed but had a stale built-in URL
  (`anti-ad-domains.txt`). The source now uses the maintained
  `https://anti-ad.net/domains.txt` default and retries that source only for
  the current generation when a user source fails. Both failures retain the
  last valid cache and keep DNS privacy independent. This fallback was
  exercised after the candidate reinstall: the device state reported
  `effective=1`, `provider_effective=1` and 107600 domains, while the log
  retained a generic source-fallback warning.
- Source commit `6defd705704a109770dc2e2d7b605ba4fbf5833b` was pushed to
  `master`; the exact OpenKill Development CI run `35443784718` completed
  successfully: https://github.com/dinggood615/openkill/actions/runs/35443784718.
- The OpenVPN status correction commit `88707d37a911781eb17582175c19c59939c8885c`
  passed its exact Development CI run `35444963099`:
  https://github.com/dinggood615/openkill/actions/runs/35444963099. The
  follow-up evidence commit `8ae80f2ed03ece9c588748ae5632cc550560c332` also
  passed Development CI run `35445400459`:
  https://github.com/dinggood615/openkill/actions/runs/35445400459.
- Formal Release run `35445726210` completed successfully:
  https://github.com/dinggood615/openkill/actions/runs/35445726210. It
  published tag `v2026-1131-ipk` at source commit
  `09842b11518d9c8e61d9bca0af17cbe964fff39c` and release page
  https://github.com/dinggood615/openkill/releases/tag/v2026-1131-ipk. The
  package-channel `master/version` is `v2026-1131`; the package-channel and
  release asset are both 9,185,445 bytes with SHA-256
  `76152E9C05640E00EC29186791F7846A6478D2BA168D0437D1D53836C0D4D8B3`.
- The formal asset was uploaded to the authorized device after a fresh
  protected backup at
  `D:\openkill-device-backups\20260919-213142-formal-2026-1131\openkill-before-formal.tgz`
  (SHA-256 `B09379D801E77745275925667F12A57061389E93540CA364EE60C7EB9C3B033D`).
  Remote and local package hashes matched. The device now reports package
  `2026-1131`, preserves the existing UCI configuration (opkg staged the
  package conffile as `openkill-opkg`), reaches Mihomo readiness, keeps the
  maintained adblock list effective, and reports the corrected OpenVPN
  disabled state. The previous release and both protected backups remain
  available for rollback.
- A non-public candidate was built from the master source, normalized to
  root-owned archive members, and audited. Candidate SHA-256 is
  `0C41597BEC8919330A1DD5A343BB8267A02E26100320D544725FA2B36894A237`.
  The protected pre-install backup is outside the repository at
  `D:\openkill-device-backups\20260919-210229-ui-adblock\openkill-before-rc.tgz`
  (SHA-256 `ADC2AE1A89F4129F72EA778F21343BBB1806DC979F43D0FB66E7DE640AACE563`).
  Upload and device SHA-256 matched. After reinstall and restart, the core,
  controller, TUN/DNS, proxy listeners, firewall readiness and watchdog were
  observed; the configured user adblock URL remained unchanged. This verifies
  the source fallback and lifecycle on this device, not strict DNS traffic,
  RustDesk connectivity, OpenVPN tunnel traffic or public IPv6.

### Planned order

1. Reproduce any current device log/status defect with a protected backup and
   sanitized output; classify code, configuration, upstream or environment.
2. Rework the production status DOM/grid and settings-card layout without
   changing control IDs or CBI persistence; add/adjust focused layout and
   state-contract tests.
3. Run local UI contracts/previews/browser capability checks, shell syntax,
   local-gate, diff/diff-check, commit and push `master`, then verify the exact
   Development CI run.
4. Build and audit a non-public RC from that commit, install only after a new
   device backup, and verify page rendering, service lifecycle and state
   recovery. Packet-path, RustDesk/OpenVPN client and strict DNS traffic
   claims remain separate device gates. The candidate install and restart
   have now completed; a stop/start recovery check and final page refresh are
  still required before a release decision.
- Device revalidation also reproduced a stale OpenVPN status field when the
  compatibility toggle was on but transport bypass was off: `generated=0`,
  `reason=disabled` was paired with `applied=1`. Commit `88707d3` changes the
  writer to report `applied=0` in that branch and adds a focused contract
  assertion. Its follow-up candidate (same package version, SHA-256
  `90574A95246D969A60C7708E8F0E84468BFFB6FD42FD89E0CCF32F0AB42254ED`) was
  uploaded after an independent local hash check. The device now reports
  `generated=0`, `applied=0`, `reason=disabled` while its core and readiness
  checks remain healthy.
5. Invoke Formal Release only if all repository release gates pass; retain the
   prior tag/assets and document any unverified traffic scenarios.

### Release preparation (2026-09-19)

- The previously published source/package version was `2026-1130`; the
  repository's formal workflow requires a strictly newer source version.
  After the functional and device checks above, release preparation advances
  the synchronized Makefile, installer, README and preview version to
  `2026-1131` and adds version-specific notes. This is a release-gate change,
  not a claim that the unverified traffic scenarios have passed.

## Running status startup/UI continuation (2026-09-19)

- Scope: authorized device `192.168.1.103`, source `master`, with no
  CENTRAL_ACTIVE, central nft apply, WAN/VMware changes, or broad LAN tests.
  Device changes must be backed up, reversible, and mirrored in source before
  any candidate reinstall.
- Startup contract under review: selected UCI config path must resolve to an
  existing readable YAML; core path/architecture/execute permission must be
  checked; generation and core validation must complete before procd marks the
  service ready; every failure must clear stale runtime markers and persist a
  bounded reason. `start` return code, `enabled`, and `running` remain
  independent facts.
- UI state contract: requested, starting, running, stopping, stopped,
  disabled, startup-failed and unknown are distinct. DNS privacy, adblock,
  RustDesk and OpenVPN cards expose configured/generated/applied/verified
  independently. A state file or HTTP 200 never proves a connection.
- Layout contract: status page remains scoped to `.openkill-status-page`, uses
  content-sized grid tracks, a four-card compatibility row (DNS, adblock,
  RustDesk, OpenVPN), and a config/metrics grid with shared boundaries at
  1920/1366/1200/768/390 CSS px and 100%/125% zoom.
- ABI/continuity: do not change legacy service-port writers, DNS listener
  split, mark/routing ABI, parser grammar, or recovery semantics. RustDesk
  compatibility must not synthesize global DIRECT/port/LAN bypasses.
- Current device lead: package `2026-1130` is installed, config/core paths
  exist, service is enabled but stopped. The fresh start reached generation
  and failed before core launch because the BusyBox `ash`-embedded Ruby in
  `yml_change.sh` lost three inner double quotes, leaving no valid
  `external-controller`; this was reproduced with `sh -x` and the generated
  YAML/runtime-context check. Commit `4996744` fixes those literals and adds
  truthful RustDesk generated/applied state; `b0cf756` normalizes RC source
  ownership to `root:root` before SDK packaging. Development CI passed for
  both commits. The final RC from `6e48598` was audited and installed after
  a protected backup; the device retained its user UCI configuration and
  PassWall state.

- Local evidence: WSL runtime 28/28 (two existing skips), optimization,
  UI-contract, UI-preview, UI-interaction and local-gate pass. Playwright is
  unavailable on this host, so no browser screenshot claim is made.
- Device evidence: RC run `35441525076` passed; IPK SHA-256 is
  `64f56d6fa60a6b163bc80541e608087a9a415aa0ac62d3827b67a353cd2c130a`.
  The package archive and installed key files are `root/root` with init and
  generator mode `755`, UI/CSS mode `644`. On `192.168.1.103`, generated YAML
  reached a valid controller, Mihomo/TUN/DNS/firewall readiness passed,
  `stop` cleared the running marker and RustDesk runtime marker, and a second
  `start` returned to ready with the controller listening on `:9090`.
  No packet-path, RustDesk client or proxy traffic evidence is implied by
  startup success. Playwright is unavailable locally, so UI evidence is from
  production-template contract/preview/interaction suites, not screenshots.

CURRENT_HEAD: `6e48598` (observed master HEAD before this evidence update)
VERSION: `2026-1130`
CURRENT_PHASE: `FORMAL_RELEASE_PUBLISHED_STAGE_B_WAITING_FOR_TRAFFIC_EVIDENCE`
CURRENT_STATUS: `2026-1130 is formally published from master after the release gate; the repaired candidate passed local/CI/RC/device fail-closed checks, while proxy-dependent DNS, region, adblock, RustDesk and OpenVPN traffic behavior remains unverified`
BLOCKER: `REAL_DEVICE_GATE` — 192.168.1.103 now has a usable Mihomo core/profile and startup evidence, but no test proxy traffic, running OpenVPN tunnel/client, or RustDesk client/service details; strict DNS, region routing, adblock traffic coverage, RustDesk recovery and OpenVPN handshake remain unverified
DEVICE_STATE: `192.168.1.103` is Kwrt 25.12-SNAPSHOT x86/64 on VMware with dnsmasq 2.93, firewall4 2025.03.17~b6e51575-r2 and OpenVPN 2.7.6; the e07a983 RC is installed with configuration/PassWall preserved, OpenKill is running and OpenVPN remains untouched
DEVICE_RETRY_READY: `RC_RUN_51_DEVICE_START_STOP_RESTART_PASS` (SSH BatchMode, protected backup, candidate hash and rollback path are recorded)
NEXT_ACTION: `obtain a test Mihomo core/profile plus OpenVPN and RustDesk client/service evidence, then run only the scoped Stage-B traffic checks; do not infer packet-path behavior from the fail-closed startup result`
RESULTING_HEAD: resolve with `git rev-parse HEAD` after this status-only update; this status records the pre-commit observation above
CENTRAL_ACTIVE: `NOT_APPROVED`
CENTRAL_NFT_APPLY: `NOT_APPROVED`
REAL_PACKET_PATH: `NOT_TESTED`
DEVICE_INSTALL_AUTHORIZATION: `APPROVED_FOR_192.168.1.103_ONLY`
DEVICE_INSTALL_SCOPE: `backup, upload/install matching RC IPK, bounded OpenKill config/service tests, limited DNS/outbound observations; preserve PassWall and do not change WAN/VMware`
DEVICE_ROLLBACK_CONTRACT: `restore backed-up UCI/files, remove candidate package, restore service enable/runtime state, verify SSH; never use broad bypass or firewall reset`
IMPLEMENTATION_CONTRACTS_UNDER_REVIEW: `DNS listener split and dnsmasq stable section identity; legacy writer continuity; route-set IPv4/IPv6 atomicity and empty-set fail-closed behavior; Mihomo DNS parser/strict bootstrap; adblock DNS/core same-generation and allow/block priority; RustDesk scoped domains; OpenVPN endpoint/protocol/client-scoped transport exception; status only after validate/apply`

## Device RC evidence and follow-up (2026-09-19)

- RC Run 47 (`35436168995`) built from master `f936a3e44dfb9d0f793c23c12850908d428a1606` and passed the SDK package audit. The artifact archive is `D:\openkill-rc-candidate-f936a3e\unpack\artifact.zip`, archive SHA-256 `6932bedc7af84188b259081b0b5468943fcc4d98763706164b7c3639e8b823c7`, and the IPK SHA-256 is `88985dd1cd8fc8dc4b76bc4f93e5edfce59364663d9a1b09af35cc5f2ba1c67b`. The package audit reports metadata, dependencies, conffile preservation, maintainer-script safety, stale-reference and sensitive-content checks as passing. SDK tar entries use the normal build uid/gid `1001:1001`; device installation resolves ownership as root, so the archive owner is not treated as runtime ownership.
- A fresh protected device backup was captured at `D:\openkill-device-backups\20260919-preinstall-f936a3e\device-backup.tar.gz` with SHA-256 `B19F44160C6F3179FD1BC624C2907BD71EF16030320E94CF388C399BAA91E50A`. The candidate upload matched the local IPK hash. Standard install skipped the equal version; the explicitly authorized `--force-reinstall` installed the matching candidate without ignore-dependency or overwrite flags. PassWall configuration hash remained unchanged, and OpenKill/OpenVPN stayed stopped.
- The bounded device start/stop test returned `start_rc=0` with `last_start_failed=1` and `failure_reason=config-missing`, `running_after_start=no`; stop returned zero. nft ruleset SHA-256 was identical before/after (`6df593927d022fb66d1872e31e5b1e4f2be4f3d496437e4a6b49fd78984b5dbe`), and the OpenVPN runtime state file was removed on stop. This validates fail-closed lifecycle behavior only; no packet path was exercised.
- The installed RC helper exposed a real disabled-state defect: several branches called the uppercase symbol `OPENKILL_OPENVPN_write_state` although the function is lowercase, so state writes were silently skipped. The source is repaired and the isolated contract test now checks that every prepare fixture writes a state file. The repaired source requires a new RC build and device reinstall before the previous device result can be used as final candidate evidence.
- RC Run 48 (`35436712808`) rebuilt the repaired `b75d76da21003e906d060ce4ee030109a4b9a5da` source. Its artifact archive is `D:\openkill-rc-candidate-b75d76d\unpack\artifact.zip`, archive SHA-256 `f8dec8f742061f2e74b8216ae0472086152aec5775391b3d0a4f40a8b4fe6918`, and IPK SHA-256 `d2811e7adbd37038862ce4179abb421a22b3a0093933cd04ef124ab12e70ca07`. The repaired candidate was installed with the same controlled reinstall path; the helper hash matches, PassWall is unchanged, disabled OpenVPN preparation writes state, and the bounded start/stop check again returned `config-missing` with unchanged nft state.

## Formal release evidence (2026-09-19)

- The reviewed version commit is `ea474aeea866428d81dbde0b60d6ff0914a75009`; its exact Development CI is Run 136 (`35437049127`) and completed successfully: https://github.com/dinggood615/openkill/actions/runs/35437049127.
- Formal Release Run 153 (`35437145461`) completed successfully with `release_gate=true`, `publish=true`, and APK disabled: https://github.com/dinggood615/openkill/actions/runs/35437145461. Tag `v2026-1130-ipk` points to the version commit and the published release is https://github.com/dinggood615/openkill/releases/tag/v2026-1130-ipk.
- Published asset `luci-app-openkill_2026-1130_all.ipk` is 9,182,177 bytes with SHA-256 `c81acf2d644fa079f593e8f81f3ee0700743378d6cdf9c05efdff0676b895ea2`; package channel `master/latest-ipk.json` records version `2026-1130`, format `ipk`, architecture `all`, the same source commit and digest. The prior release remains available for rollback.
- Documentation follow-up `d0ad12b95e28adee178db8a57363141f2acec970` passed exact Development CI Run 137 (`35437486310`): https://github.com/dinggood615/openkill/actions/runs/35437486310.

## OpenVPN and UI continuation contract (2026-09-19)

- Observed source baseline before this iteration is `5725b49c7805d067fee89eb8a4e2a1becca0564f` on `master`; the worktree was clean. This section is the pre-change contract, not evidence that device behavior is verified.
- OpenVPN compatibility is opt-in and defaults off. Transport bypass is independent from tunnel-internal traffic and DNS handling.
- A transport exception is valid only when enabled and supplied with a valid endpoint set (explicit IPv4/IPv6 addresses and/or configured names), an explicit TCP/UDP protocol, and valid ports. Empty, malformed, mixed-family, or failed updates fail closed and retain the last valid runtime set.
- Router-client mode matches configured destination endpoints and ports. LAN-client mode additionally requires configured source client addresses. Server mode does not synthesize a network-wide bypass. No rule is keyed only by a global source/target port, the whole VPN subnet, all LAN devices, or all `443`/`1194` traffic.
- IPv4 and IPv6 endpoint/client sets are generated separately with staged files and runtime-safe replacement. IPv6 remains enabled; RA/ND/DHCPv6/PMTU are outside this exception. User force-proxy policy remains higher priority than this compatibility exception.
- `remote_service_bypass` and `openkill_service_ports` remain a legacy ABI. OpenVPN uses dedicated objects and cleanup only removes objects created by OpenKill. Real-IP, adblock allow-listing, DNS policy, and tunnel policy stay independent.
- Dashboard cards and compatibility settings must distinguish requested, generated, applied, tunnel-established, business-verified, and unknown states. A status file or HTTP 200 alone never proves network success. Styles remain page-scoped and content-sized.

### Planned order

1. Perform read-only OpenVPN inventory on the authorized device and recheck current source/UI state.
2. Implement the bounded endpoint generator/writer and status contract; add isolated validation, family split, atomic failure retention, priority, and cleanup tests.
3. Add compatibility settings and independent DNS/adblock/OpenVPN dashboard summaries; exercise generated DOM/state fixtures.
4. Run local-gate, diff/diff-check, commit and push the exact `master` commit, then verify Development CI.
5. Only after local and CI gates pass, build/audit an RC package and perform the previously authorized bounded device phase. Formal release still requires actual package/device evidence and the repository workflow.

### Iteration evidence (pre-commit)

- Read-only device check on `192.168.1.103` completed over the authorized SSH alias. Current facts: OpenVPN 2.7.6 (`openvpn-openssl 2.7.6-r1`) is installed; UCI contains one server and two client sections with sensitive values redacted; no OpenVPN process or `tun` interface is running; IPv4 has a WAN default route and IPv6 currently exposes ULA/link-local routes but public IPv6 was not tested. No device configuration was changed.
- The first local implementation adds `openkill_openvpn.sh`, dedicated nft/ipset endpoint/client/port objects, bounded resolver input, staged family-separated files, one checked runtime transaction, scoped rules, cleanup, UCI defaults/normalization, compatibility-page fields, dashboard summaries, and the OpenVPN adblock-domain exception. It does not enable the feature by default and does not change the legacy service-port writer.
- Isolated OpenVPN contract test passes (`14 checks`), UI contract passes (`23/23`), UI preview passes (`2/2`), and changed shell files pass `sh -n`. `scripts/local-gate.sh` passes at the observed baseline; the unified fast runner correctly refuses to report a result while the working tree is dirty and will be rerun after the bounded commit.
- Known device gate remains: there is no running OpenVPN tunnel, test client, Mihomo core/profile or usable proxy on the authorized device, so endpoint handshake, tunnel business, DNS-outbound, RustDesk and transparent packet-path behavior remain unverified.
- Official behavior references used for the contract: OpenVPN 2.7 documents `remote host [port] [proto]` and the `udp`/`tcp-client`/`tcp-server` families (including `4`/`6` suffixes); OpenWrt documents fw4 as the nftables backend from 22.03 onward and warns that manual nft rules must coexist with fw4; Mihomo documents that DNS connections follow routing rules and require an explicit `proxy-server-nameserver`. See [OpenVPN 2.7 manual](https://openvpn.net/community-docs/community-articles/openvpn-2-7-manual.html), [OpenWrt firewall overview](https://openwrt.org/docs/guide-user/firewall/overview), and [Mihomo DNS configuration](https://wiki.metacubex.one/en/config/dns/).
- The first CI run for `07d07a9` failed because the new OpenVPN setup was inside the legacy service-port writer extraction boundary. The bounded repair moved the OpenVPN setup before that writer without changing its ABI. Local shell/preflight gates and the OpenVPN/UI/DNS tests pass; exact Development CI for `b1699deee587f2f313a564ee915ef52372f9b7e3` passed in run `35432710735` (static plus both compatibility jobs): https://github.com/dinggood615/openkill/actions/runs/35432710735.
- A second local review found that a failed endpoint update could leave the old files present but omit their rules on the next firewall rebuild, and legacy `ipset restore` could flush live sets before a later bad element. The repair stages `.next` files and promotes them only after the runtime transaction succeeds; invalid or unresolved updates retain a matching role/protocol generation, and legacy backends load temporary family-correct sets before `ipset swap`. The transport protocol now accepts `tcp`/`udp` plus `tcp4`/`tcp6`/`udp4`/`udp6`, and nft/legacy rules match the selected family and protocol.
- The resulting master commit `411321b66c3ed3bb3f724b44cf2f117930f6a1db` passed the OpenVPN contract, UI contract/preview/interaction, DNS intent, optimization, shell/preflight and Linux runtime/installer fixtures (runtime 28 tests, installer 11 tests; Ruby-only cases skipped by the local host). Development CI run `35435940545` completed successfully for that exact commit: https://github.com/dinggood615/openkill/actions/runs/35435940545.

## UI recheck and status convergence (2026-09-19)

- Observed master before this iteration is `913bd2121a5642806b1d0a0648397b3a3196a920`; the working tree was clean. The device was rechecked read-only: package `luci-app-openkill 2026-1129` is installed, no Mihomo/Clash binary was found on `PATH`, and the OpenKill service state must still be interpreted from explicit return codes rather than historical notes. No device mutation is part of this UI-first change.
- The local production-template preview reproduced two UI defects. `.main-card` inherited fixed grid tracks (`--row-1-height` through `--row-4-height`), while the core status content was taller than its first track; the preview reported a 6px content overflow. The IP checker had a 35s router timeout and failure paths that called `show_querying_state()`, so a failed request could remain displayed as `Querying...` indefinitely.
- This iteration changes only the status-page presentation/state contract and the IP-check error contract. It preserves LuCI endpoint names, DNS listener split, legacy writers, category priority, Mark ABI, parser grammar, and continuity/recovery semantics. The status UI now distinguishes loading, running, stopped, disabled, startup-failed, unknown and error; IP probes converge to success, timeout or unavailable and retain the probe source/mode in the accessible label.
- The fresh device read-only check confirmed `luci-app-openkill 2026-1129` is installed, `/etc/init.d/openkill enabled` returns `0`, `/etc/init.d/openkill running` returns `1`, no Mihomo/Clash binary is on `PATH`, and no config path is currently selected. The same check showed ordinary `uci show` returns `@dnsmasq[0]` while `uci -X show` returns a stable `cfg...` section; init, adblock and watchdog now use the extended form and share one resolved ID.
- The optimization recheck fixed stable dnsmasq identity and parent/subdomain adblock precedence. Strict-DNS proxy binding, scoped RustDesk domains, IPv4/IPv6 atomic route updates, lifecycle timing and package ownership remain separately contracted; no CENTRAL_ACTIVE, central nft state or packet-path test was enabled.
- Local evidence after the changes: UI contract 23/23, preview 2/2, interaction 1/1, DNS intent 10/10, lifecycle 18/18, optimization and autonomous workflow checks passed; changed shell files pass `sh -n`; `scripts/local-gate.sh` passed at observed baseline `913bd2121a5642806b1d0a0648397b3a3196a920`. The generated preview was checked at the available 1280 CSS px viewport and reports content-sized cards with no card overflow.
- Resulting master commit `407423734c0d4d9f9b455b11bb55c1f62b580354` passed Development CI run `35429343098`: [OpenKill Development CI](https://github.com/dinggood615/openkill/actions/runs/35429343098). The follow-up RustDesk precedence fix is `f93bc254edc439c179365fa4f802bdaf2f4186e5`; its Development CI run `35429537012` also completed successfully: [OpenKill Development CI](https://github.com/dinggood615/openkill/actions/runs/35429537012). Neither commit mutates the device or contains a candidate package.
- The RustDesk fix inserts scoped user-configured DIRECT exceptions immediately before the final MATCH/FINAL rule, preserving user-specific proxy rules and keeping dynamic peer traffic under normal policy. No broad port or LAN bypass was added.
- Documentation-only follow-up commit `b094b37` is now verified by Development CI run `35429616399` with success status: [OpenKill Development CI](https://github.com/dinggood615/openkill/actions/runs/35429616399). No local code or device mutation is pending in this UI-first batch; RC build and device installation remain separately authorized stages.

## RC audit runner compatibility (2026-09-18)

- Observed master baseline before this status update is
  `f70dee5e479d6a1f92270f6eed6934e2e1ae5001`. Development CI run
  `35312752594` passed for that exact commit after the direct package Makefile
  boundary was added; the package build itself no longer expands the full
  kernel/module graph.
- RC run `35312882508` completed the direct build and produced exactly one
  `luci-app-openkill_2026-1129_all.ipk` under the SDK package feed, but its
  audit step exited 127 because the GitHub runner image does not provide
  `rg`. RC retry `35313619098` reached the same package audit after the
  runner-compatible change, then correctly rejected the package's
  `/tmp/etc/openkill` cleanup as a false positive caused by an overly broad
  substring match. Logs are retained at `D:\\openkill-rc-build6.log` and
  `D:\\openkill-rc-build7.log`.
- The bounded fixes replace only undeclared `rg` calls in the RC input,
  package and sensitive-content audits with recursive POSIX/GNU `grep` using
  equivalent file filters, and make the maintainer-script check require a
  path boundary so `/tmp/etc/openkill` remains a permitted runtime cleanup.
  They do not weaken metadata, conffile, stale reference, maintainer-script,
   CSS cache-buster or sensitive-content checks. RC retry `35314125692` then
   exposed a stale audit assumption: packaged LuCI templates use the runtime
   `<%=plugin_version%>` cache key rather than a literal version. The pending
   adjustment accepts that runtime key or the current literal version and
   requires both CSS assets. The autonomous workflow test asserts that this RC
   workflow has no `rg` dependency.
- Local evidence before the final RC: workflow contract `10/10`,
  optimization/DNS/UCI focused suites pass, `git diff --check` passes and the
  WSL `scripts/local-gate.sh` passes. The resulting commit and its exact
  Development CI run must be recorded after Git resolves the new HEAD.
- Final candidate evidence: Development CI `35314707749` passed for exact
  source commit `9f18c7bd2e7ac3c5a13ebde27f318f9b71ba0e44`; RC run
  `35314832624` passed all steps and uploaded artifact `10535040172`. The
  candidate is `luci-app-openkill_2026-1129_all.ipk`, 7,646,752 bytes, with
  SHA-256 `7cd0010c b688a449 b9f6134c dba20c72 d84b8f75 074923e1 390dadfd
  34961e99` (spaces are formatting only). The audit report confirms package
  metadata, conffile preservation, maintainer-script path safety, stale
   development-reference and sensitive-content checks. The package was
   subsequently installed on the authorized device in Stage A after a fresh
   SSH/resource/backup recheck.

## Authorized device Stage A (2026-09-18)

- The protected pre-install archive remains at
  `D:\\openkill-device-backups\\20260918-preinstall-1619f31\\device-backup.tar.gz`
  with SHA-256
  `0E49D13E3ED57D944EA09E7D4EB17778AEB710DE73D034480071A181CE0A227C`.
  SSH BatchMode access through `openkill-103` was rechecked before mutation.
- Pre-install readiness was reconfirmed: Kwrt `25.12-SNAPSHOT` x86_64,
  overlay about 789 MB free, available memory about 700 MB, PassWall global
  switch `0`, no OpenKill/Mihomo/Clash process or rule, and the stock dnsmasq
  listener on the LAN/WAN/IPv6 addresses. The candidate uploaded to `/tmp`
  matched the RC SHA-256 before installation.
- Standard `opkg install` completed for the candidate and its declared missing
  Ruby dependencies (`ruby`, `ruby-yaml`, `ruby-digest` and related packages)
  without force flags. The installed package reports version `2026-1129` and
  the candidate conffile hash. The install used about 25 MB of overlay space;
  the previous `passwall`, `dhcp`, `firewall` and `network` UCI file hashes are
  unchanged from the protected backup, and PassWall remains at `enabled=0`.
- Device shell syntax validation passed for `/etc/init.d/openkill` and all
  installed `/usr/share/openkill/*.sh` files. The capability probe reports
  `core=0` and all Mihomo protocol capabilities `unknown`; the bundled
  `oc-cn-domain.mrs` is present at 556,732 bytes. These are packaging and
  parser-readiness checks only.
- A bounded start/stop test showed the service does not claim to be running:
  the asynchronous start returned before the service reported `running`, the
  log recorded `Config Not Found` because no Mihomo profile/core exists, and
  the normal stop removed its transient service state. After cleanup there is
  no OpenKill/Mihomo/TProxy nft or `ip rule` state, dnsmasq still owns the
  stock port 53 listeners, and the OpenKill init service is not enabled at
  boot. This is a verified fail-closed startup result, not a connectivity
  recovery claim.
- Device configuration still has the package defaults (`adblock_mode=off`,
  `rustdesk_compatibility=0`, `ipv6_dns=1`). Adblock query behavior, DNS
  privacy egress, IPv4/IPv6 region decisions, and RustDesk signaling/P2P/
  relay behavior are **not verified** because no core/profile, test proxy or
  client evidence is present. Rollback remains: stop/disable OpenKill, remove
  only the candidate package, restore the protected UCI/files if needed,
  verify SSH and dnsmasq, and leave PassWall unchanged.

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

## NaiveProxy installer current device recheck (2026-09-23)

- User authorized reconnecting to `192.168.1.103` to diagnose and repair the
  optional component installer. This bounded device phase permits diagnostic
  downloads and the component's own installation only; it does not permit
  changing OpenKill traffic policy, CENTRAL_ACTIVE, firewall ownership, WAN,
  or other nodes/subscriptions.
- Current recheck from SSH: package is `luci-app-openkill 2026-1142` and the
  OpenKill service is running. Three earlier tasks failed at `probing` with
  `loader-or-version-probe-failed` and a kernel `Trace/breakpoint trap` while
  executing `naive.new --version`. The configured official OpenWrt x86_64
  asset was fetched in a private temporary directory; its SHA256 matched, and
  the binary's version and help probes succeeded. The exact installed helper
  then succeeded in both isolated synchronous and worker modes. A fresh run
  through the helper's locked asynchronous install task also succeeded; the
  configured `/etc/openkill/core/naive` is now root-owned, executable, and
  reports `150.0.7871.63`. Refreshed state reports `component_installed=1`,
  `state=disabled`, `reason=no-enabled-nodes`, `local_ready=0`, and
  `remote_verified=0`. The old probe trap was not reproducible; no source
  installer defect was confirmed. No Naive node was enabled and no remote
  authentication or packet-path test ran.
- Navigation root cause: the compatibility template linked to `servers` with
  `add=naiveproxy` but omitted the required selected YAML `file` parameter.
  The `servers` model therefore followed its designed no-file redirect to
  Config Manage, exactly matching the screenshot. The node editor, share-link
  parser, and NaiveProxy CBI type already exist.
- Implementation: the compatibility view now uses the selected, existing
  YAML path from the OpenKill UCI accessor, validates that it is under the
  configuration directory and a YAML file, URL-encodes it, and opens the
  server/group manager with the Naive add hint. With no valid selection it
  links to Config Manage and says a configuration must be selected. Creating
  a proxy from that explicit flow carries the NaiveProxy type hint into the
  editor; existing node types remain authoritative. Related edit links retain
  encoded file paths. Network policies, node credentials, DNS, firewall,
  legacy writers, ABI, and start/restore behavior are unchanged.
- Device backup: `/etc/config/openkill` is preserved outside the repository at
  `D:\openkill-device-backup-20260923-current\openkill.config`; local SHA256
  `0bf7be81c9f5d8b959722978e8ee40c66392a2a5ee3165b2f14ed229a0dca52c`,
  matching the device before component installation. The repeat component
  install did not modify UCI or restart OpenKill; service remains running.
- Local checks: NaiveProxy integration contract, UI contract (25), UI preview
  (2), POSIX shell syntax, `git diff --check`, and `scripts/local-gate.sh`
  pass. Browser automation is unavailable in this session, so no rendered
  screenshot is claimed.
- Source implementation commit `a1e39bf7b7c79f9ec2fe47a6847455e78e82cceb`
  is on master. Its exact Development CI passed
  ([35879368818](https://github.com/dinggood615/openkill/actions/runs/35879368818)).
- RC Build from that commit passed
  ([35879571748](https://github.com/dinggood615/openkill/actions/runs/35879571748)).
  The candidate package is
  `luci-app-openkill_2026-1142_all.ipk`, SHA256
  `4e979f1e3e2c7c5eafdb57713f0b2b3356c1fa9e901d0fb56620187efd5214a5`.
  The archived view and both node-management models match source hashes;
  package ownership is root:root and the workflow audit passed metadata,
  conffile, maintainer-script, stale-reference, and sensitive-content checks.
- Device candidate upload hash matched. `opkg install` correctly treated the
  same-version package as already current; the authorized retry with the
  device-supported `--force-reinstall` installed the candidate. The installed
  compatibility view hash matches the RC/source, and marker checks found the
  path and Naive type hint. Current selected config is
  `openkill.optimized.yaml`. Device `/etc/config/openkill` remains at the
  pre-install SHA256; OpenKill is running and enabled; Naive reports
  `150.0.7871.63`; component state is installed, with no enabled node and no
  local/remote verification. The package manager kept the modified conffile
  and placed its packaged default alongside it as `/etc/config/openkill-opkg`.
  The protected backup remains at
  `D:\openkill-device-backup-20260923-current\openkill.config`.
- No browser surface was available in this session, so a rendered click-through
  was not captured. The deployed view and route inputs were verified over SSH;
  remote Naive authentication and business traffic remain untested.
- Version metadata and release notes for 2026-1143 are now prepared; the
  release bump check, NaiveProxy integration contract, UI contract (25), UI
  preview (2), `git diff --check`, and local gate pass. Next action: commit and
  push this versioned source state, verify exact Development CI, build/audit
  its RC, then invoke Formal Release with both required inputs. Preserve
  v2026-1142 and its package for rollback.

## NaiveProxy node-entry fix: final release and device verification (2026-09-23)

- Final source state: `a6df1575ba3608c8c5503574e6f776abda19fc59` on `master` (implementation is in `a1e39bf7b7c79f9ec2fe47a6847455e78e82cceb`; 2026-1143 release metadata is in the final source commit). The selected-config-aware link now reaches the proxy/group manager and preselects the NaiveProxy node type for a newly added proxy. Missing/invalid selected YAML is handled with an explicit configuration-manager path; existing node types and UCI values are retained.
- Formal Release workflow with `release_gate=true` and `publish=true` completed successfully: [run 35881678974](https://github.com/dinggood615/openkill/actions/runs/35881678974). Release: [v2026-1143-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1143-ipk). Asset `luci-app-openkill_2026-1143_all.ipk`, SHA-256 `d0c6aa5e567f4becf77237ee2fd3261551630b3218c21ce6c0266743e0f229d6`. Previous v2026-1142 release remains available.
- Versioned source commit Development CI passed: [run 35880869413](https://github.com/dinggood615/openkill/actions/runs/35880869413). Versioned RC Build passed: [run 35881071698](https://github.com/dinggood615/openkill/actions/runs/35881071698); RC package SHA-256 `24cb6b3774270db91b0478880669c0caf213ca1c6ed8b708745c7b5bfae4ae03`. Formal artifact audit confirmed package version 2026-1143, architecture `all`, expected dependencies and conffile, changed Lua files matching source, and root ownership/modes.
- Formal package was uploaded to the authorized test router; upload SHA matched the release asset. `opkg` upgraded 2026-1142 to 2026-1143. Fresh SSH recheck confirms package version 2026-1143, `/etc/init.d/openkill status` is `running`, ubus reports the core instance running, and the Naive binary remains executable as root and reports `150.0.7871.63`. Installed compatibility view SHA-256 is `17ba7e33cc45272af393c5887d18d149853a75bcd05e51a827fac41af292519c`, matching the candidate/source view. Existing `/etc/config/openkill` hash remains `0bf7be81c9f5d8b959722978e8ee40c66392a2a5ee3165b2f14ed229a0dca52c`; package-manager default copy `/etc/config/openkill-opkg` is separately backed up at `D:\openkill-device-backup-20260923-current\openkill-opkg`, SHA-256 `7b0f83a2aef735f20137902bb2e7d8cfdbb21b3adeff6b78713acaae5a9ea1d1`. The primary protected backup remains `D:\openkill-device-backup-20260923-current\openkill.config`.
- Installed component and node state are distinct: the component is installed, but there is no enabled Naive node. Therefore no local SOCKS5 listener or remote authentication was tested, and no remote connection is claimed. No browser surface was available for a rendered LuCI click-through; device files, route inputs and live service state were verified over SSH.
- Local evidence remains: NaiveProxy integration behavior contract, UI contract (25), UI preview (2), POSIX shell syntax, `sh scripts/local-gate.sh`, and `git diff --check` all passed before versioned commit. The root cause was the omitted selected-YAML `file` query parameter; no DNS, routing, firewall, subscription, node credential, or startup/restore policy was changed.
- Rollback: reinstall the retained `luci-app-openkill_2026-1142_all.ipk` package from the existing v2026-1142 release and restore the protected `/etc/config/openkill` backup only if the user’s config was changed. The upgrade preserved the current config hash, so config restoration is not needed for this release. Naive component binary was retained across OpenKill package upgrade.
- Documentation-only evidence commit follows the release; it does not advance the version or rebuild/publish another release. Verify its Development CI separately. Next action: wait for any later user-requested scope; no unresolved local code blocker remains for the Naive node-entry route.

## UI compactness and copy pass (2026-09-24)

- Scope: unify OpenKill page spacing, card surfaces, controls, status labels and responsive grids; shorten repeated visible notes and status summaries. DNS, IPv6, TUN, routing, filtering, proxy protocol, UCI field names, legacy writers, ABI and startup/restore contracts are unchanged.
- Cache contract: local generated output stays under `D:\openkill-cache`; repository cache paths remain junctions and no cache, credentials, device logs or private configuration may enter Git.
- Presentation contract: important privacy, interruption, validation and unsupported-protocol limits remain visible. Technical diagnostics stay in expandable/detail paths. “Saved”, “applied”, “loaded” and “verified” remain distinct states.
- Verification contract: run the existing UI contract/preview checks, local gate and diff checks. Browser rendering evidence is recorded only when the browser runtime is available; unavailable device/browser checks remain explicitly unverified.
- Implementation: `flat.css` now applies the compact spacing/radius/description rhythm to status and settings cards; NaiveProxy metadata/status copy and the dashboard ad summary were shortened without changing DOM hooks, UCI fields or state decisions.
- Local evidence: UI contract 25/25, UI preview 2/2, POSIX/local policy gate and `git diff --check` passed at the 2026-1144 working state. The first WSL gate invocation was environment-blocked by Git safe-directory policy; registering `/mnt/d/openkill` for the WSL test user and rerunning passed. No browser surface is available for rendered screenshots in this session.
- Release gate: version metadata is prepared for 2026-1144. Next action is exact Development CI, RC audit, then Formal Release only after those gates pass; preserve v2026-1143 for rollback.
- Versioned source commit `5bf4434eff786fee804f36782e2fc0b3df39f57b` passed exact Development CI ([run 35982382778](https://github.com/dinggood615/openkill/actions/runs/35982382778)). RC Build passed ([run 35982500360](https://github.com/dinggood615/openkill/actions/runs/35982500360)); the audited candidate `luci-app-openkill_2026-1144_all.ipk` has SHA-256 `0b2b3b895bab33c6ce37dea9efaf5c6a7d0e764254c9ec22314769f1a57b88db`. The audit reported package metadata, conffile preservation, maintainer-script deletion, stale-reference and sensitive-content checks as OK. The package was unpacked from the RC artifact and confirmed to contain the compact CSS marker, shortened NaiveProxy copy and corrected ad status wording.
- Formal Release with `release_gate=true` and `publish=true` passed ([run 35983177776](https://github.com/dinggood615/openkill/actions/runs/35983177776)). Published release: [v2026-1144-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1144-ipk), source `5bf4434eff786fee804f36782e2fc0b3df39f57b`, asset `luci-app-openkill_2026-1144_all.ipk`, downloaded SHA-256 `29f29332f785a315c34586eeb72afc38aec8fb13a572775ab890b13d2dc1e9e` (9,225,962 bytes). v2026-1143 remains available for rollback.
- Browser rendering was not claimed because this host has no available browser runtime. No device installation was requested in this UI-only pass; device state and remote business behavior remain unverified. No DNS, routing, filtering, protocol or startup policy was changed.

## Runtime status dashboard alignment and copy pass (2026-09-25)

- Scope: adjust only the runtime status page presentation: five-card copy,
  dashboard DOM grouping, responsive grid sizing and state-summary display.
  DNS, IPv6, TUN, routing, filtering, protocol behavior, UCI fields, status
  endpoint semantics and startup/restore contracts remain unchanged.
- Layout contract: the visual top row is one responsive grid with Running
  Status at roughly 1/2 width and Control Panel/Mix Proxy at roughly 1/4
  each. The lower primary and secondary columns stretch from one shared grid
  row; no filler card, fixed-height spacer, negative margin or whole-page
  scaling is allowed.
- Copy contract: each DNS, adblock, OpenVPN, RustDesk and NaiveProxy card
  keeps one evidence-based primary state plus one short necessary detail.
  Generated, loaded, applied and verified remain distinct; unknown and
  unverified states cannot be presented as healthy.
- Verification contract: exercise the existing preview states (running,
  disabled, startup_failed and error), UI contract/preview tests, local-gate
  and diff checks. Browser rendering is recorded only if a browser runtime is
  available; device and packet-path validation are outside this UI-only scope.
- Next action: implement the scoped status template/CSS changes, run local
  gates, then prepare the next version only after the exact-commit CI and RC
  audit pass.

## Runtime status dashboard alignment release evidence (2026-09-25)

- Implementation commit `8f52fe5c5c0f54b41ed8421ed240773fc9eb29e5` shortens
  the five live summaries while preserving full evidence in accessible detail
  labels, changes the top grid to `2fr 1fr 1fr`, and lets the primary config
  card and secondary metric matrix stretch across one shared lower grid row.
  No network policy, state endpoint semantics, UCI field or startup/restore
  behavior changed.
- Local evidence: UI contract 25/25, UI preview 2/2, POSIX/local policy gate,
  version bump check and `git diff --check` passed. Browser automation is not
  available in this environment, so rendered viewport measurements and
  screenshots remain unverified; device validation was not requested.
- Versioned source commit `fef4244ea88fcf4a0ead6adf90d3f144ca6f0623`
  (`2026-1145`) passed exact Development CI
  ([run 36105228266](https://github.com/dinggood615/openkill/actions/runs/36105228266)).
- RC Build from the same source passed
  ([run 36105449460](https://github.com/dinggood615/openkill/actions/runs/36105449460)).
  Candidate `luci-app-openkill_2026-1145_all.ipk` SHA-256 is
  `79f8c8a128e92a03d144d097292790f29bcd123b097f738f02baf03313ad260e`.
  The workflow audit passed package metadata, conffile preservation,
  maintainer-script deletion, stale-reference and sensitive-content checks;
  the extracted candidate contains the new status template and CSS markers.
- Formal Release with `release_gate=true` and `publish=true` passed
  ([run 36105951841](https://github.com/dinggood615/openkill/actions/runs/36105951841)).
  Published release:
  [v2026-1145-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1145-ipk),
  source `fef4244ea88fcf4a0ead6adf90d3f144ca6f0623`, asset
  `luci-app-openkill_2026-1145_all.ipk`, SHA-256
  `47c5e5e4ac308e6e493e7df86f27f5b8a3db404f774092ff23e47426037c5a68`.
  The formal asset was downloaded into `D:\openkill-cache\formal-2026-1145`
  and its extracted status template/CSS matches the versioned source.
- Previous `v2026-1144-ipk` remains available for rollback. No router,
  central nft state, packet-path test or private configuration was touched.

## NaiveProxy install and bridge handoff (2026-09-25)

- Scope: extend the existing NaiveProxy metadata/install action with a compact
  share-link entry path and a read-only, credential-free YAML preview for the
  generated loopback SOCKS5 bridge. The existing UCI fields, helper process,
  node identity, port allocation, Mihomo writer and failure recovery contract
  remain the source of truth.
- Installation contract: the one-click action must keep the official asset
  URL and expected SHA-256 bound together, use the existing staged background
  task, preserve the previous component on failure, and never start a helper
  when no NaiveProxy node is enabled.
- Node contract: the compact importer delegates parsing to the existing
  structured NaiveProxy URL parser, keeps credentials in protected UCI only,
  and preserves stable server section IDs and policy-group behavior.
- Bridge contract: the preview exposes only name, 127.0.0.1, allocated port,
  and `udp: false`; it must match the actual Mihomo SOCKS5 stanza generated by
  `yml_proxys_set.sh` and must not expose credentials or claim remote success.
- Verification contract: run the NaiveProxy integration, UI contract,
  preview, local-gate and diff checks. Browser, device and remote endpoint
  validation remain explicitly unverified in this local-only change.

## NaiveProxy bridge release evidence (2026-09-25)

- Implementation commit `eca8ff25d753e6bc7743981f8bcaf9b58d328ddf` passed exact
  Development CI ([run 36111656314](https://github.com/dinggood615/openkill/actions/runs/36111656314)).
  It adds the bridge status endpoint, compact share-link importer and a
  credential-free SOCKS5 YAML preview while preserving existing install and
  helper lifecycle contracts.
- Version commit `e1762b9e99451e1ac826e520de9fef2dc21b76e1` (`2026-1146`)
  passed exact Development CI ([run 36111847076](https://github.com/dinggood615/openkill/actions/runs/36111847076)).
- RC Build passed ([run 36111987140](https://github.com/dinggood615/openkill/actions/runs/36111987140)).
  Candidate `luci-app-openkill_2026-1146_all.ipk` SHA-256 is
  `f0b9fd4d33d3cb226a3c84dabab7801d0bd7a3616ea85df11d565b35a3e7f0c6`;
  it is archived under `D:\openkill-cache\rc-2026-1146`. The workflow audit
  passed package metadata, conffile preservation, maintainer-script deletion,
  stale-reference and sensitive-content checks. Extracted files contain the
  bridge endpoint, quick importer and `udp: false` SOCKS5 stanza.
- Formal Release with `release_gate=true` and `publish=true` passed
  ([run 36112629048](https://github.com/dinggood615/openkill/actions/runs/36112629048)).
  Published release: [v2026-1146-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1146-ipk),
  source `e1762b9e99451e1ac826e520de9fef2dc21b76e1`, asset
  `luci-app-openkill_2026-1146_all.ipk`, SHA-256
  `fc5ab070c3b27ac6fac23653b81f405bad2e3484ae93e21194a12556a582ab1f`.
  The formal asset is archived under `D:\openkill-cache\formal-2026-1146` and
  contains the same bridge, importer and UI markers. `v2026-1145-ipk` remains
  available for rollback.
- No device, browser-rendered viewport, remote Naive endpoint or packet-path
  validation was performed in this local-only change. Local integration,
  UI-contract, preview, POSIX/local-gate and package audits passed; credentials
  and private configuration were not touched.

## One-click NaiveProxy installer release evidence (2026-09-25)

- Implementation commit `1967eb87530f5884be3faa2c3cd0ad56e0a0bfd6` adds the
  non-fatal installer phase and installer contract coverage. Its first
  Development CI attempt ([run 36115591993](https://github.com/dinggood615/openkill/actions/runs/36115591993))
  correctly rejected an intermediate commit whose version fields were split
  across commits; no package was published from that state.
- Versioned source commit `30f847b8a08733fda952efb78e5b599c1ef41b5f`
  (`2026-1147`) contains the synchronized Makefile, installer, README, UI
  preview and release notes. Exact Development CI passed ([run 36115735658](https://github.com/dinggood615/openkill/actions/runs/36115735658)).
- Local evidence passed after the repair: installer tests 12/12 (one host
  dependency skip), NaiveProxy integration contract, POSIX syntax checks,
  local-gate and `git diff --check`. The integration test now decodes WSL
  diagnostics with replacement handling so locale noise cannot mask syntax
  results.
- RC Build passed ([run 36115884484](https://github.com/dinggood615/openkill/actions/runs/36115884484)).
  Candidate `luci-app-openkill_2026-1147_all.ipk` SHA-256 is
  `02452a7532b9e4f8540f2903b3e025b6d55c9e2756bcd7606fb25d8087f9026f`;
  it is archived under `D:\openkill-cache\rc-2026-1147`. The audit passed
  package metadata, conffile preservation, maintainer-script deletion,
  stale-reference and sensitive-content checks.
- Formal Release with `release_gate=true` and `publish=true` passed
  ([run 36116332106](https://github.com/dinggood615/openkill/actions/runs/36116332106)).
  Published release: [v2026-1147-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1147-ipk),
  source `30f847b8a08733fda952efb78e5b599c1ef41b5f`, asset
  `luci-app-openkill_2026-1147_all.ipk`, SHA-256
  `d9877d85489e74cd8cfa42d2ac4aed4e91c34f55b9f82ee452cfe6a6514469ea`.
  The formal asset is archived under `D:\openkill-cache\formal-2026-1147`;
  its extracted files include the NaiveProxy metadata helper, component path,
  bridge endpoint and SOCKS5 writer. `v2026-1146-ipk` remains available for
  rollback.
- No router, device, browser-rendered viewport, remote Naive endpoint or
  packet-path validation was performed. The one-click installer still treats
  metadata/download/component failures as non-fatal to OpenKill and does not
  start a helper without an enabled NaiveProxy node.

## One-click NaiveProxy installer handoff (2026-09-25)

- Scope: extend the existing OpenKill installer with an optional, non-fatal
  NaiveProxy component phase. The phase consumes the official metadata
  resolver's bound URL and SHA256 pair, installs only after ELF and version
  checks, and records the pair only when the corresponding UCI fields are
  empty. It never starts a helper or changes transparent proxy ownership.
- Path contract: installer, status probe, service lifecycle and Mihomo writer
  must use the configured `/etc/openkill/core/*` component path. A manually
  installed fallback is diagnostic evidence until it passes the same executable
  and version checks and is explicitly adopted.
- Failure contract: metadata, downloader, digest, archive, architecture and
  loader failures keep OpenKill usable and preserve a previous component;
  installer output identifies the NaiveProxy phase without exposing credentials.
- Bridge contract: enabled nodes still produce protected helper JSON, a stable
  loopback SOCKS5 port, and a matching Mihomo `type: socks5` stanza with
  `udp: false`; automatic YAML injection and user-managed snippets must not
  create duplicate names or imply remote verification.
- Verification contract: add installer contract coverage for metadata success,
  missing metadata, existing component reuse and non-fatal failure; rerun the
  NaiveProxy, UI, POSIX and local-gate suites. Device and remote endpoint tests
  remain outside this local phase.

## 2026-1151 release evidence (2026-09-25)

- Source fix commit: `1e2fcfd179beec3bc21f84f649d8cd5d8d043958`.
- Development CI for the exact commit passed: [run 36139159582](https://github.com/dinggood615/openkill/actions/runs/36139159582).
- RC Build passed from the exact commit: [run 36139343804](https://github.com/dinggood615/openkill/actions/runs/36139343804). The SDK audit summary reported `luci-app-openkill_2026-1151_all.ipk`, SHA256 `9b2280983fb956dfdf5cbc88f18524a8a4280b77bb7f45554746912d388335fb`.
- Formal Release passed with `release_gate` and `publish`: [run 36139865576](https://github.com/dinggood615/openkill/actions/runs/36139865576). Published [v2026-1151-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1151-ipk); formal IPK SHA256 `f63c8ae3f1a57010fc78786b2e1f091b0806e7ae36d7b76dd6372c1494a5b704`.
- Root cause was confirmed on the authorized device: `tblsection.htm` passed an URL-encoded `file=%2F...` route through Lua `string.format`, so `%2F` was parsed as a format directive and the NaiveProxy add/import editor failed before rendering. The fix replaces only the explicit `%s` placeholder and preserves encoded query bytes.
- Device backup before the formal install: `/tmp/openkill-naive-1151-backup-20260925-212115/config.tgz`, SHA256 `4d7e63e516bc6e47ad67dd1d35a0ca91f3f2b06623c035b7ac8b7408e26d784`.
- Device post-install evidence: OpenKill `2026-1151`, service `running`, `/etc/openkill/core/naive` executable, 127.0.0.1:11080 ready, fixed TCP SOCKS probe returned HTTP 204, helper state `configured=1/generated=1/component_installed=1/local_ready=1/remote_verified=0`. No DNS, routing, firewall, or central nft changes were made.
- Browser evidence on the formal package: both “添加 NaiveProxy 节点” and “导入分享链接” opened the existing node editor with the encoded configuration path intact; no Runtime error was rendered. The existing node and protected configuration were preserved.
- Remote Naive authentication, UDP forwarding, IPv6 behavior, and application-level streaming remain unverified because the test only used a fixed local TCP probe.

## NaiveProxy direct node flow and device loop repair (2026-09-25)

- Scope: route the compatibility-card Add/Import actions directly to the existing NaiveProxy node editor by creating a marked, disabled draft section; retain the generic server manager for management and keep the legacy encoded-file route intact. Draft sections are cleaned only when a new direct-add flow begins, so ordinary user nodes are never removed.
- UI contract: the page continues to own one node editor and one UCI source. Add/import must not open the generic server list; import remains a structured preview in the existing editor. The direct endpoint preserves the selected YAML path and the `type=naiveproxy`/`import=1` hints.
- Device contract: before changing the authorized test device, archive OpenKill configuration, component and runtime state. Remove the previously imported private Naive node only after the backup, without touching unrelated nodes, subscriptions or YAML. Keep credentials out of logs and reports.
- Outbound contract: OpenKill's existing fw4/legacy writers reserve GID 65534 as the self-traffic bypass. NaiveProxy helper instances remain root-owned for protected configuration but run with group `nogroup` so their remote TCP sockets are not recursively intercepted. No new central nft state, WAN change or broad port exemption is introduced.
- Verification: test direct routing and draft creation statically and in LuCI; on the device confirm the helper's effective group, bounded file descriptors, local SOCKS5 readiness and a redacted TCP probe. Remote authentication, UDP, IPv6 and streaming remain unverified unless a non-secret endpoint test provides evidence.

## 2026-1152 direct NaiveProxy entry and loop-repair release evidence (2026-09-25)

- Source commits `904fdcfe580547d18f346c7e771a9d40397a2dd1` (direct
  compatibility-card Add/Import route and helper `nogroup` loop fix),
  `6a928ed76eb18c12c6dd02c13ef597ad057d3aca` (version metadata), and
  `352d0b5e63fe637c88e126498c9e6dd503cc66e3` (clear marked draft after the
  editor is submitted) are on `master`. The final exact Development CI passed:
  [run 36143466609](https://github.com/dinggood615/openkill/actions/runs/36143466609).
- Local NaiveProxy integration tests, POSIX/local-gate and diff checks passed.
  The final RC Build from `352d0b5` passed:
  [run 36143804420](https://github.com/dinggood615/openkill/actions/runs/36143804420).
  The formal package is `luci-app-openkill_2026-1152_all.ipk`, SHA-256
  `2a711d3f80b5afc9902f0406500c4aa254f5b9e8a261e697c3a5611bdb006744`,
  archived under `D:\openkill-cache\formal-2026-1152`. The extracted package
  contains the direct `naive_node` route, draft cleanup, `nogroup` helper
  setting, Naive compatibility view and final CSS; archive members retain
  root ownership and expected executable/read-only modes.
- Formal Release with `release_gate=true` and `publish=true` passed:
  [run 36144577215](https://github.com/dinggood615/openkill/actions/runs/36144577215).
  Published [v2026-1152-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1152-ipk)
  from `352d0b5`; the release asset SHA-256 matches the audited package above.
  `v2026-1151-ipk` remains available for rollback.
- Authorized-device backup before cleanup was
  `/tmp/openkill-naive-cleanup-20260925-213824/config.tgz`, SHA-256
  `3822fda3e4be8588acf9f69a373a349b0d131ad0be053a85c6da44ecd47dbb93`.
  The earlier private NaiveProxy node was removed only after this backup; the
  device now has zero NaiveProxy server sections and no private node in the
  source, package or package-default conffile. Existing OpenKill configuration
  and unrelated services were preserved.
- Before cleanup, the device reproduced the failure as repeated helper
  `ERR_INSUFFICIENT_RESOURCES` with approximately 1024 descriptors because the
  root-group helper was recursively intercepted. A temporary `nogroup`
  verification reduced the helper to a bounded descriptor count and a local
  SOCKS5 HTTPS probe returned HTTP 204; this is transport-path evidence only,
  not remote authentication or application access. The formal package now
  carries the same `nogroup` service setting. After formal installation the
  device reports OpenKill `2026-1152`, the core route and direct editor route
  are present, the service core is running, and no Naive helper starts without
  an enabled node. The modified device conffile was preserved by opkg as
  `/etc/config/openkill-opkg`.
- Browser-rendered device UI could not be re-captured in this iteration because
  the browser debugging session detached; an unauthenticated HTTP probe
  correctly returned LuCI 403/login-required. Source/package route checks and
  device installation checks passed. Remote Naive authentication, UDP, IPv6,
  streaming, and full browser viewport validation remain unverified.

## One-click NaiveProxy install failure repair (2026-09-25)

- Reproduction: on the authorized test device, `openkill_naive_metadata.sh cached`
  returned `reason=official-api-unavailable`; `curl` failed the TLS handshake to
  GitHub because Fake-IP DNS resolved `api.github.com` into the synthetic
  `198.18.0.0/15` range. This is a bootstrap metadata-path failure, not proof
  that the selected component asset is invalid.
- UI failure: `autoInstall()` always forced `requestMetadata('detect', true)`.
  When the page already contained a complete URL/SHA256 pair, a metadata API
  failure still prevented the install task from being started. The repair will
  use a complete existing pair directly and only perform metadata discovery
  when either field is missing; incomplete pairs remain blocked.
- Contract: URL and SHA256 remain one bound trusted asset pair; no credentials,
  node data or network-policy changes are introduced. Metadata errors remain
  visible and never silently trigger DIRECT or an unverified download.
- Verification: add behavior coverage that a complete pair starts
  `install-task` without a metadata request, while missing/incomplete pairs
  require successful metadata discovery. Re-run NaiveProxy integration,
  POSIX/BusyBox syntax, local-gate and diff checks, then perform a device
  metadata/install-path regression without restoring private node data.

## One-click installer bounded database refresh (2026-09-25)

- Device reproduction after the 2026-1153 candidate install: the one-click
  installer remained in `/tmp/openkill-installer.*` while sequentially trying
  the four GeoSite/GeoIP/ASN mirrors. The current device resolves public
  GitHub/jsDelivr names to Fake-IP addresses and the TLS attempts fail, so
  each optional database download waits for its full 180-second timeout. The
  packaged databases are already a valid fallback; this delay makes the
  installer appear hung even though the OpenKill package and component steps
  have completed.
- Planned repair: bound the optional database refresh with a single global
  deadline, stop trying further mirrors when the deadline is exhausted, retain
  packaged files, and report the skipped refresh as a non-fatal warning. This
  does not alter DNS, routing, firewall, proxy or NaiveProxy node behavior.
- Verification must cover a fast successful mirror, timeout/synthetic-IP
  failure, deadline exhaustion and preservation of packaged databases. The
  device test will terminate only the stale installer process from this
  reproduction after recording its failure stage; no user configuration or
  node data will be changed.

## 2026-1154 one-click installer release evidence (2026-09-25)

- Source commit `ae0c24bfd17401a8de0a3c3b783c3125f65a7046` is on `master`.
  The exact Development CI passed: [run 36151093802](https://github.com/dinggood615/openkill/actions/runs/36151093802).
- The RC Build passed from that exact source: [run 36151287232](https://github.com/dinggood615/openkill/actions/runs/36151287232).
  Its SDK audit artifact is `OpenKill-openwrt-sdk-audit`, SHA256
  `a0cdb968092d4a49cf64ccc6a610b4d846aeb2e222a33aa4a475333f1fde9f39`;
  the contained `luci-app-openkill_2026-1154_all.ipk` SHA256 is
  `a630e71013f54bc36760c8034161776a5ba411205d757eff26722fb9095991a8`.
  Package metadata, conffile preservation, maintainer-script deletion audit,
  stale-development-reference audit and sensitive-content audit passed.
- Formal Release with `release_gate=true` and `publish=true` passed:
  [run 36152194588](https://github.com/dinggood615/openkill/actions/runs/36152194588).
  Published [v2026-1154-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1154-ipk)
  from the exact source; the formal IPK SHA256 is
  `ec548ab07da4c7d995a3aed7752e9508ee2635ec08e31e44e8c0dda5a5adadaf`.
  `v2026-1153-ipk` remains available for rollback.
- Authorized-device backup before the formal installation:
  `/tmp/openkill-1154-formal-20260925-231502/config.tgz`, SHA256
  `5dcb4773d84d45f55c2363f4e80828e81adab8ac614ddb3d7f132e683fc645ad`.
  The formal package installed as OpenKill `2026-1154`; `/etc/openkill/core/naive`
  is executable and the helper reports `component_installed=1`,
  `configured=0`, `generated=0`, `local_ready=0`, `remote_verified=0`,
  `state=disabled`, `reason=no-enabled-nodes`. No credentials or node data
  were emitted or changed by this verification.
- The stale pre-fix installer process was stopped after its failure stage was
  recorded. The device's selected YAML was absent after that interrupted run,
  so `/etc/init.d/openkill` correctly remains inactive instead of inventing a
  configuration. This is a missing device configuration prerequisite, not a
  claim that a NaiveProxy remote connection was restored.
- Local installer behavior, the global optional-database deadline, service
  state restoration, NaiveProxy integration, POSIX syntax and local-gate all
  passed. The device still cannot reach public GitHub/jsDelivr through its
  current Fake-IP/TLS bootstrap path; component download and remote Naive
  authentication remain device-pending.

## 2026-1160 standalone NaiveProxy bridge release evidence (2026-09-26)

- The standalone migration is implemented in source commit
  `d7aacef60ed4a1a4912cda3b2f164ebd65650ed0`; version metadata and release
  notes were finalized in `6cf5cec505133785cb46da62b48044c716ef68b6` on
  `master`. OpenKill no longer owns NaiveProxy credentials, starts or stops
  the bridge, probes nodes, or injects Naive nodes into Mihomo. The bridge
  owns `/etc/naiveproxy`, `/var/run/naiveproxy`, per-node protected JSON,
  loopback listeners, health state and the `naiveproxy-bridge` procd service.
- Local verification passed: standalone fixture, integration contracts, UI
  contracts and interactions, Python compilation, POSIX syntax, YAML and
  credential-redaction checks, `sh scripts/local-gate.sh`, and
  `git diff --check`. `scripts/test-installer.py` could not run on the Windows
  host because the optional `yaml` module is absent; browser, device and
  real-VPS packet/remote authentication tests remain unverified by plan.
- Exact Development CI passed for the implementation commit:
  [run 36237005619](https://github.com/dinggood615/openkill/actions/runs/36237005619),
  and for the release-preparation commit:
  [run 36237152719](https://github.com/dinggood615/openkill/actions/runs/36237152719).
- RC Build passed from the exact release-preparation commit:
  [run 36237326633](https://github.com/dinggood615/openkill/actions/runs/36237326633).
  The RC IPK is 7,695,999 bytes with SHA256
  `722e1483442a896f932a7430a326012be6099f57d57f890990ae7ed02085e013`.
- Formal Release passed with `release_gate=true` and `publish=true`:
  [run 36237633490](https://github.com/dinggood615/openkill/actions/runs/36237633490).
  It published [v2026-1160-ipk](https://github.com/dinggood615/openkill/releases/tag/v2026-1160-ipk)
  from commit `6cf5cec505133785cb46da62b48044c716ef68b6`.
  The formal `luci-app-openkill_2026-1160_all.ipk` SHA256 is
  `3cb809939e5f1eb1c47213be0099dc2fdbe635dbbe9b087c25a4f68df1821a4e`.
- Rollback remains `v2026-1159-ipk`; preserve `/etc/naiveproxy` before
  changing packages, stop the independent bridge if needed, reinstall the
  previous IPK, and leave user-managed YAML untouched.
