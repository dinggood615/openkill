#!/usr/bin/env python3
"""Development-only OpenKill semantic-action and abstract NFT IR.

This module deliberately stops before backend syntax.  It consumes the
versioned classifier and shadow-state models, describes owned topology and
dynamic sets, and emits a deterministic, machine-readable intermediate
representation.  It never imports an init script and never executes a
command, opens a socket, or writes a file.
"""

from __future__ import annotations

import ipaddress
import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from openkill_classifier_model import (
    CLASSIFIER_CONTRACT_VERSION,
    CURRENT_PRECEDENCE,
    DECISIONS,
    MATCH_REASONS,
    PRECEDENCE_TABLES,
    TARGET_PRECEDENCE,
    backend_action as _classifier_backend_action,
    classify,
    detect_matches,
    validate_context,
)
from openkill_shadow_adapter import normalize_state


SEMANTIC_SPEC_VERSION = 1
NFT_IR_VERSION = 1
NFT_IR_SCHEMA = "OPENKILL_NFT_IR_V1"
OWNERSHIP_MANIFEST_VERSION = 1
OWNERSHIP_MANIFEST_SCHEMA = "OPENKILL_NFT_MANIFEST_V1"
# Public aliases make the versioned names unambiguous to future development
# tools without changing the serialized schema.
OPENKILL_NFT_MANIFEST_V1 = OWNERSHIP_MANIFEST_SCHEMA
NFT_IR_SCHEMA_VERSION = NFT_IR_VERSION
DEFAULT_RENDERER_PROFILE = "current"
RENDERER_PROFILES: Tuple[str, ...] = ("current", "target")
RENDERER_BACKENDS: Tuple[str, ...] = ("ABSTRACT_NFT",)

COMPONENTS: Tuple[str, ...] = (
    "TOPOLOGY",
    "LOCAL",
    "NODE",
    "CHINA",
    "ACCESS",
    "SERVICE",
    "DNS",
    "PROXY_ACTION",
    "WAN_INPUT",
    "UPNP",
    "OWNER",
)

CHAIN_ROLES: Tuple[str, ...] = (
    "PREROUTING_PROXY",
    "PREROUTING_MANGLE",
    "OUTPUT_PROXY",
    "OUTPUT_MANGLE",
    "POSTROUTING",
    "DNS_LAN",
    "DNS_ROUTER",
    "WAN_INPUT",
    "UPNP",
)

OBJECT_TYPES: Tuple[str, ...] = (
    "table_ref",
    "chain",
    "chain_ref",
    "set",
    "rule",
    "jump",
)

MATCH_TYPES: Tuple[str, ...] = (
    "family",
    "direction",
    "protocol",
    "source_set",
    "destination_set",
    "port_set",
    "connection",
    "owner",
    "interface_role",
    "semantic_flag",
    "service",
)

ACTION_TYPES: Tuple[str, ...] = (
    "RETURN_NATIVE",
    "REDIRECT_PROXY",
    "MARK_PROXY",
    "TPROXY_PROXY",
    "DNS_REDIRECT",
    "ACCESS_DENY_REQUIRED",
    "JUMP",
    "ACCEPT_IF_REQUIRED",
    "NOT_OWNED",
    "UNSUPPORTED_ACTION",
    "CONTINUE_POLICY",
    "UNRESOLVED_SEMANTIC",
    "ACTION_FROM_CLASSIFICATION",
)

DIFF_CATEGORIES: Tuple[str, ...] = (
    "NO_CHANGE",
    "SET_ELEMENT_CHANGE",
    "RULE_CHANGE",
    "TOPOLOGY_CHANGE",
    "TOPOLOGY_ADD",
    "TOPOLOGY_REMOVE",
    "COMPONENT_CHANGE",
)

MARK_ABI = {
    "version": 1,
    "mark": "0x162",
    "mask": "0xffffffff",
    "route_table": 354,
    "rule_preference": 1888,
}

# DNS has two deliberately separate ports in the CURRENT contract.  The
# configured ``dns`` proxy port is Mihomo's loopback listener (and the
# dnsmasq upstream), while the stable mode-1 firewall entry point is the
# dnsmasq listener.  OpenWrt's dnsmasq listener defaults to port 53 and the
# production configuration does not override that default.
DEFAULT_MIHOMO_DNS_PORT = 7874
DEFAULT_DNSMASQ_LISTEN_PORT = 53


class NFTIRValidationError(ValueError):
    """Raised when an abstract IR is malformed or unsafe to consume."""


def _norm(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_")


def _family_label(family: str) -> str:
    value = _norm(family)
    if value == "IPV4":
        return "IPv4"
    if value == "IPV6":
        return "IPv6"
    raise NFTIRValidationError("unknown family: {!r}".format(family))


def _profile(profile: str) -> str:
    if not isinstance(profile, str) or profile.lower() not in RENDERER_PROFILES:
        raise NFTIRValidationError("renderer profile must be current or target")
    return profile.lower()


def _backend(backend: str) -> str:
    if not isinstance(backend, str) or backend.upper() not in RENDERER_BACKENDS:
        raise NFTIRValidationError("unsupported renderer backend: {!r}".format(backend))
    return backend.upper()


def _canonical_ip(value: Any, family: str) -> str:
    try:
        address = ipaddress.ip_address(str(value).strip())
    except ValueError as exc:
        raise NFTIRValidationError("invalid {} address: {!r}".format(family, value)) from exc
    if (address.version == 4 and family != "IPv4") or (address.version == 6 and family != "IPv6"):
        raise NFTIRValidationError("address family mismatch: {!r}".format(value))
    return str(address)


def _canonical_prefix(value: Any, family: str) -> str:
    try:
        network = ipaddress.ip_network(str(value).strip(), strict=False)
    except ValueError as exc:
        raise NFTIRValidationError("invalid {} prefix: {!r}".format(family, value)) from exc
    if (network.version == 4 and family != "IPv4") or (network.version == 6 and family != "IPv6"):
        raise NFTIRValidationError("prefix family mismatch: {!r}".format(value))
    return str(network)


def canonical_set_elements(
    values: Iterable[Any],
    element_type: str,
    family: Optional[str] = None,
    *,
    host_semantic: bool = False,
) -> List[Any]:
    """Canonicalize, deduplicate, and stably order one dynamic set."""

    kind = _norm(element_type)
    if kind not in {"ADDRESS", "PREFIX", "PORT", "MAC", "INTERVAL", "TOKEN"}:
        raise NFTIRValidationError("unknown set element type: {!r}".format(element_type))
    canonical: Set[Any] = set()
    for raw in values or ():
        if kind == "ADDRESS":
            if family not in {"IPv4", "IPv6"}:
                raise NFTIRValidationError("address set requires a family")
            item = _canonical_ip(raw, family)
            if host_semantic and family == "IPv6":
                item = "{}/128".format(item)
        elif kind == "PREFIX":
            if family not in {"IPv4", "IPv6"}:
                raise NFTIRValidationError("prefix set requires a family")
            item = _canonical_prefix(raw, family)
        elif kind == "PORT":
            if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= 65535:
                raise NFTIRValidationError("invalid port: {!r}".format(raw))
            item = int(raw)
        elif kind == "MAC":
            item = str(raw).strip().lower()
            parts = item.split(":")
            if len(parts) != 6 or any(len(part) != 2 for part in parts):
                raise NFTIRValidationError("invalid MAC: {!r}".format(raw))
            try:
                int("".join(parts), 16)
            except ValueError as exc:
                raise NFTIRValidationError("invalid MAC: {!r}".format(raw)) from exc
        elif kind == "INTERVAL":
            text = str(raw).strip()
            bounds = text.split("-", 1)
            if len(bounds) != 2:
                raise NFTIRValidationError("invalid interval: {!r}".format(raw))
            if family not in {"IPv4", "IPv6"}:
                raise NFTIRValidationError("interval set requires a family")
            start = _canonical_ip(bounds[0], family)
            end = _canonical_ip(bounds[1], family)
            if ipaddress.ip_address(start) > ipaddress.ip_address(end):
                raise NFTIRValidationError("interval start is after end: {!r}".format(raw))
            item = "{}-{}".format(start, end)
        else:
            item = str(raw).strip()
            if not item:
                raise NFTIRValidationError("empty token")
        canonical.add(item)
    return sorted(canonical, key=lambda item: (str(type(item)), str(item)))


def _owned_metadata(
    *,
    logical_id: str,
    physical_name: str,
    object_type: str,
    component: str,
    family: str = "ALL",
    parent_table: str = "inet fw4",
) -> Dict[str, Any]:
    return {
        "object_type": object_type,
        "logical_id": logical_id,
        "physical_name": physical_name,
        "owner": "OPENKILL",
        "ownership": "OWNED",
        "parent_owner": "FW4",
        "parent_table": parent_table,
        "component": component,
        "family": family,
        "semantic_spec_version": SEMANTIC_SPEC_VERSION,
    }


def _external_ref(
    logical_id: str,
    physical_name: str,
    object_type: str = "chain_ref",
    *,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    entry = {
        "object_type": object_type,
        "logical_id": logical_id,
        "physical_name": physical_name,
        "owner": "FW4",
        "ownership": "EXTERNAL",
        "parent_owner": "FW4",
        "parent_table": "inet fw4",
        "component": "TOPOLOGY",
        "family": "ALL",
        "semantic_spec_version": SEMANTIC_SPEC_VERSION,
        "external": True,
        # fw4's actual hook priorities are an external runtime fact.  The
        # IR intentionally carries no guessed number for them.
        "priority": "EXTERNAL_UNVERIFIED",
    }
    if role:
        entry["role"] = role
    return entry


_FW4_REFS: Tuple[Tuple[str, str, str], ...] = (
    ("FW4_DSTNAT", "dstnat", "DNS_LAN"),
    ("FW4_MANGLE_PREROUTING", "mangle_prerouting", "PREROUTING_MANGLE"),
    ("FW4_MANGLE_OUTPUT", "mangle_output", "OUTPUT_MANGLE"),
    ("FW4_OUTPUT", "output", "OUTPUT_PROXY"),
    ("FW4_FORWARD", "forward", "PREROUTING_PROXY"),
    ("FW4_INPUT", "input", "WAN_INPUT"),
    ("FW4_SRCNAT", "srcnat", "POSTROUTING"),
    ("FW4_UPNP", "upnp", "UPNP"),
)


def build_static_topology(owner: str = "OPENKILL", run_mode: str = "TUN") -> Dict[str, Any]:
    """Return the logical topology without backend insertion syntax."""

    owner_value = _norm(owner or "OPENKILL")
    mode = _norm(run_mode or "TUN")
    if owner_value not in {"OPENKILL", "MIHOMO", "DISABLED", "UNKNOWN"}:
        raise NFTIRValidationError("unknown owner: {!r}".format(owner))
    if mode not in {"TUN", "TPROXY", "REDIRECT"}:
        raise NFTIRValidationError("unknown run mode: {!r}".format(run_mode))

    objects: List[Dict[str, Any]] = [_external_ref("FW4_TABLE", "inet fw4", "table_ref")]
    for logical_id, physical_name, role in _FW4_REFS:
        objects.append(_external_ref(logical_id, physical_name, role=role))

    owned: List[Dict[str, Any]] = []
    if owner_value == "OPENKILL":
        chain_names = {
            "PREROUTING_PROXY": ("openkill", "openkill_v6"),
            "PREROUTING_MANGLE": ("openkill_mangle", "openkill_mangle_v6"),
            "OUTPUT_PROXY": ("openkill_output", "openkill_output_v6"),
            "OUTPUT_MANGLE": ("openkill_mangle_output", "openkill_mangle_output_v6"),
            "POSTROUTING": ("openkill_post", "openkill_post_v6"),
            "WAN_INPUT": ("openkill_wan_input", "openkill_wan6_input"),
            "DNS_LAN": ("openkill_dns_hijack", "openkill_dns_hijack_v6"),
            "DNS_ROUTER": ("openkill_dns_redirect", "openkill_dns_redirect_v6"),
        }
        for role, (v4_name, v6_name) in chain_names.items():
            for family, physical_name, suffix in (
                ("IPv4", v4_name, "V4"),
                ("IPv6", v6_name, "V6"),
            ):
                owned.append(
                    dict(
                        _owned_metadata(
                            logical_id="OPENKILL_{}_{}".format(role, suffix),
                            physical_name=physical_name,
                            object_type="chain",
                            component="WAN_INPUT" if role == "WAN_INPUT" else ("DNS" if role.startswith("DNS_") else "TOPOLOGY"),
                            family=family,
                        ),
                        role=role,
                        base_chain=False,
                    )
                )
        # UPnP lease exclusions are a single current inet chain.  The lease
        # entries are runtime-dynamic, but the chain itself is a stable
        # OpenKill-owned object and is kept separate from policy sets.
        owned.append(
            dict(
                _owned_metadata(
                    logical_id="OPENKILL_UPNP",
                    physical_name="openkill_upnp",
                    object_type="chain",
                    component="UPNP",
                ),
                role="UPNP",
                base_chain=False,
            )
        )
        # This is the one current OpenKill-owned hook chain.  Its priority is
        # source-audited (-1); no fw4 priority is guessed here.
        owned.append(
            dict(
                _owned_metadata(
                    logical_id="OPENKILL_NAT_OUTPUT_CURRENT",
                    physical_name="nat_output",
                    object_type="chain",
                    component="TOPOLOGY",
                ),
                role="OUTPUT_PROXY",
                base_chain=True,
                type="nat",
                hook="OUTPUT",
                priority=-1,
                current_only=True,
            )
        )
        if mode == "TPROXY":
            for family, suffix in (("IPv4", "V4"), ("IPv6", "V6")):
                owned.append(
                    dict(
                        _owned_metadata(
                            logical_id="OPENKILL_TPROXY_{}".format(suffix),
                            physical_name="openkill_tproxy{}".format("_v6" if suffix == "V6" else ""),
                            object_type="chain",
                            component="PROXY_ACTION",
                            family=family,
                        ),
                        role="PREROUTING_PROXY",
                        base_chain=False,
                        capability="TPROXY",
                    )
                )
        objects.extend(owned)

    jumps: List[Dict[str, Any]] = []
    if owner_value == "OPENKILL":
        for family, suffix in (("IPv4", "V4"), ("IPv6", "V6")):
            jumps.extend(
                [
                    dict(
                        _owned_metadata(
                            logical_id="ATTACH_MANGLE_PREROUTING_{}".format(suffix),
                            physical_name="jump_mangle_prerouting_{}".format(suffix.lower()),
                            object_type="jump",
                            component="TOPOLOGY",
                            family=family,
                        ),
                        from_chain="FW4_MANGLE_PREROUTING",
                        to_chain="OPENKILL_PREROUTING_MANGLE_{}".format(suffix),
                    ),
                    dict(
                        _owned_metadata(
                            logical_id="ATTACH_MANGLE_OUTPUT_{}".format(suffix),
                            physical_name="jump_mangle_output_{}".format(suffix.lower()),
                            object_type="jump",
                            component="TOPOLOGY",
                            family=family,
                        ),
                        from_chain="FW4_MANGLE_OUTPUT",
                        to_chain="OPENKILL_OUTPUT_MANGLE_{}".format(suffix),
                    ),
                    dict(
                        _owned_metadata(
                            logical_id="ATTACH_UPNP_{}".format(suffix),
                            physical_name="jump_upnp_{}".format(suffix.lower()),
                            object_type="jump",
                            component="UPNP",
                            family=family,
                        ),
                        from_chain="OPENKILL_PREROUTING_MANGLE_{}".format(suffix),
                        to_chain="OPENKILL_UPNP",
                    ),
                ]
            )
        jumps.append(
            dict(
                _owned_metadata(
                    logical_id="ATTACH_NAT_OUTPUT_CURRENT",
                    physical_name="jump_nat_output",
                    object_type="jump",
                    component="TOPOLOGY",
                ),
                from_chain="FW4_OUTPUT",
                to_chain="OPENKILL_NAT_OUTPUT_CURRENT",
            )
        )
    objects.extend(jumps)
    return {
        "objects": objects,
        "chains": [obj for obj in objects if obj.get("object_type") == "chain"],
        "chain_refs": [obj for obj in objects if obj.get("object_type") in {"chain_ref", "table_ref"}],
        "jumps": [obj for obj in objects if obj.get("object_type") == "jump"],
        "owner_state": owner_value,
        "run_mode": mode,
        "external_priority_policy": "EXTERNAL_UNVERIFIED",
    }


_SET_SPECS: Tuple[Tuple[str, str, str, str, str, str], ...] = (
    ("local4", "LOCAL_V4", "localnetwork", "PREFIX", "IPv4", "LOCAL"),
    ("local6", "LOCAL_V6", "localnetwork6", "PREFIX", "IPv6", "LOCAL"),
    ("wan4", "WAN_HOST_V4", "openkill_wan_host4", "ADDRESS", "IPv4", "LOCAL"),
    ("wan6", "WAN_HOST_V6", "openkill_wan_host6", "ADDRESS", "IPv6", "LOCAL"),
    ("lan4", "LAN_V4", "openkill_lan4", "PREFIX", "IPv4", "LOCAL"),
    ("lan6", "LAN_V6", "openkill_lan6", "PREFIX", "IPv6", "LOCAL"),
    ("delegated6", "DELEGATED_V6", "openkill_delegated6", "PREFIX", "IPv6", "LOCAL"),
    ("node4", "NODE_ENDPOINT_V4", "openkill_node4", "ADDRESS", "IPv4", "NODE"),
    ("node6", "NODE_ENDPOINT_V6", "openkill_node6", "ADDRESS", "IPv6", "NODE"),
    ("china4", "CHINA_V4", "china_ip_route", "PREFIX", "IPv4", "CHINA"),
    ("china6", "CHINA_V6", "china_ip6_route", "PREFIX", "IPv6", "CHINA"),
    ("china_pass4", "CHINA_PASS_V4", "china_ip_route_pass", "PREFIX", "IPv4", "CHINA"),
    ("china_pass6", "CHINA_PASS_V6", "china_ip6_route_pass", "PREFIX", "IPv6", "CHINA"),
    ("fake_ip4", "FAKEIP_V4", "openkill_fakeip4", "PREFIX", "IPv4", "PROXY_ACTION"),
    ("fake_ip6", "FAKEIP_V6", "openkill_fakeip6", "PREFIX", "IPv6", "PROXY_ACTION"),
    ("user_direct4", "USER_DIRECT_V4", "openkill_user_direct4", "PREFIX", "IPv4", "ACCESS"),
    ("user_direct6", "USER_DIRECT_V6", "openkill_user_direct6", "PREFIX", "IPv6", "ACCESS"),
    ("user_proxy4", "USER_PROXY_V4", "openkill_user_proxy4", "PREFIX", "IPv4", "ACCESS"),
    ("user_proxy6", "USER_PROXY_V6", "openkill_user_proxy6", "PREFIX", "IPv6", "ACCESS"),
)


def _access_set_entries(state: Mapping[str, Any], family: str) -> List[Dict[str, Any]]:
    suffix = "4" if family == "IPv4" else "6"
    result = []
    for action in ("ALLOW", "BYPASS", "DENY"):
        networks = [entry["network"] for entry in state.get("access" + suffix, ()) if entry.get("action") == action]
        result.append(
            {
                "object_type": "set",
                "logical_id": "ACCESS_{}_{}".format(family.replace("IPv", "V"), action),
                "physical_name": "openkill_access{}_{}".format(suffix, action.lower()),
                "owner": "OPENKILL",
                "ownership": "OWNED",
                "parent_owner": "FW4",
                "parent_table": "inet fw4",
                "component": "ACCESS",
                "family": family,
                "semantic_spec_version": SEMANTIC_SPEC_VERSION,
                "element_type": "PREFIX",
                "elements": canonical_set_elements(networks, "PREFIX", family),
                "flags": ["DYNAMIC", "ACCESS_{}".format(action)],
                "dynamic": True,
                "access_action": action,
            }
        )
    return result


def _legacy_acl_inventory_sets(state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Expose production ACL names as dynamic semantic sets.

    Phase 3A does not invent a new ACL parser.  The normalized shadow state
    carries the address/action ACL facts; these additional entries keep the
    legacy names visible for renderer parity and remain empty when a source
    field is not present in the normalized fixture.
    """

    specs = (
        ("WAN_AC_BLACK_V4", "wan_ac_black_ips", "IPv4", "PREFIX"),
        ("WAN_AC_BLACK_V6", "wan_ac_black_ipv6s", "IPv6", "PREFIX"),
        ("WAN_AC_BLACK_PORTS", "wan_ac_black_ports", "ALL", "PORT"),
        ("LAN_AC_BLACK_V4", "lan_ac_black_ips", "IPv4", "PREFIX"),
        ("LAN_AC_BLACK_V6", "lan_ac_black_ipv6s", "IPv6", "PREFIX"),
        ("LAN_AC_BLACK_MACS", "lan_ac_black_macs", "ALL", "MAC"),
        ("LAN_AC_WHITE_V4", "lan_ac_white_ips", "IPv4", "PREFIX"),
        ("LAN_AC_WHITE_V6", "lan_ac_white_ipv6s", "IPv6", "PREFIX"),
        ("LAN_AC_WHITE_MACS", "lan_ac_white_macs", "ALL", "MAC"),
    )
    result = []
    for logical_id, physical_name, family, element_type in specs:
        raw_values = state.get(physical_name, ())
        if element_type == "MAC":
            elements = canonical_set_elements(raw_values, element_type)
        elif element_type == "PORT":
            elements = canonical_set_elements(raw_values, element_type)
        elif family in {"IPv4", "IPv6"}:
            elements = canonical_set_elements(raw_values, element_type, family)
        else:
            elements = []
        result.append(
            dict(
                _owned_metadata(
                    logical_id=logical_id,
                    physical_name=physical_name,
                    object_type="set",
                    component="ACCESS",
                    family=family,
                ),
                element_type=element_type,
                elements=elements,
                flags=["DYNAMIC", "LEGACY_COMPATIBILITY"],
                dynamic=True,
            )
        )
    return result


def build_dynamic_sets(state_raw: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Build owned dynamic sets from a normalized shadow state."""

    if state_raw is None:
        return _empty_dynamic_sets()
    state = normalize_state(state_raw)
    # The Phase 2C state schema intentionally keeps the common ACL facts in
    # action-tagged entries.  Preserve optional legacy-named fields when a
    # fixture supplies them so the inventory can still be rendered without
    # teaching production code a second parser.
    for optional_key in (
        "wan_ac_black_ips",
        "wan_ac_black_ipv6s",
        "wan_ac_black_ports",
        "lan_ac_black_ips",
        "lan_ac_black_ipv6s",
        "lan_ac_black_macs",
        "lan_ac_white_ips",
        "lan_ac_white_ipv6s",
        "lan_ac_white_macs",
    ):
        if optional_key in state_raw:
            state[optional_key] = state_raw.get(optional_key) or []
    if state["owner"] != "OPENKILL":
        return []
    result: List[Dict[str, Any]] = []
    for state_key, logical_id, physical_name, element_type, family, component in _SET_SPECS:
        values = state.get(state_key, ())
        result.append(
            dict(
                _owned_metadata(
                    logical_id=logical_id,
                    physical_name=physical_name,
                    object_type="set",
                    component=component,
                    family=family,
                ),
                element_type=element_type,
                element_semantics="HOST_SEMANTIC_128" if logical_id == "WAN_HOST_V6" else element_type,
                elements=canonical_set_elements(
                    values,
                    element_type,
                    family,
                    host_semantic=logical_id == "WAN_HOST_V6",
                ),
                flags=["DYNAMIC"],
                dynamic=True,
            )
        )
    result.extend(_access_set_entries(state, "IPv4"))
    result.extend(_access_set_entries(state, "IPv6"))
    result.extend(_legacy_acl_inventory_sets(state))
    result.extend(
        [
            dict(
                _owned_metadata(
                    logical_id="SERVICE_PORTS",
                    physical_name="openkill_service_ports",
                    object_type="set",
                    component="SERVICE",
                ),
                element_type="PORT",
                elements=canonical_set_elements(state.get("service_ports", ()), "PORT"),
                flags=["DYNAMIC"],
                dynamic=True,
            ),
            dict(
                _owned_metadata(
                    logical_id="COMMON_PORTS",
                    physical_name="common_ports",
                    object_type="set",
                    component="SERVICE",
                ),
                element_type="PORT",
                elements=[],
                flags=["DYNAMIC", "LEGACY_COMPATIBILITY"],
                dynamic=True,
            ),
        ]
    )
    return result


def _empty_dynamic_sets() -> List[Dict[str, Any]]:
    # A context-only render still exposes the stable set inventory.  This is
    # useful for golden tests and makes an empty set an explicit state rather
    # than a topology mutation.
    state = {
        "schema": "OPENKILL_SHADOW_STATE_V1",
        "contract_version": 1,
        "id": "EMPTY",
        "owner": "OPENKILL",
        "run_mode": "TUN",
        "router_self_proxy": False,
        "tun_interface": "utun",
        "dns_scope": "NONE",
        "china_policy": "OFF",
    }
    for key, *_ in _SET_SPECS:
        state[key] = []
    state.update({"access4": [], "access6": [], "service_ports": []})
    return build_dynamic_sets(state)


_REASON_TO_SET_KEYS = {
    "NODE_ENDPOINT": ("NODE_ENDPOINT",),
    "LOCAL_DESTINATION": ("LOCAL", "LAN", "WAN_HOST", "DELEGATED"),
    "FAKEIP": ("FAKEIP",),
    "EXPLICIT_DIRECT": ("USER_DIRECT",),
    "EXPLICIT_PROXY": ("USER_PROXY",),
    "CHINA_PASS": ("CHINA_PASS",),
    "CHINA_POLICY": ("CHINA",),
    "ACCESS_CONTROL": ("ACCESS",),
}


def _set_ids_for_reason(reason: str, family: str) -> List[str]:
    suffix = "V4" if family == "IPv4" else "V6"
    ids = [
        "{}_{}".format(prefix, suffix)
        for prefix in _REASON_TO_SET_KEYS.get(reason, ())
        if "{}_{}".format(prefix, suffix) in {
            spec[1] for spec in _SET_SPECS
        }
    ]
    if reason == "ACCESS_CONTROL":
        ids.extend("ACCESS_{}_{}".format(suffix, action) for action in ("ALLOW", "BYPASS", "DENY"))
    return ids


def _semantic_reason(label: str) -> str:
    if label == "ACCESS_CONTROL_CUSTOM":
        return "ACCESS_CONTROL"
    if label == "CONTROL_PROTOCOL_IPV6":
        return "CONTROL_PROTOCOL"
    if label == "CHINA_PASS_FALLTHROUGH":
        return "CHINA_PASS"
    return label


def _rule_action(label: str, family: str, run_mode: str, profile: str) -> Tuple[str, List[str]]:
    reason = _semantic_reason(label)
    if label == "CHINA_PASS_FALLTHROUGH":
        return "CONTINUE_POLICY", ["PROXY", "DIRECT"]
    if label in {"EXPLICIT_DIRECT", "EXPLICIT_PROXY"} and profile == "current":
        return "UNRESOLVED_SEMANTIC", []
    if reason == "OWNER_DISABLED":
        return "NOT_OWNED", ["NOT_OWNED"]
    if reason == "DNS":
        return "DNS_REDIRECT", ["DNS_SPECIAL"]
    if reason in {
        "CONTROL_PROTOCOL",
        "SELF_TRAFFIC",
        "TUN_INGRESS",
        "NODE_ENDPOINT",
        "LOCAL_DESTINATION",
        "REPLY_TRAFFIC",
        "SERVICE_PORT",
    }:
        return "RETURN_NATIVE", ["BYPASS"]
    if reason == "ACCESS_CONTROL":
        return "ACTION_FROM_CLASSIFICATION", ["BYPASS", "ACCESS_DENY"]
    if reason in {"FAKEIP", "EXPLICIT_PROXY", "CHINA_PASS", "DEFAULT_POLICY"}:
        if run_mode == "TUN":
            return "MARK_PROXY", ["PROXY"]
        if run_mode == "TPROXY":
            return "TPROXY_PROXY", ["PROXY"]
        return "ACTION_FROM_CLASSIFICATION", ["PROXY"]
    if reason in {"EXPLICIT_DIRECT", "CHINA_POLICY"}:
        return "RETURN_NATIVE", ["DIRECT"]
    return "UNRESOLVED_SEMANTIC", []


def build_rule_plan(profile: str = "current", run_mode: str = "TUN") -> List[Dict[str, Any]]:
    """Build static semantic rules from the classifier's precedence table."""

    selected_profile = _profile(profile)
    mode = _norm(run_mode or "TUN")
    if mode not in {"TUN", "TPROXY", "REDIRECT"}:
        raise NFTIRValidationError("unknown run mode: {!r}".format(run_mode))
    rules: List[Dict[str, Any]] = []
    for precedence_index, label in enumerate(PRECEDENCE_TABLES[selected_profile]):
        reason = _semantic_reason(label)
        families = ("IPv6",) if label in {"CONTROL_PROTOCOL", "CONTROL_PROTOCOL_IPV6"} else ("IPv4", "IPv6")
        for family in families:
            suffix = "V4" if family == "IPv4" else "V6"
            action_type, possible_decisions = _rule_action(label, family, mode, selected_profile)
            destination_sets = _set_ids_for_reason(reason, family)
            match: Dict[str, Any] = {
                "semantic_flag": reason,
                "family": family,
                "direction": ["LAN_INGRESS", "ROUTER_OUTPUT"],
            }
            if reason == "OWNER_DISABLED":
                match = {"owner": "NOT_OPENKILL", "family": family}
            elif reason == "DNS":
                match.update({"service": "DNS", "scope": ["DNS_LAN", "DNS_ROUTER"]})
            elif reason == "CONTROL_PROTOCOL":
                match.update({"protocol": ["ICMPv6", "UDP"], "control_scope": "IPv6_ONLY"})
            elif reason == "SELF_TRAFFIC":
                match.update({"source_property": "SELF_PROCESS"})
            elif reason == "TUN_INGRESS":
                match.update({"interface_role": "OPENKILL_TUN", "direction": ["TUN_INGRESS"]})
            elif reason == "REPLY_TRAFFIC":
                match.update({"connection": "REPLY"})
            elif reason == "SERVICE_PORT":
                match.update({"port_set": "SERVICE_PORTS"})
            elif destination_sets:
                match["destination_set"] = destination_sets
            rule = {
                **_owned_metadata(
                    logical_id="{}_{}_{}".format(selected_profile.upper(), label, suffix),
                    physical_name="{}_{}_{}".format(selected_profile.lower(), label.lower(), suffix.lower()),
                    object_type="rule",
                    component=(
                        "DNS"
                        if reason == "DNS"
                        else "NODE"
                        if reason == "NODE_ENDPOINT"
                        else "LOCAL"
                        if reason == "LOCAL_DESTINATION"
                        else "CHINA"
                        if reason in {"CHINA_POLICY", "CHINA_PASS"}
                        else "ACCESS"
                        if reason == "ACCESS_CONTROL"
                        else "SERVICE"
                        if reason == "SERVICE_PORT"
                        else "PROXY_ACTION"
                    ),
                    family=family,
                ),
                "chain_ref": "OPENKILL_PREROUTING_MANGLE_{}".format(suffix),
                "chain_refs": (
                    [
                        "OPENKILL_DNS_LAN_{}".format(suffix),
                        "OPENKILL_DNS_ROUTER_{}".format(suffix),
                    ]
                    if reason == "DNS"
                    else [
                        "OPENKILL_PREROUTING_MANGLE_{}".format(suffix),
                        "OPENKILL_OUTPUT_MANGLE_{}".format(suffix),
                    ]
                ),
                "precedence_source": "openkill_classifier_model.PRECEDENCE_TABLES",
                "precedence_label": label,
                "precedence_index": precedence_index,
                "match": match,
                "semantic_reason": reason,
                "possible_decisions": possible_decisions,
                "action_type": action_type,
                "action": action_type,
                "backend_mode": mode,
                "static": True,
                "dynamic_references": destination_sets,
            }
            if selected_profile == "current" and label == "TUN_INGRESS" and family == "IPv6":
                rule["known_current_gap"] = "BC-04"
                rule["current_behavior"] = "CURRENT_IPV6_TUN_GAP"
            if label in {"ACCESS_CONTROL_CUSTOM", "ACCESS_CONTROL"} and selected_profile == "current":
                rule["current_behavior"] = "CUSTOM_ACCESS_POSITION_IS_CURRENT_ORACLE"
            if label == "CHINA_PASS_FALLTHROUGH":
                rule["current_behavior"] = "FALLTHROUGH_TO_POLICY"
            rules.append(rule)
    # Current production has no resolved explicit-policy precedence.  Keep a
    # diagnostic placeholder so the IR can carry that known gap without
    # inventing a dataplane rule.
    if selected_profile == "current":
        for family, suffix in (("IPv4", "V4"), ("IPv6", "V6")):
            for reason in ("EXPLICIT_DIRECT", "EXPLICIT_PROXY"):
                rules.append(
                    {
                        **_owned_metadata(
                            logical_id="CURRENT_UNDEFINED_{}_{}".format(reason, suffix),
                            physical_name="current_undefined_{}_{}".format(reason.lower(), suffix.lower()),
                            object_type="rule",
                            component="PROXY_ACTION",
                            family=family,
                        ),
                        "chain_ref": "OPENKILL_PREROUTING_MANGLE_{}".format(suffix),
                        "chain_refs": ["OPENKILL_PREROUTING_MANGLE_{}".format(suffix)],
                        "precedence_source": "classifier current oracle: no resolved production mapping",
                        "precedence_label": "CURRENT_UNDEFINED",
                        "precedence_index": None,
                        "match": {"semantic_flag": reason, "family": family},
                        "semantic_reason": reason,
                        "possible_decisions": [],
                        "action_type": "UNRESOLVED_SEMANTIC",
                        "backend_mode": mode,
                        "static": True,
                        "dynamic_references": ["USER_{}_{}".format("DIRECT" if reason.endswith("DIRECT") else "PROXY", suffix)],
                        "known_current_gap": "BC-01",
                        "enabled": False,
                    }
                )
    return rules


def map_backend_action(
    decision: Optional[Any],
    backend_mode: str,
    protocol: str,
) -> str:
    """Map a semantic decision to an abstract NFT action.

    The classifier's backend-neutral mapper remains the source of truth for
    capability decisions; this function only renames actions for NFT_IR_V1.
    """

    if isinstance(decision, Mapping):
        decision_value = decision.get("decision")
    else:
        decision_value = decision
    raw = _classifier_backend_action(decision_value, backend_mode, protocol)
    return {
        "MARK": "MARK_PROXY",
        "MARK_TPROXY": "TPROXY_PROXY",
        "REDIRECT": "REDIRECT_PROXY",
        "NATIVE_RETURN": "RETURN_NATIVE",
        "DNS_REDIRECT": "DNS_REDIRECT",
        "ACCESS_DENY_REQUIRED": "ACCESS_DENY_REQUIRED",
        "NOT_OWNED": "NOT_OWNED",
        "UNSUPPORTED_ACTION": "UNSUPPORTED_ACTION",
    }.get(raw, "UNRESOLVED_SEMANTIC" if raw in {"UNDEFINED", "PROXY_BACKEND_SPECIFIC"} else raw)


def _semantic_action(classification: Any, context: Mapping[str, Any]) -> Dict[str, Any]:
    decision = classification.decision
    action = map_backend_action(decision, context["backend_mode"], context["protocol"])
    known_gap = classification.status == "CURRENT_UNDEFINED"
    if known_gap:
        action = "UNRESOLVED_SEMANTIC"
    if classification.status == "INVALID_CONFIGURATION":
        action = "UNRESOLVED_SEMANTIC"
    return {
        "schema": "OPENKILL_ACTION_IR_V1",
        "status": classification.status,
        "reason": classification.reason,
        "decision": decision,
        "action_type": action,
        "matched_rule": classification.matched_rule,
        "precedence_index": classification.precedence_index,
        "trace": list(classification.trace),
        "backend_mode": context["backend_mode"],
        "protocol": context["protocol"],
        "known_current_gap": known_gap,
        "action": action,
    }


def _current_backend_execution(
    context: Mapping[str, Any],
    classification: Any,
    state: Optional[Mapping[str, Any]],
    profile: str,
) -> Dict[str, Any]:
    """Describe the audited current backend execution contract.

    The classifier still owns the semantic decision.  This development-only
    table selects the production listener/action from normalized execution
    facts (mode, family, protocol, direction and router-self scope).  It is
    deliberately separate from precedence and never changes ``PROXY`` into a
    backend-specific semantic reason.
    """

    if profile != "current":
        return {"status": "PREVIEW_GENERIC", "action_type": None}
    owner = str(context.get("owner", "")).upper()
    decision = getattr(classification, "decision", None)
    reason = getattr(classification, "reason", None)
    family = str(context.get("family", "")).upper()
    suffix = "V4" if family == "IPV4" else "V6"
    direction = str(context.get("direction", "")).upper()
    protocol = str(context.get("protocol", "")).upper()
    mode = str((state or {}).get("run_mode", context.get("backend_mode", "TUN"))).upper()
    self_proxy = bool((state or {}).get("router_self_proxy", False))
    ports = (state or {}).get("proxy_ports", {}) if isinstance((state or {}).get("proxy_ports", {}), Mapping) else {}
    # A packet context without a normalized production state is the generic
    # Phase 3B development API and retains its historical placeholder
    # listeners.  Shadow/production comparisons always pass normalized state
    # and therefore use the configured fixture ports.
    default_redirect = 7892 if state is not None else 12345
    default_tproxy = 7893 if state is not None else 12345
    default_dns = DEFAULT_MIHOMO_DNS_PORT
    redirect_port = int(ports.get("redirect", default_redirect))
    tproxy_port = int(ports.get("tproxy", default_tproxy))
    dns_port = int(ports.get("dns", default_dns))
    # A context-only DNS render retains the historical mode-2 chain form.
    # State-backed mode-1 renders model the production path: firewall ->
    # dnsmasq :53 -> Mihomo :7874.  Keeping this as a distinct execution
    # field prevents the listener/upstream value from being reused as the
    # firewall redirect target.
    dns_mode = str((state or {}).get("dns_mode", "2" if state is None else "0"))
    firewall_dns_port = (
        DEFAULT_DNSMASQ_LISTEN_PORT if dns_mode == "1" else dns_port
    )

    base: Dict[str, Any] = {
        "status": "NO_ACTION",
        "reason": reason,
        "decision": decision,
        "family": "IPv4" if family == "IPV4" else "IPv6" if family == "IPV6" else family,
        "direction": direction,
        "protocol": protocol,
        "run_mode": mode,
        "router_self_proxy": self_proxy,
        "redirect_port": redirect_port,
        "tproxy_port": tproxy_port,
        "dns_port": dns_port,
        "route_required": False,
    }
    if owner != "OPENKILL" or decision in {None, "NOT_OWNED", "BYPASS", "DIRECT"}:
        return base

    # DNS has its own packet path.  The mode and scope are facts from the
    # normalized state; no routing-policy precedence is performed here.
    if reason == "DNS" or decision == "DNS_SPECIAL":
        if state is None:
            # Preserve the original Phase 3B context-only API: without a
            # production state fixture, a DNS context represents the
            # historical hijack-chain form.  State-backed shadow renders
            # below use the normalized dns_mode and configured scope.
            if direction == "LAN_INGRESS":
                return {
                    **base,
                    "status": "READY",
                    "kind": "DNS",
                    "dns_scope": "DNS_LAN",
                    "dns_mode": "2",
                    "firewall_dns_port": firewall_dns_port,
                    "parent_chain_ref": "FW4_DSTNAT",
                    "body_chain_ref": "OPENKILL_DNS_LAN_" + suffix,
                    "action_type": "DNS_REDIRECT",
                }
            if direction == "ROUTER_OUTPUT":
                return {
                    **base,
                    "status": "READY",
                    "kind": "DNS",
                    "dns_scope": "DNS_ROUTER",
                    "dns_mode": "2",
                    "firewall_dns_port": firewall_dns_port,
                    "parent_chain_ref": "OPENKILL_NAT_OUTPUT_CURRENT",
                    "action_type": "DNS_REDIRECT",
                    "router_scope_guard": "SELF_PROCESS_EXCLUDED",
                }
        if dns_mode == "0" or (direction == "ROUTER_OUTPUT" and not self_proxy):
            return {
                **base,
                "status": "NO_ACTION",
                "kind": "DNS",
                "dns_mode": dns_mode,
                "firewall_dns_port": firewall_dns_port,
            }
        if direction == "LAN_INGRESS":
            result = {
                **base,
                "status": "READY",
                "kind": "DNS",
                "dns_scope": "DNS_LAN",
                "dns_mode": dns_mode,
                "firewall_dns_port": firewall_dns_port,
            }
            if dns_mode == "1":
                result.update({"parent_chain_ref": "FW4_DSTNAT", "action_type": "DNS_REDIRECT"})
            else:
                result.update(
                    {
                        "parent_chain_ref": "FW4_DSTNAT",
                        # The audited modern production path uses one
                        # inet-table ``openkill_dns_redirect`` chain for
                        # both families; each rule carries its own family
                        # guard.  Keep the current packet path shared even
                        # though the static topology also exposes a
                        # family-specific preview object for future
                        # refactoring.
                        "body_chain_ref": "OPENKILL_DNS_ROUTER_V4",
                        "action_type": "DNS_REDIRECT",
                    }
                )
            return result
        if direction == "ROUTER_OUTPUT":
            return {
                **base,
                "status": "READY",
                "kind": "DNS",
                "dns_scope": "DNS_ROUTER",
                "dns_mode": dns_mode,
                "firewall_dns_port": firewall_dns_port,
                "parent_chain_ref": "OPENKILL_NAT_OUTPUT_CURRENT",
                "action_type": "DNS_REDIRECT",
                "router_scope_guard": "SELF_PROCESS_EXCLUDED",
            }
        return {**base, "kind": "DNS", "firewall_dns_port": firewall_dns_port}

    if decision != "PROXY":
        return base

    # TUN mode marks LAN traffic.  Router output is only marked when the
    # router-self gate is enabled, except Fake-IP's explicit synthetic
    # destination path which production creates independently.
    if mode == "TUN":
        if direction == "LAN_INGRESS":
            return {
                **base,
                "status": "READY",
                "action_type": "MARK_PROXY",
                "chain_ref": "OPENKILL_PREROUTING_MANGLE_" + suffix,
                "route_required": True,
            }
        if direction == "ROUTER_OUTPUT" and (self_proxy or reason == "FAKEIP"):
            return {
                **base,
                "status": "READY",
                "action_type": "MARK_PROXY",
                "chain_ref": "OPENKILL_OUTPUT_MANGLE_" + suffix,
                "route_required": True,
            }
        return base

    # The current TPROXY branch is intentionally hybrid: IPv4 TCP remains a
    # nat/redirect action, while IPv4 UDP and all IPv6 transports use the
    # mangle TPROXY listener.  Router output has no proxy action unless the
    # explicit self-proxy gate is enabled.
    if mode == "TPROXY":
        if direction == "LAN_INGRESS":
            if family == "IPV4" and protocol == "TCP":
                return {
                    **base,
                    "status": "READY",
                    "action_type": "REDIRECT_PROXY",
                    "chain_ref": "OPENKILL_PREROUTING_PROXY_V4",
                    "parent_chain_ref": "FW4_DSTNAT",
                    "route_required": False,
                }
            if protocol in {"TCP", "UDP"}:
                return {
                    **base,
                    "status": "READY",
                    "action_type": "TPROXY_PROXY",
                    "chain_ref": "OPENKILL_PREROUTING_MANGLE_" + suffix,
                    "route_required": True,
                }
            return {**base, "status": "UNSUPPORTED", "action_type": "UNSUPPORTED_ACTION"}
        if direction == "ROUTER_OUTPUT" and self_proxy:
            if family == "IPV4" and protocol == "TCP":
                return {
                    **base,
                    "status": "READY",
                    "action_type": "REDIRECT_PROXY",
                    "chain_ref": "OPENKILL_OUTPUT_PROXY_V4",
                    "parent_chain_ref": "OPENKILL_NAT_OUTPUT_CURRENT",
                    "route_required": False,
                }
            if protocol in {"TCP", "UDP"}:
                return {
                    **base,
                    "status": "READY",
                    "action_type": "MARK_PROXY",
                    "chain_ref": "OPENKILL_OUTPUT_MANGLE_" + suffix,
                    "route_required": True,
                }
        return base

    # Redirect mode is only safe for TCP.  The current comparison corpus
    # keeps unresolved redirect policy cases explicit; UDP is never silently
    # converted to another action.
    if mode == "REDIRECT":
        if protocol == "TCP" and direction == "LAN_INGRESS":
            return {
                **base,
                "status": "READY",
                "action_type": "REDIRECT_PROXY",
                "chain_ref": "OPENKILL_PREROUTING_PROXY_" + suffix,
            }
        if protocol == "UDP":
            return {**base, "status": "UNSUPPORTED", "action_type": "UNSUPPORTED_ACTION"}
    return base


def _base_metadata(profile: str, backend: str, *, target_preview: bool, state_id: Optional[str] = None) -> Dict[str, Any]:
    metadata = {
        "semantic_spec_version": SEMANTIC_SPEC_VERSION,
        "classifier_contract_version": CLASSIFIER_CONTRACT_VERSION,
        "renderer_profile": profile,
        "renderer_backend": backend,
        "ir_version": NFT_IR_VERSION,
        "ownership_manifest_version": OWNERSHIP_MANIFEST_VERSION,
        "behavior_change_lock": "TARGET_PREVIEW_ONLY" if profile == "target" else "CURRENT_ONLY",
        "production_profile_default": DEFAULT_RENDERER_PROFILE,
        "preview_only": bool(target_preview),
        "mark_abi": dict(MARK_ABI),
    }
    if state_id is not None:
        metadata["state_id"] = state_id
    return metadata


def ownership_manifest(ir: Mapping[str, Any]) -> Dict[str, Any]:
    """Build a cleanup-scoped manifest from explicitly owned IR objects."""

    entries: List[Dict[str, Any]] = []
    for obj in _all_objects(ir):
        if obj.get("owner") != "OPENKILL" or obj.get("ownership") != "OWNED":
            continue
        entries.append(
            {
                "logical_id": obj["logical_id"],
                "physical_name": obj["physical_name"],
                "object_type": obj["object_type"],
                "component": obj["component"],
                "parent_table": obj.get("parent_table", "inet fw4"),
                "parent_owner": obj.get("parent_owner", "FW4"),
                "owner": "OPENKILL",
                "ownership": "OWNED",
                "semantic_spec_version": SEMANTIC_SPEC_VERSION,
            }
        )
    entries.sort(key=lambda item: item["logical_id"])
    return {
        "schema": OWNERSHIP_MANIFEST_SCHEMA,
        "version": OWNERSHIP_MANIFEST_VERSION,
        "owner": "OPENKILL",
        "semantic_spec_version": SEMANTIC_SPEC_VERSION,
        "entries": entries,
    }


def _build_dependencies() -> Dict[str, List[str]]:
    return {
        "TOPOLOGY": ["NODE", "LOCAL", "CHINA", "ACCESS", "SERVICE", "DNS", "PROXY_ACTION"],
        "NODE": ["PROXY_ACTION"],
        "LOCAL": ["PROXY_ACTION"],
        "CHINA": ["PROXY_ACTION"],
        "ACCESS": ["PROXY_ACTION"],
        "SERVICE": ["PROXY_ACTION"],
        # DNS is a self-contained component.  A literal DNS -> DNS edge
        # made graph consumers observe a cycle, although it represented no
        # dependency on another component.
        "DNS": [],
        "PROXY_ACTION": [],
        "OWNER": ["TOPOLOGY"],
    }


def _ir(
    profile: str,
    backend: str,
    *,
    owner: str,
    run_mode: str,
    state_id: Optional[str] = None,
    state: Optional[Mapping[str, Any]] = None,
    context: Optional[Mapping[str, Any]] = None,
    classification: Optional[Any] = None,
    target_preview: bool = False,
) -> Dict[str, Any]:
    topology = build_static_topology(owner=owner, run_mode=run_mode)
    dynamic_sets = build_dynamic_sets(state)
    rules = build_rule_plan(profile=profile, run_mode=run_mode) if _norm(owner) == "OPENKILL" else []
    action_items: List[Dict[str, Any]] = []
    semantic_action_plan = [
        {
            "logical_id": rule["logical_id"],
            "component": rule["component"],
            "semantic_reason": rule["semantic_reason"],
            "possible_decisions": list(rule.get("possible_decisions", ())),
            "action_type": rule["action_type"],
            "precedence_label": rule["precedence_label"],
            "precedence_index": rule.get("precedence_index"),
            "profile": profile,
        }
        for rule in rules
    ]
    context_record = None
    classification_record = None
    context_execution: Optional[Dict[str, Any]] = None
    if context is not None and classification is not None:
        # Only serialize the contract fields.  Fixture annotations (for
        # example a human note containing the word "position") are not part
        # of packet semantics and must not be mistaken for backend syntax.
        context_record = {
            key: context[key]
            for key in (
                "family",
                "direction",
                "protocol",
                "backend_mode",
                "source_properties",
                "destination_properties",
                "service",
                "connection",
                "owner",
                "china_policy",
                "icmpv6_type",
                "flags",
            )
            if key in context
        }
        context_record["flags"] = sorted(context_record.get("flags", ()))
        classification_record = classification.to_record(include_trace=True)
        action_items.append(_semantic_action(classification, context))
        context_execution = _current_backend_execution(context, classification, state, profile)
    ir: Dict[str, Any] = {
        "schema": NFT_IR_SCHEMA,
        "ir_version": NFT_IR_VERSION,
        "metadata": _base_metadata(profile, backend, target_preview=target_preview, state_id=state_id),
        "static_topology": topology,
        "dynamic_state": {
            "sets": dynamic_sets,
            "set_count": len(dynamic_sets),
            "state_normalized": state is not None,
        },
        "rules": rules,
        "semantic_action_ir": semantic_action_plan,
        "action_ir": action_items,
        "context": context_record,
        "classification": classification_record,
        "context_execution": context_execution,
        "dependencies": _build_dependencies(),
        "runtime_audit": {
            "actual_state_schema": "OPENKILL_ACTUAL_NFT_STATE_V1",
            "desired_state": "NFT_IR_V1",
            "mode": "FIXTURE_ONLY",
            "repair": "OWNERSHIP_SCOPED_INCREMENTAL",
            "foreign_preservation": True,
        },
        "cleanup_contract": {
            "scope": "OWNERSHIP_MANIFEST_ONLY",
            "flush_ruleset": False,
            "flush_parent_table": False,
            "foreign_objects": "PRESERVE",
        },
        "known_current_gaps": [
            {"id": "BC-01", "status": "CURRENT_UNDEFINED", "reason": "EXPLICIT_USER_POLICY"},
            {"id": "BC-04", "status": "KNOWN_CURRENT_GAP", "reason": "IPV6_TUN_INGRESS"},
            {"id": "BC-06", "status": "CURRENT_FALLTHROUGH", "reason": "CHINA_PASS"},
            {"id": "BC-07", "status": "BACKEND_DEPENDENT", "reason": "ACCESS_DENY"},
        ],
    }
    ir["ownership_manifest"] = ownership_manifest(ir)
    return ir


def render_context(
    context_raw: Mapping[str, Any],
    profile: str = DEFAULT_RENDERER_PROFILE,
    backend: str = "ABSTRACT_NFT",
    *,
    target_preview: bool = False,
    state: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Render one validated packet context into abstract NFT intent."""

    selected_profile = _profile(profile)
    selected_backend = _backend(backend)
    if selected_profile == "target" and not target_preview:
        raise NFTIRValidationError("target renderer requires target_preview=True")
    context = validate_context(context_raw)
    normalized_state = normalize_state(state) if state is not None else None
    owner = normalized_state["owner"] if normalized_state is not None else context["owner"]
    run_mode = normalized_state["run_mode"] if normalized_state is not None else context["backend_mode"]
    if normalized_state is not None:
        if context["owner"] != normalized_state["owner"]:
            raise NFTIRValidationError("context/state owner mismatch")
        if context["backend_mode"] != normalized_state["run_mode"]:
            raise NFTIRValidationError("context/state backend mode mismatch")
    result = classify(context, profile=selected_profile, trace=True)
    return _ir(
        selected_profile,
        selected_backend,
        owner=owner,
        run_mode=run_mode,
        state_id=normalized_state.get("id") if normalized_state else None,
        state=normalized_state,
        context=context,
        classification=result,
        target_preview=target_preview,
    )


def render_state(
    state_raw: Mapping[str, Any],
    profile: str = DEFAULT_RENDERER_PROFILE,
    backend: str = "ABSTRACT_NFT",
    *,
    target_preview: bool = False,
) -> Dict[str, Any]:
    """Render a normalized production-state fixture without packet syntax."""

    selected_profile = _profile(profile)
    selected_backend = _backend(backend)
    if selected_profile == "target" and not target_preview:
        raise NFTIRValidationError("target renderer requires target_preview=True")
    state = normalize_state(state_raw)
    return _ir(
        selected_profile,
        selected_backend,
        owner=state["owner"],
        run_mode=state["run_mode"],
        state_id=state["id"],
        state=state,
        target_preview=target_preview,
    )


def render(
    context_raw: Mapping[str, Any],
    profile: str = DEFAULT_RENDERER_PROFILE,
    backend: str = "ABSTRACT_NFT",
    *,
    target_preview: bool = False,
    state: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Short API alias for the packet-context renderer."""

    return render_context(
        context_raw,
        profile=profile,
        backend=backend,
        target_preview=target_preview,
        state=state,
    )


def _all_objects(ir: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    topology = ir.get("static_topology", {})
    objects = list(topology.get("objects", ())) if isinstance(topology, Mapping) else []
    dynamic = ir.get("dynamic_state", {})
    if isinstance(dynamic, Mapping):
        objects.extend(dynamic.get("sets", ()))
    objects.extend(ir.get("rules", ()))
    objects.extend(ir.get("foreign_objects", ()))
    return objects


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


def validate_ir(ir: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate schema, ownership, references, and backend-neutrality."""

    if not isinstance(ir, Mapping) or ir.get("schema") != NFT_IR_SCHEMA:
        raise NFTIRValidationError("unsupported NFT IR schema")
    if ir.get("ir_version") != NFT_IR_VERSION:
        raise NFTIRValidationError("NFT IR version mismatch")
    metadata = ir.get("metadata")
    if not isinstance(metadata, Mapping):
        raise NFTIRValidationError("IR metadata missing")
    required_metadata = {
        "semantic_spec_version",
        "classifier_contract_version",
        "renderer_profile",
        "renderer_backend",
        "ir_version",
        "ownership_manifest_version",
        "behavior_change_lock",
        "production_profile_default",
        "preview_only",
    }
    if not required_metadata.issubset(metadata):
        raise NFTIRValidationError("IR metadata fields missing")
    if metadata["semantic_spec_version"] != SEMANTIC_SPEC_VERSION:
        raise NFTIRValidationError("semantic specification version mismatch")
    if metadata["classifier_contract_version"] != CLASSIFIER_CONTRACT_VERSION:
        raise NFTIRValidationError("classifier contract version mismatch")
    if metadata["ir_version"] != NFT_IR_VERSION or metadata["ownership_manifest_version"] != OWNERSHIP_MANIFEST_VERSION:
        raise NFTIRValidationError("IR metadata version mismatch")
    profile = _profile(metadata["renderer_profile"])
    _backend(metadata["renderer_backend"])
    if metadata["production_profile_default"] != DEFAULT_RENDERER_PROFILE:
        raise NFTIRValidationError("renderer production default must be current")
    if profile == "current" and metadata["behavior_change_lock"] != "CURRENT_ONLY":
        raise NFTIRValidationError("current renderer must carry CURRENT_ONLY lock")
    if profile == "target" and (metadata["behavior_change_lock"] != "TARGET_PREVIEW_ONLY" or metadata.get("preview_only") is not True):
        raise NFTIRValidationError("target renderer must be preview-only")

    topology = ir.get("static_topology")
    if not isinstance(topology, Mapping) or not isinstance(topology.get("objects"), list):
        raise NFTIRValidationError("static topology is missing")
    dynamic = ir.get("dynamic_state")
    if not isinstance(dynamic, Mapping) or not isinstance(dynamic.get("sets"), list):
        raise NFTIRValidationError("dynamic state is missing")
    if not isinstance(ir.get("rules"), list) or not isinstance(ir.get("action_ir"), list) or not isinstance(ir.get("semantic_action_ir"), list):
        raise NFTIRValidationError("rules/action IR must be lists")
    if not isinstance(ir.get("dependencies"), Mapping):
        raise NFTIRValidationError("component dependency graph missing")
    runtime_audit = ir.get("runtime_audit")
    if not isinstance(runtime_audit, Mapping) or runtime_audit.get("mode") != "FIXTURE_ONLY" or runtime_audit.get("desired_state") != "NFT_IR_V1":
        raise NFTIRValidationError("runtime audit must remain fixture-only")
    cleanup = ir.get("cleanup_contract")
    if not isinstance(cleanup, Mapping) or cleanup.get("scope") != "OWNERSHIP_MANIFEST_ONLY" or cleanup.get("flush_ruleset") or cleanup.get("flush_parent_table"):
        raise NFTIRValidationError("cleanup contract is unsafe")

    ids: Set[str] = set()
    known_chain_ids: Set[str] = set()
    known_set_ids: Set[str] = set()
    for obj in _all_objects(ir):
        if not isinstance(obj, Mapping):
            raise NFTIRValidationError("IR object must be an object")
        object_type = obj.get("object_type")
        if object_type not in OBJECT_TYPES:
            raise NFTIRValidationError("unknown IR object type: {!r}".format(object_type))
        logical_id = obj.get("logical_id")
        if not isinstance(logical_id, str) or not logical_id:
            raise NFTIRValidationError("object logical_id missing")
        if logical_id in ids:
            raise NFTIRValidationError("duplicate logical id: {}".format(logical_id))
        ids.add(logical_id)
        if not isinstance(obj.get("physical_name"), str) or not obj["physical_name"]:
            raise NFTIRValidationError("physical_name missing for {}".format(logical_id))
        if obj.get("component") not in COMPONENTS:
            raise NFTIRValidationError("unknown component for {}".format(logical_id))
        if obj.get("family") not in {"ALL", "IPv4", "IPv6"}:
            raise NFTIRValidationError("unknown family for {}".format(logical_id))
        if obj.get("owner") == "OPENKILL":
            if obj.get("ownership") != "OWNED" or obj.get("semantic_spec_version") != SEMANTIC_SPEC_VERSION:
                raise NFTIRValidationError("owned object metadata incomplete: {}".format(logical_id))
        elif obj.get("ownership") not in {"EXTERNAL", "FOREIGN"}:
            raise NFTIRValidationError("unscoped foreign object: {}".format(logical_id))
        if object_type in {"chain", "chain_ref", "table_ref"}:
            known_chain_ids.add(logical_id)
        if object_type == "set":
            known_set_ids.add(logical_id)
            if obj.get("element_type") not in {"ADDRESS", "PREFIX", "PORT", "MAC", "INTERVAL", "TOKEN"}:
                raise NFTIRValidationError("unknown set element type: {}".format(logical_id))
            if not isinstance(obj.get("elements"), list):
                raise NFTIRValidationError("set elements must be a list: {}".format(logical_id))

    for rule in ir.get("rules", ()):
        if rule.get("object_type") != "rule":
            raise NFTIRValidationError("rule object type mismatch")
        if rule.get("action_type") not in ACTION_TYPES:
            raise NFTIRValidationError("unknown action type: {}".format(rule.get("action_type")))
        if rule.get("chain_ref") not in known_chain_ids:
            raise NFTIRValidationError("unresolved chain reference: {}".format(rule.get("logical_id")))
        chain_refs = rule.get("chain_refs", [rule.get("chain_ref")])
        if not isinstance(chain_refs, list):
            raise NFTIRValidationError("chain_refs must be a list: {}".format(rule.get("logical_id")))
        for chain_ref in chain_refs:
            if chain_ref not in known_chain_ids:
                raise NFTIRValidationError("unresolved chain reference: {}".format(rule.get("logical_id")))
        if not isinstance(rule.get("match"), Mapping):
            raise NFTIRValidationError("rule match missing: {}".format(rule.get("logical_id")))
        for key in rule["match"]:
            if key not in set(MATCH_TYPES) | {"source_property", "scope", "control_scope", "semantic_flag"}:
                raise NFTIRValidationError("unknown semantic match primitive: {}".format(key))
        for set_id in rule.get("dynamic_references", ()):
            if set_id not in known_set_ids and set_id not in {"ACCESS_V4", "ACCESS_V6"}:
                # Empty/undefined current placeholders are still valid only
                # when they explicitly identify their unresolved semantic.
                if rule.get("action_type") != "UNRESOLVED_SEMANTIC":
                    raise NFTIRValidationError("unresolved set reference: {}".format(set_id))

    for action in ir.get("action_ir", ()):
        if not isinstance(action, Mapping):
            raise NFTIRValidationError("action IR entry must be an object")
        if action.get("action_type") not in ACTION_TYPES:
            raise NFTIRValidationError("unknown action IR type: {!r}".format(action.get("action_type")))
        if action.get("status") not in {"VALID", "CURRENT_UNDEFINED", "INVALID_CONFIGURATION"}:
            raise NFTIRValidationError("unknown action IR status")
        if action.get("reason") is not None and action.get("reason") not in set(MATCH_REASONS):
            raise NFTIRValidationError("unknown action IR reason")
        if action.get("decision") is not None and action.get("decision") not in set(DECISIONS):
            raise NFTIRValidationError("unknown action IR decision")

    for plan in ir.get("semantic_action_ir", ()):
        if not isinstance(plan, Mapping) or not isinstance(plan.get("logical_id"), str):
            raise NFTIRValidationError("semantic action plan entry is incomplete")
        if plan.get("component") not in COMPONENTS:
            raise NFTIRValidationError("semantic action plan component is unknown")
        if plan.get("semantic_reason") not in set(MATCH_REASONS) | {"CURRENT_UNDEFINED"}:
            raise NFTIRValidationError("semantic action plan reason is unknown")
        if plan.get("action_type") not in ACTION_TYPES:
            raise NFTIRValidationError("semantic action plan action is unknown")

    manifest = ir.get("ownership_manifest")
    if not isinstance(manifest, Mapping) or manifest.get("schema") != OWNERSHIP_MANIFEST_SCHEMA:
        raise NFTIRValidationError("ownership manifest missing")
    if manifest.get("version") != OWNERSHIP_MANIFEST_VERSION or manifest.get("owner") != "OPENKILL":
        raise NFTIRValidationError("ownership manifest version/owner mismatch")
    manifest_ids = [entry.get("logical_id") for entry in manifest.get("entries", ())]
    if len(manifest_ids) != len(set(manifest_ids)):
        raise NFTIRValidationError("duplicate manifest logical id")
    expected_manifest_ids = sorted(
        obj["logical_id"] for obj in _all_objects(ir) if obj.get("owner") == "OPENKILL" and obj.get("ownership") == "OWNED"
    )
    if sorted(manifest_ids) != expected_manifest_ids:
        raise NFTIRValidationError("ownership manifest does not match owned objects")

    for foreign in ir.get("foreign_objects", ()):
        if foreign.get("owner") == "OPENKILL" or foreign.get("ownership") == "OWNED":
            raise NFTIRValidationError("foreign object claims OpenKill ownership")

    forbidden = (
        "flush ruleset",
        "flush table",
        "insert rule",
        "nft add",
        "iptables -",
        "ip6tables -",
        "ip -6 route add",
        "rule handle",
        "position ",
    )
    for text in _walk_strings(ir):
        lowered = text.lower()
        if any(pattern in lowered for pattern in forbidden):
            raise NFTIRValidationError("backend command syntax leaked into IR")
    return dict(ir)


def validate_ir_fixture(fixture: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate the machine-readable Phase 3A IR design fixture."""

    if not isinstance(fixture, Mapping) or fixture.get("schema") != "OPENKILL_NFT_IR_FIXTURE_V1":
        raise NFTIRValidationError("unsupported NFT IR fixture schema")
    for key, expected in (
        ("ir_version", NFT_IR_VERSION),
        ("semantic_spec_version", SEMANTIC_SPEC_VERSION),
        ("classifier_contract_version", CLASSIFIER_CONTRACT_VERSION),
        ("ownership_manifest_version", OWNERSHIP_MANIFEST_VERSION),
    ):
        if fixture.get(key) != expected:
            raise NFTIRValidationError("IR fixture {} mismatch".format(key))
    if fixture.get("default_renderer_profile") != DEFAULT_RENDERER_PROFILE:
        raise NFTIRValidationError("IR fixture must default to current")
    if tuple(fixture.get("supported_profiles", ())) != RENDERER_PROFILES:
        raise NFTIRValidationError("IR fixture profile enum mismatch")
    if fixture.get("supported_backend") not in RENDERER_BACKENDS:
        raise NFTIRValidationError("IR fixture backend mismatch")
    if fixture.get("production_wiring") != "NONE":
        raise NFTIRValidationError("IR fixture must remain development-only")
    if tuple(fixture.get("object_types", ())) != OBJECT_TYPES:
        raise NFTIRValidationError("IR fixture object types mismatch")
    if tuple(fixture.get("chain_roles", ())) != CHAIN_ROLES:
        raise NFTIRValidationError("IR fixture chain roles mismatch")
    if tuple(fixture.get("match_types", ())) != MATCH_TYPES:
        raise NFTIRValidationError("IR fixture match types mismatch")
    if tuple(fixture.get("action_types", ())) != ACTION_TYPES:
        raise NFTIRValidationError("IR fixture action types mismatch")
    if tuple(fixture.get("components", ())) != COMPONENTS:
        raise NFTIRValidationError("IR fixture components mismatch")
    if tuple(fixture.get("element_types", ())) != ("ADDRESS", "PREFIX", "PORT", "MAC", "INTERVAL", "TOKEN"):
        raise NFTIRValidationError("IR fixture element types mismatch")
    inventory = fixture.get("set_inventory")
    if not isinstance(inventory, list) or not inventory:
        raise NFTIRValidationError("IR fixture set inventory missing")
    seen_inventory: Set[str] = set()
    for entry in inventory:
        if not isinstance(entry, Mapping) or not entry.get("semantic_id"):
            raise NFTIRValidationError("IR fixture set inventory entry incomplete")
        if entry["semantic_id"] in seen_inventory:
            raise NFTIRValidationError("duplicate IR fixture set inventory id")
        seen_inventory.add(entry["semantic_id"])
        if entry.get("element_type") not in {"ADDRESS", "PREFIX", "PORT", "MAC", "INTERVAL", "TOKEN"}:
            raise NFTIRValidationError("unknown IR fixture set element type")
    if tuple(fixture.get("diff_categories", ())) != DIFF_CATEGORIES:
        raise NFTIRValidationError("IR fixture diff categories mismatch")
    ownership = fixture.get("ownership_model")
    if not isinstance(ownership, Mapping) or ownership.get("parent_owner") != "FW4" or ownership.get("child_owner") != "OPENKILL":
        raise NFTIRValidationError("IR fixture ownership model incomplete")
    audit = fixture.get("runtime_audit_model")
    if not isinstance(audit, Mapping) or audit.get("mode") != "FIXTURE_ONLY" or audit.get("desired_state") != "NFT_IR_V1":
        raise NFTIRValidationError("IR fixture runtime audit must be fixture-only")
    cleanup = fixture.get("cleanup_contract")
    if not isinstance(cleanup, Mapping) or cleanup.get("scope") != "OWNERSHIP_MANIFEST_ONLY" or cleanup.get("flush_ruleset") or cleanup.get("flush_parent_table"):
        raise NFTIRValidationError("IR fixture cleanup contract is unsafe")
    lock = fixture.get("behavior_change_lock")
    if not isinstance(lock, Mapping) or tuple(lock.get("ids", ())) != tuple("BC-0{}".format(i) for i in range(1, 8)):
        raise NFTIRValidationError("IR behavior-change lock incomplete")
    if lock.get("status") != "PRODUCTION_NOT_APPROVED":
        raise NFTIRValidationError("IR behavior-change lock must remain unapproved")
    golden = fixture.get("golden_compatibility")
    expected_golden = {
        "phase_2a_current_cases": 97,
        "phase_2a_target_cases": 97,
        "phase_2a_overlap_cases": 32,
        "phase_2a_parity_groups": 31,
        "phase_2c_shadow_cases": 109,
    }
    if not isinstance(golden, Mapping) or any(golden.get(key) != value for key, value in expected_golden.items()):
        raise NFTIRValidationError("IR golden compatibility counts drift")
    for example in fixture.get("examples", ()):
        if not isinstance(example, Mapping) or not example.get("id"):
            raise NFTIRValidationError("IR example is incomplete")
        if example.get("profile", "current") not in RENDERER_PROFILES:
            raise NFTIRValidationError("IR example profile is unknown")
    return dict(fixture)


def _canonical_for_serialization(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical_for_serialization(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (set, frozenset, tuple)):
        return [_canonical_for_serialization(item) for item in sorted(value, key=lambda item: str(item))]
    if isinstance(value, list):
        return [_canonical_for_serialization(item) for item in value]
    return value


def serialize_ir(ir: Mapping[str, Any]) -> str:
    """Return byte-stable JSON for review and golden diffs."""

    validate_ir(ir)
    return json.dumps(_canonical_for_serialization(ir), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _object_map(ir: Mapping[str, Any], section: str) -> Dict[str, Mapping[str, Any]]:
    if section == "topology":
        objects = ir["static_topology"]["objects"]
    elif section == "sets":
        objects = ir["dynamic_state"]["sets"]
    else:
        objects = ir.get("rules", ())
    return {obj["logical_id"]: obj for obj in objects}


def diff_ir(old: Mapping[str, Any], new: Mapping[str, Any]) -> Dict[str, Any]:
    """Compare IR semantically, ignoring state IDs and manifest regeneration."""

    validate_ir(old)
    validate_ir(new)
    changes: List[Dict[str, Any]] = []
    categories: Set[str] = set()
    components: Set[str] = set()

    for section, category in (("topology", "TOPOLOGY_CHANGE"), ("sets", "SET_ELEMENT_CHANGE"), ("rules", "RULE_CHANGE")):
        before = _object_map(old, section)
        after = _object_map(new, section)
        for logical_id in sorted(set(before) | set(after)):
            left = before.get(logical_id)
            right = after.get(logical_id)
            if left == right:
                continue
            if section == "topology":
                detail_category = "TOPOLOGY_ADD" if left is None else "TOPOLOGY_REMOVE" if right is None else category
                if detail_category != category:
                    categories.add(category)
            else:
                detail_category = category
            component = (right or left).get("component", "TOPOLOGY")
            categories.add(detail_category)
            # The object-level category says what changed; the component
            # category makes the intended future incremental apply boundary
            # explicit (NODE, LOCAL, CHINA, ...).
            categories.add("COMPONENT_CHANGE")
            components.add(component)
            changes.append(
                {
                    "category": detail_category,
                    "logical_id": logical_id,
                    "component": component,
                    "before": left,
                    "after": right,
                }
            )
    if old.get("metadata", {}).get("renderer_profile") != new.get("metadata", {}).get("renderer_profile"):
        categories.add("COMPONENT_CHANGE")
        components.add("PROXY_ACTION")
        changes.append({"category": "COMPONENT_CHANGE", "logical_id": "RENDERER_PROFILE", "component": "PROXY_ACTION"})
    old_owner = old.get("static_topology", {}).get("owner_state")
    new_owner = new.get("static_topology", {}).get("owner_state")
    if old_owner != new_owner:
        categories.add("COMPONENT_CHANGE")
        components.add("OWNER")
        changes.append(
            {
                "category": "COMPONENT_CHANGE",
                "logical_id": "OWNER_STATE",
                "component": "OWNER",
                "before": old_owner,
                "after": new_owner,
            }
        )
    if old.get("action_ir") != new.get("action_ir"):
        categories.add("COMPONENT_CHANGE")
        components.add("PROXY_ACTION")
        changes.append({"category": "COMPONENT_CHANGE", "logical_id": "ACTION_IR", "component": "PROXY_ACTION"})
    changes.sort(key=lambda item: (item["category"], item["logical_id"]))
    if not changes:
        categories = {"NO_CHANGE"}
    return {
        "categories": sorted(categories),
        "changed_components": sorted(components),
        "changes": changes,
        "no_change": not changes,
    }


def render_plan_text(ir: Mapping[str, Any]) -> str:
    """Human-readable diagnostic view; the JSON IR remains canonical."""

    validate_ir(ir)
    lines = [
        "NFT_IR_V1 profile={} backend={}".format(ir["metadata"]["renderer_profile"], ir["metadata"]["renderer_backend"]),
        "Static topology objects: {}".format(len(ir["static_topology"]["objects"])),
        "Dynamic sets: {}".format(len(ir["dynamic_state"]["sets"])),
        "Rules: {}".format(len(ir["rules"])),
    ]
    for item in ir["dynamic_state"]["sets"]:
        lines.append("SET {} ({}) elements={}".format(item["logical_id"], item["component"], len(item["elements"])))
    for rule in ir["rules"]:
        lines.append("RULE {} reason={} action={}".format(rule["logical_id"], rule["semantic_reason"], rule["action_type"]))
    return "\n".join(lines)


__all__ = [
    "SEMANTIC_SPEC_VERSION",
    "NFT_IR_VERSION",
    "NFT_IR_SCHEMA",
    "OWNERSHIP_MANIFEST_VERSION",
    "OWNERSHIP_MANIFEST_SCHEMA",
    "OPENKILL_NFT_MANIFEST_V1",
    "NFT_IR_SCHEMA_VERSION",
    "DEFAULT_RENDERER_PROFILE",
    "RENDERER_PROFILES",
    "RENDERER_BACKENDS",
    "COMPONENTS",
    "CHAIN_ROLES",
    "OBJECT_TYPES",
    "MATCH_TYPES",
    "ACTION_TYPES",
    "DIFF_CATEGORIES",
    "MARK_ABI",
    "DEFAULT_MIHOMO_DNS_PORT",
    "DEFAULT_DNSMASQ_LISTEN_PORT",
    "NFTIRValidationError",
    "canonical_set_elements",
    "build_static_topology",
    "build_dynamic_sets",
    "build_rule_plan",
    "map_backend_action",
    "_current_backend_execution",
    "backend_action",
    "render_context",
    "render",
    "render_state",
    "validate_ir",
    "validate_ir_fixture",
    "serialize_ir",
    "diff_ir",
    "ownership_manifest",
    "render_plan_text",
]


# Keep a backend-neutral name familiar to the Phase 2B model while returning
# the NFT_IR action vocabulary.
backend_action = map_backend_action
