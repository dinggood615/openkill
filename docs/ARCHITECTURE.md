# OpenKill architecture

OpenKill is an OpenWrt LuCI package that manages a Mihomo core, its generated
configuration, TUN routing, DNS interception, and legacy fw4 integration.
The installed service and legacy writers remain the runtime authority while
the shadow path observes and renders a bounded CURRENT intent.

## State flow

The migration path is deliberately one-way for reads:

`committed source/config → continuity token → coherent private snapshot →
auto-state → CURRENT renderer → bounded legacy capture → semantic comparison`.

The snapshot is self-sufficient; comparison code does not reread UCI, network,
dnsmasq, or Mihomo state. Central output is diagnostic material until a
separately approved handoff makes a single writer authoritative.

## Ownership

Semantic comparison distinguishes CURRENT-owned objects from legacy-only
safety, FW4 base, conditional/inactive objects, optional observations, and
out-of-scope evidence. Out-of-scope objects stay visible in diagnostics and
safety audits but do not alter CURRENT-owned equality. Unknown ownership fails
closed or is reported as a model gap.

## DNS layers

Firewall interception, dnsmasq listening, dnsmasq upstream, and the Mihomo
listener are separate fields. The stable mode-1 path is firewall and dnsmasq
on port 53, forwarding to the committed Mihomo listener at 127.0.0.1:7874.
Direct mode-2 DNS is a separate advanced path. Port values are never equated
transitively.

## Safety boundaries

The current migration keeps legacy writers authoritative, central writes at
zero, and shadow disabled by default. Device validation is documented in
`docs/real-device/VALIDATION.md`; it is not part of local development or the
release workflow.
