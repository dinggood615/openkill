# Phase 3B development NFT syntax renderer

Phase 3B adds a development-only lowering path:

```text
NFT_IR_V1 -> structured NFT AST -> deterministic nft text
                         -> offline safety checks -> optional nft -c
```

The implementation is in `scripts/openkill_nft_syntax.py`.  It consumes the
validated IR from `openkill_nft_ir.py`; it does not import an init script,
read UCI/ubus, invoke a network command, or mutate a ruleset.  The helper
`openkill_nft_check.py` is deliberately separate and is the only code allowed
to start a process.  Its argument vector is exactly `nft -c -f <temporary>`.
`nft -f`, `nft add`, `nft insert`, `nft delete`, and `nft flush` are never used.

## Version and profile locks

The syntax AST is `OPENKILL_NFT_AST_V1` and carries
`NFT_SYNTAX_VERSION=1`, semantic/classifier/IR versions, the ownership
manifest version, and Mark ABI v1 (`0x162`, full mask, table 354, preference
1888).  The parent `inet fw4` table and fw4 base chains are references owned by
FW4.  Current `nat_output` remains the one source-audited OpenKill base chain
(`type nat hook output priority -1`).  FW4 priorities other than that chain
remain `EXTERNAL_UNVERIFIED`.

`current` is the default and is the only production-compatible profile.  The
target profile requires the explicit development preview flag in
`render-openkill-nft.py` and is marked `DEVELOPMENT_TARGET_PREVIEW
NOT_FOR_PRODUCTION`.  BC-01 through BC-07 remain locked and are not applied.
The current IPv6 TUN gap is therefore preserved, and an unapproved
`ACCESS_DENY_REQUIRED` action is rejected instead of being guessed as DROP or
REJECT.

## Objects, ownership, and cleanup

The AST contains external references, owned chain declarations, dynamic sets,
attachment rules, and lowered rules.  Every emitted object has a stable
logical ID, component, owner, and source rule ID.  The development manifest is
bidirectional with emitted owned objects.  It is not a runtime manifest.

No parent table declaration, flush, foreign deletion, or broad name scan is
generated.  Same-name foreign objects remain outside the manifest.  A future
cleanup implementation must consume this ownership manifest rather than
comments or name patterns alone.

The Phase 3A `DNS -> DNS` notation is treated as a self-contained component.
The renderer audit removes that self-edge for graph traversal and records it
in `self_contained_components`, so the planning graph is acyclic without
changing packet semantics.

## Lowering rules

Semantic precedence and decisions come from the IR.  The syntax layer only
lowers them:

| IR action | Development syntax |
| --- | --- |
| `RETURN_NATIVE` | `return` |
| `MARK_PROXY` | `meta mark set 0x162` |
| `TPROXY_PROXY` | TProxy plus the development placeholder port 12345 and Mark ABI v1 |
| `REDIRECT_PROXY` | TCP redirect to development placeholder port 12345 |
| `DNS_REDIRECT` | jump to the owned LAN/router DNS scope chain |
| `JUMP` | jump to an owned chain |
| `CONTINUE_POLICY` / unresolved action | counter-only fall-through |
| `ACCESS_DENY_REQUIRED` | rejected until a verdict is approved |
| `UNSUPPORTED_ACTION` | rejected before any parser invocation |

Redirect plus UDP is always rejected.  Route and rule creation are not emitted;
proxy actions only carry a `requires_policy_route` metadata flag.  IPv6 WAN
addresses are rendered as host `/128` elements, while LAN and delegated
prefixes retain their prefix length.  Elements are canonicalized, deduplicated
and sorted.  Empty sets remain declared so a static rule can safely reference
them.

Rules are ordered by the precedence index supplied by the IR, then by stable
logical ID.  The renderer does not contain a second China/node/ACL ladder.
Comments contain escaped logical ID, component, reason, decision, owner and
source information; comments are diagnostic and are not ownership authority.

## FW4 parser scaffold

`render_test_scaffold()` and `render_check_file()` create a test-only file that
declares a placeholder `inet fw4` table and base chains before the production
fragment.  Its priorities are parser placeholders and do not model a device's
fw4 order.  The scaffold is never returned by `render_nft()`, never packaged,
and is rejected if it leaks into production output.

## Validation and examples

`validate_nft_ast()` checks versions, profile locks, Mark ABI, names, ownership,
manifest coverage, dependency acyclicity, action/match enums, and dangerous
commands.  `validate_nft_syntax_text()` rejects shell expansion, includes,
flush/delete operations and command chaining.  It is intentionally not an
NFT parser; only a local `nft -c` result can provide that evidence.

The development CLI is:

```text
python scripts/render-openkill-nft.py --state-id STATE-04-NODES
python scripts/render-openkill-nft.py --state-id STATE-12-TPROXY --scaffold
python scripts/render-openkill-nft.py --profile target --development-preview
```

The Phase 3B test suite covers syntax/AST schema, profile and BC locks,
address/set/comment safety, empty and interval sets, DNS/TUN/TProxy/redirect
intent, ownership and foreign preservation, current/target golden replay,
shadow/overlap compatibility, component-local diffs, 1000-run determinism,
input-order independence, and invalid IR rejection.  If `nft` is unavailable,
those parser-only checks remain useful but the `nft -c` gate is reported as
unavailable; no package installation or device fallback is allowed.

Phase 3C can later compare this current-profile syntax intent with captured
production firewall intent locally.  There is no production wiring in Phase
3B.
