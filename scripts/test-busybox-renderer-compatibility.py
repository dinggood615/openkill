#!/usr/bin/env python3
"""Focused BusyBox compatibility tests for the production shell renderer.

The device failure was in the renderer's input boundary, before any nft
payload semantics were reached.  These tests run the renderer twice: once
with the host WSL utilities and once with a PATH containing BusyBox applets
for every external utility used by the renderer.  The latter matches the
OpenWrt execution model closely enough to exercise the problematic awk
implementation without contacting a device.
"""

from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from typing import Tuple


ROOT = pathlib.Path(__file__).resolve().parents[1]
RENDERER = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_nft_renderer.sh"


def _load_shell_renderer_helpers():
    path = ROOT / "scripts/test-shell-renderer.py"
    spec = importlib.util.spec_from_file_location("openkill_shell_renderer_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load shell renderer helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPERS = _load_shell_renderer_helpers()


def _wsl_path(path: pathlib.Path) -> str:
    return HELPERS._wsl_path(path)


def _run_renderer(
    renderer: pathlib.Path,
    input_path: pathlib.Path,
    *,
    busybox: bool,
    timeout: int = 60,
) -> Tuple[int, str, str]:
    if busybox:
        command = [
            "wsl.exe", "-u", "root", "--", "busybox", "ash",
            _wsl_path(HELPERS_BUSYBOX_RUNNER), _wsl_path(renderer), _wsl_path(input_path),
        ]
    else:
        command = ["wsl.exe", "-u", "root", "--", "sh", _wsl_path(renderer), _wsl_path(input_path)]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _replace_once(data: bytes, old: bytes, new: bytes) -> bytes:
    if data.count(old) != 1:
        raise AssertionError("fixture replacement was not unique: {!r}".format(old))
    return data.replace(old, new, 1)


class BusyBoxRendererCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("wsl.exe") is None:
            raise unittest.SkipTest("WSL is required for the local BusyBox compatibility gate")
        cls.temp = tempfile.TemporaryDirectory(prefix="openkill-busybox-renderer-")
        cls.root = pathlib.Path(cls.temp.name)
        cls.input_path = cls.root / "valid.tsv"
        cls.input_path.write_bytes(cls._load_valid_input())

        global HELPERS_BUSYBOX_RUNNER
        HELPERS_BUSYBOX_RUNNER = cls.root / "busybox-runner.sh"
        HELPERS_BUSYBOX_RUNNER.write_text(
            "#!/bin/sh\n"
            "d=$(mktemp -d) || exit 70\n"
            "for a in awk od sed sort; do ln -s /usr/bin/busybox \"$d/$a\" || exit 71; done\n"
            "PATH=\"$d:/usr/bin:/bin\"; export PATH\n"
            "busybox ash \"$1\" \"$2\"\n"
            "status=$?\n"
            "rm -rf \"$d\"\n"
            "exit $status\n",
            encoding="utf-8",
            newline="\n",
        )
        cls.old_renderer = cls.root / "old" / "openkill_nft_renderer.sh"
        cls.old_renderer.parent.mkdir()
        source = RENDERER.read_text(encoding="utf-8")
        safe_structural = 'if ($0 ~ /\\r/ || index($0, "|") > 0) bad=1'
        unsafe_structural = 'if ($0 ~ /\\r/ || $0 ~ /\\x00/ || index($0, "|") > 0) bad=1'
        if source.count(safe_structural) != 1:
            raise RuntimeError("renderer structural guard changed; update the focused regression")
        old = source.replace(safe_structural, unsafe_structural, 1)
        cls.old_renderer.write_text(old, encoding="utf-8", newline="\n")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    @staticmethod
    def _load_valid_input() -> bytes:
        state = HELPERS.load_states()[0]
        text, _ = HELPERS.state_to_input(state)
        return text.encode("utf-8")

    def _write_case(self, name: str, data: bytes) -> pathlib.Path:
        path = self.root / (name + ".tsv")
        path.write_bytes(data)
        return path

    def _run_case(self, name: str, data: bytes, *, busybox: bool = True) -> Tuple[int, str, str]:
        return _run_renderer(RENDERER, self._write_case(name, data), busybox=busybox)

    def test_static_guard_and_valid_input_on_host_and_busybox(self) -> None:
        source = RENDERER.read_text(encoding="utf-8")
        structural = source.split("# Structural validation is deliberately performed", 1)[1]
        self.assertNotIn(r"\x", structural)
        self.assertIn("od -An -v -tx1", source)

        for busybox in (False, True):
            with self.subTest(busybox=busybox):
                rc, output, stderr = self._run_case("valid-{}".format(busybox), self.input_path.read_bytes(), busybox=busybox)
                self.assertEqual(rc, 0, stderr)
                self.assertTrue(output.startswith("# OPENKILL_SHELL_NFT_RENDERER_V1"))
                self.assertTrue(output)

    def test_old_busybox_bug_and_new_renderer_fix(self) -> None:
        old_rc, old_output, old_stderr = _run_renderer(
            self.old_renderer, self.input_path, busybox=True
        )
        self.assertEqual(old_rc, 64)
        self.assertEqual(old_output, "")
        self.assertIn("malformed input record", old_stderr)

        new_rc, new_output, new_stderr = self._run_case(
            "new-busybox-fix", self.input_path.read_bytes(), busybox=True
        )
        self.assertEqual(new_rc, 0, new_stderr)
        self.assertTrue(new_output)

    def test_valid_output_is_byte_identical_to_pre_fix_host_renderer(self) -> None:
        states = HELPERS.load_states()
        selected = [
            state for state in states
            if str(state.get("owner", "OPENKILL")) in {"OPENKILL", "MIHOMO", "DISABLED"}
        ][:4]
        self.assertEqual(len(selected), 4)
        for index, state in enumerate(selected):
            text, _ = HELPERS.state_to_input(state)
            path = self._write_case("golden-{}".format(index), text.encode("utf-8"))
            old_rc, old_output, old_stderr = _run_renderer(self.old_renderer, path, busybox=False)
            new_rc, new_output, new_stderr = _run_renderer(RENDERER, path, busybox=False)
            with self.subTest(state=state.get("id")):
                self.assertEqual(old_rc, 0, old_stderr)
                self.assertEqual(new_rc, 0, new_stderr)
                self.assertEqual(new_output, old_output)
                self.assertEqual(_sha256(new_output), _sha256(old_output))

    def test_real_nul_bytes_are_rejected_at_every_boundary_position(self) -> None:
        valid = self.input_path.read_bytes()
        cases = {
            "begin": b"\x00" + valid,
            "key": _replace_once(valid, b"META\towner\tOPENKILL", b"META\to\x00wner\tOPENKILL"),
            "delimiter": _replace_once(valid, b"META\towner\t", b"META\towner\x00"),
            "value": _replace_once(valid, b"META\towner\tOPENKILL", b"META\towner\tOPEN\x00KILL"),
            "end": valid.rstrip(b"\n") + b"\x00\n",
        }
        for name, data in cases.items():
            with self.subTest(position=name):
                rc, output, stderr = self._run_case("nul-" + name, data, busybox=True)
                self.assertEqual(rc, 64)
                self.assertEqual(output, "")
                self.assertIn("malformed input record", stderr)

    def test_literal_backslash_x00_is_text_not_a_nul_byte(self) -> None:
        data = _replace_once(self.input_path.read_bytes(), b"META\towner\tOPENKILL", b"META\towner\t\\x00")
        rc, output, stderr = self._run_case("literal-x00", data, busybox=True)
        self.assertEqual(rc, 64)
        self.assertEqual(output, "")
        self.assertIn("unknown owner", stderr)
        self.assertNotIn("malformed input record", stderr)

        unsupported = self.input_path.read_bytes() + b"UNSUPPORTED\tBC-99\t\\x00\n"
        rc, output, stderr = self._run_case("literal-x00-unsupported", unsupported, busybox=True)
        self.assertEqual(rc, 65)
        self.assertEqual(output, "")
        self.assertIn("unsupported", stderr.lower())
        self.assertNotIn("malformed input record", stderr)

    def test_bad_abi_values_reach_abi_guard_under_busybox(self) -> None:
        valid = self.input_path.read_bytes()
        cases = {
            "route-hex": (b"META\troute_table\t354", b"META\troute_table\t0x162"),
            "route-wrong": (b"META\troute_table\t354", b"META\troute_table\t355"),
            "mark-wrong": (b"META\tmark\t0x162", b"META\tmark\t0x163"),
            "mask-wrong": (b"META\tmask\t0xffffffff", b"META\tmask\t0xfffffffe"),
            "pref-wrong": (b"META\trule_pref\t1888", b"META\trule_pref\t1889"),
        }
        for name, (old, new) in cases.items():
            with self.subTest(case=name):
                data = _replace_once(valid, old, new)
                rc, output, stderr = self._run_case("abi-" + name, data, busybox=True)
                self.assertEqual(rc, 66)
                self.assertEqual(output, "")
                self.assertIn("mark ABI mismatch", stderr)
                self.assertNotIn("malformed input record", stderr)

    def test_structurally_malformed_record_still_fails_closed(self) -> None:
        data = self.input_path.read_bytes() + b"BROKEN\tROW\n"
        rc, output, stderr = self._run_case("malformed-record", data, busybox=True)
        self.assertEqual(rc, 64)
        self.assertEqual(output, "")
        self.assertIn("malformed input record", stderr)

    def test_existing_crlf_contract_is_unchanged(self) -> None:
        data = self.input_path.read_bytes().replace(b"\n", b"\r\n")
        rc, output, stderr = self._run_case("crlf", data, busybox=True)
        self.assertEqual(rc, 66)
        self.assertEqual(output, "")
        self.assertIn("input version mismatch", stderr)

    def test_busybox_runtime_version_and_nul_probe(self) -> None:
        host_probe = subprocess.run(
            ["wsl.exe", "-u", "root", "--", "awk", "BEGIN { print (\"x\" ~ /\\x00/ ? \"MATCHES\" : \"NO_MATCH\") }"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        self.assertEqual(host_probe.returncode, 0, host_probe.stderr)
        self.assertEqual(host_probe.stdout.strip(), "NO_MATCH")
        version = subprocess.run(
            ["wsl.exe", "-u", "root", "--", "busybox"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        self.assertEqual(version.returncode, 0)
        self.assertIn("BusyBox", version.stdout)
        probe = subprocess.run(
            ["wsl.exe", "-u", "root", "--", "busybox", "awk", "BEGIN { print (\"x\" ~ /\\x00/ ? \"MATCHES\" : \"NO_MATCH\") }"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(probe.stdout.strip(), "MATCHES")


if __name__ == "__main__":
    unittest.main(verbosity=2)
