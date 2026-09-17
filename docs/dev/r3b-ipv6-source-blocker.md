# R3B IPv6 continuity source blocker

The R3B device evidence is a continuity failure before typed comparison, not a
DNS result. Three independent automatic coordinator runs returned `STALE`
(`rc=6`, `reason=automatic-state-source`) with the same fields differing:

* the applied state had `IPV6_PROXY_RULE=1` and `IPV6_TUN_ROUTE=1`, while the
  desired state had both values `0`;
* `LOCALNETWORK6_PREFIXES` differed between the two files;
* the live snapshot reported `LOCAL_IPV6_READY=1`.

The production source path is deterministic. `openkill_collect_network_snapshot`
derives `LOCAL_IPV6_READY` from native IPv6 readiness and records the current
WAN addresses. `openkill_build_desired_state` maps that snapshot to the IPv6
rule/route flags and normalized local prefixes. The init start path builds one
desired file before startup and, after readiness, commits that desired
generation to the applied file. The shadow coordinator copies both files into
one T0 continuity workspace and fails closed when the desired and applied
copies are not equal; it then rechecks the same sources at T1/T2.

This establishes a source-convergence contract mismatch on the device. The
available evidence does not establish whether the device retained a desired
file from an earlier non-ready generation, or whether a lifecycle boundary
generated the two files in a different order. The exact historical trigger is
therefore **UNRESOLVED**. Copying applied over desired, ignoring IPv6 fields, or
relaxing T0/T1/T2 would invalidate the contract and is not an acceptable fix.

`scripts/test-shadow-continuity.py` includes a three-attempt local fixture that
reproduces the same IPv6 desired/applied split and asserts `STALE` before the
renderer is invoked. No router, host network setting, writer, or production
continuity rule is changed by this fixture.

## Local source audit (2026-09-17)

The source chain was rechecked without device access. On startup,
`start_service()` waits for the WAN, calls
`openkill_collect_network_snapshot` once, and passes that immutable snapshot to
`openkill_build_desired_state`. `LOCAL_IPV6_READY` is derived from a native
IPv6 address plus a main-table default route; it controls
`IPV6_PROXY_RULE`/`IPV6_TUN_ROUTE`, while normalized internal and WAN host
prefixes become `LOCALNETWORK6_PREFIXES`. The readiness path later calls
`openkill_commit_applied_network_state` and copies the selected desired file
to `/tmp/openkill-network.applied` only after process, TUN, DNS and firewall
checks succeed. Reloads use a token-scoped snapshot and desired path and run
the same model before deciding whether to reconcile.

This proves the production functions and call order, but it does not prove
which historical generation created the `.102` files. A stale desired file,
an earlier failed generation, or a readiness boundary between two snapshots
can all leave the observed applied/desired split. The saved device evidence
does not include the generation token and source snapshots needed to choose
between those explanations. No local code change can safely select one. The
minimum next device evidence is a read-only capture of both files, their
modification times, `/tmp/openkill-start.token` and `/tmp/openkill-ready.token`,
the current `LOCAL_IPV6_READY` snapshot, and the service log lines around the
last readiness commit. Until those values share one generation, the
continuity gate remains authoritative and `DEVICE_RETRY_READY=NO`.
