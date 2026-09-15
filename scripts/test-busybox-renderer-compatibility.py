#!/usr/bin/env python3
"""Focused BusyBox capability tests for the production shell renderer.

The device failure was in the renderer's input boundary, before any nft
payload semantics were reached.  These tests run the renderer with a tightly
controlled BusyBox PATH.  The target model exposes ``hexdump`` while omitting
``od``; an od-only model exercises the compatibility fallback and a no-scanner
model proves that capability failures remain fail-closed.  No device is
contacted.
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
HELPERS_SHADOW = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_nft_shadow.sh"
TEMPLATE_DIR = ROOT / "luci-app-openkill/root/usr/share/openkill/shadow"
AUTO_SOURCE = ROOT / "scripts/fixtures/openkill-shadow-auto-state-v1.txt"


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
    environment: str,
    timeout: int = 60,
) -> Tuple[int, str, str]:
    if environment == "host":
        command = ["wsl.exe", "-u", "root", "--", "sh", _wsl_path(renderer), _wsl_path(input_path)]
    else:
        command = [
            "wsl.exe", "-u", "root", "--", "busybox", "ash",
            _wsl_path(HELPERS_BUSYBOX_RUNNER), _wsl_path(renderer), _wsl_path(input_path), environment,
        ]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _run_producer_renderer(
    source: pathlib.Path,
    template_dir: pathlib.Path,
    input_path: pathlib.Path,
    output_path: pathlib.Path,
    timeout: int = 60,
) -> Tuple[int, str, str]:
    command = [
        "wsl.exe", "-u", "root", "--", "busybox", "ash",
        _wsl_path(HELPERS_PRODUCER_RUNNER), _wsl_path(HELPERS_SHADOW), _wsl_path(RENDERER),
        _wsl_path(source), _wsl_path(template_dir), _wsl_path(input_path), _wsl_path(output_path),
    ]
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
            "for a in awk sed sort mktemp chmod rm; do ln -s /usr/bin/busybox \"$d/$a\" || exit 71; done\n"
            "mode=$3\n"
            "case \"$mode\" in\n"
            "  target) ln -s /usr/bin/busybox \"$d/hexdump\" || exit 71 ;;\n"
            "  od-only) ln -s /usr/bin/busybox \"$d/od\" || exit 71 ;;\n"
            "  none) : ;;\n"
            "  scanner-fail) printf '%s\\n' '#!/bin/sh' 'exit 7' > \"$d/hexdump\"; chmod +x \"$d/hexdump\" || exit 71 ;;\n"
            "  scanner-partial) printf '%s\\n' '#!/bin/sh' 'printf \\\"41\\\\n\\\"' 'exit 7' > \"$d/hexdump\"; chmod +x \"$d/hexdump\" || exit 71 ;;\n"
            "  inspector-fail) rm \"$d/awk\" || exit 71; printf '%s\\n' '#!/bin/sh' 'exit 9' > \"$d/awk\"; chmod +x \"$d/awk\" || exit 71; ln -s /usr/bin/busybox \"$d/hexdump\" || exit 71 ;;\n"
            "  scanner-invalid) printf '%s\\n' '#!/bin/sh' 'printf \\\"zz\\n\\\"' > \"$d/hexdump\"; chmod +x \"$d/hexdump\" || exit 71 ;;\n"
            "  *) exit 72 ;;\n"
            "esac\n"
            "PATH=\"$d\"; export PATH\n"
            "/usr/bin/busybox ash \"$1\" \"$2\"\n"
            "status=$?\n"
            "rm -rf \"$d\"\n"
            "exit $status\n",
            encoding="utf-8",
            newline="\n",
        )
        global HELPERS_PRODUCER_RUNNER
        HELPERS_PRODUCER_RUNNER = cls.root / "producer-renderer-runner.sh"
        HELPERS_PRODUCER_RUNNER.write_text(
            "#!/bin/sh\n"
            "d=$(mktemp -d) || exit 70\n"
            "trap 'rm -rf \"$d\"' EXIT\n"
            "for a in awk sed sort mktemp chmod rm sha256sum grep cp wc tr mkdir mv cat cmp hexdump; do ln -s /usr/bin/busybox \"$d/$a\" || exit 71; done\n"
            "PATH=\"$d\"; export PATH\n"
            "if command -v od >/dev/null 2>&1; then od=present; else od=absent; fi\n"
            ". \"$1\" || exit 72\n"
            ". \"$2\" || exit 73\n"
            "OPENKILL_NETWORK_DESIRED=\"$3\"\n"
            "OPENKILL_NETWORK_APPLIED_FILE=\"$3\"\n"
            "OPENKILL_NETWORK_SNAPSHOT=\"$d/no-snapshot\"\n"
            "OPENKILL_NFT_SHADOW_NODE4_FILE=\"$d/no-node4\"\n"
            "OPENKILL_NFT_SHADOW_NODE6_FILE=\"$d/no-node6\"\n"
            "OPENKILL_NFT_SHADOW_TEMPLATE_DIR=\"$4\"\n"
            "export OPENKILL_NETWORK_DESIRED OPENKILL_NETWORK_APPLIED_FILE OPENKILL_NETWORK_SNAPSHOT OPENKILL_NFT_SHADOW_NODE4_FILE OPENKILL_NFT_SHADOW_NODE6_FILE OPENKILL_NFT_SHADOW_TEMPLATE_DIR\n"
            "openkill_shadow_auto_continuity_snapshot \"$d/continuity\" || exit $?\n"
            "openkill_shadow_build_auto_input \"$5\" || exit $?\n"
            "openkill_render_nft_desired \"$5\" > \"$6\" || exit $?\n"
            "printf 'OD=%s\\n' \"$od\"\n"
            "exit 0\n",
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

    def _run_case(self, name: str, data: bytes, *, environment: str = "target") -> Tuple[int, str, str]:
        return _run_renderer(RENDERER, self._write_case(name, data), environment=environment)

    def _assert_no_nul_temp_dirs(self) -> None:
        proc = subprocess.run(
            [
                "wsl.exe", "-u", "root", "--", "find", "/tmp", "-maxdepth", "1",
                "-type", "d", "-name", "openkill-renderer-nul.*", "-print",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")

    def test_static_guard_and_valid_input_on_host_and_busybox(self) -> None:
        source = RENDERER.read_text(encoding="utf-8")
        structural = source.split("# Structural validation is deliberately performed", 1)[1]
        self.assertNotIn(r"\x", structural)
        self.assertNotIn(r"\x00", source)
        self.assertNotIn(r"/\x00/", source)
        self.assertIn("command -v hexdump", source)
        self.assertIn("hexdump -v -e '1/1 \"%02x\\n\"'", source)
        self.assertIn("od -An -v -tx1", source)
        self.assertIn('chmod 700 "$okr_nul_dir"', source)
        self.assertIn('chmod 600 "$okr_nul_hex"', source)
        self.assertIn("umask 077", source)

        for environment in ("host", "target", "od-only"):
            with self.subTest(environment=environment):
                rc, output, stderr = self._run_case("valid-{}".format(environment), self.input_path.read_bytes(), environment=environment)
                self.assertEqual(rc, 0, stderr)
                self.assertTrue(output.startswith("# OPENKILL_SHELL_NFT_RENDERER_V1"))
                self.assertTrue(output)
        self._assert_no_nul_temp_dirs()

    def test_capability_matrix_and_scanner_failures_are_fail_closed(self) -> None:
        valid = self.input_path.read_bytes()
        for environment in ("none", "scanner-fail", "scanner-partial", "scanner-invalid", "inspector-fail"):
            with self.subTest(environment=environment):
                rc, output, stderr = self._run_case("scanner-" + environment, valid, environment=environment)
                self.assertEqual(rc, 64)
                self.assertEqual(output, "")
                self.assertIn("cannot scan input bytes", stderr)
            self._assert_no_nul_temp_dirs()

    def test_full_producer_to_renderer_path_without_od(self) -> None:
        source_path = self.root / "auto-state.txt"
        source_path.write_bytes(AUTO_SOURCE.read_bytes())
        input_path = self.root / "producer-input.tsv"
        output_path = self.root / "producer-output.nft"
        rc, stdout, stderr = _run_producer_renderer(source_path, TEMPLATE_DIR, input_path, output_path)
        self.assertEqual(rc, 0, stderr)
        self.assertIn("OD=absent", stdout)
        input_text = input_path.read_text(encoding="utf-8")
        self.assertIn("META\troute_table\t354", input_text)
        self.assertIn("META\towner\tOPENKILL", input_text)
        self.assertIn("META\trun_mode\tTUN", input_text)
        rendered = output_path.read_text(encoding="utf-8")
        self.assertTrue(rendered.startswith("# OPENKILL_SHELL_NFT_RENDERER_V1"))
        self.assertTrue(rendered)
        self._assert_no_nul_temp_dirs()

    def test_repeated_and_all_zero_bytes_are_rejected(self) -> None:
        for name, data in (
            ("repeated", b"\x00" * 64),
            ("all-zero", b"\x00" * 4096),
        ):
            with self.subTest(case=name):
                rc, output, stderr = self._run_case("nul-" + name, data, environment="target")
                self.assertEqual(rc, 64)
                self.assertEqual(output, "")
                self.assertIn("malformed input record", stderr)
        self._assert_no_nul_temp_dirs()

    def test_empty_input_keeps_existing_structural_failure(self) -> None:
        rc, output, stderr = self._run_case("empty", b"", environment="target")
        self.assertEqual(rc, 66)
        self.assertEqual(output, "")
        self.assertIn("input version mismatch", stderr)
        self._assert_no_nul_temp_dirs()

    def test_old_busybox_bug_and_new_renderer_fix(self) -> None:
        old_rc, old_output, old_stderr = _run_renderer(
            self.old_renderer, self.input_path, environment="target"
        )
        self.assertEqual(old_rc, 64)
        self.assertEqual(old_output, "")
        self.assertIn("malformed input record", old_stderr)

        new_rc, new_output, new_stderr = self._run_case(
            "new-busybox-fix", self.input_path.read_bytes(), environment="target"
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
            old_rc, old_output, old_stderr = _run_renderer(self.old_renderer, path, environment="host")
            new_rc, new_output, new_stderr = _run_renderer(RENDERER, path, environment="host")
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
                rc, output, stderr = self._run_case("nul-" + name, data, environment="target")
                self.assertEqual(rc, 64)
                self.assertEqual(output, "")
                self.assertIn("malformed input record", stderr)

    def test_literal_backslash_x00_is_text_not_a_nul_byte(self) -> None:
        data = _replace_once(self.input_path.read_bytes(), b"META\towner\tOPENKILL", b"META\towner\t\\x00")
        rc, output, stderr = self._run_case("literal-x00", data, environment="target")
        self.assertEqual(rc, 64)
        self.assertEqual(output, "")
        self.assertIn("unknown owner", stderr)
        self.assertNotIn("malformed input record", stderr)

        unsupported = self.input_path.read_bytes() + b"UNSUPPORTED\tBC-99\t\\x00\n"
        rc, output, stderr = self._run_case("literal-x00-unsupported", unsupported, environment="target")
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
                rc, output, stderr = self._run_case("abi-" + name, data, environment="target")
                self.assertEqual(rc, 66)
                self.assertEqual(output, "")
                self.assertIn("mark ABI mismatch", stderr)
                self.assertNotIn("malformed input record", stderr)

    def test_structurally_malformed_record_still_fails_closed(self) -> None:
        data = self.input_path.read_bytes() + b"BROKEN\tROW\n"
        rc, output, stderr = self._run_case("malformed-record", data, environment="target")
        self.assertEqual(rc, 64)
        self.assertEqual(output, "")
        self.assertIn("malformed input record", stderr)

    def test_existing_crlf_contract_is_unchanged(self) -> None:
        data = self.input_path.read_bytes().replace(b"\n", b"\r\n")
        rc, output, stderr = self._run_case("crlf", data, environment="target")
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
