# Test gates

OpenKill uses one local executor for the validation matrix:

```text
python scripts/openkill-test-gates.py fast
python scripts/openkill-test-gates.py full --no-cache
python scripts/openkill-test-gates.py device-preflight --no-cache
```

The executor runs every case independently, records its return code, and
fails the mode when any required case fails. A later successful case cannot
hide an earlier failure. Each run writes a bounded, local-only evidence bundle
under `artifacts/test-evidence/<run-id>/`:

```text
summary.json  summary.txt  environment.txt  hashes.txt
tests.tsv     skips.tsv    candidate-manifest.json  network-guard.json
```

The directory is ignored by Git. The evidence key for each case includes the
case source, the OpenKill production observer/renderer and fixtures it can
consume, the runner version and source hash, interpreter/platform versions,
command, environment and the case's allowed skip policy. Fast mode may reuse a matching
allowed result from the cache; `full` and `device-preflight` always execute
their cases again. A changed input
therefore invalidates only the affected evidence rather than relying on a
commit id alone. Every case receives a unique run token and executes with an
owned process boundary. Native timeouts terminate the exact PID tree; WSL
invocations also leave a token-scoped marker and verify token-owned Linux
descendants after cleanup. The evidence records the PID, cleanup status and
orphan count. A timeout or orphan is always a failure, and no unrelated
process is selected by name.

The runner records a read-only host-network snapshot before the suite and
after each case. Default routes, DNS, proxy settings, adapter state, listening
endpoints and the list of already-running WSL instances are hashed so
sensitive values are not printed. An unexplained change aborts the remaining
cases; no automatic network repair is attempted. Starting a stopped WSL distro
may change its virtual adapter and inventory for that WSL case; a host listener
change remains unexpected and fails the suite.

`fast` is the short feedback loop. It runs the policy checks, compile and diff
checks, canonical configuration, UCI lifecycle, typed producer/shadow,
semantic model, and production-shadow writer-freeze suites. Continuity and
the slower self-sufficiency replay remain in the full and device-preflight
modes. Process ownership, runner classification and the no-network Core
contract run before WSL bootstrap so local failures are found early.

The fast suite also runs `scripts/test-ui-contract.py` and
`scripts/test-ui-preview.py`. The contract check verifies cache-busting,
DOM hooks, explicit running/stopped/disabled/unknown/error state handling and
accessible controls. The preview check builds a local page from the real
status and IP templates and production CSS, then verifies the local-only
fixture contains no LuCI template expressions or external URLs. It does not
claim a live LuCI backend or device result. A browser pass, when Chrome is
available, is run by `scripts/test-ui-browser.py` as part of the same unified
gate. It loads the production template, CSS, `SettingsManager` and
`ConfigFileManager` visibility method, then exercises request races, label
clicks, hidden-child focus recovery and 1920/1366/768/390 CSS-pixel layouts
against an in-page mock backend. Every request is constrained to the local
preview server; console errors, page errors, overflow and external requests
fail the case. Missing Playwright or a browser is reported as the explicit
`PLAYWRIGHT_UNAVAILABLE`/`PLAYWRIGHT_BROWSER_UNAVAILABLE` environment result,
never as a generic pass.

The same UI contract now covers the conditional controls that share the
status-page interaction pattern: the custom CDN row in `update.htm`, the
privacy and mode icons in `myip.htm`, the legacy merge editor tabs/help
panels, the log-source tabs, settings cards/search results, dynamic CBI table
tabs in `tblsection.htm`, and subscription summaries in `sub_info_show.htm`.
Their visibility changes update native `hidden`, `aria-hidden`, focus and
selection state together; source-level regressions are intentionally kept in
the unified UI contract suite when a full LuCI backend is unavailable.
The browser interaction probe also exercises the overwrite editor's exclusive
config selection and verifies that its list-level drag/touch listeners are
bound once across card rerenders. Resetting upload options is checked to move
the age-encryption group back to its owning mode before the next edit.

`full` runs the complete local matrix. Fixture suites run with the native
Windows interpreter, while runtime, installer, network, snapshot/FW4, Stage D
and Mihomo compatibility suites run in WSL. The runner selects that
environment itself; it does not depend on a developer guessing which shell to
use. The `nft` CLI case is reported as `NOT_RUN_ENVIRONMENT` with reason
`NFT_CLI_UNAVAILABLE` when the host does not provide the binary. Ruby-dependent
tests retain their documented `RUBY_UNAVAILABLE` skip. WSL absence is reported
as `SKIP_ALLOWED` with reason `WSL_UNAVAILABLE`. The Mihomo release-download
cases additionally use `CORE_RELEASE_UNAVAILABLE` only when `test-core.py`
emits its explicit `OPENKILL_ENVIRONMENT_LIMIT=CORE_RELEASE_UNAVAILABLE`
marker for a transport failure. A generic traceback (including `urlopen
error`), checksum failure, assertion failure or timeout is a required failure.
Cache hits retain the original skip reason and evidence path and never convert
an unexecuted check into a fresh execution.

Because the compatible Mihomo Core is required evidence for a complete
candidate, a `CORE_RELEASE_UNAVAILABLE` result makes `full` and
`device-preflight` fail closed; it is reported with its explicit reason and
must not be turned into device readiness.

`device-preflight` is still completely local. It repeats the source,
canonical-config, staged-observer, internal-sidecar, provenance, continuity,
writer-freeze and semantic replay checks needed before a future `.102` phase.
Its `DEVICE_PREFLIGHT=PASS` and `DEVICE_RETRY_READY=YES` output never contacts
or probes a router. The staged observer test copies the candidate observer,
renderer and semantic templates into a private directory, records their
identity, and executes that copy for five independent automatic cycles. No
typed sidecar, Python oracle, or repository fallback is permitted.

The canonical D2D fixture and verifier are
[`scripts/fixtures/3e2-safe.yaml`](../../scripts/fixtures/3e2-safe.yaml) and
[`scripts/verify_3e2_safe_config.py`](../../scripts/verify_3e2_safe_config.py).
They validate the frozen D2C DNS contract, the independent 53/7874 fields, the
Mark ABI, determinism and secret absence without contacting a device.

The shell scripts retain narrower names for compatibility:

- `local-gate.sh` reports `LOCAL_POLICY_GATE=PASS`; it is a policy/preflight
  gate and does not claim to be the complete matrix.
- `ci-gate.sh` reports `CI_WORKFLOW_SEPARATION_GATE=PASS`; this is the local
  workflow separation check and does not claim that GitHub CI ran.

Development CI remains push/PR driven and never publishes. RC and formal
release workflows remain manual and separately gated. This local work package
does not enable central apply, install a package, access a router, or run a
packet-path test.
