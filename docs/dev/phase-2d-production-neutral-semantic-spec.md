# Phase 2D: production-neutral dataplane semantic specification

Phase 2D freezes the semantic contract that the future modern and legacy
backends must share.  The machine-readable source is
`scripts/fixtures/openkill-dataplane-semantic-spec-v1.json`; this document
explains how to read it and records the production boundary.

## Scope and versions

The specification is `OPENKILL_DATAPLANE_SEMANTIC_SPEC_V1` and carries the
following compatible versions:

| Contract | Version |
| --- | ---: |
| Dataplane semantic specification | 1 |
| Shared classifier contract | 1 |
| Shadow state schema | 1 |
| Current intent fixture | 1 |
| Mark ABI | 1 |

`current` is the only production profile.  `target` is a development preview
and is never selected implicitly.  Unknown versions or profiles fail closed.

The production fact flow is:

```text
configuration and netifd facts
        ↓
normalized desired state
        ↓
semantic facts
        ↓
classifier (current profile by default)
        ↓
backend renderer
```

The specification is consumed by future renderers, the executable classifier,
the shadow adapter, golden tests, and the component reconcile design.  Phase
2D does not connect the classifier or this file to the OpenWrt service.

## Four semantic layers

1. **Ownership and scope** determines whether OpenKill owns the context.  An
   `OPENKILL` owner continues classification; `MIHOMO`, `DISABLED`, and
   `UNKNOWN` are `NOT_OWNED`, never an implicit direct decision.  The
   `SINGLE_DATAPLANE_OWNER` invariant prevents simultaneous proxy dataplane
   owners during a transition.
2. **Safety and access** contains DNS, control protocols, self traffic, TUN
   ingress, node endpoints, local destinations, replies, service ports, and
   access-control facts.  It protects network operation and underlay loops
   before ordinary routing policy.
3. **Routing policy** contains Fake-IP, explicit user policy, China pass,
   China policy, and the default policy.  A Fake-IP is a proxy destination
   fact, not a backend action.  Explicit policy remains partially unresolved
   in the current production oracle.
4. **Backend action** translates one decision into capabilities of TUN,
   TProxy, redirect, native return, or DNS handling.  It never chooses a
   precedence or changes a classifier decision.

## Current and target profiles

The profiles have independent precedence tables.  The current table records
the audited behavior, including custom access before node endpoints, the
IPv4-only TUN return, and China-pass fall-through.  The target table places
control and underlay safety before access and explicit policy.  Every target
difference is recorded as BC-01 through BC-07 with
`PRODUCTION_NOT_APPROVED` status.

The default production profile remains `current` until each behavior change
is approved separately.  This allows a semantic-preserving renderer migration
to be reviewed independently from product policy changes.

## Native IPv6 and underlay invariants

OpenWrt/netifd owns native IPv6 addresses, SLAAC/DHCPv6, delegated prefixes,
and source-specific routes.  OpenKill preserves those facts and never creates
a generic native main-table IPv6 default or uses NAT66 as a routing substitute.
An interface WAN IPv6 address is a host identity (equivalent to `/128`), while
LAN and delegated prefixes retain network-prefix semantics.

Node endpoints, self traffic, and TUN ingress are separate diagnostic reasons
even when their outcome is a bypass.  A node-resolution failure retains the
last-known-good applied endpoint set.  A provider endpoint enters that node
state rather than creating a new semantic reason.

## Fact sources and ownership

`fact_source_map` names a primary normalized source, a fallback, the
canonicalization rule, owner, volatility, confidence, and source status for
each semantic fact.  In particular:

- local and WAN facts come from the network snapshot and desired state;
- node endpoints come from node desired/applied state and its last-known-good
  cache;
- China, China-pass, Fake-IP, service ports, DNS scope, and ACL facts come from
  normalized desired state;
- self and TUN are runtime observations normalized by reconcile;
- explicit direct/proxy mapping is deliberately marked unresolved in the
  current production source map.

Renderers consume this normalized state and do not independently re-read
configuration or reinterpret runtime sources.  The watchdog can observe or
request reconciliation, but it is not a second writer.

## Renderer and cleanup contract

The renderer input includes versions, profile, backend context, the selected
classification, semantic facts, dynamic sets, and ownership.  It must:

- reject unknown schema, profile, enum, fact, or unsupported capability;
- translate the selected decision and preserve its reason for diagnostics;
- preserve semantic parity across modern and legacy backends and across
  required IPv4/IPv6 pairs;
- use ownership-scoped cleanup and preserve foreign objects;
- keep all mutations behind reconcile and never implement a broad flush;
- report an unexpressible capability (for example redirect with UDP) instead
  of silently selecting direct behavior.

Static semantics are ownership classes, layer boundaries, precedence, safety,
enums, invariants, version compatibility, and the frozen mark ABI.  Dynamic
data are local/WAN/node/China/ACL/service/Fake-IP/DNS sets, user policy facts,
and runtime health observations.  Dynamic changes feed component reconcile;
they do not silently redefine the contract.

The frozen mark ABI is mark `0x162`, full mask `0xffffffff`, route table `354`,
and rule preference `1888`.  It is unchanged until the later Mark ABI phase.

## DNS, ACL, and custom firewall boundaries

DNS is a separate `DNS_SPECIAL` semantic entry with explicit LAN and router
scopes.  China, user, and default routing policy do not decide DNS
interception.  Access control is separate from routing policy: access bypass
and access deny are facts, while direct and proxy are routing decisions.  The
modern access-deny discrepancy remains BC-07 and is not normalized by this
specification.

Custom firewall behavior is outside the classifier unless a later design
assigns it an explicit pre-hook, post-hook, or externally unmanaged boundary.
Arbitrary custom text is never interpreted as semantic policy.

## Reconcile and ownership contracts

When semantic state is unchanged and runtime is healthy, reconcile produces
zero dataplane writes.  Node-only, local6-only, topology, route, and rule
changes have component-specific actions; a full rebuild is reserved for an
actual component dependency.  Only reconcile mutates OpenKill-owned state.

The snapshot describes native network facts and excludes proxy-owned TUN route
telemetry from the semantic fingerprint.  This keeps the fingerprint
idempotent and aligns with the earlier baseline migration work.

## Behavior-change records

BC-01 through BC-07 are complete records in the JSON source, covering current
and target behavior, safety and compatibility impact, legacy and modern impact,
packet-path impact, rollback risk, recommendation, and approval status.  Their
current status is always `PRODUCTION_NOT_APPROVED`; a recommendation is not an
approval.

## Validation

Run the development-only validator from the repository root:

```text
wsl python3 scripts/test-dataplane-semantic-spec.py
```

It validates versions, enums, profile precedence drift, behavior-change and
fact-source completeness, renderer invariants, the 97 current and 97 target
classifier cases, the 32 overlap cases, the 31 parity groups, and all 109
shadow cases.  The validator also rejects backend command syntax in the
semantic file.  No production runtime file is imported or executed.
