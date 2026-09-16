# Phase 3E.2D2D-R2B UCI lifecycle contract

This is the local source contract for the OpenKill `start → running → stop`
UCI audit.  It explains the R2A hash observation without changing production
behavior.  A whole-file hash can change while a service is running because
OpenKill records reversible runtime state and the DHCP package receives the
dnsmasq redirect.  The stop path is the convergence boundary.

## Ownership and classification

| Package/field | Owner | Running classification | Start semantic | Stop semantic |
| --- | --- | --- | --- | --- |
| `openkill.config.dnsmasq_server` | OpenKill | `REQUIRED_BACKUP_FOR_ROLLBACK` | Save the pre-redirect dnsmasq server list | Restore the list, then delete the backup |
| `openkill.config.dnsmasq_noresolv` | OpenKill | `REQUIRED_BACKUP_FOR_ROLLBACK` | Save the pre-start value | Restore it when the redirect is removed; retain the backup metadata for a later transition |
| `openkill.config.dnsmasq_resolvfile` | OpenKill | `REQUIRED_BACKUP_FOR_ROLLBACK` | Save the pre-start value | Restore it, or use the documented OpenWrt default fallback; retain the backup metadata |
| `openkill.config.dnsmasq_cachesize` | OpenKill | `REQUIRED_BACKUP_FOR_ROLLBACK` | Save the pre-start value | Restore it and delete the backup |
| `openkill.config.dnsmasq_filter_aaaa` | OpenKill | `REQUIRED_BACKUP_FOR_ROLLBACK` | Save the pre-start value when IPv6 DNS is enabled | Restore it and delete the backup |
| `openkill.config.redirect_dns` | OpenKill | `REQUIRED_TRANSIENT_RUNTIME_STATE` | Mark dnsmasq redirection active | Set `0` and delete the saved server list |
| `openkill.config.cachesize_dns` | OpenKill | `REQUIRED_TRANSIENT_RUNTIME_STATE` | Mark cache override active | Set the marker to `0` and delete the saved cache size |
| `openkill.config.filter_aaaa_dns` | OpenKill | `REQUIRED_TRANSIENT_RUNTIME_STATE` | Mark AAAA override active | Set the marker to `0` and delete the saved AAAA value |
| `openkill.config.default_resolvfile` | OpenKill | `REQUIRED_BACKUP_FOR_ROLLBACK` | Record a fallback path only when no usable saved path exists | May remain as persistent discovered-default metadata |
| `openkill.config.last_start_failed` | OpenKill | `REQUIRED_TRANSIENT_RUNTIME_STATE` | Set on a failed start | Delete after readiness; it is absent after successful startup |
| `openkill.config.compatibility_fallback*` | OpenKill | `PERSISTENT_USER_CONFIG` | Record the effective TUN ownership/fallback selected by normalization/startup | Clear or update on the next ownership decision; it is not restored by stop |
| `openkill.config.core_arch`, `core_type` | OpenKill | `PERSISTENT_USER_CONFIG` | Record detected/validated core capability metadata | Retain as capability metadata |
| `openkill.config.dns_port` | OpenKill | `PERSISTENT_USER_CONFIG` | Persist the documented default `7874` when absent | Retain; it is the Mihomo listener/upstream port, not the mode-1 firewall port |
| `openkill.@overwrite[0]` | OpenKill | `REQUIRED_TRANSIENT_RUNTIME_STATE` | Hold one-shot overwrite input | Clear after it has been consumed |
| `dhcp.@dnsmasq[0].server` | DHCP/dnsmasq | `EXPECTED_DNSMASQ_RUNTIME_MUTATION` | Replace servers with `127.0.0.1#7874` | Restore the saved list |
| `dhcp.@dnsmasq[0].noresolv` | DHCP/dnsmasq | `EXPECTED_DNSMASQ_RUNTIME_MUTATION` | Set `1` during redirect | Restore the saved value/default |
| `dhcp.@dnsmasq[0].resolvfile` | DHCP/dnsmasq | `EXPECTED_DNSMASQ_RUNTIME_MUTATION` | Remove it while `noresolv=1` | Restore the saved/default path |
| `dhcp.@dnsmasq[0].localuse` | DHCP/dnsmasq | `EXPECTED_DNSMASQ_RUNTIME_MUTATION` | Converge to `1` | Keep the formal OpenWrt default `1` |
| `dhcp.@dnsmasq[0].cachesize` | DHCP/dnsmasq | `EXPECTED_DNSMASQ_RUNTIME_MUTATION` | Set `0` | Restore the saved value |
| `dhcp.@dnsmasq[0].filter_aaaa` | DHCP/dnsmasq | `EXPECTED_DNSMASQ_RUNTIME_MUTATION` | Set `0` when IPv6 DNS is enabled | Restore the saved value |
| `openkill.config.config_path` | User/OpenKill selector | `PERSISTENT_USER_CONFIG` | Keep unchanged when the configured target exists; choose a file only in the documented missing-target fallback | Retain the selected path |
| `openkill.config.tun_owner`, `tun_auto_route`, `tun_auto_redirect`, `tun_auto_detect_interface`, `compatibility_profile` | OpenKill normalizer | `PERSISTENT_USER_CONFIG` (normalization-owned) | Derive and validate the mutually exclusive owner/profile and its safe route flags | Retain the normalized values; a target-present, already normalized start has no delta |
| `firewall.openkill` | OpenKill/firewall integration | `REQUIRED_TRANSIENT_RUNTIME_STATE` | Install the generated include before firewall use | Remove the include on normal stop |
| `firewall.passwall.reload` | PassWall/firewall integration | `PERSISTENT_USER_CONFIG` (conditional migration) | Remove the obsolete `reload` option only for Mihomo-native ownership on fw4 | Intentionally not restored; never part of the OpenKill-owned TUN delta |
| `ucitrack.@openkill` | Installed integration metadata | `PERSISTENT_USER_CONFIG` | Ensure the package integration entry exists | Retain the installed entry |
| `openkill.subscribe_info.url`, `openkill.@subscribe_info` | User subscription metadata | `PERSISTENT_USER_CONFIG` | Update only when an overwrite/subscription path supplies a URL | Retain; absent from the target-present normal start path |
| `openkill.config_age_secret` | OpenKill age-key metadata | `PERSISTENT_USER_CONFIG` | Persist age key metadata supplied by an overwrite/config operation | Retain; never synthesized by a normal target-present start |

Fields outside this table are not implicitly allowed.  An unclassified UCI
write is `FORBIDDEN_UNEXPECTED_MUTATION` until its owner and lifecycle purpose
are documented.  The `PERSISTENT_USER_CONFIG` label also covers persisted
OpenKill capability/migration metadata (`core_*`, `dns_port`, compatibility
markers and installed `ucitrack` integration); the ownership column remains
the authority for whether a field is user-owned or lifecycle-owned.

## Ownership model

The corrected gate separates who owns a field from whether it is transient or
persistent:

| Ownership | Meaning | Gate treatment |
| --- | --- | --- |
| `USER_OWNED` | A profile, selector or user supplied option that a normal target-present start must not rewrite | Compare the semantic value before and after; an unplanned change fails |
| `OPENKILL_LIFECYCLE_OWNED` | OpenKill's active marker, generated include or one-shot state | Allow only the exact start delta and required stop convergence |
| `OPENKILL_ROLLBACK_METADATA` | A saved dnsmasq value used by a later revert, including resolver backup metadata | Allow the documented save/restore or intentional persistence; unknown fields remain forbidden |
| `DNSMASQ_RUNTIME_OWNED` | The DHCP package's dnsmasq options while OpenKill's redirect is active | Allow only the documented redirect delta and require stop convergence |
| `SYSTEM_DNSMASQ_OWNED` | Base dnsmasq defaults and files outside OpenKill's bounded transition | Preserve unless a source row explicitly assigns a runtime change |
| `UNKNOWN` | A write whose owner or lifecycle purpose cannot be established from source | Fail closed as `FORBIDDEN_UNEXPECTED_MUTATION` |

Ownership is independent from persistence.  For example, the resolver backup
values are OpenKill rollback metadata and intentionally persist, while the
redirect marker is lifecycle-owned and converges to `0`.

## Source audit index

| Source and function | Phase | Package/section | Contracted write | Restore or persistence |
| --- | --- | --- | --- | --- |
| `etc/init.d/openkill:change_dnsmasq` | readiness after start | `openkill.config`, `dhcp.@dnsmasq[0]` | Save dnsmasq values, install the `127.0.0.1#7874` relay and commit both packages | `revert_dnsmasq` restores the saved values, converges markers and removes reversible backups |
| `etc/init.d/openkill:revert_dnsmasq` | formal stop/recovery | `openkill.config`, `dhcp.@dnsmasq[0]` | Restore server, resolver, cache and AAAA settings; restart dnsmasq | Reversible backup fields and active markers converge; resolver backup metadata and a discovered default may persist |
| `etc/init.d/openkill:start_fail` and `check_core_status` | failed/successful start | `openkill.config.last_start_failed` | Commit a failure marker, then delete it only after readiness | Transient; absent after a successful start |
| `etc/init.d/openkill:config_choose` | missing-config fallback | `openkill.config.config_path` | Select the first installed profile only when the configured file is absent | Persistent selector; no write when the target-present D2D file exists |
| `etc/init.d/openkill:prepare_openkill_include` / `remove_openkill_include` | start/stop integration | `firewall.openkill` | Install/remove the volatile firewall include; ensure `ucitrack.@openkill` | Include is reversible; ucitrack is installed metadata and persists |
| `etc/init.d/openkill:sanitize_native_fw4_compat` | native Mihomo + fw4 only | `firewall.passwall.reload` | Remove the obsolete PassWall reload option | Intentional one-way compatibility migration; outside OpenKill-owned TUN delta |
| `etc/init.d/openkill:get_config` | start and stop reads | `openkill.config.dns_port` | Apply the documented default `7874` when missing and commit OpenKill | Persistent default; commit is idempotent once present |
| `etc/init.d/openkill:overwrite_file` / `clear_overwrite_set` | explicit overwrite path / stop | `openkill.@overwrite[0]`, `subscribe_info`, age metadata | Materialize validated overwrite fields, subscription URLs and age keys | Overwrite section is cleared on stop; user/config metadata persists |
| `openkill_config_normalize.sh` | package/start normalization | `openkill.config.*` | Write only missing/unsafe defaults (`en_mode`, proxy/process settings, TUN ownership/flags, addresses, profile, IPv6/DNS safety and migration versions) | Persistent migration; commit occurs only when values changed |
| `openkill_core.sh` | core detection/install | `openkill.config.core_arch`, `core_type` | Record detected architecture and validated Meta core | Persistent capability metadata |
| `openkill_watchdog.sh` | running repair | `dhcp.@dnsmasq[0]` | Re-assert the bounded dnsmasq relay/resolver delta | Expected DHCP runtime mutation; no new OpenKill user field |

The package `postinst` invokes only the idempotent normalizer, while `prerm`
stops the service and preserves the conffile.  The separate
`scripts/install-openkill.sh uninstall` path intentionally deletes
`/etc/config/openkill`; it is an operator uninstall, not a lifecycle mutation
that the R2B gate permits.  No start/stop path writes `network` UCI, and no
unrelated firewall or DHCP field is implicitly whitelisted.

The normalizer is a separate migration path.  It writes only missing or
unsafe defaults and commits when it changed a value; those changes are
persistent configuration normalization, not a reason to weaken the runtime
gate.  Core detection similarly records capability metadata.  `get_config()`
also commits the OpenKill package after applying the documented missing
`dns_port=7874` default; the commit is idempotent when the value is already
present.  The watchdog's idempotent dnsmasq repair is part of the DHCP runtime
delta and is not a new user setting.

The subscription and age-key writes are reached only from an overwrite or
missing-config flow.  They are user/configuration operations and are outside
the target-present D2D start contract.  The native PassWall cleanup is a
conditional compatibility migration for `tun_owner=mihomo` with fw4; seeing
that write during an OpenKill-owned TUN run is an unexpected mutation.

## Corrected gates

The R2A `ACTIVE_UCI_SHA256_RUNNING == ACTIVE_UCI_SHA256_BEFORE` assertion was
too strong for a service that must save rollback state and redirect dnsmasq.
The replacement is field based:

```text
UCI_USER_CONFIG_UNCHANGED=PASS
OPENKILL_EXPECTED_RUNTIME_DELTA=EXACT_MATCH
DHCP_EXPECTED_RUNTIME_DELTA=EXACT_MATCH
UNEXPECTED_UCI_DELTA=0
CONFIG_PATH_UNCHANGED=PASS       # target-present D2D scenario
SUCCESS_FAILURE_MARKER_CLEAN=PASS
STOP_CONVERGENCE=PASS
OTHER_UCI_PACKAGES_UNCHANGED=PASS
```

`STOP_CONVERGENCE` means that a successful formal stop restores all reversible
dnsmasq fields, sets lifecycle markers to their inactive value, and removes
the active/reversible backup entries.  The saved resolver values and discovered
default path are intentionally retained as rollback metadata.  It does not
require a raw hash to remain constant while the service is running.  R2A's
before and after hash equality is strong supporting evidence for convergence,
and is not the running-state gate.

## Failure and recovery semantics

`last_start_failed` is a transient failure marker: `start_fail()` commits it,
and `check_core_status()` removes it only after local readiness checks pass.
The recovery checkpoint stores the generated config, matching OpenKill UCI,
and core digest without inventing a new UCI mutation.  A missing configured
target may enter `config_choose()`'s explicit fallback; the normal D2D case has
`/etc/openkill/config/3e2-safe.yaml` present and therefore must not rewrite
`config_path`.

The package declares `/etc/config/openkill` as a conffile.  Its maintainer
scripts stop OpenKill before removal and do not delete `/etc/config/openkill`
or `/etc/openkill`; package post-install and the explicit start normalizer are
the only documented default/migration paths that may persist OpenKill UCI
values.  The one-click
`scripts/install-openkill.sh uninstall` command is a separate, explicitly
destructive operator path: it stops the service, removes the package and then
deletes `/etc/config/openkill`.  It is not part of start/stop validation and
must never be used by the R2B gate.  No normal start path writes `network`
UCI; `firewall` and `ucitrack` integration writes are limited to the rows
above.

The lifecycle order relevant to the corrected gate is deterministic: the
normalizer runs first; `check_run_quick`/`overwrite_file` then consume any
explicit overwrite; `config_choose` selects a fallback only when the configured
file is missing; `get_config` reads the selected file and applies the default
port; mode setup and core preparation follow; readiness invokes
`change_dnsmasq` and firewall integration.  Stop calls `get_config`, terminates
the core, removes the firewall include, runs `revert_dnsmasq`, clears the
overwrite section and removes transient files.  This is why a running whole
file hash is not a valid gate while the post-stop field projection is.

## Verification

`scripts/test-uci-lifecycle.py` checks the source evidence and simulates a
representative pre/start/running/stop dnsmasq transition.  It asserts that
user fields and `config_path` remain unchanged in the target-present case,
that the exact runtime delta is restored, and that network UCI is untouched.
It is a local test; it never invokes UCI or accesses a router.
