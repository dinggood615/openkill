# Phase 3E.2D2C DNS CURRENT intent reconciliation

This local phase resolves the DNS mismatch reported by the frozen `.102`
shadow evidence.  It audits the checked-in OpenWrt integration and the
development CURRENT renderer; it does not read or modify a device.

## Source of truth

The production configuration and UI contract define `enable_redirect_dns=1`
as the stable dual-stack path.  LAN and router DNS packets first enter the
dnsmasq listener on port `53`; `change_dnsmasq()` forwards dnsmasq to the
committed Mihomo listener at `127.0.0.1#7874`.  The config comments and the
settings validation also state that firewall-direct mode (`enable_redirect_dns=2`)
is an advanced IPv4 non-TUN option and is unavailable for the default TUN or
IPv6 profile.

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

`dns_port=7874` is thus the Mihomo listener and dnsmasq upstream port.  It is
the firewall target only for mode-2 direct DNS.  The stable mode-1 firewall
target is a separate `firewall_dns_port` execution value backed by the
dnsmasq listener contract.  The two values are never compared transitively.

## Root cause and fix

The CURRENT packet renderer reused `context_execution["dns_port"]` when it
lowered mode-1 LAN and router attachments.  That made its desired semantic
projection say `redirect to :7874`, even though the production path is
`redirect to :53` followed by dnsmasq forwarding.  The local record-only
production harness had the same alias in its `DNSPORT` fixture value.

The minimal fix adds the separate `firewall_dns_port` execution field and
uses it only for mode-1 direct attachments.  Mode-2 body rules continue to use
`dns_port`.  The harness now models the checked-in dnsmasq listener default
independently.  No legacy writer, parser, continuity, auto-state ABI,
renderer non-DNS action, or device state changes.

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
IPv4/IPv6 scope is a `MISMATCH`.  Mode-1 renders are verified for both
families and directions, and mode-2 still renders its direct `:7874` body.

The prior D2B desired firewall values (`7874`, `7874`) remain recorded under
`frozen_device_evidence.dns_previous_desired_firewall`; they document the
resolved renderer alias defect rather than an equivalence rule.  The
reconciled desired fixture now records the mode-1 `:53` targets and matches the
frozen actual path without introducing a `53` to `7874` equivalence.  The
comparison is reproducible without a device or a live configuration read.
