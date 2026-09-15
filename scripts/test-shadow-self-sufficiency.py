#!/usr/bin/env python3
"""Local tests for the self-contained 3E.1 runtime shadow path.

The production-capable shell observer is exercised only with fixture files.
The fake nft executable used below implements list-only reads and never has a
mutating verb.  No router, host firewall, UCI database, or service is used.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SHARE = ROOT / "luci-app-openkill/root/usr/share/openkill"
HELPER = SHARE / "openkill_nft_shadow.sh"
RENDERER = SHARE / "openkill_nft_renderer.sh"
TEMPLATE_DIR = SHARE / "shadow"
AUTO_SOURCE = SCRIPTS / "fixtures/openkill-shadow-auto-state-v1.txt"
CAPTURE = SCRIPTS / "fixtures/openkill-legacy-runtime-capture-v1.txt"
TPROXY_CAPTURE = SCRIPTS / "fixtures/openkill-legacy-runtime-capture-tproxy-v1.txt"
PRODUCTION_CAPTURE = SCRIPTS / "fixtures/openkill-legacy-runtime-capture-production-v1.txt"
MODEL = SCRIPTS / "fixtures/openkill-shadow-self-sufficiency-v1.json"
DEVICE_CAPTURE = SCRIPTS / "fixtures/openkill-legacy-runtime-capture-device-3e2c-v1.txt"

CAPTURE_CHAINS = (
    "dstnat", "mangle_prerouting", "mangle_output", "output", "srcnat",
    "input", "forward", "nat_output", "openkill", "openkill_v6",
    "openkill_mangle", "openkill_mangle_v6", "openkill_output",
    "openkill_output_v6", "openkill_mangle_output", "openkill_mangle_output_v6",
    "openkill_post", "openkill_post_v6", "openkill_dns_hijack",
    "openkill_dns_hijack_v6", "openkill_dns_redirect", "openkill_dns_redirect_v6",
    "openkill_upnp", "openkill_wan_input", "openkill_wan6_input",
)
CAPTURE_SETS = (
    "localnetwork", "localnetwork6", "openkill_node4", "openkill_node6",
    "china_ip_route", "china_ip6_route", "china_ip_route_pass",
    "china_ip6_route_pass", "openkill_access4_allow", "openkill_access4_bypass",
    "openkill_access4_deny", "openkill_access6_allow", "openkill_access6_bypass",
    "openkill_access6_deny", "openkill_service_ports", "common_ports",
    "openkill_fakeip4", "openkill_fakeip6", "openkill_lan4", "openkill_lan6",
    "openkill_delegated6", "openkill_wan_host4", "openkill_wan_host6",
)


def _wsl_path(path: Path) -> str:
    resolved = path.resolve()
    if not resolved.drive:
        return str(resolved)
    drive = resolved.drive.rstrip(":").lower()
    tail = resolved.as_posix().split(":", 1)[-1]
    return f"/mnt/{drive}/{tail.lstrip('/')}"


def _quote(value: str | Path) -> str:
    text = str(value)
    return "'" + text.replace("'", "'\"'\"'") + "'"


def _write_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").replace("\r", "\n").encode())


def _object_blocks(path: Path) -> dict[tuple[str, str], str]:
    """Return bounded OBJECT blocks keyed by their capture kind and name."""
    text = path.read_text(encoding="utf-8")
    result: dict[tuple[str, str], str] = {}
    for match in re.finditer(r"(?ms)^OBJECT\t([^\t]+)\t([^\n]+)\n.*?^OBJECT_END\n", text):
        kind, name = match.group(1), match.group(2).rstrip("\r")
        result[(kind, name)] = match.group(0)
    return result


def _status_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


class ShellFixtureHarness:
    """Run one POSIX shell script in WSL and retain fixture files."""

    _UNSET = (
        "OPENKILL_NFT_SHADOW",
        "OPENKILL_NFT_SHADOW_STATE_FILE",
        "OPENKILL_NFT_SHADOW_INPUT_FILE",
        "OPENKILL_NFT_SHADOW_OLD_INTENT_FILE",
        "OPENKILL_NFT_SHADOW_OLD_INTENT_HASH",
        "OPENKILL_NFT_SHADOW_GENERATION",
        "OPENKILL_NFT_SHADOW_GENERATION_FILE",
        "OPENKILL_NFT_SHADOW_SOURCE_FILE",
        "OPENKILL_NFT_SHADOW_AUTO_STATE_FILE",
        "OPENKILL_NFT_SHADOW_STATE_SOURCE",
        "OPENKILL_NFT_SHADOW_CAPTURE_FIXTURE",
        "OPENKILL_NFT_SHADOW_NFT_BIN",
        "OPENKILL_NFT_SHADOW_CAPTURE_NFT_BIN",
        "OPENKILL_NFT_SHADOW_CAPTURE_CHAINS",
        "OPENKILL_NFT_SHADOW_CAPTURE_SETS",
        "OPENKILL_NFT_SHADOW_CAPTURE_TRACE",
        "OPENKILL_NFT_SHADOW_RENDERER",
        "OPENKILL_NFT_SHADOW_TEMPLATE_DIR",
        "OPENKILL_NFT_SHADOW_TELEMETRY_DIR",
        "OPENKILL_NFT_SHADOW_FORCE",
        "OPENKILL_NFT_SHADOW_TIMEOUT",
        "OPENKILL_NETWORK_DESIRED",
        "OPENKILL_NETWORK_APPLIED_FILE",
        "OPENKILL_NETWORK_SNAPSHOT",
    )

    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="openkill-shadow-self-")
        self.root = Path(self.temp.name)
        self.counter = 0

    def close(self) -> None:
        self.temp.cleanup()

    def run(self, body: str, env: dict[str, str | Path | None] | None = None, timeout: int = 60):
        self.counter += 1
        case = self.root / f"case-{self.counter}"
        case.mkdir(parents=True, exist_ok=True)
        runner = case / "runner.sh"
        lines = ["#!/bin/sh", "set +e"]
        for key in self._UNSET:
            lines.append(f"unset {key}")
        for key, value in (env or {}).items():
            if value is None:
                lines.append(f"unset {key}")
            else:
                lines.append(f"export {key}={_quote(value)}")
        lines.append(f". {_quote(_wsl_path(HELPER))}")
        lines.append(body)
        _write_lf(runner, "\n".join(lines) + "\n")
        if shutil.which("wsl.exe"):
            command = ["wsl.exe", "-u", "root", "--", "sh", _wsl_path(runner)]
        else:
            command = ["sh", str(runner)]
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return process, case


class ShadowSelfSufficiencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = ShellFixtureHarness()

    def tearDown(self) -> None:
        self.harness.close()

    @staticmethod
    def _rc(process: subprocess.CompletedProcess[str]) -> int:
        for line in process.stdout.splitlines():
            if line.startswith("RC="):
                return int(line.split("=", 1)[1])
        raise AssertionError(f"shell did not report RC: {process.stdout!r} {process.stderr!r}")

    def _build(self, source: Path = AUTO_SOURCE, extra_env: dict[str, str | Path] | None = None):
        output = self.harness.root / f"build-{self.harness.counter + 1}.tsv"
        stdout = output.with_suffix(".stdout")
        stderr = output.with_suffix(".stderr")
        env: dict[str, str | Path | None] = {
            "OPENKILL_NFT_SHADOW_SOURCE_FILE": _wsl_path(source),
            "OPENKILL_NFT_SHADOW_TEMPLATE_DIR": _wsl_path(TEMPLATE_DIR),
        }
        env.update(extra_env or {})
        body = (
            f"openkill_shadow_build_auto_input {_quote(_wsl_path(output))} "
            f"> {_quote(_wsl_path(stdout))} 2> {_quote(_wsl_path(stderr))}; "
            "printf 'RC=%s\\n' \"$?\""
        )
        process, case = self.harness.run(body, env)
        return {
            "process": process,
            "case": case,
            "output": output,
            "stdout": stdout,
            "stderr": stderr,
            "rc": self._rc(process),
        }

    def _coordinator(
        self,
        source: Path = AUTO_SOURCE,
        capture: Path = CAPTURE,
        *,
        enabled: bool = True,
        renderer: Path = RENDERER,
        extra_env: dict[str, str | Path | None] | None = None,
    ) -> dict[str, object]:
        case_no = self.harness.counter + 1
        case = self.harness.root / f"coordinator-{case_no}"
        telemetry = case / "telemetry"
        stdout = case / "stdout"
        stderr = case / "stderr"
        case.mkdir(parents=True, exist_ok=True)
        env: dict[str, str | Path | None] = {
            "OPENKILL_NFT_SHADOW": "1" if enabled else "0",
            "OPENKILL_NFT_SHADOW_FORCE": "1",
            "OPENKILL_NFT_SHADOW_SOURCE_FILE": _wsl_path(source),
            "OPENKILL_NFT_SHADOW_TEMPLATE_DIR": _wsl_path(TEMPLATE_DIR),
            "OPENKILL_NFT_SHADOW_CAPTURE_FIXTURE": _wsl_path(capture),
            "OPENKILL_NFT_SHADOW_RENDERER": _wsl_path(renderer),
            "OPENKILL_NFT_SHADOW_TELEMETRY_DIR": _wsl_path(telemetry),
        }
        env.update(extra_env or {})
        body = (
            f"openkill_shadow_compare_nft > {_quote(_wsl_path(stdout))} "
            f"2> {_quote(_wsl_path(stderr))}; printf 'RC=%s\\n' \"$?\""
        )
        process, _ = self.harness.run(body, env)
        status = _status_file(telemetry / "status")
        return {
            "process": process,
            "rc": self._rc(process),
            "status": status,
            "telemetry": telemetry,
            "stdout": stdout.read_text(encoding="utf-8", errors="replace") if stdout.is_file() else "",
            "stderr": stderr.read_text(encoding="utf-8", errors="replace") if stderr.is_file() else "",
        }

    def test_contract_manifest_templates_and_source_derived_fixture(self) -> None:
        model = json.loads(MODEL.read_text(encoding="utf-8"))
        self.assertEqual(model["schema"], "OPENKILL_SHADOW_SELF_SUFFICIENCY_V1")
        self.assertEqual(model["auto_state_version"], 1)
        self.assertEqual(model["legacy_runtime_intent_version"], 1)
        self.assertFalse(model["production_bundle_required"])
        self.assertEqual(model["capture"]["inventory_schema_version"], 1)
        self.assertEqual(model["capture"]["inventory_missing_classes"]["UNKNOWN"], "not present in the formal inventory; fail closed")
        self.assertIn("dstnat", model["capture"]["required_base_chains"])
        self.assertIn("WAN_HOST_V4", model["capture"]["out_of_scope_set_ids"])
        self.assertEqual(len(model["scenarios"]), 25)
        for template in ("input_tun_v1.tsv", "input_tproxy_v1.tsv", "input_redirect_v1.tsv"):
            text = (TEMPLATE_DIR / template).read_text(encoding="utf-8")
            self.assertTrue(text.startswith("SHELL_RENDERER_INPUT_V1\t1\n"))
            self.assertNotIn("TEST_SCAFFOLD", text)
            self.assertNotIn("TEST_ONLY", text)
        self.assertTrue(PRODUCTION_CAPTURE.read_text(encoding="utf-8").startswith("LEGACY_RUNTIME_CAPTURE_V1=1\n# SOURCE=3C_EXACT_PRODUCTION_GENERATOR\n"))
        self.assertTrue(TPROXY_CAPTURE.read_text(encoding="utf-8").startswith("LEGACY_RUNTIME_CAPTURE_V1=1\n# SOURCE=PYTHON_ORACLE_TPROXY_FIXTURE\n"))

    def test_auto_producer_emits_current_v1_and_shell_renderer_accepts_it(self) -> None:
        built = self._build()
        self.assertEqual(built["rc"], 0, built["process"].stderr)
        text = built["output"].read_text(encoding="utf-8")
        self.assertTrue(text.startswith("SHELL_RENDERER_INPUT_V1\t1\n"))
        self.assertIn("META\tprofile\tcurrent", text)
        self.assertIn("META\towner\tOPENKILL", text)
        self.assertIn("META\trun_mode\tTUN", text)
        self.assertIn("META\ttproxy_port\t7895", text)
        self.assertNotIn("target", text.lower())

        output = built["output"].with_suffix(".nft")
        body = (
            f"sh {_quote(_wsl_path(RENDERER))} {_quote(_wsl_path(built['output']))} "
            f"> {_quote(_wsl_path(output))}; printf 'RC=%s\\n' \"$?\""
        )
        process, _ = self.harness.run(body)
        self.assertIn("RC=0", process.stdout)
        rendered = output.read_text(encoding="utf-8")
        self.assertIn("OPENKILL_SHELL_NFT_RENDERER_V1", rendered)
        self.assertNotIn("TEST_SCAFFOLD", rendered)

    def test_source_conflict_missing_and_unsupported_fail_closed(self) -> None:
        conflict = self.harness.root / "conflict.txt"
        _write_lf(conflict, AUTO_SOURCE.read_text(encoding="utf-8") + "PROXY_PORT=7999\n")
        self.assertEqual(self._build(conflict)["rc"], 11)

        missing = self.harness.root / "missing-port.txt"
        _write_lf(missing, "\n".join(line for line in AUTO_SOURCE.read_text(encoding="utf-8").splitlines() if not line.startswith("TPROXY_PORT=")) + "\n")
        self.assertEqual(self._build(missing)["rc"], 11)

        bad_header = self.harness.root / "bad-header.txt"
        _write_lf(bad_header, AUTO_SOURCE.read_text(encoding="utf-8").replace("OPENKILL_NFT_SHADOW_AUTO_STATE_V1=1", "UNKNOWN_STATE_V9=1", 1))
        self.assertEqual(self._build(bad_header)["rc"], 2)

        for flag in ("CURRENT_UNDEFINED=1", "BC07_UNSUPPORTED=1", "ACCESS_DENY_REQUIRED=1"):
            flagged = self.harness.root / (flag.split("=", 1)[0] + ".txt")
            _write_lf(flagged, AUTO_SOURCE.read_text(encoding="utf-8") + flag + "\n")
            self.assertEqual(self._build(flagged)["rc"], 2, flag)

    def test_committed_desired_state_fallback_does_not_require_external_bundle(self) -> None:
        desired = self.harness.root / "desired.applied"
        generation = self.harness.root / "generation"
        _write_lf(
            desired,
            """OPENKILL_FWMARK=0x162
OPENKILL_FWMASK=0xffffffff
OPENKILL_ROUTE_TABLE=354
OPENKILL_RULE_PREF=1888
LOCALNETWORK6_PREFIXES=2001:db8:700::/64
NODE4_ENDPOINTS=198.51.100.20,198.51.100.19
""",
        )
        _write_lf(generation, "applied-g1\n")
        output = self.harness.root / "desired-input.tsv"
        body = (
            f"openkill_shadow_build_auto_input {_quote(_wsl_path(output))}; printf 'RC=%s\\n' \"$?\""
        )
        process, _ = self.harness.run(
            body,
            {
                "OPENKILL_NETWORK_DESIRED": _wsl_path(desired),
                "OPENKILL_NFT_SHADOW_GENERATION_FILE": _wsl_path(generation),
                "OPENKILL_TUN_OWNER": "OPENKILL",
                "OPENKILL_RUN_MODE": "TUN",
                "OPENKILL_PROXY_PORT": "7892",
                "OPENKILL_TPROXY_PORT": "7895",
                "OPENKILL_DNS_PORT": "7874",
                "OPENKILL_ROUTER_SELF_PROXY": "0",
                "OPENKILL_FWMARK": "0x162",
                "OPENKILL_FWMASK": "0xffffffff",
                "OPENKILL_ROUTE_TABLE": "354",
                "OPENKILL_RULE_PREF": "1888",
                "OPENKILL_NFT_SHADOW_TEMPLATE_DIR": _wsl_path(TEMPLATE_DIR),
            },
        )
        self.assertIn("RC=0", process.stdout)
        text = output.read_text(encoding="utf-8")
        self.assertIn("META\towner\tOPENKILL", text)
        self.assertIn("META\tprofile\tcurrent", text)
        self.assertIn("198.51.100.19,198.51.100.20", text)

    def test_run_mode_fallback_preserves_mix_backend_contract(self) -> None:
        """The production mix value is redirect/TProxy, never native TUN."""
        desired = self.harness.root / "mix.applied"
        generation = self.harness.root / "mix.generation"
        _write_lf(generation, "mix-g1\n")
        _write_lf(
            desired,
            """OPENKILL_FWMARK=0x162
OPENKILL_FWMASK=0xffffffff
OPENKILL_ROUTE_TABLE=354
OPENKILL_RULE_PREF=1888
""",
        )
        common: dict[str, str | Path] = {
            "OPENKILL_NETWORK_DESIRED": _wsl_path(desired),
            "OPENKILL_NFT_SHADOW_GENERATION_FILE": _wsl_path(generation),
            "OPENKILL_TUN_OWNER": "OPENKILL",
            "OPENKILL_TPROXY_PORT": "7895",
            "OPENKILL_PROXY_PORT": "7892",
            "OPENKILL_DNS_PORT": "7874",
            "OPENKILL_ROUTER_SELF_PROXY": "0",
            "OPENKILL_FWMARK": "0x162",
            "OPENKILL_FWMASK": "0xffffffff",
            "OPENKILL_ROUTE_TABLE": "354",
            "OPENKILL_RULE_PREF": "1888",
            "OPENKILL_NFT_SHADOW_TEMPLATE_DIR": _wsl_path(TEMPLATE_DIR),
            "en_mode_tun": "2",
        }
        for udp_enabled, expected in (("1", "TPROXY"), ("0", "REDIRECT")):
            output = self.harness.root / f"mix-{udp_enabled}.tsv"
            body = (
                f"openkill_shadow_build_auto_input {_quote(_wsl_path(output))}; "
                "printf 'RC=%s\\n' \"$?\""
            )
            env = dict(common)
            env["enable_udp_proxy"] = udp_enabled
            process, _ = self.harness.run(body, env)
            self.assertIn("RC=0", process.stdout)
            text = output.read_text(encoding="utf-8")
            self.assertIn(f"META\trun_mode\t{expected}", text)

    def test_capture_command_allowlist_is_bounded_and_read_only(self) -> None:
        trace = self.harness.root / "nft.trace"
        capture_trace = self.harness.root / "capture.trace"
        fake_path = "/tmp/openkill-shadow-self-fake-nft-$$"
        fake_body = f"""#!/bin/sh
printf '%s\\n' \"$*\" >> {_quote(_wsl_path(trace))}
if [ \"$2\" = chain ]; then
cat <<'EOF'
table inet fw4 {{
 chain openkill {{
  ip daddr @openkill_node4 counter return
 }}
}}
EOF
else
cat <<'EOF'
table inet fw4 {{
 set openkill_node4 {{
  type ipv4_addr
  elements = {{ 198.51.100.10 }}
 }}
}}
EOF
fi
"""
        body = (
            f"fake={_quote(fake_path)}; cat > \"$fake\" <<'FAKE_NFT_EOF'\n{fake_body}FAKE_NFT_EOF\n"
            "chmod 700 \"$fake\"; export OPENKILL_NFT_SHADOW_CAPTURE_NFT_BIN=\"$fake\"; "
            f"openkill_shadow_capture_legacy_nft {_quote(_wsl_path(self.harness.root / 'capture'))}; "
            "printf 'RC=%s\\n' \"$?\"; rm -f \"$fake\""
        )
        process, _ = self.harness.run(
            body,
            {
                "OPENKILL_NFT_SHADOW_CAPTURE_CHAINS": "openkill",
                "OPENKILL_NFT_SHADOW_CAPTURE_SETS": "openkill_node4",
                "OPENKILL_NFT_SHADOW_CAPTURE_TRACE": _wsl_path(capture_trace),
            },
        )
        self.assertIn("RC=0", process.stdout)
        calls = trace.read_text(encoding="utf-8").splitlines()
        self.assertEqual(calls, ["list chain inet fw4 openkill", "list set inet fw4 openkill_node4"])
        self.assertTrue(all("ruleset" not in call and not any(verb in call.split() for verb in ("add", "insert", "replace", "delete", "flush", "reset", "destroy")) for call in calls))
        captured = (self.harness.root / "capture").read_text(encoding="utf-8")
        self.assertTrue(captured.startswith("LEGACY_RUNTIME_CAPTURE_V1=1\n"))
        self.assertIn("OBJECT\tchain\topenkill", captured)

    def test_capture_parser_normalizes_and_foreign_rules_are_not_claimed(self) -> None:
        intent = self.harness.root / "intent"
        payload = self.harness.root / "payload"
        body = (
            f"openkill_shadow_parse_nft_capture {_quote(_wsl_path(CAPTURE))} "
            f"{_quote(_wsl_path(intent))} {_quote(_wsl_path(payload))}; printf 'RC=%s\\n' \"$?\""
        )
        process, _ = self.harness.run(body)
        self.assertIn("RC=0", process.stdout)
        intent_text = intent.read_text(encoding="utf-8")
        payload_text = payload.read_text(encoding="utf-8")
        self.assertTrue(intent_text.startswith("LEGACY_RUNTIME_INTENT_V1=1\n"))
        self.assertIn("HOOK\tnat_output\tnat\toutput\t-1", intent_text)
        self.assertNotIn("handle 123", payload_text)
        self.assertNotIn("counter packets", payload_text)
        self.assertIn("add set inet fw4 openkill_node4", payload_text)

        foreign = self.harness.root / "foreign.capture"
        _write_lf(
            foreign,
            """LEGACY_RUNTIME_CAPTURE_V1=1
OBJECT\tchain\tdstnat
table inet fw4 {
 chain dstnat {
  ip daddr 192.0.2.1 return
  jump openkill_dns_redirect
 }
}
OBJECT_END
OBJECT\tchain\topenkill_dns_redirect
table inet fw4 {
 chain openkill_dns_redirect {
  udp dport 53 redirect to :7874
 }
}
OBJECT_END
""",
        )
        foreign_intent = self.harness.root / "foreign.intent"
        foreign_payload = self.harness.root / "foreign.payload"
        body = (
            f"openkill_shadow_parse_nft_capture {_quote(_wsl_path(foreign))} "
            f"{_quote(_wsl_path(foreign_intent))} {_quote(_wsl_path(foreign_payload))}; printf 'RC=%s\\n' \"$?\""
        )
        process, _ = self.harness.run(body)
        self.assertIn("RC=0", process.stdout)
        normalized = foreign_intent.read_text(encoding="utf-8")
        self.assertNotIn("192.0.2.1", normalized)
        self.assertIn("ATTACH\tdstnat", normalized)

    def test_unknown_owned_rule_fails_closed(self) -> None:
        bad = self.harness.root / "unknown.capture"
        text = CAPTURE.read_text(encoding="utf-8")
        text = text.replace("chain nat_output {\n", "chain nat_output {\n  unknown verdict expression\n", 1)
        _write_lf(bad, text)
        intent = self.harness.root / "intent"
        payload = self.harness.root / "payload"
        body = (
            f"openkill_shadow_parse_nft_capture {_quote(_wsl_path(bad))} "
            f"{_quote(_wsl_path(intent))} {_quote(_wsl_path(payload))}; printf 'RC=%s\\n' \"$?\""
        )
        process, _ = self.harness.run(body)
        self.assertIn("RC=10", process.stdout)
        self.assertIn("UNKNOWN_OWNED_RULE", intent.read_text(encoding="utf-8"))

    def _conditional_inventory_capture(self, *, mutate_dns: bool = True) -> Path:
        """Build the sanitized 3E.2D2A shape: 15 chains, 9 sets, 24 misses."""
        blocks = _object_blocks(DEVICE_CAPTURE)
        blocks.update(_object_blocks(CAPTURE))
        present_chains = (
            "nat_output", "dstnat", "openkill_output", "openkill_output_v6",
            "openkill_dns_redirect", "openkill_wan_input", "openkill_wan6_input",
            "mangle_prerouting", "mangle_output", "output", "srcnat", "input",
            "forward", "openkill_upnp", "openkill_mangle",
        )
        present_sets = (
            "openkill_service_ports", "localnetwork", "localnetwork6",
            "openkill_node4", "openkill_node6", "china_ip_route", "china_ip6_route",
            "china_ip_route_pass", "china_ip6_route_pass",
        )
        lines = [
            "LEGACY_RUNTIME_CAPTURE_V1=1\n",
            "# DEVICE_CAPTURE_FIXTURE_SOURCE=192.168.1.102_PHASE_3E2D2A\n",
            "# Sanitized: no private addresses, MACs, node endpoints, or credentials.\n",
        ]
        for name in present_chains:
            block = blocks.get(("chain", name))
            if block is None:
                self.assertIn(name, {"mangle_prerouting", "mangle_output", "output", "srcnat", "input", "forward"})
                block = (
                    f"OBJECT\tchain\t{name}\n"
                    "table inet fw4 {\n"
                    f" chain {name} {{\n"
                    " }\n"
                    "}\n"
                    "OBJECT_END\n"
                )
            if mutate_dns and name == "openkill_dns_redirect":
                block = block.replace(":7874", ":53")
            lines.append(block)
        for name in present_sets:
            block = blocks.get(("set", name))
            self.assertIsNotNone(block, name)
            lines.append(block)
        for name in CAPTURE_CHAINS:
            if name not in present_chains:
                lines.append(f"MISSING\tchain\t{name}\n")
        for name in CAPTURE_SETS:
            if name not in present_sets:
                lines.append(f"MISSING\tset\t{name}\n")
        output = self.harness.root / "device-3e2d2a.capture"
        _write_lf(output, "".join(lines))
        return output

    def test_conditional_inventory_missing_reaches_comparator(self) -> None:
        capture = self._conditional_inventory_capture()
        result = self._coordinator(capture=capture)
        self.assertEqual(result["rc"], 1, result)
        self.assertEqual(result["status"].get("status"), "MISMATCH")
        status = result["status"]
        self.assertEqual(status.get("inventory_missing_count"), "24")
        self.assertEqual(status.get("inventory_schema_version"), "1")
        self.assertEqual(status.get("inventory_missing_summary"), "required=0 conditional=22 inactive=0 optional=0 out_of_scope=2 unknown=0")
        self.assertEqual(status.get("required_missing_count"), "0")
        self.assertEqual(status.get("conditional_missing_count"), "22")
        self.assertEqual(status.get("out_of_scope_missing_count"), "2")

    def test_conditional_inventory_stable_five_cycles(self) -> None:
        capture = self._conditional_inventory_capture()
        actual_hashes: set[str] = set()
        central_hashes: set[str] = set()
        continuity_hashes: set[str] = set()
        for _ in range(5):
            result = self._coordinator(capture=capture)
            self.assertEqual(result["rc"], 1)
            status = result["status"]
            self.assertEqual(status.get("status"), "MISMATCH")
            actual_hashes.add(status.get("old_hash", ""))
            central_hashes.add(status.get("new_hash", ""))
            # Fixture-backed runs intentionally use the legacy generation
            # field; production live-source runs expose the additive
            # continuity_token field.  Either way the continuity identity
            # must remain stable across all five coordinator processes.
            continuity_hashes.add(status.get("continuity_token", status.get("generation", "")))
        self.assertEqual(len(actual_hashes), 1)
        self.assertEqual(len(central_hashes), 1)
        self.assertEqual(len(continuity_hashes), 1)
        self.assertNotIn("", actual_hashes)
        self.assertNotIn("", central_hashes)
        self.assertNotIn("", continuity_hashes)

    def test_missing_required_capture_object_fails_closed(self) -> None:
        missing = self.harness.root / "missing.capture"
        _write_lf(
            missing,
            "MISSING\tchain\tnat_output\n" + CAPTURE.read_text(encoding="utf-8"),
        )
        result = self._coordinator(capture=missing)
        self.assertEqual(result["rc"], 9)
        self.assertEqual(result["status"].get("status"), "CAPTURE_ERROR")
        self.assertEqual(result["status"].get("reason"), "required-current-missing")
        self.assertEqual(result["status"].get("required_missing_count"), "1")
        self.assertEqual(result["status"].get("conditional_missing_count"), "0")

        missing_multiple = self.harness.root / "missing-multiple.capture"
        _write_lf(
            missing_multiple,
            "MISSING\tchain\tnat_output\nMISSING\tchain\tdstnat\n" + CAPTURE.read_text(encoding="utf-8"),
        )
        result = self._coordinator(capture=missing_multiple)
        self.assertEqual(result["rc"], 9)
        self.assertEqual(result["status"].get("required_missing_count"), "2")
        self.assertEqual(result["status"].get("reason"), "required-current-missing")

    def test_conditional_missing_matrix_and_inventory_evidence(self) -> None:
        cases = {
            "single-chain": "MISSING\tchain\topenkill_output\n",
            "multiple-chains": "MISSING\tchain\topenkill_output\nMISSING\tchain\topenkill_post\n",
            "single-set": "MISSING\tset\topenkill_access4_allow\n",
            "multiple-sets": "MISSING\tset\topenkill_access4_allow\nMISSING\tset\tcommon_ports\n",
        }
        for name, prefix in cases.items():
            capture = self.harness.root / f"{name}.capture"
            _write_lf(capture, prefix + CAPTURE.read_text(encoding="utf-8"))
            result = self._coordinator(capture=capture)
            self.assertEqual(result["rc"], 0, name)
            self.assertEqual(result["status"].get("status"), "MATCH", name)
            self.assertEqual(result["status"].get("required_missing_count"), "0", name)
        all_missing = self._conditional_inventory_capture(mutate_dns=False)
        result = self._coordinator(capture=all_missing)
        self.assertEqual(result["rc"], 1)
        self.assertEqual(result["status"].get("status"), "MISMATCH")
        self.assertEqual(result["status"].get("inventory_missing_count"), "24")

    def test_inactive_mode_and_optional_inventory_classification(self) -> None:
        inactive = self.harness.root / "inactive.capture"
        _write_lf(inactive, "MISSING\tchain\topenkill_tproxy\n" + CAPTURE.read_text(encoding="utf-8"))
        result = self._coordinator(capture=inactive)
        self.assertEqual(result["rc"], 0)
        self.assertEqual(result["status"].get("inactive_missing_count"), "1")

        optional = self.harness.root / "optional.capture"
        _write_lf(optional, "MISSING\tchain\topenkill_upnp\n" + CAPTURE.read_text(encoding="utf-8"))
        result = self._coordinator(capture=optional)
        self.assertEqual(result["rc"], 0)
        self.assertEqual(result["status"].get("optional_missing_count"), "1")

        tproxy_source = self.harness.root / "tproxy-source.txt"
        _write_lf(tproxy_source, AUTO_SOURCE.read_text(encoding="utf-8").replace("RUN_MODE=TUN", "RUN_MODE=TPROXY", 1))
        active_tproxy = self.harness.root / "active-tproxy.capture"
        _write_lf(active_tproxy, "MISSING\tchain\topenkill_tproxy\n" + CAPTURE.read_text(encoding="utf-8"))
        result = self._coordinator(source=tproxy_source, capture=active_tproxy)
        self.assertEqual(result["rc"], 9)
        self.assertEqual(result["status"].get("required_missing_count"), "1")

        redirect_source = self.harness.root / "redirect-source.txt"
        _write_lf(redirect_source, AUTO_SOURCE.read_text(encoding="utf-8").replace("RUN_MODE=TUN", "RUN_MODE=REDIRECT", 1))
        inactive_redirect = self.harness.root / "inactive-redirect.capture"
        _write_lf(inactive_redirect, "MISSING\tchain\topenkill_tproxy\n" + CAPTURE.read_text(encoding="utf-8"))
        result = self._coordinator(source=redirect_source, capture=inactive_redirect)
        self.assertEqual(result["rc"], 1)
        self.assertEqual(result["status"].get("status"), "MISMATCH")
        self.assertEqual(result["status"].get("inactive_missing_count"), "1")

    def test_unknown_duplicate_and_command_failures_fail_closed(self) -> None:
        unknown = self.harness.root / "unknown-inventory.capture"
        _write_lf(unknown, "MISSING\tchain\tnot_in_current_schema\n" + CAPTURE.read_text(encoding="utf-8"))
        result = self._coordinator(capture=unknown)
        self.assertEqual(result["rc"], 9)
        self.assertEqual(result["status"].get("reason"), "inventory-object-unknown")
        self.assertEqual(result["status"].get("unknown_missing_count"), "1")

        duplicate = self.harness.root / "duplicate-inventory.capture"
        _write_lf(duplicate, "MISSING\tchain\topenkill_output\nMISSING\tchain\topenkill_output\n" + CAPTURE.read_text(encoding="utf-8"))
        result = self._coordinator(capture=duplicate)
        self.assertEqual(result["rc"], 9)
        self.assertEqual(result["status"].get("reason"), "inventory-duplicate-entry")

        for code, label, diagnostic, expected_rc in (
            (13, "permission", "Operation not permitted", 9),
            (2, "syntax", "syntax error", 9),
            (1, "absent", "No such file or directory", 0),
        ):
            fake = self.harness.root / f"nft-{label}.sh"
            _write_lf(fake, f"#!/bin/sh\nprintf '%s\\n' {_quote(diagnostic)} >&2\nexit {code}\n")
            output = self.harness.root / f"capture-{label}.txt"
            trace = self.harness.root / f"trace-{label}.txt"
            body = (
                f"openkill_shadow_capture_legacy_nft {_quote(_wsl_path(output))}; "
                "printf 'RC=%s\\n' \"$?\""
            )
            process, _ = self.harness.run(
                body,
                {
                    "OPENKILL_NFT_SHADOW_CAPTURE_NFT_BIN": _wsl_path(fake),
                    "OPENKILL_NFT_SHADOW_CAPTURE_CHAINS": "openkill_output",
                    "OPENKILL_NFT_SHADOW_CAPTURE_SETS": "openkill_service_ports",
                    "OPENKILL_NFT_SHADOW_CAPTURE_TRACE": _wsl_path(trace),
                },
            )
            self.assertIn(f"RC={expected_rc}", process.stdout, label)
            trace_text = trace.read_text(encoding="utf-8")
            if expected_rc:
                self.assertIn("command-error", trace_text, label)
            else:
                self.assertIn("missing", trace_text, label)

    def test_tproxy_capture_keeps_transport_family_port_and_mark(self) -> None:
        intent = self.harness.root / "tproxy.intent"
        payload = self.harness.root / "tproxy.payload"
        body = (
            f"openkill_shadow_parse_nft_capture {_quote(_wsl_path(TPROXY_CAPTURE))} "
            f"{_quote(_wsl_path(intent))} {_quote(_wsl_path(payload))}; printf 'RC=%s\\n' \"$?\""
        )
        process, _ = self.harness.run(body)
        self.assertIn("RC=0", process.stdout)
        text = payload.read_text(encoding="utf-8")
        self.assertIn("meta l4proto tcp tproxy ip to :7895 meta mark set 0x162", text)
        self.assertIn("meta l4proto udp tproxy ip6 to :7895 meta mark set 0x162", text)
        mutated = self.harness.root / "tproxy-port-mutated"
        _write_lf(mutated, text.replace(":7895", ":7896", 1))
        compare = (
            f"openkill_shadow_compare_auto_intent {_quote(_wsl_path(mutated))} "
            f"{_quote(_wsl_path(payload))}; printf 'RC=%s\\n' \"$?\""
        )
        process, _ = self.harness.run(compare)
        self.assertIn("RC=1", process.stdout)

    def test_auto_match_mismatch_and_sensitive_telemetry(self) -> None:
        match = self._coordinator()
        self.assertEqual(match["rc"], 0)
        self.assertEqual(match["status"].get("status"), "MATCH")
        status_text = (match["telemetry"] / "status").read_text(encoding="utf-8")
        self.assertNotIn("198.51.100.10", status_text)

        changed = self.harness.root / "changed.capture"
        _write_lf(changed, CAPTURE.read_text(encoding="utf-8").replace("meta mark set 0x162", "meta mark set 0x163", 1))
        mismatch = self._coordinator(capture=changed)
        self.assertEqual(mismatch["rc"], 1)
        self.assertEqual(mismatch["status"].get("status"), "MISMATCH")
        last = (mismatch["telemetry"] / "last_mismatch").read_text(encoding="utf-8")
        self.assertNotIn("198.51.100.10", last)

    def test_default_off_performs_zero_reads_or_telemetry(self) -> None:
        fake = self.harness.root / "should-not-run"
        _write_lf(fake, "#!/bin/sh\nexit 99\n")
        result = self._coordinator(enabled=False, extra_env={"OPENKILL_NFT_SHADOW_CAPTURE_NFT_BIN": _wsl_path(fake)})
        self.assertEqual(result["rc"], 0)
        self.assertFalse((result["telemetry"] / "status").exists())
        self.assertFalse((result["telemetry"] / "last_mismatch").exists())

    def test_owner_and_unsupported_states_stop_before_capture(self) -> None:
        mihomo = self.harness.root / "mihomo.txt"
        _write_lf(mihomo, AUTO_SOURCE.read_text(encoding="utf-8").replace("OWNER=OPENKILL", "OWNER=MIHOMO", 1))
        result = self._coordinator(source=mihomo)
        self.assertEqual(result["rc"], 0)
        self.assertEqual(result["status"].get("status"), "DISABLED")

        for key in ("CURRENT_UNDEFINED", "BC07_UNSUPPORTED"):
            source = self.harness.root / f"{key}.txt"
            _write_lf(source, AUTO_SOURCE.read_text(encoding="utf-8") + f"{key}=1\n")
            result = self._coordinator(source=source)
            self.assertEqual(result["rc"], 2, key)
            self.assertEqual(result["status"].get("status"), "UNSUPPORTED_CURRENT_STATE")

    def test_generation_change_is_stale(self) -> None:
        stale_renderer = self.harness.root / "stale-renderer.sh"
        _write_lf(
            stale_renderer,
            "#!/bin/sh\n"
            "dir=${1%/*}\n"
            "printf 'g2\\n' > \"$dir/auto-generation\"\n"
            f"exec sh {_quote(_wsl_path(RENDERER))} \"$1\" \"$2\"\n",
        )
        result = self._coordinator(renderer=stale_renderer)
        self.assertEqual(result["rc"], 6)
        self.assertEqual(result["status"].get("status"), "STALE")

    def test_source_generation_change_is_stale(self) -> None:
        source = self.harness.root / "source-race.txt"
        _write_lf(source, AUTO_SOURCE.read_text(encoding="utf-8"))
        stale_renderer = self.harness.root / "source-stale-renderer.sh"
        source_path = _quote(_wsl_path(source))
        _write_lf(
            stale_renderer,
            "#!/bin/sh\n"
            f"awk '{{sub(/^GENERATION=.*/, \"GENERATION=fixture-g2\"); print}}' {source_path} > {source_path}.tmp && mv {source_path}.tmp {source_path}\n"
            f"exec sh {_quote(_wsl_path(RENDERER))} \"$1\" \"$2\"\n",
        )
        result = self._coordinator(source=source, renderer=stale_renderer)
        self.assertEqual(result["rc"], 6)
        self.assertEqual(result["status"].get("status"), "STALE")

    def test_actual_state_mutations_never_report_match(self) -> None:
        mutations = {
            "mark": ("meta mark set 0x162", "meta mark set 0x163"),
            "node": ("198.51.100.10", "198.51.100.99"),
            "dns": ("jump openkill_dns_hijack", "jump openkill_dns_redirect"),
            "port": ("tcp dport 53 jump", "tcp dport 54 jump"),
            "hook": ("type nat hook output priority -1", "type nat hook output priority 0"),
            "order": (
                "meta nfproto ipv4 ip protocol tcp jump openkill_output\n  meta nfproto ipv6 jump openkill_output_v6",
                "meta nfproto ipv6 jump openkill_output_v6\n  meta nfproto ipv4 ip protocol tcp jump openkill_output",
            ),
        }
        for name, (old, new) in mutations.items():
            changed = self.harness.root / f"mutation-{name}.capture"
            mutated = CAPTURE.read_text(encoding="utf-8").replace(old, new, 1)
            _write_lf(changed, mutated)
            result = self._coordinator(capture=changed)
            self.assertNotEqual(result["status"].get("status"), "MATCH", name)
            self.assertIn(result["status"].get("status"), {"MISMATCH", "CAPTURE_UNSUPPORTED"}, name)

    def test_producer_determinism_and_input_reorder(self) -> None:
        body = f"""
src=/tmp/openkill-shadow-self-source-$$
rich=/tmp/openkill-shadow-self-rich-$$
template=/tmp/openkill-shadow-self-template-$$
output=/tmp/openkill-shadow-self-input-$$
cp {_quote(_wsl_path(AUTO_SOURCE))} "$src"
cp "$src" "$rich"
sed 's/^OWNER=OPENKILL$/OWNER=MIHOMO/' "$src" > "$src.mihomo"
mkdir -p "$template"
cp {_quote(_wsl_path(TEMPLATE_DIR))}/input_tun_v1.tsv "$template"/
cp {_quote(_wsl_path(TEMPLATE_DIR))}/input_tproxy_v1.tsv "$template"/
cp {_quote(_wsl_path(TEMPLATE_DIR))}/input_redirect_v1.tsv "$template"/
export OPENKILL_NFT_SHADOW_SOURCE_FILE="$src.mihomo"
export OPENKILL_NFT_SHADOW_TEMPLATE_DIR="$template"
i=0
first=
while [ \"$i\" -lt 1000 ]; do
  openkill_shadow_build_auto_input "$output" || exit 91
  current=$(sha256sum "$output" | awk '{{print $1}}')
  [ -n \"$first\" ] || first=$current
  [ \"$first\" = \"$current\" ] || exit 92
  i=$((i + 1))
done
printf 'COUNT=%s HASH=%s\\n' \"$i\" \"$first\"
export OPENKILL_NFT_SHADOW_SOURCE_FILE="$rich"
j=0
while [ \"$j\" -lt 5 ]; do
  openkill_shadow_build_auto_input "$output" || exit 93
  j=$((j + 1))
done
rm -rf "$src" "$src.mihomo" "$rich" "$template" "$output"
"""
        process, _ = self.harness.run(
            body,
            {
                "OPENKILL_NFT_SHADOW_SOURCE_FILE": _wsl_path(AUTO_SOURCE),
                "OPENKILL_NFT_SHADOW_TEMPLATE_DIR": _wsl_path(TEMPLATE_DIR),
            },
            timeout=180,
        )
        self.assertIn("COUNT=1000", process.stdout, process.stderr)
        self.assertRegex(process.stdout, r"HASH=[0-9a-f]{64}")

        reordered = self.harness.root / "reordered.txt"
        source_text = AUTO_SOURCE.read_text(encoding="utf-8")
        source_text = source_text.replace("NODE4=198.51.100.10,198.51.100.11", "NODE4=198.51.100.11,198.51.100.10")
        _write_lf(reordered, source_text)
        one = self._build(AUTO_SOURCE)
        two = self._build(reordered)
        self.assertEqual(one["rc"], 0)
        self.assertEqual(two["rc"], 0)
        self.assertEqual(one["output"].read_bytes(), two["output"].read_bytes())

    def test_source_and_capture_paths_are_read_only_and_production_callsite_is_zero(self) -> None:
        helper = HELPER.read_text(encoding="utf-8")
        self.assertNotIn("eval", helper.lower())
        self.assertNotIn("python", helper.lower())
        self.assertNotRegex(helper, r"(?m)^\s*(?:uci|ubus|ip|ip6tables|iptables|nft|fw4|service|nslookup|resolveip|curl)\b")
        self.assertNotRegex(helper, r"nft\s+(?:-f|add|insert|replace|delete|flush|reset|destroy)\b")
        init = (ROOT / "luci-app-openkill/root/etc/init.d/openkill").read_text(encoding="utf-8")
        self.assertEqual(init.count("openkill_nft_renderer.sh"), 0)
        for rel in (
            "luci-app-openkill/root/usr/share/openkill/openkill_network.sh",
            "luci-app-openkill/root/usr/share/openkill/openkill_watchdog.sh",
            "luci-app-openkill/root/usr/share/openkill/openkill_fw4_reload.sh",
        ):
            self.assertNotIn("openkill_nft_renderer.sh", (ROOT / rel).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
