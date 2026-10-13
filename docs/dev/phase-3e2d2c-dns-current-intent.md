# Phase 3E.2D2C DNS CURRENT intent reconciliation

This local phase resolves the DNS mismatch reported by the frozen `.102`
shadow evidence.  It audits the checked-in OpenWrt integration and the
development CURRENT renderer; it does not read or modify a device.

## Source of truth

The production configuration and UI contract define both
`enable_redirect_dns=1` and `enable_redirect_dns=2` as dual-stack paths whose
LAN, router and authorized OpenVPN DNS packets first enter the dnsmasq
listener on port `53`; `change_dnsmasq()` forwards dnsmasq to the committed
Mihomo listener at `127.0.0.1#7874`. Mode 1 and mode 2 retain separate
ownership/ACL chains, but mode 2 is no longer a direct redirect to Mihomo's
loopback port. This is required for tunnel ingress: REDIRECT can select the
incoming tunnel address, which a loopback-only Mihomo listener cannot receive.

The fields therefore have distinct meanings:

| Semantic field | Source of truth | Owner | Meaning |
| --- | --- | --- | --- |
| `DNS_FIREWALL_LAN_TARGET` | mode-1 `set_firewall()` / dnsmasq listener contract | CURRENT_OWNED | LAN DNS redirect target, `:53` by the checked-in default |
| `DNS_FIREWALL_ROUTER_TARGET` | mode-1 `set_firewall()` / dnsmasq listener contract | CURRENT_OWNED | router-self DNS redirect target, `:53` by the checked-in default |
| `DNSMASQ_LISTEN_TARGET` | OpenWrt dnsmasq default and committed integration | CURRENT_OWNED | LAN-facing dnsmasq listener, `:53` |
| `DNSMASQ_UPSTREAM_TARGET` | `change_dnsmasq()` and committed `dns_port` | CURRENT_OWNED | dnsmasq upstream, `127.0.0.1#7874` |
| `MIHOMO_DNS_LISTENER` | committed Mihomo DNS config | CURRENT_OWNED | Mihomo loopback listener, `127.0.0.1:7874` |
| `DNS_LOOP_PREVENTION` | mode-1 router-output rule and the documented skgid guard | CURRENT_OWNED | excludes the dnsmasq/Mihomo service owner |
| `DNS_SCOPE_IPV4` | normalized `dns_scope` and `enable_redirect_dns` | CURRENT_OWNED | IPv4 LAN/router scope |
| `DNS_SCOPE_IPV6` | normalized `dns_scope` and `ipv6_dns` | CURRENT_OWNED | IPv6 LAN/router scope |

`dns_port=7874` is thus the Mihomo listener and dnsmasq upstream port. Both
redirect modes use a separate `firewall_dns_port` execution value backed by
the dnsmasq listener contract (`53`). The two values are never compared
transitively.

## Root cause and fix

The CURRENT packet renderer and production writer had two aliases: mode 1 used
the dnsmasq listener while mode 2 used the Mihomo listener for IPv4 (IPv6 had
already been special-cased to dnsmasq). On an OpenVPN ingress packet this made
the IPv4 REDIRECT target depend on the tunnel address and bypass the
loopback-only core, so the VPN could be connected while DNS and subsequent
proxy traffic failed. The fix makes mode-2 IPv4 use the same dnsmasq frontend
as IPv6, and makes the semantic renderer use `firewall_dns_port=53` for both
modes.

The minimal fix keeps the separate `firewall_dns_port` execution field,
redirects both families and both modes to it, and leaves `dns_port` solely as
the Mihomo/dnsmasq-upstream value. The harness models the checked-in dnsmasq
listener independently. No business proxy group, node, WAN rule, or DNS
upstream is changed.

The shell shadow input remains a record-only ABI: `openkill_nft_shadow.sh`
maps `DNS_PORT` from the normalized `dns_port` value and the checked-in DNS
templates emit the approved DNS chain topology.  It does not make that value
the mode-1 firewall port.  The separate port is materialized at the narrow
CURRENT context-rendering boundary where the physical mode-1 attachment is
lowered.  This preserves the input protocol and keeps the legacy init script's
`DNSPORT` discovery as the runtime authority for the actual device.

## Validation contract

The reconciled frozen fixture has firewall targets `53`, dnsmasq listen `53`,
upstream `127.0.0.1#7874`, and Mihomo listener `127.0.0.1:7874`; its CURRENT
owned DNS projection is `MATCH`.  Negative fixtures keep the fields
independent: a wrong firewall target, upstream, listener, LAN/router scope, or
IPv4/IPv6 scope is a `MISMATCH`. Both mode-1 and mode-2 renders are verified
for both families and directions and use the `:53` frontend.

The prior D2B desired firewall values (`7874`, `7874`) remain recorded under
`frozen_device_evidence.dns_previous_desired_firewall`; they document the
resolved renderer alias defect rather than an equivalence rule.  The
reconciled desired fixture now records the mode-1 `:53` targets and matches the
frozen actual path without introducing a `53` to `7874` equivalence.  The
comparison is reproducible without a device or a live configuration read.
