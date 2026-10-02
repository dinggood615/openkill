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
CONFIG_UPLOAD = VIEW_ROOT / "config_upload.htm"
CONFIG_EDIT = VIEW_ROOT / "config_edit.htm"
CONFIG_MERGE = VIEW_ROOT / "config_merge_editor.htm"
UPDATE = VIEW_ROOT / "update.htm"
MYIP = VIEW_ROOT / "myip.htm"
LOG = VIEW_ROOT / "log.htm"
SETTINGS_THEME = VIEW_ROOT / "settings_theme.htm"
UPLOAD = VIEW_ROOT / "upload.htm"
TBLSECTION = VIEW_ROOT / "tblsection.htm"
SUB_INFO = VIEW_ROOT / "sub_info_show.htm"
MAKEFILE = ROOT / "luci-app-openkill/Makefile"
COMMON_JS = ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/js/common.js"


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
        self.assertIn(
            "setStatusVisibility(element, visible, undefined, 'hidden');",
            source,
        )
        self.assertIn("element.hidden = !shouldShow;", source)
        self.assertIn("element.setAttribute('aria-hidden', shouldShow ? 'false' : 'true');", source)

    def test_proxy_actions_are_restored_when_address_returns(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        self.assertIn("DOMCache.copy_pac_config].forEach", source)
        self.assertIn("setStatusVisibility(element, true);", source)
        self.assertIn("setStatusVisibility(element, false);", source)
        self.assertIn("element.hidden = !shouldShow;", source)
        self.assertIn("element.setAttribute('aria-hidden', shouldShow ? 'false' : 'true');", source)

    def test_status_page_exposes_loading_and_live_state_hooks(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        self.assertIn('aria-live="polite"', source)
        self.assertIn('data-runtime-state="loading"', source)
        self.assertIn('aria-busy="true"', source)
        self.assertIn("<%:Collecting data...%>", source)
        self.assertIn("<%:Not Running%>", source)
        self.assertIn("<%:Disabled%>", source)
        self.assertIn("<%:Start Failed%>", source)
        self.assertIn("<%:Unknown%>", source)
        self.assertIn("<%:Error%>", source)
        self.assertIn("<%:Not Available%>", source)
        self.assertIn("status || {}", source)

    def test_runtime_state_machine_fails_closed_for_incomplete_or_failed_status(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        self.assertIn("function classifyRuntimeState(status)", source)
        self.assertIn("typeof status.clash !== 'boolean'", source)
        self.assertIn("typeof status.service_enabled !== 'boolean'", source)
        self.assertIn("return status.service_enabled ? 'stopped' : 'disabled';", source)
        self.assertIn("status.last_start_failed === true || status.last_start_failed === '1'", source)
        self.assertIn("function setRuntimeState(status, forcedState)", source)
        self.assertIn("setRuntimeState(null, 'error');", source)
        self.assertIn("updateRuntimeProfile(null);", source)
        self.assertIn("if (runtimeState !== 'running')", source)

    def test_status_controls_have_accessible_names_and_mobile_metric_layout(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        myip = (VIEW_ROOT / "myip.htm").read_text(encoding="utf-8")
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css").read_text(encoding="utf-8")
        self.assertRegex(source, r'id="theme-toggle"[^>]+aria-label=')
        self.assertRegex(source, r'id="logo_btn"[^>]+aria-label=')
        for element_id in ("eye-icon", "mode-icon", "data-refresh-icon"):
            with self.subTest(element=element_id):
                self.assertRegex(myip, rf'id="{element_id}"[^>]+role="button"')
                self.assertRegex(myip, rf'id="{element_id}"[^>]+tabindex="0"')
                self.assertRegex(myip, rf'id="{element_id}"[^>]+aria-label=')
        self.assertIn('body[data-page="admin-services-openkill-client"] .myip-main-card', css)
        self.assertIn('grid-template-columns: repeat(2, minmax(0, 1fr));', css)
        status_css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/oc.css").read_text(encoding="utf-8")
        self.assertIn('grid-auto-rows: max-content;', css)
        self.assertIn('grid-auto-rows: max-content;', status_css)
        self.assertNotIn('--row-1-height:', status_css)
        self.assertNotIn('grid-template-rows: var(--row-1-height)', status_css)

    def test_luci_theme_adapter_is_scoped_and_has_light_dark_fallbacks(self) -> None:
        oc = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/oc.css").read_text(encoding="utf-8")
        flat = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css").read_text(encoding="utf-8")
        for token in ("--ok-theme-page", "--ok-theme-surface", "--ok-theme-text", "--ok-theme-border"):
            self.assertIn(token, oc)
        self.assertIn(":root {", oc)
        self.assertIn("--ok-luci-link", oc)
        self.assertIn("    --bg-white: var(--ok-theme-surface);", oc)
        self.assertIn(".oc,\n#cbi-openkill.openkill-settings", oc)
        self.assertIn("var(--background-color", oc)
        self.assertIn('html[data-theme="dark"]', oc)
        self.assertIn("prefers-color-scheme: dark", oc)
        self.assertIn("--ok-flat-surface", flat)
        self.assertIn('body[data-page^="admin-services-openkill"]', flat)
        self.assertNotRegex(flat, r"(?m)^body\s*\{")

    def test_settings_cards_use_one_content_sized_layout_contract(self) -> None:
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css").read_text(encoding="utf-8")
        self.assertIn('/* ===== OpenKill Stage 4: Settings Card Layout Start =====', css)
        self.assertIn('grid-auto-rows: max-content;', css)
        self.assertIn('content-visibility: visible;', css)
        self.assertNotIn('contain: layout paint;', css)
        self.assertNotIn('content-visibility: auto;', css)

    def test_source_traffic_rules_are_nested_in_traffic_routing_card(self) -> None:
        theme = SETTINGS_THEME.read_text(encoding="utf-8")
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css").read_text(encoding="utf-8")
        self.assertIn("[data-openkill-card=\"traffic-routing\"]", theme)
        self.assertIn("keepEmpty: true", theme)
        self.assertIn("data-openkill-section-kind', 'source-traffic'", theme)
        self.assertIn("openkill-source-rule-card", theme)
        self.assertIn("var sourceLabels = {", theme)
        self.assertIn("var optionName = String(controlName).split('.').pop();", theme)
        self.assertNotIn("ruleLabels[c]", theme)
        self.assertIn(".openkill-settings-card-body", theme)
        self.assertIn("target.setAttribute('data-openkill-traffic-card', 'source-traffic')", theme)
        self.assertIn("function findNetworkPanel(map, tabItems)", theme)
        self.assertIn("function retrySourceTrafficMount(map, tabItems)", theme)
        self.assertIn("window.setTimeout(function() { retrySourceTrafficMount(map, tabItems); }, 900);", theme)
        self.assertIn("!target.contains(candidateBody)", theme)
        self.assertIn("target.contains(destination)", theme)
        self.assertIn("!destination.contains(target)", theme)
        self.assertIn("cell.setAttribute('data-source-label', '操作');", theme)
        self.assertIn("data-openkill-traffic-card=\"source-traffic\"", css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", css)
        self.assertIn("tr.openkill-source-rule-card", css)
        self.assertIn("content: attr(data-source-label);", css)
        self.assertIn('source-traffic"] > h3', css)
        self.assertIn('data-source-role="serial"', css)
        self.assertIn("Source rule editor final precedence (2026-2004)", css)
        self.assertIn(".cbi-section-table > tbody", css)
        self.assertIn("source-traffic", css)
        self.assertIn("Source addresses", (ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/settings.lua").read_text(encoding="utf-8"))
        self.assertIn("Source ports", (ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/settings.lua").read_text(encoding="utf-8"))

    def test_settings_card_rhythm_and_fresh_profile_markers(self) -> None:
        theme = SETTINGS_THEME.read_text(encoding="utf-8")
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css").read_text(encoding="utf-8")
        config = (ROOT / "luci-app-openkill/root/etc/config/openkill").read_text(encoding="utf-8")
        normalizer = (ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_config_normalize.sh").read_text(encoding="utf-8")
        self.assertIn("fields.length && fields[0].parentNode === content", theme)
        self.assertIn("align-items: stretch;", css)
        self.assertIn("align-self: stretch;", css)
        self.assertIn("flex: 1 1 auto;", css)
        self.assertIn("height: auto;", css)
        self.assertIn("option default_profile 'performance-dual-stack'", config)
        self.assertIn("option default_profile_version '2026-2007'", config)
        self.assertIn("option enable_custom_dns '0'", config)
        self.assertIn("option dns_privacy_mode 'strict'", config)
        self.assertIn("option dns_privacy_group 'OpenKill-DNS'", config)
        self.assertIn("set_default default_profile performance-dual-stack", normalizer)
        self.assertIn("set_default default_profile_version 2026-2007", normalizer)
        self.assertIn("dns_privacy_mode=strict", normalizer)

    def test_security_cards_use_binary_states_and_no_unresolved_banner(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css").read_text(encoding="utf-8")
        self.assertIn('class="card-title">OpenVPN<a', source)
        self.assertIn("var vpnApplied = running && asBool(status.openvpn_applied);", source)
        self.assertIn("setCard('adblock', 'disabled', '广告规则应用失败')", source)
        self.assertIn("setCard('naiveproxy', 'disabled', naiveFailed", source)
        self.assertIn("setNotice('');", source)
        self.assertNotIn("部分功能状态尚未确认", source)
        self.assertIn(".oc.openkill-status-page .security-status-notice", css)
        self.assertIn("display: none !important;", css)
        self.assertIn("grid-template-columns: repeat(5, minmax(0, 1fr));", css)

    def test_dashboard_promotes_equal_width_entry_row_and_settings_grid(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css").read_text(encoding="utf-8")
        for hook in (
            "function arrangeDashboard()",
            "dashboard-top-row",
            "dashboard-content-layout",
            "data-dashboard-layout-ready",
            "dashboard-endpoint-card",
            "setSecurityDetail",
            "核心未运行 · 出站未验证",
            "组件可执行 · 版本未知",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, source)
        self.assertIn("grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr);", css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", css)
        self.assertIn("grid-template-rows: repeat(4, minmax(min-content, 1fr));", css)
        self.assertIn(".dashboard-content-layout > .main-card", css)
        self.assertIn('[id="container.openkill.config.network"] .openkill-settings-card-stack', css)
        self.assertIn('[id="container.openkill.config.network"] .openkill-settings-card-body', css)

    def test_standalone_naive_service_has_its_own_plugin_settings_tab(self) -> None:
        theme = SETTINGS_THEME.read_text(encoding="utf-8")
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css").read_text(encoding="utf-8")
        self.assertIn("{id: 'openvpn-compatibility'", theme)
        compatibility = theme.split("compatibility: [", 1)[1].split("advanced: [", 1)[0]
        self.assertLess(compatibility.index("{id: 'openvpn-compatibility'"), compatibility.index("{id: 'remote-service'"))
        self.assertIn("{id: 'zerotier'", theme)
        self.assertIn("{id: 'naiveproxy-service'", theme)
        remote = theme.split("{id: 'remote-service'", 1)[1].split("{id: 'zerotier'", 1)[0]
        zerotier = theme.split("{id: 'zerotier'", 1)[1].split("advanced:", 1)[0]
        self.assertNotIn("zerotier_status", remote)
        self.assertIn("'zerotier_status', 'feature_zerotier'", zerotier)
        self.assertIn("s:tab(\"naive_service\", \"NaiveProxy与服务\")", (ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/settings.lua").read_text(encoding="utf-8"))
        self.assertIn("moveExplicitFieldsToCategory(map, tabItems, 'naive_service', ['_naive_component_info'])", theme)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", css)
        self.assertIn("align-items: stretch;", css)

    def test_network_cards_and_source_theme_have_stable_order(self) -> None:
        theme = SETTINGS_THEME.read_text(encoding="utf-8")
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css").read_text(encoding="utf-8")
        network = theme.split("network: [", 1)[1].split("naive_service: [", 1)[0]
        card_order = (
            "{id: 'dns-local'",
            "{id: 'traffic-routing'",
            "{id: 'ipv6-tun'",
            "{id: 'lan-wan'",
        )
        positions = [network.index(marker) for marker in card_order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Settings UI closeout (2026-2006)", css)
        self.assertIn("var(--ok-ui-surface-muted)", css)
        self.assertIn("var(--ok-ui-border)", css)
        self.assertIn("background: transparent !important;", css)
        self.assertIn("background: var(--ok-ui-surface-muted) !important;", css)
        self.assertIn("align-items: stretch;", css)

    def test_maintenance_precedes_mihomo_in_equal_width_advanced_grid(self) -> None:
        theme = SETTINGS_THEME.read_text(encoding="utf-8")
        advanced = theme.split("advanced: [", 1)[1].split("TAB_CATEGORY_ALIASES", 1)[0]
        self.assertLess(advanced.index("{id: 'maintenance-tools'"), advanced.index("{id: 'mihomo-capabilities'"))
        self.assertNotIn("card.classList.add('openkill-settings-card-version-update')", theme)
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css").read_text(encoding="utf-8")
        self.assertIn('data-openkill-card="maintenance-tools"', css)
        self.assertIn('textarea can use the', css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", css)

    def test_dashboard_status_labels_require_backend_evidence(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        controller = (ROOT / "luci-app-openkill/luasrc/controller/openkill.lua").read_text(encoding="utf-8")
        adblock = (ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_adblock.sh").read_text(encoding="utf-8")
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css").read_text(encoding="utf-8")
        for hook in (
            "adblock_provider_effective",
            "adblock_dns_loaded",
            "adblock_core_loaded",
            "adblock_verified",
            "规则已生成 · 加载待验证",
            "传输绕过已关闭",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, source if hook not in ("adblock_provider_effective", "adblock_dns_loaded", "adblock_core_loaded", "adblock_verified") else controller)
        self.assertIn('"state=generated"', adblock)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", css)
        self.assertIn("grid-template-rows: repeat(4, minmax(min-content, 1fr));", css)

    def test_dashboard_feature_cards_use_explicit_evidence_states(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        controller = (ROOT / "luci-app-openkill/luasrc/controller/openkill.lua").read_text(encoding="utf-8")
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css").read_text(encoding="utf-8")
        for hook in (
            "var securityStates =",
            "function asBool(value)",
            "function setSecurityValue(element, state, detail, fullText, customText)",
            "element.dataset.state = state",
            "status.dns_privacy_effective",
            "naive_manifest_present",
            "setSecurityValue(DOMCache.adblock_status, 'disabled'",
            "setSecurityValue(DOMCache.openvpn_status, 'enabled'",
            "setSecurityValue(DOMCache.rustdesk_status, 'error'",
            "setSecurityValue(DOMCache.naiveproxy_status, 'pending'",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, source if hook != "naive_manifest_present" else controller)
        for state in ("is-enabled", "is-disabled", "is-pending", "is-error", "is-unknown"):
            with self.subTest(state=state):
                self.assertIn(".security-status-value." + state, css)
        self.assertIn("var labels = { enabled: '已开启', disabled: '已关闭' };", source)
        self.assertIn("security-status-notice", source)
        self.assertIn("updateSecurityCards(null, true);", source)
        self.assertIn(".security-status-detail {", css)
        self.assertIn("display: none !important;", css)

    def test_myip_shell_is_visual_only_and_aligned(self) -> None:
        source = MYIP.read_text(encoding="utf-8")
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css").read_text(encoding="utf-8")
        self.assertIn('class="oc openkill-myip-page" data-openkill-myip-shell="1"', source)
        self.assertNotIn('<fieldset class="cbi-section" data-openkill-myip-shell="1">', source)
        self.assertNotIn('<table width="100%">', source)
        for hook in (
            '.openkill-myip-page[data-openkill-myip-shell="1"]',
            ".openkill-myip-page .myip-main-card",
            "background: transparent;",
            "max-width: var(--ok-client-content-max, min(1920px, 100%)) !important;",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, css)

    def test_dns_proxy_group_is_in_dns_card_before_secondary_server(self) -> None:
        theme = SETTINGS_THEME.read_text(encoding="utf-8")
        settings = (ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/settings.lua").read_text(encoding="utf-8")
        self.assertLess(
            settings.index('"dns_privacy_group"'),
            settings.index('"enable_custom_domain_dns_server"'),
        )
        dns_layout = theme.split("{id: 'dns-local'", 1)[1].split("{id: 'ipv6-tun'", 1)[0]
        self.assertIn("'dns_privacy_group'", dns_layout)
        self.assertLess(
            dns_layout.index("'dns_privacy_group'"),
            dns_layout.index("'enable_custom_domain_dns_server'"),
        )

    def test_status_settings_are_scoped_and_generation_guarded(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        for hook in (
            "pendingBySetting",
            "confirmedValues",
            "operationSequence",
            "normalizeValue: function(setting, value)",
            "shouldApplyPoll: function(setting, value)",
            "isCurrentPending: function(setting, token)",
            "if (!self.isCurrentPending(setting, token)) return;",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, source)
        self.assertNotIn("pendingOperations.has('run_mode_' + status.run_mode)", source)
        self.assertNotIn("pendingOperations.has('rule_mode_' + status.rule_mode)", source)

    def test_hidden_config_children_use_one_visibility_contract(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        self.assertIn("setVisibility: function(element, visible, displayValue)", source)
        self.assertIn("setStatusVisibility(element, visible, displayValue, 'oc-hidden');", source)
        self.assertIn("element.hidden = !shouldShow;", source)
        self.assertIn("element.setAttribute('aria-hidden'", source)
        self.assertIn("document.activeElement.blur()", source)
        self.assertIn("this.setVisibility(detailsSection, false, 'flex');", source)

    def test_runtime_optional_children_use_hidden_and_aria_contract(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        self.assertIn("function setStatusVisibility(element, visible, displayValue, hiddenClass)", source)
        self.assertIn("setStatusVisibility(element, false);", source)
        self.assertIn("setStatusVisibility(element, visible, undefined, 'hidden');", source)
        self.assertIn("element.hidden = !shouldShow;", source)
        self.assertIn("element.setAttribute('aria-hidden', shouldShow ? 'false' : 'true');", source)
        self.assertIn("controls[i].setAttribute('aria-disabled', available ? 'false' : 'true');", source)
        self.assertIn("settingControls[j].setAttribute('aria-disabled', available ? 'false' : 'true');", source)
        self.assertNotRegex(source, r"classList\.(?:add|remove)\('(?:oc-)?hidden'\)")

    def test_segmented_controls_expose_focus_and_disabled_states(self) -> None:
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/oc.css").read_text(encoding="utf-8")
        self.assertIn(
            '.oc.openkill-status-page input[type="radio"]:focus-visible + .cbi-button-option',
            css,
        )
        self.assertIn(
            '.oc.openkill-status-page input[type="radio"]:disabled + .cbi-button-option',
            css,
        )
        self.assertIn("outline-offset: 2px;", css)
        self.assertIn("cursor: not-allowed;", css)

    def test_running_mode_uses_one_visible_segmented_control(self) -> None:
        source = STATUS.read_text(encoding="utf-8")
        self.assertIn('class="card-value mode-status-value"', source)
        self.assertIn('aria-live="polite"', source)
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/oc.css").read_text(encoding="utf-8")
        self.assertIn(".oc.openkill-status-page .mode-status-value", css)
        self.assertIn("clip-path: inset(50%);", css)

    def test_upload_conditional_children_share_visibility_and_tab_contract(self) -> None:
        source = CONFIG_UPLOAD.read_text(encoding="utf-8")
        common = COMMON_JS.read_text(encoding="utf-8")
        for hook in (
            'role="tablist"',
            'role="tabpanel"',
            'aria-controls="advanced-options-container"',
            'aria-expanded="false"',
            "setVisibility: function(element, visible, displayValue)",
            "setModeTabState: function(tab, panel, selected)",
            "this.setModeTabState(modeFileTab, modeFileContent",
            "self.setVisibility(advancedOptionsContainer, false)",
            "self.setVisibility(subConvertOptions, this.checked)",
            "tabIndex = this.value === 'custom' ? 0 : -1",
            "syncAgeEncryptionPlacement: function()",
            "this.syncAgeEncryptionPlacement();",
            "this.setVisibility(ageOptionGroup, true);",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, source)
        self.assertIn("function ocSetVisibility(element, visible, displayValue)", common)
        self.assertIn("function ocSetTabState(tab, panel, selected)", common)
        # Dynamic conditional controls must not rely on a class-only toggle.
        dynamic = source[source.index("var ConfigUploader = {") :]
        self.assertNotRegex(dynamic, r"classList\.(?:add|remove)\('oc-hidden'")

    def test_config_editor_invalidates_stale_child_loads(self) -> None:
        source = CONFIG_EDIT.read_text(encoding="utf-8")
        for hook in (
            "loadSequence: 0",
            "overwriteLoadSequence: 0",
            "var loadToken = ++this.loadSequence",
            "function isCurrentLoad()",
            "if (!isCurrentLoad()) return;",
            "var mergeToken = ++this.loadSequence",
            "function isCurrentMerge()",
            "if (!isCurrentMerge()) return;",
            "hideMergeView: function(skipLoad)",
            "if (!skipLoad) this.loadConfigContent();",
            "setOverwriteMode: function(tabFile, tabSubscribe, contentFile, contentSubscribe, mode)",
            'aria-haspopup="true" aria-expanded="false" aria-controls="${dropdownId}-panel"',
            'role="group" aria-hidden="true" hidden',
            "function setDropdownOpen(open)",
            "setDropdownOpen(!container.classList.contains('open'))",
            "setDropdownOpen(false);",
            "tab.onkeydown = activate;",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, source)
        self.assertIn("this.hideMergeView(true);", source)
        self.assertRegex(source, r"aria-selected=\"\$\{activeTab==='file'\?'true':'false'\}\"")
        self.assertIn("if (list.dataset.overwriteDragBound !== '1')", source)
        self.assertIn("list.dataset.overwriteDragBound = '1';", source)
        self.assertIn("overwrite-config-dropdown-btn:focus-visible", (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/oc.css").read_text(encoding="utf-8"))

    def test_update_custom_address_uses_scoped_visibility_and_keyboard_contract(self) -> None:
        source = UPDATE.read_text(encoding="utf-8")
        for hook in (
            'id="custom-addr-option" role="button" tabindex="0"',
            'aria-controls="customOptionInput addCustomOption"',
            'aria-expanded="false"',
            'id="customOptionInput" class="custom-option-input oc-hidden"',
            'id="addCustomOption" role="button" aria-hidden="true" tabindex="-1"',
            "function setUpdateVisibility(element, visible, hiddenClass)",
            "function setCustomAddressVisibility(visible)",
            "selectPopup.onkeydown",
            "event.key !== 'Enter' && event.key !== ' '",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, source)
        dynamic = source[source.index("function update(btn, type)") :]
        self.assertNotRegex(dynamic, r"custom(?:OptionInput|Option).*classList\.(?:add|remove)\('oc-hidden'")
        self.assertIn("setCustomAddressVisibility(false);", dynamic)
        self.assertIn("setCustomAddressVisibility(true);", dynamic)

    def test_myip_privacy_icon_keeps_visual_and_accessible_state_in_sync(self) -> None:
        source = MYIP.read_text(encoding="utf-8")
        eye_markup = source[source.index('id="eye-icon"') : source.index("</svg>", source.index('id="eye-icon"'))]
        self.assertIn('aria-pressed="false"', eye_markup)
        for hook in (
            "function updateIpInfoState(provider, state)",
            "function setIpInfoError(state)",
            "IP.get(`http://myip.ipip.net?z=${random}`, 'text', 10000)",
            "xhr.ontimeout = function()",
            "setIpRefreshState(true);",
            "function setMyIpVisibility(element, visible)",
            "setMyIpVisibility(eyeOpen, true);",
            "setMyIpVisibility(eyeClosed, false);",
            "eyeIcon.setAttribute('aria-pressed', 'false');",
            "eyeIcon.setAttribute('aria-pressed', 'true');",
            "modeIcon.setAttribute('aria-label'",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, source)

    def test_legacy_merge_tabs_and_help_use_visibility_and_selection_contract(self) -> None:
        source = CONFIG_MERGE.read_text(encoding="utf-8")
        for hook in (
            'role="tablist"',
            'id="tab-original-config" role="tab" aria-selected="true"',
            'id="tab-runtime-config" role="tab" aria-selected="false"',
            'id="oc-merge-help" class="oc-hidden" aria-hidden="true"',
            'id="oc-merge-help-normal" aria-hidden="true"',
            "function setMergeVisibility(element, visible)",
            "function setMergeTabState(tab, selected)",
            "setMergeVisibility(helpNormal, !isMerge);",
            "setMergeVisibility(helpMerge, !!isMerge);",
            "setMergeTabState(tabOriginal, true);",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, source)
        dynamic = source[source.index("function config_merge_editor(") :]
        self.assertNotRegex(dynamic, r"classList\.(?:add|remove)\('oc-hidden'")

    def test_log_tabs_keep_selected_panel_and_keyboard_state_aligned(self) -> None:
        source = LOG.read_text(encoding="utf-8")
        for hook in (
            'role="tablist"',
            'role="tab" aria-selected="true" tabindex="0"',
            'role="tab" aria-selected="false" tabindex="-1"',
            'role="tabpanel" aria-hidden="false"',
            'role="tabpanel" aria-hidden="true" hidden',
            "function setLogTabState(li, panel, selected)",
            "ocSetTabState(link, panel, !!selected);",
            "link.setAttribute('aria-controls', divs[i].id);",
            "link.onkeydown = handleTabSwitch;",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, source)

    def test_settings_cards_and_search_clear_hidden_focus(self) -> None:
        source = SETTINGS_THEME.read_text(encoding="utf-8")
        for hook in (
            "function setSearchVisibility(element, visible)",
            "element._ocSearchVisibility",
            "element.hidden = true;",
            "document.activeElement.blur()",
            "function setAdvancedTabVisibility(item, visible)",
            "body.setAttribute('aria-hidden', isExpanded ? 'false' : 'true');",
            "advancedItems.forEach(function(item)",
            "setSearchVisibility(fields[j], found);",
            "setSearchVisibility(cards[k], !query || cardMatch);",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, source)

    def test_legacy_upload_notice_uses_shared_visibility_state(self) -> None:
        source = UPLOAD.read_text(encoding="utf-8")
        self.assertIn('id="upload-result" aria-live="polite"', source)
        self.assertIn("ocSetVisibility(defaultNote, false);", source)
        self.assertIn("ocSetVisibility(result, false);", source)
        self.assertIn("ocSetVisibility(defaultNote, true);", source)
        self.assertNotRegex(source, r"classList\.(?:add|remove)\('oc-hidden'")

    def test_dynamic_table_tabs_keep_panels_and_classes_aligned(self) -> None:
        source = TBLSECTION.read_text(encoding="utf-8")
        for hook in (
            'role="tablist"',
            'role="tab" aria-selected="true" tabindex="0"',
            'role="tab" aria-selected="false" tabindex="-1"',
            'role="tabpanel" aria-hidden="false"',
            'role="tabpanel" aria-hidden="true" hidden',
            "function setTableTabState",
            "function activateTableTab",
            "tab.classList.toggle('cbi-tab', isSelected);",
            "ocSetVisibility(panel, isSelected, 'block');",
            "link.onkeydown = handleTabSwitch;",
            "tab.ontouchstart = handleTabSwitch;",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, source)
        self.assertNotIn("className = 'cbi-tab-disabled'", source)
        css = (ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/oc.css").read_text(encoding="utf-8")
        self.assertIn('cbi-tabmenu li[role="presentation"] a[role="tab"]:focus-visible', css)

    def test_subscription_summary_does_not_overwrite_base_classes(self) -> None:
        source = SUB_INFO.read_text(encoding="utf-8")
        self.assertIn('class="sub_tab openkill-subscription-summary-text"', source)
        self.assertIn('role="status" aria-live="polite" aria-hidden="true"', source)
        self.assertIn("function setSubscriptionInfoState_<%=idname%>(id, visible)", source)
        self.assertIn("element.classList.toggle('sub_tab_show', shouldShow);", source)
        self.assertIn("ocSetVisibility(element, shouldShow);", source)
        self.assertNotIn('className = "sub_tab_show"', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
