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
