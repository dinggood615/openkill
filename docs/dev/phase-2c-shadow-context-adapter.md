# Phase 2C shadow context adapter

The files in this note are development-only fixtures and an oracle for the
shared classifier contract.  They do not run on OpenWrt and are not imported
by the OpenKill init script.

`openkill_shadow_adapter.py` accepts a normalized, versioned state and a
synthetic packet descriptor.  It canonicalizes addresses, CIDRs, sets, and
enums, then reports observable facts such as set membership, direction,
owner, service, control protocol, and reply state.  It never selects a
precedence rule or emits backend syntax.  `build_context()` converts those
facts into the Phase 2B `PacketContext`; `shadow_compare()` is the only
development helper that invokes the current classifier oracle.

The state fixture is `scripts/fixtures/openkill-shadow-states-v1.json` and the
independent current intent oracle is
`scripts/fixtures/openkill-current-firewall-intent-v1.json`.  The latter
contains an audited expected result, evidence reference, and confidence for
each case; replay does not generate its expectation from the adapter or
classifier.  Target-profile output is available only through
`preview_target()` and is diagnostic.

Run the focused checks with:

```text
python scripts/test-shadow-context-adapter.py
python scripts/benchmark-shadow-adapter.py
```

The benchmark reports development-tool timings only.  No production nft,
iptables, route, DNS, watchdog, or Mihomo path is wired to this module.
