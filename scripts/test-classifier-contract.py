#!/usr/bin/env python3
"""Executable Phase 2B shared-classifier model and contract tests.

The tests load only an in-memory fixture and the development oracle.  They do
not load the OpenWrt init script, execute a backend, or connect to a device.
"""

import copy
import collections
import json
import os
import pathlib
import re
import tempfile
import unittest

from openkill_classifier_model import (
    CLASSIFIER_CONTRACT_VERSION,
    CURRENT_PRECEDENCE,
    DECISIONS,
    MATCH_REASONS,
    PACKET_CONTEXT_DIMENSIONS,
    PROFILE_VALUES,
    STATUS_VALUES,
    TARGET_PRECEDENCE,
    ContextValidationError,
    FixtureValidationError,
    backend_action,
    classify,
    classify_current,
    classify_target,
    detect_matches,
    validate_context,
    validate_fixture,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "scripts/fixtures/openkill-classifier-semantic-v1.json"
MODEL = ROOT / "scripts/openkill_classifier_model.py"
PRODUCTION_FILES = (
    ROOT / "luci-app-openkill/root/etc/init.d/openkill",
    ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_network.sh",
    ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_watchdog.sh",
)

OVERLAP_REASON_ALIASES = {
    "OWNER": "OWNER_DISABLED",
    "DNS": "DNS",
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
}
FAMILY_SPECIFIC_PAIRS = {"control_nd", "control_errors", "control_dhcpv6", "ula", "tun"}


def load_fixture():
    with FIXTURE.open(encoding="utf-8") as handle:
        return json.load(handle)


def compact(result):
    return result.as_dict()


def context_for(*flags, family="IPv4", direction="LAN_INGRESS", protocol="TCP", owner="OPENKILL", **extra):
    context = {
        "family": family,
        "direction": direction,
        "protocol": protocol,
        "owner": owner,
        "backend_mode": "TUN",
        "flags": list(flags),
    }
    context.update(extra)
    return context


class ClassifierContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture()
        cls.cases = cls.fixture["cases"]
        validate_fixture(cls.fixture)

    def test_fixture_schema_and_mutation_guards(self):
        self.assertEqual(self.fixture["schema"], "CLASSIFIER_SEMANTIC_CONTRACT_V1")
        self.assertEqual(self.fixture["contract_version"], CLASSIFIER_CONTRACT_VERSION)
        self.assertEqual(tuple(self.fixture["profile_enum"]), PROFILE_VALUES)
        self.assertEqual(self.fixture["runtime_wiring"], "NONE")

        duplicate = copy.deepcopy(self.fixture)
        duplicate["cases"].append(copy.deepcopy(duplicate["cases"][0]))
        with self.assertRaises(FixtureValidationError):
            validate_fixture(duplicate)

        unknown = copy.deepcopy(self.fixture)
        unknown["cases"][0]["expected_target"]["reason"] = "NOT_A_REASON"
        with self.assertRaises(FixtureValidationError):
            validate_fixture(unknown)

        version = copy.deepcopy(self.fixture)
        version["contract_version"] = 99
        with self.assertRaises(FixtureValidationError):
            validate_fixture(version)

    def test_enums_and_context_dimensions_are_explicit(self):
        self.assertEqual(tuple(self.fixture["decision_enum"]), DECISIONS)
        self.assertEqual(tuple(self.fixture["match_reason_enum"]), MATCH_REASONS)
        for key, values in PACKET_CONTEXT_DIMENSIONS.items():
            self.assertEqual(tuple(self.fixture["packet_context_dimensions"][key]), values)
        self.assertEqual(PROFILE_VALUES, ("current", "target"))
        for case in self.cases:
            for expected in (case["expected_current"], case["expected_target"]):
                self.assertIn(expected["status"], STATUS_VALUES)
                self.assertIn(expected["reason"], MATCH_REASONS)
                if expected["decision"] is not None:
                    self.assertIn(expected["decision"], DECISIONS)

    def _assert_golden_replay(self, profile):
        statuses = collections.Counter()
        for case in self.cases:
            with self.subTest(case=case["id"], profile=profile):
                result = classify(case, profile)
                self.assertEqual(compact(result), case["expected_" + profile])
                statuses[result.status] += 1
        if profile == "current":
            self.assertEqual(statuses, {"VALID": 89, "CURRENT_UNDEFINED": 7, "INVALID_CONFIGURATION": 1})
        else:
            self.assertEqual(statuses, {"VALID": 96, "INVALID_CONFIGURATION": 1})

    def test_current_golden_replay(self):
        self._assert_golden_replay("current")

    def test_target_golden_replay(self):
        self._assert_golden_replay("target")

    def test_shared_detector_reports_all_overlap_matches(self):
        overlap_cases = [case for case in self.cases if case["category"] == "OVERLAP"]
        self.assertEqual(len(overlap_cases), 32)
        changed = 0
        for case in overlap_cases:
            expected = {
                OVERLAP_REASON_ALIASES[item]
                for item in case.get("overlap", ())
                if item in OVERLAP_REASON_ALIASES
            }
            detected = set(detect_matches(case))
            self.assertTrue(expected.issubset(detected), (case["id"], expected, detected))
            for profile in PROFILE_VALUES:
                result = classify(case, profile, trace=True)
                trace_matches = {
                    item.split(":", 1)[1]
                    for item in result.trace
                    if item.startswith("MATCH:")
                }
                self.assertTrue(expected.issubset(trace_matches), (case["id"], profile, expected, result.trace))
                if result.status != "INVALID_CONFIGURATION":
                    self.assertIsNotNone(result.matched_rule)
                    self.assertIsInstance(result.precedence_index, int)
            if case["expected_current"] != case["expected_target"]:
                changed += 1
                self.assertNotEqual(
                    compact(classify(case, "current")), compact(classify(case, "target")), case["id"]
                )
        self.assertEqual(changed, 13)

    def test_selected_reason_and_precedence_are_machine_readable(self):
        for case in self.cases:
            for profile, table, expected_key in (
                ("current", CURRENT_PRECEDENCE, "expected_current"),
                ("target", TARGET_PRECEDENCE, "expected_target"),
            ):
                result = classify(case, profile, trace=True)
                expected = case[expected_key]
                if expected["status"] == "INVALID_CONFIGURATION":
                    self.assertIsNone(result.matched_rule)
                    self.assertIsNone(result.precedence_index)
                    continue
                self.assertIn(result.matched_rule, table)
                self.assertEqual(result.precedence_index, table.index(result.matched_rule))
                self.assertIn("SELECT:" + result.matched_rule, result.trace)
                self.assertIn("REASON:" + expected["reason"], result.trace)

    def test_required_coverage_and_parity_groups(self):
        categories = {case["category"] for case in self.cases}
        required = {
            "CONTROL", "SELF", "NODE", "LOCAL", "ACCESS", "USER_DIRECT",
            "CHINA", "USER_PROXY", "FAKEIP", "DEFAULT", "DNS", "OVERLAP",
            "IPv6_CONTROL",
        }
        self.assertTrue(required.issubset(categories))
        self.assertEqual(len(self.cases), 97)
        self.assertEqual(sum(case["category"] == "OVERLAP" for case in self.cases), 32)
        pairs = {}
        for case in self.cases:
            if case.get("parity_pair"):
                pairs.setdefault(case["parity_pair"], []).append(case)
        self.assertEqual(len(pairs), 31)
        self.assertTrue(all(len(group) >= 1 for group in pairs.values()))

    def test_parity_pairs_are_machine_enforced(self):
        pairs = {}
        for case in self.cases:
            if case.get("parity_pair"):
                pairs.setdefault(case["parity_pair"], []).append(case)
        for pair, group in pairs.items():
            with self.subTest(pair=pair):
                actual = {
                    profile: [compact(classify(case, profile)) for case in group]
                    for profile in PROFILE_VALUES
                }
                if pair not in FAMILY_SPECIFIC_PAIRS:
                    families = {case["family"] for case in group}
                    self.assertEqual(families, {"IPv4", "IPv6"})
                    by_family = {case["family"]: case for case in group}
                    for profile in PROFILE_VALUES:
                        expected_key = "expected_" + profile
                        v4_expected = by_family["IPv4"][expected_key]
                        v6_expected = by_family["IPv6"][expected_key]
                        self.assertEqual(v4_expected, v6_expected, (pair, profile))
                        self.assertEqual(
                            compact(classify(by_family["IPv4"], profile)), v4_expected
                        )
                        self.assertEqual(
                            compact(classify(by_family["IPv6"], profile)), v6_expected
                        )
                else:
                    if pair == "tun":
                        self.assertEqual({case["family"] for case in group}, {"IPv4", "IPv6"})
                    else:
                        self.assertTrue(all(case["family"] == "IPv6" for case in group) or pair == "ula")

    def test_precedence_tables_are_ordered_and_backend_free(self):
        for table, expected in ((self.fixture["current_precedence"], CURRENT_PRECEDENCE),
                                (self.fixture["target_precedence"], TARGET_PRECEDENCE)):
            def semantic_key(item):
                if item.endswith("_IPV6"):
                    item = item[:-5]
                if item.endswith("_CUSTOM"):
                    item = item[:-7]
                if item == "CHINA_PASS_FALLTHROUGH":
                    item = "CHINA_PASS"
                return item
            self.assertEqual(tuple(item["match_reason"] for item in table),
                             tuple(semantic_key(item) for item in expected))
            self.assertEqual([item["order"] for item in table], list(range(len(table))))
            for item in table:
                self.assertNotRegex(item["position"], r"\b(nft|iptables|ip6tables|mark set|tproxy)\b")

    def test_profile_and_input_validation_are_fail_closed(self):
        case = self.cases[0]
        with self.assertRaises(ValueError):
            classify(case)
        with self.assertRaises(ValueError):
            classify(case, "shadow")
        with self.assertRaises(ContextValidationError):
            classify(dict(case, family="IPv7"), "current")
        with self.assertRaises(ContextValidationError):
            classify(dict(case, direction="SIDEWAYS"), "current")
        with self.assertRaises(ContextValidationError):
            classify(dict(case, protocol="SCTP"), "current")
        with self.assertRaises(ContextValidationError):
            classify(dict(case, flags=["UNKNOWN_MATCH"]), "current")
        with self.assertRaises(ContextValidationError):
            classify(dict(case, destination_properties=["UNKNOWN_DESTINATION"]), "target")
        with self.assertRaises(ContextValidationError):
            classify(dict(case, family="IPv4", protocol="ICMPv6"), "target")

    def test_owner_dns_and_safety_invariants(self):
        for owner in ("MIHOMO", "DISABLED", "UNKNOWN"):
            result = classify(context_for("EXPLICIT_PROXY", owner=owner), "target")
            self.assertEqual(compact(result), {
                "reason": "OWNER_DISABLED", "decision": "NOT_OWNED", "status": "VALID"
            })

        dns = context_for("DNS", "FAKEIP", "EXPLICIT_PROXY", "CHINA_POLICY", china_policy="BYPASS_MAINLAND")
        for profile in PROFILE_VALUES:
            result = classify(dns, profile)
            self.assertEqual((result.reason, result.decision), ("DNS", "DNS_SPECIAL"))

        safety = (
            ("SELF_TRAFFIC", "IPv4"),
            ("TUN_INGRESS", "IPv4"),
            ("NODE_ENDPOINT", "IPv4"),
            ("LOCAL_DESTINATION", "IPv4"),
            ("REPLY_TRAFFIC", "IPv4"),
            ("CONTROL_PROTOCOL", "IPv6"),
        )
        for flag, family in safety:
            result = classify(context_for(flag, "EXPLICIT_PROXY", family=family), "target")
            self.assertEqual(result.decision, "BYPASS", (flag, result))
            self.assertNotEqual(result.decision, "PROXY")

        v6_tun = context_for("TUN_INGRESS", family="IPv6")
        self.assertEqual(classify(v6_tun, "current").reason, "DEFAULT_POLICY")
        self.assertEqual(classify(v6_tun, "current").decision, "PROXY")
        self.assertEqual(classify(v6_tun, "target").reason, "TUN_INGRESS")
        self.assertEqual(classify(v6_tun, "target").decision, "BYPASS")

        self.assertEqual(
            compact(classify(context_for("EXPLICIT_DIRECT", "EXPLICIT_PROXY"), "target")),
            {"reason": "INVALID_CONFIGURATION", "decision": None, "status": "INVALID_CONFIGURATION"},
        )

    def test_context_properties_are_semantic_inputs(self):
        context = context_for(
            family="IPv6",
            direction="ROUTER_OUTPUT",
            protocol="TCP",
            source_properties=["UNKNOWN", "SELF_PROCESS"],
            destination_properties=["PUBLIC", "NODE_ENDPOINT"],
            connection="NEW",
        )
        result = classify(context, "target", trace=True)
        self.assertEqual(result.reason, "SELF_TRAFFIC")
        self.assertEqual(result.decision, "BYPASS")
        self.assertIn("MATCH:SELF_TRAFFIC", result.trace)
        self.assertIn("MATCH:NODE_ENDPOINT", result.trace)

    def test_trace_and_input_order_determinism(self):
        base = context_for("CHINA_POLICY", "EXPLICIT_PROXY", "LOCAL_DESTINATION", china_policy="BYPASS_MAINLAND")
        reordered = dict(reversed(list(base.items())))
        reordered["flags"] = list(reversed(base["flags"]))
        first = classify(base, "target", trace=True)
        second = classify(reordered, "target", trace=True)
        self.assertEqual(first.to_record(), second.to_record())
        self.assertEqual(detect_matches(base), detect_matches(reordered))

    def test_backend_action_mapping_is_separate_and_explicit(self):
        self.assertEqual(backend_action("PROXY", "TUN", "TCP"), "MARK")
        self.assertEqual(backend_action("PROXY", "TPROXY", "UDP"), "MARK_TPROXY")
        self.assertEqual(backend_action("PROXY", "REDIRECT", "TCP"), "REDIRECT")
        self.assertEqual(backend_action("PROXY", "REDIRECT", "UDP"), "UNSUPPORTED_ACTION")
        self.assertEqual(backend_action("BYPASS", "TUN", "TCP"), "NATIVE_RETURN")
        self.assertEqual(backend_action("DNS_SPECIAL", "TUN", "UDP"), "DNS_REDIRECT")
        self.assertEqual(backend_action("ACCESS_DENY", "TUN", "TCP"), "ACCESS_DENY_REQUIRED")
        self.assertEqual(backend_action("NOT_OWNED", "TUN", "TCP"), "NOT_OWNED")
        with self.assertRaises(ValueError):
            backend_action("NFT_RETURN", "TUN", "TCP")

    def test_side_effect_free_and_backend_free(self):
        original_cwd = os.getcwd()
        original_env = dict(os.environ)
        with tempfile.TemporaryDirectory() as temporary:
            before = sorted(pathlib.Path(temporary).iterdir())
            case = self.cases[0]
            for _ in range(100):
                classify(case, "target", trace=True)
                detect_matches(case)
            self.assertEqual(before, sorted(pathlib.Path(temporary).iterdir()))
        self.assertEqual(original_cwd, os.getcwd())
        self.assertEqual(original_env, dict(os.environ))
        source = MODEL.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"(?m)^\s*(import|from)\s+(subprocess|socket)\b")
        self.assertNotRegex(source, r"\b(os\.system|Popen|check_output|run)\s*\(")
        self.assertNotRegex(source, r"(?m)^\s*(import|from)\s+os\b")
        self.assertNotRegex(source, r"(?m)^\s*open\s*\(")

    def test_production_wiring_is_unchanged(self):
        for path in PRODUCTION_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("openkill_classifier_model", text)
            self.assertNotIn("openkill-classifier-semantic-v1", text)

    def test_contract_source_is_shared_not_two_classifier_implementations(self):
        source = MODEL.read_text(encoding="utf-8")
        self.assertIn("_match_reasons", source)
        self.assertIn("_rule_matches", source)
        self.assertIn("CURRENT_PRECEDENCE", source)
        self.assertIn("TARGET_PRECEDENCE", source)
        # The public profile functions delegate to one resolver.
        self.assertGreaterEqual(len(re.findall(r"return _classify\(raw,", source)), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
