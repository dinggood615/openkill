#!/usr/bin/env python3
"""Regression tests for the autonomous workflow migration contract."""
from pathlib import Path
import re
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
