# Phase 3C production versus renderer shadow comparison

Phase 3C compares the checked-out modern firewall generator with the
development `NFT_IR_V1` renderer.  It is a local, record-only audit.  The
production shell functions are extracted from the current source at test time;
they are not copied into the test and are never sourced as an init script.

```text
checked-out shell function
        -> disposable Bash sandbox
        -> fail-closed command recorder
        -> old add/insert/flush normalizer

normalized state -> current classifier/IR -> current NFT renderer

old normalized intent + new normalized intent -> semantic comparison
```

The sandbox supplies fixture values for the state reads.  `nft`, iptables,
ipset, UCI, ubus, `ip`, fw4, service, process and filesystem commands are
record-only stubs.  An unrecognised command is recorded as an error and the
harness fails; no command is allowed to reach the host or an OpenWrt device.
The only files created by the harness are disposable files below its temporary
directory.  Custom firewall hooks are represented by an empty external hook;
their arbitrary contents are not treated as OpenKill-owned intent.

The old normalizer models the final rule list, including the important nft
semantics that `insert rule` without a position inserts at the front, while
`add rule` appends.  Flushes clear the simulated chain or set.  Comparisons
therefore use final logical order rather than command-log order or runtime
handles.  Set elements are canonicalized, and actions are mapped to the
backend-neutral vocabulary (`RETURN_NATIVE`, `PROXY_MARK`, `TPROXY_PROXY`,
`REDIRECT_PROXY`, and DNS redirect intent).

The comparison baseline is independently anchored by
`openkill-current-firewall-intent-v1.json`; the new classifier is not used to
manufacture the old expected result.  The source hashes recorded by the 3C
tests are:

| Function | Source | SHA-256 |
| --- | --- | --- |
| `set_firewall` | `luci-app-openkill/root/etc/init.d/openkill` | `00d1ea473c7d9096e60b99316deeb209376ac88236a5aa00977affde5a0dad17` |
| `apply_node_endpoint_sets` | same | `6cb03454c06772265c887aac10afc66dbb947fce0b76c8d933dd18238a218617` |
| `fw4_has_dns_hijack_rule` | same | `e175ab7a7ed628f5694594ef456605762d374adec1f4ca4fdecd4a6861791c0e` |
| `fw4_dns_hijack_ready` | same | `d1937fd74d49645e4cf68a0ec98d757e319022a26ba67475c34d278bb270f776` |
| `load_ip_route_pass` | same | `3b5a265ec4ac4251719b6a0b2627df6334ee5c5553cabd037649bc07f682019a` |
| `change_dnsmasq` | same | `16e2846ddde3eb67086e8dd53280b88b1bf805cfeebe7f928305e80ce3fa4a6d` |
| `openkill_render_dns_set_rules` | `luci-app-openkill/root/usr/share/openkill/openkill_network.sh` | `283ea49e0cb94d08baf9513b2d28e645822c4e1a978cb743dec43e347fd113b0` |

The audit deliberately reports a current discrepancy instead of changing the
Phase 2 contract.  In the two access-plus-node overlap cases, the extracted
production function emits the node-underlay rule with `insert rule` after the
firewall rules have been built.  The simulated final order is therefore
`NODE_ENDPOINT` before `ACCESS_CONTROL`.  The independently reviewed current
fixture says `ACCESS_CONTROL` wins for these cases, while the current central
renderer follows that fixture.  They are reported as two
`SEMANTIC_MISMATCH` results with `BC-02` and
`PRODUCTION_BUG_CANDIDATE` evidence.  This is an unresolved production/spec
decision; it is not reclassified as a target change or hidden as a structural
difference.

DNS scope is checked using complete packet-scoped intent.  LAN and router
paths now have different physical attachments in the development renderer:
LAN uses the prerouting mangle/DNS-LAN path and router output uses the output
mangle/DNS-router path, for both families.  The equal hashes observed in the
earlier syntax phase came from hashing a scope-free fragment; they did not
prove equal packet scope.  Phase 3C records the physical paths explicitly.

The transport audit also compares the final reachable path for each TPROXY
probe.  It found eight current-profile mismatches.  The production fixture
uses a 7893 TPROXY listener (and a 7892 TCP redirect in the mixed TPROXY
branch), while the development renderer uses its 12345 development default;
the production IPv4 LAN TCP probe follows the redirect chain, and the
production TPROXY fixture has no router-output attachment.  These are reported
as `SEMANTIC_MISMATCH` with `dimension=proxy_action`; no port, protocol, or
attachment was silently normalized away.  The normalized state schema does not
yet carry proxy listener ports, so this remains a production-neutral design
gap for a later approval rather than a renderer or production fix in 3C.

The comparison remains `profile=current`; target rendering is diagnostic only.
BC-01 through BC-07 remain `PRODUCTION_NOT_APPROVED`.  A future Phase 3D must
first resolve the BC-02 and TPROXY action discrepancies (and review the
remaining documented cleanup and external-fw4 risks) before any production
wiring is considered.
