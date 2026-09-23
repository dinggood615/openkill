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
CONFIG = ROOT / "luci-app-openkill/root/etc/config/openkill"


def require(path: Path | str, text: str) -> None:
    source = path.read_text(encoding="utf-8") if isinstance(path, Path) else path
    assert text in source, f"{text!r} missing from {path}"


def main() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    metadata = METADATA.read_text(encoding="utf-8")
    generator = GENERATOR.read_text(encoding="utf-8")
    init = INIT.read_text(encoding="utf-8")
    status = STATUS.read_text(encoding="utf-8")

    require(CONFIG, "option naive_enabled '0'")
    require(SERVERS, 'o:value("naiveproxy", "NaiveProxy")')
    require(SERVERS, '"naive_username"')
    require(SERVERS, '"naive_transport"')
    require(generator, 'type: socks5')
    require(generator, 'server: "127.0.0.1"')
    require(generator, "udp: false")
    assert 'type: naiveproxy' not in "\n".join(line for line in generator.splitlines() if not line.lstrip().startswith("#")), "unsupported native Mihomo type leaked into generator"
    require(helper, '"listen": "socks://127.0.0.1:%s"')
    require(helper, 'chmod 600 "$tmp"')
    require(helper, "sha256sum")
    require(helper, "naive_arch_ok")
    require(helper, "naive_binary_probe")
    require(helper, "tar -tf")
    require(helper, "component-not-installed")
    require(metadata, "https://api.github.com/repos/klzgrad/naiveproxy/releases/latest")
    require(metadata, "official-github-release-asset")
    require(metadata, "jsonfilter")
    require(metadata, "no-compatible-openwrt-asset")
    require(init, ". $IPKG_INSTROOT/usr/share/openkill/openkill_naive.sh")
    require(init, "procd_set_param command \"$NAIVE_BIN\" \"$config_file\"")
    require(status, "id=\"naiveproxy-status\"")
    require(status, "naive_component_installed")
    require(CONTROLLER, 'entry({"admin", "services", "openkill", "naive_component"}')
    require(CONTROLLER, 'entry({"admin", "services", "openkill", "naive_metadata"}')
    require(CONTROLLER, "action_naive_redirect")
    require(SETTINGS, '"naive_enabled"')
    require(SETTINGS, 'template = "openkill/naive_compatibility"')
    require(SETTINGS_THEME, "naiveproxy-compatibility")
    require(SETTINGS_THEME, "openkill-naive-component-info")
    require(NAIVE_VIEW, "检测并填写空缺")
    require(NAIVE_VIEW, "credentials: 'same-origin'")
    require(NAIVE_VIEW, "远端连接未验证")

    if shutil.which("wsl.exe"):
        for path in (HELPER, METADATA, GENERATOR, INIT):
            result = subprocess.run(
                ["wsl.exe", "sh", "-n", path.as_posix().replace("D:", "/mnt/d").replace("\\", "/")],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"POSIX syntax failed for {path}: {result.stderr}"

    print("NAIVEPROXY_INTEGRATION_CONTRACT=PASS")


if __name__ == "__main__":
    main()
