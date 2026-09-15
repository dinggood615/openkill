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

Known gaps remain: full semantic device revalidation after D2C, any future
central writer handoff, and real packet-path testing. Do not infer those gates
from local fixtures or a successful package release.
