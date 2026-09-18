"""Focused CURRENT DNS intent reconciliation tests.

These tests use only checked-in fixtures and the development renderer/harness.
They make the three DNS layers explicit: the mode-1 firewall entry point is
the dnsmasq listener (:53), while ``dns_port`` remains Mihomo's listener and
dnsmasq upstream (:7874).  No command or device is contacted.
"""

from __future__ import annotations

import copy
import json
import pathlib
import unittest

from openkill_nft_ir import (
    DEFAULT_DNSMASQ_LISTEN_PORT,
    DEFAULT_MIHOMO_DNS_PORT,
    render_context,
)
from openkill_nft_syntax import lower_nft_ir, render_nft
from openkill_production_shadow import (
    normalize_new_context_intent,
    parse_nft_command_records,
    run_production_harness,
)
from openkill_shadow_adapter import validate_intent_fixture, validate_state_fixture
from openkill_shadow_semantic_model import compare_dns_semantics


ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_FIXTURE = ROOT / "scripts/fixtures/openkill-shadow-states-v1.json"
INTENT_FIXTURE = ROOT / "scripts/fixtures/openkill-current-firewall-intent-v1.json"
SEMANTIC_FIXTURE = ROOT / "scripts/fixtures/openkill-shadow-semantic-v1.json"


def _load(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


class CurrentDnsIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.states = validate_state_fixture(_load(STATE_FIXTURE))["states"]
        cls.state_by_id = {state["id"]: state for state in cls.states}
        cls.intent = validate_intent_fixture(_load(INTENT_FIXTURE))
        cls.case_by_id = {case["id"]: case for case in cls.intent["cases"]}
        cls.semantic_fixture = _load(SEMANTIC_FIXTURE)

    def _context_render(self, case_id):
        case = self.case_by_id[case_id]
        state = self.state_by_id[case["state_id"]]
        return state, normalize_new_context_intent(state, case["packet"])

    def test_source_contract_separates_listener_from_mode1_firewall(self):
        self.assertEqual(DEFAULT_MIHOMO_DNS_PORT, 7874)
        self.assertEqual(DEFAULT_DNSMASQ_LISTEN_PORT, 53)
        desired = self.semantic_fixture["dns_desired"]
        self.assertEqual(desired["dns_semantics"]["DNS_FIREWALL_LAN_TARGET"], 53)
        self.assertEqual(desired["dns_semantics"]["DNS_FIREWALL_ROUTER_TARGET"], 53)
        self.assertEqual(desired["dns_semantics"]["DNSMASQ_LISTEN_TARGET"], 53)
        self.assertEqual(desired["dns_semantics"]["DNSMASQ_UPSTREAM_TARGET"], "127.0.0.1#7874")
        self.assertEqual(desired["dns_semantics"]["MIHOMO_DNS_LISTENER"], "127.0.0.1:7874")

    def test_mode1_lan_and_router_render_to_dnsmasq_listener(self):
        for case_id in (
            "SHADOW-053-v4_dns_lan",
            "SHADOW-054-v4_dns_router_output",
            "SHADOW-061-v6_dns_lan",
            "SHADOW-062-v6_dns_router_output",
        ):
            with self.subTest(case=case_id):
                state, rendered = self._context_render(case_id)
                self.assertEqual(rendered["context"]["backend_mode"], "TUN")
                dns_rules = [rule for rule in rendered["rules"] if rule.get("reason") == "DNS"]
                self.assertTrue(dns_rules)
                self.assertTrue(any(rule.get("action_expression") == "redirect to :53" for rule in dns_rules))
                self.assertNotIn("redirect to :7874", rendered["rendered_text"])
                ir = render_context(
                    rendered["context"], profile="current", state=state
                )
                execution_ir = ir["context_execution"]
                self.assertEqual(execution_ir["dns_port"], 7874)
                self.assertEqual(execution_ir["firewall_dns_port"], 53)
                self.assertEqual(execution_ir["dns_mode"], "1")
                self.assertEqual(lower_nft_ir(ir)["metadata"]["renderer_profile"], "current")

    def test_mode2_keeps_direct_mihomo_listener(self):
        state = self.state_by_id["STATE-09-SELF-PROXY"]
        packet = {
            "schema": "OPENKILL_SHADOW_PACKET_V1",
            "id": "D2C-MODE2-LAN",
            "family": "IPv4",
            "direction": "LAN_INGRESS",
            "protocol": "UDP",
            "src": "192.0.2.9",
            "dst": "198.51.100.53",
            "source_kind": "LAN",
            "service": "DNS",
            "connection": "UNKNOWN",
            "self_process": False,
            "src_port": 40009,
            "dst_port": None,
        }
        rendered = normalize_new_context_intent(state, packet)
        self.assertIn("jump openkill_dns_redirect", rendered["rendered_text"])
        self.assertIn("redirect to :7874", rendered["rendered_text"])
        ir = render_context(rendered["context"], profile="current", state=state)
        self.assertEqual(ir["context_execution"]["dns_mode"], "2")
        self.assertEqual(ir["context_execution"]["dns_port"], 7874)
        self.assertEqual(ir["context_execution"]["firewall_dns_port"], 7874)

    def test_mode1_keeps_custom_mihomo_port_separate(self):
        state = copy.deepcopy(self.state_by_id["STATE-CASE-053"])
        state["proxy_ports"]["dns"] = 7999
        packet = copy.deepcopy(self.case_by_id["SHADOW-053-v4_dns_lan"]["packet"])
        rendered = normalize_new_context_intent(state, packet)
        ir = render_context(rendered["context"], profile="current", state=state)
        execution = ir["context_execution"]
        self.assertEqual(execution["dns_port"], 7999)
        self.assertEqual(execution["firewall_dns_port"], 53)
        self.assertIn("redirect to :53", rendered["rendered_text"])
        self.assertNotIn("redirect to :7999", rendered["rendered_text"])

    def test_legacy_harness_models_dnsmasq_port_independently(self):
        for case_id in ("SHADOW-053-v4_dns_lan", "SHADOW-054-v4_dns_router_output"):
            with self.subTest(case=case_id):
                case = self.case_by_id[case_id]
                state = self.state_by_id[case["state_id"]]
                capture = run_production_harness(state, packet=case["packet"])
                self.assertEqual(capture["returncode"], 0)
                parsed = parse_nft_command_records(capture["command_records"])
                dns_rules = [rule for rule in parsed["rules"] if rule.get("reason") == "DNS"]
                self.assertTrue(dns_rules)
                self.assertTrue(all("redirect to 53" in rule.get("expression", "") for rule in dns_rules))

    def test_checked_in_sources_preserve_three_layer_dns_contract(self):
        init = (ROOT / "luci-app-openkill/root/etc/init.d/openkill").read_text(encoding="utf-8")
        config = (ROOT / "luci-app-openkill/root/etc/config/openkill").read_text(encoding="utf-8")
        settings = (ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/settings.lua").read_text(encoding="utf-8")
        shadow = (ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_nft_shadow.sh").read_text(encoding="utf-8")
        self.assertIn('option dns_port \'7874\'', config)
        self.assertIn('add_list "$DNSMASQ_UCI.server"=127.0.0.1#"$dns_port"', init)
        self.assertIn('redirect to ${DNSPORT}', init)
        self.assertIn('DNSPORT=$(uci -q get "$DNSMASQ_UCI.port")', init)
        self.assertIn("firewall intercepts LAN DNS on port 53", settings)
        self.assertIn("DNS_PORT) openkill_shadow_auto_value", shadow)

    def test_reconciled_frozen_102_fixture_is_a_match_without_equivalence(self):
        actual = self.semantic_fixture["dns_actual"]
        desired = self.semantic_fixture["dns_desired"]
        report = compare_dns_semantics(actual, desired)
        self.assertEqual(report["parity"], "MATCH")
        self.assertFalse(report["dns_53_7874_direct_equivalence"])
        self.assertEqual(report["mismatches"], [])

    def test_wrong_targets_are_attributed_independently(self):
        actual = self.semantic_fixture["dns_actual"]
        desired = copy.deepcopy(self.semantic_fixture["dns_desired"])
        desired["dns_semantics"]["DNS_FIREWALL_LAN_TARGET"] = 54
        report = compare_dns_semantics(actual, desired)
        self.assertEqual(report["parity"], "MISMATCH")
        self.assertEqual([row["field"] for row in report["mismatches"]], ["DNS_FIREWALL_LAN_TARGET"])

        desired = copy.deepcopy(self.semantic_fixture["dns_desired"])
        desired["dns_semantics"]["DNSMASQ_UPSTREAM_TARGET"] = "127.0.0.1#7875"
        report = compare_dns_semantics(actual, desired)
        self.assertEqual(report["parity"], "MISMATCH")
        self.assertEqual([row["field"] for row in report["mismatches"]], ["DNSMASQ_UPSTREAM_TARGET"])

        desired = copy.deepcopy(self.semantic_fixture["dns_desired"])
        desired["dns_semantics"]["MIHOMO_DNS_LISTENER"] = "127.0.0.1:7875"
        report = compare_dns_semantics(actual, desired)
        self.assertEqual(report["parity"], "MISMATCH")
        self.assertEqual([row["field"] for row in report["mismatches"]], ["MIHOMO_DNS_LISTENER"])

    def test_mixed_lan_router_and_family_fields_do_not_collapse(self):
        actual = self.semantic_fixture["dns_actual"]
        desired = copy.deepcopy(self.semantic_fixture["dns_desired"])
        desired["dns_semantics"]["DNS_FIREWALL_ROUTER_TARGET"] = 54
        desired["dns_semantics"]["DNS_SCOPE_IPV6"] = {"lan": True, "router": False}
        report = compare_dns_semantics(actual, desired)
        self.assertEqual(report["parity"], "MISMATCH")
        self.assertEqual(
            {row["field"] for row in report["mismatches"]},
            {"DNS_FIREWALL_ROUTER_TARGET", "DNS_SCOPE_IPV6"},
        )

    def test_renderer_output_is_deterministic_after_port_split(self):
        state, rendered = self._context_render("SHADOW-053-v4_dns_lan")
        first = rendered["rendered_text"]
        second = render_nft(render_context(rendered["context"], profile="current", state=state))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
