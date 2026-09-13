#!/usr/bin/env python3
"""Phase 3A abstract NFT IR and central renderer design tests.

Everything in this test is fixture-only.  The renderer is intentionally
development-only: it does not source production shell, run a command, touch
the network, or mutate the OpenWrt dataplane.
"""

from __future__ import annotations

import ast
import copy
import json
import os
import pathlib
import unittest

from openkill_classifier_model import (
    CURRENT_PRECEDENCE,
    DECISIONS,
    MATCH_REASONS,
    TARGET_PRECEDENCE,
    classify,
    validate_fixture,
)
from openkill_shadow_adapter import adapt, shadow_compare, validate_intent_fixture, validate_state_fixture
from openkill_nft_ir import (
    ACTION_TYPES,
    COMPONENTS,
    DEFAULT_RENDERER_PROFILE,
    DIFF_CATEGORIES,
    MATCH_TYPES,
    NFT_IR_SCHEMA,
    NFT_IR_VERSION,
    NFTIRValidationError,
    OWNERSHIP_MANIFEST_SCHEMA,
    RENDERER_BACKENDS,
    RENDERER_PROFILES,
    build_static_topology,
    diff_ir,
    map_backend_action,
    ownership_manifest,
    render_context,
    render_plan_text,
    render_state,
    serialize_ir,
    validate_ir,
    validate_ir_fixture,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
IR_FIXTURE = SCRIPT_DIR / "fixtures/openkill-nft-ir-v1.json"
CLASSIFIER_FIXTURE = SCRIPT_DIR / "fixtures/openkill-classifier-semantic-v1.json"
STATE_FIXTURE = SCRIPT_DIR / "fixtures/openkill-shadow-states-v1.json"
INTENT_FIXTURE = SCRIPT_DIR / "fixtures/openkill-current-firewall-intent-v1.json"
IR_SOURCE = SCRIPT_DIR / "openkill_nft_ir.py"


def load_json(path: pathlib.Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class NFTIRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ir_fixture = validate_ir_fixture(load_json(IR_FIXTURE))
        cls.classifier_fixture = validate_fixture(load_json(CLASSIFIER_FIXTURE))
        cls.states = validate_state_fixture(load_json(STATE_FIXTURE))["states"]
        cls.state_by_id = {state["id"]: state for state in cls.states}
        cls.intent = validate_intent_fixture(load_json(INTENT_FIXTURE))

    def test_schema_versions_and_machine_fixture(self):
        self.assertEqual(self.ir_fixture["schema"], "OPENKILL_NFT_IR_FIXTURE_V1")
        self.assertEqual(self.ir_fixture["ir_version"], NFT_IR_VERSION)
        self.assertEqual(self.ir_fixture["default_renderer_profile"], DEFAULT_RENDERER_PROFILE)
        self.assertEqual(self.ir_fixture["supported_backend"], RENDERER_BACKENDS[0])
        self.assertEqual(tuple(self.ir_fixture["action_types"]), ACTION_TYPES)
        self.assertEqual(tuple(self.ir_fixture["match_types"]), MATCH_TYPES)
        self.assertEqual(tuple(self.ir_fixture["components"]), COMPONENTS)
        self.assertEqual(tuple(self.ir_fixture["diff_categories"]), DIFF_CATEGORIES)
        self.assertEqual(self.ir_fixture["ownership_model"]["manifest_schema"], OWNERSHIP_MANIFEST_SCHEMA)

    def test_profile_lock_and_unknown_version_guards(self):
        state = self.state_by_id["STATE-CASE-003"]
        current = render_state(state)
        validate_ir(current)
        self.assertEqual(current["metadata"]["renderer_profile"], "current")
        self.assertEqual(current["metadata"]["behavior_change_lock"], "CURRENT_ONLY")
        with self.assertRaises(NFTIRValidationError):
            render_state(state, profile="target")
        target = render_state(state, profile="target", target_preview=True)
        self.assertEqual(target["metadata"]["behavior_change_lock"], "TARGET_PREVIEW_ONLY")
        validate_ir(target)
        bad = copy.deepcopy(current)
        bad["ir_version"] = 99
        with self.assertRaises(NFTIRValidationError):
            validate_ir(bad)
        bad_fixture = copy.deepcopy(self.ir_fixture)
        bad_fixture["ir_version"] = 2
        with self.assertRaises(NFTIRValidationError):
            validate_ir_fixture(bad_fixture)

    def test_current_profile_replays_all_97_cases(self):
        for case in self.classifier_fixture["cases"]:
            with self.subTest(case=case["id"]):
                result = classify(case, profile="current", trace=True)
                ir = render_context(case, profile="current")
                validate_ir(ir)
                self.assertEqual(ir["classification"], result.to_record(include_trace=True))
                action = ir["action_ir"][0]
                if result.status == "CURRENT_UNDEFINED":
                    self.assertEqual(action["action_type"], "UNRESOLVED_SEMANTIC")
                self.assertEqual(action["reason"], result.reason)
        self.assertEqual(len(self.classifier_fixture["cases"]), 97)

    def test_target_preview_replays_all_97_without_becoming_default(self):
        for case in self.classifier_fixture["cases"]:
            with self.subTest(case=case["id"]):
                expected = classify(case, profile="target", trace=True).to_record(include_trace=True)
                ir = render_context(case, profile="target", target_preview=True)
                validate_ir(ir)
                self.assertEqual(ir["classification"], expected)
                self.assertEqual(ir["metadata"]["behavior_change_lock"], "TARGET_PREVIEW_ONLY")
        self.assertEqual(DEFAULT_RENDERER_PROFILE, "current")

    def test_shadow_current_intent_109_cases_are_renderable(self):
        rendered = 0
        for case in self.intent["cases"]:
            with self.subTest(case=case["id"]):
                state = self.state_by_id[case["state_id"]]
                compared = shadow_compare(state, case["packet"], case)
                adapted = compared["adapted"]
                ir = render_context(adapted["context"], profile="current", state=state)
                validate_ir(ir)
                self.assertEqual(ir["metadata"]["behavior_change_lock"], "CURRENT_ONLY")
                expected = case["independent_expected_current"]["classifier"]
                actual = ir["classification"]
                self.assertEqual(
                    {key: actual[key] for key in ("status", "reason", "decision")},
                    expected,
                    case["id"],
                )
                rendered += 1
        self.assertEqual(rendered, 109)

    def test_overlap_preserves_matches_and_current_outcome(self):
        overlap = [case for case in self.classifier_fixture["cases"] if case.get("overlap")]
        self.assertEqual(len(overlap), 32)
        label_to_reason = {
            "CONTROL": "CONTROL_PROTOCOL",
            "SELF": "SELF_TRAFFIC",
            "TUN": "TUN_INGRESS",
            "NODE": "NODE_ENDPOINT",
            "LOCAL": "LOCAL_DESTINATION",
            "REPLY": "REPLY_TRAFFIC",
            "SERVICE": "SERVICE_PORT",
            "ACCESS": "ACCESS_CONTROL",
            "ACCESS_CONTROL": "ACCESS_CONTROL",
            "FAKEIP": "FAKEIP",
            "USER_DIRECT": "EXPLICIT_DIRECT",
            "USER_PROXY": "EXPLICIT_PROXY",
            "CHINA": "CHINA_POLICY",
            "CHINA_PASS": "CHINA_PASS",
            "DNS": "DNS",
            "OWNER": "OWNER_DISABLED",
        }
        for case in overlap:
            with self.subTest(case=case["id"]):
                result = classify(case, profile="current", trace=True)
                ir = render_context(case, profile="current")
                self.assertEqual(ir["classification"]["reason"], result.reason)
                matched = {
                    item.split(":", 1)[1]
                    for item in result.trace
                    if item.startswith("MATCH:")
                }
                expected_matches = {label_to_reason.get(item, item) for item in case["overlap"]}
                self.assertTrue(expected_matches.issubset(matched), (case["id"], expected_matches, matched))
                self.assertEqual(ir["action_ir"][0]["reason"], result.reason)

    def test_set_normalization_and_ipv6_host_prefix_semantics(self):
        state = copy.deepcopy(self.state_by_id["STATE-CASE-012"])
        state["wan6"] = ["2001:0DB8:0100::12/64", "2001:db8:100::12", "2001:db8:100::12/128"]
        state["node6"] = ["2001:0db8::5", "2001:db8::5"]
        state["local6"] = ["2001:db8:200::/64", "2001:0db8:0200::1/128"]
        ir = render_state(state)
        validate_ir(ir)
        sets = {entry["logical_id"]: entry for entry in ir["dynamic_state"]["sets"]}
        self.assertEqual(sets["WAN_HOST_V6"]["elements"], ["2001:db8:100::12/128"])
        self.assertEqual(sets["NODE_ENDPOINT_V6"]["elements"], ["2001:db8::5"])
        self.assertEqual(sets["LOCAL_V6"]["elements"], ["2001:db8:200::/64", "2001:db8:200::1/128"])
        self.assertEqual(sets["NODE_ENDPOINT_V4"]["elements"], [])

    def test_static_dynamic_and_component_diffs(self):
        base = self.state_by_id["STATE-04-NODES"]
        node = copy.deepcopy(base)
        node["node4"] = list(node["node4"]) + ["203.0.113.201"]
        node_diff = diff_ir(render_state(base), render_state(node))
        self.assertFalse(node_diff["no_change"])
        self.assertIn("SET_ELEMENT_CHANGE", node_diff["categories"])
        self.assertEqual(node_diff["changed_components"], ["NODE"])
        self.assertNotIn("TOPOLOGY_CHANGE", node_diff["categories"])
        local = copy.deepcopy(base)
        local["local6"] = list(local["local6"]) + ["2001:db8:300::/64"]
        local_diff = diff_ir(render_state(base), render_state(local))
        self.assertEqual(local_diff["changed_components"], ["LOCAL"])
        china = copy.deepcopy(base)
        china["china4"] = ["203.0.113.0/24"]
        self.assertEqual(diff_ir(render_state(base), render_state(china))["changed_components"], ["CHINA"])
        acl = copy.deepcopy(base)
        acl["access4"] = [{"network": "203.0.113.0/24", "action": "DENY"}]
        self.assertEqual(diff_ir(render_state(base), render_state(acl))["changed_components"], ["ACCESS"])

    def test_mode_owner_and_no_change_diffs(self):
        base = self.state_by_id["STATE-04-NODES"]
        same = diff_ir(render_state(base), render_state(copy.deepcopy(base)))
        self.assertEqual(same["categories"], ["NO_CHANGE"])
        self.assertTrue(same["no_change"])
        tproxy = copy.deepcopy(base)
        tproxy["run_mode"] = "TPROXY"
        mode_diff = diff_ir(render_state(base), render_state(tproxy))
        self.assertIn("TOPOLOGY_CHANGE", mode_diff["categories"])
        self.assertIn("PROXY_ACTION", mode_diff["changed_components"])
        mihomo = copy.deepcopy(base)
        mihomo["owner"] = "MIHOMO"
        owner_diff = diff_ir(render_state(base), render_state(mihomo))
        self.assertIn("OWNER", owner_diff["changed_components"])
        self.assertIn("TOPOLOGY_REMOVE", owner_diff["categories"])
        self.assertEqual(render_state(mihomo)["ownership_manifest"]["entries"], [])

    def test_ownership_manifest_and_foreign_preservation(self):
        ir = render_state(self.state_by_id["STATE-CASE-003"])
        foreign = {
            "object_type": "chain",
            "logical_id": "FOREIGN_SAME_NAME",
            "physical_name": "openkill_mangle",
            "owner": "FOREIGN",
            "ownership": "FOREIGN",
            "parent_owner": "FW4",
            "parent_table": "inet fw4",
            "component": "TOPOLOGY",
            "family": "IPv4",
            "semantic_spec_version": 1,
        }
        ir["foreign_objects"] = [foreign]
        validate_ir(ir)
        manifest = ownership_manifest(ir)
        self.assertNotIn("FOREIGN_SAME_NAME", {entry["logical_id"] for entry in manifest["entries"]})
        bad = copy.deepcopy(ir)
        bad["foreign_objects"][0]["ownership"] = "OWNED"
        with self.assertRaises(NFTIRValidationError):
            validate_ir(bad)
        duplicate = copy.deepcopy(ir)
        duplicate["foreign_objects"][0]["logical_id"] = ir["rules"][0]["logical_id"]
        with self.assertRaises(NFTIRValidationError):
            validate_ir(duplicate)

    def test_actions_and_backend_capability_separation(self):
        self.assertEqual(map_backend_action("BYPASS", "TUN", "TCP"), "RETURN_NATIVE")
        self.assertEqual(map_backend_action("DIRECT", "TUN", "UDP"), "RETURN_NATIVE")
        self.assertEqual(map_backend_action("PROXY", "TUN", "TCP"), "MARK_PROXY")
        self.assertEqual(map_backend_action("PROXY", "TPROXY", "UDP"), "TPROXY_PROXY")
        self.assertEqual(map_backend_action("PROXY", "REDIRECT", "TCP"), "REDIRECT_PROXY")
        self.assertEqual(map_backend_action("PROXY", "REDIRECT", "UDP"), "UNSUPPORTED_ACTION")
        self.assertEqual(map_backend_action("DNS_SPECIAL", "TUN", "UDP"), "DNS_REDIRECT")
        self.assertEqual(map_backend_action("ACCESS_DENY", "TUN", "TCP"), "ACCESS_DENY_REQUIRED")
        self.assertEqual(map_backend_action("NOT_OWNED", "TUN", "TCP"), "NOT_OWNED")
        # Action mapper never changes the classifier result or reason.
        case = next(case for case in self.classifier_fixture["cases"] if case["id"] == "v4_default_tcp")
        ir = render_context(case)
        self.assertEqual(ir["classification"]["decision"], "PROXY")
        self.assertEqual(ir["action_ir"][0]["reason"], "DEFAULT_POLICY")

    def test_external_priority_and_current_nat_output(self):
        topology = build_static_topology()
        refs = {obj["logical_id"]: obj for obj in topology["objects"]}
        self.assertEqual(refs["FW4_MANGLE_PREROUTING"]["priority"], "EXTERNAL_UNVERIFIED")
        self.assertEqual(refs["OPENKILL_NAT_OUTPUT_CURRENT"]["priority"], -1)
        self.assertEqual(refs["OPENKILL_NAT_OUTPUT_CURRENT"]["base_chain"], True)
        self.assertEqual(refs["OPENKILL_NAT_OUTPUT_CURRENT"]["parent_owner"], "FW4")

    def test_determinism_input_order_and_plan(self):
        state = copy.deepcopy(self.state_by_id["STATE-04-NODES"])
        reordered = {key: copy.deepcopy(value) for key, value in reversed(list(state.items()))}
        for key, value in list(reordered.items()):
            if isinstance(value, list):
                reordered[key] = list(reversed(value))
        first = render_state(state)
        second = render_state(reordered)
        self.assertEqual(serialize_ir(first), serialize_ir(second))
        self.assertEqual(serialize_ir(first), serialize_ir(first))
        self.assertIn("Static topology objects", render_plan_text(first))

    def test_validation_rejects_unknown_action_duplicate_id_and_command_syntax(self):
        ir = render_state(self.state_by_id["STATE-CASE-003"])
        bad_action = copy.deepcopy(ir)
        bad_action["rules"][0]["action_type"] = "DROP_NOW"
        with self.assertRaises(NFTIRValidationError):
            validate_ir(bad_action)
        bad_id = copy.deepcopy(ir)
        bad_id["rules"][0]["logical_id"] = bad_id["rules"][1]["logical_id"]
        with self.assertRaises(NFTIRValidationError):
            validate_ir(bad_id)
        bad_command = copy.deepcopy(ir)
        bad_command["rules"][0]["match"]["note"] = "nft add rule"
        with self.assertRaises(NFTIRValidationError):
            validate_ir(bad_command)

    def test_no_policy_reimplementation_or_side_effects(self):
        source = IR_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        imported_names = {alias.name.split(".")[0] for node in imports for alias in node.names}
        self.assertNotIn("subprocess", imported_names)
        self.assertNotIn("os", imported_names)
        self.assertNotIn("socket", imported_names)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotEqual(node.func.attr, "system")
        # Only the classifier model owns precedence.  The renderer references
        # its table instead of carrying a second China/node policy ladder.
        self.assertEqual(source.count("CURRENT_PRECEDENCE"), 1)
        self.assertEqual(source.count("TARGET_PRECEDENCE"), 1)
        before_cwd = os.getcwd()
        before_env = dict(os.environ)
        render_state(self.state_by_id["STATE-CASE-003"])
        self.assertEqual(os.getcwd(), before_cwd)
        self.assertEqual(dict(os.environ), before_env)

    def test_dependency_graph_and_current_gap_guards(self):
        ir = render_state(self.state_by_id["STATE-CASE-003"])
        deps = ir["dependencies"]
        self.assertEqual(deps["TOPOLOGY"], ["NODE", "LOCAL", "CHINA", "ACCESS", "SERVICE", "DNS", "PROXY_ACTION"])
        current_rules = {rule["semantic_reason"]: rule for rule in ir["rules"] if rule.get("precedence_label") == "TUN_INGRESS"}
        self.assertIn("BC-04", {rule.get("known_current_gap") for rule in current_rules.values()})
        placeholders = [rule for rule in ir["rules"] if rule.get("precedence_label") == "CURRENT_UNDEFINED"]
        self.assertEqual(len(placeholders), 4)
        self.assertTrue(all(rule["action_type"] == "UNRESOLVED_SEMANTIC" for rule in placeholders))
        self.assertEqual(ir["metadata"]["production_profile_default"], "current")


if __name__ == "__main__":
    unittest.main(verbosity=2)
