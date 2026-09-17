#!/usr/bin/env python3
"""Verify that gate timeouts clean only the process tree they own.

The fixture has no network access and deliberately ignores normal termination
signals.  The runner must terminate its exact PID tree while an unrelated
process remains alive until this test explicitly stops it.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts/openkill-test-gates.py"
spec = importlib.util.spec_from_file_location("openkill_test_gates_process", RUNNER_PATH)
assert spec and spec.loader
gates = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gates
spec.loader.exec_module(gates)


FIXTURE = r'''
import os, pathlib, signal, subprocess, sys, time

pid_file = pathlib.Path(sys.argv[2])
pid_file.write_text(str(os.getpid()), encoding="ascii")
signal.signal(signal.SIGTERM, signal.SIG_IGN)
if sys.argv[1] == "root":
    child_file = pathlib.Path(sys.argv[3])
    subprocess.Popen([sys.executable, __file__, "child", str(child_file)], close_fds=True)
while True:
    time.sleep(1)
'''.strip() + "\n"


def pid_alive(pid: int) -> bool:
    if os.name == "nt":
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            return False
        try:
            result = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command",
                 f"try {{ Get-Process -Id {pid} -ErrorAction Stop | Out-Null; exit 0 }} catch {{ exit 1 }}"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class ProcessOwnershipTests(unittest.TestCase):
    def test_timeout_reaps_owned_descendants_and_preserves_unrelated_process(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openkill-process-ownership-") as temp:
            directory = Path(temp)
            fixture = directory / "tree.py"
            fixture.write_text(FIXTURE, encoding="utf-8", newline="\n")
            root_pid_file = directory / "root.pid"
            child_pid_file = directory / "child.pid"
            unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                command = [sys.executable, str(fixture), "root", str(root_pid_file), str(child_pid_file)]
                owned_process, metadata = gates.run_owned_command(command, timeout=2)
                self.assertEqual(owned_process.returncode, 124)
                self.assertTrue(metadata.get("timed_out"))
                self.assertEqual(metadata.get("cleanup_status"), "PASS", metadata)
                self.assertEqual(metadata.get("orphan_count"), 0, metadata)
                for path in (root_pid_file, child_pid_file):
                    deadline = time.monotonic() + 5
                    while not path.exists() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    if path.exists():
                        self.assertFalse(pid_alive(int(path.read_text(encoding="ascii"))))
                self.assertTrue(pid_alive(unrelated.pid), "unrelated process was terminated")
            finally:
                if unrelated.poll() is None:
                    unrelated.terminate()
                    try:
                        unrelated.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        unrelated.kill()
                        unrelated.wait(timeout=5)

    def test_normal_exit_does_not_report_cleanup_as_needed(self) -> None:
        process, metadata = gates.run_owned_command([sys.executable, "-c", "print('owned-ok')"], timeout=10)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(metadata.get("cleanup_status"), "NOT_REQUIRED")
        self.assertEqual(metadata.get("orphan_count"), 0)

        failed, failed_metadata = gates.run_owned_command(
            [sys.executable, "-c", "raise SystemExit(9)"], timeout=10
        )
        self.assertEqual(failed.returncode, 9)
        self.assertEqual(failed_metadata.get("cleanup_status"), "NOT_REQUIRED")
        self.assertEqual(failed_metadata.get("orphan_count"), 0)

    def test_user_cancel_cleans_owned_tree_before_propagating(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openkill-process-cancel-") as temp:
            directory = Path(temp)
            fixture = directory / "tree.py"
            fixture.write_text(FIXTURE, encoding="utf-8", newline="\n")
            pid_file = directory / "root.pid"
            child_file = directory / "child.pid"
            real_popen = subprocess.Popen

            class InterruptingProcess:
                def __init__(self, *args, **kwargs):
                    self._process = real_popen(*args, **kwargs)
                    self.pid = self._process.pid
                    command_line = " ".join(str(value) for value in (args[0] if args else ()))
                    self._should_interrupt = str(fixture) in command_line
                    self._interrupted = not self._should_interrupt

                def communicate(self, *args, **kwargs):
                    if not self._interrupted:
                        self._interrupted = True
                        raise KeyboardInterrupt
                    return self._process.communicate(*args, **kwargs)

                def __getattr__(self, name):
                    return getattr(self._process, name)

                def __enter__(self):
                    self._process.__enter__()
                    return self

                def __exit__(self, *args):
                    return self._process.__exit__(*args)

            command = [sys.executable, str(fixture), "root", str(pid_file), str(child_file)]
            with mock.patch.object(gates.subprocess, "Popen", InterruptingProcess):
                with self.assertRaises(KeyboardInterrupt):
                    gates.run_owned_command(command, timeout=10)
            for path in (pid_file, child_file):
                deadline = time.monotonic() + 5
                while not path.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                if path.exists():
                    self.assertFalse(pid_alive(int(path.read_text(encoding="ascii"))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
