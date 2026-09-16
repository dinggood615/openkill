# Phase 3E.2D2D-R3A production shadow semantic model

R3's five device cycles were a stable raw `MISMATCH`, while the bounded
device facts and the D2C DNS contract were equal.  The old shell fallback
compared normalized physical nft chains and used `openkill*` as an ownership
shortcut.  That made the legacy WAN safety chains comparable to CURRENT state
and could not represent the three DNS layers independently.

R3A adds an additive typed path to
`luci-app-openkill/root/usr/share/openkill/openkill_nft_shadow.sh`:

```
captured/parser output -> formal typed sidecar -> ownership projection
                         -> typed DNS projection -> semantic result
```

The sidecar is a bounded, line-oriented
`OPENKILL_SHADOW_TYPED_INTENT_V1=1` file.  `OBJECT` rows carry the logical ID,
physical name, component, formal D2B ownership class, active state, and a
canonical semantic payload.  `DNS` rows carry one D2C field, its value, formal
owner, source description, and active state.  Two sidecars are supplied for a
cycle (`OPENKILL_NFT_SHADOW_TYPED_ACTUAL_FILE` and
`OPENKILL_NFT_SHADOW_TYPED_DESIRED_FILE`).  The coordinator copies them into
the private cycle directory before comparison, so the comparator never
re-reads UCI, nft, dnsmasq, Mihomo, network, or ubus.

`shadow/semantic_model_v1.tsv` is the shared schema vocabulary.  It defines
the D2B ownership classes and exactly these D2C fields:

* `DNS_FIREWALL_LAN_TARGET`
* `DNS_FIREWALL_ROUTER_TARGET`
* `DNSMASQ_LISTEN_TARGET`
* `DNSMASQ_UPSTREAM_TARGET`
* `MIHOMO_DNS_LISTENER`
* `DNS_LOOP_PREVENTION`
* `DNS_SCOPE_IPV4`
* `DNS_SCOPE_IPV6`

`CURRENT_OWNED` and active `CONDITIONAL_CURRENT` rows enter equality.
`LEGACY_ONLY_SAFETY`, `FW4_BASE`, `INACTIVE_MODE`,
`OPTIONAL_OBSERVATION`, and `OUT_OF_SCOPE` rows remain in the actual full
observation and its hash, but are excluded from the CURRENT-owned projection.
An `UNKNOWN` class, duplicate logical identity, invalid row, missing DNS value,
or missing source is `MODEL_GAP` (new shell result 12).  A missing active
CURRENT row or a changed typed value is `MISMATCH` (the existing result 1).
The established result numbers for MATCH, MISMATCH, stale, capture, and
render errors are unchanged.

The physical name is only an inventory join/display value.  For example,
`openkill_wan_input` with formal role `WAN_SAFETY` and class
`LEGACY_ONLY_SAFETY` is observed and reported without affecting CURRENT parity;
the same physical name with `UNKNOWN` ownership is a model gap.  No name-based
ignore rule or new structural equivalence was added.

DNS values are compared as independent typed fields.  Mode 1 uses firewall
targets `53`, dnsmasq listener `53`, dnsmasq upstream `127.0.0.1#7874`, and
Mihomo listener `127.0.0.1:7874`.  A firewall target is never inferred from an
upstream or listener, and `53 == 7874` is not an equivalence.  Loop prevention
and IPv4/IPv6 LAN-plus-router scope are separate fields.  Mode 2 remains a
source/model consistency concern and is not silently changed by the mode-1
projection.

The shell implementation uses only POSIX `/bin/sh`, BusyBox-compatible `awk`,
`sort`, and the existing hash helper.  It has no Python, jq, Ruby, or other
new runtime dependency.  `openkill_shadow_semantic_model.py` remains the
development oracle; `scripts/test-shadow-production-typed.py` compares the
same sanitized positive and negative cases through the production shell path.
The old raw automatic fallback and explicit bundle protocol remain available
to older callers.  R3C adds an internal producer to the automatic path, so a
production caller no longer needs to provide sidecars; explicit sidecars are
retained only for fixture/development invocations.  This preserves backward
compatibility while making ownership and DNS policy explicit for the next
device revalidation.

Telemetry is additive and bounded: model versions, status, short hashes for
the full observation, CURRENT-owned projection, and DNS projection, counts,
and DNS parity only.  It contains no rules, addresses, endpoints, or
credentials.  The observer still performs no dataplane write and does not
change legacy writer behavior.
