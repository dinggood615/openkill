#!/usr/bin/env python3
"""Validate the Phase 2D production-neutral dataplane specification.

This is a development-only contract test.  It loads the versioned semantic
specification and the already approved Phase 2A/2B/2C fixtures, then checks
that the specification has not drifted from the executable classifier or the
independent shadow intent.  It never imports or executes OpenWrt production
runtime code and never talks to a device.
"""

from __future__ import annotations

import copy
import json
import pathlib
import re
import unittest

from openkill_classifier_model import (
    CLASSIFIER_CONTRACT_VERSION,
    CURRENT_PRECEDENCE,
    DECISIONS,
    MATCH_REASONS,
    PROFILE_VALUES,
    STATUS_VALUES,
    TARGET_PRECEDENCE,
    classify,
    validate_fixture,
)
from openkill_shadow_adapter import (
    SHADOW_CONTRACT_VERSION,
    SHADOW_RESULTS,
    shadow_compare,
    validate_intent_fixture,
    validate_state_fixture,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC_FILE = ROOT / "scripts/fixtures/openkill-dataplane-semantic-spec-v1.json"
CLASSIFIER_FIXTURE = ROOT / "scripts/fixtures/openkill-classifier-semantic-v1.json"
STATE_FIXTURE = ROOT / "scripts/fixtures/openkill-shadow-states-v1.json"
INTENT_FIXTURE = ROOT / "scripts/fixtures/openkill-current-firewall-intent-v1.json"

CORE_FACTS = {
    "OWNER",
    "DNS",
    "SELF",
    "TUN",
    "NODE",
    "LOCAL",
    "REPLY",
    "SERVICE",
    "ACCESS",
    "FAKEIP",
    "CHINA_PASS",
    "CHINA",
    "DEFAULT",
    "EXPLICIT_DIRECT",
    "EXPLICIT_PROXY",
}

BC_IDS = {"BC-01", "BC-02", "BC-03", "BC-04", "BC-05", "BC-06", "BC-07"}
BC_FIELDS = {
    "id",
    "current_behavior",
    "target_behavior",
    "motivation",
    "safety_impact",
    "compatibility_impact",
    "legacy_impact",
    "modern_impact",
    "packet_path_impact",
    "rollback_risk",
    "type",
    "production_approval_status",
    "recommended_decision",
    "recommendation_reason",
}

CURRENT_LABELS = tuple(CURRENT_PRECEDENCE)
TARGET_LABELS = tuple(TARGET_PRECEDENCE)
LABEL_TO_REASON = {
    "ACCESS_CONTROL_CUSTOM": "ACCESS_CONTROL",
    "CONTROL_PROTOCOL_IPV6": "CONTROL_PROTOCOL",
    "CHINA_PASS_FALLTHROUGH": "CHINA_PASS",
}

# These patterns detect backend *commands*, not ordinary references to a
# backend as a concept.  A semantic spec may name a backend, but it must not
# prescribe syntax, handles, or insertion commands.
FORBIDDEN_BACKEND_SYNTAX = (
    re.compile(r"\b(?:nft|iptables|ip6tables)\s+(?:add|insert|replace|delete|flush|list)\b", re.I),
    re.compile(r"\bip\s+-6\s+route\s+add\b", re.I),
    re.compile(r"\brule\s+handle\b", re.I),
    re.compile(r"\bchain\s+insertion\s+syntax\b", re.I),
)


class SpecValidationError(ValueError):
    """Raised when the Phase 2D specification is malformed or drifts."""


def load_json(path: pathlib.Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _require_mapping(value, label):
    if not isinstance(value, dict):
        raise SpecValidationError("{} must be an object".format(label))


def _require_nonempty_list(value, label):
    if not isinstance(value, list) or not value:
        raise SpecValidationError("{} must be a non-empty list".format(label))


def _semantic_reason(label):
    return LABEL_TO_REASON.get(label, label)


def validate_spec(spec):
    """Validate structure, versions, invariants, and model drift."""

    _require_mapping(spec, "spec")
    if spec.get("schema") != "OPENKILL_DATAPLANE_SEMANTIC_SPEC_V1":
        raise SpecValidationError("unknown semantic specification schema")
    for field in (
        "dataplane_semantic_spec_version",
        "classifier_contract_version",
        "shadow_state_schema_version",
        "current_intent_version",
    ):
        if spec.get(field) != 1:
            raise SpecValidationError("{} must be version 1".format(field))
    if spec.get("default_production_profile") != "current":
        raise SpecValidationError("production profile must default to current")
    if spec.get("production_wiring") != "NONE":
        raise SpecValidationError("production wiring must remain NONE")

    if tuple(spec.get("decision_enum", ())) != DECISIONS:
        raise SpecValidationError("decision enum drift")
    if tuple(spec.get("match_reason_enum", ())) != MATCH_REASONS:
        raise SpecValidationError("match reason enum drift")
    if tuple(spec.get("status_enum", ())) != STATUS_VALUES:
        raise SpecValidationError("status enum drift")

    layers = spec.get("semantic_layers")
    _require_mapping(layers, "semantic_layers")
    for layer in ("OWNERSHIP_SCOPE", "SAFETY_ACCESS", "ROUTING_POLICY", "BACKEND_ACTION"):
        _require_mapping(layers.get(layer), "semantic_layers." + layer)
    ownership_values = {item.get("owner") for item in layers["OWNERSHIP_SCOPE"].get("values", ())}
    if ownership_values != {"OPENKILL", "MIHOMO", "DISABLED", "UNKNOWN"}:
        raise SpecValidationError("ownership values incomplete")
    if layers["OWNERSHIP_SCOPE"].get("invariant") != "SINGLE_DATAPLANE_OWNER":
        raise SpecValidationError("single-owner invariant missing")
    safety_reasons = set(layers["SAFETY_ACCESS"].get("reasons", ()))
    required_safety = {
        "DNS",
        "CONTROL_PROTOCOL",
        "SELF_TRAFFIC",
        "TUN_INGRESS",
        "NODE_ENDPOINT",
        "LOCAL_DESTINATION",
        "REPLY_TRAFFIC",
        "SERVICE_PORT",
        "ACCESS_CONTROL",
    }
    if not required_safety.issubset(safety_reasons):
        raise SpecValidationError("safety layer is incomplete")
    policy_reasons = set(layers["ROUTING_POLICY"].get("reasons", ()))
    if not {"FAKEIP", "EXPLICIT_DIRECT", "EXPLICIT_PROXY", "CHINA_PASS", "CHINA_POLICY", "DEFAULT_POLICY"}.issubset(policy_reasons):
        raise SpecValidationError("routing-policy layer is incomplete")

    reason_contract = spec.get("semantic_reason_contract")
    _require_mapping(reason_contract, "semantic_reason_contract")
    if set(reason_contract) != set(MATCH_REASONS):
        raise SpecValidationError("semantic reason contract must cover every match reason")
    for reason in MATCH_REASONS:
        entry = reason_contract[reason]
        _require_mapping(entry, "semantic_reason_contract." + reason)
        for field in (
            "layer",
            "meaning",
            "family_scope",
            "direction_scope",
            "decision_current",
            "decision_target",
            "precedence_current",
            "precedence_target",
            "current_behavior",
            "target_behavior",
        ):
            if field not in entry:
                raise SpecValidationError("semantic reason {} missing {}".format(reason, field))
        if not entry["meaning"] or not entry["current_behavior"] or not entry["target_behavior"]:
            raise SpecValidationError("semantic reason {} has empty explanation".format(reason))
        if not isinstance(entry["family_scope"], list) or not entry["family_scope"]:
            raise SpecValidationError("semantic reason {} has no family scope".format(reason))
        if not isinstance(entry["direction_scope"], list) or not entry["direction_scope"]:
            raise SpecValidationError("semantic reason {} has no direction scope".format(reason))
        if entry["decision_current"] is not None and entry["decision_current"] not in set(DECISIONS) | {"CURRENT_UNDEFINED", "BYPASS_OR_CURRENT_GAP", "BYPASS_OR_ACCESS_DENY", "DEFAULT_FALLTHROUGH"}:
            raise SpecValidationError("semantic reason {} has invalid current decision".format(reason))
        if entry["decision_target"] is not None and entry["decision_target"] not in set(DECISIONS) | {"CURRENT_UNDEFINED", "BYPASS_OR_CURRENT_GAP", "BYPASS_OR_ACCESS_DENY", "DEFAULT_FALLTHROUGH"}:
            raise SpecValidationError("semantic reason {} has invalid target decision".format(reason))

    profiles = spec.get("profiles")
    _require_mapping(profiles, "profiles")
    if set(profiles) != set(PROFILE_VALUES):
        raise SpecValidationError("profile set must be exactly current and target")
    for profile, expected_labels in (("current", CURRENT_LABELS), ("target", TARGET_LABELS)):
        _require_mapping(profiles[profile], "profiles." + profile)
        if tuple(profiles[profile].get("precedence_labels", ())) != expected_labels:
            raise SpecValidationError("{} precedence drift".format(profile))
    if profiles["current"].get("production_approved") is not True:
        raise SpecValidationError("current profile must be the production oracle")
    if profiles["target"].get("production_approved") is not False:
        raise SpecValidationError("target profile must remain preview-only")

    details = spec.get("precedence_detail")
    _require_mapping(details, "precedence_detail")
    for profile, expected_labels in (("current", CURRENT_LABELS), ("target", TARGET_LABELS)):
        table = details.get(profile)
        if not isinstance(table, list) or len(table) != len(expected_labels):
            raise SpecValidationError("{} precedence detail length".format(profile))
        for index, (entry, expected_label) in enumerate(zip(table, expected_labels)):
            _require_mapping(entry, "precedence_detail.{}.{}".format(profile, index))
            if entry.get("order") != index or entry.get("label") != expected_label:
                raise SpecValidationError("{} precedence order drift".format(profile))
            if _semantic_reason(expected_label) != entry.get("match_reason"):
                raise SpecValidationError("{} precedence reason drift".format(profile))
            if entry.get("family") not in {"ALL", "IPv4", "IPv6"}:
                raise SpecValidationError("invalid precedence family")
            decision = entry.get("decision", "")
            allowed_decisions = set(DECISIONS) | {
                "BYPASS_OR_ACCESS_DENY",
                "DEFAULT_FALLTHROUGH",
            }
            if decision not in allowed_decisions:
                raise SpecValidationError("backend-specific or unknown decision in precedence")

    family_rules = spec.get("family_specific_rules")
    _require_nonempty_list(family_rules, "family_specific_rules")
    for rule in family_rules:
        _require_mapping(rule, "family_specific_rules entry")
        if rule.get("family") not in {"IPv4", "IPv6", "ALL"}:
            raise SpecValidationError("invalid family-specific rule family")
    if not any(rule.get("semantic") == "WAN_HOST" and rule.get("representation") == "HOST_SEMANTIC_128" for rule in family_rules):
        raise SpecValidationError("WAN IPv6 host semantic missing")
    if not any(rule.get("semantic") == "NATIVE_ROUTING" and rule.get("generic_main_default") == "FORBIDDEN" for rule in family_rules):
        raise SpecValidationError("native IPv6 default guard missing")

    decision_contract = spec.get("semantic_decision_contract")
    _require_mapping(decision_contract, "semantic_decision_contract")
    if set(decision_contract) != set(DECISIONS):
        raise SpecValidationError("semantic decision contract incomplete")
    for decision, detail in decision_contract.items():
        _require_mapping(detail, "semantic_decision_contract." + decision)
        if not detail.get("meaning") or not detail.get("backend_requirement"):
            raise SpecValidationError("decision contract entry incomplete")

    local_contract = spec.get("local_destination_contract")
    _require_mapping(local_contract, "local_destination_contract")
    local_facts = {entry.get("name") for entry in local_contract.get("facts", ()) if isinstance(entry, dict)}
    if local_facts != {"LOOPBACK", "PRIVATE", "LINK_LOCAL", "MULTICAST", "WAN_HOST", "LAN_PREFIX", "DELEGATED_PREFIX"}:
        raise SpecValidationError("local destination fact taxonomy incomplete")
    if local_contract.get("decision") != "BYPASS" or not local_contract.get("rule"):
        raise SpecValidationError("local destination contract incomplete")

    source_map = spec.get("fact_source_map")
    _require_nonempty_list(source_map, "fact_source_map")
    seen_facts = set()
    for entry in source_map:
        _require_mapping(entry, "fact_source_map entry")
        fact = entry.get("semantic_fact")
        if fact in seen_facts:
            raise SpecValidationError("duplicate fact source: {}".format(fact))
        seen_facts.add(fact)
        for field in ("current_source", "primary_source", "normalization", "owner", "volatility", "confidence", "source_status"):
            if not entry.get(field):
                raise SpecValidationError("fact source {} missing {}".format(fact, field))
    if seen_facts != CORE_FACTS:
        raise SpecValidationError("fact source map incomplete: {}".format(sorted(CORE_FACTS - seen_facts)))
    for fact in ("EXPLICIT_DIRECT", "EXPLICIT_PROXY"):
        entry = next(item for item in source_map if item["semantic_fact"] == fact)
        if entry.get("source_status") != "UNRESOLVED_CURRENT_MAPPING":
            raise SpecValidationError("explicit policy mapping must stay unresolved")

    renderer = spec.get("renderer_input_contract")
    _require_mapping(renderer, "renderer_input_contract")
    for field in ("required_fields", "classification_fields", "backend_context_fields", "rules"):
        _require_nonempty_list(renderer.get(field), "renderer_input_contract." + field)
    if "profile" not in renderer["required_fields"] or "classification" not in renderer["required_fields"]:
        raise SpecValidationError("renderer input is missing profile/classification")
    for rule in renderer["rules"]:
        if not isinstance(rule, str) or not rule.strip():
            raise SpecValidationError("renderer rule must be text")

    invariants = spec.get("renderer_invariants")
    _require_nonempty_list(invariants, "renderer_invariants")
    invariant_names = {entry.get("name") for entry in invariants if isinstance(entry, dict)}
    required_invariants = {
        "POLICY_INDEPENDENT",
        "FAIL_CLOSED",
        "OWNERSHIP_SCOPED_CLEANUP",
        "SINGLE_WRITER",
        "FAMILY_PARITY",
        "BACKEND_PARITY",
        "NATIVE_IPV6_OWNERSHIP",
        "NO_GENERIC_IPV6_DEFAULT",
        "NO_FOREIGN_FLUSH",
        "DEFAULT_CURRENT",
    }
    if not required_invariants.issubset(invariant_names):
        raise SpecValidationError("renderer invariants incomplete")
    for entry in invariants:
        _require_mapping(entry, "renderer invariant")
        if not entry.get("id") or not entry.get("requirement"):
            raise SpecValidationError("renderer invariant entry incomplete")

    action_contract = spec.get("backend_action_contract")
    _require_mapping(action_contract, "backend_action_contract")
    for key in ("PROXY", "BYPASS", "DIRECT", "DNS_SPECIAL", "NOT_OWNED", "ACCESS_DENY"):
        if key not in action_contract:
            raise SpecValidationError("backend action contract missing {}".format(key))
    proxy_actions = action_contract["PROXY"]
    if not isinstance(proxy_actions, list) or not any(item.get("run_mode") == "TUN" for item in proxy_actions):
        raise SpecValidationError("TUN proxy action missing")
    if not any(item.get("run_mode") == "REDIRECT" and item.get("protocol") == "UDP" and item.get("action") == "UNSUPPORTED_ACTION" for item in proxy_actions):
        raise SpecValidationError("REDIRECT UDP capability result missing")

    parity = spec.get("family_parity")
    _require_mapping(parity, "family_parity")
    if not parity.get("parity_required") or not parity.get("family_specific"):
        raise SpecValidationError("family parity contract incomplete")
    modern_legacy = spec.get("modern_legacy_parity")
    _require_mapping(modern_legacy, "modern_legacy_parity")
    if not modern_legacy.get("requirements") or not modern_legacy.get("rule"):
        raise SpecValidationError("modern/legacy parity contract incomplete")

    static_dynamic = spec.get("static_dynamic_contract")
    _require_mapping(static_dynamic, "static_dynamic_contract")
    _require_nonempty_list(static_dynamic.get("static_semantics"), "static semantics")
    _require_nonempty_list(static_dynamic.get("dynamic_data"), "dynamic data")
    if not static_dynamic.get("rule"):
        raise SpecValidationError("static/dynamic rule missing")

    access = spec.get("access_control_contract")
    _require_mapping(access, "access_control_contract")
    if access.get("independent_layer") is not True or set(access.get("facts", ())) != {"ACCESS_BYPASS", "ACCESS_DENY"}:
        raise SpecValidationError("access/routing separation missing")
    dns = spec.get("dns_contract")
    _require_mapping(dns, "dns_contract")
    if dns.get("reason") != "DNS" or dns.get("decision") != "DNS_SPECIAL" or dns.get("independent_from_routing_policy") is not True:
        raise SpecValidationError("DNS special contract incomplete")

    underlay = spec.get("underlay_contract")
    _require_mapping(underlay, "underlay_contract")
    if set(underlay.get("loop_prevention_reasons", ())) != {"NODE_ENDPOINT", "SELF_TRAFFIC", "TUN_INGRESS"}:
        raise SpecValidationError("underlay loop-prevention reasons incomplete")
    native = spec.get("native_routing_contract")
    _require_mapping(native, "native_routing_contract")
    if native.get("generic_main_table_ipv6_default") != "FORBIDDEN" or native.get("nat66") != "FORBIDDEN_AS_ROUTING_SOLUTION":
        raise SpecValidationError("native IPv6 routing guard missing")
    mark = spec.get("mark_abi")
    _require_mapping(mark, "mark_abi")
    if mark != {
        "version": 1,
        "mark": "0x162",
        "mask": "0xffffffff",
        "route_table": 354,
        "rule_preference": 1888,
        "status": "FROZEN_UNTIL_PHASE_8",
    }:
        raise SpecValidationError("mark ABI drift")

    changes = spec.get("behavior_changes")
    _require_nonempty_list(changes, "behavior_changes")
    if {entry.get("id") for entry in changes} != BC_IDS or len(changes) != len(BC_IDS):
        raise SpecValidationError("BC list must be exactly BC-01 through BC-07")
    for entry in changes:
        _require_mapping(entry, "behavior change")
        if set(entry) != BC_FIELDS:
            raise SpecValidationError("{} behavior change fields incomplete".format(entry.get("id")))
        if entry.get("production_approval_status") != "PRODUCTION_NOT_APPROVED":
            raise SpecValidationError("{} is unexpectedly approved".format(entry.get("id")))
        if entry.get("recommended_decision") not in {"APPROVE", "DEFER", "REJECT"}:
            raise SpecValidationError("{} has invalid recommendation".format(entry.get("id")))
        if not isinstance(entry.get("type"), list) or not entry["type"]:
            raise SpecValidationError("{} has no behavior type".format(entry.get("id")))

    pipeline = spec.get("production_fact_pipeline")
    if pipeline != ["CONFIG_AND_NETIFD", "NORMALIZED_DESIRED_STATE", "SEMANTIC_FACTS", "CLASSIFIER", "BACKEND_RENDERER"]:
        raise SpecValidationError("production fact pipeline drift")
    ssot = spec.get("single_source_of_truth")
    _require_mapping(ssot, "single_source_of_truth")
    if ssot.get("watchdog_role") != "OBSERVER_OR_REQUESTER":
        raise SpecValidationError("watchdog must not be a direct writer")
    phase3_policy = spec.get("phase_3_migration_policy")
    _require_mapping(phase3_policy, "phase_3_migration_policy")
    if phase3_policy.get("initial_profile") != "current" or phase3_policy.get("first_step") != "SEMANTIC_PRESERVING_REFACTOR":
        raise SpecValidationError("phase 3 migration policy must begin with current-preserving refactor")
    golden = spec.get("golden_compatibility")
    _require_mapping(golden, "golden_compatibility")
    for key, expected in {
        "phase_2a_current_cases": 97,
        "phase_2a_target_cases": 97,
        "phase_2a_overlap_cases": 32,
        "phase_2a_parity_groups": 31,
        "phase_2c_shadow_cases": 109,
    }.items():
        if golden.get(key) != expected:
            raise SpecValidationError("golden count drift: {}".format(key))

    serialized = json.dumps(spec, sort_keys=True)
    for pattern in FORBIDDEN_BACKEND_SYNTAX:
        if pattern.search(serialized):
            raise SpecValidationError("backend command syntax leaked into semantic spec: {}".format(pattern.pattern))
    return spec


class DataplaneSemanticSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = validate_spec(load_json(SPEC_FILE))
        cls.classifier_fixture = load_json(CLASSIFIER_FIXTURE)
        validate_fixture(cls.classifier_fixture)
        cls.states_fixture = validate_state_fixture(load_json(STATE_FIXTURE))
        cls.intent_fixture = validate_intent_fixture(load_json(INTENT_FIXTURE))
        cls.state_by_id = {state["id"]: state for state in cls.states_fixture["states"]}

    def test_schema_and_versions(self):
        self.assertEqual(self.spec["dataplane_semantic_spec_version"], 1)
        self.assertEqual(self.spec["classifier_contract_version"], CLASSIFIER_CONTRACT_VERSION)
        self.assertEqual(self.spec["shadow_state_schema_version"], SHADOW_CONTRACT_VERSION)
        self.assertEqual(self.spec["current_intent_version"], self.intent_fixture["contract_version"])
        self.assertEqual(self.spec["default_production_profile"], "current")

    def test_mutation_guards_reject_schema_profile_and_enum_drift(self):
        mutations = []
        unknown_profile = copy.deepcopy(self.spec)
        unknown_profile["profiles"]["future"] = {}
        mutations.append(unknown_profile)
        bad_profile = copy.deepcopy(self.spec)
        bad_profile["default_production_profile"] = "target"
        mutations.append(bad_profile)
        bad_enum = copy.deepcopy(self.spec)
        bad_enum["decision_enum"].append("MARK")
        mutations.append(bad_enum)
        bad_version = copy.deepcopy(self.spec)
        bad_version["dataplane_semantic_spec_version"] = 2
        mutations.append(bad_version)
        for mutated in mutations:
            with self.assertRaises(SpecValidationError):
                validate_spec(mutated)

    def test_precedence_and_renderer_contract_drift(self):
        for profile, expected in (("current", CURRENT_LABELS), ("target", TARGET_LABELS)):
            self.assertEqual(tuple(self.spec["profiles"][profile]["precedence_labels"]), expected)
            details = self.spec["precedence_detail"][profile]
            self.assertEqual([entry["order"] for entry in details], list(range(len(expected))))
            self.assertEqual(tuple(entry["label"] for entry in details), expected)
        self.assertEqual(self.spec["renderer_input_contract"]["classification_fields"], [
            "status", "reason", "decision", "matched_rule", "precedence_index"
        ])
        self.assertEqual(self.spec["renderer_invariants"][0]["name"], "POLICY_INDEPENDENT")

    def test_behavior_change_records_and_fact_sources_are_complete(self):
        self.assertEqual({entry["id"] for entry in self.spec["behavior_changes"]}, BC_IDS)
        self.assertTrue(all(entry["production_approval_status"] == "PRODUCTION_NOT_APPROVED" for entry in self.spec["behavior_changes"]))
        self.assertEqual({entry["semantic_fact"] for entry in self.spec["fact_source_map"]}, CORE_FACTS)

    def test_current_golden_replay_and_counts(self):
        statuses = {status: 0 for status in STATUS_VALUES}
        for case in self.classifier_fixture["cases"]:
            result = classify(case, profile="current")
            self.assertEqual(result.as_dict(), case["expected_current"], case["id"])
            statuses[result.status] += 1
        self.assertEqual(len(self.classifier_fixture["cases"]), 97)
        self.assertEqual(statuses, {"VALID": 89, "CURRENT_UNDEFINED": 7, "INVALID_CONFIGURATION": 1})

    def test_target_golden_replay_and_counts(self):
        statuses = {status: 0 for status in STATUS_VALUES}
        for case in self.classifier_fixture["cases"]:
            result = classify(case, profile="target")
            self.assertEqual(result.as_dict(), case["expected_target"], case["id"])
            statuses[result.status] += 1
        self.assertEqual(statuses, {"VALID": 96, "CURRENT_UNDEFINED": 0, "INVALID_CONFIGURATION": 1})

    def test_shadow_current_intent_compatibility(self):
        results = []
        for case in self.intent_fixture["cases"]:
            result = shadow_compare(self.state_by_id[case["state_id"]], case["packet"], case)
            self.assertIn(result["result"], SHADOW_RESULTS)
            self.assertIsNone(result["mismatch"], case["id"])
            results.append(result["result"])
        self.assertEqual(len(results), 109)
        self.assertEqual(results.count("MATCH"), 101)
        self.assertEqual(results.count("EXPECTED_CURRENT_GAP"), 7)
        self.assertEqual(results.count("INVALID_STATE"), 1)
        self.assertEqual(results.count("SEMANTIC_MISMATCH"), 0)
        self.assertEqual(results.count("UNMAPPED_STATE"), 0)
        self.assertEqual(results.count("NOT_APPLICABLE"), 0)

    def test_cross_contract_counts_and_references(self):
        cases = self.classifier_fixture["cases"]
        self.assertEqual(sum(case["category"] == "OVERLAP" for case in cases), 32)
        pairs = {case["parity_pair"] for case in cases if case.get("parity_pair")}
        self.assertEqual(len(pairs), 31)
        golden = self.spec["golden_compatibility"]
        self.assertEqual(golden["current_intent_fixture"], INTENT_FIXTURE.name)
        self.assertEqual(golden["shadow_state_fixture"], STATE_FIXTURE.name)

    def test_unknown_profile_and_unknown_backend_action_are_fail_closed(self):
        case = self.classifier_fixture["cases"][0]
        with self.assertRaises(ValueError):
            classify(case, profile="future")
        action = self.spec["backend_action_contract"]["PROXY"]
        udp_redirect = next(item for item in action if item.get("run_mode") == "REDIRECT" and item.get("protocol") == "UDP")
        self.assertEqual(udp_redirect["action"], "UNSUPPORTED_ACTION")
        self.assertEqual(self.spec["backend_action_contract"]["ACCESS_DENY"], "ACCESS_DENY_REQUIRED_CAPABILITY")

    def test_production_wiring_and_native_invariants_are_explicit(self):
        self.assertEqual(self.spec["production_wiring"], "NONE")
        self.assertEqual(self.spec["cleanup_contract"]["writer"], "RECONCILE_ONLY")
        self.assertEqual(self.spec["single_source_of_truth"]["watchdog_role"], "OBSERVER_OR_REQUESTER")
        self.assertEqual(self.spec["native_routing_contract"]["generic_main_table_ipv6_default"], "FORBIDDEN")
        self.assertEqual(self.spec["mark_abi"]["mark"], "0x162")
        self.assertEqual(self.spec["mark_abi"]["mask"], "0xffffffff")
        self.assertEqual(self.spec["mark_abi"]["route_table"], 354)
        self.assertEqual(self.spec["mark_abi"]["rule_preference"], 1888)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DataplaneSemanticSpecTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
