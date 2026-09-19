#!/usr/bin/env python3
"""Isolated contract tests for the opt-in OpenVPN transport exception."""

from __future__ import annotations

import subprocess
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_openvpn.sh"
INIT = ROOT / "luci-app-openkill/root/etc/init.d/openkill"


def run(script: str) -> str:
    if os.name == "nt":
        script = script.replace("D:/openkill", "/mnt/d/openkill")
        command = ["wsl.exe", "--cd", "/mnt/d/openkill", "--exec", "sh", "-c", script]
        result = subprocess.run(command, text=True, capture_output=True, encoding="utf-8", errors="replace")
    else:
        result = subprocess.run(["sh", "-c", script], cwd=ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise AssertionError(f"shell fixture failed ({result.returncode}):\n{result.stdout}\n{result.stderr}")
    return result.stdout


def prepare_fixture(config: dict[str, str]) -> str:
    pairs = " ".join(f"{key}={value!r}" for key, value in config.items())
    return run(
        f"""
        set -eu
        OPENKILL_OPENVPN_DIR=$(mktemp -d)
        OPENKILL_OPENVPN_STATE="$OPENKILL_OPENVPN_DIR/state"
        trap 'rm -rf "$OPENKILL_OPENVPN_DIR"' EXIT
        uci_get_config() {{
            case "$1" in
                openvpn_compatibility) printf '%s' {config.get('openvpn_compatibility', '0')!r} ;;
                openvpn_transport_bypass) printf '%s' {config.get('openvpn_transport_bypass', '0')!r} ;;
                openvpn_role) printf '%s' {config.get('openvpn_role', 'router-client')!r} ;;
                openvpn_transport_protocol) printf '%s' {config.get('openvpn_transport_protocol', 'udp')!r} ;;
                openvpn_server_ports) printf '%s' {config.get('openvpn_server_ports', '')!r} ;;
                openvpn_server_ips) printf '%s' {config.get('openvpn_server_ips', '')!r} ;;
                openvpn_server_domains) printf '%s' {config.get('openvpn_server_domains', '')!r} ;;
                openvpn_client_ips) printf '%s' {config.get('openvpn_client_ips', '')!r} ;;
                *) printf '' ;;
            esac
        }}
        . '{HELPER.as_posix()}'
        openkill_openvpn_prepare
        test -s "$OPENKILL_OPENVPN_STATE"
        printf 'generated=%s reason=%s endpoint4=%s endpoint6=%s client4=%s client6=%s ports=%s clear=%s\\n' \\
          "$OPENKILL_OPENVPN_generated" "$OPENKILL_OPENVPN_reason" \\
          "$OPENKILL_OPENVPN_endpoint4" "$OPENKILL_OPENVPN_endpoint6" \\
          "$OPENKILL_OPENVPN_client4" "$OPENKILL_OPENVPN_client6" \\
          "$OPENKILL_OPENVPN_ports" "$OPENKILL_OPENVPN_clear"
        """
    )


def main() -> None:
    text = HELPER.read_text(encoding="utf-8")
    init = INIT.read_text(encoding="utf-8")

    valid = run(
        f"""
        set -eu
        . '{HELPER.as_posix()}'
        for value in 0.0.0.0 192.0.2.1 198.51.100.10; do openkill_openvpn_valid_ipv4 "$value"; done
        for value in :: ::1 2001:db8::1 2001:db8:0:0:0:0:0:1; do openkill_openvpn_valid_ipv6 "$value"; done
        for value in 1 1194 65535; do openkill_openvpn_valid_port "$value"; done
        ! openkill_openvpn_valid_ipv4 256.1.1.1
        ! openkill_openvpn_valid_ipv4 192.0.2
        ! openkill_openvpn_valid_ipv6 2001:::1
        ! openkill_openvpn_valid_ipv6 2001:db8:0:0:0:0:0:0:1
        ! openkill_openvpn_valid_port 0
        ! openkill_openvpn_valid_port 65536
        printf 'ok\\n'
        """
    )
    assert valid.strip() == "ok"

    generated = prepare_fixture(
        {
            "openvpn_compatibility": "1",
            "openvpn_transport_bypass": "1",
            "openvpn_role": "router-client",
            "openvpn_transport_protocol": "udp",
            "openvpn_server_ports": "1194 65536 0",
            "openvpn_server_ips": "198.51.100.10 2001:db8::1 256.1.1.1 2001:::1",
        }
    )
    assert "generated=1" in generated and "reason=generated" in generated
    assert "endpoint4=1" in generated and "endpoint6=1" in generated
    assert "ports=1194" in generated

    missing_clients = prepare_fixture(
        {
            "openvpn_compatibility": "1",
            "openvpn_transport_bypass": "1",
            "openvpn_role": "lan-client",
            "openvpn_transport_protocol": "tcp",
            "openvpn_server_ports": "443",
            "openvpn_server_ips": "198.51.100.10",
        }
    )
    assert "generated=0" in missing_clients and "reason=missing-client-scope" in missing_clients

    bad_protocol = prepare_fixture(
        {
            "openvpn_compatibility": "1",
            "openvpn_transport_bypass": "1",
            "openvpn_role": "router-client",
            "openvpn_transport_protocol": "http",
            "openvpn_server_ports": "443",
            "openvpn_server_ips": "198.51.100.10",
        }
    )
    assert "generated=0" in bad_protocol and "reason=invalid-protocol" in bad_protocol

    family_protocol = prepare_fixture(
        {
            "openvpn_compatibility": "1",
            "openvpn_transport_bypass": "1",
            "openvpn_role": "router-client",
            "openvpn_transport_protocol": "udp6",
            "openvpn_server_ports": "1194",
            "openvpn_server_ips": "2001:db8::1",
        }
    )
    assert "generated=1" in family_protocol and "endpoint6=1" in family_protocol

    disabled = prepare_fixture({"openvpn_compatibility": "0", "openvpn_transport_bypass": "0"})
    assert "generated=0" in disabled and "reason=disabled" in disabled and "clear=1" in disabled
    # A disabled transport policy may clear old runtime sets, but it must not
    # report that a new bypass rule was applied.
    assert "OPENKILL_OPENVPN_applied=0" in text
    assert "OPENKILL_OPENVPN_applied=1\n      OPENKILL_OPENVPN_reason=disabled" not in text

    retained = run(
        f"""
        set -eu
        tmp=$(mktemp -d)
        trap 'rm -rf "$tmp"' EXIT
        uci_get_config() {{
            case "$1" in
                openvpn_compatibility) printf '1' ;;
                openvpn_transport_bypass) printf '1' ;;
                openvpn_role) printf 'router-client' ;;
                openvpn_transport_protocol) printf 'udp' ;;
                openvpn_server_ports) printf 'bad-port' ;;
                openvpn_server_ips) printf 'bad-address' ;;
                *) printf '' ;;
            esac
        }}
        . '{HELPER.as_posix()}'
        OPENKILL_OPENVPN_DIR="$tmp"
        printf '198.51.100.10\n' > "$tmp/endpoints4.new"
        : > "$tmp/endpoints6.new"
        : > "$tmp/clients4.new"
        : > "$tmp/clients6.new"
        printf '1194\n' > "$tmp/ports.new"
        printf '%s\n' 'role=router-client' 'protocol=udp' > "$OPENKILL_OPENVPN_STATE"
        openkill_openvpn_prepare
        test "$OPENKILL_OPENVPN_generated" = 1
        test "$OPENKILL_OPENVPN_retained" = 1
        test "$OPENKILL_OPENVPN_reason" = invalid-retained-last-valid
        test "$OPENKILL_OPENVPN_endpoint4" = 1
        test "$OPENKILL_OPENVPN_ports" = 1194
        """
    )

    # The writer uses dedicated objects, a single checked nft transaction and
    # never converts the legacy global service-port set into OpenVPN policy.
    for name in (
        "openkill_openvpn_endpoints4",
        "openkill_openvpn_endpoints6",
        "openkill_openvpn_clients4",
        "openkill_openvpn_clients6",
        "openkill_openvpn_ports",
    ):
        assert name in text
    assert "nft -f \"$batch\"" in text
    assert "ipset swap" in text
    assert "okov4n.$$" in text
    assert 'meta l4proto $l4proto' in text
    assert 'case "${OPENKILL_OPENVPN_PROTOCOL_FAMILY:-all}"' in text
    assert "openkill_service_ports" not in text
    assert "openkill_openvpn_add_nft_rules" in init
    assert "openkill_openvpn_add_legacy_rules" in init
    assert "CENTRAL_ACTIVE" not in text
    print("openvpn compatibility contract: checks passed")


if __name__ == "__main__":
    main()
