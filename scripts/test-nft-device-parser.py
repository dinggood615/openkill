#!/usr/bin/env python3
"""Local hardening tests for the three real nft forms seen on the 3E.2C device.

Everything is fixture-only.  No router, nft ruleset, or service is touched.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_nft_shadow.sh"
FIXTURE = ROOT / "scripts/fixtures/openkill-legacy-runtime-capture-device-3e2c-v1.txt"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    tail = resolved.as_posix().split(":", 1)[-1]
    return f"/mnt/{drive}/{tail.lstrip('/')}"


def quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def write_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").replace("\r", "\n").encode())


class ParserHarness:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="openkill-device-parser-")
        self.root = Path(self.temp.name)
        self.index = 0

    def close(self) -> None:
        self.temp.cleanup()

    def run(self, body: str):
        self.index += 1
        case = self.root / f"case-{self.index}"
        case.mkdir(parents=True, exist_ok=True)
        runner = case / "runner.sh"
        write_lf(
            runner,
            "#!/bin/sh\nset +e\n"
            f". {quote(wsl_path(HELPER))}\n"
            f"{body}\n",
        )
        if shutil.which("wsl.exe"):
            command = ["wsl.exe", "-u", "root", "--", "sh", wsl_path(runner)]
        else:
            command = ["sh", str(runner)]
        return subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )

    def parse(self, capture: Path):
        self.index += 1
        case = self.root / f"parse-{self.index}"
        case.mkdir(parents=True, exist_ok=True)
        intent = case / "intent"
        payload = case / "payload"
        body = (
            f"openkill_shadow_parse_nft_capture {quote(wsl_path(capture))} "
            f"{quote(wsl_path(intent))} {quote(wsl_path(payload))}; "
            "printf 'RC=%s\\n' \"$?\""
        )
        process = self.run(body)
        rc_match = re.search(r"(?:^|\n)RC=(-?\d+)", process.stdout)
        if rc_match is None:
            raise AssertionError(f"parser did not report RC: {process.stdout!r} {process.stderr!r}")
        return int(rc_match.group(1)), intent, payload, process


class DeviceNftParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = ParserHarness()
        self.text = FIXTURE.read_text(encoding="utf-8")

    def tearDown(self) -> None:
        self.harness.close()

    def test_device_fixture_source_and_three_current_forms(self) -> None:
        self.assertIn("# DEVICE_CAPTURE_FIXTURE_SOURCE=192.168.1.102_PHASE_3E2C", self.text)
        rc, intent, payload, process = self.harness.parse(FIXTURE)
        self.assertEqual(rc, 0, process.stderr)
        intent_text = intent.read_text(encoding="utf-8")
        payload_text = payload.read_text(encoding="utf-8")
        self.assertIn("HOOK\tnat_output\tnat\toutput\t-1", intent_text)
        self.assertIn("RULE\topenkill_wan_input", intent_text)
        ipv4_line = next(line for line in intent_text.splitlines() if "RULE\topenkill_wan_input" in line)
        self.assertIn("reject", ipv4_line)
        ipv6_line = next(line for line in intent_text.splitlines() if "RULE\topenkill_wan6_input" in line)
        self.assertIn("ip6", ipv6_line)
        self.assertIn("reject with icmpv6 port-unreachable", ipv6_line)
        self.assertIn("priority -1", payload_text)
        self.assertIn("reject with icmpv6 port-unreachable", payload_text)
        self.assertIn("dport { 7874, 7890, 7891, 7892, 7893, 7895, 9090 }", payload_text)
        self.assertNotIn("192.0.2.1", intent_text)
        self.assertIn("ATTACH\tdstnat", intent_text)

    def _mutated(self, name: str, text: str) -> Path:
        path = self.harness.root / f"{name}.capture"
        write_lf(path, text)
        return path

    def test_unsupported_owned_forms_fail_closed(self) -> None:
        cases = {
            "unknown-reject-subtype": self.text.replace(
                'reject comment "OpenKill WAN v4"',
                'reject with tcp reset comment "OpenKill WAN v4"',
                1,
            ),
            "unknown-priority": self.text.replace("priority filter -1", "priority filter +1", 1),
            "unknown-hook": self.text.replace("hook output", "hook input", 1),
            "unknown-policy": self.text.replace("policy accept", "policy drop", 1),
            "unknown-inline-priority": self.text.replace(
                " chain nat_output {\n  type nat hook output priority filter -1; policy accept;",
                " chain nat_output { type nat hook output priority filter +1; policy accept;",
                1,
            ),
            "unsupported-owned-match": self.text.replace(
                'th dport { 7893, 7892, 7891, 7890, 7874, 7895, 9090 } counter packets 0 bytes 0 reject',
                'meta l4proto sctp th dport { 7892 } drop',
                1,
            ),
            "malformed-multiport": self.text.replace(
                'th dport { 7893, 7892, 7891, 7890, 7874, 7895, 9090 } counter packets 0 bytes 0 reject',
                'th dport { , 7892 } counter packets 0 bytes 0 reject',
                1,
            ),
            "unknown-ipv6-reject": self.text.replace(
                "reject with icmpv6 port-unreachable",
                "reject with tcp reset",
                1,
            ),
            "v4-ipv6-family-collapse": self.text.replace(
                "th dport { 7893, 7892, 7891, 7890, 7874, 7895, 9090 } counter packets 0 bytes 0 reject",
                "ip6 nexthdr { tcp, udp } th dport { 7892 } counter packets 0 bytes 0 reject",
                1,
            ),
        }
        for name, text in cases.items():
            rc, intent, _payload, process = self.harness.parse(self._mutated(name, text))
            self.assertEqual(rc, 10, (name, process.stdout, process.stderr))
            self.assertIn("UNKNOWN_OWNED_RULE", intent.read_text(encoding="utf-8"), name)

    def test_priority_spellings_are_strictly_normalized(self) -> None:
        for spelling in ("filter -1", "filter-1", "filter - 1", "-1"):
            capture = self._mutated(f"priority-{spelling.replace(' ', '_')}", self.text.replace("filter -1", spelling, 1))
            rc, intent, _payload, process = self.harness.parse(capture)
            self.assertEqual(rc, 0, (spelling, process.stderr))
            self.assertIn("HOOK\tnat_output\tnat\toutput\t-1", intent.read_text(encoding="utf-8"))
        for expression in ("filter +1", "filter 0", "foo -1", "filter --1"):
            capture = self._mutated(f"bad-priority-{expression.replace(' ', '_')}", self.text.replace("filter -1", expression, 1))
            rc, _intent, _payload, process = self.harness.parse(capture)
            self.assertEqual(rc, 10, (expression, process.stdout, process.stderr))

    def test_handles_counters_comments_and_port_or_set_order_do_not_change_payload(self) -> None:
        rc, _intent, payload, process = self.harness.parse(FIXTURE)
        self.assertEqual(rc, 0, process.stderr)
        baseline = hashlib.sha256(payload.read_bytes()).hexdigest()
        reordered = self.text.replace(
            "{ 7893, 7892, 7891, 7890, 7874, 7895, 9090 }",
            "{ 9090, 7895, 7874, 7890, 7891, 7892, 7893 }",
            2,
        ).replace(
            "{ 7893, 7892, 53, 7892 }",
            "{ 53, 7892, 7893, 7892 }",
            1,
        )
        reordered = re.sub(r"handle (10|11|20|21|30|31|40|41)", "handle 999", reordered)
        reordered = reordered.replace("counter packets 4 bytes 320", "counter packets 400 bytes 40000")
        reordered = reordered.replace('comment "OpenKill WAN v4"', 'comment "diagnostic text changed"')
        rc, _intent, payload2, process = self.harness.parse(self._mutated("reordered", reordered))
        self.assertEqual(rc, 0, process.stderr)
        self.assertEqual(baseline, hashlib.sha256(payload2.read_bytes()).hexdigest())

    def test_rule_order_is_retained_and_changes_hash(self) -> None:
        rc, _intent, payload, process = self.harness.parse(FIXTURE)
        self.assertEqual(rc, 0, process.stderr)
        block_a = '  meta nfproto ipv4 ip protocol tcp jump openkill_output comment "device nat output" handle 10\n  meta nfproto ipv6 jump openkill_output_v6 counter packets 4 bytes 320 handle 11'
        block_b = '  meta nfproto ipv6 jump openkill_output_v6 counter packets 4 bytes 320 handle 11\n  meta nfproto ipv4 ip protocol tcp jump openkill_output comment "device nat output" handle 10'
        swapped = self._mutated("swapped-order", self.text.replace(block_a, block_b, 1))
        rc, _intent, payload2, process = self.harness.parse(swapped)
        self.assertEqual(rc, 0, process.stderr)
        self.assertNotEqual(hashlib.sha256(payload.read_bytes()).hexdigest(), hashlib.sha256(payload2.read_bytes()).hexdigest())

    def test_foreign_rule_is_ignored_and_ipv4_ipv6_rejects_remain_distinct(self) -> None:
        rc, intent, payload, process = self.harness.parse(FIXTURE)
        self.assertEqual(rc, 0, process.stderr)
        intent_text = intent.read_text(encoding="utf-8")
        payload_text = payload.read_text(encoding="utf-8")
        self.assertNotIn("192.0.2.1", intent_text)
        self.assertNotIn("192.0.2.1", payload_text)
        v4 = next(line for line in payload_text.splitlines() if "add rule inet fw4 openkill_wan_input" in line)
        v6 = next(line for line in payload_text.splitlines() if "add rule inet fw4 openkill_wan6_input" in line)
        self.assertNotEqual(v4, v6)
        self.assertIn("reject", v4)
        self.assertIn("reject with icmpv6 port-unreachable", v6)

    def test_parser_determinism_and_permuted_port_order(self) -> None:
        out = self.harness.root / "stable-intent"
        payload = self.harness.root / "stable-payload"
        fixture = wsl_path(FIXTURE)
        intent_path = wsl_path(out)
        payload_path = wsl_path(payload)
        body = (
            f"native_fixture=/tmp/openkill-device-parser-fixture-$$; "
            f"native_intent=/tmp/openkill-device-parser-intent-$$; "
            f"native_payload=/tmp/openkill-device-parser-payload-$$; "
            f"cp {quote(fixture)} \"$native_fixture\" || exit 90; "
            f"i=0; first=; while [ $i -lt 1000 ]; do "
            f"openkill_shadow_parse_nft_capture \"$native_fixture\" \"$native_intent\" \"$native_payload\" || exit 91; "
            f"h=$(sha256sum \"$native_payload\" | awk '{{print $1}}'); "
            f"[ -n \"$first\" ] || first=$h; [ \"$first\" = \"$h\" ] || exit 92; "
            "i=$((i + 1)); done; rm -f \"$native_fixture\" \"$native_intent\" \"$native_payload\"; printf 'COUNT=%s HASH=%s\\n' \"$i\" \"$first\""
        )
        process = self.harness.run(body)
        self.assertIn("COUNT=1000", process.stdout, process.stderr)
        self.assertRegex(process.stdout, r"HASH=[0-9a-f]{64}")

        permuted = []
        for i in range(100):
            ports = ["7874", "7890", "7891", "7892", "7893", "7895", "9090"]
            # Deterministic rotations stand in for the device's arbitrary set
            # display order without introducing a random source into fixtures.
            shift = i % len(ports)
            rotated = ports[shift:] + ports[:shift]
            text = self.text.replace(
                "{ 7893, 7892, 7891, 7890, 7874, 7895, 9090 }",
                "{ " + ", ".join(rotated) + " }",
                2,
            )
            path = self._mutated(f"permutation-{i:03d}", text)
            permuted.append(path)
        files = " ".join(quote(wsl_path(path)) for path in permuted)
        body = (
            "native_dir=/tmp/openkill-device-parser-permutations-$$; mkdir -p \"$native_dir\" || exit 92; "
            "copy_count=0; for f in " + files + "; do "
            "copy_count=$((copy_count + 1)); cp \"$f\" \"$native_dir/$copy_count\" || exit 92; done; "
            "first=; count=0; native_intent=/tmp/openkill-device-parser-perm-intent-$$; native_payload=/tmp/openkill-device-parser-perm-payload-$$; "
            "for f in \"$native_dir\"/*; do "
            "openkill_shadow_parse_nft_capture \"$f\" \"$native_intent\" \"$native_payload\" || exit 93; "
            "h=$(sha256sum \"$native_payload\" | awk '{print $1}'); "
            "[ -n \"$first\" ] || first=$h; [ \"$first\" = \"$h\" ] || exit 94; "
            "count=$((count + 1)); done; rm -rf \"$native_dir\" \"$native_intent\" \"$native_payload\"; printf 'PERMUTATIONS=%s HASH=%s\\n' \"$count\" \"$first\""
        )
        process = self.harness.run(body)
        self.assertIn("PERMUTATIONS=100", process.stdout, process.stderr)
        self.assertRegex(process.stdout, r"HASH=[0-9a-f]{64}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
