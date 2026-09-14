# Phase 3E.2C1 real nft parser hardening

This local-only change extends the production-capable read-only capture parser
for the three current nft forms recorded during the 3E.2C device baseline. The
sanitized transcript is
`scripts/fixtures/openkill-legacy-runtime-capture-device-3e2c-v1.txt` and is
marked `DEVICE_CAPTURE_FIXTURE_SOURCE=192.168.1.102_PHASE_3E2C`.

`nat_output` accepts only the current `type nat hook output priority`
expression (`-1`, `filter -1`, `filter-1`, or the whitespace-equivalent
`filter - 1`) and an optional `policy accept`. The symbolic fw4 priority is
normalized to numeric `-1` in the existing `LEGACY_RUNTIME_INTENT_V1` hook
record. The declaration is chain metadata, never a packet rule; `policy accept`
is validated as the current default and is not emitted as a separate packet
operation.

The parser accepts a numeric `th/tcp/udp dport { ... }` set followed by a plain
`reject` only in the frozen `openkill_wan_input` chain. In
`openkill_wan6_input` it additionally requires the current `ip6 nexthdr {
tcp, udp }` qualifier and the exact `reject with icmpv6 port-unreachable`
verdict. Ports are validated, sorted, and deduplicated for semantic stability;
rule order remains unchanged. Handles, counters, and quoted diagnostic comments
remain outside the intent hash.

Any other owned-chain declaration, reject subtype, multiport form, or match is
reported as `CAPTURE_UNSUPPORTED`. Foreign rules in fw4 base chains remain
ignored and are never adopted by name or comment. The parser invokes no device
or mutation command; the fixture tests run locally through the same `/bin/sh`
entry point used by the read-only shadow helper.
