#!/usr/bin/env python3
"""Regression tests for the canonical D2D test configuration.

The suite is local-only.  It exercises the checked-in fixture and temporary
negative cases without contacting a device or starting a Mihomo daemon.
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from openkill_nft_ir import DEFAULT_DNSMASQ_LISTEN_PORT, DEFAULT_MIHOMO_DNS_PORT, MARK_ABI
from verify_3e2_safe_config import (
    CANONICAL_CONFIG_SHA256,
    DEFAULT_CONFIG,
    VerificationError,
    load_yaml,
    scan_sensitive_material,
    validate_config,
)


class CanonicalD2DConfigTests(unittest.TestCase):
    def test_canonical_fixture_identity_and_contract(self):
        evidence = validate_config()
        self.assertEqual(evidence["sha256"], CANONICAL_CONFIG_SHA256)
        self.assertEqual(evidence["yaml"], "PASS")
        self.assertEqual(evidence["duplicate_keys"], "NONE")
        self.assertEqual(evidence["sensitive_material"], "NONE")
        self.assertEqual(evidence["semantic"]["firewall_mode1_target"], 53)
        self.assertEqual(evidence["semantic"]["dnsmasq_upstream"], "127.0.0.1#7874")
        self.assertEqual(evidence["semantic"]["mihomo_listener"], "127.0.0.1:7874")
        self.assertEqual(evidence["semantic"]["proxy_behavior"], "MATCH,DIRECT")

    def test_contract_is_sourced_from_frozen_openkill_constants(self):
        self.assertEqual(DEFAULT_DNSMASQ_LISTEN_PORT, 53)
        self.assertEqual(DEFAULT_MIHOMO_DNS_PORT, 7874)
        self.assertEqual(
            MARK_ABI,
            {
                "version": 1,
                "mark": "0x162",
                "mask": "0xffffffff",
                "route_table": 354,
                "rule_preference": 1888,
            },
        )

    def test_determinism_ten_reads(self):
        hashes = []
        summaries = []
        for _ in range(10):
            evidence = validate_config()
            hashes.append(evidence["sha256"])
            summaries.append(repr(evidence["semantic"]))
        self.assertEqual(set(hashes), {CANONICAL_CONFIG_SHA256})
        self.assertEqual(len(set(summaries)), 1)

    def test_fixture_is_inside_repository_and_has_lf_bytes(self):
        self.assertTrue(DEFAULT_CONFIG.is_relative_to(DEFAULT_CONFIG.parents[2]))
        self.assertNotIn(b"\r\n", DEFAULT_CONFIG.read_bytes())

    def test_duplicate_yaml_keys_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="openkill-3e2-negative-") as directory:
            path = pathlib.Path(directory) / "duplicate.yaml"
            path.write_text("mode: rule\nmode: rule\n", encoding="utf-8", newline="\n")
            with self.assertRaises(VerificationError):
                load_yaml(path.read_bytes(), path)

    def test_nonempty_sensitive_material_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="openkill-3e2-negative-") as directory:
            path = pathlib.Path(directory) / "secret.yaml"
            path.write_text("secret: leaked\n", encoding="utf-8", newline="\n")
            with self.assertRaises(VerificationError):
                validate_config(path, expected_hash=None)

    def test_empty_sensitive_fields_are_not_reported_as_material(self):
        self.assertEqual(scan_sensitive_material({"secret": "", "token": None}), [])
        self.assertTrue(scan_sensitive_material({"nested": {"password": "value"}}))

    def test_binary_nul_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="openkill-3e2-negative-") as directory:
            path = pathlib.Path(directory) / "nul.yaml"
            path.write_bytes(b"mode: rule\n\x00\n")
            with self.assertRaises(VerificationError):
                validate_config(path, expected_hash=None)

    def test_external_provider_url_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="openkill-3e2-negative-") as directory:
            path = pathlib.Path(directory) / "url.yaml"
            path.write_text("mode: rule\nurl: https://example.invalid/config\n", encoding="utf-8", newline="\n")
            with self.assertRaises(VerificationError):
                validate_config(path, expected_hash=None)

    def test_wrong_dns_listener_fails_contract(self):
        with tempfile.TemporaryDirectory(prefix="openkill-3e2-negative-") as directory:
            path = pathlib.Path(directory) / "wrong.yaml"
            # This is only a negative semantic fixture; the production
            # verifier never serializes or accepts this representation.
            path.write_text(
                "mode: rule\n"
                "log-level: warning\n"
                "ipv6: true\n"
                "allow-lan: false\n"
                "bind-address: 127.0.0.1\n"
                "rules:\n  - MATCH,DIRECT\n"
                "proxies: []\nproxy-groups: []\n"
                "tun:\n  enable: true\n  device: utun\n  stack: system\n"
                "  auto-route: false\n  auto-redirect: false\n"
                "  dns-hijack:\n    - any:53\n    - tcp://any:53\n"
                "dns:\n  enable: true\n  listen: 127.0.0.1:7875\n"
                "  ipv6: true\n  enhanced-mode: fake-ip\n"
                "  fake-ip-range: 198.18.0.1/16\n  nameserver:\n    - 192.0.2.53\n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaises(VerificationError):
                validate_config(path, expected_hash=None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
