# Phase 3E.2D2B semantic mismatch model

This phase adds a local, development-only semantic projection for the shadow
comparison.  It consumes the already captured legacy intent and the existing
CURRENT renderer intent.  It does not execute a command, read live state, or
write a device.

## Why the previous result was ambiguous

The original shadow comparison compared packet decisions and whole normalized
intent records.  A complete observation hash therefore changed when a legacy
WAN safety object was present, even though that object was outside the CURRENT
ownership contract.  The old comparison also had no typed representation for
the three DNS layers (firewall interception, dnsmasq, and Mihomo), so an
actual-versus-desired hash difference could not say whether it was a policy
difference or missing model data.

The D2B model keeps both hashes.  `observation_hash` is the complete bounded
semantic observation (including stable object payloads, with volatile handles
and counters removed) used for drift and safety diagnostics.  `owned_hash`
contains only
objects whose ownership is defined by the CURRENT contract.  The comparison
also exposes `actual_current_owned_hash` and `desired_current_owned_hash`,
which combine that object projection with typed DNS fields when DNS input is
provided; this is the hash used for the complete CURRENT-owned parity view.

## Ownership

Every object is resolved from explicit `semantic_ownership` metadata or an
audited inventory entry joined by logical or physical identity.  The model
recognizes `CURRENT_OWNED`, `LEGACY_ONLY_SAFETY`, `FW4_BASE`,
`CONDITIONAL_CURRENT`, `INACTIVE_MODE`, `OPTIONAL_OBSERVATION`, `OUT_OF_SCOPE`,
and `UNKNOWN`.

WAN input is classified from the formal `component`/`role` metadata
(`WAN_INPUT`), never from a list of physical names.  It remains in the
diagnostic observation with `OUT_OF_SCOPE_LEGACY_OBJECT` and can be observed as
either `OBSERVED` or `ABSENT`; it is excluded from CURRENT-owned equality.
Unknown or conflicting ownership remains a model gap.  A CURRENT-owned extra,
missing, or changed object remains a mismatch.  Conditional objects can be
marked active for a mode with `active_modes`/`required_modes`; inactive-mode
absence is retained without becoming an owned mismatch.
Reviewed `BC-01` through `BC-07` markers remain explicit
`KNOWN_CURRENT_GAP` results rather than being converted into a match.

## DNS fields

DNS is represented as independently typed fields:

* `DNS_FIREWALL_LAN_TARGET`
* `DNS_FIREWALL_ROUTER_TARGET`
* `DNSMASQ_LISTEN_TARGET`
* `DNSMASQ_UPSTREAM_TARGET`
* `MIHOMO_DNS_LISTENER`
* `DNS_LOOP_PREVENTION`
* `DNS_SCOPE_IPV4`
* `DNS_SCOPE_IPV6`

Firewall ports, dnsmasq upstream endpoints, and Mihomo listener endpoints are
validated separately.  A renderer `dns_port` is never inferred to be a
dnsmasq upstream or a Mihomo listener.  Consequently `53` and `7874` have no
direct or transitive equivalence.  A field without a formal owner/source is a
`COMPARATOR_MODEL_GAP`; missing evidence is `INSUFFICIENT_EVIDENCE`.  An
explicitly owned differing field is a `MISMATCH`.

The DNS fixture records the frozen `.102` actual path (`53` at the firewall and
dnsmasq listener, `127.0.0.1#7874` upstream, and `127.0.0.1:7874` Mihomo
listener).  The desired firewall targets come from the CURRENT renderer's
formal `DNS_REDIRECT` execution contract (`dns_port=7874`), while the desired
dnsmasq and Mihomo fields come from their committed state contracts.  The
result is therefore an attributable DNS mismatch on the two firewall target
fields; it is not a `53` to `7874` equivalence.  The comparison is reproducible
without a device or a live configuration read.

## Regression coverage

`scripts/test-shadow-semantic-model.py` covers ownership attribution, observed
and absent out-of-scope objects, active/inactive modes (including metadata-only
inventory entries), unknown and duplicate identity fail-closed behavior,
typed DNS mismatches and missing evidence, IPv6 endpoint canonicalization, hash
isolation, and ten deterministic runs of the frozen stable-mismatch fixture.
Existing D2A
coordinator, parser, renderer, continuity, and writer tests remain unchanged.

No renderer NFT payload, parser grammar, auto-state ABI, continuity algorithm,
coordinator capture classification, legacy writer, DNS writer, or device state
is changed by this phase.
