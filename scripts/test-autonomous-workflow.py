#!/usr/bin/env python3
"""Regression tests for the autonomous workflow migration contract."""
from pathlib import Path
import re
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AutonomousWorkflowTests(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_required_source_of_truth_documents_exist(self):
        for relative in (
            "AGENTS.md",
            "docs/ARCHITECTURE.md",
            "docs/development/AUTONOMOUS_WORKFLOW.md",
            "docs/testing/TEST_GATES.md",
            "docs/release/RELEASE_GATES.md",
            "docs/real-device/VALIDATION.md",
            "docs/exec-plans/CURRENT.md",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_development_ci_is_push_pr_only_and_read_only(self):
        source = self.read(".github/workflows/validate.yml")
        self.assertIn("name: OpenKill Development CI", source)
        self.assertIn("  push:", source)
        self.assertIn("  pull_request:", source)
        self.assertNotIn("publish-package.sh", source)
        self.assertNotIn("release_gate", source)
        self.assertIn("  contents: read", source)
        self.assertNotIn("contents: write", source)
        self.assertIn("sh scripts/local-gate.sh", source)
        self.assertIn("autonomous-workflow", source)

    def test_rc_build_is_manual_and_never_publishes(self):
        source = self.read(".github/workflows/build-openkill.yml")
        self.assertIn("name: OpenKill RC Build", source)
        self.assertNotRegex(source, r"(?m)^  (push|pull_request|schedule|workflow_run):")
        self.assertIn("  contents: read", source)
        self.assertIn("  workflow_dispatch:", source)
        self.assertNotIn("publish-package.sh", source)

    def test_rc_build_resets_sdk_package_selection(self):
        source = self.read(".github/workflows/build-openkill.yml")
        self.assertIn("timeout-minutes: 20", source)
        self.assertIn("[ -f .config ] || : > .config", source)
        self.assertIn("/^CONFIG_PACKAGE_[^=]*=/d", source)
        self.assertIn("selected_package_count", source)
        self.assertIn('Refusing an unexpectedly broad package selection', source)
        self.assertIn('make CONFIG_USE_APK= package/luci-app-openkill/compile V=s', source)
        self.assertNotIn('make -j"$(nproc)" package/luci-app-openkill/compile', source)

    def test_formal_release_has_no_push_trigger_and_requires_gate(self):
        source = self.read(".github/workflows/compile_new_ipk.yml")
        self.assertIn("name: OpenKill Formal Release", source)
        self.assertIn("  workflow_dispatch:", source)
        self.assertNotRegex(source, r"(?m)^  push:")
        self.assertIn("release_gate:", source)
        self.assertIn("publish:", source)
        self.assertIn("Require explicit release gate", source)
        self.assertIn("check-version-bump.sh", source)
        self.assertIn("inputs.release_gate == true && inputs.publish == true", source)
        self.assertNotIn("prune-published-packages.sh", source)

    def test_formal_ipk_build_resets_sdk_package_selection(self):
        source = self.read(".github/workflows/compile_new_ipk.yml")
        self.assertIn("[ -f .config ] || : > .config", source)
        self.assertIn("/^CONFIG_PACKAGE_[^=]*=/d", source)
        self.assertIn("for symbol in CONFIG_ALL CONFIG_ALL_KMODS", source)
        self.assertIn("selected_package_count", source)
        self.assertIn('Refusing an unexpectedly broad package selection', source)
        self.assertIn('make -j"$(nproc)" package/luci-app-openkill/compile', source)

    def test_missing_release_notes_fail_before_external_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, RELEASE_VERSION="9999-9999", PACKAGE_FORMAT="ipk",
                       GITHUB_REPOSITORY="fixture/fixture", GITHUB_SHA="fixture")
            command = ["bash", str(ROOT / "scripts/publish-package.sh")]
            if os.name == "nt":
                script = (ROOT / "scripts/publish-package.sh").as_posix()
                script = "/mnt/" + script[0].lower() + script[2:]
                temp_path = Path(directory).as_posix()
                temp_path = "/mnt/" + temp_path[0].lower() + temp_path[2:]
                command = ["wsl.exe", "--cd", temp_path, "--exec", "env", "RELEASE_VERSION=9999-9999", "PACKAGE_FORMAT=ipk",
                           "GITHUB_REPOSITORY=fixture/fixture", "GITHUB_SHA=fixture", "bash", script]
            result = subprocess.run(command,
                                    cwd=ROOT if os.name == "nt" else directory,
                                    env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing reviewed release notes", result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_version_metadata_is_consistent(self):
        makefile = self.read("luci-app-openkill/Makefile")
        installer = self.read("scripts/install-openkill.sh")
        readme = self.read("README.md")
        version = re.search(r"^PKG_VERSION:=(\d{4}-\d{4})$", makefile, re.MULTILINE)
        project = re.search(r'^PROJECT_VERSION="([^"]+)"$', installer, re.MULTILINE)
        readme_version = re.search(r"当前版本：`([^`]+)`", readme)
        self.assertIsNotNone(version)
        self.assertEqual(version.group(1), project.group(1))
        self.assertEqual(version.group(1), readme_version.group(1))

    def test_gate_helpers_are_dependency_light(self):
        for relative in (
            "scripts/preflight-openkill.sh",
            "scripts/local-gate.sh",
            "scripts/ci-gate.sh",
        ):
            source = self.read(relative)
            self.assertIn("#!/bin/sh", source)
            self.assertNotRegex(source, r"\b(ssh|scp|nmap|uci|ubus|nft)\b")

    def test_current_plan_records_recovered_baseline(self):
        source = self.read("docs/exec-plans/CURRENT.md")
        for marker in ("1a9678b", "D2A", "D2B", "D2C", "2026-1127", "v2026-1127-ipk"):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
