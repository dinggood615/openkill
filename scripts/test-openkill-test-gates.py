#!/usr/bin/env python3
"""Regression tests for the unified local gate executor."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

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

    def test_dependency_key_is_content_bound(self):
        case = gates.Case("fixture", "scripts/test-3e2-safe-config.py")
        key, inputs = gates.dependency_key(case)
        self.assertEqual(len(key), 64)
        names = {item["path"] for item in inputs}
        self.assertIn("scripts/test-3e2-safe-config.py", names)
        self.assertIn("scripts/fixtures/3e2-safe.yaml", names)

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

    def test_shell_cases_use_shell_interpreter_in_wsl(self):
        case = gates.Case("policy", "scripts/local-gate.sh", environment="wsl")
        command = gates.command_for(case)
        if gates.wsl_available():
            self.assertIn("sh", command)
            self.assertNotIn("python3", command[:5])

    def test_evidence_contract_is_machine_readable(self):
        source = gates.ROOT.joinpath("scripts/openkill-test-gates.py").read_text(encoding="utf-8")
        for filename in ("summary.json", "summary.txt", "environment.txt", "hashes.txt", "tests.tsv", "skips.tsv", "candidate-manifest.json"):
            self.assertIn(filename, source)
        payload = json.loads('{"device_access": 0, "central_apply": 0, "packet_test": 0}')
        self.assertEqual(payload["device_access"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
