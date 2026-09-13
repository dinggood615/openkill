#!/usr/bin/env python3
"""Validate the Phase 3D guarded central-renderer wiring design.

The tests exercise only the pure development model and its machine-readable
fixture.  They do not import production shell, invoke a command, contact a
device, or mutate a firewall.
"""

from __future__ import annotations

import ast
import json
import pathlib
import unittest

from openkill_central_wiring_model import (
    ALLOWED_TRANSITIONS,
    CENTRAL_WIRING_SCHEMA,
    CENTRAL_WIRING_VERSION,
    DEFAULT_ENGINE_MODE,
    DEFAULT_PRODUCTION_PROFILE,
    ENGINE_MODES,
    FAILURE_CLASSES,
    MARK_ABI,
    OWNERS,
    WIRING_STATES,
    WiringValidationError,
    central_renderer_eligible,
    desired_hash,
    evaluate_eligibility,
    failure_action,
    ownership_transition,
    payload_hash,
    profile_allowed,
    single_writer_valid,
    source_drift_ok,
    validate_transition,
    validate_wiring_fixture,
    writer_policy,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "scripts/fixtures/openkill-central-wiring-v1.json"
MODEL = ROOT / "scripts/openkill_central_wiring_model.py"


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def eligible_facts():
    return {
        "fw4_present": True,
        "nft_capability_supported": True,
        "backend": "modern_fw4_nft",
        "owner": "OPENKILL",
        "profile": "current",
        "semantic_spec_version": 1,
        "classifier_contract_version": 1,
        "shadow_state_schema_version": 1,
        "nft_ir_version": 1,
        "manifest_version": 1,
        "current_state_supported": True,
        "bc07_active": False,
        "explicit_policy_unresolved": False,
        "bc02_current_order_verified": True,
        "bc03_current_order_preserved": True,
        "bc04_current_gap_preserved": True,
        "bc05_diagnostic_only": True,
        "bc06_diagnostic_only": True,
        "nft_check_pass": True,
        "runtime_healthy": True,
        "owner_transition": False,
        "pending_fw4_reconcile": False,
        "component_failure": False,
        "restart_required": False,
        "same_name_foreign_collision": False,
        "listener_ports_valid": True,
        "watchdog_single_writer_ready": True,
        "fw4_worker_single_writer_ready": True,
        "no_old_writer_active": True,
        "manifest_ready": True,
        "mark_abi": dict(MARK_ABI),
    }


class CentralWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture()
        validate_wiring_fixture(cls.fixture)

    def test_machine_fixture_schema_versions_and_enums(self):
        self.assertEqual(self.fixture["schema"], CENTRAL_WIRING_SCHEMA)
        self.assertEqual(self.fixture["version"], CENTRAL_WIRING_VERSION)
        self.assertEqual(self.fixture["default_engine"], DEFAULT_ENGINE_MODE)
        self.assertEqual(self.fixture["default_production_profile"], DEFAULT_PRODUCTION_PROFILE)
        self.assertEqual(tuple(self.fixture["engine_modes"]), ENGINE_MODES)
        self.assertEqual(tuple(self.fixture["states"]), WIRING_STATES)
        self.assertEqual(set(self.fixture["failure_classes"]), set(FAILURE_CLASSES))
        self.assertEqual(self.fixture["versions"]["mark_abi"], MARK_ABI["version"])
        self.assertEqual(self.fixture["mark_abi"], MARK_ABI)

    def test_default_is_legacy_and_target_is_preview_only(self):
        self.assertEqual(self.fixture["default_engine"], "legacy")
        self.assertTrue(profile_allowed("current", production=True))
        self.assertFalse(profile_allowed("target", production=True))
        self.assertFalse(profile_allowed("target", production=False, development_preview=False))
        self.assertTrue(profile_allowed("target", production=False, development_preview=True))
        self.assertFalse(profile_allowed("future", production=True))

    def test_writer_modes_have_at_most_one_mutator(self):
        legacy = writer_policy("legacy")
        shadow = writer_policy("shadow")
        blocked = writer_policy("central", central_eligible=False)
        central = writer_policy("central", central_eligible=True)
        self.assertTrue(legacy["old_can_write"])
        self.assertFalse(legacy["new_can_write"])
        self.assertTrue(shadow["old_can_write"])
        self.assertTrue(shadow["new_can_compute"])
        self.assertFalse(shadow["new_can_write"])
        self.assertTrue(blocked["blocked"])
        self.assertEqual(blocked["runtime_writer"], "none")
        self.assertTrue(central["new_can_write"])
        for policy in (legacy, shadow, blocked, central):
            self.assertTrue(single_writer_valid(policy))
        self.assertFalse(single_writer_valid({"old_can_write": True, "new_can_write": False, "runtime_writer": "central"}))
        self.assertFalse(single_writer_valid({"old_can_write": False, "new_can_write": False, "runtime_writer": "legacy"}))

    def test_state_machine_requires_precheck(self):
        self.assertTrue(validate_transition("LEGACY_AUTHORITATIVE", "SHADOW_COMPARE")["valid"])
        self.assertTrue(validate_transition("SHADOW_COMPARE", "CENTRAL_PRECHECK")["valid"])
        with self.assertRaises(WiringValidationError):
            validate_transition("LEGACY_AUTHORITATIVE", "CENTRAL_ACTIVE")
        with self.assertRaises(WiringValidationError):
            validate_transition("CENTRAL_PRECHECK", "CENTRAL_ACTIVE")
        self.assertTrue(validate_transition("CENTRAL_PRECHECK", "CENTRAL_ACTIVE", eligibility_pass=True)["writer_grant"])
        with self.assertRaises(WiringValidationError):
            validate_transition("CENTRAL_ACTIVE", "LEGACY_AUTHORITATIVE")

    def test_fixture_transitions_match_executable_graph(self):
        listed = {(item["from"], item["to"]) for item in self.fixture["transitions"]}
        for source, targets in ALLOWED_TRANSITIONS.items():
            for target in targets:
                self.assertIn((source, target), listed)
        illegal = {(item["from"], item["to"]) for item in self.fixture["illegal_transitions"]}
        self.assertIn(("LEGACY_AUTHORITATIVE", "CENTRAL_ACTIVE"), illegal)

    def test_complete_eligibility_passes(self):
        result = evaluate_eligibility(eligible_facts())
        self.assertTrue(result["eligible"], result)
        self.assertTrue(central_renderer_eligible(eligible_facts()))
        self.assertEqual(result["blockers"], [])
        self.assertTrue(all(result["checks"].values()))

    def test_each_unsafe_fact_fails_closed(self):
        cases = {
            "bc07_active": True,
            "explicit_policy_unresolved": True,
            "owner_transition": True,
            "pending_fw4_reconcile": True,
            "same_name_foreign_collision": True,
            "nft_check_pass": False,
            "listener_ports_valid": False,
            "watchdog_single_writer_ready": False,
            "fw4_worker_single_writer_ready": False,
            "no_old_writer_active": False,
        }
        for key, value in cases.items():
            facts = eligible_facts()
            facts[key] = value
            result = evaluate_eligibility(facts)
            self.assertFalse(result["eligible"], key)
            self.assertTrue(result["blockers"], key)

    def test_unknown_and_wrong_profile_owner_version_fail_closed(self):
        for key, value in (
            ("profile", "target"),
            ("owner", "MIHOMO"),
            ("semantic_spec_version", 9),
            ("backend", "legacy_iptables"),
        ):
            facts = eligible_facts()
            facts[key] = value
            self.assertFalse(evaluate_eligibility(facts)["eligible"], key)
        facts = eligible_facts()
        del facts["nft_ir_version"]
        result = evaluate_eligibility(facts)
        self.assertFalse(result["eligible"])
        self.assertIn("UNKNOWN_NFT_IR_VERSION", result["blockers"])

    def test_mark_abi_is_exact_and_frozen(self):
        facts = eligible_facts()
        facts["mark_abi"] = dict(MARK_ABI, mark="0x163")
        result = evaluate_eligibility(facts)
        self.assertFalse(result["eligible"])
        self.assertIn("MARK_ABI_MISMATCH", result["blockers"])

    def test_failure_classes_have_bounded_safe_actions(self):
        for failure in FAILURE_CLASSES:
            action = failure_action(failure)
            self.assertIn("next_state", action)
            self.assertIn("action", action)
            self.assertTrue(action["action"])
        self.assertTrue(failure_action("PRECHECK_FAIL")["runtime_untouched"])
        self.assertTrue(failure_action("NFT_CHECK_FAIL")["old_authority_unchanged"])
        self.assertEqual(failure_action("POST_VERIFY_FAIL")["next_state"], "ROLLBACK")
        with self.assertRaises(WiringValidationError):
            failure_action("UNKNOWN")

    def test_owner_transition_never_dual_owns(self):
        same = ownership_transition("OPENKILL", "OPENKILL")
        self.assertTrue(same["allowed"])
        mihomo = ownership_transition("OPENKILL", "MIHOMO")
        self.assertFalse(mihomo["allowed"])
        self.assertEqual(mihomo["writer"], "NONE")
        reacquire = ownership_transition("MIHOMO", "OPENKILL")
        self.assertFalse(reacquire["allowed"])
        unknown = ownership_transition("UNKNOWN", "OPENKILL")
        self.assertFalse(unknown["allowed"])
        self.assertEqual(unknown["action"], "FAIL_CLOSED_UNKNOWN_OWNER")

    def test_source_hash_drift_gate(self):
        baseline = self.fixture["source_drift_gate"]["baseline_sha256"]
        self.assertTrue(source_drift_ok(baseline, baseline))
        changed = dict(baseline)
        key = next(iter(changed))
        changed[key] = "0" * 64
        self.assertFalse(source_drift_ok(changed, baseline))
        malformed = dict(baseline)
        malformed[key] = "short"
        self.assertFalse(source_drift_ok(malformed, baseline))
        self.assertFalse(source_drift_ok({}, {}))

    def test_hashes_are_canonical_and_not_time_based(self):
        left = {"sets": ["node4", "node6"], "rules": {"b": 2, "a": 1}}
        right = {"rules": {"a": 1, "b": 2}, "sets": ["node4", "node6"]}
        self.assertEqual(desired_hash(left), desired_hash(right))
        self.assertEqual(desired_hash(dict(left, timestamp=1)), desired_hash(dict(left, timestamp=2)))
        self.assertEqual(payload_hash("table inet fw4 { }"), payload_hash("table inet fw4 { }"))
        self.assertNotEqual(payload_hash("table inet fw4 { }"), payload_hash("table inet fw4 { }\n"))

    def test_unsupported_inventory_and_rollout_are_explicit(self):
        ids = {item["id"] for item in self.fixture["unsupported_blockers"]}
        for required in {"BC-01", "BC-07", "BC-04", "FIXTURE_ONLY_REDIRECT", "LEGACY_BACKEND", "MIHOMO_OWNER", "UNKNOWN_VERSION", "FOREIGN_COLLISION"}:
            self.assertIn(required, ids)
        rollout = self.fixture["rollout"]["recommended_order"]
        self.assertEqual(rollout[0], "PRODUCTION_SHELL_RENDERER_FIRST")
        self.assertEqual(self.fixture["rollout"]["central_default"], "OFF")

    def test_all_behavior_change_guards_are_frozen(self):
        records = self.fixture["behavior_change_guards"]
        self.assertEqual({item["id"] for item in records}, {"BC-01", "BC-02", "BC-03", "BC-04", "BC-05", "BC-06", "BC-07"})
        statuses = {item["id"]: item["status"] for item in records}
        self.assertEqual(statuses["BC-02"], "BASELINE_CORRECTION")
        for key in ("BC-01", "BC-03", "BC-04", "BC-05", "BC-06", "BC-07"):
            self.assertEqual(statuses[key], "NOT_APPROVED")
        for item in records:
            self.assertTrue(item["central_guard"])

    def test_backend_and_dns_boundaries_are_declared(self):
        contract = self.fixture["backend_execution_contract"]
        self.assertIn("listener_ports", contract["inputs"])
        self.assertEqual(contract["actions"]["REDIRECT_UDP"], "UNSUPPORTED_ACTION; never silently downgrade")
        dns = self.fixture["dns_boundary"]
        self.assertIn("dstnat", dns["lan"])
        self.assertIn("nat_output", dns["router"])
        self.assertIn("mangle migration", dns["hook_migration"])

    def test_model_is_pure_development_code(self):
        tree = ast.parse(MODEL.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
            if node.module
        )
        self.assertNotIn("subprocess", imported)
        self.assertNotIn("socket", imported)
        self.assertNotIn("openkill_network", imported)
        source = MODEL.read_text(encoding="utf-8").lower()
        for forbidden in ("nft -f", "nft add", "nft flush", "uci", "ubus"):
            self.assertNotIn(forbidden, source)

    def test_runtime_impact_is_zero_in_fixture(self):
        impact = self.fixture["runtime_impact"]
        self.assertTrue(all(value == "NO" for value in impact.values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
