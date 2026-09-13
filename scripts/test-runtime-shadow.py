#!/usr/bin/env python3
"""Local harness for the Phase 3E read-only runtime shadow observer.

The harness runs the production-capable shell coordinator in a disposable WSL
process with fixture files only.  The old writer is represented by a recorder
function, while the new renderer writes only a temporary payload.  No firewall,
route, service, or device command is available to the child process.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SHARE = ROOT / "luci-app-openkill/root/usr/share/openkill"
HELPER = SHARE / "openkill_nft_shadow.sh"
RENDERER = SHARE / "openkill_nft_renderer.sh"
FIXTURE = SCRIPTS / "fixtures/openkill-runtime-shadow-v1.json"


def _load_shell_renderer_tests():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("openkill_shell_renderer_tests", SCRIPTS / "test-shell-renderer.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load shell renderer test helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SHELL_TESTS = _load_shell_renderer_tests()


def _wsl_path(path: pathlib.Path) -> str:
    resolved = path.resolve()
    if not resolved.drive:
        return str(resolved)
    drive = resolved.drive.rstrip(":").lower()
    tail = resolved.as_posix().split(":", 1)[-1]
    return "/mnt/{}/{}".format(drive, tail.lstrip("/"))


def _shell_script_command(path: pathlib.Path, shell: str = "sh") -> list[str]:
    if shutil.which("wsl.exe"):
        if shell == "busybox":
            return ["wsl.exe", "-u", "root", "--", "busybox", "sh", _wsl_path(path)]
        return ["wsl.exe", "-u", "root", "--", shell, _wsl_path(path)]
    return [shell, str(path)]


def _write_lf(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _status_file(path: pathlib.Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


class ShadowHarness:
    def __init__(self, input_text: str, old_text: str):
        self.temp = tempfile.TemporaryDirectory(prefix="openkill-runtime-shadow-")
        self.root = pathlib.Path(self.temp.name)
        self.input_text = input_text
        self.old_text = old_text
        self.renderer_wsl = _wsl_path(RENDERER)
        self.helper_wsl = _wsl_path(HELPER)

    def close(self) -> None:
        self.temp.cleanup()

    def run(
        self,
        name: str,
        *,
        input_text: str | None = None,
        old_text: str | None = None,
        owner: str | None = None,
        missing_input: bool = False,
        enabled: bool = True,
        old_rc: int = 0,
        source_drift: bool = False,
        renderer_mode: str | None = None,
        repeat: int = 1,
        shell: str = "sh",
    ) -> dict[str, object]:
        case = self.root / name
        case.mkdir(parents=True, exist_ok=True)
        input_path = case / "input.tsv"
        old_path = case / "old.nft"
        generation_path = case / "generation"
        state_path = case / "state"
        telemetry = case / "telemetry"
        trace_path = case / "writer.trace"
        log_path = case / "shadow.log"
        _write_lf(input_path, self.input_text if input_text is None else input_text)
        _write_lf(old_path, self.old_text if old_text is None else old_text)
        _write_lf(generation_path, "g1\n")

        state_lines = [
            "OPENKILL_SHADOW_STATE_V1=1",
            "INPUT_FILE=" + _wsl_path(input_path),
            "OLD_INTENT_FILE=" + _wsl_path(old_path),
            "GENERATION_FILE=" + _wsl_path(generation_path),
        ]
        if source_drift:
            source_path = case / "source.hash"
            baseline_path = case / "baseline.hash"
            _write_lf(source_path, "source\n")
            _write_lf(baseline_path, "baseline\n")
            state_lines.extend(
                [
                    "SOURCE_HASH_FILE=" + _wsl_path(source_path),
                    "BASELINE_HASH_FILE=" + _wsl_path(baseline_path),
                ]
            )
        if missing_input:
            # A missing source is an explicit input error, rather than a
            # silently invented production state.
            state_lines[1] = "INPUT_FILE=" + _wsl_path(case / "missing-input.tsv")
        _write_lf(state_path, "\n".join(state_lines) + "\n")

        renderer = RENDERER
        if renderer_mode:
            renderer = case / "renderer.sh"
            if renderer_mode == "error":
                body = "#!/bin/sh\nexit 67\n"
            elif renderer_mode == "stale":
                body = (
                    "#!/bin/sh\n"
                    "printf 'g2\\n' > " + _quote(_wsl_path(generation_path)) + "\n"
                    "exec sh " + _quote(self.renderer_wsl) + " \"$1\" \"$2\"\n"
                )
            elif renderer_mode == "timeout":
                body = "#!/bin/sh\nsleep 2\nexit 0\n"
            else:
                raise ValueError(renderer_mode)
            _write_lf(renderer, body)

        exports = [
            "export OPENKILL_NFT_SHADOW=" + ("1" if enabled else "0"),
            "export OPENKILL_NFT_SHADOW_STATE_FILE=" + _quote(_wsl_path(state_path)),
            "export OPENKILL_NFT_SHADOW_RENDERER=" + _quote(_wsl_path(renderer)),
            "export OPENKILL_NFT_SHADOW_TELEMETRY_DIR=" + _quote(_wsl_path(telemetry)),
            "export OPENKILL_NFT_SHADOW_FORCE=1",
            "export OPENKILL_NFT_SHADOW_TIMEOUT=1" if renderer_mode == "timeout" else "",
        ]
        exports = [line for line in exports if line]
        old_writer = (
            "old_writer() { printf '%s\\n' old-writer >> " + _quote(_wsl_path(trace_path)) + "; return " + str(old_rc) + "; }\n"
            "old_writer\n"
            "old_rc_value=$?\n"
        )
        calls = []
        for index in range(repeat):
            calls.append(
                "openkill_shadow_compare_nft > "
                + _quote(_wsl_path(case / ("shadow.%d.stdout" % index)))
                + " 2>"
                + _quote(_wsl_path(case / ("shadow.%d.stderr" % index)))
                + "\n"
                + "shadow_rc_%d=$?\n" % index
            )
        runner = case / "runner.sh"
        runner_text = "#!/bin/sh\nset +e\n" + "\n".join(exports) + "\n"
        runner_text += ". " + _quote(self.helper_wsl) + "\n"
        # Supply the same short warning hook that rc.common exposes.  The
        # helper must deduplicate an identical mismatch before invoking it.
        runner_text += "LOG_WARN(){ printf '%s\\n' \"$*\" >> " + _quote(_wsl_path(log_path)) + "; }\n"
        runner_text += old_writer + "".join(calls)
        runner_text += "printf 'OLD_RC=%s\\n' \"$old_rc_value\"\n"
        runner_text += "printf 'SHADOW_RC=%s\\n' \"${shadow_rc_0:-0}\"\n"
        if repeat > 1:
            runner_text += "printf 'SHADOW_RC_1=%s\\n' \"${shadow_rc_1:-0}\"\n"
        _write_lf(runner, runner_text)
        proc = subprocess.run(
            _shell_script_command(runner, shell),
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
        values: dict[str, str] = {}
        for line in proc.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        values["runner_rc"] = str(proc.returncode)
        status = _status_file(telemetry / "status")
        last_mismatch = (telemetry / "last_mismatch").read_text(encoding="utf-8") if (telemetry / "last_mismatch").is_file() else ""
        log_lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.is_file() else []
        trace = trace_path.read_text(encoding="utf-8").splitlines() if trace_path.is_file() else []
        values["status"] = status.get("status", "")
        values["reason"] = status.get("reason", "")
        values["last_mismatch"] = last_mismatch
        values["log_lines"] = "\n".join(log_lines)
        values["trace"] = "\n".join(trace)
        values["stdout"] = proc.stdout
        values["stderr"] = proc.stderr
        return values


class RuntimeShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        input_text, old_text = SHELL_TESTS.state_to_input(SHELL_TESTS.load_states()[0])
        cls.input_text = input_text
        cls.old_text = old_text
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def setUp(self):
        self.harness = ShadowHarness(self.input_text, self.old_text)

    def tearDown(self):
        self.harness.close()

    def test_default_off_does_not_invoke_renderer_or_write_telemetry(self):
        result = self.harness.run("disabled", enabled=False)
        self.assertEqual(result["runner_rc"], "0")
        self.assertEqual(result["SHADOW_RC"], "0")
        self.assertEqual(result["status"], "")
        self.assertEqual(result["trace"], "old-writer")

    def test_match_preserves_old_writer_and_publishes_bounded_status(self):
        result = self.harness.run("match")
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["SHADOW_RC"], "0")
        self.assertEqual(result["OLD_RC"], "0")
        self.assertEqual(result["trace"], "old-writer")
        status_text = self._status_text("match")
        self.assertIn("OPENKILL_NFT_SHADOW_TELEMETRY_V1=1", status_text)
        self.assertIn("compare_schema_version=1", status_text)
        self.assertIn("profile=current", status_text)
        self.assertIn("renderer_version=1", status_text)

    def test_error_and_mismatch_statuses_are_isolated(self):
        error = self.harness.run("renderer-error", renderer_mode="error", old_rc=17)
        self.assertEqual(error["status"], "RENDER_ERROR")
        self.assertEqual(error["OLD_RC"], "17")
        self.assertEqual(error["trace"], "old-writer")

        missing = self.harness.run("input-error", missing_input=True, old_rc=19)
        self.assertEqual(missing["status"], "INPUT_ERROR")
        self.assertEqual(missing["OLD_RC"], "19")

        changed = self.old_text.replace(" return comment", " counter comment", 1)
        mismatch = self.harness.run("mismatch", old_text=changed)
        self.assertEqual(mismatch["status"], "MISMATCH")
        self.assertEqual(mismatch["SHADOW_RC"], "1")

    def test_unsupported_current_cases_fail_closed(self):
        target = self.input_text.replace("META\tprofile\tcurrent", "META\tprofile\ttarget", 1)
        target_result = self.harness.run("target", input_text=target)
        self.assertEqual(target_result["status"], "UNSUPPORTED_CURRENT_STATE")
        self.assertEqual(target_result["SHADOW_RC"], "2")

        bc07 = self.input_text + "UNSUPPORTED\tBC-07\tACCESS_DENY\n"
        bc07_result = self.harness.run("bc07", input_text=bc07)
        self.assertEqual(bc07_result["status"], "UNSUPPORTED_CURRENT_STATE")
        self.assertEqual(bc07_result["SHADOW_RC"], "2")

    def test_source_drift_and_generation_change_never_report_match(self):
        drift = self.harness.run("source-drift", source_drift=True)
        self.assertEqual(drift["status"], "SOURCE_DRIFT")
        self.assertEqual(drift["SHADOW_RC"], "5")

        stale = self.harness.run("stale", renderer_mode="stale")
        self.assertEqual(stale["status"], "STALE")
        self.assertEqual(stale["SHADOW_RC"], "6")

    def test_owner_skip_noop_and_old_failure_paths(self):
        mihomo = self.harness.run("mihomo", input_text=self.input_text.replace("META\towner\tOPENKILL", "META\towner\tMIHOMO", 1))
        disabled = self.harness.run("owner-disabled", input_text=self.input_text.replace("META\towner\tOPENKILL", "META\towner\tDISABLED", 1))
        for result in (mihomo, disabled):
            self.assertEqual(result["status"], "DISABLED")
            self.assertEqual(result["SHADOW_RC"], "0")

        no_action = self.harness.run("no-action")
        self.assertEqual(no_action["status"], "MATCH")
        self.assertEqual(no_action["trace"], "old-writer")

        reload_success = self.harness.run("reload-success")
        self.assertEqual(reload_success["status"], "MATCH")
        self.assertEqual(reload_success["OLD_RC"], "0")

        old_failure = self.harness.run("old-failure", old_rc=23)
        self.assertEqual(old_failure["OLD_RC"], "23")
        self.assertEqual(old_failure["status"], "MATCH")
        self.assertEqual(old_failure["trace"], "old-writer")

    def test_repeated_mismatch_has_one_bounded_dedupe_key(self):
        changed = self.old_text.replace(" return comment", " counter comment", 1)
        result = self.harness.run("repeat-mismatch", old_text=changed, repeat=2)
        self.assertEqual(result["status"], "MISMATCH")
        self.assertEqual(result["SHADOW_RC"], "1")
        self.assertEqual(result["SHADOW_RC_1"], "1")
        self.assertTrue(result["last_mismatch"])
        self.assertNotIn("198.51.100.1", result["last_mismatch"])
        self.assertEqual(len(result["log_lines"].splitlines()), 1)

    def test_old_writer_trace_is_identical_with_shadow_enabled(self):
        # The recorder stands in for the already authoritative writer.  Run a
        # representative set of stable boundaries with the observer disabled
        # and enabled; only the observer's telemetry may differ.
        for name in ("basic-tun", "tproxy", "dns", "node", "acl", "no-action"):
            with self.subTest(boundary=name):
                before = self.harness.run(name + "-before", enabled=False)
                after = self.harness.run(name + "-after", enabled=True)
                self.assertEqual(before["trace"], after["trace"])
                self.assertEqual(before["OLD_RC"], after["OLD_RC"])

    def test_timeout_is_a_compare_error_and_old_path_stays_successful(self):
        result = self.harness.run("timeout", renderer_mode="timeout")
        self.assertEqual(result["status"], "COMPARE_ERROR")
        self.assertEqual(result["SHADOW_RC"], "7")
        self.assertEqual(result["OLD_RC"], "0")

    def test_source_hashes_and_callsite_boundary(self):
        sys.path.insert(0, str(SCRIPTS))
        from openkill_production_shadow import production_function_hashes

        current = production_function_hashes(ROOT)
        for name, expected in self.fixture["production_source_hashes"].items():
            self.assertEqual(current[name]["sha256"], expected, name)

        init = (ROOT / "luci-app-openkill/root/etc/init.d/openkill").read_text(encoding="utf-8")
        self.assertGreaterEqual(init.count("openkill_shadow_compare_nft"), 1)
        self.assertGreaterEqual(init.count("openkill_shadow_stable_boundary"), 3)
        self.assertIn(". $IPKG_INSTROOT/usr/share/openkill/openkill_nft_shadow.sh", init)
        for rel in (
            "luci-app-openkill/root/usr/share/openkill/openkill_network.sh",
            "luci-app-openkill/root/usr/share/openkill/openkill_watchdog.sh",
            "luci-app-openkill/root/usr/share/openkill/openkill_fw4_reload.sh",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("openkill_shadow_compare_nft", text)
            self.assertNotIn("openkill_nft_renderer.sh", text)
        helper = HELPER.read_text(encoding="utf-8")
        self.assertNotIn("eval", helper.lower())
        self.assertNotRegex(helper, r"(?m)^\s*(?:uci|ubus|ip|ip6tables|iptables|nft|fw4|service|nslookup|resolveip|curl)\b")
        self.assertNotRegex(helper, r"nft\s+(?:-f|add|insert|delete|replace|flush)\b")
        self.assertNotIn("python", helper.lower())

    def test_shell_syntax_and_state_protocol_are_versioned(self):
        proc = subprocess.run(
            (["wsl.exe", "-u", "root", "--", "sh", "-n", _wsl_path(HELPER)]
             if shutil.which("wsl.exe") else ["sh", "-n", str(HELPER)]),
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        if shutil.which("wsl.exe"):
            busybox = subprocess.run(
                ["wsl.exe", "-u", "root", "--", "busybox", "sh", "-n", _wsl_path(HELPER)],
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(busybox.returncode, 0, busybox.stderr)
            busybox_run = self.harness.run("busybox-match", shell="busybox")
            self.assertEqual(busybox_run["status"], "MATCH")
        self.assertEqual(self.fixture["schema"], "OPENKILL_RUNTIME_SHADOW_V1")
        self.assertEqual(self.fixture["protocol_version"], 1)
        self.assertEqual(self.fixture["compare_schema_version"], 1)
        self.assertEqual(self.fixture["state_schema_version"], 1)
        self.assertEqual(self.fixture["renderer_version"], 1)
        self.assertEqual(self.fixture["default"], "OFF")
        self.assertEqual(len(self.fixture["scenarios"]), 15)
        self.assertTrue(all(item.startswith("SH-") for item in self.fixture["scenarios"]))
        self.assertEqual(
            set(self.fixture["statuses"]),
            {"MATCH", "KNOWN_CURRENT_GAP", "UNSUPPORTED_CURRENT_STATE", "MISMATCH", "INPUT_ERROR", "RENDER_ERROR", "COMPARE_ERROR", "SOURCE_DRIFT", "DISABLED", "STALE"},
        )

    def _status_text(self, name: str) -> str:
        # Kept as a small helper for the bounded telemetry assertion.  Each
        # test owns a fresh harness directory, so locate the sole status file.
        files = list(self.harness.root.glob(name + "/telemetry/status"))
        return files[0].read_text(encoding="utf-8") if files else ""


if __name__ == "__main__":
    unittest.main(verbosity=2)
