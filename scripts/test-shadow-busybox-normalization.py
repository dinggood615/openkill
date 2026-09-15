#!/usr/bin/env python3
"""Regression tests for the BusyBox-safe shadow enum normalizers.

These tests run the production shell helper against sanitized committed-state
fixtures.  They never contact a router, read a host nft ruleset, or invoke a
service lifecycle.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SELF_TEST = ROOT / "scripts/test-shadow-self-sufficiency.py"
CONTINUITY_TEST = ROOT / "scripts/test-shadow-continuity.py"
NETWORK_HELPER = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_network.sh"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


self_test = _load(SELF_TEST, "shadow_self_sufficiency_for_busybox")
continuity_test = _load(CONTINUITY_TEST, "shadow_continuity_for_busybox")


class BusyBoxNormalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = self_test.ShellFixtureHarness()

    def tearDown(self) -> None:
        self.harness.close()

    def _busybox_run(self, body: str, env: dict[str, str | Path]) -> subprocess.CompletedProcess[str]:
        """Run a fixture runner under BusyBox ash, not the host shell."""
        case = self.harness.root / f"busybox-case-{len(list(self.harness.root.glob('busybox-case-*')))}"
        case.mkdir(parents=True, exist_ok=True)
        runner = case / "runner.sh"
        lines = ["#!/bin/sh", "set +e"]
        for key in self.harness._UNSET:
            lines.append(f"unset {key}")
        for key, value in env.items():
            lines.append(f"export {key}={self_test._quote(value)}")
        lines.extend([f". {self_test._quote(self_test._wsl_path(self_test.HELPER))}", body])
        self_test._write_lf(runner, "\n".join(lines) + "\n")
        command = (
            ["wsl.exe", "-u", "root", "--", "busybox", "sh", self_test._wsl_path(runner)]
            if shutil.which("wsl.exe")
            else ["busybox", "sh", str(runner)]
        )
        return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)

    def _source(self, field: str, value: str) -> Path:
        source = self.harness.root / f"{field.lower()}-{len(list(self.harness.root.glob('*.txt')))}.txt"
        text = self_test.AUTO_SOURCE.read_text(encoding="utf-8")
        pattern = rf"^{re.escape(field)}=.*$"
        replacement = f"{field}={value}"
        updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
        self.assertEqual(count, 1, field)
        self_test._write_lf(source, updated)
        return source

    def _build(self, field: str, value: str) -> dict[str, object]:
        source = self._source(field, value)
        return self._build_source(source)

    def _build_source(self, source: Path) -> dict[str, object]:
        output = self.harness.root / f"input-{len(list(self.harness.root.glob('input-*.tsv')))}.tsv"
        stdout = output.with_suffix(".stdout")
        stderr = output.with_suffix(".stderr")
        body = (
            f"openkill_shadow_build_auto_input {self_test._quote(self_test._wsl_path(output))} "
            f"> {self_test._quote(self_test._wsl_path(stdout))} "
            f"2> {self_test._quote(self_test._wsl_path(stderr))}; "
            "printf 'RC=%s\\n' \"$?\""
        )
        process = self._busybox_run(
            body,
            {
                "OPENKILL_NFT_SHADOW_SOURCE_FILE": self_test._wsl_path(source),
                "OPENKILL_NFT_SHADOW_TEMPLATE_DIR": self_test._wsl_path(self_test.TEMPLATE_DIR),
            },
        )
        return {
            "process": process,
            "output": output,
            "rc": self_test.ShadowSelfSufficiencyTests._rc(process),
        }

    def test_device_busybox_bad_class_evidence_and_portable_range(self) -> None:
        """Record the device observation while proving the portable form.

        The OpenWrt BusyBox build observed on .102 returned ``ppenkiuu`` for
        the class form.  The Ubuntu WSL BusyBox used for local tests may carry
        a different implementation and return ``OPENKILL``; either result is
        recorded by the test, while the range form must always be correct.
        """
        busybox_prefix = (["wsl.exe", "-u", "root", "--", "busybox", "sh", "-c"]
                          if shutil.which("wsl.exe") else ["busybox", "sh", "-c"])
        old = subprocess.run(
            busybox_prefix + ["printf openkill | busybox tr '[:lower:]' '[:upper:]'"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(old.returncode, 0, old.stderr)
        self.assertIn(old.stdout.strip(), {"ppenkiuu", "OPENKILL"})
        portable = subprocess.run(
            busybox_prefix + ["printf openkill | busybox tr a-z A-Z"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(portable.returncode, 0, portable.stderr)
        self.assertEqual(portable.stdout.strip(), "OPENKILL")

    def test_owner_enum_canonicalization_and_unknowns_fail_closed(self) -> None:
        expected = {
            "openkill": (0, "OPENKILL"),
            "OPENKILL": (0, "OPENKILL"),
            "OpenKill": (0, "OPENKILL"),
            "oPeNkIlL": (0, "OPENKILL"),
            "mihomo": (0, "MIHOMO"),
            "DISABLED": (0, "DISABLED"),
            "UNKNOWN": (3, None),
            "openkil": (11, None),
            "openkillx": (11, None),
            "foo": (11, None),
            "": (11, None),
        }
        for raw, (rc, owner) in expected.items():
            result = self._build("OWNER", raw)
            self.assertEqual(result["rc"], rc, raw)
            if owner is not None:
                self.assertIn(f"META\towner\t{owner}", result["output"].read_text(encoding="utf-8"), raw)

    def test_run_mode_and_unsupported_boolean_enums_are_portable(self) -> None:
        for raw, canonical in (("tun", "TUN"), ("tUn", "TUN"), ("tproxy", "TPROXY"), ("ReDiReCt", "REDIRECT")):
            result = self._build("RUN_MODE", raw)
            self.assertEqual(result["rc"], 0, raw)
            self.assertIn(f"META\trun_mode\t{canonical}", result["output"].read_text(encoding="utf-8"), raw)
        self.assertEqual(self._build("RUN_MODE", "tunx")["rc"], 11)
        for raw in ("yes", "TRUE", "Active", "unsupported", "ReQuIrEd"):
            source = self._source("OWNER", "openkill")
            text = source.read_text(encoding="utf-8") + f"CURRENT_UNDEFINED={raw}\n"
            flagged = self.harness.root / f"flag-{raw}.txt"
            self_test._write_lf(flagged, text)
            self.assertEqual(self._build_source(flagged)["rc"], 2, raw)

    def test_full_lowercase_auto_input_without_generation_helper(self) -> None:
        state_text = continuity_test.AUTO_SOURCE.read_text(encoding="utf-8").replace("OWNER=OPENKILL", "OWNER=openkill", 1)
        desired = self.harness.root / "desired-lower"
        applied = self.harness.root / "applied-lower"
        self_test._write_lf(desired, state_text)
        self_test._write_lf(applied, state_text)
        telemetry = self.harness.root / "telemetry"
        emitted = self.harness.root / "auto-input.tsv"
        renderer = self.harness.root / "renderer.sh"
        self_test._write_lf(
            renderer,
            "#!/bin/sh\n"
            f"cp \"$1\" {self_test._quote(self_test._wsl_path(emitted))}\n"
            f"exec sh {self_test._quote(self_test._wsl_path(continuity_test.RENDERER))} \"$1\" \"$2\"\n",
        )
        body = (
            f". {self_test._quote(self_test._wsl_path(NETWORK_HELPER))}; "
            "openkill_shadow_compare_nft; printf 'RC=%s\\n' \"$?\""
        )
        process = self._busybox_run(
            body,
            {
                "OPENKILL_NFT_SHADOW": "1",
                "OPENKILL_NFT_SHADOW_FORCE": "1",
                "OPENKILL_NETWORK_DESIRED": continuity_test._wsl(desired),
                "OPENKILL_NETWORK_APPLIED_FILE": continuity_test._wsl(applied),
                "OPENKILL_NETWORK_SNAPSHOT": continuity_test._wsl(self.harness.root / "missing-snapshot"),
                "OPENKILL_NFT_SHADOW_NODE4_FILE": continuity_test._wsl(self.harness.root / "missing-node4"),
                "OPENKILL_NFT_SHADOW_NODE6_FILE": continuity_test._wsl(self.harness.root / "missing-node6"),
                "OPENKILL_NFT_SHADOW_CAPTURE_FIXTURE": continuity_test._wsl(continuity_test.CAPTURE),
                "OPENKILL_NFT_SHADOW_RENDERER": continuity_test._wsl(renderer),
                "OPENKILL_NFT_SHADOW_TEMPLATE_DIR": continuity_test._wsl(continuity_test.TEMPLATE_DIR),
                "OPENKILL_NFT_SHADOW_TELEMETRY_DIR": continuity_test._wsl(telemetry),
                "OPENKILL_TUN_OWNER": "openkill",
                "OPENKILL_RUN_MODE": "tUn",
                "OPENKILL_PROXY_PORT": "7892",
                "OPENKILL_TPROXY_PORT": "7895",
                "OPENKILL_DNS_PORT": "7874",
                "OPENKILL_ROUTER_SELF_PROXY": "0",
                "OPENKILL_FWMARK": "0x162",
                "OPENKILL_FWMASK": "0xffffffff",
                "OPENKILL_RULE_PREF": "1888",
            },
        )
        self.assertIn("RC=0", process.stdout, process.stderr)
        status = self_test._status_file(telemetry / "status")
        self.assertEqual(status.get("status"), "MATCH")
        emitted_text = emitted.read_text(encoding="utf-8")
        self.assertTrue(emitted_text.startswith("SHELL_RENDERER_INPUT_V1\t1\n"))
        self.assertIn("META\towner\tOPENKILL", emitted_text)
        self.assertIn("META\tmark\t0x162", emitted_text)
        self.assertIn("META\tmask\t0xffffffff", emitted_text)
        self.assertIn("META\troute_table\t354", emitted_text)
        self.assertIn("META\trule_pref\t1888", emitted_text)
        self.assertFalse((self.harness.root / "generation").exists())
        self.assertTrue((telemetry / "status").exists())

    def test_network_source_maps_mark_and_route_table_independently(self) -> None:
        snapshot = self.harness.root / "network-snapshot"
        desired = self.harness.root / "network-desired"
        self_test._write_lf(snapshot, "SNAPSHOT_VERSION=1\nLOCAL_IPV6_READY=1\n")
        body = (
            f". {self_test._quote(self_test._wsl_path(NETWORK_HELPER))}; "
            'OPENKILL_FWMARK="0x123"; OPENKILL_FWMASK="0xffffffff"; '
            'OPENKILL_ROUTE_TABLE="456"; OPENKILL_RULE_PREF="789"; '
            f"openkill_build_desired_state {self_test._quote(self_test._wsl_path(snapshot))} "
            f"{self_test._quote(self_test._wsl_path(desired))}; printf 'RC=%s\\n' \"$?\""
        )
        process = self._busybox_run(body, {})
        self.assertIn("RC=0", process.stdout, process.stderr)
        state = dict(
            line.split("=", 1)
            for line in desired.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        self.assertEqual(state["OPENKILL_FWMARK"], "0x123")
        self.assertEqual(state["OPENKILL_ROUTE_TABLE"], "456")
        self.assertNotEqual(state["OPENKILL_FWMARK"], state["OPENKILL_ROUTE_TABLE"])

    def test_same_raw_state_keeps_continuity_token_without_generation_file(self) -> None:
        state_text = continuity_test.AUTO_SOURCE.read_text(encoding="utf-8").replace("OWNER=OPENKILL", "OWNER=openkill", 1)
        state_text = state_text.replace("GENERATION=fixture-g1\n", "")
        desired = self.harness.root / "token-desired"
        applied = self.harness.root / "token-applied"
        self_test._write_lf(desired, state_text)
        self_test._write_lf(applied, state_text)
        first = self.harness.root / "token-first"
        second = self.harness.root / "token-second"
        body = (
            f"openkill_shadow_auto_continuity_token {self_test._quote(continuity_test._wsl(first))} "
            f"{self_test._quote(continuity_test._wsl(self.harness.root / 'token-work-1'))} "
            f"{self_test._quote(continuity_test._wsl(desired))} {self_test._quote(continuity_test._wsl(applied))} "
            f"{self_test._quote(continuity_test._wsl(self.harness.root / 'missing-snapshot'))} "
            f"{self_test._quote(continuity_test._wsl(self.harness.root / 'missing-node4'))} "
            f"{self_test._quote(continuity_test._wsl(self.harness.root / 'missing-node6'))} || exit 91; "
            f"openkill_shadow_auto_continuity_token {self_test._quote(continuity_test._wsl(second))} "
            f"{self_test._quote(continuity_test._wsl(self.harness.root / 'token-work-2'))} "
            f"{self_test._quote(continuity_test._wsl(desired))} {self_test._quote(continuity_test._wsl(applied))} "
            f"{self_test._quote(continuity_test._wsl(self.harness.root / 'missing-snapshot'))} "
            f"{self_test._quote(continuity_test._wsl(self.harness.root / 'missing-node4'))} "
            f"{self_test._quote(continuity_test._wsl(self.harness.root / 'missing-node6'))}; "
            "cmp -s "
            f"{self_test._quote(continuity_test._wsl(first))} {self_test._quote(continuity_test._wsl(second))}; "
            "printf 'RC=%s\\n' \"$?\""
        )
        process, _ = self.harness.run(body)
        self.assertIn("RC=0", process.stdout, process.stderr)

    def test_static_guard_keeps_character_class_tr_out_of_shadow_enum_path(self) -> None:
        helper = self_test.HELPER.read_text(encoding="utf-8")
        self.assertNotRegex(helper, r"tr\s+['\"]\[:lower:\]['\"]\s+['\"]\[:upper:\]['\"]")
        self.assertNotRegex(helper, r"tr\s+['\"]\[:upper:\]['\"]\s+['\"]\[:lower:\]['\"]")
        syntax_command = (
            ["wsl.exe", "-u", "root", "--", "busybox", "sh", "-n", self_test._wsl_path(self_test.HELPER)]
            if shutil.which("wsl.exe")
            else ["busybox", "sh", "-n", str(self_test.HELPER)]
        )
        syntax = subprocess.run(syntax_command, cwd=ROOT, capture_output=True, text=True, check=False, timeout=30)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
