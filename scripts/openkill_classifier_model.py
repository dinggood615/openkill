#!/usr/bin/env python3
"""Pure, backend-neutral shared classifier model used by development tests.

This module is intentionally detached from OpenKill's OpenWrt runtime.  It
accepts an in-memory packet context, detects semantic matches, and resolves a
single decision using either the current production oracle or the approved
Phase 2A target profile.  It never executes commands, opens files, accesses a
network, or mutates process state.
"""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


CLASSIFIER_CONTRACT_VERSION = 1
PROFILE_VALUES: Tuple[str, ...] = ("current", "target")

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

# These labels describe semantic layers in the audited generated chains.  A
# few labels retain a family or implementation detail so that the current
# oracle can faithfully record today's behavior without adding it to the
# public reason enum.
CURRENT_PRECEDENCE: Tuple[str, ...] = (
    "OWNER_DISABLED",
    "DNS",
    "NODE_ENDPOINT",
    "ACCESS_CONTROL_CUSTOM",
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

PRECEDENCE_TABLES = {
    "current": CURRENT_PRECEDENCE,
    "target": TARGET_PRECEDENCE,
}

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

_NORMALIZED_DIMENSIONS: Dict[str, Tuple[str, ...]] = {
    key: tuple(str(item).strip().upper().replace("-", "_") for item in values)
    for key, values in PACKET_CONTEXT_DIMENSIONS.items()
}

_KNOWN_FLAGS: Tuple[str, ...] = (
    "DNS",
    "CONTROL_PROTOCOL",
    "SELF_TRAFFIC",
    "TUN_INGRESS",
    "NODE_ENDPOINT",
    "LOCAL_DESTINATION",
    "REPLY_TRAFFIC",
    "SERVICE_PORT",
    "ACCESS_CONTROL",
    "ACCESS_DENY",
    "CUSTOM_ACCESS",
    "FAKEIP",
    "EXPLICIT_DIRECT",
    "EXPLICIT_PROXY",
    "CHINA_PASS",
    "CHINA_POLICY",
)
_KNOWN_FLAG_SET = frozenset(_KNOWN_FLAGS)

_FLAG_ALIASES = {
    # Canonical names are accepted too; aliases make the in-memory API easy
    # to use without permitting arbitrary/unknown flags.
    "DNS": "DNS",
    "CONTROL": "CONTROL_PROTOCOL",
    "CONTROL_PROTOCOL": "CONTROL_PROTOCOL",
    "CONTROL_PROTOCOL_IPV6": "CONTROL_PROTOCOL",
    "SELF": "SELF_TRAFFIC",
    "SELF_TRAFFIC": "SELF_TRAFFIC",
    "TUN": "TUN_INGRESS",
    "TUN_INGRESS": "TUN_INGRESS",
    "NODE": "NODE_ENDPOINT",
    "NODE_ENDPOINT": "NODE_ENDPOINT",
    "LOCAL": "LOCAL_DESTINATION",
    "LOCAL_DESTINATION": "LOCAL_DESTINATION",
    "REPLY": "REPLY_TRAFFIC",
    "REPLY_TRAFFIC": "REPLY_TRAFFIC",
    "SERVICE": "SERVICE_PORT",
    "SERVICE_PORT": "SERVICE_PORT",
    "ACCESS": "ACCESS_CONTROL",
    "ACCESS_BYPASS": "ACCESS_CONTROL",
    "ACCESS_CONTROL": "ACCESS_CONTROL",
    "ACCESS_DENY": "ACCESS_DENY",
    "CUSTOM_ACCESS": "CUSTOM_ACCESS",
    "FAKE_IP": "FAKEIP",
    "FAKEIP": "FAKEIP",
    "FAKEIP6": "FAKEIP",
    "USER_DIRECT": "EXPLICIT_DIRECT",
    "EXPLICIT_DIRECT": "EXPLICIT_DIRECT",
    "DIRECT": "EXPLICIT_DIRECT",
    "USER_PROXY": "EXPLICIT_PROXY",
    "EXPLICIT_PROXY": "EXPLICIT_PROXY",
    "PROXY": "EXPLICIT_PROXY",
    "CHINA": "CHINA_POLICY",
    "CHINA_POLICY": "CHINA_POLICY",
    "CHINA_PASS": "CHINA_PASS",
}

_CHINA_POLICIES = frozenset(
    ("OFF", "BYPASS_MAINLAND", "MAINLAND", "1", "BYPASS_OVERSEAS", "OVERSEAS", "2")
)
_ICMPV6_TYPES = frozenset(
    ("RS", "RA", "NS", "NA", "PTB", "DESTINATION_UNREACHABLE", "TIME_EXCEEDED", "PARAMETER_PROBLEM")
)


class ContextValidationError(ValueError):
    """Raised when a classifier context is not part of the contract schema."""


class FixtureValidationError(ValueError):
    """Raised when a semantic contract fixture is malformed or unversioned."""


@dataclass(frozen=True)
class Classification:
    """A semantic result; backend syntax is deliberately absent."""

    status: str
    reason: Optional[str]
    decision: Optional[str]
    matched_rule: Optional[str] = None
    precedence_index: Optional[int] = None
    trace: Tuple[str, ...] = ()

    # Keep Phase 2A's compact representation as the default so existing
    # fixture consumers remain stable.  Extended callers can request the
    # machine-readable rule position and trace explicitly.
    def as_dict(self, include_details: bool = False, include_trace: bool = False) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "status": self.status,
            "reason": self.reason,
            "decision": self.decision,
        }
        if include_details:
            result["matched_rule"] = self.matched_rule
            result["precedence_index"] = self.precedence_index
        if include_trace:
            result["trace"] = list(self.trace)
        return result

    def to_record(self, include_trace: bool = True) -> Dict[str, Any]:
        """Return the complete stable API record for new consumers."""

        return self.as_dict(include_details=True, include_trace=include_trace)


def _norm(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_")


def _canonical_dimension(key: str, value: Any, default: str) -> str:
    normalized = _norm(default if value is None else value)
    allowed = _NORMALIZED_DIMENSIONS[key]
    if normalized not in allowed:
        raise ContextValidationError("unknown {}: {!r}".format(key, value))
    return normalized


def _canonical_property_values(key: str, value: Any, default: Sequence[str]) -> Tuple[str, ...]:
    if value is None:
        values: Sequence[Any] = default
    elif isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        values = tuple(value)
    else:
        raise ContextValidationError("{} must be a string or property sequence".format(key))
    allowed = set(_NORMALIZED_DIMENSIONS[key])
    normalized: Set[str] = set()
    for item in values:
        candidate = _norm(item)
        if candidate not in allowed:
            raise ContextValidationError("unknown {} value: {!r}".format(key, item))
        normalized.add(candidate)
    if not normalized:
        raise ContextValidationError("{} cannot be empty".format(key))
    return tuple(sorted(normalized))


def _canonical_flag(value: Any) -> str:
    candidate = _norm(value).replace(" ", "_")
    try:
        return _FLAG_ALIASES[candidate]
    except KeyError:
        raise ContextValidationError("unknown flag: {!r}".format(value))


def _flags(raw: Mapping[str, Any], strict: bool = False) -> Set[str]:
    values: Set[str] = set()
    supplied = raw.get("flags", ())
    if supplied is None:
        supplied = ()
    if isinstance(supplied, str):
        if strict:
            raise ContextValidationError("flags must be a sequence, not a string")
        supplied = (supplied,)
    if not isinstance(supplied, (list, tuple, set, frozenset)):
        raise ContextValidationError("flags must be a sequence")
    for item in supplied:
        values.add(_canonical_flag(item))

    flat_aliases = {
        "dns": "DNS",
        "control": "CONTROL_PROTOCOL",
        "control_protocol": "CONTROL_PROTOCOL",
        "self_traffic": "SELF_TRAFFIC",
        "tun_ingress": "TUN_INGRESS",
        "node_endpoint": "NODE_ENDPOINT",
        "local_destination": "LOCAL_DESTINATION",
        "reply": "REPLY_TRAFFIC",
        "service_port": "SERVICE_PORT",
        "access_bypass": "ACCESS_CONTROL",
        "access_control": "ACCESS_CONTROL",
        "access_deny": "ACCESS_DENY",
        "fakeip": "FAKEIP",
        "fakeip6": "FAKEIP",
        "user_direct": "EXPLICIT_DIRECT",
        "explicit_direct": "EXPLICIT_DIRECT",
        "user_proxy": "EXPLICIT_PROXY",
        "explicit_proxy": "EXPLICIT_PROXY",
        "china": "CHINA_POLICY",
        "china_pass": "CHINA_PASS",
        "custom_access": "CUSTOM_ACCESS",
    }
    for key, flag in flat_aliases.items():
        if raw.get(key):
            values.add(flag)

    service = _norm(raw.get("service"))
    if service in {"DNS", "DNS_UDP", "DNS_TCP"}:
        values.add("DNS")
    if service in {"DHCPV6", "ICMPV6_CONTROL"}:
        values.add("CONTROL_PROTOCOL")
    if raw.get("icmpv6_type"):
        values.add("CONTROL_PROTOCOL")

    # Semantic properties may be supplied directly by future context
    # adapters.  They are equivalent to the explicit fixture flags.
    source = raw.get("source_properties") or ()
    source_values = (source,) if isinstance(source, str) else tuple(source)
    destination = raw.get("destination_properties") or ()
    destination_values = (destination,) if isinstance(destination, str) else tuple(destination)
    source_norm = {_norm(item) for item in source_values}
    destination_norm = {_norm(item) for item in destination_values}
    if "SELF_PROCESS" in source_norm:
        values.add("SELF_TRAFFIC")
    if _norm(raw.get("direction")) == "TUN_INGRESS":
        values.add("TUN_INGRESS")
    if "REPLY" == _norm(raw.get("connection")):
        values.add("REPLY_TRAFFIC")
    if destination_norm & {"NODE_ENDPOINT"}:
        values.add("NODE_ENDPOINT")
    if destination_norm & {"LOCAL_PRIVATE", "WAN_HOST", "LAN_PREFIX", "DELEGATED_PREFIX"}:
        values.add("LOCAL_DESTINATION")
    if "CHINA" in destination_norm:
        values.add("CHINA_POLICY")
    if "USER_DIRECT" in destination_norm:
        values.add("EXPLICIT_DIRECT")
    if "USER_PROXY" in destination_norm:
        values.add("EXPLICIT_PROXY")
    if "FAKEIP" in destination_norm:
        values.add("FAKEIP")

    if not values.issubset(_KNOWN_FLAG_SET):
        # This should only be reachable if the alias table is accidentally
        # edited; retaining the guard makes the contract fail closed.
        raise ContextValidationError("unknown semantic flag")
    return values


def _normalize_context(raw: Mapping[str, Any], strict: bool) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ContextValidationError("context must be a mapping")
    context: Dict[str, Any] = dict(raw)
    required = ("family", "direction", "protocol")
    if strict:
        missing = [key for key in required if key not in raw]
        if missing:
            raise ContextValidationError("missing context field(s): {}".format(", ".join(missing)))

    context["family"] = _canonical_dimension("family", context.get("family"), "")
    context["direction"] = _canonical_dimension("direction", context.get("direction"), "UNKNOWN")
    context["protocol"] = _canonical_dimension("protocol", context.get("protocol"), "OTHER")
    # Preserve the Phase 2A convenience that an omitted/empty owner denotes
    # the OpenKill-owned classifier; explicit non-empty unknown owners remain
    # fail-closed via the dimension validator.
    context["owner"] = _canonical_dimension("owner", context.get("owner") or "OPENKILL", "OPENKILL")
    context["backend_mode"] = _canonical_dimension("backend_mode", context.get("backend_mode"), "TUN")
    context["service"] = _canonical_dimension("service", context.get("service"), "OTHER")
    context["connection"] = _canonical_dimension("connection", context.get("connection"), "UNKNOWN")
    context["source_properties"] = _canonical_property_values(
        "source_properties", context.get("source_properties"), ("UNKNOWN",)
    )
    context["destination_properties"] = _canonical_property_values(
        "destination_properties", context.get("destination_properties"), ("PUBLIC",)
    )
    context["china_policy"] = _norm(context.get("china_policy") or "OFF")
    if context["china_policy"] not in _CHINA_POLICIES:
        raise ContextValidationError("unknown china_policy: {!r}".format(context.get("china_policy")))
    if context.get("icmpv6_type"):
        icmp_type = _norm(context["icmpv6_type"]).replace(" ", "_")
        if icmp_type not in _ICMPV6_TYPES:
            raise ContextValidationError("unknown icmpv6_type: {!r}".format(context["icmpv6_type"]))
        context["icmpv6_type"] = icmp_type
    context["flags"] = frozenset(_flags(context, strict=strict))

    # A protocol/family mismatch is an input error.  IPv6 may use the generic
    # ICMP label in fixture shorthand, but IPv4 cannot carry ICMPv6.
    if context["family"] == "IPV4" and context["protocol"] == "ICMPV6":
        raise ContextValidationError("ICMPv6 is only valid for IPv6 contexts")
    return context


def normalize_context(raw: Mapping[str, Any], strict: bool = False) -> Dict[str, Any]:
    """Return a canonical context; ``strict=True`` enforces the public API."""

    return _normalize_context(raw, strict=strict)


def validate_context(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and canonicalize a public classifier context."""

    return _normalize_context(raw, strict=True)


def _invalid(trace: Iterable[str] = ()) -> Classification:
    return Classification("INVALID_CONFIGURATION", "INVALID_CONFIGURATION", None, trace=tuple(trace))


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


def _match_reasons(context: Mapping[str, Any]) -> Tuple[str, ...]:
    """Detect every semantic match in a stable order, without selecting one."""

    flags = context["flags"]
    matches: Set[str] = set()
    if _owner_disabled(context):
        matches.add("OWNER_DISABLED")
    if "DNS" in flags:
        matches.add("DNS")
    if "CONTROL_PROTOCOL" in flags:
        matches.add("CONTROL_PROTOCOL")
    if "SELF_TRAFFIC" in flags:
        matches.add("SELF_TRAFFIC")
    if "TUN_INGRESS" in flags:
        matches.add("TUN_INGRESS")
    if "NODE_ENDPOINT" in flags:
        matches.add("NODE_ENDPOINT")
    if "LOCAL_DESTINATION" in flags:
        matches.add("LOCAL_DESTINATION")
    if "REPLY_TRAFFIC" in flags:
        matches.add("REPLY_TRAFFIC")
    if "SERVICE_PORT" in flags:
        matches.add("SERVICE_PORT")
    if "ACCESS_CONTROL" in flags or "CUSTOM_ACCESS" in flags:
        matches.add("ACCESS_CONTROL")
    if "FAKEIP" in flags:
        matches.add("FAKEIP")
    if "EXPLICIT_DIRECT" in flags:
        matches.add("EXPLICIT_DIRECT")
    if "EXPLICIT_PROXY" in flags:
        matches.add("EXPLICIT_PROXY")
    if "CHINA_PASS" in flags:
        matches.add("CHINA_PASS")
    if "CHINA_POLICY" in flags or _china_direct_match(context):
        matches.add("CHINA_POLICY")
    order = (
        "OWNER_DISABLED", "DNS", "CONTROL_PROTOCOL", "SELF_TRAFFIC", "TUN_INGRESS",
        "NODE_ENDPOINT", "LOCAL_DESTINATION", "REPLY_TRAFFIC", "SERVICE_PORT",
        "ACCESS_CONTROL", "FAKEIP", "EXPLICIT_DIRECT", "EXPLICIT_PROXY",
        "CHINA_PASS", "CHINA_POLICY",
    )
    return tuple(item for item in order if item in matches)


def detect_matches(raw: Mapping[str, Any]) -> Tuple[str, ...]:
    """Public shared match detector; result is deterministic and backend-free."""

    return _match_reasons(validate_context(raw))


def _rule_matches(label: str, context: Mapping[str, Any], matches: Set[str], profile: str) -> bool:
    if label == "OWNER_DISABLED":
        return "OWNER_DISABLED" in matches
    if label == "DNS":
        return "DNS" in matches
    if label == "ACCESS_CONTROL_CUSTOM":
        return "CUSTOM_ACCESS" in context["flags"]
    if label == "CONTROL_PROTOCOL_IPV6":
        return context["family"] == "IPV6" and "CONTROL_PROTOCOL" in matches
    if label == "CONTROL_PROTOCOL":
        return "CONTROL_PROTOCOL" in matches and context["family"] == "IPV6"
    if label == "TUN_INGRESS":
        # The current oracle intentionally retains the observed IPv6 TUN gap.
        return "TUN_INGRESS" in matches and (profile == "target" or context["family"] != "IPV6")
    if label == "ACCESS_CONTROL":
        return "ACCESS_CONTROL" in matches
    if label == "CHINA_PASS_FALLTHROUGH":
        return "CHINA_PASS" in matches
    if label == "CHINA_PASS":
        return "CHINA_PASS" in matches and context.get("china_policy") != "OFF"
    if label == "CHINA_POLICY":
        return _china_direct_match(context)
    if label == "EXPLICIT_DIRECT":
        return "EXPLICIT_DIRECT" in matches
    if label == "EXPLICIT_PROXY":
        return "EXPLICIT_PROXY" in matches
    if label == "DEFAULT_POLICY":
        return True
    return label in matches


def _decision_for(label: str, context: Mapping[str, Any]) -> Tuple[str, str]:
    if label == "OWNER_DISABLED":
        return "OWNER_DISABLED", "NOT_OWNED"
    if label == "DNS":
        return "DNS", "DNS_SPECIAL"
    if label in {
        "CONTROL_PROTOCOL", "CONTROL_PROTOCOL_IPV6", "SELF_TRAFFIC", "TUN_INGRESS",
        "NODE_ENDPOINT", "LOCAL_DESTINATION", "REPLY_TRAFFIC", "SERVICE_PORT",
    }:
        return label.replace("_IPV6", ""), "BYPASS"
    if label in {"ACCESS_CONTROL", "ACCESS_CONTROL_CUSTOM"}:
        return "ACCESS_CONTROL", "ACCESS_DENY" if "ACCESS_DENY" in context["flags"] else "BYPASS"
    if label == "FAKEIP":
        return "FAKEIP", "PROXY"
    if label == "EXPLICIT_DIRECT":
        return "EXPLICIT_DIRECT", "DIRECT"
    if label == "EXPLICIT_PROXY":
        return "EXPLICIT_PROXY", "PROXY"
    if label == "CHINA_PASS":
        return "CHINA_PASS", "PROXY"
    if label == "CHINA_POLICY":
        return "CHINA_POLICY", "DIRECT"
    return "DEFAULT_POLICY", "PROXY"


def _classify(raw: Mapping[str, Any], profile: str, trace: bool = False) -> Classification:
    context = validate_context(raw)
    matches_tuple = _match_reasons(context)
    matches = set(matches_tuple)
    trace_items: List[str] = list("MATCH:" + item for item in matches_tuple)

    # Owner is a gate before configuration conflicts, matching the audited
    # production behavior and preserving the Phase 2A oracle.
    if "OWNER_DISABLED" not in matches and {"EXPLICIT_DIRECT", "EXPLICIT_PROXY"}.issubset(matches):
        if trace:
            trace_items.append("INVALID:EXPLICIT_DIRECT+EXPLICIT_PROXY")
        return _invalid(trace_items if trace else ())

    rules = PRECEDENCE_TABLES[profile]
    selected_label: Optional[str] = None
    selected_index: Optional[int] = None
    for index, label in enumerate(rules):
        if _rule_matches(label, context, matches, profile):
            # Current CHINA_PASS is an explicit exclusion from the direct
            # China return rule; it records a match but intentionally falls
            # through to the default proxy action.
            if label == "CHINA_PASS_FALLTHROUGH":
                if trace:
                    trace_items.append("MATCH_RULE:" + label)
                continue
            selected_label = label
            selected_index = index
            break
    if selected_label is None:  # Defensive; DEFAULT_POLICY is unconditional.
        selected_label = "DEFAULT_POLICY"
        selected_index = len(rules) - 1
    reason, decision = _decision_for(selected_label, context)
    status = "VALID"
    if profile == "current" and selected_label == "DEFAULT_POLICY" and {
        "EXPLICIT_DIRECT", "EXPLICIT_PROXY"
    }.intersection(matches):
        status = "CURRENT_UNDEFINED"
    if trace:
        trace_items.append("SELECT:" + selected_label)
        trace_items.append("REASON:" + reason)
        trace_items.append("DECISION:" + decision)
    return Classification(status, reason, decision, selected_label, selected_index, tuple(trace_items) if trace else ())


def _canonical_profile(profile: str) -> str:
    if not isinstance(profile, str) or profile.lower() not in PROFILE_VALUES:
        raise ValueError("profile must be 'current' or 'target'")
    return profile.lower()


def classify_current(raw: Mapping[str, Any], trace: bool = False) -> Classification:
    """Replay the current production semantic oracle."""

    return _classify(raw, "current", trace=trace)


def classify_target(raw: Mapping[str, Any], trace: bool = False) -> Classification:
    """Evaluate the detached Phase 2A target semantic profile."""

    return _classify(raw, "target", trace=trace)


def classify(raw: Mapping[str, Any], profile: Optional[str] = None, trace: bool = False) -> Classification:
    """Classify a context using an explicit ``current`` or ``target`` profile.

    There is deliberately no implicit target/current default: callers must
    select the oracle they intend to evaluate.
    """

    selected_profile = _canonical_profile(profile)
    return _classify(raw, selected_profile, trace=trace)


def backend_action(decision: Optional[str], backend_mode: str, protocol: str) -> str:
    """Map a semantic decision to an abstract action, never command syntax."""

    if decision is not None and decision not in DECISIONS:
        raise ValueError("unknown decision: {!r}".format(decision))
    mode = _canonical_dimension("backend_mode", backend_mode, "TUN")
    proto = _canonical_dimension("protocol", protocol, "OTHER")
    if decision == "NOT_OWNED":
        return "NOT_OWNED"
    if decision in {"BYPASS", "DIRECT"}:
        return "NATIVE_RETURN"
    if decision == "DNS_SPECIAL":
        return "DNS_REDIRECT"
    if decision == "ACCESS_DENY":
        return "ACCESS_DENY_REQUIRED"
    if decision == "PROXY":
        if mode == "TUN":
            return "MARK"
        if mode == "TPROXY":
            return "MARK_TPROXY"
        if mode == "REDIRECT" and proto == "TCP":
            return "REDIRECT"
        if mode == "REDIRECT" and proto == "UDP":
            return "UNSUPPORTED_ACTION"
        return "PROXY_BACKEND_SPECIFIC"
    return "UNDEFINED"


def _expected_mapping(value: Any, case_id: str, profile: str) -> None:
    if not isinstance(value, Mapping):
        raise FixtureValidationError("{} expected_{} must be an object".format(case_id, profile))
    required = {"reason", "decision", "status"}
    if set(value) != required:
        raise FixtureValidationError("{} expected_{} fields must be {}".format(case_id, profile, sorted(required)))
    if value["status"] not in STATUS_VALUES:
        raise FixtureValidationError("{} has unknown {} status".format(case_id, profile))
    if value["reason"] not in MATCH_REASONS:
        raise FixtureValidationError("{} has unknown {} reason".format(case_id, profile))
    decision = value["decision"]
    if decision is not None and decision not in DECISIONS:
        raise FixtureValidationError("{} has unknown {} decision".format(case_id, profile))
    if value["status"] == "INVALID_CONFIGURATION":
        if value["reason"] != "INVALID_CONFIGURATION" or decision is not None:
            raise FixtureValidationError("{} invalid result must be INVALID_CONFIGURATION/null".format(case_id))
    elif decision is None:
        raise FixtureValidationError("{} non-invalid result cannot have null decision".format(case_id))


def validate_fixture(fixture: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate the versioned Phase 2A fixture and return it unchanged."""

    if not isinstance(fixture, Mapping):
        raise FixtureValidationError("fixture must be an object")
    if fixture.get("schema") != "CLASSIFIER_SEMANTIC_CONTRACT_V1":
        raise FixtureValidationError("unsupported fixture schema")
    if fixture.get("contract_version") != CLASSIFIER_CONTRACT_VERSION:
        raise FixtureValidationError("contract version mismatch")
    if tuple(fixture.get("profile_enum", ())) != PROFILE_VALUES:
        raise FixtureValidationError("profile enum mismatch")
    if fixture.get("runtime_wiring") != "NONE":
        raise FixtureValidationError("fixture must remain model-only")
    if tuple(fixture.get("decision_enum", ())) != DECISIONS:
        raise FixtureValidationError("decision enum mismatch")
    if tuple(fixture.get("match_reason_enum", ())) != MATCH_REASONS:
        raise FixtureValidationError("match reason enum mismatch")
    dimensions = fixture.get("packet_context_dimensions")
    if not isinstance(dimensions, Mapping):
        raise FixtureValidationError("packet context dimensions missing")
    for key, values in PACKET_CONTEXT_DIMENSIONS.items():
        if tuple(dimensions.get(key, ())) != values:
            raise FixtureValidationError("context dimension mismatch: {}".format(key))
    for key, expected in (("current_precedence", CURRENT_PRECEDENCE), ("target_precedence", TARGET_PRECEDENCE)):
        table = fixture.get(key)
        if not isinstance(table, list) or len(table) != len(expected):
            raise FixtureValidationError("{} table mismatch".format(key))
        for index, (item, label) in enumerate(zip(table, expected)):
            if not isinstance(item, Mapping) or item.get("order") != index:
                raise FixtureValidationError("{} order mismatch at {}".format(key, index))
            for required_key in ("match_reason", "decision", "position", "change"):
                if required_key not in item:
                    raise FixtureValidationError("{} missing {} at {}".format(key, required_key, index))
            actual_reason = str(item.get("match_reason", "")).upper().replace("-", "_")
            semantic_label = label
            if semantic_label.endswith("_IPV6"):
                semantic_label = semantic_label[:-5]
            if semantic_label.endswith("_CUSTOM"):
                semantic_label = semantic_label[:-7]
            if semantic_label == "CHINA_PASS_FALLTHROUGH":
                semantic_label = "CHINA_PASS"
            if actual_reason != semantic_label:
                raise FixtureValidationError("{} semantic order mismatch at {}".format(key, index))
            decisions = [part.strip() for part in str(item.get("decision", "")).split("/")]
            if not decisions or any(part not in DECISIONS for part in decisions):
                raise FixtureValidationError("{} unknown decision at {}".format(key, index))

    cases = fixture.get("cases")
    if not isinstance(cases, list):
        raise FixtureValidationError("cases must be a list")
    seen: Set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping):
            raise FixtureValidationError("case must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise FixtureValidationError("case id missing")
        if case_id in seen:
            raise FixtureValidationError("duplicate case id: {}".format(case_id))
        seen.add(case_id)
        for key in ("category", "family", "direction", "protocol", "owner", "backend_mode"):
            if key not in case:
                raise FixtureValidationError("{} missing {}".format(case_id, key))
        try:
            validate_context(case)
        except ContextValidationError as exc:
            raise FixtureValidationError("{} context: {}".format(case_id, exc))
        _expected_mapping(case.get("expected_current"), case_id, "current")
        _expected_mapping(case.get("expected_target"), case_id, "target")
        if "parity_pair" in case and case["parity_pair"] is not None and not isinstance(case["parity_pair"], str):
            raise FixtureValidationError("{} parity_pair must be a string".format(case_id))
        if "overlap" in case and not isinstance(case["overlap"], list):
            raise FixtureValidationError("{} overlap must be a list".format(case_id))
        if "overlap" in case:
            for item in case["overlap"]:
                if item not in {"OWNER", "DNS", "CONTROL", "SELF", "TUN", "NODE", "LOCAL", "REPLY", "SERVICE", "ACCESS", "ACCESS_CONTROL", "FAKEIP", "USER_DIRECT", "USER_PROXY", "CHINA", "CHINA_PASS"}:
                    raise FixtureValidationError("{} unknown overlap label: {}".format(case_id, item))
    return dict(fixture)


def enum_values() -> Dict[str, Tuple[str, ...]]:
    return {
        "decision": DECISIONS,
        "match_reason": MATCH_REASONS,
        "status": STATUS_VALUES,
        "profile": PROFILE_VALUES,
    }


__all__ = [
    "CLASSIFIER_CONTRACT_VERSION",
    "PROFILE_VALUES",
    "DECISIONS",
    "MATCH_REASONS",
    "STATUS_VALUES",
    "Classification",
    "ContextValidationError",
    "FixtureValidationError",
    "CURRENT_PRECEDENCE",
    "TARGET_PRECEDENCE",
    "PRECEDENCE_TABLES",
    "PACKET_CONTEXT_DIMENSIONS",
    "backend_action",
    "classify",
    "classify_current",
    "classify_target",
    "detect_matches",
    "enum_values",
    "normalize_context",
    "validate_context",
    "validate_fixture",
]
