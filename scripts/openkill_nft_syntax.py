#!/usr/bin/env python3
"""Development-only deterministic NFT syntax renderer for ``NFT_IR_V1``.

The Phase 3A module stops at an abstract action model.  This module lowers
that model to a structured, deterministic nftables program.  It deliberately
has no production imports and no command execution; the optional ``nft -c``
wrapper lives in :mod:`check-nft-syntax` and is the only place where a process
may be started by the Phase 3B tests.

The renderer consumes policy decisions already present in the IR.  It never
rebuilds classifier precedence, reads UCI/ubus, or mutates a ruleset.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from openkill_nft_ir import (
    ACTION_TYPES,
    COMPONENTS,
    MATCH_TYPES,
    NFT_IR_SCHEMA,
    NFT_IR_VERSION,
    MARK_ABI,
    NFTIRValidationError,
    validate_ir,
    serialize_ir,
)


NFT_SYNTAX_VERSION = 1
NFT_SYNTAX_SCHEMA = "OPENKILL_NFT_SYNTAX_V1"
NFT_AST_SCHEMA = "OPENKILL_NFT_AST_V1"
OWNERSHIP_MANIFEST_VERSION = 1
OWNERSHIP_MANIFEST_SCHEMA = "OPENKILL_NFT_MANIFEST_V1"
NFT_COMMENT_MAX = 128
DEFAULT_RENDERER_PROFILE = "current"
SUPPORTED_PROFILES = ("current", "target")
SUPPORTED_BACKEND = "ABSTRACT_NFT"
DEFAULT_TPROXY_PORT = 12345
DEFAULT_REDIRECT_PORT = 12345

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_LOGICAL_ID_RE = re.compile(r"^[A-Za-z0-9_:.=-]+$")
_SAFE_INTERFACES = {"utun", "tun0", "tun1", "openvpn", "mihomo"}
_FAMILIES = {"IPv4", "IPv6", "ALL"}
_ACTIONS = set(ACTION_TYPES)
_MATCHES = set(MATCH_TYPES) | {
    "source_property",
    "scope",
    "control_scope",
    "semantic_flag",
}
_DANGEROUS_TEXT = (
    "flush ruleset",
    "flush table",
    "flush ",
    "delete table",
    "delete ruleset",
    "delete ",
    "include ",
    "nft -",
    "nft add",
    "iptables ",
    "ip6tables ",
    "ip -",
    "$(",
    "`",
)

_SHELL_COMMANDS = {
    "bash",
    "busybox",
    "cat",
    "cmd",
    "cp",
    "echo",
    "ip",
    "iptables",
    "mv",
    "nft",
    "perl",
    "powershell",
    "python",
    "rm",
    "sh",
}


class NftSyntaxValidationError(ValueError):
    """Raised when an IR cannot be lowered safely to nft syntax."""


class UnsupportedNftAction(NftSyntaxValidationError):
    """Raised when a semantic action has no safe current syntax mapping."""


def _fail(message: str) -> None:
    raise NftSyntaxValidationError(message)


def validate_nft_identifier(value: Any, *, kind: str = "identifier") -> str:
    """Validate a physical nft identifier without allowing shell syntax."""

    if not isinstance(value, str) or not _NAME_RE.fullmatch(value):
        _fail("invalid nft {}: {!r}".format(kind, value))
    return value


def validate_logical_id(value: Any) -> str:
    if not isinstance(value, str) or not value or not _LOGICAL_ID_RE.fullmatch(value):
        _fail("invalid logical id: {!r}".format(value))
    return value


def _table_ref(value: Any) -> Tuple[str, str]:
    if value != "inet fw4":
        _fail("only the external inet fw4 table is supported")
    return "inet", "fw4"


def quote_comment(value: Any) -> str:
    """Return one safely quoted nft comment string.

    Newlines and control characters are rejected so a comment cannot create a
    second command.  Quotes and backslashes are escaped by JSON's stable
    string encoder; semicolons remain ordinary characters inside the quote.
    """

    if not isinstance(value, str):
        _fail("comment must be text")
    if any(ord(char) < 0x20 and char not in "\t" for char in value):
        _fail("control/newline character in comment")
    if "\r" in value or "\n" in value:
        _fail("newline in comment")
    # nft limits a comment payload to 128 characters.  Use the UTF-8 byte
    # length as the conservative check so non-ASCII diagnostics cannot be
    # accepted here and rejected later by the real parser.
    if len(value.encode("utf-8")) > NFT_COMMENT_MAX:
        _fail("comment exceeds nft {} character limit".format(NFT_COMMENT_MAX))
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _quote_string(value: Any, *, kind: str = "string") -> str:
    if not isinstance(value, str) or "\r" in value or "\n" in value:
        _fail("invalid {}".format(kind))
    if "$(" in value or "`" in value:
        _fail("shell expansion in {}".format(kind))
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _has_unsafe_shell_operator(text: str) -> bool:
    """Detect shell operators outside quoted nft strings.

    nft uses semicolons inside declarations, and comments may legitimately
    contain semicolons or ``&&``.  Only an operator followed by a known shell
    command outside a quoted string is rejected.
    """

    quoted = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            index += 1
            continue
        if char == '"':
            quoted = True
            index += 1
            continue
        if text.startswith("&&", index) or text.startswith("||", index):
            return True
        if char == ";":
            cursor = index + 1
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            match = re.match(r"[A-Za-z_][A-Za-z0-9_-]*", text[cursor:])
            if match and match.group(0).lower() in _SHELL_COMMANDS:
                return True
        index += 1
    return quoted


def _family(value: Any) -> str:
    if value not in _FAMILIES:
        _fail("unknown object family: {!r}".format(value))
    return value


def _canonical_address(value: Any, family: str, *, prefix: bool = False) -> str:
    try:
        parsed = ipaddress.ip_network(str(value), strict=False) if prefix else ipaddress.ip_address(str(value))
    except ValueError as exc:
        raise NftSyntaxValidationError("invalid {} address/prefix: {!r}".format(family, value)) from exc
    expected = 4 if family == "IPv4" else 6
    if parsed.version != expected:
        _fail("address family mismatch: {!r}".format(value))
    return str(parsed)


def _canonical_element(raw: Any, element_type: str, family: str) -> str:
    if element_type == "ADDRESS":
        if family not in {"IPv4", "IPv6"}:
            _fail("address set requires a family")
        text = str(raw)
        # Address sets may carry /128 for a host-only IPv6 semantic.
        if "/" in text:
            network = ipaddress.ip_network(text, strict=False)
            if network.version != (4 if family == "IPv4" else 6):
                _fail("address family mismatch: {!r}".format(raw))
            if network.prefixlen == (128 if family == "IPv6" else 32):
                # A host and its explicit /128 or /32 spelling are the same
                # nft address element.  Canonicalizing both to the bare host
                # makes semantic deduplication explicit.
                return str(network.network_address)
            _fail("non-host prefix in address set: {!r}".format(raw))
        return _canonical_address(raw, family)
    if element_type == "PREFIX":
        if family not in {"IPv4", "IPv6"}:
            _fail("prefix set requires a family")
        return _canonical_address(raw, family, prefix=True)
    if element_type == "INTERVAL":
        if family not in {"IPv4", "IPv6"} or not isinstance(raw, str) or "-" not in raw:
            _fail("invalid interval element: {!r}".format(raw))
        left, right = raw.split("-", 1)
        start = ipaddress.ip_address(left.strip())
        end = ipaddress.ip_address(right.strip())
        expected = 4 if family == "IPv4" else 6
        if start.version != expected or end.version != expected or start > end:
            _fail("invalid interval bounds: {!r}".format(raw))
        return "{}-{}".format(start, end)
    if element_type == "PORT":
        if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= 65535:
            _fail("invalid service port: {!r}".format(raw))
        return str(int(raw))
    if element_type == "MAC":
        text = str(raw).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}", text):
            _fail("invalid MAC: {!r}".format(raw))
        return text
    if element_type == "TOKEN":
        text = str(raw).strip()
        if not text or not _NAME_RE.fullmatch(text):
            _fail("invalid token element: {!r}".format(raw))
        return text
    _fail("unknown element type: {!r}".format(element_type))
    return ""


def normalize_elements(values: Iterable[Any], element_type: str, family: str) -> List[str]:
    """Canonicalize and stably sort set elements for syntax output."""

    kind = str(element_type).upper()
    if kind not in {"ADDRESS", "PREFIX", "PORT", "MAC", "INTERVAL", "TOKEN"}:
        _fail("unknown element type: {!r}".format(element_type))
    canonical = {_canonical_element(item, kind, family) for item in (values or ())}
    if kind == "PORT":
        return sorted(canonical, key=lambda item: int(item))
    if kind == "INTERVAL":
        return sorted(canonical, key=lambda item: tuple(ipaddress.ip_address(part) for part in item.split("-", 1)))
    return sorted(canonical)


def _set_nft_type(element_type: str, family: str) -> Tuple[str, List[str]]:
    kind = str(element_type).upper()
    if kind in {"ADDRESS", "PREFIX", "INTERVAL"}:
        if family == "IPv4":
            nft_type = "ipv4_addr"
        elif family == "IPv6":
            nft_type = "ipv6_addr"
        else:
            _fail("address set cannot use family ALL")
        flags = ["interval"] if kind in {"PREFIX", "INTERVAL"} else []
        return nft_type, flags
    if kind == "PORT":
        return "inet_service", []
    if kind == "MAC":
        return "ether_addr", []
    _fail("TOKEN sets have no current nft type")
    return "", []


def _owned_comment(obj: Mapping[str, Any], *, source_logical_id: Optional[str] = None) -> str:
    logical_id = str(obj.get("logical_id", ""))
    component = str(obj.get("component", ""))
    reason = obj.get("semantic_reason")
    decision = obj.get("decision")
    source = source_logical_id if source_logical_id and source_logical_id != logical_id else None

    # Keep human-readable field names whenever the nft limit allows them.  A
    # derived rule's logical_id already identifies its source, so source is
    # optional metadata and is omitted before required trace fields are
    # abbreviated.  Every fallback still carries logical id, component,
    # reason, decision, and owner for diagnostics.
    full = ["OpenKill", "logical_id={}".format(logical_id), "component={}".format(component)]
    if source:
        full.append("source={}".format(source))
    if reason:
        full.append("reason={}".format(reason))
    if decision:
        full.append("decision={}".format(decision))
    full.append("owner=OPENKILL")
    candidates = [full]
    without_source = [item for item in full if not item.startswith("source=")]
    if without_source != full:
        candidates.append(without_source)
    compact = ["OpenKill", "logical_id={}".format(logical_id), "component={}".format(component)]
    if reason:
        compact.append("r={}".format(reason))
    if decision:
        compact.append("d={}".format(decision))
    compact.append("o=OPENKILL")
    candidates.append(compact)
    candidates.append(
        ["OpenKill", "id={}".format(logical_id), "c={}".format(component)]
        + (["r={}".format(reason)] if reason else [])
        + (["d={}".format(decision)] if decision else [])
        + ["o=OPENKILL"]
    )
    for values in candidates:
        text = " ".join(values)
        if len(text.encode("utf-8")) <= NFT_COMMENT_MAX:
            return quote_comment(text)
    _fail("owned comment exceeds nft {} character limit".format(NFT_COMMENT_MAX))
    return ""


def audit_dependency_graph(dependencies: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize the development dependency graph and prove it is acyclic.

    Phase 3A's ``DNS -> DNS`` notation describes a self-contained component,
    not a dependency on another component.  It is removed from the graph and
    retained in ``self_contained_components`` for diagnostics.
    """

    if not isinstance(dependencies, Mapping):
        _fail("dependency graph must be a mapping")
    nodes = set(str(key) for key in dependencies if key != "self_contained_components")
    self_contained = set(str(item) for item in dependencies.get("self_contained_components", ()))
    normalized: Dict[str, List[str]] = {}
    for node in sorted(nodes):
        values = dependencies.get(node, ())
        if not isinstance(values, (list, tuple, set, frozenset)):
            _fail("dependency list must be a sequence: {}".format(node))
        clean = []
        for value in values:
            target = str(value)
            if target == node:
                self_contained.add(node)
                continue
            if target not in nodes:
                _fail("unknown dependency target: {}".format(target))
            clean.append(target)
        normalized[node] = sorted(set(clean))
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            _fail("component dependency cycle at {}".format(node))
        if node in visited:
            return
        visiting.add(node)
        for child in normalized.get(node, ()):
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(nodes):
        visit(node)
    return {
        "graph": normalized,
        "self_contained_components": sorted(self_contained),
        "self_edges": sorted(item for item in self_contained if item in nodes),
        "acyclic": True,
    }


def _validate_ir_for_syntax(ir: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        validated = validate_ir(ir)
    except NFTIRValidationError as exc:
        raise NftSyntaxValidationError(str(exc)) from exc
    metadata = validated["metadata"]
    if metadata.get("renderer_backend") != SUPPORTED_BACKEND:
        _fail("unsupported renderer backend")
    profile = metadata.get("renderer_profile")
    if profile not in SUPPORTED_PROFILES:
        _fail("unknown renderer profile")
    if profile == "target" and metadata.get("behavior_change_lock") != "TARGET_PREVIEW_ONLY":
        _fail("target syntax must be preview-only")
    if profile == "current" and metadata.get("behavior_change_lock") != "CURRENT_ONLY":
        _fail("current syntax must carry CURRENT_ONLY lock")
    if metadata.get("mark_abi") != MARK_ABI:
        _fail("Mark ABI changed or missing")
    audit_dependency_graph(validated.get("dependencies", {}))
    return dict(validated)


def _object_maps(ir: Mapping[str, Any]) -> Tuple[Dict[str, Mapping[str, Any]], Dict[str, Mapping[str, Any]], Dict[str, Mapping[str, Any]]]:
    topology = ir["static_topology"]
    chains: Dict[str, Mapping[str, Any]] = {}
    external: Dict[str, Mapping[str, Any]] = {}
    for obj in topology.get("objects", ()):
        if obj.get("object_type") in {"chain", "chain_ref", "table_ref"}:
            (external if obj.get("ownership") == "EXTERNAL" else chains)[obj["logical_id"]] = obj
    sets = {obj["logical_id"]: obj for obj in ir.get("dynamic_state", {}).get("sets", ())}
    return chains, external, sets


def _physical_chain(logical_id: str, chains: Mapping[str, Mapping[str, Any]], external: Mapping[str, Mapping[str, Any]]) -> str:
    obj = chains.get(logical_id) or external.get(logical_id)
    if obj is None:
        _fail("unresolved chain reference: {}".format(logical_id))
    physical = obj.get("physical_name")
    if obj.get("ownership") == "EXTERNAL":
        if logical_id == "FW4_TABLE":
            return "inet fw4"
        return validate_nft_identifier(physical, kind="external chain")
    return validate_nft_identifier(physical, kind="chain")


def _physical_set(logical_id: str, sets: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any]:
    obj = sets.get(logical_id)
    if obj is None:
        _fail("unresolved set reference: {}".format(logical_id))
    validate_nft_identifier(obj.get("physical_name"), kind="set")
    return obj


def _serialize_set(obj: Mapping[str, Any]) -> Dict[str, Any]:
    family = _family(obj.get("family"))
    element_type = str(obj.get("element_type", "")).upper()
    nft_type, flags = _set_nft_type(element_type, family)
    elements = normalize_elements(obj.get("elements", ()), element_type, family)
    return {
        "object_type": "set",
        "logical_id": validate_logical_id(obj.get("logical_id")),
        "physical_name": validate_nft_identifier(obj.get("physical_name"), kind="set"),
        "owner": "OPENKILL",
        "ownership": "OWNED",
        "parent_owner": "FW4",
        "parent_table": "inet fw4",
        "component": obj.get("component"),
        "family": family,
        "element_type": element_type,
        "nft_type": nft_type,
        "flags": flags,
        "elements": elements,
        "dynamic": bool(obj.get("dynamic", True)),
    }


def _serialize_chain(obj: Mapping[str, Any]) -> Dict[str, Any]:
    family = _family(obj.get("family"))
    return {
        "object_type": "chain",
        "logical_id": validate_logical_id(obj.get("logical_id")),
        "physical_name": validate_nft_identifier(obj.get("physical_name"), kind="chain"),
        "owner": "OPENKILL",
        "ownership": "OWNED",
        "parent_owner": "FW4",
        "parent_table": "inet fw4",
        "component": obj.get("component"),
        "family": family,
        "role": obj.get("role"),
        "base_chain": bool(obj.get("base_chain")),
        "type": obj.get("type"),
        "hook": obj.get("hook"),
        "priority": obj.get("priority"),
    }


def _protocol_terms(match: Mapping[str, Any], family: str) -> List[str]:
    values = match.get("protocol")
    if values is None:
        return [""]
    if isinstance(values, str):
        values = [values]
    terms = []
    for value in values:
        label = str(value).upper().replace("-", "_")
        if label == "TCP":
            terms.append("tcp")
        elif label == "UDP":
            terms.append("udp")
        elif label == "ICMP":
            terms.append("icmp")
        elif label == "ICMPV6":
            if family != "IPv6":
                _fail("ICMPv6 match on IPv4 rule")
            terms.append("icmpv6")
        elif label in {"OTHER", ""}:
            terms.append("")
        else:
            _fail("unknown protocol match: {}".format(value))
    return sorted(set(terms)) or [""]


_ICMPV6_CONTROL_NAMES = (
    "router-solicitation",
    "router-advertisement",
    "neighbor-solicitation",
    "neighbor-advertisement",
    "packet-too-big",
    "destination-unreachable",
    "time-exceeded",
    "parameter-problem",
)

# The semantic contract uses descriptive names.  nftables uses the shorter
# RFC 4861 ``nd-*`` spellings for the four Neighbor Discovery messages; keep
# that translation in the syntax lowering layer so the classifier contract
# remains backend-neutral.
_ICMPV6_NFT_NAMES = {
    "router-solicitation": "nd-router-solicit",
    "router-advertisement": "nd-router-advert",
    "neighbor-solicitation": "nd-neighbor-solicit",
    "neighbor-advertisement": "nd-neighbor-advert",
    "packet-too-big": "packet-too-big",
    "destination-unreachable": "destination-unreachable",
    "time-exceeded": "time-exceeded",
    "parameter-problem": "parameter-problem",
}


def _base_match_expressions(rule: Mapping[str, Any], family: str) -> List[str]:
    match = rule.get("match", {})
    if not isinstance(match, Mapping):
        _fail("rule match must be an object")
    unknown = set(match) - _MATCHES
    if unknown:
        _fail("unknown match primitive: {}".format(sorted(unknown)[0]))
    # Regular chains live in an ``inet`` table, so an explicit family guard is
    # required for matches that do not themselves carry an ip/ip6 expression
    # (service, reply, self and default rules).
    expressions: List[str] = ["meta nfproto {}".format("ipv4" if family == "IPv4" else "ipv6")]
    source_property = match.get("source_property")
    if source_property:
        if source_property != "SELF_PROCESS":
            _fail("unknown source property: {}".format(source_property))
        expressions.append("meta skgid 65534")
    interface_role = match.get("interface_role")
    if interface_role:
        if interface_role != "OPENKILL_TUN":
            _fail("unknown interface role: {}".format(interface_role))
        expressions.append('iifname "utun"')
    if match.get("connection"):
        if match["connection"] != "REPLY":
            _fail("only reply connection matching is supported")
        expressions.append("ct direction reply")
    service = match.get("service")
    if service and service not in {"DNS", "OTHER"}:
        _fail("unsupported service match: {}".format(service))
    if match.get("control_scope") and match["control_scope"] != "IPv6_ONLY":
        _fail("unknown control scope")
    return expressions


def _destination_expression(set_obj: Mapping[str, Any]) -> str:
    family = set_obj["family"]
    prefix = "ip" if family == "IPv4" else "ip6"
    return "{} daddr @{}".format(prefix, set_obj["physical_name"])


def _source_expression(set_obj: Mapping[str, Any]) -> str:
    family = set_obj["family"]
    prefix = "ip" if family == "IPv4" else "ip6"
    return "{} saddr @{}".format(prefix, set_obj["physical_name"])


def _match_variants(
    rule: Mapping[str, Any],
    family: str,
    sets: Mapping[str, Mapping[str, Any]],
) -> List[Tuple[str, str]]:
    """Return ``(suffix, expression)`` variants without choosing policy."""

    match = rule.get("match", {})
    terms = _protocol_terms(match, family)
    destination_refs = match.get("destination_set", ())
    if isinstance(destination_refs, str):
        destination_refs = [destination_refs]
    source_refs = match.get("source_set", ())
    if isinstance(source_refs, str):
        source_refs = [source_refs]
    if destination_refs and source_refs:
        _fail("source and destination set expansion together is not supported")
    set_variants: List[Tuple[str, str]] = [("", "")]
    if destination_refs:
        set_variants = []
        for index, ref in enumerate(destination_refs):
            obj = _physical_set(str(ref), sets)
            if obj.get("family") != family:
                _fail("destination set family mismatch: {}".format(ref))
            set_variants.append(("set{:02d}".format(index), _destination_expression(obj)))
    elif source_refs:
        set_variants = []
        for index, ref in enumerate(source_refs):
            obj = _physical_set(str(ref), sets)
            if obj.get("family") != family:
                _fail("source set family mismatch: {}".format(ref))
            set_variants.append(("src{:02d}".format(index), _source_expression(obj)))

    result: List[Tuple[str, str]] = []
    service = match.get("service")
    port_ref = match.get("port_set")
    control = match.get("control_scope") == "IPv6_ONLY" or rule.get("semantic_reason") == "CONTROL_PROTOCOL"
    for protocol in terms:
        protocol_options = [protocol]
        if service == "DNS":
            protocol_options = ["tcp", "udp"]
        elif port_ref and not protocol:
            protocol_options = ["tcp", "udp"]
        elif rule.get("action_type") == "TPROXY_PROXY" and not protocol and not service and not port_ref:
            # nft requires a transport-protocol match for tproxy.  A
            # protocol-neutral semantic PROXY rule therefore lowers to its
            # TCP and UDP variants; it does not broaden policy to ICMP.
            protocol_options = ["tcp", "udp"]
        for p in protocol_options:
            extra: List[str] = []
            if control and family == "IPv6":
                if p == "icmpv6":
                    extra.append(
                        "icmpv6 type {"
                        + ", ".join(_ICMPV6_NFT_NAMES[name] for name in _ICMPV6_CONTROL_NAMES)
                        + "}"
                    )
                elif p == "udp":
                    extra.append("udp dport { 546, 547 }")
            elif service == "DNS":
                extra.append("{} dport 53".format(p))
            elif port_ref:
                port_obj = _physical_set(str(port_ref), sets)
                if port_obj.get("family") != "ALL" or port_obj.get("element_type") != "PORT":
                    _fail("port set must be an inet_service set")
                extra.append("{} dport @{}".format(p, port_obj["physical_name"]))
            base = _base_match_expressions(rule, family)
            for suffix, set_expression in set_variants:
                parts = list(base)
                if set_expression:
                    parts.append(set_expression)
                if p and not extra:
                    # A bare ``tcp``/``udp`` token is not a complete nft
                    # protocol match.  Use the generic l4 protocol
                    # primitive when no transport header expression (such as
                    # dport) follows it.
                    parts.append("meta l4proto {}".format(p))
                parts.extend(extra)
                result.append(("{}{}{}".format(suffix, "_" if suffix and p else "", p), " ".join(parts)))
    if not result:
        result = [("", " ".join(_base_match_expressions(rule, family)))]
    # A semantic family field is represented by the selected nft address
    # expression where possible; family itself is retained in metadata.
    return result


def _action_expression(
    action_type: str,
    *,
    chain: Optional[str] = None,
    target_chain: Optional[str] = None,
    protocol: str = "",
    family: Optional[str] = None,
    tproxy_port: int = DEFAULT_TPROXY_PORT,
    redirect_port: int = DEFAULT_REDIRECT_PORT,
) -> Optional[str]:
    if action_type == "RETURN_NATIVE":
        return "return"
    if action_type == "MARK_PROXY":
        return "meta mark set {}".format(MARK_ABI["mark"])
    if action_type == "TPROXY_PROXY":
        if not 1 <= int(tproxy_port) <= 65535:
            _fail("invalid TProxy port")
        if protocol not in {"tcp", "udp"}:
            raise UnsupportedNftAction("TPROXY_PROXY requires a TCP or UDP match")
        if family not in {"IPv4", "IPv6"}:
            _fail("TPROXY_PROXY requires an IP family")
        address_family = "ip6" if family == "IPv6" else "ip"
        return "tproxy {} to :{} meta mark set {}".format(
            address_family,
            int(tproxy_port),
            MARK_ABI["mark"],
        )
    if action_type == "REDIRECT_PROXY":
        if protocol != "tcp":
            raise UnsupportedNftAction("REDIRECT_PROXY is only valid for TCP")
        if not 1 <= int(redirect_port) <= 65535:
            _fail("invalid redirect port")
        return "redirect to :{}".format(int(redirect_port))
    if action_type == "DNS_REDIRECT":
        if target_chain:
            return "jump {}".format(validate_nft_identifier(target_chain, kind="DNS chain"))
        if not 1 <= int(redirect_port) <= 65535:
            _fail("invalid DNS redirect port")
        return "redirect to :{}".format(int(redirect_port))
    if action_type == "JUMP":
        if not target_chain:
            _fail("JUMP requires a target chain")
        return "jump {}".format(validate_nft_identifier(target_chain, kind="jump target"))
    if action_type in {"CONTINUE_POLICY", "ACTION_FROM_CLASSIFICATION"}:
        # A counter-only rule records a current fall-through intent without
        # inventing a verdict.  The classifier remains the policy authority.
        return "counter"
    if action_type == "ACCEPT_IF_REQUIRED":
        return "accept"
    if action_type == "ACCESS_DENY_REQUIRED":
        raise UnsupportedNftAction("ACCESS_DENY_REQUIRED has no approved current verdict")
    if action_type == "UNSUPPORTED_ACTION":
        raise UnsupportedNftAction("IR contains an unsupported action")
    if action_type in {"NOT_OWNED", "UNRESOLVED_SEMANTIC"}:
        return None
    if action_type == "ACTION_FROM_CLASSIFICATION":
        return "counter"
    _fail("unknown action type: {}".format(action_type))
    return None


def _chain_targets_for_rule(
    rule: Mapping[str, Any],
    family: str,
    chains: Mapping[str, Mapping[str, Any]],
    external: Mapping[str, Mapping[str, Any]],
) -> List[Tuple[str, Optional[str]]]:
    action = rule.get("action_type")
    explicit_chain = rule.get("context_execution_chain_ref")
    if explicit_chain:
        return [(_physical_chain(str(explicit_chain), chains, external), None)]
    if action == "DNS_REDIRECT":
        # DNS is an independent entry point: LAN traffic is sent to the LAN
        # hijack chain and router output to the router redirect chain.
        suffix = "V4" if family == "IPv4" else "V6"
        scope = rule.get("dns_scope")
        if scope == "DNS_LAN":
            return [
                (
                    _physical_chain("OPENKILL_PREROUTING_MANGLE_" + suffix, chains, external),
                    _physical_chain("OPENKILL_DNS_LAN_" + suffix, chains, external),
                )
            ]
        if scope == "DNS_ROUTER":
            return [
                (
                    _physical_chain("OPENKILL_OUTPUT_MANGLE_" + suffix, chains, external),
                    _physical_chain("OPENKILL_DNS_ROUTER_" + suffix, chains, external),
                )
            ]
        return [
            (
                _physical_chain("OPENKILL_PREROUTING_MANGLE_" + suffix, chains, external),
                _physical_chain("OPENKILL_DNS_LAN_" + suffix, chains, external),
            ),
            (
                _physical_chain("OPENKILL_OUTPUT_MANGLE_" + suffix, chains, external),
                _physical_chain("OPENKILL_DNS_ROUTER_" + suffix, chains, external),
            ),
        ]
    refs = rule.get("chain_refs") or [rule.get("chain_ref")]
    result = []
    for ref in refs:
        if not ref:
            continue
        target = _physical_chain(str(ref), chains, external)
        # Rules are only emitted into OpenKill-owned chains.  External refs
        # are attachment targets and are handled by the jump inventory.
        obj = chains.get(str(ref))
        if obj is not None and obj.get("owner") == "OPENKILL":
            result.append((target, None))
    if not result:
        ref = rule.get("chain_ref")
        if ref:
            obj = chains.get(str(ref))
            if obj is not None and obj.get("owner") == "OPENKILL":
                result.append((_physical_chain(str(ref), chains, external), None))
    return result


def _rule_family(rule: Mapping[str, Any]) -> Optional[str]:
    family = rule.get("family")
    if family in {"IPv4", "IPv6"}:
        return family
    return None


def _lower_rule_variants(
    rule: Mapping[str, Any],
    *,
    chains: Mapping[str, Mapping[str, Any]],
    external: Mapping[str, Mapping[str, Any]],
    sets: Mapping[str, Mapping[str, Any]],
    tproxy_port: int,
    redirect_port: int,
) -> List[Dict[str, Any]]:
    if rule.get("enabled") is False or rule.get("action_type") in {"NOT_OWNED", "UNRESOLVED_SEMANTIC"}:
        return []
    # The current profile intentionally preserves the audited IPv6 TUN gap;
    # emitting a symmetric return here would silently apply BC-04.
    if rule.get("known_current_gap") == "BC-04" and rule.get("current_behavior") == "CURRENT_IPV6_TUN_GAP":
        return []
    action_type = rule.get("action_type")
    if action_type not in _ACTIONS:
        _fail("unknown action type: {!r}".format(action_type))
    family = _rule_family(rule)
    if family is None:
        _fail("rule family is required")
    chain_targets = _chain_targets_for_rule(rule, family, chains, external)
    matches = _match_variants(rule, family, sets)
    output: List[Dict[str, Any]] = []
    for chain_index, (chain, target) in enumerate(chain_targets):
        for match_index, (suffix, expression) in enumerate(matches):
            protocol = ""
            for token in ("tcp", "udp", "icmpv6", "icmp"):
                if token in expression.split():
                    protocol = token
                    break
            action = _action_expression(
                action_type,
                chain=chain,
                target_chain=target,
                protocol=protocol,
                family=family,
                tproxy_port=tproxy_port,
                redirect_port=redirect_port,
            )
            if action is None:
                continue
            parent_id = validate_logical_id(rule.get("logical_id"))
            derived = parent_id
            if len(chain_targets) > 1 or len(matches) > 1:
                derived = "{}__c{:02d}__m{:02d}".format(parent_id, chain_index, match_index)
            # The physical name is only a manifest identity for a rule; nft
            # rules themselves have no stable runtime name/handle.
            physical = "rule_{}".format(re.sub(r"[^A-Za-z0-9_]", "_", derived).lower())
            if len(physical) > 128:
                physical = physical[:128]
            output.append(
                {
                    "object_type": "rule",
                    "logical_id": derived,
                    "physical_name": validate_nft_identifier(physical, kind="rule"),
                    "owner": "OPENKILL",
                    "ownership": "OWNED",
                    "parent_owner": "FW4",
                    "parent_table": "inet fw4",
                    "component": rule.get("component"),
                    "family": family,
                    "chain": chain,
                    "match_expression": expression,
                    "action_type": action_type,
                    "action_expression": action,
                    "semantic_reason": rule.get("semantic_reason"),
                    "decision": (rule.get("possible_decisions") or [None])[0],
                    "source_logical_id": parent_id,
                    "precedence_index": rule.get("precedence_index"),
                    "known_current_gap": rule.get("known_current_gap"),
                    "trace_comment": _owned_comment(
                        {
                            **rule,
                            "logical_id": derived,
                            "decision": (rule.get("possible_decisions") or [None])[0],
                        },
                        source_logical_id=parent_id,
                    ),
                }
            )
    return output


def _lower_action_ir(
    ir: Mapping[str, Any],
    *,
    chains: Mapping[str, Mapping[str, Any]],
    external: Mapping[str, Mapping[str, Any]],
    sets: Mapping[str, Mapping[str, Any]],
    tproxy_port: int,
    redirect_port: int,
) -> List[Dict[str, Any]]:
    """Lower a concrete context classification, when present in the IR."""

    context = ir.get("context")
    actions = ir.get("action_ir", ())
    execution = ir.get("context_execution") or {}
    if not context or not actions:
        return []
    if ir.get("static_topology", {}).get("owner_state") != "OPENKILL":
        # Mihomo-owned/disabled dataplanes are explicitly NOT_OWNED; no
        # OpenKill syntax object should be invented for their classification.
        return []
    action = actions[0]
    action_type = execution.get("action_type") or action.get("action_type")
    # ACCESS_DENY_REQUIRED is intentionally unsupported for the current
    # modern backend.  Check the action before honoring a NO_ACTION execution
    # status so the development/current corpus cannot silently lower an
    # unapproved deny into an absent rule.
    if action_type == "ACCESS_DENY_REQUIRED":
        raise UnsupportedNftAction("ACCESS_DENY_REQUIRED has no approved current verdict")
    if execution.get("status") in {"NO_ACTION", "PREVIEW_GENERIC"} and execution.get("status") == "NO_ACTION":
        return []
    if action_type == "UNSUPPORTED_ACTION":
        raise UnsupportedNftAction("current backend execution is unsupported for this context")
    # DNS mode 1 and router-self DNS are emitted as complete parent-chain
    # attachments.  Only mode 2 LAN DNS has an owned body rule to lower here.
    if execution.get("kind") == "DNS" and not execution.get("body_chain_ref"):
        return []
    if action_type in {"NOT_OWNED", "UNRESOLVED_SEMANTIC"}:
        return []
    family_value = str(context.get("family", "")).upper().replace("-", "_")
    family = "IPv4" if family_value == "IPV4" else "IPv6" if family_value == "IPV6" else None
    if family is None:
        _fail("context family missing")
    suffix = "V4" if family == "IPv4" else "V6"
    direction = context.get("direction")
    chain_id = execution.get("chain_ref")
    if not chain_id:
        if direction == "ROUTER_OUTPUT":
            chain_id = "OPENKILL_OUTPUT_MANGLE_" + suffix
        else:
            chain_id = "OPENKILL_PREROUTING_MANGLE_" + suffix
    chain = _physical_chain(chain_id, chains, external)
    reason = action.get("reason")
    match: Dict[str, Any] = {
        "family": family,
        "protocol": context.get("protocol"),
    }
    # The context renderer intentionally carries semantic properties instead
    # of physical set IDs.  Resolve only the already selected reason to the
    # dynamic set inventory; no precedence is performed here.
    destination = set(context.get("destination_properties") or ())
    candidate_ids: List[str] = []
    mapping = {
        "NODE_ENDPOINT": "NODE_ENDPOINT_" + suffix,
        "FAKEIP": "FAKEIP_" + suffix,
        "EXPLICIT_DIRECT": "USER_DIRECT_" + suffix,
        "EXPLICIT_PROXY": "USER_PROXY_" + suffix,
        "CHINA_POLICY": "CHINA_" + suffix,
        "CHINA_PASS": "CHINA_PASS_" + suffix,
    }
    if reason in mapping:
        candidate_ids.append(mapping[reason])
    elif reason == "LOCAL_DESTINATION":
        candidate_ids.extend(
            [
                "LOCAL_" + suffix,
                "LAN_" + suffix,
                "WAN_HOST_" + suffix,
                "DELEGATED_V6" if family == "IPv6" else "LAN_" + suffix,
            ]
        )
    elif reason == "SERVICE_PORT":
        match["port_set"] = "SERVICE_PORTS"
    elif reason == "DNS":
        match["service"] = "DNS"
    elif reason == "SELF_TRAFFIC":
        match["source_property"] = "SELF_PROCESS"
    elif reason == "TUN_INGRESS":
        match["interface_role"] = "OPENKILL_TUN"
    elif reason == "REPLY_TRAFFIC":
        match["connection"] = "REPLY"
    if candidate_ids:
        match["destination_set"] = list(dict.fromkeys(item for item in candidate_ids if item in sets))
    # Reuse the same primitive lowerer as static rules; action_ir's semantic
    # decision is already resolved and is represented by its action_type.
    source_rule = {
        "logical_id": "CLASSIFICATION_{}".format(action.get("reason") or "UNKNOWN"),
        "physical_name": "classification",
        "component": "PROXY_ACTION",
        "family": family,
        "chain_ref": chain_id,
        "chain_refs": [chain_id],
        "match": match,
        "action_type": action_type,
        "semantic_reason": action.get("reason"),
        "possible_decisions": [action.get("decision")] if action.get("decision") else [],
        "precedence_index": action.get("precedence_index"),
        "context_execution_chain_ref": chain_id,
    }
    if reason == "DNS":
        source_rule["dns_scope"] = "DNS_ROUTER" if direction == "ROUTER_OUTPUT" else "DNS_LAN"
    if execution.get("kind") == "DNS" and execution.get("body_chain_ref"):
        source_rule["context_execution_chain_ref"] = execution["body_chain_ref"]
    return _lower_rule_variants(
        source_rule,
        chains=chains,
        external=external,
        sets=sets,
        tproxy_port=int(execution.get("tproxy_port", tproxy_port)),
        redirect_port=int(
            execution.get(
                "dns_port" if execution.get("kind") == "DNS" else "redirect_port",
                redirect_port,
            )
        ),
    )


def _lower_jump(
    jump: Mapping[str, Any],
    *,
    chains: Mapping[str, Mapping[str, Any]],
    external: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    source = _physical_chain(str(jump.get("from_chain")), chains, external)
    target = _physical_chain(str(jump.get("to_chain")), chains, external)
    logical_id = validate_logical_id(jump.get("logical_id"))
    return {
        "object_type": "attachment",
        "logical_id": logical_id,
        "physical_name": validate_nft_identifier(jump.get("physical_name"), kind="attachment"),
        "owner": "OPENKILL",
        "ownership": "OWNED",
        "parent_owner": "FW4",
        "parent_table": "inet fw4",
        "component": jump.get("component"),
        "family": jump.get("family"),
        "from_chain": source,
        "to_chain": target,
        "match_expression": (
            "meta nfproto {}".format("ipv4" if jump.get("family") == "IPv4" else "ipv6")
            if jump.get("family") in {"IPv4", "IPv6"}
            else ""
        ),
        "action_type": "JUMP",
        "action_expression": "jump {}".format(target),
        "trace_comment": _owned_comment(jump),
    }


def _lower_current_nat_output_jumps(
    jump: Mapping[str, Any],
    *,
    chains: Mapping[str, Mapping[str, Any]],
    external: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Lower the current nat_output hook without jumping into a base chain.

    nftables rejects a jump whose target is itself a hooked (base) chain.  The
    production OpenKill topology instead hooks ``nat_output`` directly and
    jumps from that chain into the family-specific regular output chain.  The
    IR keeps one logical current attachment, so the syntax layer expands it
    into the two deterministic family attachments here.
    """

    parent_id = validate_logical_id(jump.get("logical_id"))
    source = _physical_chain("OPENKILL_NAT_OUTPUT_CURRENT", chains, external)
    lowered: List[Dict[str, Any]] = []
    for family, suffix in (("IPv4", "V4"), ("IPv6", "V6")):
        target = _physical_chain("OPENKILL_OUTPUT_PROXY_" + suffix, chains, external)
        logical_id = parent_id + "_" + suffix
        match = (
            "meta nfproto ipv4 ip protocol tcp"
            if family == "IPv4"
            else "meta nfproto ipv6"
        )
        lowered.append(
            {
                "object_type": "attachment",
                "logical_id": logical_id,
                "physical_name": validate_nft_identifier("jump_nat_output_" + suffix.lower(), kind="attachment"),
                "owner": "OPENKILL",
                "ownership": "OWNED",
                "parent_owner": "FW4",
                "parent_table": "inet fw4",
                "component": jump.get("component"),
                "family": family,
                "from_chain": source,
                "to_chain": target,
                "match_expression": match,
                "action_type": "JUMP",
                "action_expression": "jump " + target,
                "source_logical_id": parent_id,
                "trace_comment": _owned_comment(
                    {**jump, "logical_id": logical_id},
                    source_logical_id=parent_id,
                ),
            }
        )
    return lowered


def _lower_context_attachments(
    ir: Mapping[str, Any],
    *,
    chains: Mapping[str, Mapping[str, Any]],
    external: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Lower packet-scoped current attachments without resolving policy.

    The selected semantic reason/action is already present in
    ``context_execution``.  This helper only materializes the production
    entry point for that action (for example ``dstnat`` versus ``nat_output``
    for DNS, or the IPv4 TCP redirect jump).
    """

    execution = ir.get("context_execution") or {}
    if execution.get("status") != "READY":
        return []
    family = execution.get("family")
    suffix = "V4" if family == "IPv4" else "V6"
    kind = execution.get("kind")
    result: List[Dict[str, Any]] = []

    def owned_attachment(
        logical_id: str,
        physical_name: str,
        source_ref: str,
        match_expression: str,
        action_type: str,
        action_expression: str,
        *,
        target_ref: Optional[str] = None,
        component: str = "PROXY_ACTION",
    ) -> Dict[str, Any]:
        source = _physical_chain(source_ref, chains, external)
        target = _physical_chain(target_ref, chains, external) if target_ref else None
        return {
            "object_type": "attachment",
            "logical_id": validate_logical_id(logical_id),
            "physical_name": validate_nft_identifier(physical_name, kind="attachment"),
            "owner": "OPENKILL",
            "ownership": "OWNED",
            "parent_owner": "FW4",
            "parent_table": "inet fw4",
            "component": component,
            "family": family,
            "from_chain": source,
            "to_chain": target,
            "match_expression": match_expression,
            "action_type": action_type,
            "action_expression": action_expression,
            "semantic_reason": execution.get("reason"),
            "decision": execution.get("decision"),
            "source_logical_id": "CONTEXT_EXECUTION",
            "trace_comment": _owned_comment(
                {
                    "logical_id": logical_id,
                    "component": component,
                    "semantic_reason": execution.get("reason"),
                    "decision": execution.get("decision"),
                }
            ),
        }

    if kind == "DNS":
        protocol_match = "meta l4proto {tcp,udp} th dport 53"
        family_match = "meta nfproto {}".format("ipv4" if family == "IPv4" else "ipv6")
        if execution.get("dns_scope") == "DNS_LAN":
            source = _physical_chain("FW4_DSTNAT", chains, external)
            if str(execution.get("dns_mode")) == "1":
                result.append(
                    owned_attachment(
                        "ATTACH_DNS_LAN_CURRENT_" + suffix,
                        "jump_dns_lan_current_" + suffix.lower(),
                        "FW4_DSTNAT",
                        family_match + " " + protocol_match,
                        "DNS_REDIRECT",
                        "redirect to :{}".format(int(execution["dns_port"])),
                        component="DNS",
                    )
                )
            else:
                target = _physical_chain(str(execution["body_chain_ref"]), chains, external)
                result.append(
                    owned_attachment(
                        "ATTACH_DNS_LAN_CURRENT_" + suffix,
                        "jump_dns_lan_current_" + suffix.lower(),
                        "FW4_DSTNAT",
                        family_match + " " + protocol_match,
                        "JUMP",
                        "jump " + target,
                        target_ref=str(execution["body_chain_ref"]),
                        component="DNS",
                    )
                )
        elif execution.get("dns_scope") == "DNS_ROUTER":
            family_tail = "ip daddr {127.0.0.1}" if family == "IPv4" else "ip6 daddr {::1}"
            result.append(
                owned_attachment(
                    "ATTACH_DNS_ROUTER_CURRENT_" + suffix,
                    "dns_router_current_" + suffix.lower(),
                    "OPENKILL_NAT_OUTPUT_CURRENT",
                    "meta skgid != 65534 " + family_match + " " + protocol_match + " " + family_tail,
                    "DNS_REDIRECT",
                    "redirect to :{}".format(int(execution["dns_port"])),
                    component="DNS",
                )
            )
        return result

    parent_ref = execution.get("parent_chain_ref")
    if parent_ref == "FW4_DSTNAT":
        proto = str(execution.get("protocol", "")).lower()
        proto_match = "ip protocol {}".format(proto) if proto in {"tcp", "udp", "icmp"} else "meta l4proto {}".format(proto)
        family_match = "meta nfproto {}".format("ipv4" if family == "IPv4" else "ipv6")
        target_ref = str(execution.get("chain_ref"))
        target = _physical_chain(target_ref, chains, external)
        result.append(
            owned_attachment(
                "ATTACH_CONTEXT_PREROUTING_" + suffix,
                "jump_context_prerouting_" + suffix.lower(),
                "FW4_DSTNAT",
                family_match + " " + proto_match,
                "JUMP",
                "jump " + target,
                target_ref=target_ref,
            )
        )
    return result


def _manifest(objects: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    entries = []
    for obj in objects:
        entries.append(
            {
                "logical_id": obj["logical_id"],
                "physical_name": obj["physical_name"],
                "object_type": obj["object_type"],
                "component": obj.get("component"),
                "parent_table": "inet fw4",
                "parent_owner": "FW4",
                "owner": "OPENKILL",
                "ownership": "OWNED",
                "semantic_spec_version": 1,
                "syntax_version": NFT_SYNTAX_VERSION,
            }
        )
    entries.sort(key=lambda item: (item["object_type"], item["logical_id"]))
    return {
        "schema": OWNERSHIP_MANIFEST_SCHEMA,
        "version": OWNERSHIP_MANIFEST_VERSION,
        "owner": "OPENKILL",
        "semantic_spec_version": 1,
        "syntax_version": NFT_SYNTAX_VERSION,
        "entries": entries,
    }


def _stable_metadata(ir: Mapping[str, Any], *, target_preview: bool) -> Dict[str, Any]:
    metadata = ir["metadata"]
    profile = metadata["renderer_profile"]
    return {
        "semantic_spec_version": metadata["semantic_spec_version"],
        "classifier_contract_version": metadata["classifier_contract_version"],
        "renderer_profile": profile,
        "renderer_backend": metadata["renderer_backend"],
        "ir_version": NFT_IR_VERSION,
        "syntax_renderer_version": NFT_SYNTAX_VERSION,
        "ownership_manifest_version": OWNERSHIP_MANIFEST_VERSION,
        "mark_abi": dict(MARK_ABI),
        "behavior_change_lock": metadata["behavior_change_lock"],
        "production_profile_default": DEFAULT_RENDERER_PROFILE,
        "preview_only": bool(target_preview),
        "production_output": False,
        "external_priority_policy": "EXTERNAL_UNVERIFIED",
        "requires_policy_route": any(
            item.get("action_type") in {"MARK_PROXY", "TPROXY_PROXY"} for item in ir.get("rules", ())
        ),
    }


def lower_nft_ir(
    ir: Mapping[str, Any],
    *,
    tproxy_port: int = DEFAULT_TPROXY_PORT,
    redirect_port: int = DEFAULT_REDIRECT_PORT,
) -> Dict[str, Any]:
    """Lower validated ``NFT_IR_V1`` to a structured syntax AST."""

    normalized = _validate_ir_for_syntax(ir)
    profile = normalized["metadata"]["renderer_profile"]
    target_preview = profile == "target"
    chains, external, sets = _object_maps(normalized)
    topology_objects = normalized["static_topology"].get("objects", ())
    owned_chains = [_serialize_chain(obj) for obj in topology_objects if obj.get("object_type") == "chain" and obj.get("owner") == "OPENKILL"]
    owned_chains.sort(key=lambda item: item["logical_id"])
    syntax_sets = [_serialize_set(obj) for obj in normalized["dynamic_state"].get("sets", ())]
    syntax_sets.sort(key=lambda item: item["logical_id"])

    rules: List[Dict[str, Any]] = []
    context_record = normalized.get("context")
    for rule in normalized.get("rules", ()):
        # A context render is a packet-scoped intent.  Its concrete DNS
        # action is emitted below with the selected LAN/router scope; the
        # state-level DNS policy rules would otherwise expand to both entry
        # points and make LAN and router renders indistinguishable.  The
        # state renderer (without context) retains the complete static plan.
        if context_record and rule.get("semantic_reason") == "DNS":
            continue
        # Packet-scoped rendering uses the single selected execution action
        # below.  Static proxy rules are still present in state-level IR, but
        # emitting them here would create phantom TPROXY/redirect paths (for
        # example router output when router_self_proxy is disabled).
        if context_record and rule.get("action_type") in {
            "MARK_PROXY", "TPROXY_PROXY", "REDIRECT_PROXY"
        }:
            continue
        rules.extend(
            _lower_rule_variants(
                rule,
                chains=chains,
                external=external,
                sets=sets,
                tproxy_port=tproxy_port,
                redirect_port=redirect_port,
            )
        )
    rules.extend(
        _lower_action_ir(
            normalized,
            chains=chains,
            external=external,
            sets=sets,
            tproxy_port=tproxy_port,
            redirect_port=redirect_port,
        )
    )
    # Rule precedence is semantic; the logical id is only a deterministic tie
    # breaker after that precedence has already been supplied by the IR.
    rules.sort(key=lambda item: (item["chain"], item.get("precedence_index") is None, item.get("precedence_index") or 0, item["logical_id"]))

    attachments = []
    for jump in normalized["static_topology"].get("jumps", ()):
        if jump.get("owner") == "OPENKILL":
            if jump.get("logical_id") == "ATTACH_NAT_OUTPUT_CURRENT":
                attachments.extend(
                    _lower_current_nat_output_jumps(jump, chains=chains, external=external)
                )
            else:
                attachments.append(_lower_jump(jump, chains=chains, external=external))
    attachments.extend(
        _lower_context_attachments(normalized, chains=chains, external=external)
    )
    attachments.sort(key=lambda item: item["logical_id"])

    external_refs = []
    for obj in topology_objects:
        if obj.get("ownership") == "EXTERNAL":
            external_refs.append(
                {
                    "logical_id": obj["logical_id"],
                    "physical_name": obj["physical_name"],
                    "object_type": obj["object_type"],
                    "role": obj.get("role"),
                    "priority": "EXTERNAL_UNVERIFIED",
                }
            )
    external_refs.sort(key=lambda item: item["logical_id"])
    manifest_objects: List[Mapping[str, Any]] = [*owned_chains, *syntax_sets, *rules, *attachments]
    dependencies = audit_dependency_graph(normalized.get("dependencies", {}))
    ast = {
        "schema": NFT_AST_SCHEMA,
        "syntax_schema": NFT_SYNTAX_SCHEMA,
        "syntax_version": NFT_SYNTAX_VERSION,
        "metadata": _stable_metadata(normalized, target_preview=target_preview),
        "table": {"family": "inet", "name": "fw4", "ownership": "REFERENCE_ONLY", "owner": "FW4"},
        "external_chain_refs": external_refs,
        "owned_chains": owned_chains,
        "sets": syntax_sets,
        "rules": rules,
        "attachments": attachments,
        "dependencies": dependencies,
        "ownership_manifest": _manifest(manifest_objects),
        "source_ir_fingerprint": hashlib.sha256(serialize_ir(normalized).encode("utf-8")).hexdigest(),
        "target_preview_banner": "DEVELOPMENT_TARGET_PREVIEW NOT_FOR_PRODUCTION" if target_preview else None,
        "known_current_gaps": list(normalized.get("known_current_gaps", ())),
    }
    validate_nft_ast(ast)
    return ast


def _ast_text_comment(ast: Mapping[str, Any]) -> str:
    metadata = ast["metadata"]
    profile = metadata["renderer_profile"]
    lines = [
        "# {} syntax_version={} profile={} backend={}".format(
            NFT_SYNTAX_SCHEMA,
            NFT_SYNTAX_VERSION,
            profile,
            metadata["renderer_backend"],
        ),
        "# semantic_spec_version={} classifier_contract_version={} ir_version={}".format(
            metadata["semantic_spec_version"],
            metadata["classifier_contract_version"],
            metadata["ir_version"],
        ),
        "# table inet fw4 is an external FW4 reference; no parent table mutation is emitted",
    ]
    if ast.get("target_preview_banner"):
        lines.append("# DEVELOPMENT_TARGET_PREVIEW NOT_FOR_PRODUCTION")
    return "\n".join(lines)


def _serialize_chain_text(chain: Mapping[str, Any]) -> str:
    name = chain["physical_name"]
    if chain.get("base_chain"):
        chain_type = chain.get("type")
        hook = str(chain.get("hook", "")).lower()
        priority = chain.get("priority")
        if chain_type != "nat" or hook != "output" or priority != -1:
            _fail("unsupported owned base-chain declaration")
        return "add chain inet fw4 {} {{ type nat hook output priority -1; }}".format(name)
    return "add chain inet fw4 {} {{ }}".format(name)


def _serialize_set_text(item: Mapping[str, Any]) -> str:
    fields = ["type {}".format(item["nft_type"])]
    if item.get("flags"):
        fields.append("flags {}".format(", ".join(item["flags"])))
    elements = item.get("elements", ())
    if elements:
        fields.append("elements = {{ {} }}".format(", ".join(elements)))
    return "add set inet fw4 {} {{ {}; }}".format(item["physical_name"], "; ".join(fields))


def _serialize_rule_text(rule: Mapping[str, Any]) -> str:
    chain = validate_nft_identifier(rule["chain"], kind="chain")
    match = str(rule.get("match_expression", "")).strip()
    action = str(rule.get("action_expression", "")).strip()
    if not action:
        _fail("rule action missing")
    body = " ".join(item for item in (match, action) if item)
    return "add rule inet fw4 {} {} comment {}".format(chain, body, rule["trace_comment"])


def _serialize_attachment_text(item: Mapping[str, Any]) -> str:
    # ``nat_output`` is already a hooked base chain.  nftables does not allow
    # a rule in another base chain to jump into it (the parser reports
    # ``Operation not supported``).  The current OpenKill topology hooks this
    # chain directly and dispatches to the regular family output chains, so
    # the expanded family attachments produced by _lower_current_nat_output_jumps
    # are serialized normally below.
    match = str(item.get("match_expression", "")).strip()
    return "add rule inet fw4 {} {} comment {}".format(
        validate_nft_identifier(item["from_chain"], kind="attachment source"),
        " ".join(part for part in (match, item["action_expression"]) if part),
        item["trace_comment"],
    )


def serialize_nft(ast: Mapping[str, Any]) -> str:
    """Serialize a syntax AST to deterministic nft text."""

    validate_nft_ast(ast)
    lines = [_ast_text_comment(ast)]
    # Serialization canonicalizes all object collections as a final guard so
    # callers may reorder an AST for diagnostics without changing its bytes.
    chains = sorted(ast.get("owned_chains", ()), key=lambda item: item["logical_id"])
    sets = sorted(ast.get("sets", ()), key=lambda item: item["logical_id"])
    attachments = sorted(ast.get("attachments", ()), key=lambda item: item["logical_id"])
    rules = sorted(
        ast.get("rules", ()),
        key=lambda item: (
            item.get("chain", ""),
            item.get("precedence_index") is None,
            item.get("precedence_index") if item.get("precedence_index") is not None else 0,
            item.get("logical_id", ""),
        ),
    )
    lines.extend(_serialize_chain_text(item) for item in chains)
    lines.extend(_serialize_set_text(item) for item in sets)
    lines.extend(_serialize_attachment_text(item) for item in attachments)
    lines.extend(_serialize_rule_text(item) for item in rules)
    text = "\n".join(lines) + "\n"
    validate_nft_syntax_text(text, production_output=True)
    return text


def render_nft(
    ir: Mapping[str, Any],
    *,
    tproxy_port: int = DEFAULT_TPROXY_PORT,
    redirect_port: int = DEFAULT_REDIRECT_PORT,
) -> str:
    """Convenience API: IR -> deterministic nft text."""

    return serialize_nft(lower_nft_ir(ir, tproxy_port=tproxy_port, redirect_port=redirect_port))


def validate_nft_ast(ast: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(ast, Mapping) or ast.get("schema") != NFT_AST_SCHEMA:
        _fail("unsupported NFT AST schema")
    if ast.get("syntax_schema") != NFT_SYNTAX_SCHEMA or ast.get("syntax_version") != NFT_SYNTAX_VERSION:
        _fail("NFT syntax version mismatch")
    metadata = ast.get("metadata")
    if not isinstance(metadata, Mapping):
        _fail("syntax metadata missing")
    if metadata.get("production_profile_default") != DEFAULT_RENDERER_PROFILE:
        _fail("renderer default must remain current")
    profile = metadata.get("renderer_profile")
    if profile not in SUPPORTED_PROFILES:
        _fail("unknown syntax profile")
    if profile == "current" and metadata.get("behavior_change_lock") != "CURRENT_ONLY":
        _fail("current syntax lock missing")
    if profile == "target" and (metadata.get("behavior_change_lock") != "TARGET_PREVIEW_ONLY" or not metadata.get("preview_only")):
        _fail("target syntax must be preview-only")
    if metadata.get("mark_abi") != MARK_ABI:
        _fail("Mark ABI mismatch")
    table = ast.get("table")
    if table != {"family": "inet", "name": "fw4", "ownership": "REFERENCE_ONLY", "owner": "FW4"}:
        _fail("parent FW4 table must remain a reference")
    ids: set[str] = set()
    physical: set[str] = set()
    owned: List[Mapping[str, Any]] = []
    for section in ("owned_chains", "sets", "rules", "attachments"):
        values = ast.get(section)
        if not isinstance(values, list):
            _fail("syntax {} must be a list".format(section))
        for obj in values:
            if not isinstance(obj, Mapping):
                _fail("syntax object must be an object")
            logical_id = validate_logical_id(obj.get("logical_id"))
            if logical_id in ids:
                _fail("duplicate syntax logical id: {}".format(logical_id))
            ids.add(logical_id)
            physical_name = validate_nft_identifier(obj.get("physical_name"), kind="physical name")
            if physical_name in physical:
                _fail("duplicate physical object name: {}".format(physical_name))
            physical.add(physical_name)
            if obj.get("owner") != "OPENKILL" or obj.get("ownership") != "OWNED":
                _fail("syntax object ownership is not OpenKill-scoped")
            if obj.get("component") not in COMPONENTS:
                _fail("unknown syntax component")
            owned.append(obj)
    for item in ast.get("external_chain_refs", ()):
        if item.get("physical_name") == "inet fw4":
            continue
        validate_nft_identifier(item.get("physical_name"), kind="external chain")
    manifest = ast.get("ownership_manifest")
    if not isinstance(manifest, Mapping) or manifest.get("schema") != OWNERSHIP_MANIFEST_SCHEMA:
        _fail("syntax ownership manifest missing")
    if manifest.get("version") != OWNERSHIP_MANIFEST_VERSION or manifest.get("owner") != "OPENKILL":
        _fail("syntax ownership manifest version/owner mismatch")
    manifest_entries = manifest.get("entries")
    if not isinstance(manifest_entries, list):
        _fail("syntax ownership manifest entries missing")
    manifest_by_id: Dict[str, Mapping[str, Any]] = {}
    for entry in manifest_entries:
        if not isinstance(entry, Mapping):
            _fail("syntax ownership manifest entry must be an object")
        entry_id = validate_logical_id(entry.get("logical_id"))
        if entry_id in manifest_by_id:
            _fail("duplicate manifest logical id: {}".format(entry_id))
        manifest_by_id[entry_id] = entry
    owned_by_id = {obj["logical_id"]: obj for obj in owned}
    if set(manifest_by_id) != set(owned_by_id):
        _fail("syntax manifest does not match owned objects")
    for logical_id, obj in owned_by_id.items():
        entry = manifest_by_id[logical_id]
        for key in ("physical_name", "object_type", "component", "owner", "ownership", "parent_table", "parent_owner"):
            if entry.get(key) != obj.get(key):
                _fail("syntax manifest metadata mismatch: {}".format(logical_id))
        if entry.get("semantic_spec_version") != metadata.get("semantic_spec_version"):
            _fail("syntax manifest semantic version mismatch: {}".format(logical_id))
        if entry.get("syntax_version") != NFT_SYNTAX_VERSION:
            _fail("syntax manifest syntax version mismatch: {}".format(logical_id))
    for rule in ast.get("rules", ()):
        if rule.get("action_type") not in _ACTIONS:
            _fail("unknown syntax action")
        if rule.get("action_type") == "REDIRECT_PROXY" and "udp" in rule.get("match_expression", "").split():
            raise UnsupportedNftAction("redirect UDP is unsupported")
        validate_nft_identifier(rule.get("chain"), kind="rule chain")
        if rule.get("semantic_reason") is not None and not isinstance(rule.get("semantic_reason"), str):
            _fail("invalid semantic reason")
        if "comment" in rule.get("trace_comment", ""):
            pass
    forbidden = _DANGEROUS_TEXT
    for value in _walk_strings(ast):
        lower = value.lower()
        if any(pattern in lower for pattern in forbidden):
            _fail("dangerous command syntax in AST")
    dependencies = ast.get("dependencies", {})
    if not isinstance(dependencies, Mapping) or dependencies.get("acyclic") is not True:
        _fail("component graph is not acyclic")
    return dict(ast)


def validate_syntax_fixture(fixture: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate the checked-in, machine-readable Phase 3B contract."""

    if not isinstance(fixture, Mapping) or fixture.get("schema") != "OPENKILL_NFT_SYNTAX_FIXTURE_V1":
        _fail("unsupported NFT syntax fixture schema")
    expected = {
        "syntax_version": NFT_SYNTAX_VERSION,
        "ir_schema": NFT_IR_SCHEMA,
        "semantic_spec_version": 1,
        "classifier_contract_version": 1,
        "ownership_manifest_schema": OWNERSHIP_MANIFEST_SCHEMA,
        "default_profile": DEFAULT_RENDERER_PROFILE,
        "backend": SUPPORTED_BACKEND,
        "production_wiring": "NONE",
    }
    for key, value in expected.items():
        if fixture.get(key) != value:
            _fail("syntax fixture {} mismatch".format(key))
    if tuple(fixture.get("supported_profiles", ())) != SUPPORTED_PROFILES:
        _fail("syntax fixture profile enum mismatch")
    parent = fixture.get("parent_table")
    if parent != {"family": "inet", "name": "fw4", "ownership": "REFERENCE_ONLY", "owner": "FW4"}:
        _fail("syntax fixture parent table ownership mismatch")
    current_chain = fixture.get("current_owned_base_chain")
    if not isinstance(current_chain, Mapping) or current_chain.get("priority") != -1 or current_chain.get("hook") != "output":
        _fail("syntax fixture nat_output contract mismatch")
    abi = fixture.get("mark_abi")
    if abi != MARK_ABI:
        _fail("syntax fixture Mark ABI mismatch")
    sections = fixture.get("object_sections")
    if tuple(sections or ()) != ("owned_chains", "sets", "rules", "attachments"):
        _fail("syntax fixture object sections mismatch")
    lock = fixture.get("behavior_change_lock")
    if not isinstance(lock, Mapping) or tuple(lock.get("ids", ())) != tuple("BC-0{}".format(i) for i in range(1, 8)):
        _fail("syntax fixture behavior-change lock incomplete")
    if lock.get("status") != "PRODUCTION_NOT_APPROVED":
        _fail("syntax fixture behavior changes must remain unapproved")
    if fixture.get("scaffold", {}).get("production_output_contains") is not False:
        _fail("syntax scaffold isolation missing")
    matrix = fixture.get("golden_matrix")
    if not isinstance(matrix, list) or len(matrix) < 20 or len(set(matrix)) != len(matrix):
        _fail("syntax golden matrix is incomplete or duplicated")
    return dict(fixture)


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _walk_strings(key)
            yield from _walk_strings(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _walk_strings(item)


def validate_nft_syntax_text(text: Any, *, production_output: bool = True) -> str:
    """Reject dangerous commands and malformed renderer markers.

    This is a structural safety check, not a replacement for nft's parser.
    The real syntax gate is the separate ``nft -c`` wrapper.
    """

    if not isinstance(text, str) or not text:
        _fail("nft text must be non-empty")
    if "\x00" in text:
        _fail("NUL in nft text")
    lower = text.lower()
    for pattern in _DANGEROUS_TEXT:
        if pattern in lower:
            _fail("forbidden nft text: {}".format(pattern))
    if production_output and ("TEST_SCAFFOLD" in text or "TEST_ONLY" in text):
        _fail("test scaffold leaked into production syntax")
    if _has_unsafe_shell_operator(text):
        _fail("shell operator in nft text")
    # Comments carry the traceability contract and must be quoted.  Any
    # unbalanced quote is rejected here; nft -c remains authoritative.
    for line in text.splitlines():
        if line.startswith("add ") and line.count('"') % 2:
            _fail("unbalanced comment quote")
    return text


def render_test_scaffold(ir: Mapping[str, Any]) -> str:
    """Build an isolated FW4 placeholder file for ``nft -c`` only.

    The scaffold is never returned by :func:`render_nft` and never enters a
    package or production path.  Its priorities are parser placeholders, not
    claims about the device's fw4 ordering.
    """

    normalized = _validate_ir_for_syntax(ir)
    lines = [
        "# TEST_SCAFFOLD ONLY; never use this file for apply",
        "add table inet fw4",
        "add chain inet fw4 dstnat { type nat hook prerouting priority -100; policy accept; }",
        "add chain inet fw4 srcnat { type nat hook postrouting priority 100; policy accept; }",
        "add chain inet fw4 mangle_prerouting { type filter hook prerouting priority -150; policy accept; }",
        "add chain inet fw4 mangle_output { type filter hook output priority -150; policy accept; }",
        "add chain inet fw4 output { type filter hook output priority 0; policy accept; }",
        "add chain inet fw4 input { type filter hook input priority 0; policy accept; }",
        "add chain inet fw4 forward { type filter hook forward priority 0; policy accept; }",
    ]
    # These chains are only reference targets in the production output; a
    # regular placeholder is enough for parser validation.
    refs = {obj["physical_name"] for obj in normalized["static_topology"].get("objects", ()) if obj.get("ownership") == "EXTERNAL" and obj.get("object_type") == "chain_ref"}
    for name in sorted(refs):
        if name not in {"dstnat", "srcnat", "mangle_prerouting", "mangle_output", "output", "input", "forward", "upnp"}:
            lines.append("add chain inet fw4 {} {{ }}".format(validate_nft_identifier(name, kind="scaffold chain")))
    production = render_nft(normalized)
    lines.append(production.rstrip("\n"))
    return "\n".join(lines) + "\n"


def render_check_file(ir: Mapping[str, Any]) -> str:
    """Alias used by the offline validator; returns scaffold + production IR."""

    text = render_test_scaffold(ir)
    validate_nft_syntax_text(text, production_output=False)
    return text


def parse_normalized_intent(text: str) -> Dict[str, Any]:
    """Extract a conservative abstract intent from generated comments.

    This parser is intentionally diagnostic only.  It does not claim to be an
    nft parser; ``nft -c`` remains the syntax authority.
    """

    validate_nft_syntax_text(text, production_output=False)
    records: List[Dict[str, str]] = []
    for line in text.splitlines():
        match = re.search(r'comment\s+"([^"]*)"', line)
        if not match:
            continue
        fields: Dict[str, str] = {}
        for token in match.group(1).split():
            if "=" in token:
                key, value = token.split("=", 1)
                fields[key] = value
        # Long rule IDs can require the compact diagnostic spelling used by
        # _owned_comment.  Normalize those aliases so parsed intent keeps the
        # same field contract regardless of comment length.
        for short, long in (("id", "logical_id"), ("c", "component"), ("r", "reason"), ("d", "decision"), ("o", "owner")):
            if short in fields and long not in fields:
                fields[long] = fields[short]
        if fields:
            records.append(fields)
    records.sort(key=lambda item: (item.get("logical_id", ""), item.get("component", "")))
    return {"schema": "OPENKILL_NFT_PARSED_INTENT_V1", "records": records, "parser_only": True}


def syntax_fingerprint(value: Any) -> str:
    text = serialize_nft(value) if isinstance(value, Mapping) and value.get("schema") == NFT_AST_SCHEMA else str(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def diff_syntax(old: Mapping[str, Any], new: Mapping[str, Any]) -> Dict[str, Any]:
    """Compare two ASTs at owned object/component granularity."""

    validate_nft_ast(old)
    validate_nft_ast(new)
    changes: List[Dict[str, Any]] = []
    categories: set[str] = set()
    components: set[str] = set()
    for section, category in (("owned_chains", "TOPOLOGY_CHANGE"), ("sets", "SET_ELEMENT_CHANGE"), ("rules", "RULE_CHANGE"), ("attachments", "TOPOLOGY_CHANGE")):
        before = {item["logical_id"]: item for item in old.get(section, ())}
        after = {item["logical_id"]: item for item in new.get(section, ())}
        for logical_id in sorted(set(before) | set(after)):
            left, right = before.get(logical_id), after.get(logical_id)
            if left == right:
                continue
            detail = "TOPOLOGY_ADD" if left is None and section in {"owned_chains", "attachments"} else "TOPOLOGY_REMOVE" if right is None and section in {"owned_chains", "attachments"} else category
            categories.add(detail)
            if detail in {"TOPOLOGY_ADD", "TOPOLOGY_REMOVE"}:
                categories.add("TOPOLOGY_CHANGE")
            categories.add("COMPONENT_CHANGE")
            component = (right or left).get("component")
            components.add(component)
            changes.append({"category": detail, "logical_id": logical_id, "component": component, "before": left, "after": right})
    if not changes:
        categories.add("NO_CHANGE")
    changes.sort(key=lambda item: (item["category"], item["logical_id"]))
    return {
        "categories": sorted(categories),
        "changed_components": sorted(components),
        "changes": changes,
        "no_change": not changes,
    }


def render_plan_text(ast: Mapping[str, Any]) -> str:
    validate_nft_ast(ast)
    lines = [
        "{} profile={}".format(NFT_SYNTAX_SCHEMA, ast["metadata"]["renderer_profile"]),
        "Owned chains: {}".format(len(ast.get("owned_chains", ()))),
        "Dynamic sets: {}".format(len(ast.get("sets", ()))),
        "Rules: {}".format(len(ast.get("rules", ()))),
        "Attachments: {}".format(len(ast.get("attachments", ()))),
    ]
    for item in ast.get("sets", ()):
        lines.append("SET {} elements={}".format(item["logical_id"], len(item.get("elements", ()))))
    for item in ast.get("rules", ()):
        lines.append("RULE {} reason={} action={}".format(item["logical_id"], item.get("semantic_reason"), item.get("action_type")))
    return "\n".join(lines)


__all__ = [
    "NFT_SYNTAX_VERSION",
    "NFT_SYNTAX_SCHEMA",
    "NFT_AST_SCHEMA",
    "OWNERSHIP_MANIFEST_VERSION",
    "OWNERSHIP_MANIFEST_SCHEMA",
    "NFT_COMMENT_MAX",
    "DEFAULT_RENDERER_PROFILE",
    "SUPPORTED_PROFILES",
    "SUPPORTED_BACKEND",
    "DEFAULT_TPROXY_PORT",
    "DEFAULT_REDIRECT_PORT",
    "NftSyntaxValidationError",
    "UnsupportedNftAction",
    "validate_nft_identifier",
    "validate_logical_id",
    "quote_comment",
    "normalize_elements",
    "audit_dependency_graph",
    "lower_nft_ir",
    "validate_nft_ast",
    "validate_syntax_fixture",
    "serialize_nft",
    "render_nft",
    "render_test_scaffold",
    "render_check_file",
    "validate_nft_syntax_text",
    "parse_normalized_intent",
    "syntax_fingerprint",
    "diff_syntax",
    "render_plan_text",
]
