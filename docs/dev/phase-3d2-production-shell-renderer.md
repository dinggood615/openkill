# Phase 3D.2 production-capable shell renderer candidate

`luci-app-openkill/root/usr/share/openkill/openkill_nft_renderer.sh` is an
unwired OpenWrt renderer candidate.  It is packaged with the application but
no init, network, watchdog, fw4 worker, DNS, route, or Mihomo path references
it.  The current production writer therefore remains unchanged.

The module is a POSIX `/bin/sh` library/CLI.  Its only public operation is
`openkill_render_nft_desired INPUT [OUTPUT]`.  It consumes
`SHELL_RENDERER_INPUT_V1` line-oriented records and writes a canonical nft
desired batch to stdout (or to the caller-provided output path).  It never
reads UCI, ubus, interfaces, node domains, or China files, and it never calls
`nft` or any firewall, network, service, or discovery command.  Its small set
of POSIX/BusyBox text utilities is used only to validate and sort input.  The
caller owns syntax checking and any future apply transaction.

The input boundary carries the already resolved CURRENT profile, owner, run
mode, listener ports, mark ABI, topology, dynamic sets, attachments, and
classifier action records.  The renderer validates versions, enums, names,
addresses, ports, action/transport combinations, and the frozen mark ABI:
`0x162`, mask `0xffffffff`, route table `354`, preference `1888`.  Unknown
versions, TARGET, UNKNOWN owner, malformed records, unresolved explicit policy,
modern ACCESS_DENY, and other unsupported CURRENT states fail closed before
any output is emitted.  No development fallback port is applied.

Before parsing the already bounded line-oriented input, the renderer performs
a byte preflight with `od -An -v -tx1` and rejects an actual `00` byte.  The
`-v` keeps `od` from folding repeated blocks, so every input byte is checked.
The text grammar is then checked with portable awk; it does not use awk `\xNN`
character escapes, whose meaning is not portable across BusyBox releases.
This keeps literal text such as the four characters `\x00` distinct from a
binary NUL while preserving the existing structural and ABI fail-closed
checks.  The preflight never stores input bytes in a shell variable.

The emitted batch references the external `inet fw4` table and existing fw4
base chains.  It declares only OpenKill-owned child chains and sets, emits
stable attachment/rule order, and contains no table/ruleset flush, delete,
foreign cleanup, or shell-evaluable text.  `nat_output` retains the CURRENT
owned `nat` output hook at priority `-1`; LAN DNS remains on `dstnat`, router
DNS on `nat_output`, and IPv6 TUN ingress preserves the recorded CURRENT gap.
Node, local, China, ACL, service, fake-IP, control, reply, and proxy actions
are consumed from upstream semantic records rather than reclassified here.

Set elements are de-duplicated and byte-stably sorted.  IPv6 WAN interface
addresses remain host values (never an interface `/64`), while delegated/LAN
prefixes retain their prefix length.  Empty sets are emitted without dummy
elements and may be referenced by always-present rules.

The development oracle and parity suite are in
`scripts/test-shell-renderer.py`; the machine-readable input contract is
`scripts/fixtures/openkill-shell-renderer-input-v1.json`.  The suite compares
120 supported CURRENT states to the Python NFT oracle, rejects the two UNKNOWN
owner fixtures, checks BusyBox-compatible POSIX syntax and applets, verifies
injection and unsupported-action handling, checks deterministic output and
component-local diffs, and runs every unique supported payload through local
`nft -c -f` only.  The Python implementation remains the CI/reference oracle;
no Python runtime dependency is added to OpenWrt.

`scripts/test-busybox-renderer-compatibility.py` is the focused portability
regression.  It forces BusyBox `awk`, `od`, `sed`, and `sort`, preserves a
pre-fix host-output golden comparison, rejects real NUL bytes at each input
boundary, treats literal `\x00` text according to the existing grammar, and
checks that malformed ABI values reach the original ABI guard.

This phase adds a production-capable package file while keeping
`PRODUCTION_RENDERER_CALLSITES=0`, `PRODUCTION_RUNTIME_BEHAVIOR_CHANGED=NO`,
and `DEVICE_CONNECTION=NO`.  Runtime shadow wiring requires a later approved
phase.
