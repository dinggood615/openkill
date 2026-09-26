"""Offline contract checks for the standalone NaiveProxy boundary."""

from pathlib import Path
import subprocess
import shutil

ROOT = Path(__file__).resolve().parents[1]
STANDALONE = ROOT / "luci-app-openkill/root/usr/share/openkill/naiveproxy-standalone.sh"
BRIDGE_INIT = ROOT / "luci-app-openkill/root/etc/init.d/naiveproxy-bridge"
OPENKILL_INIT = ROOT / "luci-app-openkill/root/etc/init.d/openkill"
INSTALLER = ROOT / "scripts/install-openkill.sh"
CONTROLLER = ROOT / "luci-app-openkill/luasrc/controller/openkill.lua"
SETTINGS = ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/settings.lua"
SERVERS = ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/servers-config.lua"
LEGACY_CBI = ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/naive.lua"
VIEW = ROOT / "luci-app-openkill/luasrc/view/openkill/naive_compatibility.htm"
GENERATOR = ROOT / "luci-app-openkill/root/usr/share/openkill/yml_proxys_set.sh"


def require(path: Path, value: str) -> str:
    text = path.read_text(encoding="utf-8")
    assert value in text, f"{value!r} missing from {path}"
    return text


def main() -> None:
    standalone = require(STANDALONE, "/etc/naiveproxy")
    require(STANDALONE, "socks5h://127.0.0.1")
    require(STANDALONE, "udp: false")
    require(STANDALONE, "chmod 600")
    require(STANDALONE, "component_status=available")
    require(STANDALONE, "expires_at")
    require(STANDALONE, "remote-auth-failed")
    require(STANDALONE, "NP_HEALTH_LOCK")
    assert "openkill.config" not in standalone and "uci" not in standalone
    bridge = require(BRIDGE_INIT, "USE_PROCD=1")
    require(BRIDGE_INIT, "procd_set_param respawn 300 5 3")
    require(BRIDGE_INIT, "group nogroup")
    assert "uci" not in bridge
    openkill = require(OPENKILL_INIT, "standalone")
    assert ". openkill_naive.sh" not in openkill
    assert "openkill_naive_health.sh" not in openkill
    installer = require(INSTALLER, "NaiveProxy is independent")
    assert "install_naive_component(){" not in installer
    require(INSTALLER, "naiveproxy-bridge")
    controller = require(CONTROLLER, "action_naive_standalone_status")
    require(CONTROLLER, "/var/run/naiveproxy/manifest")
    require(CONTROLLER, "/var/run/naiveproxy/snippets.yaml")
    assert "cursor:set(\"openkill\", sid, \"naive_password\"" not in controller
    assert "cursor:set(\"openkill\", sid, \"naive_username\"" not in controller
    settings = require(SETTINGS, "_naive_component_info")
    require(SETTINGS, "openkill/naive_compatibility")
    servers = require(SERVERS, 'o:value("naiveproxy", "NaiveProxy")')
    assert '"naive_username"' not in servers and '"naive_password"' not in servers
    require(LEGACY_CBI, "standalone bridge")
    view = require(VIEW, "独立辅助服务")
    require(VIEW, "刷新状态")
    require(VIEW, "naiveproxy-standalone.sh health all")
    require(VIEW, "生成 SOCKS5 YAML")
    assert "data-naive-node-action" not in view
    assert "naive_username" not in view and "naive_password" not in view
    generator = require(GENERATOR, "manual-yaml-required")
    assert "type: naiveproxy" not in generator

    if shutil.which("wsl.exe"):
        for path in (STANDALONE, BRIDGE_INIT, OPENKILL_INIT):
            result = subprocess.run(
                ["wsl.exe", "sh", "-n", path.as_posix().replace("D:", "/mnt/d").replace("\\", "/")],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            )
            assert result.returncode == 0, f"POSIX syntax failed for {path}: {result.stderr}"

    print("NAIVEPROXY_INTEGRATION_CONTRACT=PASS")


if __name__ == "__main__":
    main()
