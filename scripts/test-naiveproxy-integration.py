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
VIEW = ROOT / "luci-app-openkill/luasrc/view/openkill/naive_compatibility.htm"
GENERATOR = ROOT / "luci-app-openkill/root/usr/share/openkill/yml_proxys_set.sh"
CONFIG = ROOT / "luci-app-openkill/root/etc/config/openkill"
NORMALIZE = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_config_normalize.sh"


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
    require(STANDALONE, "np_component_install")
    require(STANDALONE, "install URL SHA256 [SIZE]")
    # UCI appears only in the explicit, protected legacy cleanup command;
    # ordinary node/config/health paths remain independent.
    assert "np_legacy_cleanup" in standalone
    bridge = require(BRIDGE_INIT, "USE_PROCD=1")
    require(BRIDGE_INIT, "procd_set_param respawn 300 5 3")
    require(BRIDGE_INIT, "group nogroup")
    require(STANDALONE, "np_control")
    require(STANDALONE, "np_control_add")
    assert "uci" not in bridge
    openkill = require(OPENKILL_INIT, "standalone")
    assert ". openkill_naive.sh" not in openkill
    assert "openkill_naive_health.sh" not in openkill
    installer = require(INSTALLER, "install_naive_standalone_component")
    require(INSTALLER, "naiveproxy-component-metadata.sh")
    assert "install_naive_component(){" not in installer
    require(INSTALLER, "naiveproxy-bridge")
    controller = require(CONTROLLER, "action_naive_standalone_status")
    require(CONTROLLER, "/var/run/naiveproxy/manifest")
    require(CONTROLLER, "/var/run/naiveproxy/snippets.yaml")
    require(CONTROLLER, "action_naive_bridge_control")
    assert "legacy_migration" not in controller
    require(CONTROLLER, 'HTTP.formvalue("operation")')
    assert "cursor:set(\"openkill\", sid, \"naive_password\"" not in controller
    assert "cursor:set(\"openkill\", sid, \"naive_username\"" not in controller
    settings = require(SETTINGS, "_naive_component_info")
    require(SETTINGS, "openkill/naive_compatibility")
    servers = require(SERVERS, 'o:value("naiveproxy", "NaiveProxy")')
    assert '"naive_username"' not in servers and '"naive_password"' not in servers
    view = require(VIEW, "NaiveProxy 独立服务")
    require(VIEW, "刷新状态")
    require(VIEW, "naiveproxy-standalone.sh health all")
    require(VIEW, "生成 SOCKS5 YAML")
    require(VIEW, "启动服务")
    require(VIEW, "导入链接")
    require(VIEW, "粘贴 NaiveProxy 分享链接")
    require(VIEW, "data-naive-parse-link")
    require(VIEW, "data-naive-node-health")
    require(VIEW, "data-naive-node-remove")
    assert "data-naive-node-action" not in view
    assert "naive_username" not in view and "naive_password" not in view
    generator = require(GENERATOR, "independent service")
    assert "openkill_naive.sh" not in generator
    config = require(CONFIG, "independent service")
    assert "option naive_enabled" not in config and "option naive_component_path" not in config
    normalize = require(NORMALIZE, "Legacy naive_*")
    assert "set_default naive_enabled" not in normalize
    assert "uci -q set openkill.config.naive_bridge_mode" not in normalize
    assert "type: naiveproxy" not in generator
    require(STANDALONE, "np_legacy_cleanup")
    require(STANDALONE, "np_import_link")
    require(STANDALONE, "component_reason=")
    require(CONTROLLER, "component_reason")
    require(CONTROLLER, "component_detail")
    assert "zerotier = \"advanced\"" not in SETTINGS.read_text(encoding="utf-8")

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
