# Release gates

Release is an explicit, reviewable operation.

1. Start from a clean branch and run `sh scripts/local-gate.sh`.
2. Confirm the source, installer, and README versions are identical.
3. Change the version only as part of the reviewed release commit; ordinary
   pushes must not bump it or publish anything.
4. Dispatch `OpenKill Formal Release` with `release_gate=true` and
   `publish=true`.
5. Require the version-bump check, runtime compatibility matrix, package
   audit, artifact upload and publication to pass. Preserve existing releases
   and tags. Version-specific notes under `docs/release/notes/` are mandatory
   and must disclose device verification gaps before publication.
6. Verify the published IPK and package-channel metadata, then record the
   release tag and digest in the execution plan.

The formal workflow has no push trigger. RC artifacts come from the separate
manual SDK audit and are never promoted automatically. Device installation,
central apply, and packet-path validation are separate approvals.

## Recovered 2026-1127 incident

The former push-triggered release workflow published `v2026-1127-ipk` while
the source was being repaired. The artifact is retained as historical evidence;
the workflow is now manual and release-gated so development pushes cannot
repeat that behavior.
