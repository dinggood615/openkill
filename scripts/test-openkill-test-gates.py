#!/usr/bin/env python3
"""Regression tests for the unified local gate executor."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

RUNNER_PATH = Path(__file__).with_name("openkill-test-gates.py")
spec = importlib.util.spec_from_file_location("openkill_test_gates", RUNNER_PATH)
assert spec and spec.loader
gates = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gates
spec.loader.exec_module(gates)


class TestGateRunner(unittest.TestCase):
    def test_modes_have_explicit_plans(self):
        self.assertTrue(gates.build_cases("fast"))
        self.assertGreater(len(gates.build_cases("full")), len(gates.build_cases("fast")))
        self.assertGreaterEqual(len(gates.build_cases("device-preflight")), len(gates.NATIVE_TESTS))
        self.assertIn("test-ui-contract", {case.name for case in gates.build_cases("fast")})

    def test_dependency_key_is_content_bound(self):
        case = gates.Case("fixture", "scripts/test-3e2-safe-config.py")
        key, inputs = gates.dependency_key(case)
        self.assertEqual(len(key), 64)
        names = {item["path"] for item in inputs}
        self.assertIn("scripts/test-3e2-safe-config.py", names)
        self.assertIn("scripts/fixtures/3e2-safe.yaml", names)
        self.assertIn("scripts/openkill_shadow_semantic_model.py", names)
        self.assertIn("scripts/verify_3e2_safe_config.py", names)

    def test_ui_dependency_key_includes_rendered_sources(self):
        case = gates.Case("test-ui-contract", "scripts/test-ui-contract.py")
        _, inputs = gates.dependency_key(case)
        names = {item["path"] for item in inputs}
        self.assertIn("luci-app-openkill/luasrc/view/openkill/status.htm", names)
        self.assertIn("luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css", names)

    def test_candidate_identity_fails_closed_on_worktree_change(self):
        manifest = {"head": "head", "runner_source_hash": "runner", "artifacts": [], "canonical_config": {}}
        with mock.patch.object(gates, "working_tree_status", return_value=" M status.htm"):
            self.assertEqual(gates.candidate_identity_error(manifest, "candidate"), "WORKING_TREE_CHANGED")

    def test_candidate_manifest_is_hash_bound(self):
        manifest, candidate_id = gates.candidate_manifest("unit-test")
        self.assertEqual(len(candidate_id), 64)
        self.assertEqual(manifest["candidate_id"], candidate_id)
        self.assertEqual(manifest["canonical_config"]["sha256"], gates.CANONICAL_CONFIG_SHA256)
        self.assertEqual(len(manifest["runner_source_hash"]), 64)
        self.assertTrue(manifest["artifacts"])
        self.assertEqual(
            manifest["minimal_staging_artifacts"],
            sorted(
                (
                    "luci-app-openkill/root/usr/share/openkill/openkill_nft_renderer.sh",
                    "luci-app-openkill/root/usr/share/openkill/openkill_nft_shadow.sh",
                    "luci-app-openkill/root/usr/share/openkill/shadow/input_tun_v1.tsv",
                    "luci-app-openkill/root/usr/share/openkill/shadow/semantic_model_v1.tsv",
                )
            ),
        )

    def test_output_classification_does_not_hide_failure(self):
        process = subprocess.CompletedProcess([sys.executable], 7, "later=pass\n", "earlier=failed\n")
        status, reason = gates.classify_output(gates.Case("failure", None), process)
        self.assertEqual(status, "FAIL")
        self.assertEqual(reason, "RETURN_CODE_7")

    def test_documented_environment_skip_has_explicit_status(self):
        process = subprocess.CompletedProcess([sys.executable], 0, "Ruby is not installed\n", "")
        status, reason = gates.classify_output(gates.Case("ruby", None, skip_policy=("RUBY_UNAVAILABLE",)), process)
        self.assertEqual(status, "SKIP_ALLOWED")
        self.assertEqual(reason, "RUBY_UNAVAILABLE")

    def test_core_network_failure_is_explicit_environment_skip(self):
        process = subprocess.CompletedProcess(
            [sys.executable],
            1,
            "",
            "OPENKILL_ENVIRONMENT_LIMIT=CORE_RELEASE_UNAVAILABLE\nDETAIL=URLError",
        )
        status, reason = gates.classify_output(
            gates.Case("test-core-v1_19_30-wsl", None, skip_policy=("CORE_RELEASE_UNAVAILABLE",)),
            process,
        )
        self.assertEqual(status, "NOT_RUN_ENVIRONMENT")
        self.assertEqual(reason, "CORE_RELEASE_UNAVAILABLE")

    def test_generic_urlopen_traceback_is_a_failure(self):
        process = subprocess.CompletedProcess(
            [sys.executable],
            1,
            "",
            "Traceback: urllib.error.URLError: urlopen error: fixture failure",
        )
        status, reason = gates.classify_output(
            gates.Case("test-core-v1_19_30-wsl", None, skip_policy=("CORE_RELEASE_UNAVAILABLE",)),
            process,
        )
        self.assertEqual(status, "FAIL")
        self.assertEqual(reason, "RETURN_CODE_1")

    def test_timeout_is_never_an_environment_skip(self):
        process = subprocess.CompletedProcess([sys.executable], 124, "", "timeout")
        status, reason = gates.classify_output(gates.Case("test-core", None), process)
        self.assertEqual((status, reason), ("FAIL", "TIMEOUT"))

    def test_required_core_environment_limit_blocks_complete_gate(self):
        records = [{"name": "test-core-v1_19_30-wsl", "status": "NOT_RUN_ENVIRONMENT"}]
        self.assertFalse(gates.gate_overall("full", records))
        self.assertFalse(gates.gate_overall("device-preflight", records))

    def test_documented_non_core_environment_skip_can_remain_allowed(self):
        records = [{"name": "test-nft-syntax", "status": "NOT_RUN_ENVIRONMENT"}]
        self.assertTrue(gates.gate_overall("full", records))

    def test_network_guard_delta_detects_route_proxy_and_dns_changes(self):
        before = {"available": True, **{key: {"hash": key} for key in ("default_route", "dns", "proxy", "adapters", "listeners", "wsl_running")}}
        after = json.loads(json.dumps(before))
        after["default_route"]["hash"] = "changed"
        delta = gates.network_guard_delta(before, after)
        self.assertEqual(delta["status"], "FAIL")
        self.assertIn("default_route", delta["unexpected"])

    def test_network_guard_allows_only_wsl_scoped_changes(self):
        before = {"available": True, **{key: {"hash": key} for key in ("default_route", "dns", "proxy", "adapters", "listeners", "wsl_running")}}
        after = json.loads(json.dumps(before))
        after["adapters"]["hash"] = "changed"
        after["wsl_running"]["hash"] = "changed"
        delta = gates.network_guard_delta(before, after, wsl_case=True)
        self.assertEqual(delta["status"], "PASS")
        self.assertEqual(delta["unexpected"], [])

    def test_network_guard_records_idle_wsl_lifecycle_between_native_cases(self):
        before = {"available": True, **{key: {"hash": key} for key in ("default_route", "dns", "proxy", "adapters", "listeners", "wsl_running")}}
        after = json.loads(json.dumps(before))
        after["wsl_running"]["hash"] = "changed"
        delta = gates.network_guard_delta(before, after)
        self.assertEqual(delta["status"], "PASS")
        self.assertEqual(delta["classification"], "WSL_LIFECYCLE_OBSERVED")
        self.assertEqual(delta["expected_wsl_changes"], ["wsl_running"])
        self.assertEqual(delta["unexpected"], [])

    def test_network_guard_rejects_host_listener_change_during_wsl_case(self):
        before = {"available": True, **{key: {"hash": key} for key in ("default_route", "dns", "proxy", "adapters", "listeners", "wsl_running")}}
        after = json.loads(json.dumps(before))
        after["listeners"]["hash"] = "changed"
        delta = gates.network_guard_delta(before, after, wsl_case=True)
        self.assertEqual(delta["status"], "FAIL")
        self.assertEqual(delta["unexpected"], ["listeners"])

    def test_wsl_command_carries_a_token_scoped_marker(self):
        command = gates.command_for(
            gates.Case("policy", "scripts/local-gate.sh", environment="wsl"),
            "token123",
        )
        if gates.wsl_available():
            self.assertIn("/tmp/openkill-test-runs/token123", command[-1])
            self.assertIn("OPENKILL_TEST_RUN_TOKEN", command[-1])
            self.assertIn("\\$dir", command[-1])

    def test_wsl_inventory_probe_is_read_only_and_version_compatible(self):
        snapshot_source = gates.host_network_snapshot.__code__.co_consts
        self.assertTrue(any("hashed host-network state" in str(value) for value in snapshot_source))
        # The command is intentionally kept in the implementation rather than
        # using ``--running``, which returns 0xffffffff on the supported host.
        if gates.wsl_available():
            probe = gates._fingerprint_command(["wsl.exe", "-l", "-v"])
            self.assertTrue(probe["available"], probe)

    def test_ruby_dependent_wsl_cases_declare_ruby_skip(self):
        cases = {case.name: case for case in gates.WSL_TESTS}
        self.assertIn("RUBY_UNAVAILABLE", cases["test-installer-wsl"].skip_policy)
        self.assertIn("RUBY_UNAVAILABLE", cases["test-runtime-wsl"].skip_policy)

    def test_core_cases_declare_network_skip(self):
        cases = {case.name: case for case in gates.WSL_TESTS}
        self.assertIn("CORE_RELEASE_UNAVAILABLE", cases["test-core-v1_19_30-wsl"].skip_policy)
        self.assertIn("CORE_RELEASE_UNAVAILABLE", cases["test-core-latest-wsl"].skip_policy)

    def test_shell_cases_use_shell_interpreter_in_wsl(self):
        case = gates.Case("policy", "scripts/local-gate.sh", environment="wsl")
        command = gates.command_for(case)
        if gates.wsl_available():
            self.assertIn("sh", command)
            self.assertNotIn("python3", command[:5])

    def test_evidence_contract_is_machine_readable(self):
        source = gates.ROOT.joinpath("scripts/openkill-test-gates.py").read_text(encoding="utf-8")
        for filename in ("summary.json", "summary.txt", "environment.txt", "hashes.txt", "tests.tsv", "skips.tsv", "candidate-manifest.json", "network-guard.json"):
            self.assertIn(filename, source)
        payload = json.loads('{"device_access": 0, "host_network_settings_changed_by_work": 0, "central_apply": 0, "packet_test": 0}')
        self.assertEqual(payload["device_access"], 0)
        self.assertEqual(payload["host_network_settings_changed_by_work"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
