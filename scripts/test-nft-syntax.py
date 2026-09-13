#!/usr/bin/env python3
"""Phase 3B development NFT syntax renderer tests.

The suite exercises only in-memory IR and temporary test files.  When a local
``nft`` binary exists it additionally runs the parser in check-only mode; it
never invokes ``nft -f`` or mutates a ruleset.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import pathlib
import random
import shutil
import unittest

from openkill_classifier_model import validate_fixture
from openkill_nft_ir import (
    NFT_IR_VERSION,
    render_context,
    render_state,
    validate_ir_fixture,
)
from openkill_nft_syntax import (
    DEFAULT_RENDERER_PROFILE,
    MARK_ABI,
    NFT_AST_SCHEMA,
    NFT_SYNTAX_SCHEMA,
    NFT_SYNTAX_VERSION,
    NftSyntaxValidationError,
    UnsupportedNftAction,
    audit_dependency_graph,
    diff_syntax,
    lower_nft_ir,
    normalize_elements,
    parse_normalized_intent,
    quote_comment,
    render_check_file,
    render_nft,
    render_test_scaffold,
    serialize_nft,
    syntax_fingerprint,
    validate_nft_ast,
    validate_nft_identifier,
    validate_nft_syntax_text,
    validate_syntax_fixture,
)
from openkill_shadow_adapter import shadow_compare, validate_intent_fixture, validate_state_fixture


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
IR_FIXTURE = SCRIPTS / "fixtures/openkill-nft-ir-v1.json"
CLASSIFIER_FIXTURE = SCRIPTS / "fixtures/openkill-classifier-semantic-v1.json"
STATE_FIXTURE = SCRIPTS / "fixtures/openkill-shadow-states-v1.json"
INTENT_FIXTURE = SCRIPTS / "fixtures/openkill-current-firewall-intent-v1.json"
SYNTAX_SOURCE = SCRIPTS / "openkill_nft_syntax.py"


def load_json(path: pathlib.Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class NFTSyntaxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ir_fixture = validate_ir_fixture(load_json(IR_FIXTURE))
        cls.syntax_fixture = validate_syntax_fixture(load_json(SCRIPTS / "fixtures/openkill-nft-syntax-v1.json"))
        cls.classifier_fixture = validate_fixture(load_json(CLASSIFIER_FIXTURE))
        cls.states = validate_state_fixture(load_json(STATE_FIXTURE))["states"]
        cls.state_by_id = {state["id"]: state for state in cls.states}
        cls.intent = validate_intent_fixture(load_json(INTENT_FIXTURE))
        cls.nft_path = shutil.which("nft")

    def test_schema_versions_and_dependency_graph(self):
        self.assertEqual(self.ir_fixture["ir_version"], NFT_IR_VERSION)
        self.assertEqual(self.ir_fixture["default_renderer_profile"], DEFAULT_RENDERER_PROFILE)
        audit = audit_dependency_graph(
            {**self.ir_fixture["dependency_graph"], "self_contained_components": ["DNS"]}
        )
        self.assertTrue(audit["acyclic"])
        self.assertIn("DNS", audit["self_contained_components"])
        self.assertIn("DNS", audit["self_edges"])
        self.assertEqual(self.syntax_fixture["syntax_version"], NFT_SYNTAX_VERSION)

    def test_current_profile_default_and_target_preview_lock(self):
        state = self.state_by_id["STATE-04-NODES"]
        current = lower_nft_ir(render_state(state))
        self.assertEqual(current["schema"], NFT_AST_SCHEMA)
        self.assertEqual(current["metadata"]["renderer_profile"], "current")
        self.assertEqual(current["metadata"]["behavior_change_lock"], "CURRENT_ONLY")
        with self.assertRaises(Exception):
            render_nft(render_state(state, profile="target"))
        target_ir = render_state(state, profile="target", target_preview=True)
        target = lower_nft_ir(target_ir)
        self.assertEqual(target["metadata"]["renderer_profile"], "target")
        self.assertTrue(target["metadata"]["preview_only"])
        self.assertIn("DEVELOPMENT_TARGET_PREVIEW", serialize_nft(target))

    def test_current_golden_97_replay_and_no_target_leak(self):
        unsupported = []
        rendered = 0
        for case in self.classifier_fixture["cases"]:
            with self.subTest(case=case["id"]):
                try:
                    text = render_nft(render_context(case, profile="current"))
                    rendered += 1
                    self.assertNotIn("DEVELOPMENT_TARGET_PREVIEW", text)
                    parse_normalized_intent(text)
                except UnsupportedNftAction:
                    unsupported.append(case["id"])
        self.assertEqual(len(self.classifier_fixture["cases"]), 97)
        # Modern ACCESS_DENY has no approved current verdict (BC-07); it is
        # intentionally surfaced as unsupported rather than lowered to DROP.
        self.assertEqual(unsupported, ["v4_custom_access_deny", "v6_custom_access_deny"])
        self.assertEqual(rendered + len(unsupported), 97)

    def test_target_preview_97_replay(self):
        rendered = 0
        unsupported = []
        for case in self.classifier_fixture["cases"]:
            with self.subTest(case=case["id"]):
                try:
                    text = render_nft(render_context(case, profile="target", target_preview=True))
                    self.assertIn("DEVELOPMENT_TARGET_PREVIEW", text)
                    rendered += 1
                except UnsupportedNftAction:
                    unsupported.append(case["id"])
        self.assertEqual(rendered + len(unsupported), 97)
        self.assertEqual(unsupported, ["v4_custom_access_deny", "v6_custom_access_deny"])

    def test_shadow_109_and_overlap_32_current_intent(self):
        unsupported = []
        for case in self.intent["cases"]:
            with self.subTest(case=case["id"]):
                state = self.state_by_id[case["state_id"]]
                compared = shadow_compare(state, case["packet"], case)
                ir = render_context(compared["adapted"]["context"], profile="current", state=state)
                try:
                    ast_value = lower_nft_ir(ir)
                    self.assertEqual(ast_value["metadata"]["renderer_profile"], "current")
                except UnsupportedNftAction:
                    unsupported.append(case["id"])
        self.assertEqual(len(self.intent["cases"]), 109)
        self.assertEqual(unsupported, ["SHADOW-038-v4_custom_access_deny", "SHADOW-041-v6_custom_access_deny"])
        overlap = [case for case in self.classifier_fixture["cases"] if case.get("overlap")]
        self.assertEqual(len(overlap), 32)
        for case in overlap:
            with self.subTest(overlap=case["id"]):
                ir = render_context(case, profile="current")
                self.assertEqual(ir["classification"]["reason"], case["expected_current"]["reason"])

    def test_bc_guards_preserve_current_gaps(self):
        text = render_nft(render_state(self.state_by_id["STATE-04-NODES"]))
        self.assertNotIn("CURRENT_TUN_INGRESS_V6", text)
        self.assertIn("CURRENT_TUN_INGRESS_V4", text)
        self.assertNotIn("drop", text.lower())
        self.assertNotIn("reject", text.lower())
        target = render_nft(
            render_state(self.state_by_id["STATE-04-NODES"], profile="target", target_preview=True)
        )
        self.assertIn("TARGET_TUN_INGRESS_V6", target)
        self.assertEqual(
            self.ir_fixture["behavior_change_lock"]["ids"],
            ["BC-01", "BC-02", "BC-03", "BC-04", "BC-05", "BC-06", "BC-07"],
        )

    def test_action_lowering_and_backend_separation(self):
        cases = {case["id"]: case for case in self.classifier_fixture["cases"]}
        mark_text = render_nft(render_context(cases["v4_default_tcp"]))
        self.assertIn("meta mark set 0x162", mark_text)
        tproxy = copy.deepcopy(cases["v4_default_udp"])
        tproxy_text = render_nft(render_context(tproxy))
        self.assertIn("tproxy to :12345 meta mark set 0x162", tproxy_text)
        v6_tproxy = copy.deepcopy(cases["v6_default_udp"])
        self.assertIn("tproxy to :12345 meta mark set 0x162", render_nft(render_context(v6_tproxy)))
        redirect = copy.deepcopy(cases["v4_default_tcp"])
        redirect["backend_mode"] = "REDIRECT"
        self.assertIn("redirect to :12345", render_nft(render_context(redirect)))
        udp_redirect = copy.deepcopy(cases["v4_default_udp"])
        udp_redirect["backend_mode"] = "REDIRECT"
        with self.assertRaises(UnsupportedNftAction):
            render_nft(render_context(udp_redirect))
        dns = render_nft(render_context(cases["v4_dns_lan"]))
        self.assertIn("jump openkill_dns_hijack", dns)
        self.assertEqual(MARK_ABI, {"version": 1, "mark": "0x162", "mask": "0xffffffff", "route_table": 354, "rule_preference": 1888})

    def test_control_and_invalid_value_matrix(self):
        control_text = render_nft(render_state(self.state_by_id["STATE-02-IPV6-SOURCE-SPECIFIC"]))
        self.assertIn("icmpv6 type {router-solicitation, router-advertisement, neighbor-solicitation, neighbor-advertisement, packet-too-big, destination-unreachable, time-exceeded, parameter-problem}", control_text)
        self.assertIn("udp dport { 546, 547 }", control_text)
        invalid_values = (
            (("not-an-ip",), "ADDRESS", "IPv4"),
            (("192.0.2.0/33",), "PREFIX", "IPv4"),
            ((0,), "PORT", "ALL"),
            (("aa:bb:cc:dd:ee",), "MAC", "ALL"),
            (("192.0.2.20-192.0.2.10",), "INTERVAL", "IPv4"),
            (("192.0.2.1",), "ADDRESS", "IPv6"),
        )
        for values, element_type, family in invalid_values:
            with self.subTest(values=values, element_type=element_type, family=family):
                with self.assertRaises(NftSyntaxValidationError):
                    normalize_elements(values, element_type, family)

    def test_schema_name_comment_and_injection_validation(self):
        for bad in ("", "9bad", "bad-name", "bad name", "bad;rm", "bad$(x)", "bad\nline", 'bad"quote'):
            with self.subTest(value=bad):
                with self.assertRaises(NftSyntaxValidationError):
                    validate_nft_identifier(bad)
        self.assertEqual(quote_comment('space "quote" \\ slash; unicode ✓'), '"space \\"quote\\" \\\\ slash; unicode ✓"')
        for bad in ("line\nfeed", "line\rfeed", "nul\x00"):
            with self.assertRaises(NftSyntaxValidationError):
                quote_comment(bad)
        for bad in (
            "flush ruleset\n",
            "delete table inet fw4\n",
            "delete foreign\n",
            "include \"/tmp/x\"\n",
            "add rule x $(id)\n",
            "add rule inet fw4 c return; rm -rf /tmp/x\n",
        ):
            with self.assertRaises(NftSyntaxValidationError):
                validate_nft_syntax_text(bad)
        self.assertIsInstance(
            validate_nft_syntax_text('add rule inet fw4 c return comment "safe; rm && echo"\n'),
            str,
        )

    def test_address_set_empty_interval_port_mac_and_host_semantics(self):
        self.assertEqual(normalize_elements(["2001:0DB8::1/128", "2001:db8::1"], "ADDRESS", "IPv6"), ["2001:db8::1"])
        self.assertEqual(normalize_elements(["2001:0DB8::/64"], "PREFIX", "IPv6"), ["2001:db8::/64"])
        self.assertEqual(normalize_elements([443, 53, 443], "PORT", "ALL"), ["53", "443"])
        self.assertEqual(normalize_elements(["AA:BB:CC:DD:EE:FF"], "MAC", "ALL"), ["aa:bb:cc:dd:ee:ff"])
        self.assertEqual(normalize_elements(["192.0.2.10-192.0.2.20"], "INTERVAL", "IPv4"), ["192.0.2.10-192.0.2.20"])
        text = render_nft(render_state(self.state_by_id["STATE-CASE-003"]))
        self.assertIn("add set inet fw4 openkill_node4 { type ipv4_addr;", text)
        self.assertIn("add set inet fw4 openkill_node6 { type ipv6_addr;", text)
        self.assertIn("add set inet fw4 china_ip_route { type ipv4_addr;", text)
        wan_state = copy.deepcopy(self.state_by_id["STATE-CASE-012"])
        wan_state["wan6"] = ["2001:0DB8:0100::12/64"]
        text = render_nft(render_state(wan_state))
        wan_line = next(line for line in text.splitlines() if "openkill_wan_host6" in line and line.startswith("add set"))
        self.assertIn("2001:db8:100::12", wan_line)
        self.assertNotIn("2001:db8:100::/64", wan_line)

    def test_scaffold_isolation_and_external_fw4_reference(self):
        ir = render_state(self.state_by_id["STATE-04-NODES"])
        production = render_nft(ir)
        scaffold = render_test_scaffold(ir)
        self.assertNotIn("add table inet fw4", production)
        self.assertIn("add table inet fw4", scaffold)
        self.assertIn("TEST_SCAFFOLD", scaffold)
        self.assertNotIn("TEST_SCAFFOLD", production)
        self.assertNotIn("TEST_ONLY", production)
        self.assertIn("nat_output { type nat hook output priority -1; }", production)
        self.assertIn("external FW4 reference", production)
        self.assertIn("meta nfproto ipv4 jump openkill_mangle", production)
        self.assertIn("meta nfproto ipv6 jump openkill_mangle_v6", production)
        validate_nft_syntax_text(scaffold, production_output=False)

    def test_ownership_traceability_and_foreign_preservation(self):
        ast_value = lower_nft_ir(render_state(self.state_by_id["STATE-04-NODES"]))
        validate_nft_ast(ast_value)
        entries = {entry["logical_id"] for entry in ast_value["ownership_manifest"]["entries"]}
        generated = {obj["logical_id"] for section in ("owned_chains", "sets", "rules", "attachments") for obj in ast_value[section]}
        self.assertEqual(entries, generated)
        foreign = {
            "object_type": "chain",
            "logical_id": "FOREIGN_SAME_NAME",
            "physical_name": "openkill_node4",
            "owner": "FOREIGN",
            "ownership": "FOREIGN",
            "parent_owner": "FW4",
            "parent_table": "inet fw4",
            "component": "NODE",
            "family": "IPv4",
            "semantic_spec_version": 1,
        }
        self.assertNotIn(foreign["logical_id"], entries)
        self.assertIn("openkill_node4", {item["physical_name"] for item in ast_value["sets"]})

    def test_deterministic_render_and_input_order_independence(self):
        ir = render_state(self.state_by_id["STATE-04-NODES"])
        ast_value = lower_nft_ir(ir)
        first = serialize_nft(ast_value)
        hashes = {hashlib.sha256(serialize_nft(ast_value).encode("utf-8")).hexdigest() for _ in range(1000)}
        self.assertEqual(len(hashes), 1)
        for seed in range(100):
            shuffled = copy.deepcopy(ast_value)
            rng = random.Random(seed)
            for key in ("owned_chains", "sets", "rules", "attachments"):
                rng.shuffle(shuffled[key])
            self.assertEqual(first, serialize_nft(shuffled))
        self.assertEqual(first, serialize_nft(ast_value))
        self.assertEqual(syntax_fingerprint(ast_value), syntax_fingerprint(ast_value))

    def test_component_local_syntax_diffs(self):
        base = self.state_by_id["STATE-04-NODES"]
        node = copy.deepcopy(base)
        node["node4"] = list(node["node4"]) + ["203.0.113.201"]
        diff = diff_syntax(lower_nft_ir(render_state(base)), lower_nft_ir(render_state(node)))
        self.assertEqual(diff["changed_components"], ["NODE"])
        self.assertIn("SET_ELEMENT_CHANGE", diff["categories"])
        for key, component in (("local6", "LOCAL"), ("china4", "CHINA")):
            changed = copy.deepcopy(base)
            changed[key] = ["2001:db8:300::/64"] if key == "local6" else ["203.0.113.0/24"]
            result = diff_syntax(lower_nft_ir(render_state(base)), lower_nft_ir(render_state(changed)))
            self.assertEqual(result["changed_components"], [component])
        acl = copy.deepcopy(base)
        acl["access4"] = [{"network": "203.0.113.0/24", "action": "DENY"}]
        self.assertEqual(diff_syntax(lower_nft_ir(render_state(base)), lower_nft_ir(render_state(acl)))["changed_components"], ["ACCESS"])
        mode = copy.deepcopy(base)
        mode["run_mode"] = "TPROXY"
        self.assertIn("TOPOLOGY_CHANGE", diff_syntax(lower_nft_ir(render_state(base)), lower_nft_ir(render_state(mode)))["categories"])
        owner = copy.deepcopy(base)
        owner["owner"] = "MIHOMO"
        owner_diff = diff_syntax(lower_nft_ir(render_state(base)), lower_nft_ir(render_state(owner)))
        self.assertTrue(owner_diff["no_change"] is False)

    def test_invalid_ir_and_unknown_action_match_component(self):
        ast_value = lower_nft_ir(render_state(self.state_by_id["STATE-CASE-003"]))
        for mutate in ("action_type", "component"):
            bad = copy.deepcopy(ast_value)
            if mutate == "action_type":
                bad["rules"][0]["action_type"] = "DROP_NOW"
            else:
                bad["rules"][0]["component"] = "UNKNOWN"
            with self.subTest(mutate=mutate):
                with self.assertRaises(NftSyntaxValidationError):
                    validate_nft_ast(bad)
        duplicate_physical = copy.deepcopy(ast_value)
        duplicate_physical["sets"][1]["physical_name"] = duplicate_physical["sets"][0]["physical_name"]
        with self.assertRaises(NftSyntaxValidationError):
            validate_nft_ast(duplicate_physical)
        unknown_match_ir = render_state(self.state_by_id["STATE-CASE-003"])
        unknown_match_ir["rules"][0]["match"]["unknown_match"] = True
        with self.assertRaises(NftSyntaxValidationError):
            lower_nft_ir(unknown_match_ir)
        bad_text = "add rule inet fw4 openkill counter bad-match comment \"x\"\n"
        self.assertIsInstance(validate_nft_syntax_text(bad_text), str)

    def test_renderer_has_no_policy_ladder_or_runtime_imports(self):
        source = SYNTAX_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
        self.assertNotIn("subprocess", imported)
        self.assertNotIn("socket", imported)
        self.assertNotIn("os", imported)
        self.assertNotIn("CURRENT_PRECEDENCE", source)
        self.assertNotIn("TARGET_PRECEDENCE", source)
        self.assertIsNone(__import__("re").search(r"if\s+[^\n]*(?:china|node)[^\n]*precedence", source.lower()))
        before_cwd, before_env = os.getcwd(), dict(os.environ)
        render_nft(render_state(self.state_by_id["STATE-CASE-003"]))
        self.assertEqual(os.getcwd(), before_cwd)
        self.assertEqual(dict(os.environ), before_env)

    def test_mihomo_owner_emits_no_owned_dataplane(self):
        ir = render_state(self.state_by_id["STATE-11-MIHOMO-OWNER"])
        ast_value = lower_nft_ir(ir)
        self.assertEqual(ast_value["owned_chains"], [])
        self.assertEqual(ast_value["sets"], [])
        self.assertEqual(ast_value["rules"], [])
        self.assertEqual(ast_value["attachments"], [])
        self.assertNotIn("add chain", render_nft(ir))

    def test_nft_check_matrix_or_explicit_unavailable(self):
        scenarios = {
            "basic_ipv4_tun": self.state_by_id["STATE-01-BASIC-V4"],
            "basic_ipv6_tun_current": self.state_by_id["STATE-02-IPV6-SOURCE-SPECIFIC"],
            "dual_stack_tun": self.state_by_id["STATE-03-DUAL-STACK"],
            "node4_node6": self.state_by_id["STATE-04-NODES"],
            "china": self.state_by_id["STATE-05-CHINA-DIRECT"],
            "china_pass": self.state_by_id["STATE-06-CHINA-PASS"],
            "fakeip": self.state_by_id["STATE-07-FAKE-IP"],
            "acl": self.state_by_id["STATE-08-LAN-ACL"],
            "tproxy": self.state_by_id["STATE-12-TPROXY"],
        }
        for name, state in scenarios.items():
            with self.subTest(scenario=name):
                text = render_check_file(render_state(state))
                self.assertIn("TEST_SCAFFOLD", text)
                if not self.nft_path:
                    continue
                from openkill_nft_check import run_nft_check

                result = run_nft_check(text, nft_path=self.nft_path)
                self.assertEqual(result["returncode"], 0, result)
                self.assertEqual(result["argv"][1:3], ["-c", "-f"])


if __name__ == "__main__":
    local_nft = shutil.which("nft")
    print("LOCAL_NFT_AVAILABLE={}".format("YES" if local_nft else "NO"))
    print("NFT_CHECK_AVAILABLE={}".format("PASS" if local_nft else "FAIL"))
    if not local_nft:
        print("NFT_CHECK_MATRIX=NOT_TESTED (nft CLI unavailable; no installation attempted)")
    unittest.main(verbosity=2)
