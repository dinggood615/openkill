#!/usr/bin/env python3
"""Local regression checks for the OpenKill LuCI presentation contract.

These checks do not start LuCI, contact a router, or execute runtime writers.
They cover template hooks which previously caused stale CSS and a missing
subscription detail container to leave the page visually out of sync.
"""

from __future__ import annotations

import collections
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
VIEW_ROOT = ROOT / "luci-app-openkill/luasrc/view/openkill"
STATUS = VIEW_ROOT / "status.htm"
MAKEFILE = ROOT / "luci-app-openkill/Makefile"


def package_version() -> str:
    match = re.search(
        r"^PKG_VERSION:=([^\r\n]+)",
        MAKEFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not match:
        raise AssertionError("PKG_VERSION is missing")
    return match.group(1).strip()


class LuCIContractTests(unittest.TestCase):
    def test_openkill_css_uses_runtime_version_cache_buster(self) -> None:
        """Every template must invalidate CSS with the installed package version."""
        version = package_version()
        self.assertTrue(version)
        links = []
        for path in sorted(VIEW_ROOT.glob("*.htm")):
            source = path.read_text(encoding="utf-8")
            links.extend(
                (path.name, link)
                for link in re.findall(
                    r'<link\b[^>]*href="([^"]*/openkill/css/[^"]+)"',
                    source,
                )
            )
        self.assertTrue(links, "no OpenKill stylesheet links found")
        for name, link in links:
            with self.subTest(view=name, link=link):
                self.assertIn("?v=<%=plugin_version%>", link)
                self.assertNotRegex(link, r"\?v=20\d\d[-/.]")
        self.assertNotIn("?v=2026-1123", "\n".join(link for _, link in links))

    def test_status_dom_ids_are_unique_and_all_static_hooks_exist(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        ids = re.findall(r'\bid=["\']([^"\']+)', source)
        self.assertEqual(
            [value for value, count in collections.Counter(ids).items() if count > 1],
            [],
        )
        refs = re.findall(r'getElementById\(["\']([^"\']+)', source)
        self.assertEqual(sorted(set(refs) - set(ids)), [])

    def test_subscription_details_container_matches_javascript_hook(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        self.assertRegex(
            source,
            r'<div\s+id="subscription-info-details"\s+class="subscription-info-details">',
        )
        self.assertGreaterEqual(
            source.count("getElementById('subscription-info-details')"),
            4,
        )

    def test_dashboard_visibility_recovers_after_runtime_transition(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        self.assertIn("function setDashboardVisibility(element, visible)", source)
        expected = {
            "yacd": "web",
            "dashboard": "webo",
            "metacubexd": "webm",
            "zashboard": "webz",
        }
        for field, cache_name in expected.items():
            self.assertIn(
                f"setDashboardVisibility(DOMCache.{cache_name}, !!status.{field});",
                source,
            )
        self.assertIn("classList.toggle('hidden', !visible)", source)

    def test_proxy_actions_are_restored_when_address_returns(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        self.assertIn("DOMCache.copy_pac_config].forEach", source)
        self.assertIn("element.style.display = '';", source)
        self.assertIn("element.style.display = 'none';", source)

    def test_status_page_exposes_loading_and_live_state_hooks(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        self.assertIn('aria-live="polite"', source)
        self.assertIn("<%:Collecting data...%>", source)
        self.assertIn("<%:Not Running%>", source)
        self.assertIn("<%:Not Available%>", source)
        self.assertIn("status || {}", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
