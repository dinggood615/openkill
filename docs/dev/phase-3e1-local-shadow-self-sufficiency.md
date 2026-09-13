# Phase 3E.1 local shadow self-sufficiency

This note describes the read-only path added for the 3E.1 gate.  The legacy
OpenKill writer remains the only dataplane writer.  When
`OPENKILL_NFT_SHADOW` is unset or `0`, the observer returns before reading
state, invoking the renderer, invoking `nft`, or writing telemetry.

## Automatic input

`openkill_shadow_build_auto_input` produces the existing
`SHELL_RENDERER_INPUT_V1=1` protocol.  A canonical line-oriented source may be
provided with `OPENKILL_NFT_SHADOW_SOURCE_FILE` (the test fixture is
`scripts/fixtures/openkill-shadow-auto-state-v1.txt`).  In an OpenWrt process
the same function reads the committed desired/applied/snapshot files and the
already-populated control-plane variables.  It never calls `uci`, `ubus`,
`ip`, DNS tools, or a node/China discovery path.

The source map is recorded in
`scripts/fixtures/openkill-shadow-self-sufficiency-v1.json`.  A field has one
primary source, explicit aliases are checked for conflicting values, and
missing required values return `INPUT_SOURCE_GAP`.  `CURRENT_UNDEFINED`,
`BC01_UNSUPPORTED`, and `BC07_UNSUPPORTED` facts are rejected before rendering;
ordinary `ACCESS*_DENY` sets are not treated as BC-07 flags.  `MIHOMO` and
`DISABLED` are an explicit no-owner result and produce no OpenKill topology.

Static topology is kept in the package data files
`/usr/share/openkill/shadow/input_{tun,tproxy,redirect}_v1.tsv`.  The producer
only substitutes validated metadata and normalized dynamic set contents, so a
node or local-set change does not rebuild unrelated topology.  The files are
not test scaffolds and contain no `TEST_ONLY` or fake fw4 declaration.

## Actual legacy capture

`openkill_shadow_capture_legacy_nft` performs a bounded read of known fw4 base
chains, OpenKill-owned chains, and OpenKill-owned sets.  Its only nft forms are
`nft list chain inet fw4 <known-name>` and `nft list set inet fw4 <known-name>`.
The optional `OPENKILL_NFT_SHADOW_CAPTURE_FIXTURE` is a test-only transcript
hook; the production path uses the local `nft` binary.  Missing required
objects, malformed output, or an unknown rule in an OpenKill-owned chain fail
closed as `CAPTURE_ERROR`/`CAPTURE_UNSUPPORTED`.  Foreign base-chain rules are
ignored without being claimed, and a same-name object is never adopted by
comment matching.

`openkill_shadow_parse_nft_capture` emits `LEGACY_RUNTIME_INTENT_V1=1` and a
canonical comparison payload.  It preserves rule order, sorts/deduplicates
set elements, and excludes handles, counters, and diagnostic comments from
the semantic comparison.  `nat_output` is recognized with its current
`type nat hook output priority -1` declaration.  The parser is deliberately a
finite parser for the current inventory; an unrecognized owned expression is
not silently discarded.

## Runtime flow and safety

With shadow enabled, the coordinator builds the input, captures the legacy
actual state, renders the current desired state, compares both projections,
and performs a second generation read.  A generation change returns `STALE`.
Capture, input, and renderer failures publish additive status values and do
not replace the old writer's return code.  Telemetry contains only bounded
hashes, counts/status, and generation; endpoint, LAN, and MAC values are not
written to the status or mismatch key.

The helper has no Python dependency and no production central-write callsite.
It never executes an nft mutation verb.  The only filesystem writes are the
caller-provided temporary comparison files and the existing mode-0700,
atomic shadow telemetry directory.

## Local evidence

The fixture suite covers automatic input, source conflicts and unsupported
current facts, bounded list-only capture, foreign and unknown-owned rules,
actual mark/node/DNS/order mismatches, owner skip, stale generation, and the
default-off zero-read path.  It also runs 1,000 deterministic producer
serializations for the no-owner path plus rich-state smoke iterations, and
checks reordered set input for byte stability.  The source-derived capture
fixture `openkill-legacy-runtime-capture-production-v1.txt` is marked as
coming from the Phase 3C exact production generator; it is not reverse-built
from the desired renderer output.

No production writer, watchdog, fw4 worker, route/rule, DNS lifecycle, or
Mihomo runtime file is changed by this phase.  Device access is prohibited.
