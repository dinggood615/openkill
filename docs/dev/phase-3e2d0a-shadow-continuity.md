# Phase 3E.2D0A shadow continuity contract

This phase replaces the test-only reconcile generation file with a
content-derived continuity token.  The legacy OpenKill writer and reconcile
lifecycle remain unchanged; the shadow remains opt-in and read-only.

## Frozen generation diagnosis

`/tmp/openkill-network-reconcile/generation` is a development artifact created
by `openkill_generation_start` for development tests.  No production start,
reload, reconcile, writer, or shadow reader creates or requires it.  The
automatic runtime path therefore never falls back to that file.  An explicit
`OPENKILL_NFT_SHADOW_GENERATION_FILE` is retained only for the versioned test
bundle protocol.

## Production source map

The automatic producer reads the normalized desired/applied state files and
its already-populated control-plane variables.  Its fixed source map is:

| Field group | Primary source | Required | Token component |
| --- | --- | --- | --- |
| owner, run mode, router self proxy | committed state aliases, then normalized process variables | owner/mode required for OpenKill | state plus `shell_scalars` |
| redirect, TProxy, DNS ports | committed state aliases, then normalized process variables | required | state plus `shell_scalars` |
| mark, mask, route table, rule preference | committed state aliases, then frozen process ABI variables | required | state plus `shell_scalars` |
| local, LAN, delegated, WAN, fake-IP, China and ACL sets | desired state, then applied/snapshot aliases | conditional by current contract | state hash |
| node4/node6 endpoints | fixed desired endpoint files, with committed-state aliases as fallback | conditional when empty | `node4`/`node6` |
| IPv6 readiness and unsupported-current facts | committed state aliases or normalized process facts | readiness/facts are validated | state plus `shell_scalars` |
| `config.applied` | not read by the current automatic producer | diagnostic only | excluded |

The helper does not call UCI, ubus, `ip`, DNS resolution, China source
parsing, or node discovery.  Aliases are checked for conflicting values and
missing required values fail closed.

The production `/tmp/openkill-network.fingerprint` remains a useful native
network fingerprint, but it covers only network roles, addresses, native
routes, DNS servers, readiness and TUN owner.  It does not cover all shadow
inputs such as desired/applied policy sets, listener ports or ACLs, so it is
`EXISTING_FINGERPRINT_PARTIAL` and is not used as the continuity token.

## `SHADOW_CONTINUITY_TOKEN_V1`

The token is the SHA-256 of a fixed-order component record:

```
SHADOW_CONTINUITY_TOKEN_V1=1
profile<TAB>PRESENT<TAB>current
desired<TAB>PRESENT|ABSENT_ALLOWED<TAB>canonical-content-sha256
applied<TAB>PRESENT<TAB>canonical-content-sha256
snapshot<TAB>PRESENT|ABSENT_ALLOWED<TAB>canonical-content-sha256
node4<TAB>PRESENT|ABSENT_ALLOWED<TAB>canonical-content-sha256
node6<TAB>PRESENT|ABSENT_ALLOWED<TAB>canonical-content-sha256
shell_scalars<TAB>PRESENT<TAB>canonical-scalar-sha256
```

State keys are allow-listed.  Set-like values are whitespace/comma
canonicalized, sorted and deduplicated; source record order, mtimes, clocks,
PIDs, counters, nft handles, locks, logs and telemetry are excluded.  Missing
optional sources are represented explicitly as `ABSENT_ALLOWED`, while a
missing applied state is `INPUT_SOURCE_GAP`.

A coherent automatic run computes `T0`, copies the fixed source files into a
private mode-0700 snapshot (files mode 0600), then computes `T1`.  A mismatch
returns `STALE` before rendering.  The renderer consumes only those private
copies.  After capture/render/compare, the live sources are hashed as `T2`;
`T1 != T2` always wins over a provisional result and publishes `STALE`.
Desired/applied divergence is also fail-closed before rendering.

The token protects control-plane state continuity; it does not replace source
code drift checks or the bounded read-only legacy nft capture.  Telemetry keeps
only short hashes and status.  The existing `generation=` field remains for
wire compatibility and carries the short continuity token on the automatic
path; `continuity_token=` is additive.

## Runtime boundaries

With `OPENKILL_NFT_SHADOW` unset or `0`, the helper returns before calculating a
token, copying state, reading nft, invoking the renderer, or writing
telemetry.  With the flag enabled, it performs only state reads, bounded
canonicalization, and the existing read-only capture; it never mutates nft,
routes, DNS, services, or the legacy writer return value.  Python remains a
development oracle and is not a runtime dependency.

The test-only generation helper remains available to the older explicit bundle
fixtures, but it is not a production ABI and cannot affect an automatic token.
