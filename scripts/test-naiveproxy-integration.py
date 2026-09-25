"""Local contract checks for the optional NaiveProxy bridge.

The test is deliberately offline. It checks the generated boundary (helper
JSON -> loopback SOCKS5 -> Mihomo) and runs POSIX syntax validation through
WSL when available; it never contacts a device or a remote server.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_naive.sh"
METADATA = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_naive_metadata.sh"
GENERATOR = ROOT / "luci-app-openkill/root/usr/share/openkill/yml_proxys_set.sh"
INIT = ROOT / "luci-app-openkill/root/etc/init.d/openkill"
STATUS = ROOT / "luci-app-openkill/luasrc/view/openkill/status.htm"
CONTROLLER = ROOT / "luci-app-openkill/luasrc/controller/openkill.lua"
SERVERS = ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/servers-config.lua"
SETTINGS = ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/settings.lua"
SETTINGS_THEME = ROOT / "luci-app-openkill/luasrc/view/openkill/settings_theme.htm"
NAIVE_VIEW = ROOT / "luci-app-openkill/luasrc/view/openkill/naive_compatibility.htm"
TBLSECTION = ROOT / "luci-app-openkill/luasrc/view/openkill/tblsection.htm"
CONFIG = ROOT / "luci-app-openkill/root/etc/config/openkill"
MAKEFILE = ROOT / "luci-app-openkill/Makefile"


def require(path: Path | str, text: str) -> None:
    source = path.read_text(encoding="utf-8") if isinstance(path, Path) else path
    assert text in source, f"{text!r} missing from {path}"


def main() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    metadata = METADATA.read_text(encoding="utf-8")
    generator = GENERATOR.read_text(encoding="utf-8")
    init = INIT.read_text(encoding="utf-8")
    status = STATUS.read_text(encoding="utf-8")
    makefile = MAKEFILE.read_text(encoding="utf-8")

    require(CONFIG, "option naive_enabled '0'")
    require(CONFIG, "option naive_bridge_mode 'auto'")
    require(SERVERS, 'o:value("naiveproxy", "NaiveProxy")')
    require(SERVERS, '"naive_username"')
    require(SERVERS, '"naive_transport"')
    require(generator, 'type: socks5')
    require(generator, 'server: "127.0.0.1"')
    require(generator, "udp: false")
    require(generator, "naive_bridge_mode")
    assert 'type: naiveproxy' not in "\n".join(line for line in generator.splitlines() if not line.lstrip().startswith("#")), "unsupported native Mihomo type leaked into generator"
    require(helper, '"listen": "socks://127.0.0.1:%s"')
    require(helper, 'chmod 600 "$tmp"')
    require(helper, "sha256sum")
    require(helper, "naive_arch_ok")
    require(helper, "naive_read_byte")
    require(helper, "naive_refresh_status")
    require(helper, "command -v hexdump")
    require(helper, "naive_binary_probe")
    require(helper, "tar -tf")
    require(helper, "component-not-installed")
    require(helper, "NAIVE_CONFIGURED_BIN")
    require(helper, "/usr/bin/naiveproxy")
    require(helper, "uci -q -X show openkill")
    require(helper, ". /lib/functions.sh")
    require(helper, "naive_port_listening")
    require(helper, "local_ready=1")
    require(helper, "*.tar.xz)")
    require(helper, "install-task")
    require(helper, "task-status")
    require(helper, "NAIVE_TASK_LOCK")
    require(helper, "naive_task_stage")
    require(helper, "command -v xz")
    require(helper, 'xz -dc "$tmp"')
    require(makefile, "+unzip +xz")
    require(metadata, "https://api.github.com/repos/klzgrad/naiveproxy/releases/latest")
    require(metadata, "official-github-release-asset")
    require(metadata, "jsonfilter")
    require(metadata, "no-compatible-openwrt-asset")
    require(init, ". $IPKG_INSTROOT/usr/share/openkill/openkill_naive.sh")
    require(init, "procd_set_param command \"$NAIVE_BIN\" \"$config_file\"")
    require(init, "procd_set_param user root")
    require(init, "procd_set_param group nogroup")
    assert init.count("uci -q -X show openkill") >= 2, "init must resolve stable server IDs for stop/start"
    require(status, "id=\"naiveproxy-status\"")
    require(status, "naive_component_installed")
    require(CONTROLLER, 'entry({"admin", "services", "openkill", "naive_component"}')
    require(CONTROLLER, 'entry({"admin", "services", "openkill", "naive_metadata"}')
    require(CONTROLLER, 'entry({"admin", "services", "openkill", "naive_bridge"}')
    require(CONTROLLER, "function action_naive_bridge()")
    require(CONTROLLER, "type: socks5")
    require(CONTROLLER, 'server = "127.0.0.1"')
    require(CONTROLLER, "udp = false")
    require(CONTROLLER, 'mode = fs.uci_get_config("config", "naive_bridge_mode")')
    bridge_section = CONTROLLER.read_text(encoding="utf-8").split("function action_naive_bridge()", 1)[1].split("function action_naive_redirect", 1)[0]
    assert "naive_username" not in bridge_section and "naive_password" not in bridge_section, "bridge preview must not expose credentials"
    require(CONTROLLER, "action_naive_redirect")
    assert 'action_naive_redirect"),"NaiveProxy"' not in CONTROLLER.read_text(encoding="utf-8"), "legacy NaiveProxy route must stay hidden from the menu"
    assert 'uci_cursor:commit("openkill")' not in CONTROLLER.read_text(encoding="utf-8").split("function action_naive_metadata()", 1)[1].split("function action_naive_component()", 1)[0], "metadata discovery must not commit UCI"
    require(SETTINGS, '"naive_enabled"')
    require(SETTINGS, '"naive_bridge_mode"')
    require(SETTINGS, 'template = "openkill/naive_compatibility"')
    require(SETTINGS_THEME, "naiveproxy-compatibility")
    require(SETTINGS_THEME, "openkill-naive-component-info")
    require(SETTINGS_THEME, "naive_bridge_mode")
    require(NAIVE_VIEW, "检测并填写空缺")
    require(NAIVE_VIEW, "一键安装 NaiveProxy")
    require(NAIVE_VIEW, "添加 NaiveProxy 节点")
    require(NAIVE_VIEW, "data-naive-node-action=\"add\"")
    require(NAIVE_VIEW, "data-naive-node-action=\"import\"")
    require(NAIVE_VIEW, "data-naive-node-modal")
    require(NAIVE_VIEW, "function openNodeModal(kind)")
    assert '<a class="cbi-button" href="<%=node_add_url%>"' not in NAIVE_VIEW.read_text(encoding="utf-8"), "Naive add must open in-page modal"
    require(NAIVE_VIEW, 'fs.uci_get_config("config", "config_path")')
    require(NAIVE_VIEW, 'current_config:sub(1, #config_prefix) == config_prefix')
    require(NAIVE_VIEW, 'fs.access(current_config) and fs.IsYamlExt(fs.basename(current_config))')
    require(NAIVE_VIEW, 'http.urlencode(current_config)')
    require(NAIVE_VIEW, '"naive_node"')
    require(NAIVE_VIEW, '请先选择配置文件')
    require(NAIVE_VIEW, "credentials: 'same-origin'")
    require(NAIVE_VIEW, "远端连接未验证")
    require(NAIVE_VIEW, "辅助组件未安装（OpenKill 插件本体可独立运行）")
    require(NAIVE_VIEW, "requestMetadata('detect', true)")
    require(NAIVE_VIEW, "return data;")
    require(NAIVE_VIEW, "operation=task-status")
    require(NAIVE_VIEW, "function pollTask(taskId)")
    require(NAIVE_VIEW, "data-naive-bridge-url")
    require(NAIVE_VIEW, "本地 SOCKS5 YAML")
    require(NAIVE_VIEW, "data-naive-bridge-copy")
    require(NAIVE_VIEW, "导入分享链接")
    require(TBLSECTION, 'self.extedit:gsub("%%s", section, 1)')
    assert ':format(section)' not in TBLSECTION.read_text(encoding="utf-8"), "encoded file query must not pass through string.format"
    require(CONTROLLER, 'operation == "task-status"')
    require(CONTROLLER, 'openkill_naive.sh install-task')

    server_url = ROOT / "luci-app-openkill/luasrc/view/openkill/server_url.htm"
    server_url_text = server_url.read_text(encoding="utf-8")
    require(server_url_text, "function parseNaiveProxy(url, sid)")
    require(server_url_text, 'case "naive+https":')
    require(server_url_text, 'case "naive+quic":')
    require(server_url_text, 'case "naiveproxy":')
    require(server_url_text, "naive_username")
    require(server_url_text, "naiveImportWarnings")
    server_manager = ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/servers.lua"
    require(server_manager, 'HTTP.formvalue("add") == "naiveproxy"')
    require(server_manager, 'HTTP.redirect(DISP.build_url("admin", "services", "openkill", "config"))')
    require(ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/servers.lua", 'edit_url .. "&type=naiveproxy"')
    require(CONTROLLER, 'function action_naive_node()')
    require(CONTROLLER, 'entry({"admin", "services", "openkill", "naive_node"}')
    require(CONTROLLER, 'cursor:set("openkill", sid, "naive_pending", "1")')
    require(ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/servers-config.lua", 'HTTP.formvalue("type") == "naiveproxy"')
    require(ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/servers-config.lua", 'o.default = "naiveproxy"')
    require(ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/servers-config.lua", 'naive_pending") == "1"')
    require(ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/servers-config.lua", 'REQUEST_METHOD") == "POST"')
    require(ROOT / "luci-app-openkill/luasrc/model/cbi/openkill/servers.lua", 'edit_url = edit_url .. "&import=1"')
    require(server_url, "import_naive_quick")
    require(server_url, "naive-quick-link-")

    if shutil.which("wsl.exe"):
        for path in (HELPER, METADATA, GENERATOR, INIT):
            result = subprocess.run(
                ["wsl.exe", "sh", "-n", path.as_posix().replace("D:", "/mnt/d").replace("\\", "/")],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            assert result.returncode == 0, f"POSIX syntax failed for {path}: {result.stderr}"

    print("NAIVEPROXY_INTEGRATION_CONTRACT=PASS")


if __name__ == "__main__":
    main()
