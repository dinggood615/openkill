#!/usr/bin/env python3
"""Local parity tests for the unwired OpenWrt shell NFT renderer.

The shell candidate consumes only a canonical line-oriented input.  This
suite converts the already validated Python IR into that input, compares the
resulting desired batch with the Python reference, and runs the result through
the local nft parser in check-only mode.  No production shell function is
called and no nft mutation is permitted.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import random
import re
import shutil
import subprocess
import tempfile
import unittest
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from openkill_nft_ir import render_state
from openkill_nft_syntax import render_nft, render_test_scaffold, lower_nft_ir
from openkill_shadow_adapter import validate_state_fixture


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
RENDERER = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_nft_renderer.sh"
STATE_FIXTURE = SCRIPTS / "fixtures/openkill-shadow-states-v1.json"
INPUT_FIXTURE = SCRIPTS / "fixtures/openkill-shell-renderer-input-v1.json"

MARK = "0x162"
MASK = "0xffffffff"
ROUTE_TABLE = "354"
RULE_PREF = "1888"
TAB = "\t"


def load_states() -> List[Mapping[str, Any]]:
    return validate_state_fixture(json.loads(STATE_FIXTURE.read_text(encoding="utf-8")))["states"]


def _shell_supported_state(state: Mapping[str, Any]) -> bool:
    """Return whether the production candidate may render this CURRENT owner."""

    return str(state.get("owner", "OPENKILL")) in {"OPENKILL", "MIHOMO", "DISABLED"}


def _port(state: Mapping[str, Any], name: str, fallback: int) -> int:
    value = (state.get("proxy_ports") or {}).get(name, fallback)
    return int(value)


def _row(*fields: Any) -> str:
    values = [str(value) for value in fields]
    if any("\t" in value or "\r" in value or "\n" in value for value in values):
        raise ValueError("shell input fields cannot contain line breaks or tabs")
    return TAB.join(values)


def state_to_input(state: Mapping[str, Any]) -> Tuple[str, str]:
    """Serialize a Python CURRENT AST as SHELL_RENDERER_INPUT_V1."""

    tproxy = _port(state, "tproxy", 7895)
    redirect = _port(state, "redirect", 7892)
    dns = _port(state, "dns", 7874)
    ir = render_state(state, profile="current")
    ast = lower_nft_ir(ir, tproxy_port=tproxy, redirect_port=redirect)
    rows = ["SHELL_RENDERER_INPUT_V1\t1"]
    metadata = (
        ("profile", "current"),
        ("owner", state.get("owner", "OPENKILL")),
        ("backend", "modern_fw4_nft"),
        ("run_mode", state.get("run_mode", "TUN")),
        ("semantic_spec_version", 1),
        ("classifier_contract_version", 1),
        ("nft_ir_version", 1),
        ("ownership_manifest_version", 1),
        ("redirect_port", redirect),
        ("tproxy_port", tproxy),
        ("dns_port", dns),
        ("mark", MARK),
        ("mask", MASK),
        ("route_table", ROUTE_TABLE),
        ("rule_pref", RULE_PREF),
        ("router_self_proxy", int(bool(state.get("router_self_proxy")))),
        ("component_state", "READY"),
    )
    rows.extend(_row("META", key, value) for key, value in metadata)
    for chain in ast["owned_chains"]:
        rows.append(
            _row(
                "CHAIN",
                chain["logical_id"],
                chain["physical_name"],
                chain["family"],
                chain["component"],
                chain.get("role") or "TOPOLOGY",
                "1" if chain.get("base_chain") else "0",
                chain.get("type") or "-",
                str(chain.get("hook") or "-").upper(),
                chain.get("priority") if chain.get("priority") is not None else "-",
            )
        )
    for item in ast["sets"]:
        rows.append(
            _row(
                "SET",
                item["logical_id"],
                item["physical_name"],
                item["family"],
                item["element_type"],
                ",".join(str(flag) for flag in item.get("flags", ())) or "-",
                ",".join(str(value) for value in item.get("elements", ())) or "-",
                item["component"],
            )
        )
    for item in ast["attachments"]:
        rows.append(
            _row(
                "ATTACH",
                item["logical_id"],
                item["component"],
                item["family"],
                item["from_chain"],
                item.get("match_expression") or "-",
                item["action_type"],
                item["action_expression"],
                item["to_chain"],
            )
        )
    chain_orders: Dict[str, int] = {}
    for rule in ast["rules"]:
        chain = str(rule["chain"])
        order = chain_orders.get(chain, 0)
        chain_orders[chain] = order + 1
        rows.append(
            _row(
                "RULE",
                rule["logical_id"],
                rule["component"],
                rule["family"],
                chain,
                order,
                rule.get("match_expression") or "-",
                rule["action_type"],
                rule.get("action_expression") or "-",
                rule.get("semantic_reason") or "-",
                rule.get("decision") or "-",
                rule.get("known_current_gap") or "-",
            )
        )
    return "\n".join(rows) + "\n", render_nft(ir, tproxy_port=tproxy, redirect_port=redirect)


def _wsl_path(path: pathlib.Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    tail = resolved.as_posix().split(":", 1)[-1]
    return "/mnt/{}/{}".format(drive, tail.lstrip("/"))


def _run_shell(input_text: str, *, timeout: int = 60) -> Tuple[int, str, str]:
    with tempfile.TemporaryDirectory(prefix="openkill-shell-") as temp:
        input_path = pathlib.Path(temp) / "input.tsv"
        with input_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(input_text)
        command = [
            "wsl.exe",
            "-u",
            "root",
            "--",
            "sh",
            _wsl_path(RENDERER),
            _wsl_path(input_path),
        ]
        # WSL on Windows may emit a UTF-16 diagnostic on stderr before the
        # child process starts.  Decode explicitly and replace that launcher
        # noise so the renderer result, which is UTF-8/ASCII, remains testable
        # on hosts whose locale is GBK.
        proc = subprocess.run(
            command, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr


def _run_shell_batch(inputs: Mapping[str, str], *, timeout: int = 180) -> Dict[str, Tuple[int, str, str]]:
    """Run many pure renders inside one disposable WSL process.

    WSL startup dominates individual calls on the development host.  The
    renderer itself still runs once per input; batching only keeps the parser
    gate practical for the 120-state corpus.
    """

    with tempfile.TemporaryDirectory(prefix="openkill-shell-batch-") as temp:
        root = pathlib.Path(temp)
        input_dir = root / "inputs"
        output_dir = root / "outputs"
        input_dir.mkdir()
        output_dir.mkdir()
        for name, text in inputs.items():
            with (input_dir / (name + ".tsv")).open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        renderer = _wsl_path(RENDERER)
        wsl_input_dir = _wsl_path(input_dir)
        wsl_output_dir = _wsl_path(output_dir)
        # Paths are generated by tempfile and then single-quoted as a shell
        # literal.  No input record is interpolated into this command.
        def quote(value: str) -> str:
            return "'" + value.replace("'", "'\\''") + "'"

        script = (
            "#!/bin/sh\n"
            "work=/tmp/openkill-shell-batch-$$\n"
            "mkdir -p \"$work/in\" \"$work/out\" || exit 70\n"
            "cp " + quote(wsl_input_dir) + "/*.tsv \"$work/in/\" || exit 70\n"
            ". " + quote(renderer) + " || exit 70\n"
            "for f in \"$work/in\"/*.tsv; do "
            "base=${f##*/}; base=${base%.tsv}; "
            "openkill_render_nft_desired \"$f\" > \"$work/out/$base.nft\" || exit $?; "
            "done\n"
            "cp \"$work/out\"/*.nft " + quote(wsl_output_dir) + "/ || exit 70\n"
            "rm -rf \"$work\"\n"
        )
        runner = root / "runner.sh"
        with runner.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(script)
        proc = subprocess.run(
            ["wsl.exe", "-u", "root", "--", "sh", _wsl_path(runner)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        result: Dict[str, Tuple[int, str, str]] = {}
        for name in inputs:
            path = output_dir / (name + ".nft")
            output = path.read_text(encoding="utf-8") if path.exists() else ""
            result[name] = (proc.returncode if not path.exists() else 0, output, proc.stderr)
        return result


def _core_lines(text: str) -> List[str]:
    """Drop comments/header while retaining complete desired object syntax."""

    lines: List[str] = []
    for line in text.splitlines():
        if not line.startswith("add "):
            continue
        lines.append(line.split(' comment "', 1)[0].rstrip())
    return sorted(lines)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _nft_check(text: str, ir: Mapping[str, Any]) -> Tuple[int, str]:
    """Check shell output beside a development-only FW4 scaffold."""

    scaffold = render_test_scaffold(ir)
    marker = "# OPENKILL_NFT_SYNTAX_V1"
    if marker not in scaffold:
        raise AssertionError("Python scaffold marker missing")
    check_text = scaffold.split(marker, 1)[0] + text
    with tempfile.TemporaryDirectory(prefix="openkill-nft-check-") as temp:
        path = pathlib.Path(temp) / "check.nft"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(check_text)
        proc = subprocess.run(
            ["wsl.exe", "-u", "root", "--", "nft", "-c", "-f", _wsl_path(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        return proc.returncode, (proc.stderr or proc.stdout).strip()


class ShellRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.states = load_states()
        cls.state_by_id = {str(state["id"]): state for state in cls.states}
        cls.nft_available = bool(shutil.which("wsl.exe"))

    def test_machine_fixture_and_posix_source(self):
        fixture = json.loads(INPUT_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["schema"], "SHELL_RENDERER_INPUT_V1")
        self.assertEqual(fixture["version"], 1)
        self.assertEqual(fixture["supported_profiles"], ["current"])
        self.assertEqual(fixture["mark_abi"]["mark"], MARK)
        source = RENDERER.read_text(encoding="utf-8")
        self.assertTrue(source.startswith("#!/bin/sh\n"))
        self.assertNotIn("#!/bin/bash", source)
        self.assertNotIn("eval", source)
        self.assertNotRegex(source, r"(?m)^\s*\[\[")
        self.assertNotRegex(source, r"(?m)^\s*(nft|iptables|ip6tables|uci|ubus|fw4|ip)\s")
        proc = subprocess.run(
            ["wsl.exe", "-u", "root", "--", "sh", "-n", _wsl_path(RENDERER)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for applet in ("awk", "sort", "sed", "tr", "grep", "printf"):
            check = subprocess.run(
                ["wsl.exe", "-u", "root", "--", "command", "-v", applet],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            self.assertEqual(check.returncode, 0, applet)

    def test_current_shell_matches_python_for_all_states(self):
        self.assertGreaterEqual(len(self.states), 120)
        inputs: Dict[str, str] = {}
        expected: Dict[str, str] = {}
        for state in self.states:
            if not _shell_supported_state(state):
                continue
            input_text, python_text = state_to_input(state)
            inputs[str(state["id"])] = input_text
            expected[str(state["id"])] = python_text
        rendered = _run_shell_batch(inputs)
        self.assertGreaterEqual(len(inputs), 120)
        for state in self.states:
            state_id = str(state["id"])
            with self.subTest(state=state_id):
                if not _shell_supported_state(state):
                    input_text, _ = state_to_input(state)
                    rc, stdout, _ = _run_shell(input_text)
                    self.assertEqual(rc, 64)
                    self.assertEqual(stdout, "")
                    continue
                rc, shell_text, stderr = rendered[state_id]
                self.assertEqual(rc, 0, stderr)
                self.assertTrue(shell_text.startswith("# OPENKILL_SHELL_NFT_RENDERER_V1"))
                self.assertNotIn("TEST_SCAFFOLD", shell_text)
                self.assertNotIn("TEST_ONLY", shell_text)
                self.assertEqual(_core_lines(shell_text), _core_lines(expected[state_id]))

    def test_current_profile_and_fail_closed_inputs(self):
        input_text, _ = state_to_input(self.state_by_id["STATE-12-TPROXY"])
        cases = (
            (input_text.replace("META\tprofile\tcurrent", "META\tprofile\ttarget"), 66),
            (input_text.replace("META\ttproxy_port\t7893", "META\ttproxy_port\t0"), 64),
            (input_text.replace("META\tprofile\tcurrent", "META\tprofile\tcurrent\nMETA\tbogus\tx"), 64),
            (input_text.replace("SET\tNODE_ENDPOINT_V4", "SET\tbad-name", 1), 64),
            (input_text.replace("\tADDRESS\t-\t", "\tADDRESS\tbogus\t", 1), 64),
            (input_text.replace("\tDNS_LAN\t0\t-\t-\t-", "\tNOPE\t0\t-\t-\t-", 1), 64),
            (input_text.replace("meta nfproto ipv4", "meta nfproto ipv4 \"bad\"", 1), 64),
            (input_text.replace("meta nfproto ipv4", "meta nfproto ipv4 'bad'", 1), 64),
            (input_text + _row("RULE", "UNRESOLVED_POLICY", "PROXY_ACTION", "IPv4", "openkill_mangle", 999, "meta nfproto ipv4", "UNRESOLVED_SEMANTIC", "-", "EXPLICIT_PROXY", "-", "BC-01") + "\n", 65),
            (input_text + "UNSUPPORTED\tBC-07\tACCESS_DENY\n", 65),
        )
        for value, expected in cases:
            with self.subTest(expected=expected):
                rc, stdout, _ = _run_shell(value)
                self.assertEqual(rc, expected)
                self.assertEqual(stdout, "")

    def test_unsupported_access_deny_is_not_lowered(self):
        input_text, _ = state_to_input(self.state_by_id["STATE-12-TPROXY"])
        row = _row(
            "RULE", "UNSUPPORTED_DENY", "ACCESS", "IPv4", "openkill_mangle", 999,
            "meta nfproto ipv4", "ACCESS_DENY_REQUIRED", "-", "ACCESS_CONTROL", "ACCESS_DENY", "BC-07",
        )
        rc, stdout, stderr = _run_shell(input_text + row + "\n")
        self.assertEqual(rc, 65)
        self.assertEqual(stdout, "")
        self.assertIn("action", stderr)

    def test_shell_output_passes_real_nft_check_for_unique_states(self):
        self.assertTrue(self.nft_available)
        supported = [state for state in self.states if _shell_supported_state(state)]
        inputs = {str(state["id"]): state_to_input(state)[0] for state in supported}
        rendered = _run_shell_batch(inputs)
        seen: Dict[str, Tuple[str, Mapping[str, Any]]] = {}
        for state in supported:
            rc, shell_text, stderr = rendered[str(state["id"])]
            self.assertEqual(rc, 0, stderr)
            seen.setdefault(_hash(shell_text), (shell_text, state))
        self.assertGreaterEqual(len(seen), 5)
        for digest, (shell_text, state) in seen.items():
            with self.subTest(hash=digest, state=state["id"]):
                ir = render_state(state, profile="current")
                rc, detail = _nft_check(shell_text, ir)
                self.assertEqual(rc, 0, detail)

    def test_empty_sets_and_address_semantics_reach_nft_parser(self):
        for state_id in ("STATE-01-BASIC-V4", "STATE-02-IPV6-SOURCE-SPECIFIC", "STATE-12-TPROXY"):
            state = self.state_by_id[state_id]
            input_text, _ = state_to_input(state)
            rc, shell_text, stderr = _run_shell(input_text)
            self.assertEqual(rc, 0, stderr)
            ir = render_state(state, profile="current")
            checked, detail = _nft_check(shell_text, ir)
            self.assertEqual(checked, 0, detail)
            self.assertNotIn("0.0.0.0", shell_text)
            self.assertNotIn("::,", shell_text)
        state = self.state_by_id["STATE-02-IPV6-SOURCE-SPECIFIC"]
        _, text = state_to_input(state)
        self.assertIn("openkill_wan_host6", text)
        self.assertIn("openkill_delegated6", text)

    def test_tproxy_dns_and_bc_current_guards(self):
        state = self.state_by_id["STATE-12-TPROXY"]
        input_text, shell_text = state_to_input(state)
        self.assertIn("tproxy ip to :7893 meta mark set 0x162", shell_text)
        self.assertIn("tproxy ip6 to :7893 meta mark set 0x162", shell_text)
        self.assertIn("priority -1", shell_text)
        self.assertNotIn("CURRENT_TUN_INGRESS_V6", shell_text)
        dns_state = self.state_by_id["STATE-09-SELF-PROXY"]
        _, dns_text = state_to_input(dns_state)
        self.assertIn("openkill_dns_hijack", dns_text)
        self.assertIn("openkill_dns_redirect", dns_text)
        self.assertNotIn("drop", dns_text.lower())
        self.assertNotIn("reject", dns_text.lower())
        self.assertEqual(_core_lines(dns_text), _core_lines(render_nft(render_state(dns_state))))

    def test_component_local_set_changes_do_not_change_topology(self):
        input_text, _ = state_to_input(self.state_by_id["STATE-01-BASIC-V4"])
        mutations = {
            "openkill_node4": "203.0.113.10",
            "localnetwork6": "fd00::/8",
            "china_ip_route": "198.51.100.0/24",
            "openkill_access4_allow": "192.168.50.0/24",
        }
        for physical, element in mutations.items():
            with self.subTest(physical=physical):
                lines = input_text.splitlines()
                changed: List[str] = []
                for line in lines:
                    fields = line.split(TAB)
                    if len(fields) == 8 and fields[0] == "SET" and fields[2] == physical:
                        fields[6] = element
                        line = TAB.join(fields)
                    changed.append(line)
                rc1, before, err1 = _run_shell(input_text)
                rc2, after, err2 = _run_shell("\n".join(changed) + "\n")
                self.assertEqual((rc1, rc2), (0, 0), (err1, err2))
                before_core = set(_core_lines(before))
                after_core = set(_core_lines(after))
                changed_lines = before_core.symmetric_difference(after_core)
                self.assertEqual(len(changed_lines), 2)
                self.assertTrue(all(physical in line for line in changed_lines))

    def test_deterministic_and_input_order_independent(self):
        state = self.state_by_id["STATE-12-TPROXY"]
        input_text, _ = state_to_input(state)
        rc, baseline, stderr = _run_shell(input_text)
        self.assertEqual(rc, 0, stderr)
        baseline_hash = _hash(baseline)
        # The 1000-run check exercises the renderer's complete validation and
        # serialization path, but uses a tiny valid input so the test measures
        # determinism rather than repeatedly parsing the largest corpus state.
        deterministic_input = "\n".join(
            (
                "SHELL_RENDERER_INPUT_V1\t1",
                _row("META", "profile", "current"),
                _row("META", "owner", "OPENKILL"),
                _row("META", "backend", "modern_fw4_nft"),
                _row("META", "run_mode", "TUN"),
                _row("META", "semantic_spec_version", 1),
                _row("META", "classifier_contract_version", 1),
                _row("META", "nft_ir_version", 1),
                _row("META", "ownership_manifest_version", 1),
                _row("META", "redirect_port", 7892),
                _row("META", "tproxy_port", 7893),
                _row("META", "dns_port", 7874),
                _row("META", "mark", MARK),
                _row("META", "mask", MASK),
                _row("META", "route_table", ROUTE_TABLE),
                _row("META", "rule_pref", RULE_PREF),
                _row("META", "router_self_proxy", 0),
                _row("META", "component_state", "READY"),
                _row("CHAIN", "DET_CHAIN", "det_chain", "IPv4", "TOPOLOGY", "TOPOLOGY", 0, "-", "-", "-"),
                _row("SET", "DET_SET", "det_set", "IPv4", "ADDRESS", "-", "198.51.100.0/24", "LOCAL"),
                _row("RULE", "DET_RULE", "PROXY_ACTION", "IPv4", "det_chain", 0, "meta nfproto ipv4", "RETURN_NATIVE", "return", "DEFAULT_POLICY", "BYPASS", "-"),
            )
        ) + "\n"
        rc, deterministic_baseline, stderr = _run_shell(deterministic_input)
        self.assertEqual(rc, 0, stderr)
        # A single shell-side loop performs the requested 1000 pure renders;
        # only hashes are retained by the test harness.
        with tempfile.TemporaryDirectory(prefix="openkill-shell-determinism-") as temp:
            path = pathlib.Path(temp) / "input.tsv"
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(deterministic_input)
            runner = pathlib.Path(temp) / "determinism.sh"
            runner_text = (
                "#!/bin/sh\n"
                "work=/tmp/openkill-shell-determinism-$$\n"
                "mkdir -p \"$work\" || exit 70\n"
                "cp '" + _wsl_path(path) + "' \"$work/input.tsv\" || exit 70\n"
                ". '" + _wsl_path(RENDERER) + "' || exit 70\n"
                "i=1\n"
                "while [ $i -le 1000 ]; do\n"
                "  openkill_render_nft_desired \"$work/input.tsv\" | sha256sum | awk '{print $1}'\n"
                "  i=$((i+1))\n"
                "done | sort -u | wc -l\n"
                "rm -rf \"$work\"\n"
            )
            with runner.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(runner_text)
            proc = subprocess.run(
                ["wsl.exe", "-u", "root", "--", "sh", _wsl_path(runner)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.strip(), "1")
        self.assertEqual(baseline_hash, _hash(baseline))
        self.assertTrue(deterministic_baseline.startswith("# OPENKILL_SHELL_NFT_RENDERER_V1"))

        records = input_text.splitlines()
        header, rest = records[0], records[1:]
        randomizer = random.Random(20261126)
        reordered_inputs: Dict[str, str] = {}
        for index in range(100):
            shuffled = list(rest)
            randomizer.shuffle(shuffled)
            reordered_inputs["reordered-{:03d}".format(index)] = header + "\n" + "\n".join(shuffled) + "\n"
        reordered_outputs = _run_shell_batch(reordered_inputs)
        for index in range(100):
            rc, output, stderr = reordered_outputs["reordered-{:03d}".format(index)]
            self.assertEqual(rc, 0, (index, stderr))
            self.assertEqual(output, baseline)

    def test_production_callsite_audit_is_zero(self):
        runtime_paths = (
            ROOT / "luci-app-openkill/root/etc/init.d/openkill",
            ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_network.sh",
            ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_watchdog.sh",
            ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_fw4_reload.sh",
        )
        needles = ("openkill_nft_renderer.sh", "openkill_render_nft_desired", "SHELL_RENDERER_INPUT_V1")
        hits = []
        for path in runtime_paths:
            text = path.read_text(encoding="utf-8")
            for needle in needles:
                if needle in text:
                    hits.append((str(path), needle))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
