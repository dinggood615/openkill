# Local validation hardening

This work package closes the gap between a local typed-shadow replay and the
candidate that may later be staged on `.102`. It does not change the packet
writers, DNS topology, routing ABI, package version, or device state.

The automatic shadow coordinator freezes DNS evidence before its continuity
token is created. `DNSMASQ_LISTEN_TARGET` and
`DNSMASQ_UPSTREAM_TARGET` come from the committed dnsmasq state; the
`MIHOMO_DNS_LISTENER` actual value comes from one unambiguous, process-owned
UDP socket in the bounded `netstat` evidence. The process name must be one of
the supported Mihomo/Clash core names, so unrelated TCP control or proxy ports
do not make a valid DNS listener ambiguous. Multiple core-owned UDP ports,
unknown core names, or missing UDP evidence are a source gap.
`OPENKILL_DNS_ENDPOINT` is a readiness/configuration intent used by init and
is never treated as live listener evidence. Fixture-only runs may use their
checked-in runtime snapshot because that source is explicitly labelled as
fixture evidence.

The T0 artifact is the only DNS value consumed by the typed producer and
comparator. T1 and T2 re-sample the same live dnsmasq and core-owned listener
sources at continuity boundaries and compare them with the T0 artifact. A
change or missing source makes the whole cycle `STALE`/source-gap; it never
mixes a later live value into the frozen sidecar and never performs a
comparator-stage reread.

The typed provenance contract is deliberately field-specific:

| Field | Actual source | Desired source | Missing behavior |
| --- | --- | --- | --- |
| `DNS_FIREWALL_LAN_TARGET` | bounded legacy nft capture/parser | CURRENT renderer output | `MODEL_GAP` |
| `DNS_FIREWALL_ROUTER_TARGET` | bounded legacy nft capture/parser | CURRENT renderer output | `MODEL_GAP` |
| `DNSMASQ_LISTEN_TARGET` | frozen dnsmasq UCI/runtime evidence | committed D2C contract | `MODEL_GAP` |
| `DNSMASQ_UPSTREAM_TARGET` | frozen dnsmasq UCI/runtime evidence | committed D2C contract | `MODEL_GAP` |
| `MIHOMO_DNS_LISTENER` | frozen process-owned `netstat` evidence | committed Mihomo contract | `MODEL_GAP` |
| `DNS_LOOP_PREVENTION` | parsed nft semantic rule | CURRENT manifest/renderer contract | `MODEL_GAP` |
| `DNS_SCOPE_IPV4` | parsed v4 interception scope | CURRENT scope contract | `MODEL_GAP` |
| `DNS_SCOPE_IPV6` | parsed v6 interception scope | CURRENT scope contract | `MODEL_GAP` |

Each row is captured before the T0 continuity identity is sealed. The only
later reads are the explicit T1/T2 continuity boundary checks described above;
the comparator itself does not query live UCI, nft, ip, netstat or Mihomo
state. Missing, duplicate or ambiguous provenance fails closed.

The staged observer regression copies the observer, renderer and semantic
templates to a private directory and sources that copy through a separate
wrapper. The wrapper records execution identity and verifies the observer
hash before sourcing it; it never changes the candidate bytes. Five
independent automatic cycles must report `MATCH` with stable owned and DNS
hashes. The test does not provide typed sidecars, a Python oracle, or a
repository runtime fallback. Execution metadata and candidate hashes bind the
result to the bytes that were executed.

`scripts/openkill-test-gates.py` is the single local entry point. `fast` is the
short feedback loop, `full` runs the Windows/WSL matrix, and
`device-preflight` repeats the local checks that must pass before requesting a
new device phase. Each case has an explicit environment and timeout, captures
its own return code, and writes a run bundle under
`artifacts/test-evidence/<run-id>/`. Cache keys contain source/test/fixture
hashes, runner and interpreter versions, command and environment; a commit id
alone is never used as evidence.

The preflight result is a local readiness statement. It records a candidate
manifest containing the observer, renderer, semantic manifest/template and
canonical fixture hashes. `DEVICE_RETRY_READY=YES` means only that this
candidate is ready to be considered for an explicitly approved `.102` phase;
it does not imply device verification, package release, central apply, or
packet-path proof.

The gate runner rejects a dirty worktree or a missing candidate artifact before
it runs a mode. After every mode it rechecks the HEAD, runner source, canonical
fixture, and every manifest artifact byte/hash. A candidate identity record is
written with the evidence bundle, so a source or staging change during a long
run cannot be reported as device-ready evidence. Fast-mode cache keys include
the UI templates and stylesheets used by the LuCI contract test, while full
and device-preflight always execute their cases.

The LuCI contract check also covers the presentation fixes in this work
package: stylesheet cache keys are rendered from the installed package
version, the subscription detail wrapper has the id used by its JavaScript,
and dashboard/proxy controls restore their visible state when a later status
poll reports recovery. It is a static template regression check; it does not
claim that a live LuCI backend or browser session was exercised.

Official Mihomo compatibility downloads remain fail-closed: if the local
WSL TLS/DNS/network path cannot reach the release API or asset, the unified
runner records `CORE_RELEASE_UNAVAILABLE` as an explicit environment-limited
case. A download or checksum that reaches the test but fails validation is
still a required failure.
