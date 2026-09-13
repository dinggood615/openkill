# Phase 3A: central NFT renderer design

Phase 3A defines a development-only abstract renderer.  The machine-readable
contract is [`openkill-nft-ir-v1.json`](../../scripts/fixtures/openkill-nft-ir-v1.json)
and the implementation is [`openkill_nft_ir.py`](../../scripts/openkill_nft_ir.py).
It consumes the Phase 2D semantic specification and the Phase 2B classifier;
it stops at an abstract intent and never applies a rule to a device.

## Architecture

The renderer has two levels:

```
semantic facts
    -> classifier result (reason, decision)
    -> semantic action IR (backend-neutral)
    -> NFT_IR_V1 (tables, chains, sets, rules, ownership metadata)
    -> validator and semantic diff
```

The semantic classifier remains the only owner of precedence.  The renderer
translates the selected result and records backend requirements; it does not
re-evaluate China, node, Fake-IP, ACL, or user-policy precedence.  A future
legacy renderer may consume the same semantic action layer.

`NFT_IR_VERSION=1`, `semantic_spec_version=1`,
`classifier_contract_version=1`, and `OPENKILL_NFT_MANIFEST_V1` are explicit
metadata.  The production default is `profile=current`.  `profile=target`
requires an explicit development preview flag and carries
`TARGET_PREVIEW_ONLY`.  BC-01 through BC-07 remain
`PRODUCTION_NOT_APPROVED`.

## IR schema

An IR document contains:

| Section | Purpose |
| --- | --- |
| `metadata` | version tuple, profile, backend, current/target lock, frozen mark ABI |
| `static_topology` | external fw4 references, owned chains, owned jumps and stable roles |
| `dynamic_state` | canonical dynamic sets; empty sets are valid |
| `rules` | semantic match primitives, stable logical rule IDs, precedence labels and action requirements |
| `action_ir` | one concrete classifier result when rendering a packet context |
| `dependencies` | component dependencies used by future incremental reconcile |
| `ownership_manifest` | exact owned objects eligible for future cleanup |

Object types are `table_ref`, `chain`, `chain_ref`, `set`, `rule`, and `jump`.
Match primitives are semantic (`family`, `direction`, `protocol`, set
membership, service, connection, owner, interface role, and semantic flag),
never backend expressions.  Action types include `RETURN_NATIVE`,
`MARK_PROXY`, `TPROXY_PROXY`, `REDIRECT_PROXY`, `DNS_REDIRECT`,
`ACCESS_DENY_REQUIRED`, `NOT_OWNED`, `CONTINUE_POLICY`,
`UNRESOLVED_SEMANTIC`, and `UNSUPPORTED_ACTION`.

`PROXY` is the semantic decision.  The separate action mapper maps it to
`MARK_PROXY` for TUN, `TPROXY_PROXY` for TProxy, and `REDIRECT_PROXY` for TCP
redirect mode.  Redirect plus UDP is explicitly `UNSUPPORTED_ACTION`; it is
never silently changed to direct or another backend.  `ACCESS_DENY` maps to
`ACCESS_DENY_REQUIRED` without choosing drop versus reject.

## Static topology

The topology contains external references to the fw4-owned `inet fw4` table
and its base chains (`dstnat`, `mangle_prerouting`, `mangle_output`, `output`,
`forward`, `input`, `srcnat`, and `upnp`).  Their priorities are recorded as
`EXTERNAL_UNVERIFIED`; Phase 3A does not invent fw4 priority numbers.

OpenKill-owned regular chains retain the names found in the current source:

| Role | IPv4 | IPv6 |
| --- | --- | --- |
| `PREROUTING_PROXY` | `openkill` | `openkill_v6` |
| `PREROUTING_MANGLE` | `openkill_mangle` | `openkill_mangle_v6` |
| `OUTPUT_PROXY` | `openkill_output` | `openkill_output_v6` |
| `OUTPUT_MANGLE` | `openkill_mangle_output` | `openkill_mangle_output_v6` |
| `POSTROUTING` | `openkill_post` | `openkill_post_v6` |
| `WAN_INPUT` | `openkill_wan_input` | `openkill_wan6_input` |
| `DNS_LAN` | `openkill_dns_hijack` | `openkill_dns_hijack_v6` |
| `DNS_ROUTER` | `openkill_dns_redirect` | `openkill_dns_redirect_v6` |

The current `nat_output` base chain is represented as
`OPENKILL_NAT_OUTPUT_CURRENT`, owned by OpenKill inside the fw4 parent, with
the source-audited `OUTPUT` hook and priority `-1`.  This is a current-profile
expression only.  A future fw4-owned attachment can be proposed separately;
it must not alter the current IR silently.  TProxy preview mode adds explicit
IPv4/IPv6 TProxy chain objects, while route creation remains a route-component
responsibility.

The current `openkill_upnp` lease-exclusion chain is represented as one
inet-wide `UPNP` chain.  Lease entries remain dynamic and isolated from the
classifier policy sets; the abstract topology records the owned chain and its
semantic attachment without embedding lease parsing or backend syntax.

## Dynamic state

Dynamic sets have stable semantic IDs separate from physical names:

| Semantic ID | Current physical name | Component | Family/type |
| --- | --- | --- | --- |
| `LOCAL_V4`, `LOCAL_V6` | `localnetwork`, `localnetwork6` | LOCAL | prefix |
| `WAN_HOST_V4`, `WAN_HOST_V6` | `openkill_wan_host4`, `openkill_wan_host6` | LOCAL | address |
| `LAN_V4`, `LAN_V6`, `DELEGATED_V6` | OpenKill-owned names | LOCAL | prefix |
| `NODE_ENDPOINT_V4`, `NODE_ENDPOINT_V6` | `openkill_node4`, `openkill_node6` | NODE | address |
| `CHINA_V4`, `CHINA_V6` | `china_ip_route`, `china_ip6_route` | CHINA | prefix |
| `CHINA_PASS_V4`, `CHINA_PASS_V6` | `china_ip_route_pass`, `china_ip6_route_pass` | CHINA | prefix |
| `FAKEIP_V4`, `FAKEIP_V6` | OpenKill-owned names | PROXY_ACTION | prefix |
| `USER_DIRECT_*`, `USER_PROXY_*` | OpenKill-owned names | ACCESS | prefix |
| `ACCESS_V4_*`, `ACCESS_V6_*` | OpenKill-owned names | ACCESS | prefix |
| `SERVICE_PORTS`, `COMMON_PORTS` | `openkill_service_ports`, `common_ports` | SERVICE | port |

All elements are deduplicated and sorted.  IPv4/IPv6 addresses and prefixes
are canonicalized with explicit family validation.  A WAN IPv6 interface
address is represented as a host semantic `/128`; a LAN or delegated prefix
retains its network semantic.  An empty dynamic set remains a valid referenced
set so endpoint churn does not require topology churn.

## Ownership and cleanup

The fw4 table and base chains have `parent_owner=FW4`; OpenKill children have
`owner=OPENKILL`, `ownership=OWNED`, a component, a stable `logical_id`, and
the semantic-spec version.  The `OPENKILL_NFT_MANIFEST_V1` manifest contains
only those explicit owned entries.  A comment or a name pattern is diagnostic
only and is never sufficient for deletion.

Future cleanup is manifest-scoped.  It may remove an object only when its
logical ID and ownership metadata are in the manifest.  It must not flush a
ruleset/table, delete a foreign chain/set/rule/jump, or modify unrelated fw4
objects.  The design accepts a foreign object with an OpenKill-like physical
name and keeps it outside the manifest.

## Rules and components

Rules have stable logical IDs derived from the imported classifier precedence
table, not runtime handles.  The current profile records the known gaps rather
than hiding them: explicit direct/proxy policy is unresolved, current IPv6
TUN ingress remains the BC-04 gap, custom access retains its current position,
and China-pass is a fall-through rule.  A rule that is only a current gap is
marked `UNRESOLVED_SEMANTIC` and disabled in the abstract plan; no target
behavior is smuggled into current output.

The component set is `TOPOLOGY`, `LOCAL`, `NODE`, `CHINA`, `ACCESS`,
`SERVICE`, `DNS`, `PROXY_ACTION`, `WAN_INPUT`, `UPNP`, and `OWNER`.  The
dependency graph is:

```
TOPOLOGY -> NODE, LOCAL, CHINA, ACCESS, SERVICE, DNS, PROXY_ACTION
NODE     -> PROXY_ACTION
LOCAL    -> PROXY_ACTION
CHINA    -> PROXY_ACTION
ACCESS   -> PROXY_ACTION
SERVICE  -> PROXY_ACTION
DNS      -> DNS
OWNER    -> TOPOLOGY
```

The abstract `diff_ir()` reports `NO_CHANGE`, set-element changes, rule
changes, topology add/remove/change, component changes, and changed
components.  A node-only mutation therefore changes NODE sets only; local6,
China, ACL, and DNS state have their own component boundaries.  A run-mode
change can add TProxy topology and PROXY_ACTION rules.  An owner transition
removes OpenKill-owned desired objects from the IR and records an OWNER
component change; Phase 3A does not perform cleanup.

## Family, native routing, DNS, and underlay

NODE, LOCAL, SELF, REPLY, FAKEIP, CHINA, and DEFAULT are parity-required
semantics.  DHCPv6, ICMPv6 neighbor/control messages, PTB/errors, delegated
prefixes, and source-specific IPv6 behavior remain explicitly family-specific.

The IR only references the frozen mark ABI (`0x162`, full mask,
route table `354`, rule preference `1888`).  Direct/bypass remains native
routing.  TUN/TProxy actions carry a route dependency; they do not create a
route.  OpenWrt/netifd owns SLAAC, DHCPv6, PD, native addresses, and
source-specific routes.  The IR forbids a generic native IPv6 main-table
default and does not introduce NAT66.

DNS is an independent semantic entry with separate `DNS_LAN` and
`DNS_ROUTER` scopes.  Ordinary China or default rules cannot decide DNS
interception.  `SELF_TRAFFIC`, `NODE_ENDPOINT`, and `TUN_INGRESS` are kept as
distinct underlay loop-prevention reasons even when their outcome is native
bypass.

## Validation and determinism

`validate_ir()` rejects unknown versions, profiles, backends, object types,
components, actions, duplicate logical IDs, unresolved chain/set references,
unscoped foreign objects, missing manifest entries, and concrete backend
command syntax.  Target output requires an explicit preview flag.  The
serializer sorts mapping keys and preserves canonical list order, so equal
semantic state produces byte-identical JSON.  The validator also checks that
external priorities remain unverified and that the current `nat_output`
priority remains `-1`.

The Phase 3A test suite replays all 97 current classifier cases and all 109
shadow cases, checks the 32 overlap cases, current gaps, ownership and foreign
preservation, family/address normalization, component diffs, action
capabilities, determinism, and side-effect freedom.  The development
benchmark measures render and diff operations over 1,000 iterations; it is not
a production performance claim.

## Runtime boundary and Phase 3B

No production file is imported or edited.  The module uses in-memory state
only and does not call `nft`, `iptables`, `ip`, `uci`, `ubus`, dnsmasq,
Mihomo, or a shell.  There is no production renderer wiring, route writer,
watchdog writer, DNS change, or cleanup operation in Phase 3A.

Phase 3B may implement a deterministic syntax renderer:

```
NFT_IR_V1 -> nft syntax -> offline syntax validation
```

It should remain local and development-only, preserve the current profile by
default, compare abstract output to current intent, and still stop before
`set_firewall()` or any runtime writer.  Production shadow comparison and
controlled wiring are later, separately approved phases.
