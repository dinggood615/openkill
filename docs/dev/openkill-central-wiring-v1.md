# OpenKill guarded central renderer wiring (development design)

This document records the Phase 3D design.  It does not add a production
flag, call a renderer from an init path, or apply an nft transaction.  The
machine-readable companion is
`scripts/fixtures/openkill-central-wiring-v1.json`, and the pure executable
checks are in `scripts/openkill_central_wiring_model.py`.

## Authority and modes

The production default remains `NFT_ENGINE=legacy` in design terms:
`LEGACY_AUTHORITATIVE` keeps the checked-in production generator as the only
writer.  `SHADOW_COMPARE` lets the new CURRENT renderer compute and compare a
desired result while the old generator continues to write.  `CENTRAL` is an
internal migration mode only; it may become `CENTRAL_ACTIVE` after an explicit
precheck and a writer handoff.  `target` is never a production profile.

The state machine is explicit:

```text
LEGACY_AUTHORITATIVE -> SHADOW_COMPARE -> CENTRAL_PRECHECK -> CENTRAL_ACTIVE
        ^                    |                  |                 |
        |                    v                  v                 v
        +-------------- LEGACY             BLOCKED            ROLLBACK
                                                               |
                                             +-----------------+
                                             v
                                      LEGACY_AUTHORITATIVE
```

Stable self-transitions are no-ops.  A direct legacy-to-central-active edge,
or any edge that skips precheck, is invalid.  Leaving central for legacy goes
through `ROLLBACK`, so the old writer cannot wake up while the central writer
is still active.

## Single writer

At most one implementation can mutate OpenKill's nft objects.  Legacy mode
has the old writer; shadow mode still has the old writer and the new side is
read/compare only.  Central mode first stops the old writer and only then
grants the central writer.  A stale worker is rejected with an activation
generation/token and the existing reconcile lock.  The watchdog and fw4
worker remain ineligible while they can write directly; the Phase 4 design
converts them to request-only observers.

## Eligibility

`CENTRAL_RENDERER_ELIGIBLE()` is all-or-nothing.  It requires an actual modern
fw4/nft backend, OpenKill ownership, CURRENT profile, known semantic/IR/state/
manifest versions, supported CURRENT state, valid configured listener ports,
exact mark ABI (`0x162`, `0xffffffff`, table `354`, preference `1888`), a
successful check of the exact apply payload, healthy runtime, no owner/fw4/
component/restart transition, no foreign name collision, no old writer, and a
ready manifest.  Active BC-07 ACCESS_DENY or an unresolved BC-01 explicit
policy blocks central.  The preserved IPv6 TUN gap (BC-04) is allowed only
when CURRENT parity is proven; it is not silently repaired.

Any missing, unknown, or malformed fact fails closed.  The old production
authority remains unchanged when precheck or nft check fails.

## Data and execution boundary

The future production path is:

```text
config/netifd -> snapshot -> normalized desired state -> semantic facts
    -> classifier(CURRENT) -> backend execution contract -> NFT IR
    -> production renderer -> checked apply payload
```

The renderer consumes this normalized boundary.  It does not read UCI/ubus,
resolve node domains, recalculate China sets, or infer DNS scope.  Listener
ports come from the same normalized state for old and new implementations.
The semantic decision stays `PROXY`; run mode, family, protocol, direction,
router-self scope, listener ports, and the frozen mark ABI select the backend
action.  UDP redirect and modern ACCESS_DENY remain explicit unsupported
paths, never silent downgrades.

The central NFT boundary covers DNS interception intent only.  LAN remains on
the proven `dstnat` path and router DNS on `nat_output`, with their scope and
`router_self_proxy` gates preserved.  dnsmasq and Mihomo DNS lifecycle is
outside this wiring design.  Route creation is owned by a separate route
component; the NFT plan may declare its dependency but never writes routes.

## Apply, ownership, and recovery

One future transaction prepares the desired state, validates versions and
eligibility, renders the canonical payload, checks that exact payload with
`nft -c`, derives an ownership-scoped plan, applies atomically where the
platform permits, verifies the owned runtime, and only then commits
`OPENKILL_NFT_MANIFEST_V1`.  `NFT_DESIRED_HASH` covers canonical semantic owned
state; `NFT_APPLY_PAYLOAD_HASH` covers the exact batch.  Neither includes a
timestamp, PID, random value, or temporary path, and the check/apply hashes
must match.

OpenKill does not own `inet fw4`; it owns only manifest-listed child chains,
sets, rules, jumps, and its current `nat_output` object.  Adoption of an
existing object is allowed only with proven provenance, type, and structure.
A same-name foreign object fails closed.  Cleanup is manifest/logical-ID
scoped and never flushes a ruleset/table or deletes foreign objects.

Destroy-and-rebuild is rejected because of interruption and rollback risk.
Side-by-side switching is deferred because only one attachment may be active
and the ownership transition is complex.  In-place reconciliation of proven
OpenKill-owned objects is recommended for the eventual current-profile
migration.

Precheck and nft-check failures leave runtime untouched.  Apply failure first
checks transaction atomicity; post-verify failure rolls back owned changes and
falls back to legacy.  Manifest commit failure freezes activation and enters
manifest recovery rather than blindly reapplying.  A fallback failure enters
`BLOCKED` with bounded escalation and no retry loop.

## Rollout boundary

The development Python renderer remains an oracle, not router runtime.  The
recommended implementation order is:

1. Build a small production shell renderer from the frozen semantic/action
   tables and validate it locally against the Python oracle.
2. Implement runtime shadow only; old production remains the authority and
   all mismatches lock central activation.
3. Add guarded apply after capability and ownership gates are independently
   approved.
4. Migrate steady-state, then stop/cleanup ownership in a separate step.

These are proposals for Phase 3E/Phase 4 and are not implemented here.
