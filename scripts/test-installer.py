"""Host-only checks for the OpenKill installer and Mihomo download path."""
import pathlib
import subprocess
import shutil
import unittest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASH = shutil.which("bash") or "C:/Program Files/Git/bin/bash.exe"
SOURCE = (ROOT / "scripts/install-openkill.sh").read_text(encoding="utf-8")
CORE_SOURCE = (ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_core.sh").read_text(encoding="utf-8")
SETTINGS_SOURCE = (ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/settings.lua").read_text(encoding="utf-8")
SETTINGS_THEME = (ROOT / "luci-app-openkill/luasrc/view/openkill/settings_theme.htm").read_text(encoding="utf-8")
VERSION_BUMP_CHECK = ROOT / "scripts/check-version-bump.sh"

class InstallerTests(unittest.TestCase):
    def test_repository_is_reused_after_download_failure(self):
        functions = SOURCE[SOURCE.index("pm_run(){"):SOURCE.index("download(){")]
        harness = """
set -eu
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
PM=opkg
FEED_CONFIG=original
FEED_CANDIDATES="original mirror"
INSTALL_LOG=""
detail(){ :; }
log(){ :; }
die(){ return 1; }
opkg(){
  if [ "$1" = status ]; then return 1; fi
  printf '%s\\n' "$*" >> "$WORK_DIR/calls"
  case "$*" in
    "-f original install curl") return 1;;
    "-f mirror update"|"-f mirror install curl"|"-f mirror install local.ipk") return 0;;
    *) return 1;;
  esac
}
""" + functions + """
install_package_batch curl
[ "$FEED_CONFIG" = mirror ]
pm_run install local.ipk
grep -q -- '-f mirror update' "$WORK_DIR/calls"
grep -q -- '-f mirror install curl' "$WORK_DIR/calls"
grep -q -- '-f mirror install local.ipk' "$WORK_DIR/calls"
"""
        # Feed the harness through stdin.  Passing the expanded installer
        # helpers as a Windows command-line argument breaks quoting once the
        # feed de-duplication logic grows beyond the old short snippet.
        subprocess.run([BASH], input=harness, text=True, check=True)

    def test_vendor_feed_is_never_rewritten(self):
        self.assertIn("dl.openwrt.ai must remain unchanged", SOURCE)
        self.assertNotIn('s#https://dl.openwrt.ai/', SOURCE)
        self.assertIn('https://downloads.openwrt.org/', SOURCE)

    def test_local_package_does_not_require_ruby_json_manifest_module(self):
        self.assertIn('LOCAL_PACKAGE_MODE=1', SOURCE)
        self.assertIn('local package mode does not need remote manifest parsing', SOURCE)
        self.assertIn('ruby -ryaml -e', SOURCE)

    def test_installer_refreshes_databases_with_mirror_fallbacks(self):
        self.assertIn('download_databases()', SOURCE)
        self.assertIn('Country.mmdb', SOURCE)
        self.assertIn('GeoSite.dat', SOURCE)
        self.assertIn('ASN.mmdb', SOURCE)
        self.assertIn('openkill_chnroute.sh', SOURCE)
        self.assertIn('testingcf.jsdelivr.net', SOURCE)
        self.assertIn('fastly.jsdelivr.net', SOURCE)

    def test_manifest_selection_prefers_newest_version_over_fastest_stale_cdn(self):
        if not shutil.which("ruby"):
            self.skipTest("Ruby is not installed on this host")
        functions = SOURCE[SOURCE.index("validate_manifest(){"):SOURCE.index("resolve_package(){")]
        harness = """
set -eu
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
""" + functions + r'''
printf '%b\n' '2026-1015\t1\thttps://cdn.example.invalid\told.json' '2026-1050\t2\thttps://raw.example.invalid\tnew.json' > "$WORK_DIR/rows"
chosen=$(select_newest_manifest "$WORK_DIR/rows")
[ "$(printf '%s\n' "$chosen" | sed -n '1p')" = 2 ]
[ "$(printf '%s\n' "$chosen" | sed -n '2p')" = https://raw.example.invalid ]
'''
        subprocess.run([BASH], input=harness, text=True, check=True)

    def test_manifest_resolution_has_cache_busting_and_api_freshness_fallback(self):
        self.assertIn("openkill_cache_bust=", SOURCE)
        self.assertIn("version_greater()", SOURCE)
        self.assertIn("github.dpik.top/https://api.github.com", SOURCE)
        self.assertIn("gh-proxy.com/https://api.github.com", SOURCE)

    def test_core_uses_release_digest_and_no_invalid_jsdelivr_asset_path(self):
        self.assertIn('a["digest"]', CORE_SOURCE)
        self.assertIn('sha256sum "$PARTIAL_FILE"', CORE_SOURCE)
        self.assertIn('rank_core_sources()', CORE_SOURCE)
        self.assertIn('Selected fastest valid core source', CORE_SOURCE)
        self.assertIn('report_tip()', CORE_SOURCE)
        self.assertIn('--max-time 300', CORE_SOURCE)
        self.assertNotIn('MetaCubeX/mihomo@${CORE_LV}', CORE_SOURCE)
        self.assertNotIn('cdn.jsdelivr.net/gh/MetaCubeX/mihomo', CORE_SOURCE)

    def test_settings_keep_six_categories_and_embedded_update(self):
        expected = (
            's:tab("basic", translate("Runtime & Services"))',
            's:tab("network", translate("Network & Routing"))',
            's:tab("rules", translate("Rules & Subscriptions"))',
            's:tab("stability", translate("Performance & Stability"))',
            's:tab("compatibility", "兼容设置")',
            's:tab("advanced", "系统维护")',
        )
        for marker in expected:
            self.assertIn(marker, SETTINGS_SOURCE)
        self.assertEqual(SETTINGS_SOURCE.count('s:tab("'), 6)
        self.assertNotIn('s:tab("version_update"', SETTINGS_SOURCE)
        self.assertIn('version_update_panel = s:taboption("advanced"', SETTINGS_SOURCE)
        self.assertIn("local native_taboption = s.taboption", SETTINGS_SOURCE)
        self.assertIn("openkill-settings-toolbar", SETTINGS_THEME)
        self.assertIn("openkill-settings-search", SETTINGS_THEME)
        self.assertIn("openkill-advanced-collapsed", SETTINGS_THEME)
        self.assertIn("openkill-settings-card", SETTINGS_THEME)
        self.assertIn("data-openkill-cards-ready", SETTINGS_THEME)
        self.assertIn("var CARD_LAYOUTS = {", SETTINGS_THEME)
        self.assertIn("var TAB_CATEGORY_ALIASES = {", SETTINGS_THEME)
        for category in ("basic", "network", "rules", "stability", "compatibility", "advanced"):
            self.assertIn(f"{category}: [", SETTINGS_THEME)
        self.assertIn("function buildCards(tabItems, activeOnly)", SETTINGS_THEME)
        self.assertIn("var layout = category ? CARD_LAYOUTS[category] : null;", SETTINGS_THEME)
        self.assertIn("panel.setAttribute('data-openkill-cards-ready', '1')", SETTINGS_THEME)
        self.assertIn("id: 'ipv6-tun'", SETTINGS_THEME)
        self.assertIn("'native_ipv6_state'", SETTINGS_THEME)
        self.assertIn("id: 'maintenance-tools'", SETTINGS_THEME)
        self.assertIn("'version_update_panel', 'firewall_custom'", SETTINGS_THEME)
        self.assertIn("openkill-settings-card-version-update", SETTINGS_THEME)

    def test_release_pipeline_wires_outputs_and_checks_version_bump(self):
        data = yaml.safe_load((ROOT / ".github/workflows/compile_new_ipk.yml").read_text(encoding="utf-8"))
        version_job = data["jobs"]["Get-Version"]
        matrix_job = data["jobs"]["Prepare-Matrix"]
        compile_job = data["jobs"]["Compile"]
        self.assertEqual(version_job["outputs"]["current_version"], "${{ steps.current_version.outputs.version }}")
        new_version_step = next(step for step in version_job["steps"] if step.get("id") == "version")
        self.assertIn("expected YYYY-NNNN", new_version_step["run"])
        current_step = next(step for step in version_job["steps"] if step.get("id") == "current_version")
        self.assertIn("Package channel version is missing even though IPK releases exist.", current_step["run"])
        self.assertNotIn("|| true", current_step["run"])
        bump_step = next(step for step in matrix_job["steps"] if step["name"] == "Require Source Version Bump")
        self.assertEqual(bump_step["run"], 'sh scripts/check-version-bump.sh "$SOURCE_VERSION" "$RELEASED_VERSION"')
        self.assertEqual(bump_step["env"]["SOURCE_VERSION"], "${{ needs.Get-Version.outputs.version }}")
        self.assertEqual(bump_step["env"]["RELEASED_VERSION"], "${{ needs.Get-Version.outputs.current_version }}")
        self.assertEqual(matrix_job["needs"], "Get-Version")
        self.assertEqual(set(compile_job["needs"]), {"Get-Version", "Runtime-Tests", "Prepare-Matrix"})
        self.assertNotIn("if", compile_job)
        self.assertFalse(compile_job["strategy"]["fail-fast"])
        self.assertTrue(any(step.get("run") == "bash scripts/publish-package.sh" for step in compile_job["steps"]))
        self.assertNotIn("Post-Process", data["jobs"])

        for released, source, expected_returncode in (
            ("2026-1121", "2026-1122", 0),
            ("2026-1122", "2026-1122", 1),
            ("2026-1122", "2026-1120", 1),
            ("2026-9999", "2027-0001", 0),
        ):
            with self.subTest(released=released, source=source):
                result = subprocess.run(
                    [BASH, str(VERSION_BUMP_CHECK), source, released],
                    text=True, capture_output=True, check=False,
                )
                self.assertEqual(result.returncode, expected_returncode, result.stderr)
                expected_message = (
                    f"Source version {source} is greater than released version {released}"
                    if expected_returncode == 0 else
                    f"Source version {source} must be greater than released version {released}"
                )
                self.assertIn(expected_message, result.stdout + result.stderr)

    def test_shell_syntax(self):
        for name in ("install-openkill.sh", "check-version-bump.sh", "publish-package.sh"):
            subprocess.run([BASH, "-n", str(ROOT / "scripts" / name)], check=True)
        subprocess.run([BASH, "-n", str(ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_core.sh")], check=True)

if __name__ == "__main__":
    unittest.main()
