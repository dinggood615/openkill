#!/usr/bin/env python3
"""Focused D2B ownership and typed DNS model regressions.

Everything in this test is a sanitized, in-process mapping.  It deliberately
does not invoke SSH, nft, UCI, a device, the legacy writer, or the D2A
coordinator.
"""

from __future__ import annotations

import copy
import json
import pathlib
import unittest

from openkill_shadow_semantic_model import (
    COMPONENTS,
    DNS_FIELDS,
    SemanticModelError,
    build_dns_semantic_intent,
    build_semantic_projection,
    classify_object_ownership,
    compare_dns_semantics,
    compare_semantic_intents,
)
from openkill_production_shadow import compare_current_semantic_intents


ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "scripts/fixtures/openkill-shadow-semantic-v1.json"


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def simple_intent(*, extra_wan: bool = False, owned_action: str = "RETURN"):
    chains = [
        {
            "logical_id": "CURRENT_LOCAL_CHAIN",
            "physical_name": "openkill_local",
            "owner": "OPENKILL",
            "ownership": "OWNED",
            "component": "LOCAL",
            "family": "IPv4",
        }
    ]
    if extra_wan:
        chains.append(
            {
                "logical_id": "LEGACY_WAN_INPUT_V4",
                "physical_name": "openkill_wan_input",
                "owner": "OPENKILL",
                "component": "WAN_INPUT",
                "role": "WAN_INPUT",
                "family": "IPv4",
            }
        )
    return {
        "schema": "OPENKILL_TEST_INTENT_V1",
        "chains": chains,
        "sets": [],
        "attachments": [],
        "rules": [
            {
                "logical_id": "CURRENT_LOCAL_RULE",
                "physical_name": "recorded_rule" if owned_action == "RETURN" else "changed_rule",
                "owner": "OPENKILL",
                "ownership": "OWNED",
                "component": "LOCAL",
                "family": "IPv4",
                "chain": "openkill_local",
                "match_expression": "meta nfproto ipv4",
                "action_type": owned_action,
                "action_expression": owned_action.lower(),
                "semantic_reason": "LOCAL",
                "action": owned_action,
            }
        ],
    }


def full_dns(*, firewall_lan=53, firewall_router=53, upstream="127.0.0.1#7874", mihomo="127.0.0.1:7874"):
    values = {
        "DNS_FIREWALL_LAN_TARGET": firewall_lan,
        "DNS_FIREWALL_ROUTER_TARGET": firewall_router,
        "DNSMASQ_LISTEN_TARGET": 53,
        "DNSMASQ_UPSTREAM_TARGET": upstream,
        "MIHOMO_DNS_LISTENER": mihomo,
        "DNS_LOOP_PREVENTION": {"skgid_exempt": 65534},
        "DNS_SCOPE_IPV4": {"lan": True, "router": True},
        "DNS_SCOPE_IPV6": {"lan": True, "router": True},
    }
    ownership = {field: "CURRENT_OWNED" for field in DNS_FIELDS}
    return build_dns_semantic_intent(
        {
            "dns_semantics": values,
            "field_ownership": ownership,
            "sources": {field: "sanitized committed source" for field in DNS_FIELDS},
        }
    )


class SemanticModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture()
        cls.inventory = cls.fixture["formal_inventory"]

    def test_public_contract_and_component_catalog(self):
        self.assertEqual(len(COMPONENTS), 11)
        self.assertIn("WAN_SAFETY", COMPONENTS)
        self.assertIn("DNSMASQ_UPSTREAM_TARGET", DNS_FIELDS)
        self.assertEqual(
            classify_object_ownership(
                {"component": "WAN_INPUT", "role": "WAN_INPUT", "owner": "OPENKILL"}
            ),
            "LEGACY_ONLY_SAFETY",
        )
        self.assertEqual(
            classify_object_ownership({"ownership_class": "REQUIRED_CURRENT"}),
            "CURRENT_OWNED",
        )
        with self.assertRaises(SemanticModelError):
            classify_object_ownership({"owner": "OPENKILL", "ownership_class": "NOT_A_CLASS"})

    def test_out_of_scope_actual_only_is_observed_without_owned_mismatch(self):
        actual = simple_intent(extra_wan=True)
        desired = simple_intent()
        report = compare_semantic_intents(actual, desired, formal_inventory=self.inventory)
        self.assertEqual(report["framework"], "PASS")
        self.assertEqual(report["parity"], "MATCH")
        self.assertEqual(report["actual_owned_hash"], report["desired_owned_hash"])
        observations = report["out_of_scope_observations"]
        self.assertTrue(any(item["component"] == "WAN_SAFETY" and item["observation_retained"] for item in observations))
        self.assertEqual(report["components"]["WAN_SAFETY"]["result"], "OUT_OF_SCOPE_LEGACY_OBJECT")

        physical_only = simple_intent()
        physical_only["chains"].append(
            {"physical_name": "openkill_wan_input", "name": "openkill_wan_input", "family": "IPv4"}
        )
        report = compare_semantic_intents(physical_only, desired, formal_inventory=self.inventory)
        self.assertEqual(report["parity"], "MATCH")
        self.assertTrue(any(item["component"] == "WAN_SAFETY" for item in report["out_of_scope_observations"]))

        current_physical_only = simple_intent()
        current_physical_only["chains"][0].pop("logical_id")
        report = compare_semantic_intents(current_physical_only, desired, formal_inventory=self.inventory)
        self.assertEqual(report["parity"], "MATCH")

    def test_out_of_scope_absence_is_retained_as_absent(self):
        report = compare_semantic_intents(simple_intent(), simple_intent(), formal_inventory=self.inventory)
        wan = [item for item in report["out_of_scope_observations"] if item["component"] == "WAN_SAFETY"]
        self.assertTrue(wan)
        self.assertTrue(all(item["observation_status"] == "ABSENT" and not item["actual_present"] for item in wan))
        self.assertEqual(report["parity"], "MATCH")

    def test_owned_extra_and_owned_missing_are_mismatches(self):
        actual = simple_intent()
        desired = simple_intent()
        actual["chains"].append(
            {
                "logical_id": "CURRENT_EXTRA",
                "physical_name": "openkill_extra",
                "owner": "OPENKILL",
                "ownership": "OWNED",
                "component": "LOCAL",
            }
        )
        report = compare_semantic_intents(actual, desired)
        self.assertEqual(report["parity"], "MISMATCH")
        self.assertTrue(any(item["component"] == "LOCAL" for item in report["mismatches"]))
        desired["chains"].append(copy.deepcopy(actual["chains"][-1]))
        desired["chains"][-1]["physical_name"] = "changed_name"
        report = compare_semantic_intents(actual, desired)
        self.assertEqual(report["parity"], "MISMATCH")

    def test_approved_current_gap_remains_explicit(self):
        actual = simple_intent()
        desired = simple_intent()
        actual["rules"][0]["component"] = "TUN"
        desired["rules"][0]["component"] = "TUN"
        actual["rules"][0]["known_gap"] = "BC-04"
        desired["rules"][0]["known_gap"] = "BC-04"
        actual["rules"][0]["action"] = "MARK"
        desired["rules"][0]["action"] = "RETURN"
        report = compare_semantic_intents(actual, desired)
        self.assertEqual(report["framework"], "PASS")
        self.assertEqual(report["parity"], "KNOWN_CURRENT_GAP")
        self.assertEqual(report["components"]["TUN"]["result"], "KNOWN_CURRENT_GAP")
        self.assertEqual(report["known_gaps"][0]["id"], "BC-04")

    def test_unknown_ownership_is_a_model_gap(self):
        actual = simple_intent()
        desired = simple_intent()
        actual["chains"].append(
            {"logical_id": "UNKNOWN_EXTRA", "physical_name": "mystery_object", "component": "LOCAL"}
        )
        report = compare_semantic_intents(actual, desired)
        self.assertEqual(report["parity"], "MODEL_GAP")
        self.assertTrue(any(item["type"] == "UNKNOWN_OWNERSHIP" for item in report["model_gaps"]))
        absent = {"chains": [], "sets": [], "attachments": [], "rules": []}
        report = compare_semantic_intents(
            absent,
            absent,
            formal_inventory=[{"logical_id": "MYSTERY", "physical_name": "mystery", "ownership_class": "UNKNOWN"}],
        )
        self.assertEqual(report["parity"], "MODEL_GAP")

    def test_unsupported_object_is_not_downgraded_to_match(self):
        actual = simple_intent()
        actual["rules"].append(
            {
                "logical_id": "UNSUPPORTED_RULE",
                "physical_name": "unsupported_rule",
                "owner": "OPENKILL",
                "ownership": "OWNED",
                "component": "BACKEND",
                "status": "UNSUPPORTED",
            }
        )
        report = compare_semantic_intents(actual, simple_intent())
        self.assertEqual(report["parity"], "MODEL_GAP")
        self.assertTrue(any(item["type"] == "UNSUPPORTED_OBJECT" for item in report["model_gaps"]))

    def test_conditional_active_and_inactive_modes(self):
        conditional = {
            "logical_id": "TPROXY_ONLY_RULE",
            "physical_name": "openkill_tproxy_only",
            "component": "BACKEND",
            "ownership_class": "CONDITIONAL_CURRENT",
            "active_modes": ["TPROXY"],
            "required_modes": ["TPROXY"],
        }
        desired = {"chains": [conditional], "sets": [], "attachments": [], "rules": []}
        self.assertEqual(build_semantic_projection(desired, mode="TUN")["entries"][0]["ownership"], "INACTIVE_MODE")
        actual = {"chains": [], "sets": [], "attachments": [], "rules": []}
        report = compare_semantic_intents(actual, desired, mode="TPROXY")
        self.assertEqual(report["parity"], "MISMATCH")
        report = compare_semantic_intents(actual, desired, mode="TUN")
        self.assertEqual(report["parity"], "MATCH")

        # Mode metadata can live only in the formal inventory, as it does for
        # a bounded capture that carries an object identity but no policy
        # annotations.  TPROXY must still treat the conditional object as
        # required and fail closed when it is absent on both sides.
        inventory_only = [dict(conditional)]
        absent = {"chains": [], "sets": [], "attachments": [], "rules": []}
        report = compare_semantic_intents(absent, absent, mode="TPROXY", formal_inventory=inventory_only)
        self.assertEqual(report["parity"], "MISMATCH")
        report = compare_semantic_intents(absent, absent, mode="TUN", formal_inventory=inventory_only)
        self.assertEqual(report["parity"], "MATCH")

    def test_formal_inventory_mapping_and_conflict_are_fail_closed(self):
        desired = simple_intent()
        metadata = {
            "CURRENT_LOCAL_CHAIN": {
                "logical_id": "CURRENT_LOCAL_CHAIN",
                "physical_name": "openkill_local",
                "component": "LOCAL",
                "ownership_class": "CURRENT_OWNED",
            }
        }
        report = compare_semantic_intents(desired, desired, formal_inventory=metadata)
        self.assertEqual(report["parity"], "MATCH")
        conflict = [
            metadata["CURRENT_LOCAL_CHAIN"],
            {**metadata["CURRENT_LOCAL_CHAIN"], "component": "WAN_INPUT"},
        ]
        with self.assertRaises(SemanticModelError):
            compare_semantic_intents(desired, desired, formal_inventory=conflict)

    def test_duplicate_identity_is_fail_closed_and_order_independent(self):
        actual = simple_intent()
        actual["chains"].append(copy.deepcopy(actual["chains"][0]))
        report = compare_semantic_intents(actual, simple_intent())
        self.assertEqual(report["parity"], "MODEL_GAP")
        reordered = copy.deepcopy(actual)
        reordered["chains"].reverse()
        self.assertEqual(
            compare_semantic_intents(reordered, simple_intent())["parity"],
            "MODEL_GAP",
        )

    def test_typed_dns_match_and_no_53_7874_equivalence(self):
        actual = full_dns()
        desired = full_dns()
        report = compare_dns_semantics(actual, desired)
        self.assertEqual(report["parity"], "MATCH")
        self.assertFalse(report["dns_53_7874_direct_equivalence"])
        self.assertEqual(report["fields"][0]["actual_ownership"], "CURRENT_OWNED")

    def test_dns_targets_are_independent_fields(self):
        actual = full_dns()
        desired = full_dns(firewall_lan=54)
        report = compare_dns_semantics(actual, desired)
        self.assertEqual(report["parity"], "MISMATCH")
        self.assertEqual([item["field"] for item in report["mismatches"]], ["DNS_FIREWALL_LAN_TARGET"])
        desired = full_dns(upstream="127.0.0.1#7875")
        report = compare_dns_semantics(actual, desired)
        self.assertEqual(report["parity"], "MISMATCH")
        desired = full_dns(mihomo="127.0.0.1:7875")
        self.assertEqual(compare_dns_semantics(actual, desired)["parity"], "MISMATCH")
        desired = full_dns(firewall_lan=7874)
        self.assertEqual(compare_dns_semantics(actual, desired)["parity"], "MISMATCH")

        report = compare_semantic_intents(
            simple_intent(),
            simple_intent(),
            dns_actual=actual,
            dns_desired=desired,
        )
        self.assertNotEqual(report["actual_current_owned_hash"], report["desired_current_owned_hash"])

    def test_dns_scope_and_skgid_are_independent_typed_fields(self):
        actual = full_dns()
        desired = full_dns()
        desired["fields"]["DNS_FIREWALL_ROUTER_TARGET"]["value"] = "54"
        report = compare_dns_semantics(actual, desired)
        self.assertEqual(
            [item["field"] for item in report["mismatches"]],
            ["DNS_FIREWALL_ROUTER_TARGET"],
        )

        desired = full_dns()
        desired["fields"]["DNS_SCOPE_IPV6"]["value"] = {"lan": False, "router": True}
        self.assertEqual(compare_dns_semantics(actual, desired)["parity"], "MISMATCH")

        # A formally legacy-only loop-prevention implementation detail remains
        # observable but is outside CURRENT-owned equality on both sides.
        actual = full_dns()
        desired = full_dns()
        actual["fields"]["DNS_LOOP_PREVENTION"]["ownership"] = "LEGACY_ONLY_SAFETY"
        desired["fields"]["DNS_LOOP_PREVENTION"]["ownership"] = "LEGACY_ONLY_SAFETY"
        report = compare_dns_semantics(actual, desired)
        self.assertEqual(report["parity"], "MATCH")
        loop = next(item for item in report["fields"] if item["field"] == "DNS_LOOP_PREVENTION")
        self.assertFalse(loop["comparable"])

    def test_dns_ownership_disagreement_is_a_model_gap(self):
        actual = full_dns()
        desired = full_dns()
        desired["fields"]["DNSMASQ_UPSTREAM_TARGET"]["ownership"] = "UNKNOWN"
        self.assertEqual(compare_dns_semantics(actual, desired)["parity"], "COMPARATOR_MODEL_GAP")

    def test_dns_missing_evidence_and_invalid_values_fail_closed(self):
        actual = full_dns()
        desired = full_dns()
        desired["fields"]["DNSMASQ_UPSTREAM_TARGET"]["value"] = None
        desired["fields"]["DNSMASQ_UPSTREAM_TARGET"]["evidence"] = "MISSING"
        self.assertEqual(compare_dns_semantics(actual, desired)["parity"], "INSUFFICIENT_EVIDENCE")
        with self.assertRaises(SemanticModelError):
            build_dns_semantic_intent({"DNS_FIREWALL_LAN_TARGET": "53x"})
        with self.assertRaises(SemanticModelError):
            build_dns_semantic_intent({"DNSMASQ_UPSTREAM_TARGET": "127.0.0.1#0"})

        desired_without_source = copy.deepcopy(desired)
        desired_without_source["fields"]["DNS_FIREWALL_LAN_TARGET"]["source"] = None
        self.assertEqual(compare_dns_semantics(actual, desired_without_source)["parity"], "COMPARATOR_MODEL_GAP")
        actual_without_source = copy.deepcopy(actual)
        actual_without_source["fields"]["DNS_FIREWALL_LAN_TARGET"]["source"] = None
        self.assertEqual(compare_dns_semantics(actual_without_source, desired)["parity"], "INSUFFICIENT_EVIDENCE")
        invalid_normalized = copy.deepcopy(actual)
        invalid_normalized["fields"]["DNS_FIREWALL_LAN_TARGET"]["value"] = "53x"
        with self.assertRaises(SemanticModelError):
            compare_dns_semantics(invalid_normalized, desired)

    def test_dns_sources_are_not_inferred_from_renderer_port(self):
        renderer_only = build_dns_semantic_intent(
            {"dns_semantics": {"DNS_FIREWALL_LAN_TARGET": 53, "dns_port": 7874}}
        )
        self.assertIsNone(renderer_only["fields"]["DNSMASQ_UPSTREAM_TARGET"]["value"])
        self.assertEqual(renderer_only["fields"]["DNSMASQ_UPSTREAM_TARGET"]["ownership"], "UNKNOWN")

    def test_dns_field_local_source_and_ipv6_listener_are_canonicalized(self):
        source = build_dns_semantic_intent(
            {
                "fields": {
                    "MIHOMO_DNS_LISTENER": {
                        "value": "[2001:db8::1]:7874",
                        "source": "committed Mihomo state",
                        "ownership": "CURRENT_OWNED",
                    }
                }
            }
        )
        field = source["fields"]["MIHOMO_DNS_LISTENER"]
        self.assertEqual(field["value"], "[2001:db8::1]:7874")
        self.assertEqual(field["source"], "committed Mihomo state")

    def test_projection_hash_isolates_out_of_scope_observation(self):
        desired = simple_intent()
        base = compare_semantic_intents(simple_intent(), desired, formal_inventory=self.inventory)
        extra = compare_semantic_intents(simple_intent(extra_wan=True), desired, formal_inventory=self.inventory)
        self.assertNotEqual(base["actual_observation_hash"], extra["actual_observation_hash"])
        self.assertEqual(base["actual_owned_hash"], extra["actual_owned_hash"])
        changed_scope = simple_intent(extra_wan=True)
        changed_scope["chains"][-1]["action"] = "DROP"
        changed_scope_report = compare_semantic_intents(changed_scope, desired, formal_inventory=self.inventory)
        self.assertNotEqual(extra["actual_observation_hash"], changed_scope_report["actual_observation_hash"])
        self.assertEqual(extra["actual_owned_hash"], changed_scope_report["actual_owned_hash"])
        changed = simple_intent(owned_action="DROP")
        changed_hash = compare_semantic_intents(changed, desired)["actual_owned_hash"]
        self.assertNotEqual(base["actual_owned_hash"], changed_hash)

    def test_frozen_102_fixture_is_deterministic_and_component_attributed(self):
        f = self.fixture
        self.assertEqual(f["frozen_device_evidence"]["bounded_capture"]["chain_probes"], 25)
        self.assertEqual(f["frozen_device_evidence"]["bounded_capture"]["set_probes"], 23)
        self.assertEqual(f["frozen_device_evidence"]["bounded_capture"]["required_current_missing"], 0)
        self.assertEqual(f["frozen_device_evidence"]["bounded_capture"]["conditional_or_inventory_missing"], 24)
        self.assertEqual(
            f["frozen_device_evidence"]["dns_previous_desired_firewall"],
            {"lan": 7874, "router": 7874},
        )
        self.assertEqual(
            f["frozen_device_evidence"]["dns_reconciled_architecture"],
            "LEGACY_53_PATH_IS_CURRENT_CONTRACT",
        )
        first = compare_semantic_intents(
            f["actual_intent"],
            f["desired_intent"],
            mode=f["mode"],
            formal_inventory=f["formal_inventory"],
            dns_actual=f["dns_actual"],
            dns_desired=f["dns_desired"],
        )
        self.assertEqual(first["framework"], "PASS")
        self.assertEqual(first["parity"], "MATCH")
        self.assertTrue(any(item["component"] == "WAN_SAFETY" for item in first["out_of_scope_observations"]))
        self.assertEqual(first["dns"]["parity"], "MATCH")
        self.assertEqual(first["dns"]["mismatches"], [])
        second = compare_semantic_intents(
            f["actual_intent"],
            f["desired_intent"],
            mode=f["mode"],
            formal_inventory=f["formal_inventory"],
            dns_actual=f["dns_actual"],
            dns_desired=f["dns_desired"],
        )
        self.assertEqual(first["actual_owned_hash"], second["actual_owned_hash"])
        self.assertEqual(first["desired_owned_hash"], second["desired_owned_hash"])

    def test_frozen_fixture_ten_stable_cycles_after_dns_reconciliation(self):
        f = self.fixture
        reports = [
            compare_semantic_intents(
                f["actual_intent"],
                f["desired_intent"],
                mode=f["mode"],
                formal_inventory=f["formal_inventory"],
                dns_actual=f["dns_actual"],
                dns_desired=f["dns_desired"],
            )
            for _ in range(10)
        ]
        self.assertEqual({item["parity"] for item in reports}, {"MATCH"})
        self.assertEqual({item["actual_owned_hash"] for item in reports}, {reports[0]["actual_owned_hash"]})
        self.assertEqual({item["desired_owned_hash"] for item in reports}, {reports[0]["desired_owned_hash"]})
        self.assertEqual({item["actual_current_owned_hash"] for item in reports}, {reports[0]["actual_current_owned_hash"]})
        self.assertEqual({item["desired_current_owned_hash"] for item in reports}, {reports[0]["desired_current_owned_hash"]})
        self.assertEqual(reports[0]["actual_current_owned_hash"], reports[0]["desired_current_owned_hash"])

    def test_production_shadow_adapter_exposes_same_model(self):
        f = self.fixture
        kwargs = {
            "mode": f["mode"],
            "formal_inventory": f["formal_inventory"],
            "dns_actual": f["dns_actual"],
            "dns_desired": f["dns_desired"],
        }
        direct = compare_semantic_intents(f["actual_intent"], f["desired_intent"], **kwargs)
        through_shadow = compare_current_semantic_intents(f["actual_intent"], f["desired_intent"], **kwargs)
        self.assertEqual(through_shadow["parity"], direct["parity"])
        self.assertEqual(through_shadow["actual_owned_hash"], direct["actual_owned_hash"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
