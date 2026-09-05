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
        subprocess.run([BASH, "-c", harness], check=True)

    def test_vendor_feed_is_never_rewritten(self):
        self.assertIn("dl.openwrt.ai must remain unchanged", SOURCE)
        self.assertNotIn('s#https://dl.openwrt.ai/', SOURCE)
        self.assertIn('https://downloads.openwrt.org/', SOURCE)

    def test_manifest_selection_prefers_newest_version_over_fastest_stale_cdn(self):
        if not shutil.which("ruby"):
            self.skipTest("Ruby is not installed on this host")
        functions = SOURCE[SOURCE.index("validate_manifest(){"):SOURCE.index("resolve_package(){")]
        harness = """
set -eu
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
""" + functions + r'''
printf '%s\n' '2026-1015\t1\thttps://cdn.example.invalid\told.json' '2026-1050\t2\thttps://raw.example.invalid\tnew.json' > "$WORK_DIR/rows"
chosen=$(select_newest_manifest "$WORK_DIR/rows")
[ "$(printf '%s\n' "$chosen" | sed -n '1p')" = 2 ]
[ "$(printf '%s\n' "$chosen" | sed -n '2p')" = https://raw.example.invalid ]
'''
        subprocess.run([BASH, "-c", harness], check=True)

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

    def test_settings_keep_five_categories_and_ui_helpers(self):
        expected = (
            's:tab("basic", translate("Basic & Runtime"))',
            's:tab("network", translate("Network & Routing"))',
            's:tab("rules", translate("Rules & Resources"))',
            's:tab("stability", translate("Stability & Performance"))',
            's:tab("advanced", translate("Advanced & Maintenance"))',
        )
        for marker in expected:
            self.assertIn(marker, SETTINGS_SOURCE)
        self.assertEqual(SETTINGS_SOURCE.count('s:tab("'), 5)
        self.assertIn("local native_taboption = s.taboption", SETTINGS_SOURCE)
        self.assertIn("openkill-settings-toolbar", SETTINGS_THEME)
        self.assertIn("openkill-settings-search", SETTINGS_THEME)
        self.assertIn("openkill-advanced-collapsed", SETTINGS_THEME)

    def test_formats_publish_inside_their_own_job(self):
        data = yaml.safe_load((ROOT / ".github/workflows/compile_new_ipk.yml").read_text(encoding="utf-8"))
        job = data["jobs"]["Compile"]
        self.assertFalse(job["strategy"]["fail-fast"])
        self.assertTrue(any(s.get("run") == "bash scripts/publish-package.sh" for s in job["steps"]))
        self.assertNotIn("Post-Process", data["jobs"])

    def test_shell_syntax(self):
        for name in ("install-openkill.sh", "publish-package.sh"):
            subprocess.run([BASH, "-n", str(ROOT / "scripts" / name)], check=True)
        subprocess.run([BASH, "-n", str(ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_core.sh")], check=True)

if __name__ == "__main__":
    unittest.main()
