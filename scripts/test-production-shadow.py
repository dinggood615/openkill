#!/usr/bin/env python3
"""Phase 3C local comparison of current production firewall intent.

The old side is captured by executing exact checked-out shell function bodies
inside a record-only Bash sandbox.  The new side is the development NFT IR
renderer.  No command recorded by the old side is executed, and this test
never connects to an OpenWrt device.
"""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import shutil
import tempfile
import unittest
from collections import Counter

from openkill_nft_ir import render_context
from openkill_nft_syntax import lower_nft_ir, render_nft
from openkill_shadow_adapter import adapt, normalize_state, validate_intent_fixture, validate_state_fixture
from openkill_production_shadow import (
    COMMAND_ALLOWLIST,
    MISMATCH_CLASSES,
    audit_tproxy_router_self,
    build_production_scenarios,
    coverage_summary,
    dns_scope_audit,
    normalize_new_context_intent,
    parse_nft_command_records,
    production_function_hashes,
    run_production_harness,
    run_shadow_comparison,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_FIXTURE = ROOT / "scripts/fixtures/openkill-shadow-states-v1.json"
INTENT_FIXTURE = ROOT / "scripts/fixtures/openkill-current-firewall-intent-v1.json"
PRODUCTION_FILES = {
    "luci-app-openkill/root/etc/init.d/openkill",
    "luci-app-openkill/root/usr/share/openkill/openkill_network.sh",
}


def load(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


class ProductionShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_states = load(STATE_FIXTURE)
        cls.raw_intent = load(INTENT_FIXTURE)
        cls.states = validate_state_fixture(cls.raw_states)["states"]
        cls.intent = validate_intent_fixture(cls.raw_intent)
        # One bounded run supplies all comparison and coverage assertions.
        cls.report = run_shadow_comparison(cls.states, cls.intent, scenario_limit=120)
        cls.scenarios = cls.report["scenarios"]

    def test_function_extraction_hashes_and_drift_detection(self):
        hashes = production_function_hashes(ROOT)
        for name in ("set_firewall", "apply_node_endpoint_sets", "fw4_has_dns_hijack_rule", "fw4_dns_hijack_ready", "change_dnsmasq", "openkill_render_dns_set_rules"):
            self.assertIn(name, hashes)
            self.assertRegex(hashes[name]["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(hashes[name]["bytes"], 100)
        # A copied, mutated source must not silently reuse the baseline hash.
        with tempfile.TemporaryDirectory(prefix="openkill-3c-hash-") as tmp:
            tmp_root = pathlib.Path(tmp)
            for rel in ("luci-app-openkill/root/etc/init.d/openkill", "luci-app-openkill/root/usr/share/openkill/openkill_network.sh"):
                dst = tmp_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / rel, dst)
            init = tmp_root / "luci-app-openkill/root/etc/init.d/openkill"
            original = init.read_text(encoding="utf-8")
            marker = "set_firewall()\n{"
            self.assertIn(marker, original)
            init.write_text(original.replace(marker, marker + "\n# phase3c drift probe", 1), encoding="utf-8")
            changed = production_function_hashes(tmp_root)
            self.assertNotEqual(changed["set_firewall"]["sha256"], hashes["set_firewall"]["sha256"])

    def test_record_only_harness_and_fail_closed_command_surface(self):
        state = next(item for item in self.states if item["id"] == "STATE-01-BASIC-V4")
        packet = {
            "schema": "OPENKILL_SHADOW_PACKET_V1", "id": "P3C-HARNESS-PACKET", "family": "IPv4",
            "direction": "LAN_INGRESS", "protocol": "TCP", "src": "192.0.2.2", "dst": "203.0.113.2",
            "source_kind": "LAN", "service": "OTHER", "connection": "UNKNOWN", "self_process": False,
            "src_port": 40000, "dst_port": 443,
        }
        capture = run_production_harness(state, packet=packet)
        self.assertEqual(capture["returncode"], 0)
        self.assertEqual(capture["unknown_commands"], [])
        self.assertFalse(capture["real_mutation"])
        for line in capture["command_records"]:
            kind, _, command = line.partition("\t")
            self.assertIn(kind, COMMAND_ALLOWLIST | {"INTERNAL"})
            if kind == "nft":
                self.assertTrue(command.startswith("nft "))

    def test_old_normalizer_models_insert_flush_and_files(self):
        records = [
            "nft\tnft add chain inet fw4 openkill_mangle",
            "nft\tnft add rule inet fw4 openkill_mangle add-first counter return",
            "nft\tnft insert rule inet fw4 openkill_mangle position 0 ip daddr @node counter return",
            "nft\tnft flush chain inet fw4 openkill_mangle",
            "nft\tnft add rule inet fw4 openkill_mangle position 0 ip daddr @node counter return",
            "nft\tnft add rule inet fw4 openkill_mangle counter mark set 0x162",
        ]
        parsed = parse_nft_command_records(records)
        rules = [item for item in parsed["rules"] if item["chain"] == "openkill_mangle"]
        self.assertEqual([item["action"] for item in rules], ["RETURN_NATIVE", "MARK_PROXY"])
        state = next(item for item in self.states if item["id"] == "STATE-CASE-043")
        capture = run_production_harness(state, packet=next(c["packet"] for c in self.intent["cases"] if c["id"] == "SHADOW-043-v4_china_mainland"))
        parsed = parse_nft_command_records(capture["command_records"], file_records=capture["file_records"])
        china = next(item for item in parsed["sets"] if item["name"] == "china_ip_route")
        self.assertIn("198.51.100.43/32", china["elements"])

    def test_scenario_coverage_is_broad_and_ids_are_unique(self):
        self.assertGreaterEqual(len(self.scenarios), 40)
        self.assertEqual(len(self.scenarios), len({item["id"] for item in self.scenarios}))
        categories = Counter(item["category"] for item in self.scenarios)
        for category, minimum in {
            "TUN": 8, "TPROXY": 8, "REDIRECT": 4, "DNS": 8, "NODE": 8,
            "LOCAL": 8, "CHINA": 8, "ACCESS": 8, "OVERLAP": 15,
        }.items():
            self.assertGreaterEqual(categories[category], minimum, category)
        families = Counter(item["packet"]["family"] for item in self.scenarios)
        self.assertGreaterEqual(families["IPv4"], 15)
        self.assertGreaterEqual(families["IPv6"], 15)
        # Dual-stack coverage is represented by packet pairs in the fixture;
        # require at least five states containing both address families.
        dual = sum(
            1
            for item in self.scenarios
            if any(normalize_state(item["state"]).get(key) for key in ("wan4", "node4", "local4", "lan4", "china4", "fake_ip4"))
            and any(normalize_state(item["state"]).get(key) for key in ("wan6", "node6", "local6", "lan6", "delegated6", "china6", "fake_ip6"))
        )
        self.assertGreaterEqual(dual, 5)
        self.assertEqual(self.report["unknown_mismatch_count"], 0)

    def test_comparison_reconciles_current_production_baseline(self):
        # The exact extracted production updater inserts NODE_ENDPOINT at
        # position zero.  The current oracle and renderer now record that
        # observed order, while target behavior remains locked separately.
        # The execution contract also carries the production hybrid listener
        # actions (redirect 7892 versus TPROXY 7893) and router-self gate.
        self.assertEqual(self.report["semantic_mismatch_count"], 0)
        self.assertEqual(self.report["unknown_mismatch_count"], 0)
        mismatches = {
            item["id"] for item in self.report["results"] if item["classification"] == "SEMANTIC_MISMATCH"
        }
        self.assertEqual(mismatches, set())
        for item in self.report["results"]:
            if item["id"] in {"SHADOW-066-overlap_access_node_v4", "SHADOW-067-overlap_access_node_v6"}:
                self.assertEqual(item["dimensions"]["old_selected_reason"], "NODE_ENDPOINT")
                self.assertEqual(item["dimensions"]["new_selected_reason"], "NODE_ENDPOINT")
                self.assertFalse(item["dimensions"]["relative_order_changed"])
            elif item["id"].startswith("P3C-TPROXY-"):
                self.assertTrue(item["transport"]["equivalent"])
        allowed = {"EXACT_STRUCTURAL_MATCH", "SEMANTIC_EQUIVALENT_STRUCTURAL_DIFF", "KNOWN_CURRENT_GAP", "UNSUPPORTED_CURRENT_CASE"}
        allowed |= {"SEMANTIC_MISMATCH"}
        self.assertTrue(set(item["classification"] for item in self.report["results"]) <= allowed)
        self.assertIn("SEMANTIC_EQUIVALENT_STRUCTURAL_DIFF", self.report["comparison_classes"])
        self.assertIn("KNOWN_CURRENT_GAP", self.report["comparison_classes"])
        self.assertEqual(self.report["comparison_classes"]["NEW_RENDERER_DEFECT"], 0)
        self.assertEqual(len(self.report["unsupported_current_cases"]), 10)
        self.assertFalse(self.report["unbounded_unsupported_current_case"])
        self.assertEqual(
            {item["id"] for item in self.report["unsupported_current_cases"]},
            {
                "SHADOW-038-v4_custom_access_deny", "SHADOW-041-v6_custom_access_deny",
                "P3C-SYN-ACCESS-050-038-v4_custom_access_deny",
                "P3C-SYN-ACCESS-052-041-v6_custom_access_deny",
                "P3C-SYN-ACCESS-054-038-v4_custom_access_deny",
                "P3C-SYN-ACCESS-056-041-v6_custom_access_deny",
                "P3C-REDIRECT-01", "P3C-REDIRECT-02", "P3C-REDIRECT-03", "P3C-REDIRECT-04",
            },
        )

    def test_tproxy_transport_parity_is_explicit(self):
        tproxy = [item for item in self.report["results"] if item["id"].startswith("P3C-TPROXY-")]
        self.assertEqual(len(tproxy), 8)
        self.assertEqual(self.report["tproxy_parity"]["scenarios"], 8)
        self.assertEqual(self.report["tproxy_parity"]["mismatches"], 0)
        self.assertEqual(sum(1 for item in tproxy if item["transport"] is not None), 8)
        self.assertEqual(sum(1 for item in tproxy if item["transport"]["equivalent"]), 8)
        self.assertEqual(
            tproxy[0]["transport"]["configured_ports"],
            {"dns": 7874, "redirect": 7892, "tproxy": 7893},
        )
        # Every transport result retains family/protocol, reachable-chain,
        # mark and listener-port evidence for the final report.
        for item in tproxy:
            detail = item["transport"]
            self.assertIn(detail["family"], {"IPv4", "IPv6"})
            self.assertIn(detail["protocol"], {"TCP", "UDP"})
            self.assertIn("old_actions", detail)
            self.assertIn("new_actions", detail)

        router_self = self.report["tproxy_router_self"]
        self.assertEqual(router_self["scenarios"], 4)
        self.assertEqual(router_self["equivalent"], 4)
        self.assertEqual(router_self["mismatches"], 0)
        self.assertTrue(all(row["router_self_proxy"] for row in router_self["rows"]))
        by_transport = {(row["family"], row["protocol"]): row for row in router_self["rows"]}
        self.assertEqual(by_transport[("IPv4", "TCP")]["new_actions"][0][0], "REDIRECT_PROXY")
        self.assertEqual(by_transport[("IPv4", "UDP")]["new_actions"][0][0], "MARK_PROXY")
        self.assertEqual(by_transport[("IPv6", "TCP")]["new_actions"][0][0], "MARK_PROXY")
        self.assertEqual(by_transport[("IPv6", "UDP")]["new_actions"][0][0], "MARK_PROXY")

    def test_order_dimension_is_recorded_independently(self):
        by_id = {item["id"]: item for item in self.report["results"]}
        for case_id in ("SHADOW-066-overlap_access_node_v4", "SHADOW-067-overlap_access_node_v6"):
            dimensions = by_id[case_id]["dimensions"]
            self.assertEqual(dimensions["old_selected_reason"], "NODE_ENDPOINT")
            self.assertEqual(dimensions["new_selected_reason"], "NODE_ENDPOINT")
            self.assertFalse(dimensions["relative_order_changed"])
            self.assertFalse(dimensions["winner_conflict"])

    def test_acl_node_audit_covers_all_family_chains(self):
        audit = self.report["acl_node_audit"]
        self.assertEqual(audit["classification"], "CURRENT_SEMANTIC_BASELINE_DEFECT")
        self.assertTrue(audit["all_node_before_access"])
        self.assertEqual(
            audit["chains"],
            [
                "openkill", "openkill_mangle", "openkill_output", "openkill_mangle_output",
                "openkill_v6", "openkill_mangle_v6", "openkill_output_v6", "openkill_mangle_output_v6",
            ],
        )
        rows = [row for row in audit["rows"] if row["winner"] != "NOT_APPLICABLE"]
        self.assertTrue(rows)
        self.assertTrue(all(row["final_node_index"] < row["final_access_index"] for row in rows))

    def test_dns_scope_is_physical_and_not_metadata_only(self):
        audit = dns_scope_audit(self.states, self.intent, root=ROOT)
        self.assertEqual(audit["dns_scope_distinctness"], "PASS")
        self.assertEqual(audit["dns_packet_action_body_parity"], "PASS")
        self.assertEqual(audit["dns_current_hook_parity"], "PASS")
        self.assertNotEqual(audit["records"]["LAN_V4"]["new"]["chains"], audit["records"]["ROUTER_V4"]["new"]["chains"])
        self.assertNotEqual(audit["records"]["LAN_V6"]["new"]["chains"], audit["records"]["ROUTER_V6"]["new"]["chains"])
        self.assertIn("dstnat", audit["records"]["LAN_V4"]["old"]["chains"])
        self.assertIn("nat_output", audit["records"]["ROUTER_V4"]["old"]["chains"])
        for label in ("LAN_V4_MODE2", "LAN_V6_MODE2"):
            self.assertEqual(audit["records"][label]["old"]["path_signature"]["attachment_action"], "JUMP")
            self.assertEqual(audit["records"][label]["new"]["path_signature"]["attachment_action"], "JUMP")
            self.assertTrue(audit["records"][label]["packet_action_body_equivalent"])

    def test_current_profile_and_bc_leakage(self):
        for item in self.report["results"]:
            self.assertNotIn("TARGET", json.dumps(item, sort_keys=True))
        for item in self.report["scenarios"]:
            if item["category"] != "REDIRECT":
                self.assertNotIn("target_preview", item)
        self.assertEqual(self.report["comparison_classes"]["UNKNOWN"], 0)

    def test_production_owner_and_underlay_evidence(self):
        by_id = {item["state"]["id"]: item for item in self.scenarios}
        mihomo = next(item for item in self.scenarios if item["state"]["owner"] == "MIHOMO")
        disabled = next(item for item in self.scenarios if item["state"]["owner"] == "DISABLED")
        for item in (mihomo, disabled):
            self.assertEqual(item["state"]["owner"], item["state"]["owner"])
        # The current intent fixture contains explicit IPv4 TUN protection,
        # IPv6 current gap, node endpoint, and TProxy cases.
        classifications = {item["id"]: item["classification"] for item in self.report["results"]}
        self.assertTrue(any("v4_tun_ingress" in key and value == "EXACT_STRUCTURAL_MATCH" for key, value in classifications.items()))
        self.assertTrue(any("node" in key and value in {"EXACT_STRUCTURAL_MATCH", "SEMANTIC_EQUIVALENT_STRUCTURAL_DIFF"} for key, value in classifications.items()))

    def test_renderer_context_is_pure_and_reorder_stable(self):
        state = next(item for item in self.states if item["id"] == "STATE-01-BASIC-V4")
        packet = {
            "schema": "OPENKILL_SHADOW_PACKET_V1", "id": "P3C-PURE", "family": "IPv4", "direction": "LAN_INGRESS",
            "protocol": "TCP", "src": "192.0.2.2", "dst": "203.0.113.2", "source_kind": "LAN",
            "service": "OTHER", "connection": "UNKNOWN", "self_process": False, "src_port": 40000, "dst_port": 443,
        }
        before = hashlib.sha256(STATE_FIXTURE.read_bytes()).hexdigest()
        first = normalize_new_context_intent(state, packet)["rendered_text"]
        second = normalize_new_context_intent(copy.deepcopy(state), copy.deepcopy(packet))["rendered_text"]
        self.assertEqual(first, second)
        self.assertEqual(before, hashlib.sha256(STATE_FIXTURE.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main(verbosity=2)
