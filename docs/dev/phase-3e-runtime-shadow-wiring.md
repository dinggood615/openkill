# Phase 3E runtime shadow wiring

Phase 3E adds a read-only observer around the already authoritative OpenKill
control path.  The observer is a migration aid: it computes a CURRENT-profile
desired nft payload with the production-capable shell renderer and compares it
with the normalized intent captured from the old writer.  It never becomes a
writer, and it does not select policy, routes, DNS configuration, or service
lifecycle actions.

The call is at the end of `check_core_status()`, after the legacy firewall and
route work, runtime checks, applied-state commits, readiness token, and quick
state have completed.  The same coordinator is also called immediately before
the two healthy `reload_service()` NO_ACTION returns, while the normalized
transaction files are still available.  Each call is deliberately wrapped as
`openkill_shadow_compare_nft || true`, with the preceding legacy return code
captured and returned afterwards; every legacy return value and failure path
therefore remains unchanged.  Stop, watchdog, and fw4-reload helpers are not
connected.

## Runtime boundary

The coordinator is
`luci-app-openkill/root/usr/share/openkill/openkill_nft_shadow.sh`.  It is
sourceable by `/bin/sh` and invokes the shell renderer only after a caller has
set the internal gate `OPENKILL_NFT_SHADOW=1`.  The default is disabled and no
ordinary UCI or LuCI option enables it.  A missing state bundle is an
`INPUT_ERROR`, so enabling the observer cannot cause it to invent state.

The state bundle is a small key/value file:

```text
OPENKILL_SHADOW_STATE_V1=1
INPUT_FILE=/tmp/openkill-shadow/input.tsv
OLD_INTENT_FILE=/tmp/openkill-shadow/old-intent.nft
GENERATION_FILE=/tmp/openkill-shadow/generation
SOURCE_HASH_FILE=/tmp/openkill-shadow/source.sha256
BASELINE_HASH_FILE=/tmp/openkill-shadow/baseline.sha256
```

`INPUT_FILE` must contain the existing `SHELL_RENDERER_INPUT_V1` normalized
line format with `profile=current`.  The coordinator does not rediscover
interfaces, parse subscriptions, resolve node domains, or read policy sources.
Listener ports, ownership, dynamic sets, execution actions, and generation are
therefore supplied by the control-plane normalized state producer.  The old
intent is either a canonical capture file or a previously computed canonical
hash.  Source hash files are optional until a migration baseline is installed;
when either side is explicitly supplied, both must match or the comparison is
`SOURCE_DRIFT`.

The observer captures generation **G**, copies and validates the normalized
input, renders into a temporary file, canonicalizes declarations while
preserving per-chain rule order, compares the old and new intent, then reads
the generation again.  A changed or missing generation is `STALE` and can
never be reported as `MATCH`.  Renderer execution is bounded by the local
`timeout` utility; an unavailable timeout or a timeout result is a compare
error.  The historical rc.common descriptor is closed in a BusyBox ash child
when that shell supports the numeric descriptor syntax; Debian dash is probed
in a separate child and uses the safe no-close fallback.

## Status and telemetry

The status vocabulary is versioned by
`scripts/fixtures/openkill-runtime-shadow-v1.json`:

`MATCH`, `KNOWN_CURRENT_GAP`, `UNSUPPORTED_CURRENT_STATE`, `MISMATCH`,
`INPUT_ERROR`, `RENDER_ERROR`, `COMPARE_ERROR`, `SOURCE_DRIFT`, `DISABLED`, and
`STALE`.

Telemetry is written atomically under `/tmp/openkill-shadow` (or an internal
test directory) with mode `0700`.  It contains only protocol/profile/renderer
version, status, short hashes, generation, reason, and a mismatch count.
`last_mismatch` is a bounded dedupe key; payloads, address lists, node domains,
subscriptions, and credentials are never logged or persisted.  Telemetry is
evidence only and is not an applied-state checkpoint.

The observer has no runtime firewall, route, DNS, service, or network side
effects.  In particular it does not execute an nft transaction or a route
command.  Development and CI continue to use the existing real parser gate;
the production shadow path compares intent without running that parser on
every reconcile.

## Failure isolation and rollout boundary

The old production implementation remains the sole dataplane writer.  Shadow
failure, an unsupported CURRENT case (including unresolved explicit policy or
BC-07 access-deny), source drift, stale input, or a mismatch records telemetry
and leaves the old operation authoritative.  The coordinator has no central
mode and cannot enable target behavior.  BC-01 and BC-03 through BC-07 remain
unapproved; BC-02 remains the observed `NODE > ACCESS` baseline correction.

The local harness in `scripts/test-runtime-shadow.py` covers disabled, match,
renderer/input errors, mismatch, BC-01/BC-07 rejection, source drift, stale
generation, Mihomo/disabled ownership, NO_ACTION, old-writer failure and return
code preservation, reload success, repeated mismatch dedupe, timeout, source
hash drift, syntax, and callsite scans.  It runs the helper in WSL with fixture
files only.  It does not contact a device.

Phase 3E is not central activation, packet-path validation, or device
validation.  A later phase must first provide a production normalized-state
producer and a native/BusyBox implementation of that producer, then exercise
the shadow mode on an approved environment while the old writer remains
authoritative.  No target profile or central writer may be introduced by this
phase.
