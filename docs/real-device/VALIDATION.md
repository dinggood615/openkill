# Real-device validation

Device validation is a separate, explicitly approved activity. Local
development, RC builds, and formal release jobs must not connect to a router.

The approved test target for the completed 3E.2D work was `192.168.1.102` via
the `openkill-test-102` SSH alias. Other routers were out of scope. The device
evidence is historical input to the local migration plan, not a permission to
connect during ordinary work.

Frozen results include the Mark ABI (`fwmark=0x162`, `fwmask=0xffffffff`,
`route_table=354`, `rule_pref=1888`), coherent continuity snapshots, BusyBox
hexdump byte preflight, CURRENT rendering, bounded parser capture, and zero
write shadow checks. D2A classified conditional inventory absence correctly;
D2B separated ownership and DNS fields; D2C reconciled the mode-1 DNS path.

The D2D device run consumes the checked-in, secret-free fixture
`scripts/fixtures/3e2-safe.yaml`, verified by
`scripts/verify_3e2_safe_config.py`.  Its canonical SHA-256 is
`9cd8d91750758823776df9c982c1e15f0baa1a72baa1792fa2f82c0df4d24a6e`.
This provenance is a test-asset identity; it does not authorize device
access, central activation, or packet testing.  The fixture is restricted to
the approved `.102` shadow validation procedure.

Known gaps remain: full semantic device revalidation after D2C, any future
central writer handoff, and real packet-path testing. Do not infer those gates
from local fixtures or a successful package release.
