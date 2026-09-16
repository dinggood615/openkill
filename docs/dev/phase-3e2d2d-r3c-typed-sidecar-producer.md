# Phase 3E.2D2D-R3C typed sidecar producer

R3B stopped before a device run because the production automatic coordinator
could consume typed sidecars but could not create them.  Supplying the checked
in sidecar fixtures would only prove the parser and comparator; it would not
prove that a live device capture and the CURRENT renderer produce independent
observations.  R3C closes that producer gap locally.  No device, router,
package, or dataplane is touched by this phase.

## Automatic cycle

The automatic path now keeps one private cycle directory and follows this
order:

```
coherent T0/T1 snapshot
  -> bounded legacy capture and parser
  -> formal inventory classification
  -> CURRENT input and renderer output
  -> typed actual producer + typed desired producer
  -> existing typed comparator
  -> T2 continuity check and bounded telemetry
```

The producers run after the renderer has succeeded.  The actual side uses the
parsed capture for nft objects and the scalar values frozen by the same auto
state snapshot for runtime DNS, loop prevention, scope, and ABI fields.  The
desired side uses the renderer output for firewall DNS targets, the renderer's
typed input/template and semantic manifest for desired objects, and explicit
`DNS_EXPECTED` contract records for the other DNS layers.  It never copies
actual values into desired values, and neither producer performs a discovery
read after the snapshot.

If a required source is absent, two different values are found for one field,
or an object cannot be joined to the formal inventory, the cycle returns
`MODEL_GAP` (exit status 12).  A typed value that is present but different
returns the existing `MISMATCH` result.  `MATCH`, `MISMATCH`, `MODEL_GAP`,
`STALE`, and capture/input errors therefore remain distinct.

## Sidecar contract

Each internal file is a private, mode-0600,
`OPENKILL_SHADOW_TYPED_SIDECAR_V1` sidecar with a cycle and continuity
identity.  It contains versioned metadata, formal `OBJECT` rows, and the
independent D2C `DNS` fields:

* `DNS_FIREWALL_LAN_TARGET`
* `DNS_FIREWALL_ROUTER_TARGET`
* `DNSMASQ_LISTEN_TARGET`
* `DNSMASQ_UPSTREAM_TARGET`
* `MIHOMO_DNS_LISTENER`
* `DNS_LOOP_PREVENTION`
* `DNS_SCOPE_IPV4`
* `DNS_SCOPE_IPV6`

The manifest at
`luci-app-openkill/root/usr/share/openkill/shadow/semantic_model_v1.tsv` is
the shared line-oriented vocabulary.  WAN safety rows remain in the full
observation and are classified as `LEGACY_ONLY_SAFETY`; they are excluded
from CURRENT-owned equality by their formal metadata, never by a physical-name
ignore list.  Required and conditional presence rules from D2A are preserved.

The automatic production path is self-contained by default and does not use
`OPENKILL_NFT_SHADOW_TYPED_ACTUAL_FILE` or
`OPENKILL_NFT_SHADOW_TYPED_DESIRED_FILE`.  Those variables remain available
only for an explicit fixture/development invocation.  Automatic mode rejects
them even if a caller exports a legacy override flag, so externally prepared
sidecars can never become device parity evidence.

The sidecars and their hashes are temporary cycle data.  They are bounded by
`OPENKILL_NFT_SHADOW_MAX_PAYLOAD_BYTES`, cleaned by the existing coordinator
trap, and never written to `/etc`, `/usr/share`, UCI, or package-managed
files.  Telemetry contains only status, counts, versions, and semantic hashes;
it excludes counters, handles, PIDs, timestamps, addresses, credentials,
subscriptions, and private endpoints.

## Runtime and validation

The production implementation remains POSIX `/bin/sh` with BusyBox `awk`,
`sort`, and the existing hash helper.  It adds no Python, jq, Ruby, or other
runtime dependency.  Python's
`scripts/openkill_shadow_semantic_model.py` remains a local test oracle only.

`scripts/test-shadow-sidecar-producer.py` covers the automatic no-sidecar
path, renderer/actual source separation, DNS and ABI mutations, missing source
model gaps, deterministic hashes, and a minimal staged observer/manifest
simulation.  The existing explicit typed, self-sufficiency, continuity,
BusyBox, and runtime suites remain in the local and development CI gates.

R3C does not claim that the installed 2026-1128 release contains this
observer, and it does not grant device parity, central apply, or packet-path
approval.  The next device phase may stage the observer and manifest only
after this local producer contract is reviewed.
