#!/usr/bin/env python3
"""Backend-neutral semantic classifier oracle for Phase 2A.

This module is deliberately a development/test artifact.  It is not imported
by OpenKill's shell runtime and it never writes nftables, iptables, routes,
DNS, or configuration.  The JSON fixture next to it is the contract consumed
by future renderer tests.
"""

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Set, Tuple


DECISIONS: Tuple[str, ...] = (
    "NOT_OWNED",
    "BYPASS",
    "DIRECT",
    "PROXY",
    "DNS_SPECIAL",
    "ACCESS_DENY",
)

MATCH_REASONS: Tuple[str, ...] = (
    "OWNER_DISABLED",
    "DNS",
    "CONTROL_PROTOCOL",
    "SELF_TRAFFIC",
    "TUN_INGRESS",
    "NODE_ENDPOINT",
    "LOCAL_DESTINATION",
    "REPLY_TRAFFIC",
    "SERVICE_PORT",
    "ACCESS_CONTROL",
    "FAKEIP",
    "EXPLICIT_DIRECT",
    "EXPLICIT_PROXY",
    "CHINA_PASS",
    "CHINA_POLICY",
    "DEFAULT_POLICY",
    "INVALID_CONFIGURATION",
)

STATUS_VALUES: Tuple[str, ...] = (
    "VALID",
    "CURRENT_UNDEFINED",
    "INVALID_CONFIGURATION",
)

# These are semantic layers, not nft/iptables commands.  The current list is
# an audit record of the generated chains; the target list is the Phase 2A
# contract that a later renderer may implement after approval.
CURRENT_PRECEDENCE: Tuple[str, ...] = (
    "OWNER_DISABLED",
    "DNS",
    "ACCESS_CONTROL_CUSTOM",
    "NODE_ENDPOINT",
    "SELF_TRAFFIC",
    "TUN_INGRESS",
    "LOCAL_DESTINATION",
    "REPLY_TRAFFIC",
    "SERVICE_PORT",
    "CONTROL_PROTOCOL_IPV6",
    "ACCESS_CONTROL",
    "FAKEIP",
    "CHINA_PASS_FALLTHROUGH",
    "CHINA_POLICY",
    "DEFAULT_POLICY",
)

TARGET_PRECEDENCE: Tuple[str, ...] = (
    "OWNER_DISABLED",
    "DNS",
    "CONTROL_PROTOCOL",
    "SELF_TRAFFIC",
    "TUN_INGRESS",
    "NODE_ENDPOINT",
    "LOCAL_DESTINATION",
    "REPLY_TRAFFIC",
    "SERVICE_PORT",
    "ACCESS_CONTROL",
    "FAKEIP",
    "EXPLICIT_DIRECT",
    "EXPLICIT_PROXY",
    "CHINA_PASS",
    "CHINA_POLICY",
    "DEFAULT_POLICY",
)

PACKET_CONTEXT_DIMENSIONS = {
    "family": ("IPv4", "IPv6"),
    "direction": ("LAN_INGRESS", "ROUTER_OUTPUT", "TUN_INGRESS", "UNKNOWN"),
    "protocol": ("TCP", "UDP", "ICMP", "ICMPv6", "OTHER"),
    "backend_mode": ("TUN", "TPROXY", "REDIRECT"),
    "source_properties": ("LAN", "ROUTER", "SELF_PROCESS", "UNKNOWN"),
    "destination_properties": (
        "NODE_ENDPOINT",
        "LOCAL_PRIVATE",
        "WAN_HOST",
        "LAN_PREFIX",
        "DELEGATED_PREFIX",
        "CHINA",
        "USER_DIRECT",
        "USER_PROXY",
        "FAKEIP",
        "PUBLIC",
    ),
    "service": ("DNS", "DHCP", "DHCPv6", "NTP", "OTHER"),
    "connection": ("REPLY", "NEW", "UNKNOWN"),
    "owner": ("OPENKILL", "MIHOMO", "DISABLED", "UNKNOWN"),
}


@dataclass(frozen=True)
class Classification:
    """A semantic result, without a backend action or packet syntax."""

    reason: Optional[str]
    decision: Optional[str]
    status: str = "VALID"

    def as_dict(self) -> Dict[str, Optional[str]]:
        return {
            "reason": self.reason,
            "decision": self.decision,
            "status": self.status,
        }


def _norm(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_")


def _flags(raw: Mapping[str, Any]) -> Set[str]:
    values: Set[str] = set()
    for item in raw.get("flags", ()) or ():
        values.add(_norm(item))
    # A flat field is convenient for callers that construct a context in code.
    aliases = {
        "dns": "DNS",
        "control": "CONTROL_PROTOCOL",
        "self_traffic": "SELF_TRAFFIC",
        "tun_ingress": "TUN_INGRESS",
        "node_endpoint": "NODE_ENDPOINT",
        "local_destination": "LOCAL_DESTINATION",
        "reply": "REPLY_TRAFFIC",
        "service_port": "SERVICE_PORT",
        "access_bypass": "ACCESS_CONTROL",
        "access_deny": "ACCESS_DENY",
        "fakeip": "FAKEIP",
        "fakeip6": "FAKEIP",
        "user_direct": "EXPLICIT_DIRECT",
        "user_proxy": "EXPLICIT_PROXY",
        "china": "CHINA_POLICY",
        "china_pass": "CHINA_PASS",
        "custom_access": "CUSTOM_ACCESS",
    }
    for key, flag in aliases.items():
        if raw.get(key):
            values.add(flag)
    service = _norm(raw.get("service"))
    if service in {"DNS", "DNS_UDP", "DNS_TCP"}:
        values.add("DNS")
    if service in {"DHCPV6", "ICMPV6_CONTROL"}:
        values.add("CONTROL_PROTOCOL")
    if raw.get("icmpv6_type"):
        values.add("CONTROL_PROTOCOL")
    return values


def normalize_context(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize JSON fixture or caller input into a stable context mapping."""

    context = dict(raw)
    context["family"] = _norm(context.get("family"))
    context["direction"] = _norm(context.get("direction"))
    context["protocol"] = _norm(context.get("protocol"))
    context["owner"] = _norm(context.get("owner") or "OPENKILL")
    context["backend_mode"] = _norm(context.get("backend_mode") or "TUN")
    context["china_policy"] = _norm(context.get("china_policy") or "OFF")
    context["flags"] = _flags(context)
    return context


def _result(reason: str, decision: str, status: str = "VALID") -> Classification:
    return Classification(reason, decision, status)


def _invalid() -> Classification:
    return Classification("INVALID_CONFIGURATION", None, "INVALID_CONFIGURATION")


def _owner_disabled(context: Mapping[str, Any]) -> bool:
    return context.get("owner") not in {"OPENKILL", ""}


def _has(context: Mapping[str, Any], flag: str) -> bool:
    return flag in context["flags"]


def _china_direct_match(context: Mapping[str, Any]) -> bool:
    policy = context.get("china_policy", "OFF")
    china = _has(context, "CHINA_POLICY")
    passed = _has(context, "CHINA_PASS")
    if policy in {"BYPASS_MAINLAND", "MAINLAND", "1"}:
        return china and not passed
    if policy in {"BYPASS_OVERSEAS", "OVERSEAS", "2"}:
        return (not china) and not passed
    return False


def _validate_context(context: Mapping[str, Any]) -> Optional[Classification]:
    if _has(context, "EXPLICIT_DIRECT") and _has(context, "EXPLICIT_PROXY"):
        return _invalid()
    return None


def classify_current(raw: Mapping[str, Any]) -> Classification:
    """Model the currently observed production rule order.

    The order is intentionally conservative.  It mirrors the shell generator:
    custom access rules can be inserted at position zero; node rules are then
    inserted ahead of the generated chain; output self/TUN, local, reply,
    service, IPv6 control, ACL, fake-IP, China, and default follow.  Explicit
    user direct/proxy flags are marked CURRENT_UNDEFINED because the current
    firewall generator has no standalone semantic layer for them.
    """

    context = normalize_context(raw)
    if _owner_disabled(context):
        return _result("OWNER_DISABLED", "NOT_OWNED")
    invalid = _validate_context(context)
    if invalid:
        return invalid

    flags = context["flags"]
    if "DNS" in flags:
        return _result("DNS", "DNS_SPECIAL")
    # lan_ac_traffic uses nft insert position 0 after the normal generator.
    if "CUSTOM_ACCESS" in flags:
        if "ACCESS_DENY" in flags:
            return _result("ACCESS_CONTROL", "ACCESS_DENY")
        return _result("ACCESS_CONTROL", "BYPASS")
    if "NODE_ENDPOINT" in flags:
        return _result("NODE_ENDPOINT", "BYPASS")
    if "SELF_TRAFFIC" in flags:
        return _result("SELF_TRAFFIC", "BYPASS")
    # The IPv4 TUN mangle chain has an explicit iifname utun return.  The
    # current IPv6-specific mangle chain does not, so keep that gap visible in
    # the current oracle; the target contract still requires family parity.
    if "TUN_INGRESS" in flags and context.get("family") != "IPV6":
        return _result("TUN_INGRESS", "BYPASS")
    if "LOCAL_DESTINATION" in flags:
        return _result("LOCAL_DESTINATION", "BYPASS")
    if "REPLY_TRAFFIC" in flags:
        return _result("REPLY_TRAFFIC", "BYPASS")
    if "SERVICE_PORT" in flags:
        return _result("SERVICE_PORT", "BYPASS")
    # The explicit control return exists in the IPv6 mangle chains.  There is
    # no equivalent OpenKill-owned IPv4 control rule in the current generator.
    if context.get("family") == "IPV6" and "CONTROL_PROTOCOL" in flags:
        return _result("CONTROL_PROTOCOL", "BYPASS")
    if "ACCESS_CONTROL" in flags:
        if "ACCESS_DENY" in flags:
            return _result("ACCESS_CONTROL", "ACCESS_DENY")
        return _result("ACCESS_CONTROL", "BYPASS")
    if "FAKEIP" in flags:
        return _result("FAKEIP", "PROXY")
    if _china_direct_match(context):
        return _result("CHINA_POLICY", "DIRECT")
    # china_*_route_pass is implemented as an exclusion from the China return
    # rule, so it falls through to the final proxy action today.
    status = "CURRENT_UNDEFINED" if {"EXPLICIT_DIRECT", "EXPLICIT_PROXY"} & flags else "VALID"
    return _result("DEFAULT_POLICY", "PROXY", status)


def classify_target(raw: Mapping[str, Any]) -> Classification:
    """Approved Phase 2A semantic target, still detached from production."""

    context = normalize_context(raw)
    if _owner_disabled(context):
        return _result("OWNER_DISABLED", "NOT_OWNED")
    invalid = _validate_context(context)
    if invalid:
        return invalid

    flags = context["flags"]
    if "DNS" in flags:
        return _result("DNS", "DNS_SPECIAL")
    # Protocol control is a safety gate.  Keep the exception family-specific;
    # IPv4 has no corresponding OpenKill-owned control rule today.
    if context.get("family") == "IPV6" and "CONTROL_PROTOCOL" in flags:
        return _result("CONTROL_PROTOCOL", "BYPASS")
    if "SELF_TRAFFIC" in flags:
        return _result("SELF_TRAFFIC", "BYPASS")
    if "TUN_INGRESS" in flags:
        return _result("TUN_INGRESS", "BYPASS")
    if "NODE_ENDPOINT" in flags:
        return _result("NODE_ENDPOINT", "BYPASS")
    if "LOCAL_DESTINATION" in flags:
        return _result("LOCAL_DESTINATION", "BYPASS")
    if "REPLY_TRAFFIC" in flags:
        return _result("REPLY_TRAFFIC", "BYPASS")
    if "SERVICE_PORT" in flags:
        return _result("SERVICE_PORT", "BYPASS")
    if "CUSTOM_ACCESS" in flags or "ACCESS_CONTROL" in flags:
        if "ACCESS_DENY" in flags:
            return _result("ACCESS_CONTROL", "ACCESS_DENY")
        return _result("ACCESS_CONTROL", "BYPASS")
    # A fake-IP address is synthetic and cannot be sent to native routing;
    # preserve this safety rule ahead of explicit direct policy.
    if "FAKEIP" in flags:
        return _result("FAKEIP", "PROXY")
    if "EXPLICIT_DIRECT" in flags:
        return _result("EXPLICIT_DIRECT", "DIRECT")
    if "EXPLICIT_PROXY" in flags:
        return _result("EXPLICIT_PROXY", "PROXY")
    if "CHINA_PASS" in flags and context.get("china_policy") != "OFF":
        return _result("CHINA_PASS", "PROXY")
    if _china_direct_match(context):
        return _result("CHINA_POLICY", "DIRECT")
    return _result("DEFAULT_POLICY", "PROXY")


def classify(raw: Mapping[str, Any], profile: str = "target") -> Classification:
    """Dispatch to the explicit current or target oracle."""

    if profile.lower() == "current":
        return classify_current(raw)
    if profile.lower() == "target":
        return classify_target(raw)
    raise ValueError("profile must be 'current' or 'target'")


def backend_action(decision: Optional[str], backend_mode: str, protocol: str) -> str:
    """Map semantics to an abstract backend action, never to command syntax."""

    decision = decision or ""
    mode = _norm(backend_mode)
    proto = _norm(protocol)
    if decision == "NOT_OWNED":
        return "NOT_OWNED"
    if decision in {"BYPASS", "DIRECT"}:
        return "NATIVE_RETURN"
    if decision == "DNS_SPECIAL":
        return "DNS_REDIRECT"
    if decision == "ACCESS_DENY":
        return "REJECT"
    if decision == "PROXY":
        if mode == "TUN":
            return "MARK"
        if mode == "TPROXY":
            return "MARK_TPROXY"
        if mode == "REDIRECT" and proto == "TCP":
            return "REDIRECT"
        return "PROXY_BACKEND_SPECIFIC"
    return "UNDEFINED"


def enum_values() -> Dict[str, Tuple[str, ...]]:
    return {
        "decision": DECISIONS,
        "match_reason": MATCH_REASONS,
        "status": STATUS_VALUES,
    }


__all__ = [
    "DECISIONS",
    "MATCH_REASONS",
    "STATUS_VALUES",
    "Classification",
    "CURRENT_PRECEDENCE",
    "TARGET_PRECEDENCE",
    "PACKET_CONTEXT_DIMENSIONS",
    "backend_action",
    "classify",
    "classify_current",
    "classify_target",
    "enum_values",
    "normalize_context",
]
