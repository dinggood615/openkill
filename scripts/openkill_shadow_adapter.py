#!/usr/bin/env python3
"""Pure production-state to semantic-context shadow adapter.

The adapter consumes already-normalized state and synthetic packet
descriptors.  It only reports observable facts (set membership, direction,
owner, service, and protocol properties); precedence and decisions remain the
responsibility of :mod:`openkill_classifier_model` in ``shadow_compare``.

This is a development artifact.  It deliberately does not import or execute
the OpenWrt init script and has no shell, filesystem, network, or runtime
side-effects.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


SHADOW_STATE_SCHEMA = "OPENKILL_SHADOW_STATE_V1"
SHADOW_PACKET_SCHEMA = "OPENKILL_SHADOW_PACKET_V1"
SHADOW_FIXTURE_SCHEMA = "OPENKILL_SHADOW_FIXTURE_V1"
SHADOW_CONTRACT_VERSION = 1
# The execution fields below are an additive development-side extension of
# the Phase 2C state contract.  They describe configured listeners; they do
# not change semantic decisions and are never read by production runtime.
SHADOW_EXECUTION_CONTRACT_VERSION = 1
DEFAULT_PROXY_PORTS = {
    "redirect": 7892,
    # The production get_config() fallback is 7895.  Individual shadow
    # states may override this with their explicitly normalized fixture
    # listener (for example the Phase 3C TPROXY baseline uses 7893).
    "tproxy": 7895,
    "dns": 7874,
}

SHADOW_RESULTS: Tuple[str, ...] = (
    "MATCH",
    "EXPECTED_CURRENT_GAP",
    "UNMAPPED_STATE",
    "SEMANTIC_MISMATCH",
    "INVALID_STATE",
    "NOT_APPLICABLE",
)
CONFIDENCE_VALUES: Tuple[str, ...] = ("HIGH", "MEDIUM", "LOW")
_INTENT_STATUSES = frozenset(("VALID", "CURRENT_UNDEFINED", "INVALID_CONFIGURATION"))
_INTENT_REASONS = frozenset(
    (
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
)
_INTENT_DECISIONS = frozenset(("NOT_OWNED", "BYPASS", "DIRECT", "PROXY", "DNS_SPECIAL", "ACCESS_DENY"))
_INTENT_MATCHES = frozenset(
    (
        "DNS",
        "CONTROL_PROTOCOL",
        "SELF_TRAFFIC",
        "TUN_INGRESS",
        "NODE_ENDPOINT",
        "LOCAL_DESTINATION",
        "REPLY_TRAFFIC",
        "SERVICE_PORT",
        "ACCESS_CONTROL",
        "CUSTOM_ACCESS",
        "ACCESS_DENY",
        "FAKEIP",
        "EXPLICIT_DIRECT",
        "EXPLICIT_PROXY",
        "CHINA_PASS",
        "CHINA_POLICY",
    )
)
STATE_OWNERS: Tuple[str, ...] = ("OPENKILL", "MIHOMO", "DISABLED", "UNKNOWN")
RUN_MODES: Tuple[str, ...] = ("TUN", "TPROXY", "REDIRECT")
DNS_SCOPES: Tuple[str, ...] = ("NONE", "LAN", "LAN_AND_ROUTER", "ROUTER_ONLY")
ACCESS_ACTIONS: Tuple[str, ...] = ("ALLOW", "BYPASS", "DENY")
SOURCE_KINDS: Tuple[str, ...] = ("LAN", "ROUTER", "SELF_PROCESS", "UNKNOWN")
CONNECTION_VALUES: Tuple[str, ...] = ("REPLY", "NEW", "UNKNOWN")
SERVICE_VALUES: Tuple[str, ...] = ("DNS", "DHCP", "DHCPv6", "NTP", "OTHER")
ICMPV6_CONTROL_TYPES = frozenset(
    ("RS", "RA", "NS", "NA", "PTB", "DESTINATION_UNREACHABLE", "TIME_EXCEEDED", "PARAMETER_PROBLEM")
)
CHINA_POLICIES = frozenset(
    ("OFF", "BYPASS_MAINLAND", "MAINLAND", "1", "BYPASS_OVERSEAS", "OVERSEAS", "2")
)

_ADDRESS_FIELDS = ("wan4", "wan6", "node4", "node6")
_NETWORK_FIELDS = (
    "local4",
    "local6",
    "lan4",
    "lan6",
    "delegated6",
    "china4",
    "china6",
    "china_pass4",
    "china_pass6",
    "fake_ip4",
    "fake_ip6",
    "user_direct4",
    "user_direct6",
    "user_proxy4",
    "user_proxy6",
)


class ShadowValidationError(ValueError):
    """A state, packet, or intent fixture is outside the shadow schema."""


class ShadowComparisonError(ValueError):
    """An intent fixture cannot be compared safely."""


def _norm(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_")


def _canonical_owner(value: Any) -> str:
    candidate = _norm(value or "OPENKILL")
    if candidate not in STATE_OWNERS:
        raise ShadowValidationError("unknown owner: {!r}".format(value))
    return candidate


def _canonical_family(value: Any) -> str:
    candidate = _norm(value)
    if candidate not in {"IPV4", "IPV6"}:
        raise ShadowValidationError("unknown family: {!r}".format(value))
    return "IPv4" if candidate == "IPV4" else "IPv6"


def _canonical_direction(value: Any) -> str:
    candidate = _norm(value or "UNKNOWN")
    allowed = {"LAN_INGRESS", "ROUTER_OUTPUT", "TUN_INGRESS", "UNKNOWN"}
    if candidate not in allowed:
        raise ShadowValidationError("unknown direction: {!r}".format(value))
    return candidate


def _canonical_protocol(value: Any) -> str:
    candidate = _norm(value or "OTHER")
    if candidate not in {"TCP", "UDP", "ICMP", "ICMPV6", "OTHER"}:
        raise ShadowValidationError("unknown protocol: {!r}".format(value))
    return "ICMPv6" if candidate == "ICMPV6" else candidate


def _canonical_service(value: Any) -> str:
    candidate = _norm(value or "OTHER")
    if candidate not in {"DNS", "DHCP", "DHCPV6", "NTP", "OTHER"}:
        raise ShadowValidationError("unknown service: {!r}".format(value))
    return "DHCPv6" if candidate == "DHCPV6" else candidate


def _canonical_connection(value: Any) -> str:
    candidate = _norm(value or "UNKNOWN")
    if candidate not in set(CONNECTION_VALUES):
        raise ShadowValidationError("unknown connection: {!r}".format(value))
    return candidate


def _canonical_run_mode(value: Any) -> str:
    candidate = _norm(value or "TUN")
    if candidate not in RUN_MODES:
        raise ShadowValidationError("unknown run_mode: {!r}".format(value))
    return candidate


def _canonical_dns_scope(value: Any) -> str:
    candidate = _norm(value or "NONE")
    if candidate not in DNS_SCOPES:
        raise ShadowValidationError("unknown dns_scope: {!r}".format(value))
    return candidate


def _canonical_dns_mode(value: Any, scope: str) -> str:
    """Normalize the production DNS switch without inferring packet policy."""

    if value is None or value == "":
        return {
            "NONE": "0",
            "LAN": "1",
            "ROUTER_ONLY": "1",
            "LAN_AND_ROUTER": "2",
        }[scope]
    candidate = str(value).strip()
    if candidate not in {"0", "1", "2"}:
        raise ShadowValidationError("unknown dns_mode: {!r}".format(value))
    return candidate


def _canonical_proxy_ports(value: Any) -> Dict[str, int]:
    """Return validated listener ports in a stable, explicit shape."""

    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise ShadowValidationError("proxy_ports must be an object")
    result: Dict[str, int] = {}
    for key, default in DEFAULT_PROXY_PORTS.items():
        raw = value.get(key, default)
        if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= 65535:
            raise ShadowValidationError("invalid {} proxy port: {!r}".format(key, raw))
        result[key] = int(raw)
    unknown = set(value) - set(DEFAULT_PROXY_PORTS)
    if unknown:
        raise ShadowValidationError("unknown proxy port field: {!r}".format(sorted(unknown)))
    return result


def _canonical_network(value: Any, family: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ShadowValidationError("network entry must be a non-empty string")
    try:
        network = ipaddress.ip_network(value.strip(), strict=False)
    except ValueError as exc:
        raise ShadowValidationError("invalid {} network: {!r}".format(family, value)) from exc
    if network.version != (4 if family == "IPv4" else 6):
        raise ShadowValidationError("{} network has wrong family: {!r}".format(family, value))
    return str(network)


def _canonical_host(value: Any, family: str, allow_prefix: bool = True) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ShadowValidationError("address entry must be a non-empty string")
    try:
        address = ipaddress.ip_interface(value.strip()).ip if (allow_prefix and "/" in value) else ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise ShadowValidationError("invalid {} address: {!r}".format(family, value)) from exc
    if address.version != (4 if family == "IPv4" else 6):
        raise ShadowValidationError("{} address has wrong family: {!r}".format(family, value))
    return str(address)


def _canonical_list(value: Any) -> Tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple, set, frozenset)):
        raise ShadowValidationError("collection must be a sequence")
    return tuple(value)


def _sorted_unique(values: Iterable[str]) -> List[str]:
    return sorted(set(values), key=lambda item: (ipaddress.ip_address(item.split("/", 1)[0]).version, item))


def _normalize_ip_collection(value: Any, family: str) -> List[str]:
    return _sorted_unique(_canonical_host(item, family) for item in _canonical_list(value))


def _normalize_network_collection(value: Any, family: str) -> List[str]:
    values = (_canonical_network(item, family) for item in _canonical_list(value))
    return sorted(set(values), key=lambda item: (ipaddress.ip_network(item).prefixlen, item))


def _normalize_access(value: Any, family: str) -> List[Dict[str, str]]:
    normalized: Dict[str, str] = {}
    for item in _canonical_list(value):
        if not isinstance(item, Mapping):
            raise ShadowValidationError("access entry must be an object")
        network = _canonical_network(item.get("network"), family)
        action = _norm(item.get("action") or "ALLOW")
        if action not in ACCESS_ACTIONS:
            raise ShadowValidationError("unknown access action: {!r}".format(item.get("action")))
        previous = normalized.get(network)
        if previous is not None and previous != action:
            raise ShadowValidationError("conflicting access actions for {}".format(network))
        normalized[network] = action
    return [{"network": network, "action": normalized[network]} for network in sorted(normalized)]


def normalize_state(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and canonicalize one normalized shadow state."""

    if not isinstance(raw, Mapping):
        raise ShadowValidationError("state must be an object")
    if raw.get("schema", SHADOW_STATE_SCHEMA) != SHADOW_STATE_SCHEMA:
        raise ShadowValidationError("unsupported state schema")
    if raw.get("contract_version", SHADOW_CONTRACT_VERSION) != SHADOW_CONTRACT_VERSION:
        raise ShadowValidationError("state contract version mismatch")
    state_id = raw.get("id", raw.get("state_id"))
    if not isinstance(state_id, str) or not state_id:
        raise ShadowValidationError("state id missing")
    owner = _canonical_owner(raw.get("owner"))
    run_mode = _canonical_run_mode(raw.get("run_mode"))
    dns_scope = _canonical_dns_scope(raw.get("dns_scope"))
    dns_mode = _canonical_dns_mode(raw.get("dns_mode"), dns_scope)
    execution_contract_version = raw.get(
        "execution_contract_version", SHADOW_EXECUTION_CONTRACT_VERSION
    )
    if execution_contract_version != SHADOW_EXECUTION_CONTRACT_VERSION:
        raise ShadowValidationError("shadow execution contract version mismatch")
    proxy_ports = _canonical_proxy_ports(raw.get("proxy_ports"))
    china_policy = _norm(raw.get("china_policy") or "OFF")
    if china_policy not in CHINA_POLICIES:
        raise ShadowValidationError("unknown china_policy: {!r}".format(raw.get("china_policy")))
    tun_interface = raw.get("tun_interface", "utun")
    if not isinstance(tun_interface, str) or not tun_interface.strip():
        raise ShadowValidationError("tun_interface must be non-empty")
    self_proxy = raw.get("router_self_proxy", False)
    if not isinstance(self_proxy, bool):
        raise ShadowValidationError("router_self_proxy must be boolean")

    state: Dict[str, Any] = {
        "schema": SHADOW_STATE_SCHEMA,
        "contract_version": SHADOW_CONTRACT_VERSION,
        "id": state_id,
        "owner": owner,
        "run_mode": run_mode,
        "router_self_proxy": self_proxy,
        "tun_interface": tun_interface.strip(),
        "dns_scope": dns_scope,
        "dns_mode": dns_mode,
        "china_policy": china_policy,
        "execution_contract_version": SHADOW_EXECUTION_CONTRACT_VERSION,
        "proxy_ports": proxy_ports,
    }
    for field in ("wan4", "node4", "wan6", "node6"):
        family = "IPv4" if field.endswith("4") else "IPv6"
        state[field] = _normalize_ip_collection(raw.get(field), family)
    for field in _NETWORK_FIELDS:
        family = "IPv4" if field.endswith("4") else "IPv6"
        state[field] = _normalize_network_collection(raw.get(field), family)
    state["access4"] = _normalize_access(raw.get("access4"), "IPv4")
    state["access6"] = _normalize_access(raw.get("access6"), "IPv6")
    ports = []
    for value in _canonical_list(raw.get("service_ports")):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
            raise ShadowValidationError("invalid service port: {!r}".format(value))
        ports.append(value)
    state["service_ports"] = sorted(set(ports))
    return state


def validate_state_fixture(fixture: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate a versioned state fixture and return its normalized states."""

    if not isinstance(fixture, Mapping) or fixture.get("schema") != SHADOW_FIXTURE_SCHEMA:
        raise ShadowValidationError("unsupported shadow fixture schema")
    if fixture.get("contract_version") != SHADOW_CONTRACT_VERSION:
        raise ShadowValidationError("shadow fixture contract version mismatch")
    states = fixture.get("states")
    if not isinstance(states, list) or not states:
        raise ShadowValidationError("states must be a non-empty list")
    normalized = []
    seen: Set[str] = set()
    for raw in states:
        state = normalize_state(raw)
        if state["id"] in seen:
            raise ShadowValidationError("duplicate state id: {}".format(state["id"]))
        seen.add(state["id"])
        normalized.append(state)
    return {
        "schema": SHADOW_FIXTURE_SCHEMA,
        "contract_version": SHADOW_CONTRACT_VERSION,
        "states": normalized,
    }


def normalize_packet(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and canonicalize one synthetic packet descriptor."""

    if not isinstance(raw, Mapping):
        raise ShadowValidationError("packet must be an object")
    if raw.get("schema", SHADOW_PACKET_SCHEMA) != SHADOW_PACKET_SCHEMA:
        raise ShadowValidationError("unsupported packet schema")
    packet_id = raw.get("id", raw.get("packet_id"))
    if not isinstance(packet_id, str) or not packet_id:
        raise ShadowValidationError("packet id missing")
    family = _canonical_family(raw.get("family"))
    direction = _canonical_direction(raw.get("direction"))
    protocol = _canonical_protocol(raw.get("protocol"))
    if family == "IPv4" and protocol == "ICMPv6":
        raise ShadowValidationError("IPv4 cannot carry ICMPv6")
    src = _canonical_host(raw.get("src"), family, allow_prefix=False)
    dst = _canonical_host(raw.get("dst"), family, allow_prefix=False)
    source_kind = _norm(raw.get("source_kind") or "UNKNOWN")
    if source_kind not in SOURCE_KINDS:
        raise ShadowValidationError("unknown source_kind: {!r}".format(raw.get("source_kind")))
    service = _canonical_service(raw.get("service"))
    connection = _canonical_connection(raw.get("connection"))
    self_process = raw.get("self_process", False)
    if not isinstance(self_process, bool):
        raise ShadowValidationError("self_process must be boolean")
    result: Dict[str, Any] = {
        "schema": SHADOW_PACKET_SCHEMA,
        "id": packet_id,
        "family": family,
        "direction": direction,
        "protocol": protocol,
        "src": src,
        "dst": dst,
        "source_kind": source_kind,
        "service": service,
        "connection": connection,
        "self_process": self_process,
    }
    for key in ("src_port", "dst_port"):
        value = raw.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 65535):
            raise ShadowValidationError("invalid {}: {!r}".format(key, value))
        result[key] = value
    if raw.get("iifname") is not None:
        if not isinstance(raw["iifname"], str) or not raw["iifname"].strip():
            raise ShadowValidationError("iifname must be non-empty")
        result["iifname"] = raw["iifname"].strip()
    else:
        result["iifname"] = ""
    if raw.get("icmpv6_type") is not None:
        icmp_type = _norm(raw["icmpv6_type"]).replace(" ", "_")
        if icmp_type not in ICMPV6_CONTROL_TYPES and icmp_type != "ECHO_REQUEST":
            raise ShadowValidationError("unknown icmpv6_type: {!r}".format(raw["icmpv6_type"]))
        if family != "IPv6" or protocol != "ICMPv6":
            raise ShadowValidationError("icmpv6_type requires an IPv6 ICMPv6 packet")
        result["icmpv6_type"] = icmp_type
    else:
        result["icmpv6_type"] = ""
    return result


def _contains(collection: Sequence[str], address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return any(ip in ipaddress.ip_network(item) for item in collection)


def _contains_host(collection: Sequence[str], address: str) -> bool:
    return address in set(collection)


def _access_match(collection: Sequence[Mapping[str, str]], address: str) -> Optional[str]:
    ip = ipaddress.ip_address(address)
    actions = {entry["action"] for entry in collection if ip in ipaddress.ip_network(entry["network"])}
    if not actions:
        return None
    if len(actions) > 1:
        raise ShadowValidationError("overlapping access actions are ambiguous")
    return next(iter(actions))


def _dns_in_scope(state: Mapping[str, Any], packet: Mapping[str, Any]) -> bool:
    port_dns = packet.get("src_port") == 53 or packet.get("dst_port") == 53
    explicit_dns = packet.get("service") == "DNS"
    if not (port_dns or explicit_dns):
        return False
    scope = state["dns_scope"]
    if scope == "NONE":
        return False
    if packet["direction"] == "ROUTER_OUTPUT" and not state["router_self_proxy"]:
        # Port 53 alone is not enough to claim router DNS ownership.  The
        # normalized state must say that OpenKill is proxying router-originated
        # DNS; LAN DNS remains independently scoped below.
        return False
    if scope == "LAN":
        return packet["direction"] == "LAN_INGRESS"
    if scope == "ROUTER_ONLY":
        return packet["direction"] == "ROUTER_OUTPUT"
    return packet["direction"] in {"LAN_INGRESS", "ROUTER_OUTPUT"}


def _source_properties(state: Mapping[str, Any], packet: Mapping[str, Any]) -> Set[str]:
    if packet.get("self_process") or packet.get("source_kind") == "SELF_PROCESS":
        return {"SELF_PROCESS"}
    source_kind = packet.get("source_kind")
    if source_kind == "UNKNOWN":
        if packet["direction"] == "LAN_INGRESS":
            return {"LAN"}
        if packet["direction"] == "ROUTER_OUTPUT":
            return {"ROUTER"}
        return {"UNKNOWN"}
    if source_kind == "LAN" and packet["direction"] not in {"LAN_INGRESS", "UNKNOWN"}:
        raise ShadowValidationError("LAN source_kind conflicts with direction")
    if source_kind == "ROUTER" and packet["direction"] == "LAN_INGRESS":
        raise ShadowValidationError("ROUTER source_kind conflicts with LAN ingress")
    return {source_kind}


def derive_packet_facts(state_raw: Mapping[str, Any], packet_raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Derive facts from normalized state and a packet, without decisions."""

    state = normalize_state(state_raw)
    packet = normalize_packet(packet_raw)
    if packet["direction"] == "TUN_INGRESS" and packet.get("iifname") != state["tun_interface"]:
        raise ShadowValidationError("TUN ingress interface does not match configured TUN")
    family = packet["family"]
    suffix = "4" if family == "IPv4" else "6"
    dst = packet["dst"]
    source_props = _source_properties(state, packet)
    destination_props: Set[str] = set()
    if _contains_host(state["node" + suffix], dst):
        destination_props.add("NODE_ENDPOINT")
    if _contains_host(state["wan" + suffix], dst):
        destination_props.add("WAN_HOST")
    if _contains(state["lan" + suffix], dst):
        destination_props.add("LAN_PREFIX")
    if family == "IPv6" and _contains(state["delegated6"], dst):
        destination_props.add("DELEGATED_PREFIX")
    if _contains(state["local" + suffix], dst):
        destination_props.add("LOCAL_PRIVATE")
    if _contains(state["china" + suffix], dst):
        destination_props.add("CHINA")
    if _contains(state["user_direct" + suffix], dst):
        destination_props.add("USER_DIRECT")
    if _contains(state["user_proxy" + suffix], dst):
        destination_props.add("USER_PROXY")
    if _contains(state["fake_ip" + suffix], dst):
        destination_props.add("FAKEIP")
    access_action = _access_match(state["access" + suffix], dst)
    semantic_flags: Set[str] = set()
    if "SELF_PROCESS" in source_props:
        semantic_flags.add("SELF_TRAFFIC")
    if packet["direction"] == "TUN_INGRESS":
        semantic_flags.add("TUN_INGRESS")
    if packet["connection"] == "REPLY":
        semantic_flags.add("REPLY_TRAFFIC")
    if destination_props & {"NODE_ENDPOINT"}:
        semantic_flags.add("NODE_ENDPOINT")
    if destination_props & {"WAN_HOST", "LAN_PREFIX", "DELEGATED_PREFIX", "LOCAL_PRIVATE"}:
        semantic_flags.add("LOCAL_DESTINATION")
    if destination_props & {"USER_DIRECT"}:
        semantic_flags.add("EXPLICIT_DIRECT")
    if destination_props & {"USER_PROXY"}:
        semantic_flags.add("EXPLICIT_PROXY")
    if destination_props & {"FAKEIP"}:
        semantic_flags.add("FAKEIP")
    if access_action is not None:
        # ACL membership is a separate fact from topology.  An ALLOW/BYPASS
        # entry must not be converted into LOCAL_DESTINATION; routing policy
        # remains the classifier's responsibility.
        semantic_flags.add("ACCESS_CONTROL")
        semantic_flags.add("CUSTOM_ACCESS")
        if access_action == "DENY":
            semantic_flags.add("ACCESS_DENY")
    china_pass = _contains(state["china_pass" + suffix], dst)
    if china_pass:
        semantic_flags.add("CHINA_PASS")
    # A literal membership in the configured China set is a fact.  The
    # classifier derives the complementary overseas-policy match from the
    # policy field; adding a synthetic flag here would invert that meaning.
    if "CHINA" in destination_props:
        semantic_flags.add("CHINA_POLICY")
    if packet.get("src_port") in state["service_ports"] or packet.get("dst_port") in state["service_ports"]:
        semantic_flags.add("SERVICE_PORT")
    control = False
    if family == "IPv6" and packet["protocol"] == "ICMPv6" and packet.get("icmpv6_type") in ICMPV6_CONTROL_TYPES:
        control = True
    if family == "IPv6" and packet["service"] == "DHCPv6":
        control = True
    if family == "IPv6" and packet["protocol"] == "UDP" and {packet.get("src_port"), packet.get("dst_port")} & {546, 547}:
        control = True
    if control:
        semantic_flags.add("CONTROL_PROTOCOL")
    if _dns_in_scope(state, packet):
        semantic_flags.add("DNS")
        service = "DNS"
    else:
        service = packet["service"]
    if not destination_props:
        destination_props.add("PUBLIC")
    flag_order = (
        "DNS", "CONTROL_PROTOCOL", "SELF_TRAFFIC", "TUN_INGRESS", "NODE_ENDPOINT",
        "LOCAL_DESTINATION", "REPLY_TRAFFIC", "SERVICE_PORT", "ACCESS_CONTROL",
        "CUSTOM_ACCESS", "ACCESS_DENY", "FAKEIP", "EXPLICIT_DIRECT", "EXPLICIT_PROXY", "CHINA_PASS",
        "CHINA_POLICY",
    )
    return {
        "source_properties": sorted(source_props),
        "destination_properties": sorted(destination_props),
        "semantic_flags": [item for item in flag_order if item in semantic_flags],
        "access_action": access_action,
        "china_pass": china_pass,
        "dns_in_scope": "DNS" in semantic_flags,
        "control_protocol": control,
        "service": service,
        "packet": packet,
        "state_id": state["id"],
    }


def build_context(state_raw: Mapping[str, Any], packet_raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Build a classifier-compatible PacketContext from facts."""

    state = normalize_state(state_raw)
    facts = derive_packet_facts(state, packet_raw)
    packet = facts["packet"]
    return {
        "family": packet["family"],
        "direction": packet["direction"],
        "protocol": packet["protocol"],
        "owner": state["owner"],
        "backend_mode": state["run_mode"],
        "source_properties": facts["source_properties"],
        "destination_properties": facts["destination_properties"],
        "service": facts["service"] if "service" in facts else ("DNS" if facts["dns_in_scope"] else packet["service"]),
        "connection": packet["connection"],
        "flags": facts["semantic_flags"],
        "china_policy": state["china_policy"],
        "icmpv6_type": packet.get("icmpv6_type", ""),
    }


def adapt(state_raw: Mapping[str, Any], packet_raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Return facts and context together for audit/reporting."""

    facts = derive_packet_facts(state_raw, packet_raw)
    state = normalize_state(state_raw)
    packet = facts["packet"]
    context = {
        "family": packet["family"],
        "direction": packet["direction"],
        "protocol": packet["protocol"],
        "owner": state["owner"],
        "backend_mode": state["run_mode"],
        "source_properties": facts["source_properties"],
        "destination_properties": facts["destination_properties"],
        "service": "DNS" if facts["dns_in_scope"] else packet["service"],
        "connection": packet["connection"],
        "flags": facts["semantic_flags"],
        "china_policy": state["china_policy"],
        "icmpv6_type": packet.get("icmpv6_type", ""),
    }
    return {"state_id": state["id"], "packet_id": packet["id"], "facts": facts, "context": context}


def validate_intent_fixture(fixture: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate the independent current-intent oracle."""

    if not isinstance(fixture, Mapping) or fixture.get("schema") != "OPENKILL_CURRENT_INTENT_V1":
        raise ShadowComparisonError("unsupported intent fixture schema")
    if fixture.get("contract_version") != SHADOW_CONTRACT_VERSION:
        raise ShadowComparisonError("intent fixture contract version mismatch")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ShadowComparisonError("intent cases missing")
    seen: Set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping):
            raise ShadowComparisonError("intent case must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ShadowComparisonError("duplicate/missing intent id: {}".format(case_id))
        seen.add(case_id)
        if not isinstance(case.get("state_id"), str):
            raise ShadowComparisonError("{} state_id missing".format(case_id))
        if not isinstance(case.get("packet"), Mapping):
            raise ShadowComparisonError("{} packet missing".format(case_id))
        try:
            normalize_packet(case["packet"])
        except ShadowValidationError as exc:
            raise ShadowComparisonError("{} packet: {}".format(case_id, exc))
        expected = case.get("independent_expected_current")
        if not isinstance(expected, Mapping):
            raise ShadowComparisonError("{} independent expectation missing".format(case_id))
        result = expected.get("result")
        if result not in SHADOW_RESULTS:
            raise ShadowComparisonError("{} unknown shadow result".format(case_id))
        confidence = expected.get("confidence", "HIGH")
        if confidence not in CONFIDENCE_VALUES:
            raise ShadowComparisonError("{} unknown confidence".format(case_id))
        classifier_expected = expected.get("classifier")
        if result not in {"INVALID_STATE", "NOT_APPLICABLE", "UNMAPPED_STATE"} and not isinstance(classifier_expected, Mapping):
            raise ShadowComparisonError("{} classifier expectation missing".format(case_id))
        if classifier_expected is not None:
            if not isinstance(classifier_expected, Mapping) or set(classifier_expected) != {"status", "reason", "decision"}:
                raise ShadowComparisonError("{} classifier expectation fields invalid".format(case_id))
            if classifier_expected.get("status") not in _INTENT_STATUSES:
                raise ShadowComparisonError("{} unknown classifier status".format(case_id))
            if classifier_expected.get("reason") not in _INTENT_REASONS:
                raise ShadowComparisonError("{} unknown classifier reason".format(case_id))
            if classifier_expected.get("decision") not in _INTENT_DECISIONS and classifier_expected.get("decision") is not None:
                raise ShadowComparisonError("{} unknown classifier decision".format(case_id))
        expected_matches = expected.get("expected_matches")
        if expected_matches is not None:
            if not isinstance(expected_matches, list) or len(expected_matches) != len(set(expected_matches)):
                raise ShadowComparisonError("{} expected_matches must be a unique list".format(case_id))
            if any(item not in _INTENT_MATCHES for item in expected_matches):
                raise ShadowComparisonError("{} unknown expected match".format(case_id))
        if result == "EXPECTED_CURRENT_GAP":
            gap = expected.get("known_gap")
            if gap not in {"BC-01", "BC-02", "BC-03", "BC-04", "BC-05", "BC-06", "BC-07"}:
                raise ShadowComparisonError("{} expected gap must name BC-01..BC-07".format(case_id))
            if classifier_expected is not None and classifier_expected.get("status") != "CURRENT_UNDEFINED":
                raise ShadowComparisonError("{} expected gap must carry CURRENT_UNDEFINED".format(case_id))
        if result == "INVALID_STATE" and classifier_expected is not None and classifier_expected.get("status") != "INVALID_CONFIGURATION":
            raise ShadowComparisonError("{} invalid state must carry INVALID_CONFIGURATION".format(case_id))
        candidate = case.get("behavior_change_candidate")
        if candidate is not None:
            if not isinstance(candidate, Mapping) or set(candidate) != {"id", "status"}:
                raise ShadowComparisonError("{} behavior-change candidate fields invalid".format(case_id))
            if candidate.get("id") not in {"BC-01", "BC-02", "BC-03", "BC-04", "BC-05", "BC-06", "BC-07"}:
                raise ShadowComparisonError("{} unknown behavior-change candidate".format(case_id))
            if candidate.get("status") != "PRODUCTION_NOT_APPROVED":
                raise ShadowComparisonError("{} behavior-change candidate must remain unapproved".format(case_id))
        if "target" in expected or "expected_target" in case:
            raise ShadowComparisonError("{} current intent must not contain target expectations".format(case_id))
        for key in ("production_component", "production_reference", "evidence"):
            if not isinstance(case.get(key), str) or not case[key]:
                raise ShadowComparisonError("{} {} missing".format(case_id, key))
    return dict(fixture)


def shadow_compare(
    state_raw: Mapping[str, Any],
    packet_raw: Mapping[str, Any],
    intent_case: Mapping[str, Any],
) -> Dict[str, Any]:
    """Compare adapter facts/classifier output with independent intent."""

    from openkill_classifier_model import classify  # development-only import

    expected = intent_case["independent_expected_current"]
    try:
        adapted = adapt(state_raw, packet_raw)
    except ShadowValidationError as exc:
        if expected.get("result") == "INVALID_STATE":
            return {
                "id": intent_case["id"],
                "result": "INVALID_STATE",
                "mismatch": None,
                "error": str(exc),
            }
        return {
            "id": intent_case["id"],
            "result": "SEMANTIC_MISMATCH",
            "mismatch": {"type": "ADAPTER_DEFECT", "detail": str(exc)},
            "error": str(exc),
        }

    facts = adapted["facts"]
    expected_matches = expected.get("expected_matches")
    if expected_matches is not None:
        if sorted(expected_matches) != sorted(facts["semantic_flags"]):
            return {
                "id": intent_case["id"],
                "result": "SEMANTIC_MISMATCH",
                "mismatch": {
                    "type": "ADAPTER_DEFECT",
                    "detail": "semantic facts differ",
                    "expected": expected_matches,
                    "actual": facts["semantic_flags"],
                },
                "adapted": adapted,
            }
    try:
        classification = classify(adapted["context"], profile="current", trace=True)
    except (ValueError, TypeError) as exc:
        return {
            "id": intent_case["id"],
            "result": "SEMANTIC_MISMATCH",
            "mismatch": {"type": "CLASSIFIER_CONTRACT_DEFECT", "detail": str(exc)},
            "adapted": adapted,
        }
    actual = classification.as_dict()
    expected_classifier = expected.get("classifier")
    if expected_classifier is not None and actual != dict(expected_classifier):
        mismatch_type = "PRODUCTION_AMBIGUITY" if expected.get("result") == "UNMAPPED_STATE" else "CLASSIFIER_CONTRACT_DEFECT"
        return {
            "id": intent_case["id"],
            "result": "SEMANTIC_MISMATCH",
            "mismatch": {"type": mismatch_type, "expected": expected_classifier, "actual": actual},
            "adapted": adapted,
            "classification": classification.to_record(),
        }
    result = expected.get("result", "MATCH")
    if result not in {"MATCH", "EXPECTED_CURRENT_GAP", "UNMAPPED_STATE", "INVALID_STATE", "NOT_APPLICABLE"}:
        raise ShadowComparisonError("unsupported comparison result: {}".format(result))
    return {
        "id": intent_case["id"],
        "result": result,
        "mismatch": None,
        "adapted": adapted,
        "classification": classification.to_record(),
    }


def preview_target(context: Mapping[str, Any]) -> Dict[str, Any]:
    """Show current/target outcomes without changing production behavior."""

    from openkill_classifier_model import classify

    current = classify(context, profile="current", trace=True)
    target = classify(context, profile="target", trace=True)
    return {
        "current": current.to_record(),
        "target": target.to_record(),
        "changed": current.to_record() != target.to_record(),
    }


@dataclass(frozen=True)
class ShadowCase:
    """Convenience record for callers that do not need fixture metadata."""

    state_id: str
    packet_id: str
    context: Mapping[str, Any]
    facts: Mapping[str, Any]


__all__ = [
    "ACCESS_ACTIONS",
    "CONFIDENCE_VALUES",
    "SHADOW_CONTRACT_VERSION",
    "SHADOW_EXECUTION_CONTRACT_VERSION",
    "DEFAULT_PROXY_PORTS",
    "SHADOW_FIXTURE_SCHEMA",
    "SHADOW_PACKET_SCHEMA",
    "SHADOW_RESULTS",
    "SHADOW_STATE_SCHEMA",
    "ShadowCase",
    "ShadowComparisonError",
    "ShadowValidationError",
    "adapt",
    "build_context",
    "derive_packet_facts",
    "normalize_packet",
    "normalize_state",
    "preview_target",
    "shadow_compare",
    "validate_intent_fixture",
    "validate_state_fixture",
]
