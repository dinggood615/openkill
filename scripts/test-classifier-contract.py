#!/usr/bin/env python3
"""Executable Phase 2A contract/golden tests.

The fixture is an oracle for semantic classification only.  This test never
loads or executes the OpenKill init script and never touches a device.
"""

import json
import pathlib
import unittest

from openkill_classifier_model import (
    CURRENT_PRECEDENCE,
    DECISIONS,
    MATCH_REASONS,
    PACKET_CONTEXT_DIMENSIONS,
    STATUS_VALUES,
    TARGET_PRECEDENCE,
    backend_action,
    classify_current,
    classify_target,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "scripts/fixtures/openkill-classifier-semantic-v1.json"
PRODUCTION_FILES = (
    ROOT / "luci-app-openkill/root/etc/init.d/openkill",
    ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_network.sh",
    ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_watchdog.sh",
)


def load_fixture():
    with FIXTURE.open(encoding="utf-8") as handle:
        return json.load(handle)


def result_dict(result):
    return result.as_dict()


class ClassifierContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture()
        cls.cases = cls.fixture["cases"]

    def test_fixture_is_versioned_and_model_only(self):
        self.assertEqual(self.fixture["schema"], "CLASSIFIER_SEMANTIC_CONTRACT_V1")
        self.assertEqual(self.fixture["runtime_wiring"], "NONE")

    def test_enums_and_context_dimensions_are_explicit(self):
        self.assertEqual(tuple(self.fixture["decision_enum"]), DECISIONS)
        self.assertEqual(tuple(self.fixture["match_reason_enum"]), MATCH_REASONS)
        for key, values in PACKET_CONTEXT_DIMENSIONS.items():
            self.assertEqual(tuple(self.fixture["packet_context_dimensions"][key]), values)
        for case in self.cases:
            for expected in (case["expected_current"], case["expected_target"]):
                self.assertIn(expected["status"], STATUS_VALUES)
                self.assertIn(expected["reason"], MATCH_REASONS)
                if expected["decision"] is not None:
                    self.assertIn(expected["decision"], DECISIONS)

    def test_current_and_target_goldens(self):
        for case in self.cases:
            with self.subTest(case=case["id"], profile="current"):
                self.assertEqual(result_dict(classify_current(case)), case["expected_current"])
            with self.subTest(case=case["id"], profile="target"):
                self.assertEqual(result_dict(classify_target(case)), case["expected_target"])

    def test_required_coverage(self):
        categories = {case["category"] for case in self.cases}
        required = {
            "CONTROL", "SELF", "NODE", "LOCAL", "ACCESS", "USER_DIRECT",
            "CHINA", "USER_PROXY", "FAKEIP", "DEFAULT", "DNS", "OVERLAP",
            "IPv6_CONTROL",
        }
        self.assertTrue(required.issubset(categories))
        self.assertGreaterEqual(len(self.cases), 40)
        self.assertGreaterEqual(sum(case["category"] == "OVERLAP" for case in self.cases), 12)
        pairs = {case["parity_pair"] for case in self.cases if case.get("parity_pair")}
        self.assertGreaterEqual(len(pairs), 15)

    def test_overlap_decisions_are_explicit(self):
        by_id = {case["id"]: case for case in self.cases}
        # These are deliberate contract points, not implicit ordering guesses.
        self.assertEqual(by_id["overlap_user_proxy_china_v4"]["expected_current"]["decision"], "DIRECT")
        self.assertEqual(by_id["overlap_user_proxy_china_v4"]["expected_target"]["decision"], "PROXY")
        self.assertEqual(by_id["overlap_fakeip_user_direct_v4"]["expected_target"]["reason"], "FAKEIP")
        self.assertEqual(by_id["overlap_user_direct_proxy_invalid_v4"]["expected_target"]["status"], "INVALID_CONFIGURATION")
        self.assertEqual(by_id["overlap_node_self_v4"]["expected_current"]["reason"], "NODE_ENDPOINT")
        self.assertEqual(by_id["overlap_node_self_v4"]["expected_target"]["reason"], "SELF_TRAFFIC")

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
                # Backend syntax belongs to Phase 2B/3, never in this table.
                self.assertNotRegex(item["position"], r"\b(nft|iptables|ip6tables|mark set|tproxy)\b")

    def test_backend_action_mapping_is_abstract(self):
        self.assertEqual(backend_action("PROXY", "TUN", "TCP"), "MARK")
        self.assertEqual(backend_action("PROXY", "TPROXY", "UDP"), "MARK_TPROXY")
        self.assertEqual(backend_action("PROXY", "REDIRECT", "TCP"), "REDIRECT")
        self.assertEqual(backend_action("BYPASS", "TUN", "TCP"), "NATIVE_RETURN")
        self.assertEqual(backend_action("DNS_SPECIAL", "TUN", "UDP"), "DNS_REDIRECT")
        self.assertEqual(backend_action("ACCESS_DENY", "TUN", "TCP"), "REJECT")

    def test_production_wiring_is_unchanged(self):
        for path in PRODUCTION_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("openkill_classifier_model", text)
            self.assertNotIn("openkill-classifier-semantic-v1", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
