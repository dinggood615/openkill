#!/usr/bin/env python3
"""Validate the local browser preview uses production presentation inputs."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build-ui-preview.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("openkill_ui_preview_builder", BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load preview builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LocalUIPreviewTests(unittest.TestCase):
    def test_preview_is_built_from_real_templates_and_is_local_only(self) -> None:
        builder = load_builder()
        with tempfile.TemporaryDirectory(prefix="openkill-ui-preview-") as directory:
            target = builder.build_preview(Path(directory))
            html = target.read_text(encoding="utf-8")

        self.assertIn('class="oc openkill-status-page"', html)
        self.assertIn('class="myip-main-card"', html)
        self.assertIn('data-preview-fixture="local-only"', html)
        self.assertIn('data-preview-state="running"', html)
        self.assertIn('data-preview-state="disabled"', html)
        self.assertIn('data-preview-state="error"', html)
        self.assertIn('oc-icons.js', html)
        self.assertIn('aria-busy="true"', html)
        self.assertIn("var live = state === 'running';", html)
        self.assertIn("toggle.disabled = state === 'loading' || state === 'unknown' || state === 'error';", html)
        self.assertIn("'_daip', '_mix_proxy'", html)
        self.assertIn("'_webm': 'Metacubexd'", html)
        self.assertIn("'_flush_dns_cache_btn': '清理 DNS 缓存'", html)
        self.assertNotIn("<%", html)
        self.assertNotIn("OPENKILL_DNS_ENDPOINT", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)

    def test_preview_contains_the_responsive_dashboard_hooks(self) -> None:
        source = (ROOT / "luci-app-openkill/luasrc/view/openkill/status.htm").read_text(encoding="utf-8")
        self.assertIn("dashboard-metrics-section", source)
        self.assertIn("dashboard-actions-section", source)
        self.assertIn("subscription-info-details", source)
        self.assertIn("data-preview-state", load_builder().PREVIEW_SCRIPT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
