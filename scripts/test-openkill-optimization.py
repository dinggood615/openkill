#!/usr/bin/env python3
"""Focused behavior checks for the dual-stack/DNS/adblock hardening."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "luci-app-openkill/root/etc/init.d/openkill"
CHN = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_chnroute.sh"
ADBLOCK = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_adblock.sh"
YML = ROOT / "luci-app-openkill/root/usr/share/openkill/yml_change.sh"


def posix_path(path: Path) -> str:
    value = path.as_posix()
    if os.name == "nt" and re.match(r"^[A-Za-z]:/", value):
        return "/mnt/" + value[0].lower() + value[2:]
    return value


def run_validator(function: str, content: str, family: str) -> tuple[int, str]:
    with tempfile.NamedTemporaryFile("wb", suffix=".route", dir=ROOT, delete=False) as source:
        source.write(content.replace("\r\n", "\n").encode("utf-8"))
        source_path = Path(source.name)
    script_path = source_path.with_suffix(".sh")
    script_path.write_bytes((function.replace("\r\n", "\n") + '\nvalidate_route_download "$1" "$2"\n').encode("utf-8"))
    try:
        if os.name == "nt":
            command = ["wsl.exe", "--exec", "sh", posix_path(script_path), posix_path(source_path), family]
        else:
            command = ["sh", str(script_path), str(source_path), family]
        result = subprocess.run(command, text=True, capture_output=True, timeout=30)
        return result.returncode, source_path.read_text(encoding="utf-8") if source_path.exists() else ""
    finally:
        source_path.unlink(missing_ok=True)
        script_path.unlink(missing_ok=True)


def main() -> int:
    init = INIT.read_text(encoding="utf-8")
    chn = CHN.read_text(encoding="utf-8")
    adblock = ADBLOCK.read_text(encoding="utf-8")
    yml = YML.read_text(encoding="utf-8")

    assert "apply_nft_set_file 4 china_ip_route \"$route4_file\"" in init
    assert "apply_nft_set_file 6 china_ip6_route \"$route6_file\"" in init
    assert "nft -c -f \"$batch\"" in init and "nft -f \"$batch\"" in init
    assert "nft 'flush set inet fw4 china_ip_route'" not in init
    assert "ipset -! flush china_ip_route" not in init
    assert "ip6 nexthdr" not in init[init.index("set_firewall()") : init.index("#IPTABLES")]

    marker = "validate_route_download()"
    start = chn.index(marker)
    end = chn.index('mv -f "$normalized" "$input"', start)
    end = chn.index("\n}", end) + 2
    function = chn[start:end]
    valid4 = "0.0.0.0/0\n10.0.0.0/8\n192.0.2.1/32\n"
    valid6 = "::/0\n2001:db8::/32\n2001:db8::1/128\n"
    invalid4 = "10.0.0.0/8\n300.1.1.1/24\n"
    invalid6 = "2001:db8::/32\n2001::db8::1/64\n"
    assert run_validator(function, valid4, "4")[0] == 0
    assert run_validator(function, valid6, "6")[0] == 0
    assert run_validator(function, invalid4, "4")[0] != 0
    assert run_validator(function, invalid6, "6")[0] != 0

    assert "type' => 'file'" in yml and "openkill-anti-ad.yaml" in yml
    assert "providers['openkill-anti-ad']" in yml
    assert "rules.unshift(*adblock_allow.map" not in yml
    assert "(?:https|tls|quic|h3)" in yml and "https?" not in yml[yml.index("encrypted_server") : yml.index("encrypted_server") + 180]
    assert "strict DNS privacy requires at least one selectable proxy group" in yml
    assert "provider_effective=1" in adblock and "source_sha256=" in adblock
    assert 'DEFAULT_ADBLOCK_URL="https://anti-ad.net/domains.txt"' in adblock
    assert "validate_download \"$DEFAULT_ADBLOCK_URL\"" in adblock
    assert "Configured adblock source failed; used the maintained built-in source." in adblock
    assert "https://anti-ad.net/domains.txt" in yml
    assert "provider_file=\"$provider_dir/openkill-anti-ad.yaml\"" in adblock
    assert "DEFAULT_DNSMASQ_CFGID" in adblock and "dnsmasq.conf.$DEFAULT_DNSMASQ_CFGID" in adblock
    assert "function under(domain, parent)" in adblock
    assert "!listed(domain, ok) && !listed(domain, deny)" in adblock
    assert "def openkill_insert_before_match(rules, additions)" in yml
    assert "openkill_insert_before_match(rules, rustdesk_rules)" in yml
    assert "rules.unshift(*rustdesk_rules)" not in yml
    # These Ruby literals are embedded in an outer shell double-quoted -e
    # program.  %Q keeps interpolation while preventing BusyBox ash from
    # stripping the quotes before Ruby parses the program.
    assert "%Q{DOMAIN-SUFFIX,#{domain},PASS}" in yml
    assert "%Q{DOMAIN-SUFFIX,#{domain},REJECT}" in yml
    assert "%Q{DOMAIN-SUFFIX,#{domain},DIRECT}" in yml
    assert "generated=1\\napplied=0" in yml
    assert "openkill_mark_rustdesk_applied" in init
    print("OPENKILL_OPTIMIZATION_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
