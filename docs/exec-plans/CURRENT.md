# Current status

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
