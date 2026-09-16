#!/usr/bin/env python3
"""Verify the canonical, direct-only D2D Mihomo configuration.

The fixture is deliberately independent from live UCI, network state, and a
router.  This module validates bytes, YAML structure, the OpenKill D2D
contract, and (when requested) a Mihomo ``-t`` run in an isolated directory.
It is a test helper; it is never imported by the OpenWrt runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

try:
    from openkill_nft_ir import (
        DEFAULT_DNSMASQ_LISTEN_PORT,
        DEFAULT_MIHOMO_DNS_PORT,
        MARK_ABI,
    )
except ImportError as error:  # pragma: no cover - only when called outside repo
    raise SystemExit(f"cannot load OpenKill contract helpers: {error}") from error

try:
    import yaml
except ImportError:  # pragma: no cover - exercised by the actionable CLI error
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "scripts" / "fixtures" / "3e2-safe.yaml"

# Updated after the fixture bytes are finalized.  The old R2A session hash is
# intentionally not reused: those bytes were not recoverable from the repo.
CANONICAL_CONFIG_SHA256 = "9cd8d91750758823776df9c982c1e15f0baa1a72baa1792fa2f82c0df4d24a6e"

D2D_CONTRACT = {
    "purpose": "REAL_DEVICE_SHADOW_SEMANTIC_TEST_ONLY",
    "direct_only": True,
    "tun": {
        "enable": True,
        "device": "utun",
        "stack": "system",
        "auto_route": False,
        "auto_redirect": False,
    },
    "ipv4": True,
    "ipv6": True,
    "dns_mode": "fake-ip",
    "firewall_mode1_target": DEFAULT_DNSMASQ_LISTEN_PORT,
    "dnsmasq_listen": DEFAULT_DNSMASQ_LISTEN_PORT,
    "dnsmasq_upstream": f"127.0.0.1#{DEFAULT_MIHOMO_DNS_PORT}",
    "mihomo_listener": f"127.0.0.1:{DEFAULT_MIHOMO_DNS_PORT}",
    "proxy_behavior": "MATCH,DIRECT",
    "fwmark": MARK_ABI["mark"],
    "fwmask": MARK_ABI["mask"],
    "route_table": MARK_ABI["route_table"],
    "rule_pref": MARK_ABI["rule_preference"],
}

_FROZEN_MARK_ABI = {
    "mark": "0x162",
    "mask": "0xffffffff",
    "route_table": 354,
    "rule_preference": 1888,
}

_SENSITIVE_KEY = re.compile(
    r"(?:password|passwd|token|secret|authorization|subscription|"
    r"proxy[-_]?provider|private[-_]?key|credential)",
    re.IGNORECASE,
)
_EXTERNAL_URL = re.compile(r"(?i)\b(?:https?|ftp|ss|vmess|vless|trojan|socks)://")
_TOP_LEVEL_KEYS = {
    "mode",
    "log-level",
    "ipv6",
    "allow-lan",
    "bind-address",
    "rules",
    "proxies",
    "proxy-groups",
    "tun",
    "dns",
}
_TUN_KEYS = {
    "enable",
    "device",
    "stack",
    "auto-route",
    "auto-redirect",
    "dns-hijack",
}
_DNS_KEYS = {
    "enable",
    "listen",
    "ipv6",
    "enhanced-mode",
    "fake-ip-range",
    "nameserver",
}


class VerificationError(ValueError):
    """A user-actionable fixture validation failure."""


if yaml is not None:

    class _UniqueKeyLoader(yaml.SafeLoader):
        """SafeLoader that rejects duplicate mapping keys."""

        pass

    def _construct_mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise VerificationError(f"duplicate YAML key: {key}")
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    _UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
    )


def _nonempty(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def _walk(value: Any, path: str = "root") -> Iterable[tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def scan_sensitive_material(data: Any) -> list[str]:
    findings: list[str] = []
    for path, value in _walk(data):
        key = path.rsplit(".", 1)[-1]
        if _SENSITIVE_KEY.search(key) and _nonempty(value):
            findings.append(f"sensitive key at {path}")
        if isinstance(value, str):
            if _EXTERNAL_URL.search(value):
                findings.append(f"external URL at {path}")
    return findings


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VerificationError(f"{name} must be a mapping")
    return value


def _exact_keys(mapping: dict[str, Any], allowed: set[str], name: str) -> None:
    unexpected = sorted(set(mapping) - allowed)
    if unexpected:
        raise VerificationError(f"unexpected {name} keys: {', '.join(unexpected)}")


def semantic_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and return the bounded human-readable semantic contract."""

    if DEFAULT_DNSMASQ_LISTEN_PORT != 53 or DEFAULT_MIHOMO_DNS_PORT != 7874:
        raise VerificationError("D2C DNS port contract drifted from 53/7874")
    if any(MARK_ABI.get(key) != value for key, value in _FROZEN_MARK_ABI.items()):
        raise VerificationError("Mark ABI contract drifted from 0x162/354/1888")
    _exact_keys(data, _TOP_LEVEL_KEYS, "top-level")
    if data.get("mode") != "rule":
        raise VerificationError("mode must be rule")
    if data.get("log-level") != "warning":
        raise VerificationError("log-level must be warning")
    if data.get("ipv6") is not True:
        raise VerificationError("top-level ipv6 must be true")
    if data.get("allow-lan") is not False:
        raise VerificationError("allow-lan must be false for the local fixture")
    if data.get("bind-address") != "127.0.0.1":
        raise VerificationError("bind-address must be 127.0.0.1")
    if data.get("rules") != ["MATCH,DIRECT"]:
        raise VerificationError("rules must contain only MATCH,DIRECT")
    if data.get("proxies") != [] or data.get("proxy-groups") != []:
        raise VerificationError("direct-only fixture must have empty proxies and groups")

    tun = _mapping(data.get("tun"), "tun")
    _exact_keys(tun, _TUN_KEYS, "tun")
    expected_tun = {
        "enable": True,
        "device": "utun",
        "stack": "system",
        "auto-route": False,
        "auto-redirect": False,
        "dns-hijack": ["any:53", "tcp://any:53"],
    }
    if tun != expected_tun:
        raise VerificationError(f"tun contract mismatch: {tun!r}")

    dns = _mapping(data.get("dns"), "dns")
    _exact_keys(dns, _DNS_KEYS, "dns")
    expected_dns = {
        "enable": True,
        "listen": "127.0.0.1:7874",
        "ipv6": True,
        "enhanced-mode": "fake-ip",
        "fake-ip-range": "198.18.0.1/16",
        "nameserver": ["192.0.2.53"],
    }
    if dns != expected_dns:
        raise VerificationError(f"dns contract mismatch: {dns!r}")

    # The firewall/dnsmasq and policy-routing values are OpenKill-owned
    # contracts; they are intentionally not invented as Mihomo YAML fields.
    return {
        "purpose": D2D_CONTRACT["purpose"],
        "direct_only": D2D_CONTRACT["direct_only"],
        "tun": {
            "enable": tun["enable"],
            "device": tun["device"],
            "stack": tun["stack"],
            "auto_route": tun["auto-route"],
            "auto_redirect": tun["auto-redirect"],
        },
        "ipv4": True,
        "ipv6": dns["ipv6"],
        "dns_mode": dns["enhanced-mode"],
        "firewall_mode1_target": D2D_CONTRACT["firewall_mode1_target"],
        "dnsmasq_listen": D2D_CONTRACT["dnsmasq_listen"],
        "dnsmasq_upstream": D2D_CONTRACT["dnsmasq_upstream"],
        "mihomo_listener": dns["listen"],
        "proxy_behavior": data["rules"][0],
        "fwmark": D2D_CONTRACT["fwmark"],
        "fwmask": D2D_CONTRACT["fwmask"],
        "route_table": D2D_CONTRACT["route_table"],
        "rule_pref": D2D_CONTRACT["rule_pref"],
    }


def load_yaml(raw: bytes, path: Path) -> dict[str, Any]:
    if yaml is None:
        raise VerificationError(
            "PyYAML is required for canonical config verification; install python3-yaml"
        )
    if b"\x00" in raw:
        raise VerificationError("config contains a binary NUL")
    try:
        data = yaml.load(raw.decode("utf-8"), Loader=_UniqueKeyLoader)
    except UnicodeDecodeError as error:
        raise VerificationError(f"config is not UTF-8: {error}") from error
    except VerificationError:
        raise
    except Exception as error:  # PyYAML parser/constructor errors
        raise VerificationError(f"invalid YAML in {path}: {error}") from error
    if not isinstance(data, dict):
        raise VerificationError("YAML document must be a mapping")
    return data


def _run_mihomo(config_bytes: bytes, binary: str | Path) -> tuple[int, str]:
    executable = shutil.which(str(binary)) or str(binary)
    with tempfile.TemporaryDirectory(prefix="openkill-3e2-config-") as directory:
        root = Path(directory)
        config = root / "config.yaml"
        config.write_bytes(config_bytes)
        try:
            result = subprocess.run(
                [executable, "-t", "-d", str(root), "-f", str(config)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return 1, str(error)
        output = (result.stdout + result.stderr).strip()
        return result.returncode, output[-1000:]


def validate_config(
    path: str | Path = DEFAULT_CONFIG,
    *,
    expected_hash: str | None = CANONICAL_CONFIG_SHA256,
    mihomo: str | Path | None = None,
    require_mihomo: bool = False,
) -> dict[str, Any]:
    """Validate one config and return bounded evidence for tests/CI."""

    config_path = Path(path).resolve()
    if not config_path.is_file():
        raise VerificationError(f"config not found: {config_path}")
    raw = config_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_hash is not None and digest != expected_hash:
        raise VerificationError(
            f"canonical SHA256 mismatch: expected {expected_hash}, got {digest}"
        )
    data = load_yaml(raw, config_path)
    findings = scan_sensitive_material(data)
    if findings:
        raise VerificationError("sensitive material detected: " + "; ".join(findings))
    summary = semantic_summary(data)

    mihomo_result = "NOT_REQUESTED"
    mihomo_output = ""
    binary = str(mihomo) if mihomo else shutil.which("mihomo")
    if binary:
        rc, output = _run_mihomo(raw, binary)
        mihomo_output = output
        if rc != 0:
            raise VerificationError(f"mihomo -t failed (rc={rc}): {output}")
        mihomo_result = "PASS"
    elif require_mihomo:
        raise VerificationError("mihomo binary is unavailable (use --mihomo or PATH)")
    else:
        mihomo_result = "NOT_AVAILABLE"

    return {
        "path": str(config_path),
        "sha256": digest,
        "bytes": len(raw),
        "yaml": "PASS",
        "duplicate_keys": "NONE",
        "sensitive_material": "NONE",
        "mihomo": mihomo_result,
        "mihomo_output": mihomo_output,
        "semantic": summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--mihomo", help="path/name of a Mihomo binary to test")
    parser.add_argument(
        "--require-mihomo",
        action="store_true",
        help="fail when no Mihomo binary is available",
    )
    parser.add_argument(
        "--allow-different-hash",
        action="store_true",
        help="validate semantics for a temporary negative fixture",
    )
    args = parser.parse_args(argv)
    try:
        evidence = validate_config(
            args.config,
            expected_hash=None if args.allow_different_hash else CANONICAL_CONFIG_SHA256,
            mihomo=args.mihomo,
            require_mihomo=args.require_mihomo,
        )
    except VerificationError as error:
        print(f"3e2-safe-config: FAIL: {error}", file=sys.stderr)
        return 1
    print(f"CANONICAL_CONFIG_PATH={evidence['path']}")
    print(f"CANONICAL_CONFIG_SHA256={evidence['sha256']}")
    print(f"CANONICAL_CONFIG_BYTES={evidence['bytes']}")
    print(f"VALID_YAML={evidence['yaml']}")
    print(f"DUPLICATE_KEYS={evidence['duplicate_keys']}")
    print(f"SENSITIVE_MATERIAL={evidence['sensitive_material']}")
    print(f"MIHOMO_VALIDATION={evidence['mihomo']}")
    print("SEMANTIC_SUMMARY=" + json.dumps(evidence["semantic"], sort_keys=True, separators=(",", ":")))
    print("D2C_DNS_53_7874_DIRECT_EQUIVALENCE=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
