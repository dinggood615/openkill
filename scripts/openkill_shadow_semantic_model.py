#!/usr/bin/env python3
"""Typed, ownership-aware semantic comparison for the local shadow audit.

The runtime shadow observer deliberately compares a legacy observation with a
CURRENT renderer result.  A byte-for-byte or whole-inventory comparison is
not sufficient for that job: a legacy safety object may be observable without
being part of the CURRENT ownership contract, and DNS spans several owners
and targets.  This module provides the small, deterministic model used by
the local D2B audit.

It is development-only.  It consumes already captured/normalized mappings,
does not execute commands, read live state, or write a device, and it never
turns an unknown ownership or DNS source into an equality.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple


SEMANTIC_MODEL_SCHEMA = "OPENKILL_SHADOW_SEMANTIC_MODEL_V1"

OWNERSHIP_CLASSES: Tuple[str, ...] = (
    "CURRENT_OWNED",
    "LEGACY_ONLY_SAFETY",
    "FW4_BASE",
    "CONDITIONAL_CURRENT",
    "INACTIVE_MODE",
    "OPTIONAL_OBSERVATION",
    "OUT_OF_SCOPE",
    "UNKNOWN",
)

# Public names for callers that want to state an ownership class without
# repeating a string literal.  The values are intentionally the wire values
# used by the semantic model and are not aliases for object names.
CURRENT_OWNED = "CURRENT_OWNED"
LEGACY_ONLY_SAFETY = "LEGACY_ONLY_SAFETY"
FW4_BASE = "FW4_BASE"
CONDITIONAL_CURRENT = "CONDITIONAL_CURRENT"
INACTIVE_MODE = "INACTIVE_MODE"
OPTIONAL_OBSERVATION = "OPTIONAL_OBSERVATION"
OUT_OF_SCOPE = "OUT_OF_SCOPE"
UNKNOWN = "UNKNOWN"

CURRENT_OWNERSHIP = frozenset(("CURRENT_OWNED", "CONDITIONAL_CURRENT"))
NON_COMPARABLE_OWNERSHIP = frozenset(
    (
        "LEGACY_ONLY_SAFETY",
        "FW4_BASE",
        "INACTIVE_MODE",
        "OPTIONAL_OBSERVATION",
        "OUT_OF_SCOPE",
    )
)

COMPONENTS: Tuple[str, ...] = (
    "HOOK_TOPOLOGY",
    "LOCAL",
    "NODE",
    "CHINA",
    "TUN",
    "MARK_ABI",
    "BACKEND",
    "DNS",
    "WAN_SAFETY",
    "ACCESS",
    "OTHER",
)

DNS_FIELDS: Tuple[str, ...] = (
    "DNS_FIREWALL_LAN_TARGET",
    "DNS_FIREWALL_ROUTER_TARGET",
    "DNSMASQ_LISTEN_TARGET",
    "DNSMASQ_UPSTREAM_TARGET",
    "MIHOMO_DNS_LISTENER",
    "DNS_LOOP_PREVENTION",
    "DNS_SCOPE_IPV4",
    "DNS_SCOPE_IPV6",
)

DNS_RESULT_VALUES = frozenset(("MATCH", "MISMATCH", "COMPARATOR_MODEL_GAP", "INSUFFICIENT_EVIDENCE"))
KNOWN_CURRENT_GAP_IDS = frozenset(("BC-01", "BC-02", "BC-03", "BC-04", "BC-05", "BC-06", "BC-07"))

# The renderer owns firewall topology.  The remaining values are deliberately
# UNKNOWN until a committed, typed source is supplied.  In particular, this
# prevents a renderer ``dns_port`` from being guessed to mean a dnsmasq
# listener or upstream endpoint.
_DEFAULT_DNS_OWNERSHIP = {
    "DNS_FIREWALL_LAN_TARGET": "CURRENT_OWNED",
    "DNS_FIREWALL_ROUTER_TARGET": "CURRENT_OWNED",
    "DNSMASQ_LISTEN_TARGET": "UNKNOWN",
    "DNSMASQ_UPSTREAM_TARGET": "UNKNOWN",
    "MIHOMO_DNS_LISTENER": "UNKNOWN",
    "DNS_LOOP_PREVENTION": "UNKNOWN",
    "DNS_SCOPE_IPV4": "UNKNOWN",
    "DNS_SCOPE_IPV6": "UNKNOWN",
}

_FIELD_ALIASES = {
    "firewall_lan_target": "DNS_FIREWALL_LAN_TARGET",
    "firewall_router_target": "DNS_FIREWALL_ROUTER_TARGET",
    "dns_firewall_lan_target": "DNS_FIREWALL_LAN_TARGET",
    "dns_firewall_router_target": "DNS_FIREWALL_ROUTER_TARGET",
    "dnsmasq_listen": "DNSMASQ_LISTEN_TARGET",
    "dnsmasq_listen_target": "DNSMASQ_LISTEN_TARGET",
    "dnsmasq_upstream": "DNSMASQ_UPSTREAM_TARGET",
    "dnsmasq_upstream_target": "DNSMASQ_UPSTREAM_TARGET",
    "mihomo_listener": "MIHOMO_DNS_LISTENER",
    "mihomo_dns_listener": "MIHOMO_DNS_LISTENER",
    "loop_prevention": "DNS_LOOP_PREVENTION",
    "dns_loop_prevention": "DNS_LOOP_PREVENTION",
    "dns_scope_ipv4": "DNS_SCOPE_IPV4",
    "dns_scope_ipv6": "DNS_SCOPE_IPV6",
}

_VOLATILE_KEYS = frozenset(
    (
        "handle",
        "counter",
        "packets",
        "bytes",
        "source",
        "trace_comment",
        "operation",
        "position",
    )
)


class SemanticModelError(ValueError):
    """Raised when a semantic model is incomplete or ambiguous."""


def _norm(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def semantic_hash(value: Any) -> str:
    """Hash canonical semantic data (never raw runtime counters/handles)."""

    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_class(value: Any) -> str:
    candidate = _norm(value)
    aliases = {
        "OWNED": "CURRENT_OWNED",
        "CURRENT": "CURRENT_OWNED",
        "CURRENT_OWNED": "CURRENT_OWNED",
        # D2A's inventory vocabulary calls an always-required CURRENT object
        # ``REQUIRED_CURRENT``.  It is the same ownership class for equality;
        # absence is still a hard mismatch because it is not conditional.
        "REQUIRED": "CURRENT_OWNED",
        "REQUIRED_CURRENT": "CURRENT_OWNED",
        "CURRENT_REQUIRED": "CURRENT_OWNED",
        "LEGACY_ONLY": "LEGACY_ONLY_SAFETY",
        "LEGACY_SAFETY": "LEGACY_ONLY_SAFETY",
        "LEGACY_ONLY_SAFETY": "LEGACY_ONLY_SAFETY",
        "FW4": "FW4_BASE",
        "FW4_BASE": "FW4_BASE",
        "CONDITIONAL": "CONDITIONAL_CURRENT",
        "CONDITIONAL_CURRENT": "CONDITIONAL_CURRENT",
        "INACTIVE": "INACTIVE_MODE",
        "INACTIVE_MODE": "INACTIVE_MODE",
        "OPTIONAL": "OPTIONAL_OBSERVATION",
        "OPTIONAL_OBSERVATION": "OPTIONAL_OBSERVATION",
        "OUT_OF_SCOPE": "OUT_OF_SCOPE",
        "OUT_OF_SCOPE_LEGACY_OBJECT": "OUT_OF_SCOPE",
        "UNKNOWN": "UNKNOWN",
    }
    if candidate in aliases:
        return aliases[candidate]
    if candidate in {"FOREIGN", "REFERENCE_ONLY", "EXTERNAL"}:
        return "OUT_OF_SCOPE" if candidate != "REFERENCE_ONLY" else "FW4_BASE"
    if candidate not in OWNERSHIP_CLASSES:
        raise SemanticModelError("unknown ownership class: {!r}".format(value))
    return candidate


def _inventory_maps(inventory: Any) -> Tuple[Dict[str, Mapping[str, Any]], Dict[str, Mapping[str, Any]]]:
    by_logical: Dict[str, Mapping[str, Any]] = {}
    by_physical: Dict[str, Mapping[str, Any]] = {}
    if inventory is None:
        return by_logical, by_physical
    values: Iterable[Any]
    if isinstance(inventory, Mapping):
        if "entries" in inventory and isinstance(inventory["entries"], Sequence):
            values = inventory["entries"]
        elif "objects" in inventory and isinstance(inventory["objects"], Sequence):
            values = inventory["objects"]
        else:
            values = list(inventory.values())
    elif isinstance(inventory, Sequence) and not isinstance(inventory, (str, bytes)):
        values = inventory
    else:
        raise SemanticModelError("formal inventory must be a sequence or mapping")
    for item in values:
        if not isinstance(item, Mapping):
            raise SemanticModelError("formal inventory entry must be an object")
        logical = item.get("logical_id") or item.get("semantic_id")
        physical = item.get("physical_name") or item.get("name")
        if logical:
            key = str(logical)
            if key in by_logical and by_logical[key] != item:
                raise SemanticModelError("duplicate formal logical id: {}".format(key))
            by_logical[key] = item
        if physical:
            key = str(physical)
            if key in by_physical and by_physical[key] != item:
                raise SemanticModelError("duplicate formal physical name: {}".format(key))
            by_physical[key] = item
    return by_logical, by_physical


def _inventory_metadata(obj: Mapping[str, Any], inventory: Any) -> Optional[Mapping[str, Any]]:
    if inventory is None:
        return None
    by_logical, by_physical = _inventory_maps(inventory)
    logical = obj.get("logical_id") or obj.get("semantic_id")
    physical = obj.get("physical_name") or obj.get("name")
    if logical and str(logical) in by_logical:
        return by_logical[str(logical)]
    if physical and str(physical) in by_physical:
        return by_physical[str(physical)]
    return None


def _component_for_object(obj: Mapping[str, Any]) -> str:
    component = _norm(obj.get("component"))
    role = _norm(obj.get("role"))
    if component in {"TOPOLOGY", "HOOK", "HOOK_TOPOLOGY"} or role in {
        "PREROUTING_PROXY",
        "PREROUTING_MANGLE",
        "OUTPUT_PROXY",
        "OUTPUT_MANGLE",
        "POSTROUTING",
    }:
        return "HOOK_TOPOLOGY"
    if component in {"PROXY_ACTION", "BACKEND"}:
        # TUN is a semantic transport component only when an object explicitly
        # marks the TUN path.  Generic proxy actions remain BACKEND.
        if _norm(obj.get("backend")) == "TUN" or _norm(obj.get("run_mode")) == "TUN":
            return "TUN"
        return "BACKEND"
    if component in {"WAN_INPUT", "WAN_SAFETY"} or role == "WAN_INPUT":
        return "WAN_SAFETY"
    if component in COMPONENTS:
        return component
    if component == "PROXY":
        return "BACKEND"
    reason = _norm(obj.get("reason") or obj.get("semantic_reason"))
    by_reason = {
        "LOCAL_DESTINATION": "LOCAL",
        "NODE_ENDPOINT": "NODE",
        "CHINA_POLICY": "CHINA",
        "CHINA_PASS": "CHINA",
        "DNS": "DNS",
        "TUN_INGRESS": "TUN",
        "FAKEIP": "BACKEND",
        "DEFAULT_POLICY": "BACKEND",
        "ACCESS_CONTROL": "ACCESS",
        "SERVICE_PORT": "OTHER",
    }
    return by_reason.get(reason, "OTHER")


def classify_object_ownership(
    obj: Mapping[str, Any],
    *,
    formal_inventory: Any = None,
) -> str:
    """Resolve one object's ownership from formal metadata.

    Physical names are used only to join a captured object to an audited
    inventory entry.  They are never an ignore list or a policy rule.
    """

    if not isinstance(obj, Mapping):
        raise SemanticModelError("semantic object must be an object")
    metadata = _inventory_metadata(obj, formal_inventory)

    for source in (obj, metadata or {}):
        for key in ("semantic_ownership", "ownership_class", "current_ownership", "classification", "class"):
            if key in source and source.get(key) not in (None, ""):
                return _canonical_class(source.get(key))

    # FW4 references are never CURRENT-owned child state.
    owner = _norm(obj.get("owner") or (metadata or {}).get("owner"))
    raw_ownership = _norm(obj.get("ownership") or (metadata or {}).get("ownership"))
    if owner == "FW4" or raw_ownership == "REFERENCE_ONLY":
        return "FW4_BASE"
    if raw_ownership in {"FOREIGN", "EXTERNAL"} or owner in {"FOREIGN", "EXTERNAL"}:
        return "OUT_OF_SCOPE"

    # These are schema roles, not physical-name exceptions.  The current
    # renderer's WAN input role is retained as a safety observation while the
    # optional UPNP path is diagnostic unless explicitly promoted by metadata.
    component = _norm(obj.get("component") or (metadata or {}).get("component"))
    role = _norm(obj.get("role") or (metadata or {}).get("role"))
    if component == "WAN_INPUT" or role == "WAN_INPUT":
        return "LEGACY_ONLY_SAFETY"
    if component == "UPNP" or role == "UPNP":
        return "OPTIONAL_OBSERVATION"

    if raw_ownership == "OWNED" or owner == "OPENKILL" or (metadata and metadata.get("owner") == "OPENKILL"):
        return "CURRENT_OWNED"
    return "UNKNOWN"


def _flatten_intent(intent: Mapping[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(intent, Mapping):
        raise SemanticModelError("intent must be an object")
    rows: List[Dict[str, Any]] = []
    table = intent.get("table")
    if isinstance(table, Mapping):
        rows.append({**dict(table), "object_type": "table_ref", "name": table.get("name", "inet fw4")})
    for section, default_type in (
        ("chains", "chain"),
        ("sets", "set"),
        ("attachments", "attachment"),
        ("rules", "rule"),
    ):
        values = intent.get(section, ())
        if values is None:
            continue
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise SemanticModelError("intent {} must be a list".format(section))
        for item in values:
            if not isinstance(item, Mapping):
                raise SemanticModelError("intent {} entry must be an object".format(section))
            row = dict(item)
            row.setdefault("object_type", default_type)
            if not row.get("physical_name") and row.get("name"):
                row["physical_name"] = row.get("name")
            if not row.get("name") and row.get("physical_name"):
                row["name"] = row.get("physical_name")
            rows.append(row)
    return rows


def _normalize_expression(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\bmeta nfproto\s+(ipv4|ipv6)\b", r"family \1", text, flags=re.I)
    text = re.sub(r"\bip protocol\b", "l4proto", text, flags=re.I)
    text = re.sub(r"\bskgid\s*==\s*", "skgid ", text, flags=re.I)
    return text.lower()


def _canonical_value(value: Any) -> Any:
    """Canonicalize nested semantic values without executing or guessing."""

    if isinstance(value, Mapping):
        return {str(key): _canonical_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (set, frozenset)):
        return sorted(_canonical_json(_canonical_value(item)) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical_value(item) for item in value]
    return value


def _canonical_object_payload(row: Mapping[str, Any], ownership: str, component: str) -> Dict[str, Any]:
    allowed = {
        "object_type",
        "logical_id",
        "semantic_id",
        "physical_name",
        "name",
        "family",
        "component",
        "role",
        "base_chain",
        "type",
        "hook",
        "priority",
        "chain",
        "from_chain",
        "to_chain",
        "order",
        "match_expression",
        "expression",
        "action_type",
        "action_expression",
        "action",
        "backend",
        "backend_mode",
        "reason",
        "semantic_reason",
        "decision",
        "known_gap",
        "status",
        "unsupported",
        "element_type",
        "elements",
        "flags",
        "match",
        "chain_ref",
        "chain_refs",
        "possible_decisions",
        "direction",
        "service",
        "protocol",
        "ports",
        "mark",
        "mask",
        "fwmark",
        "fwmask",
        "route_table",
        "rule_pref",
    }
    object_type = str(row.get("object_type", "object"))
    # Captured rules/attachments often have recorder-specific names and
    # logical ids.  Their semantic identity is built separately by
    # ``_object_key``; carrying those labels into equality would turn a
    # representation difference into a policy mismatch.
    identity_keys = {"logical_id", "semantic_id", "physical_name", "name"}
    if object_type not in {"rule", "attachment"}:
        identity_keys = set()
    result: Dict[str, Any] = {
        "ownership": ownership,
        "component": component,
    }
    for key in sorted(allowed):
        if key not in row or key in _VOLATILE_KEYS or key in identity_keys:
            continue
        value = row.get(key)
        if key in {"match_expression", "expression", "action_expression"}:
            value = _normalize_expression(value)
        elif key in {"elements", "flags", "possible_decisions", "chain_refs"}:
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                value = sorted({_canonical_json(item) for item in value})
        else:
            value = _canonical_value(value)
        result[key] = value
    # Raw OWNED versus CURRENT_OWNED and logical aliases are metadata, not
    # semantic differences.  Keep only the stable physical name here.
    if result.get("physical_name") is None and result.get("name") is not None:
        result["physical_name"] = result["name"]
    return result


def _object_key(row: Mapping[str, Any], payload: Mapping[str, Any], inventory: Any) -> str:
    object_type = str(row.get("object_type", "object"))
    # Rules and attachments are compared by semantic action facts because old
    # captures do not carry the renderer's logical IDs.
    if object_type in {"rule", "attachment"}:
        parts = (
            object_type,
            payload.get("component"),
            payload.get("family"),
            payload.get("chain") or payload.get("from_chain"),
            payload.get("to_chain"),
            payload.get("reason") or payload.get("semantic_reason"),
            payload.get("action") or payload.get("action_type"),
            payload.get("match_expression") or payload.get("expression"),
            payload.get("action_expression"),
        )
        return "semantic:" + semantic_hash(parts)[:32]
    metadata = _inventory_metadata(row, inventory)
    logical = row.get("logical_id") or row.get("semantic_id") or (metadata or {}).get("logical_id") or (metadata or {}).get("semantic_id")
    if logical:
        return "logical:" + str(logical)
    physical = row.get("physical_name") or row.get("name")
    if physical:
        return "physical:{}:{}".format(object_type, physical)
    return "anonymous:" + semantic_hash(payload)[:32]


def _catalog_from_intent(intent: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Build formal join metadata from an already audited desired intent."""

    rows = []
    for row in _flatten_intent(intent):
        ownership = classify_object_ownership(row)
        component = _component_for_object(row)
        row_copy: Dict[str, Any] = {
            "logical_id": row.get("logical_id") or row.get("semantic_id"),
            "physical_name": row.get("physical_name") or row.get("name"),
            "object_type": row.get("object_type"),
            "component": row.get("component") or row.get("semantic_reason") or component,
            "role": row.get("role"),
            "ownership_class": ownership,
        }
        if row_copy.get("logical_id") or row_copy.get("physical_name"):
            rows.append(row_copy)
    return rows


def build_semantic_projection(
    intent: Mapping[str, Any],
    *,
    mode: str = "TUN",
    formal_inventory: Any = None,
) -> Dict[str, Any]:
    """Return full observation and CURRENT-owned projections for one intent."""

    mode_value = _norm(mode)
    if mode_value not in {"TUN", "TPROXY", "REDIRECT"}:
        raise SemanticModelError("unknown comparison mode: {!r}".format(mode))
    catalog = formal_inventory
    rows: List[Dict[str, Any]] = []
    duplicate_keys: List[str] = []
    unsupported_keys: List[str] = []
    seen: set[str] = set()
    for row in _flatten_intent(intent):
        metadata = _inventory_metadata(row, catalog)
        # Mode/requirement annotations belong to the audited inventory when a
        # bounded capture carries only a physical/logical identity.  Merge
        # metadata for classification decisions, while retaining the row's
        # own payload as the observed semantic fact.
        effective_row = dict(metadata or {})
        effective_row.update(row)
        ownership = classify_object_ownership(effective_row, formal_inventory=catalog)
        # A formal mode annotation can promote a conditional row only when
        # the current mode explicitly activates it.  Otherwise it remains a
        # retained observation and does not enter owned equality.
        active_modes = effective_row.get("active_modes")
        effective_ownership = ownership
        active_mode_values = (
            {_norm(item) for item in active_modes}
            if isinstance(active_modes, Sequence) and not isinstance(active_modes, (str, bytes))
            else set()
        )
        if ownership == "CONDITIONAL_CURRENT" and active_mode_values and mode_value not in active_mode_values:
            effective_ownership = "INACTIVE_MODE"
        required_modes = effective_row.get("required_modes")
        required_mode_values = (
            {_norm(item) for item in required_modes}
            if isinstance(required_modes, Sequence) and not isinstance(required_modes, (str, bytes))
            else set()
        )
        conditional_required = bool(
            ownership == "CONDITIONAL_CURRENT"
            and (
                effective_row.get("required_when_active") is True
                or mode_value in required_mode_values
                or (not required_mode_values and mode_value in active_mode_values)
            )
        )
        component_row = dict(metadata or {})
        component_row.update(row)
        component = _component_for_object(component_row)
        payload_row = dict(row)
        # A bounded legacy capture may carry only a physical name.  Once the
        # audited inventory joins that name to a logical identity, normalize
        # the identity for equality so recorder labels cannot become a false
        # CURRENT-owned mismatch.
        if metadata:
            logical_identity = metadata.get("logical_id") or metadata.get("semantic_id")
            if logical_identity and not payload_row.get("logical_id") and not payload_row.get("semantic_id"):
                payload_row["logical_id"] = logical_identity
            physical_identity = metadata.get("physical_name") or metadata.get("name")
            if physical_identity and not payload_row.get("physical_name") and not payload_row.get("name"):
                payload_row["physical_name"] = physical_identity
        payload = _canonical_object_payload(payload_row, effective_ownership, component)
        key = _object_key(payload_row, payload, catalog)
        if key in seen:
            duplicate_keys.append(key)
        seen.add(key)
        if row.get("unsupported") is True or _norm(row.get("status")) == "UNSUPPORTED":
            unsupported_keys.append(key)
        rows.append(
            {
                "key": key,
                "object_type": row.get("object_type"),
                "physical_name": row.get("physical_name") or row.get("name"),
                "logical_id": row.get("logical_id") or row.get("semantic_id"),
                "ownership": effective_ownership,
                "component": component,
                "conditional_required": conditional_required,
                "payload": payload,
                "present": True,
            }
        )
    rows.sort(key=lambda item: item["key"])
    unknown = [item for item in rows if item["ownership"] == "UNKNOWN"]
    owned = [item for item in rows if item["ownership"] in CURRENT_OWNERSHIP]
    observations = [
        {
            "key": item["key"],
            "object_type": item["object_type"],
            "physical_name": item["physical_name"],
            "logical_id": item["logical_id"],
            "ownership": item["ownership"],
            "component": item["component"],
            # Keep the complete bounded semantic observation available for
            # drift/safety diagnostics.  Volatile handles/counters were
            # removed by ``_canonical_object_payload`` before this point.
            "payload": item["payload"],
            "present": True,
        }
        for item in rows
    ]
    return {
        "schema": SEMANTIC_MODEL_SCHEMA,
        "mode": mode_value,
        "entries": rows,
        "owned_entries": owned,
        "unknown_entries": unknown,
        "duplicate_keys": sorted(set(duplicate_keys)),
        "unsupported_keys": sorted(set(unsupported_keys)),
        "observation_hash": semantic_hash(observations),
        "owned_hash": semantic_hash([{"key": item["key"], "payload": item["payload"]} for item in owned]),
    }


def _entry_map(projection: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    return {str(item["key"]): item for item in projection.get("entries", ())}


def _component_rows() -> Dict[str, Dict[str, Any]]:
    return {
        component: {
            "component": component,
            "actual_present": False,
            "desired_present": False,
            "actual_ownership": [],
            "desired_ownership": [],
            "comparable": False,
            "result": "NOT_OBSERVED",
            "reason": "no semantic entries",
        }
        for component in COMPONENTS
    }


def compare_semantic_intents(
    actual: Mapping[str, Any],
    desired: Mapping[str, Any],
    *,
    mode: str = "TUN",
    formal_inventory: Any = None,
    dns_actual: Optional[Mapping[str, Any]] = None,
    dns_desired: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Compare actual and desired intents using ownership and typed DNS.

    The result keeps the complete observation hash while deciding parity from
    the CURRENT-owned projection.  Unknown ownership, duplicate semantic
    identities, and incomplete required DNS sources produce MODEL_GAP rather
    than a false match.
    """

    # The CURRENT intent itself carries the audited logical/physical ownership
    # manifest for objects emitted by the renderer.  An explicit inventory can
    # add legacy observations that are absent from that intent.  Objects with
    # no matching manifest entry remain UNKNOWN and fail closed.
    desired_catalog: List[Mapping[str, Any]] = _catalog_from_intent(desired)
    if formal_inventory is not None:
        # Validate and merge caller-supplied metadata; conflicting entries are
        # rejected by _inventory_maps instead of silently picking one side.
        _inventory_maps(formal_inventory)
        if isinstance(formal_inventory, Sequence) and not isinstance(formal_inventory, (str, bytes)):
            inventory_values = list(formal_inventory)
        elif isinstance(formal_inventory, Mapping):
            inventory_values = (
                formal_inventory.get("entries")
                or formal_inventory.get("objects")
                or list(formal_inventory.values())
            )
        else:
            inventory_values = []
        desired_catalog = [item for item in inventory_values if isinstance(item, Mapping)]
    # De-duplicate identical catalog rows deterministically.
    catalog_unique: Dict[Tuple[Any, Any], Mapping[str, Any]] = {}
    for item in desired_catalog:
        if not isinstance(item, Mapping):
            raise SemanticModelError("formal inventory entry must be an object")
        key = (item.get("logical_id") or item.get("semantic_id"), item.get("physical_name") or item.get("name"))
        if key == (None, None):
            raise SemanticModelError("formal inventory entry has no stable identity")
        if key in catalog_unique and catalog_unique[key] != item:
            raise SemanticModelError("conflicting formal inventory identity: {}".format(key))
        catalog_unique[key] = item
    catalog = list(catalog_unique.values())

    actual_projection = build_semantic_projection(actual, mode=mode, formal_inventory=catalog)
    desired_projection = build_semantic_projection(desired, mode=mode, formal_inventory=catalog)
    actual_map = _entry_map(actual_projection)
    desired_map = _entry_map(desired_projection)
    components = _component_rows()
    mismatches: List[Dict[str, Any]] = []
    model_gaps: List[Dict[str, Any]] = []
    known_gaps: List[Dict[str, Any]] = []
    out_of_scope: List[Dict[str, Any]] = []
    # An audited CONDITIONAL_CURRENT entry is a required semantic object when
    # its active mode says so.  If the catalog itself says it is required but
    # neither side emitted a row, retain a deterministic missing-object
    # mismatch instead of silently treating the inventory entry as absent.
    mode_value = _norm(mode)
    for catalog_row in catalog:
        if not isinstance(catalog_row, Mapping):
            continue
        catalog_owner = classify_object_ownership(catalog_row)
        if catalog_owner != "CONDITIONAL_CURRENT":
            continue
        active_modes = catalog_row.get("active_modes")
        active_mode_values = (
            {_norm(item) for item in active_modes}
            if isinstance(active_modes, Sequence) and not isinstance(active_modes, (str, bytes))
            else set()
        )
        required_modes = catalog_row.get("required_modes")
        required_mode_values = (
            {_norm(item) for item in required_modes}
            if isinstance(required_modes, Sequence) and not isinstance(required_modes, (str, bytes))
            else set()
        )
        required_now = bool(
            (catalog_row.get("required_when_active") is True and (not active_mode_values or mode_value in active_mode_values))
            or mode_value in required_mode_values
            or (not required_mode_values and mode_value in active_mode_values)
        )
        if not required_now:
            continue
        catalog_component = _component_for_object(catalog_row)
        catalog_payload = _canonical_object_payload(catalog_row, catalog_owner, catalog_component)
        catalog_key = _object_key(catalog_row, catalog_payload, catalog)
        if catalog_key not in actual_map and catalog_key not in desired_map:
            mismatches.append(
                {
                    "key": catalog_key,
                    "component": catalog_component,
                    "actual_present": False,
                    "desired_present": False,
                    "actual_ownership": None,
                    "desired_ownership": catalog_owner,
                    "comparable": True,
                    "result": "MISMATCH",
                    "reason": "CURRENT-owned conditional object required for active mode is absent",
                }
            )

    for component in COMPONENTS:
        components[component]["actual_present"] = any(item["component"] == component for item in actual_projection["entries"])
        components[component]["desired_present"] = any(item["component"] == component for item in desired_projection["entries"])
        components[component]["actual_ownership"] = sorted({item["ownership"] for item in actual_projection["entries"] if item["component"] == component})
        components[component]["desired_ownership"] = sorted({item["ownership"] for item in desired_projection["entries"] if item["component"] == component})

    if actual_projection["duplicate_keys"] or desired_projection["duplicate_keys"]:
        model_gaps.append(
            {
                "type": "DUPLICATE_SEMANTIC_IDENTITY",
                "actual": actual_projection["duplicate_keys"],
                "desired": desired_projection["duplicate_keys"],
            }
        )
    if actual_projection["unknown_entries"] or desired_projection["unknown_entries"]:
        model_gaps.append(
            {
                "type": "UNKNOWN_OWNERSHIP",
                "actual": [item["key"] for item in actual_projection["unknown_entries"]],
                "desired": [item["key"] for item in desired_projection["unknown_entries"]],
            }
        )
    unknown_catalog = []
    for catalog_row in catalog:
        if not isinstance(catalog_row, Mapping):
            continue
        if classify_object_ownership(catalog_row) == "UNKNOWN":
            unknown_catalog.append(
                str(catalog_row.get("logical_id") or catalog_row.get("semantic_id") or catalog_row.get("physical_name") or catalog_row.get("name"))
            )
    if unknown_catalog:
        model_gaps.append(
            {
                "type": "UNKNOWN_OWNERSHIP",
                "catalog": sorted(unknown_catalog),
                "reason": "formal inventory entry has no ownership classification",
            }
        )
    if actual_projection.get("unsupported_keys") or desired_projection.get("unsupported_keys"):
        model_gaps.append(
            {
                "type": "UNSUPPORTED_OBJECT",
                "actual": actual_projection.get("unsupported_keys", []),
                "desired": desired_projection.get("unsupported_keys", []),
                "reason": "unsupported semantic object cannot be compared",
            }
        )

    for key in sorted(set(actual_map) | set(desired_map)):
        old = actual_map.get(key)
        new = desired_map.get(key)
        row = old or new
        assert row is not None
        actual_ownership = old.get("ownership") if old else None
        desired_ownership = new.get("ownership") if new else None
        ownership = desired_ownership or actual_ownership
        component = str((old or new).get("component") or "OTHER")
        if old is not None and new is not None and actual_ownership != desired_ownership:
            if "UNKNOWN" in {actual_ownership, desired_ownership}:
                model_gaps.append(
                    {
                        "type": "OWNERSHIP_METADATA_GAP",
                        "key": key,
                        "component": component,
                        "actual_ownership": actual_ownership,
                        "desired_ownership": desired_ownership,
                        "reason": "ownership class is unknown or disagrees",
                    }
                )
                continue
            if actual_ownership in NON_COMPARABLE_OWNERSHIP or desired_ownership in NON_COMPARABLE_OWNERSHIP:
                model_gaps.append(
                    {
                        "type": "OWNERSHIP_SCOPE_MISMATCH",
                        "key": key,
                        "component": component,
                        "actual_ownership": actual_ownership,
                        "desired_ownership": desired_ownership,
                        "reason": "actual and desired ownership classes disagree",
                    }
                )
                continue
        if ownership == "UNKNOWN":
            continue
        if ownership in NON_COMPARABLE_OWNERSHIP:
            out_of_scope.append(
                {
                    "key": key,
                    "component": component,
                    "ownership": ownership,
                    "actual_present": old is not None,
                    "desired_present": new is not None,
                    "observation_status": "OBSERVED" if old is not None else "ABSENT",
                    "observation_retained": True,
                }
            )
            continue
        if old is None or new is None:
            missing_side = "desired" if old is not None else "actual"
            gap_id = (old or new).get("payload", {}).get("known_gap") if (old or new) else None
            if gap_id in KNOWN_CURRENT_GAP_IDS:
                known_gaps.append(
                    {
                        "key": key,
                        "component": component,
                        "id": gap_id,
                        "actual_present": old is not None,
                        "desired_present": new is not None,
                        "reason": "approved CURRENT gap remains explicit",
                    }
                )
                continue
            # Conditional objects may be absent in either side.  The absence
            # is retained in diagnostics, but it is not an owned mismatch.
            conditional_required = bool(
                (old or {}).get("conditional_required") or (new or {}).get("conditional_required")
            )
            if ownership == "CONDITIONAL_CURRENT" and not conditional_required:
                components[component]["reason"] = "conditional object absent; equality not required"
                continue
            mismatches.append(
                {
                    "key": key,
                    "component": component,
                    "actual_present": old is not None,
                    "desired_present": new is not None,
                    "actual_ownership": old.get("ownership") if old else None,
                    "desired_ownership": new.get("ownership") if new else None,
                    "comparable": True,
                    "result": "MISMATCH",
                    "reason": "CURRENT-owned object missing from {}".format(missing_side),
                }
            )
            continue
        if old["payload"] != new["payload"]:
            gap_id = old["payload"].get("known_gap") or new["payload"].get("known_gap")
            if gap_id in KNOWN_CURRENT_GAP_IDS:
                known_gaps.append(
                    {
                        "key": key,
                        "component": component,
                        "id": gap_id,
                        "actual_present": True,
                        "desired_present": True,
                        "reason": "approved CURRENT gap remains explicit",
                    }
                )
                continue
            mismatches.append(
                {
                    "key": key,
                    "component": component,
                    "actual_present": True,
                    "desired_present": True,
                    "actual_ownership": old["ownership"],
                    "desired_ownership": new["ownership"],
                    "comparable": True,
                    "result": "MISMATCH",
                    "reason": "CURRENT-owned semantic payload differs",
                    "actual": old["payload"],
                    "desired": new["payload"],
                }
            )

    # A formal catalog also describes objects that are currently absent.  Keep
    # those absences visible as observations so a safety audit cannot confuse
    # "not observed" with "present", while still excluding non-comparable
    # classes from CURRENT-owned equality.
    observed_keys = set(actual_map) | set(desired_map)
    for catalog_row in catalog:
        if not isinstance(catalog_row, Mapping):
            continue
        catalog_ownership = classify_object_ownership(catalog_row)
        if catalog_ownership not in NON_COMPARABLE_OWNERSHIP:
            continue
        catalog_component = _component_for_object(catalog_row)
        catalog_payload = _canonical_object_payload(catalog_row, catalog_ownership, catalog_component)
        catalog_key = _object_key(catalog_row, catalog_payload, catalog)
        if catalog_key in observed_keys or any(item["key"] == catalog_key for item in out_of_scope):
            continue
        out_of_scope.append(
            {
                "key": catalog_key,
                "component": catalog_component,
                "ownership": catalog_ownership,
                "actual_present": False,
                "desired_present": False,
                "observation_status": "ABSENT",
                "observation_retained": True,
            }
        )

    for row in mismatches:
        component = components[row["component"]]
        component["comparable"] = True
        component["result"] = "MISMATCH"
        component["reason"] = row["reason"]
    for gap in known_gaps:
        component = components[gap["component"]]
        if component["result"] == "NOT_OBSERVED":
            component["comparable"] = False
            component["result"] = "KNOWN_CURRENT_GAP"
            component["reason"] = "approved CURRENT gap remains explicit"
    for gap in model_gaps:
        component_name = str(gap.get("component") or ("DNS" if str(gap.get("type", "")).startswith("DNS_") else "OTHER"))
        if component_name not in components:
            component_name = "OTHER"
        component = components[component_name]
        if component["result"] not in {"MISMATCH", "OUT_OF_SCOPE_LEGACY_OBJECT", "OUT_OF_SCOPE"}:
            component["comparable"] = False
            component["result"] = "MODEL_GAP"
            component["reason"] = str(gap.get("reason") or gap.get("type") or "semantic model incomplete")
    for row in out_of_scope:
        component = components[row["component"]]
        if component["result"] == "NOT_OBSERVED":
            component["result"] = "OUT_OF_SCOPE_LEGACY_OBJECT" if row["ownership"] == "LEGACY_ONLY_SAFETY" else "OUT_OF_SCOPE"
            component["reason"] = "observed and retained outside CURRENT-owned equality"
    for component in components.values():
        if component["result"] == "NOT_OBSERVED" and component["actual_present"] and component["desired_present"]:
            component["comparable"] = True
            component["result"] = "MATCH"
            component["reason"] = "CURRENT-owned semantic entries agree"

    dns_result: Optional[Dict[str, Any]] = None
    if dns_actual is not None or dns_desired is not None:
        dns_result = compare_dns_semantics(dns_actual or {}, dns_desired or {})
        dns_component = components["DNS"]
        dns_component["actual_present"] = True
        dns_component["desired_present"] = True
        dns_component["actual_ownership"] = sorted(
            {item["actual_ownership"] for item in dns_result["fields"] if item.get("actual_ownership")}
        )
        dns_component["desired_ownership"] = sorted(
            {item["desired_ownership"] for item in dns_result["fields"] if item.get("desired_ownership")}
        )
        dns_component["comparable"] = dns_result["parity"] not in {"COMPARATOR_MODEL_GAP", "INSUFFICIENT_EVIDENCE"}
        dns_component["result"] = dns_result["parity"]
        dns_component["reason"] = dns_result["reason"]
        if dns_result["parity"] == "MISMATCH":
            mismatches.append(
                {
                    "key": "dns:typed-fields",
                    "component": "DNS",
                    "actual_present": True,
                    "desired_present": True,
                    "actual_ownership": "CURRENT_OWNED",
                    "desired_ownership": "CURRENT_OWNED",
                    "comparable": True,
                    "result": "MISMATCH",
                    "reason": dns_result["reason"],
                    "fields": dns_result["mismatches"],
                }
            )
        elif dns_result["parity"] in {"COMPARATOR_MODEL_GAP", "INSUFFICIENT_EVIDENCE"}:
            model_gaps.append({"type": "DNS_" + dns_result["parity"], "reason": dns_result["reason"], "fields": dns_result["fields"]})

    if model_gaps:
        parity = "MODEL_GAP"
    elif mismatches:
        parity = "MISMATCH"
    elif known_gaps:
        parity = "KNOWN_CURRENT_GAP"
    else:
        parity = "MATCH"
    # A model-gap result must not be presented as a component match even when
    # all currently comparable fields happened to agree.
    if model_gaps:
        for row in components.values():
            if row["result"] == "MATCH" and not row["comparable"]:
                row["result"] = "MODEL_GAP"

    # Keep the object projection hash for callers that audit NFT inventory,
    # and expose a second hash covering every CURRENT-owned semantic layer.
    # DNS is intentionally included only when a typed DNS intent was supplied;
    # an omitted DNS input remains an explicit model boundary rather than an
    # inferred value.
    actual_current_owned_hash = semantic_hash(
        {
            "objects": actual_projection["owned_hash"],
            "dns": dns_result.get("actual_hash") if dns_result is not None else None,
        }
    )
    desired_current_owned_hash = semantic_hash(
        {
            "objects": desired_projection["owned_hash"],
            "dns": dns_result.get("desired_hash") if dns_result is not None else None,
        }
    )
    return {
        "schema": SEMANTIC_MODEL_SCHEMA,
        "parity": parity,
        "framework": "PASS" if parity in {"MATCH", "MISMATCH", "KNOWN_CURRENT_GAP", "MODEL_GAP"} else "FAIL",
        "actual_observation_hash": actual_projection["observation_hash"],
        "desired_observation_hash": desired_projection["observation_hash"],
        "actual_owned_hash": actual_projection["owned_hash"],
        "desired_owned_hash": desired_projection["owned_hash"],
        "actual_current_owned_hash": actual_current_owned_hash,
        "desired_current_owned_hash": desired_current_owned_hash,
        "owned_projection_hash": {
            "actual": actual_current_owned_hash,
            "desired": desired_current_owned_hash,
            "objects_actual": actual_projection["owned_hash"],
            "objects_desired": desired_projection["owned_hash"],
        },
        "components": components,
        "mismatches": mismatches,
        "known_gaps": known_gaps,
        "model_gaps": model_gaps,
        "out_of_scope_observations": out_of_scope,
        "observation_retained": True,
        "dns": dns_result,
        "approved_equivalences_only": True,
        "new_ad_hoc_equivalence": 0,
        "dns_direct_port_equivalence": False,
        "actual_projection": actual_projection,
        "desired_projection": desired_projection,
    }


def _field_source(source: Mapping[str, Any], field: str) -> Optional[str]:
    candidates = [source]
    nested = source.get("dns_semantics") or source.get("dns")
    if isinstance(nested, Mapping):
        candidates.append(nested)
    for candidate in candidates:
        sources = candidate.get("sources") or candidate.get("field_sources") or {}
        if isinstance(sources, Mapping):
            value = sources.get(field) or sources.get(field.lower())
            if value is not None:
                return str(value)
        fields = candidate.get("fields")
        if isinstance(fields, Mapping) and isinstance(fields.get(field), Mapping):
            value = fields[field].get("source")
            if value is not None:
                return str(value)
        # A typed input may put value/ownership/source beside each field in
        # the DNS mapping itself.  Treat that as source metadata, but never
        # infer a source for a different field or layer.
        candidate_field = candidate.get(field)
        if isinstance(candidate_field, Mapping):
            value = candidate_field.get("source")
            if value is not None:
                return str(value)
        for alias, canonical in _FIELD_ALIASES.items():
            if canonical == field and isinstance(candidate.get(alias), Mapping):
                value = candidate[alias].get("source")
                if value is not None:
                    return str(value)
    return None


def _canonical_port(value: Any, field: str) -> str:
    if isinstance(value, bool):
        raise SemanticModelError("{} must be a port".format(field))
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]{1,5}", text):
        raise SemanticModelError("{} must be a decimal port".format(field))
    number = int(text)
    if not 1 <= number <= 65535:
        raise SemanticModelError("{} port out of range".format(field))
    return str(number)


def _canonical_endpoint(value: Any, field: str, separator: str) -> str:
    text = str(value).strip()
    if any(char.isspace() for char in text) or not text:
        raise SemanticModelError("{} endpoint is invalid".format(field))
    if separator not in text:
        raise SemanticModelError("{} endpoint must contain {}".format(field, separator))
    host, port = text.rsplit(separator, 1)
    if not host or not port:
        raise SemanticModelError("{} endpoint is incomplete".format(field))
    if host.startswith("[") or host.endswith("]"):
        if not (host.startswith("[") and host.endswith("]")):
            raise SemanticModelError("{} endpoint host is invalid".format(field))
        host = host[1:-1]
        if not host:
            raise SemanticModelError("{} endpoint host is invalid".format(field))
    # Hosts are intentionally kept as supplied except for IP canonicalization;
    # a hostname is still a typed endpoint and is not DNS-resolved here.
    try:
        host = str(ipaddress.ip_address(host))
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", host):
            raise SemanticModelError("{} endpoint host is invalid".format(field))
    # Keep bracketed IPv6 listeners canonical and unambiguous.  Upstream
    # ``host#port`` values do not need brackets because ``#`` is not an IPv6
    # separator; listener ``host:port`` values do.
    if separator == ":" and ":" in host and not host.startswith("["):
        host = "[{}]".format(host)
    return "{}{}{}".format(host, separator, _canonical_port(port, field))


def _canonical_dns_field(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field in {"DNS_FIREWALL_LAN_TARGET", "DNS_FIREWALL_ROUTER_TARGET", "DNSMASQ_LISTEN_TARGET"}:
        return _canonical_port(value, field)
    if field == "DNSMASQ_UPSTREAM_TARGET":
        return _canonical_endpoint(value, field, "#")
    if field == "MIHOMO_DNS_LISTENER":
        return _canonical_endpoint(value, field, ":")
    if field in {"DNS_SCOPE_IPV4", "DNS_SCOPE_IPV6", "DNS_LOOP_PREVENTION"}:
        if isinstance(value, Mapping):
            return {str(key): value[key] for key in sorted(value)}
        text = str(value).strip()
        if not text:
            raise SemanticModelError("{} cannot be empty".format(field))
        return text
    raise SemanticModelError("unknown DNS field: {}".format(field))


def build_dns_semantic_intent(
    source: Mapping[str, Any],
    *,
    field_ownership: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Normalize typed DNS fields without inferring one layer from another."""

    if not isinstance(source, Mapping):
        raise SemanticModelError("DNS source must be an object")
    nested = source.get("dns_semantics") or source.get("dns")
    values: Mapping[str, Any] = nested if isinstance(nested, Mapping) else source
    if isinstance(source.get("fields"), Mapping):
        values = source["fields"]
    ownership_input = field_ownership or source.get("ownership") or source.get("field_ownership") or {}
    if not ownership_input and isinstance(values.get("ownership"), Mapping):
        ownership_input = values.get("ownership")
    if not isinstance(ownership_input, Mapping):
        raise SemanticModelError("DNS field ownership must be an object")
    rows: Dict[str, Dict[str, Any]] = {}
    for field in DNS_FIELDS:
        raw: Any = None
        if field in values:
            candidate = values.get(field)
            if isinstance(candidate, Mapping) and "value" in candidate:
                raw = candidate.get("value")
            else:
                raw = candidate
        else:
            for alias, canonical in _FIELD_ALIASES.items():
                if canonical == field and alias in values:
                    raw = values.get(alias)
                    break
        if isinstance(raw, Mapping) and "value" in raw:
            raw = raw.get("value")
        owner_raw = ownership_input.get(field) or ownership_input.get(field.lower())
        candidate_meta = values.get(field)
        if isinstance(candidate_meta, Mapping) and candidate_meta.get("ownership") not in (None, ""):
            owner_raw = candidate_meta.get("ownership")
        owner = _canonical_class(owner_raw) if owner_raw not in (None, "") else _DEFAULT_DNS_OWNERSHIP[field]
        canonical = _canonical_dns_field(field, raw) if raw is not None else None
        rows[field] = {
            "field": field,
            "value": canonical,
            "ownership": owner,
            "source": _field_source(source, field),
            "evidence": "PRESENT" if raw is not None else "MISSING",
        }
    return {
        "schema": SEMANTIC_MODEL_SCHEMA,
        "fields": rows,
        "semantic_hash": semantic_hash(
            {
                field: {"value": row["value"], "ownership": row["ownership"], "evidence": row["evidence"]}
                for field, row in rows.items()
            }
        ),
    }


def compare_dns_semantics(
    actual: Mapping[str, Any],
    desired: Mapping[str, Any],
    *,
    field_ownership: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Compare DNS layers field-by-field; never compare 53 to 7874 transitively."""

    # Re-normalize even an object carrying our schema marker.  Callers may
    # have received a model from a file or test fixture and then altered a
    # field; bypassing the strict typed parser here would let an invalid port,
    # endpoint, or ownership value reach equality unchecked.
    old = build_dns_semantic_intent(actual, field_ownership=field_ownership)
    new = build_dns_semantic_intent(desired, field_ownership=field_ownership)
    fields: List[Dict[str, Any]] = []
    mismatches: List[Dict[str, Any]] = []
    gaps: List[Dict[str, Any]] = []
    for field in DNS_FIELDS:
        a = old["fields"][field]
        d = new["fields"][field]
        owner = d["ownership"] if d["ownership"] != "UNKNOWN" else a["ownership"]
        comparable = owner in CURRENT_OWNERSHIP
        ownership_disagrees = a["ownership"] != d["ownership"]
        if "UNKNOWN" in {a["ownership"], d["ownership"]}:
            result = "COMPARATOR_MODEL_GAP"
            reason = "field ownership/source is not defined on both sides"
            gaps.append({"field": field, "reason": reason})
        elif ownership_disagrees:
            result = "COMPARATOR_MODEL_GAP"
            reason = "actual and desired field ownership classes disagree"
            gaps.append({"field": field, "reason": reason})
        elif owner in NON_COMPARABLE_OWNERSHIP:
            result = "MATCH"
            reason = "field is outside CURRENT-owned DNS equality"
            comparable = False
        elif d.get("source") is None:
            result = "COMPARATOR_MODEL_GAP"
            reason = "desired DNS field has no formal source"
            gaps.append({"field": field, "reason": reason})
        elif a.get("source") is None:
            result = "INSUFFICIENT_EVIDENCE"
            reason = "actual DNS field has no evidence source"
            gaps.append({"field": field, "reason": reason})
        elif a["value"] is None or d["value"] is None:
            result = "INSUFFICIENT_EVIDENCE"
            reason = "actual or desired DNS evidence is missing"
            gaps.append({"field": field, "reason": reason})
        elif a["value"] != d["value"]:
            result = "MISMATCH"
            reason = "typed DNS field differs"
            mismatches.append(
                {
                    "field": field,
                    "actual": a["value"],
                    "desired": d["value"],
                    "ownership": owner,
                    "reason": reason,
                }
            )
        else:
            result = "MATCH"
            reason = "typed DNS field agrees"
        fields.append(
            {
                "field": field,
                "actual": a["value"],
                "desired": d["value"],
                "actual_ownership": a["ownership"],
                "desired_ownership": d["ownership"],
                "ownership": owner,
                "actual_source": a.get("source"),
                "desired_source": d.get("source"),
                "comparable": comparable,
                "result": result,
                "reason": reason,
            }
        )
    if gaps:
        parity = "COMPARATOR_MODEL_GAP" if any(item["result"] == "COMPARATOR_MODEL_GAP" for item in fields) else "INSUFFICIENT_EVIDENCE"
    elif mismatches:
        parity = "MISMATCH"
    else:
        parity = "MATCH"
    return {
        "schema": SEMANTIC_MODEL_SCHEMA,
        "parity": parity,
        "reason": "; ".join(item["reason"] for item in gaps + mismatches) if gaps or mismatches else "all comparable DNS fields agree",
        "fields": fields,
        "mismatches": mismatches,
        "gaps": gaps,
        "dns_53_7874_direct_equivalence": False,
        "actual_hash": old["semantic_hash"],
        "desired_hash": new["semantic_hash"],
    }


def build_dns_fields_from_intent(
    intent: Mapping[str, Any],
    *,
    firewall_lan_target: Optional[Any] = None,
    firewall_router_target: Optional[Any] = None,
    sources: Optional[Mapping[str, str]] = None,
    field_ownership: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Extract only explicit firewall redirect targets from a normalized intent.

    dnsmasq and Mihomo values must be supplied by their own committed source;
    this helper intentionally leaves those fields missing.
    """

    values: Dict[str, Any] = {}
    if firewall_lan_target is not None:
        values["DNS_FIREWALL_LAN_TARGET"] = firewall_lan_target
    if firewall_router_target is not None:
        values["DNS_FIREWALL_ROUTER_TARGET"] = firewall_router_target
    result = build_dns_semantic_intent({"dns_semantics": values, "sources": dict(sources or {})}, field_ownership=field_ownership)
    return result


__all__ = [
    "COMPONENTS",
    "CONDITIONAL_CURRENT",
    "CURRENT_OWNERSHIP",
    "CURRENT_OWNED",
    "DNS_FIELDS",
    "DNS_RESULT_VALUES",
    "FW4_BASE",
    "LEGACY_ONLY_SAFETY",
    "INACTIVE_MODE",
    "KNOWN_CURRENT_GAP_IDS",
    "NON_COMPARABLE_OWNERSHIP",
    "OWNERSHIP_CLASSES",
    "OPTIONAL_OBSERVATION",
    "OUT_OF_SCOPE",
    "SEMANTIC_MODEL_SCHEMA",
    "SemanticModelError",
    "UNKNOWN",
    "build_dns_fields_from_intent",
    "build_dns_semantic_intent",
    "build_semantic_projection",
    "classify_object_ownership",
    "compare_dns_semantics",
    "compare_semantic_intents",
    "semantic_hash",
]
