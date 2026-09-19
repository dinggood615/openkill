#!/usr/bin/env python3
"""Unified, local-only OpenKill validation gates.

The runner deliberately owns only test orchestration.  It never opens a
network socket to a device, invokes scp/ssh, installs a package, or enables a
dataplane writer.  Every case is executed independently and its return code
is recorded, so a later successful command cannot hide an earlier failure.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import signal
import shutil
import subprocess
import sys
import time
import uuid
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = Path(__file__).resolve()
RUNNER_VERSION = "2"
RUNNER_SOURCE_HASH = hashlib.sha256(RUNNER_PATH.read_bytes()).hexdigest()
CANONICAL_CONFIG = ROOT / "scripts/fixtures/3e2-safe.yaml"
CANONICAL_CONFIG_SHA256 = "9cd8d91750758823776df9c982c1e15f0baa1a72baa1792fa2f82c0df4d24a6e"
OBSERVER = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_nft_shadow.sh"
RENDERER = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_nft_renderer.sh"
MANIFEST = ROOT / "luci-app-openkill/root/usr/share/openkill/shadow/semantic_model_v1.tsv"
TEMPLATES = ROOT / "luci-app-openkill/root/usr/share/openkill/shadow"
TUN_TEMPLATE = TEMPLATES / "input_tun_v1.tsv"
EVIDENCE_ROOT = ROOT / "artifacts/test-evidence"
CACHE_ROOT = EVIDENCE_ROOT / "cache"


@dataclass(frozen=True)
class Case:
    name: str
    script: str | None
    args: tuple[str, ...] = ()
    environment: str = "windows"
    timeout: int = 180
    command: tuple[str, ...] = ()
    cacheable: bool = True
    skip_policy: tuple[str, ...] = ()


NATIVE_TESTS: tuple[Case, ...] = tuple(
        Case(
            name=path.stem,
            script=f"scripts/{path.name}",
            timeout=180,
            skip_policy=("NFT_CLI_UNAVAILABLE",) if path.stem == "test-nft-syntax" else
            ("PLAYWRIGHT_UNAVAILABLE", "PLAYWRIGHT_BROWSER_UNAVAILABLE") if path.stem == "test-ui-browser" else (),
        )
    for path in (
        Path("test-3e2-safe-config.py"),
        Path("test-autonomous-workflow.py"),
        Path("test-busybox-renderer-compatibility.py"),
        Path("test-central-wiring.py"),
        Path("test-classifier-contract.py"),
        Path("test-dataplane-semantic-spec.py"),
        Path("test-dns-current-intent.py"),
        Path("test-nft-device-parser.py"),
        Path("test-nft-ir.py"),
        Path("test-nft-syntax.py"),
        Path("test-production-shadow.py"),
        Path("test-runtime-shadow.py"),
        Path("test-shadow-busybox-normalization.py"),
        Path("test-shadow-context-adapter.py"),
        Path("test-shadow-continuity.py"),
        Path("test-shadow-production-typed.py"),
        Path("test-shadow-self-sufficiency.py"),
        Path("test-shadow-semantic-model.py"),
        Path("test-shadow-sidecar-producer.py"),
        Path("test-shell-renderer.py"),
        Path("test-process-ownership.py"),
        Path("test-core-download-contract.py"),
        Path("test-openkill-optimization.py"),
        Path("test-openvpn-compatibility.py"),
        Path("test-openkill-test-gates.py"),
        Path("test-ui-contract.py"),
        Path("test-ui-interactions.py"),
        Path("test-ui-browser.py"),
        Path("test-ui-preview.py"),
        Path("test-uci-lifecycle.py"),
    )
)

# The shell/Python differential renderer deliberately exercises every current
# state and invokes several isolated POSIX shells; on a cold Windows/WSL host
# it takes about three minutes. Continuity also launches many short-lived WSL
# shells. Keep both timeouts separate from ordinary unit suites so a slow host
# is not mistaken for a functional failure.
NATIVE_TESTS = tuple(
    Case(
        case.name,
        case.script,
        case.args,
        case.environment,
        360 if case.name == "test-shell-renderer" else 300 if case.name == "test-shadow-continuity" else case.timeout,
        case.command,
        case.cacheable,
        case.skip_policy,
    )
    for case in NATIVE_TESTS
)

WSL_RUBY_POLICY = ("WSL_UNAVAILABLE", "RUBY_UNAVAILABLE")
WSL_CORE_POLICY = ("WSL_UNAVAILABLE", "CORE_RELEASE_UNAVAILABLE")

WSL_TESTS: tuple[Case, ...] = (
    Case("test-installer-wsl", "scripts/test-installer.py", environment="wsl", timeout=300, skip_policy=WSL_RUBY_POLICY),
    Case("test-network-model-wsl", "scripts/test-network-model.py", environment="wsl", timeout=300, skip_policy=("WSL_UNAVAILABLE",)),
    Case("test-runtime-wsl", "scripts/test-runtime.py", environment="wsl", timeout=300, skip_policy=WSL_RUBY_POLICY),
    Case("test-snapshot-fw4-wsl", "scripts/test-snapshot-fw4.py", environment="wsl", timeout=300, skip_policy=("WSL_UNAVAILABLE",)),
    Case("test-stage-d-wsl", "scripts/test-stage-d.py", environment="wsl", timeout=300, skip_policy=("WSL_UNAVAILABLE",)),
    Case("test-core-v1_19_30-wsl", "scripts/test-core.py", ("--release", "v1.19.30"), "wsl", 600, skip_policy=WSL_CORE_POLICY),
    Case("test-core-latest-wsl", "scripts/test-core.py", ("--release", "latest"), "wsl", 600, skip_policy=WSL_CORE_POLICY),
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    if not resolved.drive:
        return resolved.as_posix()
    drive = resolved.drive.rstrip(":").lower()
    tail = resolved.as_posix().split(":", 1)[-1]
    return f"/mnt/{drive}/{tail.lstrip('/')}"


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def candidate_manifest(run_id: str) -> tuple[dict[str, object], str]:
    role_by_path = {
        OBSERVER: "staged-observer",
        RENDERER: "renderer",
        MANIFEST: "semantic-manifest",
        TUN_TEMPLATE: "renderer-template",
    }
    # The preflight candidate is for the canonical D2D TUN profile.  Keep the
    # upload set minimal and explicit: REDIRECT/TPROXY templates are valid
    # product assets, but are not consumed by this device retry.
    files = [OBSERVER, RENDERER, MANIFEST, TUN_TEMPLATE]
    entries = []
    for path in sorted(set(files)):
        if not path.is_file():
            raise FileNotFoundError(f"required candidate artifact is missing: {path.relative_to(ROOT)}")
        entries.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "role": role_by_path.get(path, "runtime-dependency"),
            }
        )
    canonical_sha = sha256_file(CANONICAL_CONFIG)
    if canonical_sha != CANONICAL_CONFIG_SHA256:
        raise ValueError(
            "canonical D2D fixture hash mismatch: "
            f"expected {CANONICAL_CONFIG_SHA256}, got {canonical_sha}"
        )
    stable = {
        "head": git_head(),
        "runner_version": RUNNER_VERSION,
        "runner_source_hash": RUNNER_SOURCE_HASH,
        "canonical_config": {
            "path": CANONICAL_CONFIG.relative_to(ROOT).as_posix(),
            "sha256": canonical_sha,
        },
        "artifacts": entries,
        "minimal_staging_artifacts": [entry["path"] for entry in entries if entry["role"] in ("staged-observer", "semantic-manifest", "renderer", "renderer-template")],
    }
    candidate_id = sha256_bytes(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode())
    manifest = dict(stable)
    manifest["evidence_run_id"] = run_id
    manifest["candidate_id"] = candidate_id
    manifest["execution_identity_hash"] = candidate_id
    return manifest, candidate_id


def dependency_files(case: Case) -> list[Path]:
    paths: list[Path] = []
    if case.script:
        paths.append(ROOT / case.script)
    paths.extend((OBSERVER, RENDERER, MANIFEST))
    paths.extend(sorted(TEMPLATES.glob("*.tsv")))
    if case.name.startswith("test-core"):
        paths.extend((ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_validate.sh",))
    if case.name == "test-core-download-contract":
        paths.append(ROOT / "scripts/test-core.py")
    if case.name == "compileall":
        paths.extend(sorted((ROOT / "scripts").glob("*.py")))
    if case.name in ("test-ui-contract", "test-ui-interactions", "test-ui-preview"):
        paths.extend(sorted((ROOT / "luci-app-openkill/luasrc/view/openkill").glob("*.htm")))
        paths.extend((
            ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/oc.css",
            ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css",
            ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/js/common.js",
            ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/js/oc-icons.js",
        ))
        if case.name in ("test-ui-interactions", "test-ui-preview"):
            paths.append(ROOT / "scripts/build-ui-preview.py")
    if case.name == "test-ui-browser":
        paths.extend((
            ROOT / "scripts/build-ui-preview.py",
            ROOT / "scripts/test-ui-browser.py",
            ROOT / "luci-app-openkill/luasrc/view/openkill/status.htm",
            ROOT / "luci-app-openkill/luasrc/view/openkill/myip.htm",
            ROOT / "luci-app-openkill/luasrc/view/openkill/config_upload.htm",
            ROOT / "luci-app-openkill/luasrc/view/openkill/config_edit.htm",
            ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/oc.css",
            ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css",
            ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/js/common.js",
            ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/js/oc-icons.js",
        ))
    if case.name == "test-openkill-test-gates":
        paths.append(RUNNER_PATH)
    if case.name == "test-process-ownership":
        paths.append(RUNNER_PATH)
    # The test suites import these modules dynamically (including through
    # WSL). Keep the cache bound to their actual bytes instead of a commit
    # label or only the top-level test file.
    paths.extend(sorted((ROOT / "scripts").glob("openkill_*.py")))
    paths.append(ROOT / "scripts/verify_3e2_safe_config.py")
    # The fixture directory is small and is a safer dependency boundary than
    # a commit id: changing any checked-in evidence invalidates its cache.
    paths.extend(sorted((ROOT / "scripts/fixtures").glob("*")))
    return sorted({path for path in paths if path.is_file()})


@lru_cache(maxsize=1)
def environment_versions() -> dict[str, str]:
    wsl_inventory = "unavailable"
    if wsl_available():
        # Hash the read-only distro inventory rather than trusting only the
        # host binary version; a changed distro/runtime invalidates WSL
        # evidence as well.
        wsl_inventory = json.dumps(_fingerprint_command(("wsl.exe", "-l", "-v")), sort_keys=True)
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "native_shell": read_version(("sh", "--version")),
        "wsl_host": read_version(("wsl.exe", "--version")) if wsl_available() else "unavailable",
        "wsl_inventory": wsl_inventory,
        "busybox": read_version(("busybox", "--help")),
    }


def dependency_key(case: Case) -> tuple[str, list[dict[str, str]]]:
    inputs = []
    for path in dependency_files(case):
        inputs.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)})
    versions = dict(environment_versions())
    if case.name == "test-ui-browser":
        versions["browser_runtime"] = browser_runtime_identity()
    versions.update({
        "environment": case.environment,
        "runner": RUNNER_VERSION,
        "runner_source_hash": RUNNER_SOURCE_HASH,
    })
    payload = {
        "case": case.name,
        "script": case.script,
        "args": case.args,
        "command": case.command,
        "skip_policy": case.skip_policy,
        "inputs": inputs,
        "versions": versions,
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()), inputs


def wsl_available() -> bool:
    return shutil.which("wsl.exe") is not None or shutil.which("wsl") is not None


def working_tree_status() -> str:
    result = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def candidate_identity_error(manifest: dict[str, object], candidate_id: str) -> str:
    """Verify that the bytes described before a gate stayed unchanged."""
    dirty = working_tree_status()
    if dirty:
        return "WORKING_TREE_CHANGED"
    if git_head() != manifest.get("head"):
        return "HEAD_CHANGED"
    if not RUNNER_PATH.is_file():
        return "RUNNER_SOURCE_MISSING"
    if sha256_file(RUNNER_PATH) != manifest.get("runner_source_hash"):
        return "RUNNER_SOURCE_CHANGED"
    canonical = manifest.get("canonical_config")
    if not isinstance(canonical, dict):
        return "CANONICAL_CONFIG_IDENTITY_MISSING"
    if not CANONICAL_CONFIG.is_file():
        return "CANONICAL_CONFIG_MISSING"
    if sha256_file(CANONICAL_CONFIG) != canonical.get("sha256"):
        return "CANONICAL_CONFIG_CHANGED"
    for entry in manifest.get("artifacts", []):
        path = ROOT / str(entry["path"])
        if not path.is_file():
            return "CANDIDATE_ARTIFACT_MISSING"
        if path.stat().st_size != entry.get("bytes") or sha256_file(path) != entry.get("sha256"):
            return f"CANDIDATE_ARTIFACT_CHANGED:{entry['path']}"
    _, current_id = candidate_manifest(str(manifest.get("evidence_run_id", "identity")))
    if current_id != candidate_id:
        return "CANDIDATE_ID_CHANGED"
    return ""


WSL_RUN_ROOT = "/tmp/openkill-test-runs"


def command_for(case: Case, run_token: str | None = None) -> list[str]:
    if case.command:
        return list(case.command)
    if not case.script:
        raise ValueError(f"case {case.name} has no command")
    interpreter = "sh" if case.script.endswith(".sh") else "python3"
    if case.environment == "windows":
        if interpreter == "sh":
            local_sh = shutil.which("sh")
            if local_sh:
                return [local_sh, str(ROOT / case.script), *case.args]
            return []
        return [sys.executable, str(ROOT / case.script), *case.args]
    if not wsl_available():
        return []
    root = wsl_path(ROOT)
    script = wsl_path(ROOT / case.script)
    args = " ".join(shell_quote(arg) for arg in case.args)
    command = f"cd {shell_quote(root)} && {interpreter} {shell_quote(script)}"
    if args:
        command += f" {args}"
    if run_token:
        # Keep a token-scoped Linux marker so a Windows timeout can verify the
        # WSL descendants are gone.  The trap is part of the temporary shell
        # only and never touches a distro-wide process or service.
        marker = f"{WSL_RUN_ROOT}/{run_token}"
        command = (
            f"umask 077; dir={shell_quote(marker)}; mkdir -p \"\\$dir\"; "
            "printf '%s\\n' \"\\$\\$\" > \"\\$dir/leader.pid\"; "
            "trap 'rm -rf \"\\$dir\"' EXIT HUP INT TERM; "
            f"export OPENKILL_TEST_RUN_TOKEN={shell_quote(run_token)}; {command}"
        )
    return ["wsl.exe", "-u", "root", "--", "sh", "-lc", command]


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        powershell = (
            shutil.which("powershell.exe")
            or shutil.which("pwsh.exe")
            or shutil.which("pwsh")
            or shutil.which("powershell")
        )
        if not powershell:
            return False
        try:
            result = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command",
                 f"try {{ Get-Process -Id {pid} -ErrorAction Stop | Out-Null; exit 0 }} catch {{ exit 1 }}"],
                cwd=ROOT,
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _wsl_token_count(run_token: str, *, cleanup: bool = False) -> tuple[int | None, int | None]:
    """Count (and optionally terminate) only WSL processes carrying our token."""
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if not wsl:
        return None, None
    marker = f"{WSL_RUN_ROOT}/{run_token}"
    cleanup_script = ""
    if cleanup:
        # Kill every process carrying this exact token, not just the shell
        # leader.  A child may ignore TERM or detach from the leader; the
        # token scan keeps cleanup scoped to this run and makes an orphan
        # observable instead of silently leaving it behind.
        cleanup_script = (
            "for envfile in /proc/[0-9]*/environ; do "
            "grep -aFq \"OPENKILL_TEST_RUN_TOKEN=\\$token\" \"\\$envfile\" 2>/dev/null || continue; "
            "pid=\\$(basename \"\\$(dirname \"\\$envfile\")\"); "
            "kill -TERM \"\\$pid\" 2>/dev/null || true; "
            "done; sleep 1; "
            "for envfile in /proc/[0-9]*/environ; do "
            "grep -aFq \"OPENKILL_TEST_RUN_TOKEN=\\$token\" \"\\$envfile\" 2>/dev/null || continue; "
            "pid=\\$(basename \"\\$(dirname \"\\$envfile\")\"); "
            "kill -KILL \"\\$pid\" 2>/dev/null || true; "
            "done; "
        )
    script = (
        f"token={shell_quote(run_token)}; marker={shell_quote(marker)}; "
        + (cleanup_script if cleanup else "")
        + "count=0; for envfile in /proc/[0-9]*/environ; do "
        "grep -aFq \"OPENKILL_TEST_RUN_TOKEN=\\$token\" \"\\$envfile\" 2>/dev/null || continue; "
        "count=\\$((count + 1)); done; printf 'COUNT=%s\\n' \"\\$count\"; "
        + ("rm -rf \"\\$marker\"; " if cleanup else "")
        + "exit 0"
    )
    try:
        result = subprocess.run(
            [wsl, "-u", "root", "--", "sh", "-lc", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None, None
    count = None
    for line in (result.stdout or "").splitlines():
        if line.startswith("COUNT="):
            try:
                count = int(line.split("=", 1)[1])
            except ValueError:
                count = None
    return count, result.returncode


def _terminate_windows_tree(pid: int) -> int:
    """Terminate descendants by exact parent-PID traversal, never by name."""
    powershell = (
        shutil.which("powershell.exe")
        or shutil.which("pwsh.exe")
        or shutil.which("pwsh")
        or shutil.which("powershell")
    )
    if not powershell:
        return 1
    script = """
$seen = @{}
function Stop-Children([int]$parent) {
    $children = Get-CimInstance Win32_Process -Filter ("ParentProcessId={0}" -f $parent) -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        $childPid = [int]$child.ProcessId
        if (-not $seen.ContainsKey($childPid)) {
            $seen[$childPid] = $true
            Stop-Children $childPid
            Stop-Process -Id $childPid -Force -ErrorAction SilentlyContinue
        }
    }
}
Stop-Children ROOT_PID
Stop-Process -Id ROOT_PID -Force -ErrorAction SilentlyContinue
exit 0
""".replace("ROOT_PID", str(pid))
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return 1
    return result.returncode


def _cleanup_owned_process(process: subprocess.Popen[str], run_token: str, *, wsl_owned: bool = False) -> dict[str, object]:
    """Terminate only the process tree created for one runner token.

    Windows uses taskkill with the exact root PID and tree flag. POSIX uses a
    private process group. No executable name or global process matching is
    used. The post-check is deliberately conservative: a live root is an
    orphan and fails the gate.
    """
    pid = process.pid
    cleanup_rc: int | None = None
    token_count: int | None = 0
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=10,
            )
            tree_rc = _terminate_windows_tree(pid)
            cleanup_rc = 0 if result.returncode == 0 or tree_rc == 0 else 1
        else:
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            cleanup_rc = 0
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name != "nt":
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=5)
        if wsl_owned:
            _, wsl_cleanup_rc = _wsl_token_count(run_token, cleanup=True)
            token_count, _ = _wsl_token_count(run_token, cleanup=False)
            if wsl_cleanup_rc != 0 or token_count != 0:
                cleanup_rc = 1
    except (OSError, subprocess.SubprocessError):
        cleanup_rc = 1
    time.sleep(0.1)
    alive = _pid_alive(pid)
    orphan_count = (1 if alive else 0) + (token_count or 0)
    return {
        "run_token": run_token,
        "owned_pid": pid,
        "cleanup_rc": cleanup_rc,
        "cleanup_status": "PASS" if not alive and orphan_count == 0 and cleanup_rc in (0, None) else "FAIL",
        "orphan_count": orphan_count,
    }


def run_owned_command(
    command: Sequence[str],
    *,
    timeout: int,
    env: dict[str, str] | None = None,
    run_token: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    """Run a command with an owned process boundary and verified cleanup."""
    run_token = run_token or uuid.uuid4().hex
    child_env = os.environ.copy()
    child_env.update(env or {})
    child_env["OPENKILL_TEST_RUN_TOKEN"] = run_token
    kwargs: dict[str, object] = {
        "cwd": ROOT,
        "env": child_env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    started = time.monotonic()
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(list(command), **kwargs)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            wsl_owned = bool(command and str(command[0]).lower().endswith(("wsl.exe", "wsl")))
            token_count = 0
            if wsl_owned:
                token_count, _ = _wsl_token_count(run_token)
                if token_count is None:
                    token_count = 1
            completed = subprocess.CompletedProcess(list(command), process.returncode, stdout, stderr)
            metadata = {
                "run_token": run_token,
                "owned_pid": process.pid,
                "cleanup_rc": 0,
                "cleanup_status": "NOT_REQUIRED",
                "orphan_count": token_count or 0,
                "timed_out": False,
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
            return completed, metadata
        except subprocess.TimeoutExpired as error:
            wsl_owned = bool(command and str(command[0]).lower().endswith(("wsl.exe", "wsl")))
            cleanup = _cleanup_owned_process(process, run_token, wsl_owned=wsl_owned)
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired as second_timeout:
                # A descendant that still owns a pipe is itself evidence of
                # incomplete cleanup.  Do not hang the runner or turn this
                # into a successful environment skip.
                stdout = _text(error.stdout) + _text(second_timeout.stdout)
                stderr = _text(error.stderr) + _text(second_timeout.stderr)
                cleanup["cleanup_status"] = "FAIL"
                cleanup["orphan_count"] = max(int(cleanup.get("orphan_count", 0)), 1)
            completed = subprocess.CompletedProcess(
                list(command),
                124,
                _text(error.stdout) + _text(stdout),
                _text(error.stderr) + _text(stderr) or "timeout",
            )
            cleanup.update({"timed_out": True, "elapsed_seconds": round(time.monotonic() - started, 3)})
            return completed, cleanup
        except KeyboardInterrupt:
            # Ctrl-C is a cancellation of this owned case.  Reuse the same
            # exact-PID/token cleanup path as a timeout before propagating the
            # interrupt to the suite, so a cancelled run cannot leave a child
            # process or WSL descendant behind.
            wsl_owned = bool(command and str(command[0]).lower().endswith(("wsl.exe", "wsl")))
            _cleanup_owned_process(process, run_token, wsl_owned=wsl_owned)
            try:
                process.communicate(timeout=5)
            except (OSError, subprocess.SubprocessError):
                pass
            raise
    except OSError as error:
        metadata = {
            "run_token": run_token,
            "owned_pid": process.pid if process is not None else None,
            "cleanup_rc": None,
            "cleanup_status": "NOT_STARTED",
            "orphan_count": 0,
            "timed_out": False,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        return subprocess.CompletedProcess(list(command), 127, "", str(error)), metadata


def _fingerprint_command(command: Sequence[str], timeout: int = 10) -> dict[str, object]:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {"available": False, "hash": "", "detail": type(error).__name__}
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    return {
        "available": result.returncode == 0,
        "hash": sha256_bytes(output.encode("utf-8", errors="replace")),
        "bytes": len(output.encode("utf-8", errors="replace")),
        "return_code": result.returncode,
    }


def host_network_snapshot() -> dict[str, object]:
    """Read a bounded, hashed host-network state without changing it."""
    if os.name == "nt":
        ps = (
            shutil.which("powershell.exe")
            or shutil.which("pwsh.exe")
            or shutil.which("pwsh")
            or shutil.which("powershell")
        )
        if not ps:
            return {"available": False, "reason": "POWERSHELL_UNAVAILABLE"}
        commands = {
            "default_route": [
                ps,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "@(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0'; Get-NetRoute -AddressFamily IPv6 -DestinationPrefix '::/0') | Sort-Object AddressFamily,InterfaceIndex,RouteMetric | Select-Object AddressFamily,InterfaceIndex,RouteMetric,NextHop | ConvertTo-Json -Compress",
            ],
            "dns": [ps, "-NoProfile", "-NonInteractive", "-Command", "Get-DnsClientServerAddress | Select-Object InterfaceAlias,AddressFamily,ServerAddresses | ConvertTo-Json -Compress"],
            "proxy": [ps, "-NoProfile", "-NonInteractive", "-Command", r"(netsh winhttp show proxy); (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue | Select-Object ProxyEnable,ProxyServer | ConvertTo-Json -Compress)"],
            "adapters": [ps, "-NoProfile", "-NonInteractive", "-Command", "Get-NetAdapter | Select-Object Name,Status,ifIndex,Virtual,MacAddress | Sort-Object ifIndex | ConvertTo-Json -Compress"],
            "listeners": [ps, "-NoProfile", "-NonInteractive", "-Command", "Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess | Sort-Object LocalPort,OwningProcess | ConvertTo-Json -Compress"],
            # ``--running`` is not supported consistently by older WSL builds
            # and returns 0xffffffff even when WSL is healthy.  ``-l -v`` is a
            # read-only, version-compatible inventory that includes each
            # distro's Running/Stopped state without starting one.
            "wsl_running": ["wsl.exe", "-l", "-v"],
        }
    else:
        commands = {
            "default_route": ["sh", "-c", "ip -4 route show default; ip -6 route show default"],
            "dns": ["sh", "-c", "cat /etc/resolv.conf"],
            "proxy": ["sh", "-c", "env | sed -n '/^[A-Za-z_]*proxy=/Ip'"],
            "adapters": ["sh", "-c", "ip -o link show"],
            "listeners": ["sh", "-c", "ss -lntup 2>/dev/null || true"],
            "wsl_running": ["sh", "-c", "printf 'not-applicable\\n'"],
        }
    result: dict[str, object] = {"available": True, "platform": platform.system()}
    for name, command in commands.items():
        result[name] = _fingerprint_command(command)
    required = ("default_route", "dns", "proxy", "adapters", "listeners")
    result["available"] = all(bool(result.get(name, {}).get("available")) for name in required)
    # A machine without WSL can still run the native portion of the local
    # gate.  If WSL is installed, however, an unreadable inventory is an
    # unknown network state and must fail closed rather than be ignored.
    if wsl_available() and not bool(result.get("wsl_running", {}).get("available")):
        result["available"] = False
        result["availability_reason"] = "WSL_INVENTORY_UNAVAILABLE"
    result["snapshot_hash"] = sha256_bytes(json.dumps(result, sort_keys=True, separators=(",", ":")).encode())
    return result


def network_guard_delta(before: dict[str, object], after: dict[str, object], *, wsl_case: bool = False) -> dict[str, object]:
    keys = ("default_route", "dns", "proxy", "adapters", "listeners", "wsl_running")
    changed = [key for key in keys if before.get(key) != after.get(key)]
    expected: list[str] = []
    classification = "NO_CHANGE"
    # WSL may stop an idle distro between two short native cases.  This is a
    # read-only lifecycle observation, not a host network mutation.  Keep it
    # explicit in evidence while continuing to fail closed on route, DNS,
    # proxy, adapter or listener changes.
    if changed == ["wsl_running"] and not wsl_case:
        expected = ["wsl_running"]
        classification = "WSL_LIFECYCLE_OBSERVED"
    # Starting a stopped WSL distro may add its virtual adapter and change the
    # distro inventory.  Host listener changes remain unexpected: a test must
    # not expose a new socket merely because it ran inside WSL.
    if wsl_case and changed and set(changed).issubset({"adapters", "wsl_running"}):
        expected = list(changed)
        classification = "WSL_BOOTSTRAP_OBSERVED"
    unexpected = [key for key in changed if key not in expected]
    return {
        "available": bool(before.get("available") and after.get("available")),
        "changed": changed,
        "expected_wsl_changes": expected,
        "unexpected": unexpected,
        "classification": classification,
        "status": "PASS" if not unexpected and before.get("available") and after.get("available") else "FAIL",
    }


def read_version(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    return (result.stdout or result.stderr).strip().splitlines()[0][:200] if (result.stdout or result.stderr) else "ok"


def browser_runtime_identity() -> str:
    """Return a read-only browser/Playwright identity for UI cache keys."""
    try:
        playwright_version = importlib.metadata.version("playwright")
    except importlib.metadata.PackageNotFoundError:
        playwright_version = "unavailable"

    candidates: list[Path] = []
    if os.name == "nt":
        roots = [
            Path(path)
            for path in (
                os.environ.get("PROGRAMFILES", ""),
                os.environ.get("PROGRAMFILES(X86)", ""),
            )
            if path
        ]
        candidates = [
            root / relative
            for root in roots
            for relative in (
                Path("Google/Chrome/Application/chrome.exe"),
                Path("Microsoft/Edge/Application/msedge.exe"),
            )
        ]
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            path = shutil.which(name)
            if path:
                candidates.append(Path(path))

    for executable in candidates:
        if executable.is_file():
            return json.dumps(
                {
                    "playwright": playwright_version,
                    "executable": str(executable),
                    "version": read_version((str(executable), "--version")),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
    return json.dumps(
        {"playwright": playwright_version, "executable": "unavailable", "version": "unavailable"},
        sort_keys=True,
        separators=(",", ":"),
    )


def build_cases(mode: str) -> list[Case]:
    policy = (
        Case("local-policy-gate", "scripts/local-gate.sh", environment="wsl", timeout=300, cacheable=False),
        Case("ci-workflow-separation-gate", "scripts/ci-gate.sh", environment="wsl", timeout=180),
        Case("compileall", None, command=(sys.executable, "-m", "compileall", "-q", "scripts"), timeout=180),
        Case("git-diff-check", None, command=("git", "diff", "--check"), timeout=60),
    )
    focused = (
        "test-3e2-safe-config",
        "test-shadow-sidecar-producer",
        "test-shadow-production-typed",
        "test-shadow-semantic-model",
        "test-uci-lifecycle",
        "test-process-ownership",
        "test-core-download-contract",
        "test-openkill-optimization",
        "test-production-shadow",
        "test-ui-contract",
        "test-ui-interactions",
        "test-ui-browser",
        "test-ui-preview",
    )
    native_by_name = {case.name: case for case in NATIVE_TESTS}
    if mode == "fast":
        # Fail-safe local checks run first, before WSL bootstrap or any Core
        # compatibility work.  This gives a quick signal for process leaks and
        # runner classification defects without spending time on the longer
        # policy/runtime cases.
        priority = ("test-process-ownership", "test-openkill-test-gates", "test-core-download-contract")
        remainder = tuple(name for name in focused if name not in priority)
        return [native_by_name[name] for name in priority] + list(policy) + [native_by_name[name] for name in remainder]
    if mode == "device-preflight":
        selected = list(policy)
        selected.extend(native_by_name.values())
        return selected
    if mode == "full":
        return list(policy) + list(NATIVE_TESTS) + list(WSL_TESTS)
    raise ValueError(mode)


def classify_output(case: Case, process: subprocess.CompletedProcess[str]) -> tuple[str, str]:
    output = (process.stdout or "") + "\n" + (process.stderr or "")
    if process.returncode == 124:
        return "FAIL", "TIMEOUT"
    if process.returncode == 0:
        # These are documented environment observations, not silent skips.
        if "nft CLI unavailable" in output or "nft command is unavailable" in output:
            reason = "NFT_CLI_UNAVAILABLE"
            return ("NOT_RUN_ENVIRONMENT", reason) if reason in case.skip_policy else ("FAIL", "UNDECLARED_ENVIRONMENT_SKIP")
        if "Ruby is not installed" in output or "Ruby required" in output:
            reason = "RUBY_UNAVAILABLE"
            return ("SKIP_ALLOWED", reason) if reason in case.skip_policy else ("FAIL", "UNDECLARED_ENVIRONMENT_SKIP")
        if case.name == "test-ui-browser":
            for reason in ("PLAYWRIGHT_UNAVAILABLE", "PLAYWRIGHT_BROWSER_UNAVAILABLE"):
                if f"OPENKILL_ENVIRONMENT_LIMIT={reason}" in output:
                    return ("NOT_RUN_ENVIRONMENT", reason) if reason in case.skip_policy else ("FAIL", "UNDECLARED_ENVIRONMENT_SKIP")
        return "PASS", ""
    # A release-download limitation is an explicit, structured result from
    # test-core.py.  Generic traceback text (including ``urlopen error``) is
    # an ordinary test failure and must never become a skip.
    if (
        case.name.startswith("test-core")
        and "OPENKILL_ENVIRONMENT_LIMIT=CORE_RELEASE_UNAVAILABLE" in output
    ):
        reason = "CORE_RELEASE_UNAVAILABLE"
        return ("NOT_RUN_ENVIRONMENT", reason) if reason in case.skip_policy else ("FAIL", "UNDECLARED_ENVIRONMENT_SKIP")
    return "FAIL", f"RETURN_CODE_{process.returncode}"


def gate_overall(mode: str, records: Sequence[dict[str, object]]) -> bool:
    """Return the mode result without treating required Core as completed.

    Ruby, nft and WSL availability have explicit documented policies.  A
    Mihomo Core release test is different: it is required evidence for a
    complete full/preflight gate, so an environment-limited Core result keeps
    the run from claiming readiness even though the reason is recorded.
    """
    allowed = {"PASS", "SKIP_ALLOWED", "NOT_RUN_ENVIRONMENT"}
    for record in records:
        if record.get("status") not in allowed:
            return False
        if str(record.get("name", "")).startswith("test-core") and record.get("status") == "NOT_RUN_ENVIRONMENT":
            return False
    return True


def write_case_output(directory: Path, name: str, process: subprocess.CompletedProcess[str] | None) -> None:
    if process is None:
        (directory / f"{name}.stdout").write_text("", encoding="utf-8")
        (directory / f"{name}.stderr").write_text("", encoding="utf-8")
        return
    (directory / f"{name}.stdout").write_text(process.stdout or "", encoding="utf-8", errors="replace")
    (directory / f"{name}.stderr").write_text(process.stderr or "", encoding="utf-8", errors="replace")


def run_case(case: Case, output_dir: Path, use_cache: bool) -> dict[str, object]:
    key, inputs = dependency_key(case)
    cache_file = CACHE_ROOT / f"{key}.json"
    if use_cache and case.cacheable and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if cached.get("status") in ("PASS", "SKIP_ALLOWED", "NOT_RUN_ENVIRONMENT") and cached.get("evidence_key") == key:
                write_case_output(output_dir, case.name, None)
                return {
                    "name": case.name,
                    "status": cached.get("status"),
                    "return_code": cached.get("return_code"),
                    "environment": case.environment,
                    "elapsed_seconds": 0,
                    "evidence_key": key,
                    "cached": True,
                    "reason": cached.get("reason", ""),
                    "original_reason": cached.get("original_reason", cached.get("reason", "")),
                    "cache_source": cached.get("evidence_path", str(cache_file)),
                    "run_token": cached.get("run_token"),
                    "owned_pid": cached.get("owned_pid"),
                    "cleanup_status": cached.get("cleanup_status", "CACHED"),
                    "orphan_count": cached.get("orphan_count", 0),
                    "timed_out": cached.get("timed_out", False),
                    "script": case.script,
                    "args": list(case.args),
                    "skip_policy": list(case.skip_policy),
                    "inputs": cached.get("inputs", inputs),
                }
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    if case.environment == "wsl" and not wsl_available():
        write_case_output(output_dir, case.name, None)
        status = "SKIP_ALLOWED" if "WSL_UNAVAILABLE" in case.skip_policy else "FAIL"
        reason = "WSL_UNAVAILABLE" if status == "SKIP_ALLOWED" else "UNDECLARED_ENVIRONMENT_SKIP"
        record = {
            "name": case.name,
            "status": status,
            "return_code": None,
            "environment": case.environment,
            "elapsed_seconds": 0,
            "evidence_key": key,
            "cached": False,
            "reason": reason,
            "original_reason": reason,
            "cache_source": "",
            "script": case.script,
            "args": list(case.args),
            "skip_policy": list(case.skip_policy),
            "inputs": inputs,
        }
        return record
    run_token = uuid.uuid4().hex
    command = command_for(case, run_token)
    process, execution = run_owned_command(command, timeout=case.timeout, run_token=run_token)
    status, reason = classify_output(case, process)
    if execution.get("orphan_count", 0) or execution.get("cleanup_status") == "FAIL":
        status, reason = "FAIL", "TIMEOUT_ORPHANED_PROCESS" if execution.get("timed_out") else "ORPHANED_PROCESS"
    write_case_output(output_dir, case.name, process)
    record = {
        "name": case.name,
        "status": status,
        "return_code": process.returncode,
        "environment": case.environment,
        "elapsed_seconds": execution.get("elapsed_seconds", 0),
        "evidence_key": key,
        "cached": False,
        "reason": reason,
        "script": case.script,
        "args": list(case.args),
        "skip_policy": list(case.skip_policy),
        "inputs": inputs,
        "run_token": execution.get("run_token"),
        "owned_pid": execution.get("owned_pid"),
        "cleanup_status": execution.get("cleanup_status"),
        "orphan_count": execution.get("orphan_count", 0),
        "timed_out": execution.get("timed_out", False),
    }
    if status in ("PASS", "SKIP_ALLOWED", "NOT_RUN_ENVIRONMENT"):
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        cache_record = dict(record)
        cache_record["evidence_path"] = str(output_dir)
        cache_record["original_reason"] = reason
        cache_file.write_text(json.dumps(cache_record, sort_keys=True, indent=2), encoding="utf-8")
    return record


def write_evidence(
    mode: str,
    run_id: str,
    output_dir: Path,
    records: list[dict[str, object]],
    manifest: dict[str, object],
    candidate_id: str,
    network_events: list[dict[str, object]] | None = None,
) -> None:
    network_events = network_events or []
    summary = {
        "runner": "scripts/openkill-test-gates.py",
        "runner_version": RUNNER_VERSION,
        "runner_source_hash": RUNNER_SOURCE_HASH,
        "run_id": run_id,
        "mode": mode,
        "head": manifest.get("head"),
        "final_head": manifest.get("final_head"),
        "overall": "PASS" if gate_overall(mode, records) else "FAIL",
        "device_access": 0,
        "host_network_settings_changed_by_work": 0,
        "central_apply": 0,
        "packet_test": 0,
        "candidate_id": candidate_id,
        "candidate_manifest": manifest,
        "candidate_identity": next(
            (record for record in records if record["name"] == "candidate-identity"),
            None,
        ),
        # A cached PASS is reusable evidence, but it is not a fresh execution
        # in this run.  Device-preflight disables the cache, so its readiness
        # statement always comes from an actual staged execution.
        "staged_observer_actually_executed": next((record["status"] == "PASS" and not record.get("cached", False) for record in records if record["name"] == "test-shadow-sidecar-producer"), False),
        "staged_observer_evidence_reused": next((record.get("cached", False) for record in records if record["name"] == "test-shadow-sidecar-producer"), False),
        "repo_runtime_fallback": 0,
        "auto_typed_sidecars": "INTERNAL",
        "host_network_guard": "PASS" if all(event.get("status") == "PASS" for event in network_events) else "FAIL",
        "network_guard_events": network_events,
        "records": records,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"OPENKILL_TEST_GATES={summary['overall']}",
        f"MODE={mode}",
        f"HEAD={manifest.get('head', '')}",
        f"FINAL_HEAD={manifest.get('final_head', '')}",
        f"CANDIDATE_ID={candidate_id}",
        f"DEVICE_ACCESS=0",
        "HOST_NETWORK_SETTINGS_CHANGED_BY_WORK=0",
        f"CENTRAL_APPLY=0",
        f"PACKET_TEST=0",
        f"STAGED_OBSERVER_ACTUALLY_EXECUTED={'PASS' if summary['staged_observer_actually_executed'] else 'FAIL'}",
        f"STAGED_OBSERVER_EVIDENCE_REUSED={'YES' if summary['staged_observer_evidence_reused'] else 'NO'}",
        f"CANDIDATE_IDENTITY={'PASS' if manifest.get('identity_verified') else 'FAIL'}",
        "REPO_RUNTIME_FALLBACK=0",
        "AUTO_TYPED_SIDECARS=INTERNAL",
        f"HOST_NETWORK_GUARD={summary['host_network_guard']}",
    ]
    lines.extend(f"{record['name']}={record['status']} rc={record['return_code']} reason={record['reason']}" for record in records)
    (output_dir / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    environment_lines = [
        f"python={sys.version}",
        f"platform={platform.platform()}",
        f"system={platform.system()}",
        f"wsl_available={wsl_available()}",
        f"git_head={manifest.get('head', '')}",
        f"runner_version={RUNNER_VERSION}",
        f"runner_source_hash={RUNNER_SOURCE_HASH}",
    ]
    if any(record.get("name") == "test-ui-browser" for record in records):
        environment_lines.append(f"browser_runtime={browser_runtime_identity()}")
    (output_dir / "environment.txt").write_text("\n".join(environment_lines) + "\n", encoding="utf-8")
    hash_lines = [f"candidate_id={candidate_id}"]
    for record in records:
        hash_lines.append(f"{record['name']}={record['evidence_key']}")
        hash_lines.append(f"{record['name']}.inputs={json.dumps(record.get('inputs', []), sort_keys=True, separators=(',', ':'))}")
    (output_dir / "hashes.txt").write_text("\n".join(hash_lines) + "\n", encoding="utf-8")
    with (output_dir / "tests.tsv").open("w", encoding="utf-8", newline="") as stream:
        stream.write("name\tstatus\treturn_code\tenvironment\telapsed_seconds\tevidence_key\tcached\treason\toriginal_reason\towned_pid\tcleanup_status\torphan_count\ttimed_out\tscript\targs\tskip_policy\n")
        for record in records:
            stream.write(
                "\t".join(
                    (
                        str(record.get(key, ""))
                        if key not in ("args", "skip_policy")
                        else json.dumps(record.get(key, []), separators=(",", ":"))
                    )
                    for key in ("name", "status", "return_code", "environment", "elapsed_seconds", "evidence_key", "cached", "reason", "original_reason", "owned_pid", "cleanup_status", "orphan_count", "timed_out", "script", "args", "skip_policy")
                )
                + "\n"
            )
    with (output_dir / "skips.tsv").open("w", encoding="utf-8", newline="") as stream:
        stream.write("name\tstatus\treason\n")
        for record in records:
            if record["status"] in ("SKIP_ALLOWED", "NOT_RUN_ENVIRONMENT") or record.get("reason") in ("NFT_CLI_UNAVAILABLE", "RUBY_UNAVAILABLE", "CORE_RELEASE_UNAVAILABLE"):
                stream.write(f"{record['name']}\t{record['status']}\t{record.get('reason', '')}\n")
    (output_dir / "candidate-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "network-guard.json").write_text(json.dumps(network_events, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fast", "full", "device-preflight"))
    parser.add_argument("--no-cache", action="store_true", help="always execute cases")
    args = parser.parse_args(argv)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{os.getpid()}"
    output_dir = EVIDENCE_ROOT / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    network_events: list[dict[str, object]] = []
    try:
        if working_tree_status():
            raise RuntimeError("WORKING_TREE_DIRTY")
        manifest, candidate_id = candidate_manifest(run_id)
        cases = build_cases(args.mode)
        network_before = host_network_snapshot()
        if not network_before.get("available"):
            raise RuntimeError(f"HOST_NETWORK_GUARD_UNAVAILABLE:{network_before.get('reason', 'UNKNOWN')}")
        network_events = [{"point": "suite-start", "snapshot_hash": network_before.get("snapshot_hash"), "status": "PASS"}]
        for index, case in enumerate(cases, start=1):
            print(f"[{index}/{len(cases)}] START {case.name}", flush=True)
            record = run_case(case, output_dir, use_cache=(args.mode == "fast" and not args.no_cache))
            network_after = host_network_snapshot()
            delta = network_guard_delta(network_before, network_after, wsl_case=case.environment == "wsl")
            delta["point"] = case.name
            delta["before_hash"] = network_before.get("snapshot_hash", "")
            delta["after_hash"] = network_after.get("snapshot_hash", "")
            record["network_guard"] = delta
            records.append(record)
            print(
                f"[{index}/{len(cases)}] {record['status']} {case.name} "
                f"elapsed={record['elapsed_seconds']}s reason={record['reason']}",
                flush=True,
            )
            network_events.append(delta)
            if delta.get("status") != "PASS":
                record["status"] = "FAIL"
                record["reason"] = "HOST_NETWORK_DRIFT"
                for remaining in cases[index:]:
                    records.append({
                        "name": remaining.name,
                        "status": "FAIL",
                        "return_code": None,
                        "environment": remaining.environment,
                        "elapsed_seconds": 0,
                        "evidence_key": "",
                        "cached": False,
                        "reason": "ABORTED_HOST_NETWORK_DRIFT",
                        "original_reason": "ABORTED_HOST_NETWORK_DRIFT",
                        "owned_pid": None,
                        "cleanup_status": "NOT_STARTED",
                        "orphan_count": 0,
                        "timed_out": False,
                        "script": remaining.script,
                        "args": list(remaining.args),
                        "skip_policy": list(remaining.skip_policy),
                        "inputs": [],
                    })
                break
            network_before = network_after
        identity_error = candidate_identity_error(manifest, candidate_id)
        records.append({
            "name": "candidate-identity",
            "status": "PASS" if not identity_error else "FAIL",
            "return_code": 0 if not identity_error else 1,
            "environment": "windows",
            "elapsed_seconds": 0,
            "evidence_key": "",
            "cached": False,
            "reason": identity_error,
            "script": None,
            "args": [],
            "skip_policy": [],
            "inputs": [],
        })
        manifest["final_head"] = git_head()
        manifest["identity_verified"] = not identity_error
    except KeyboardInterrupt:
        # Preserve a bounded cancellation record when the user interrupts a
        # suite after its manifest was created.  The active case has already
        # cleaned its owned process tree in run_owned_command().
        if "manifest" in locals() and "candidate_id" in locals():
            records.append({
                "name": "suite-cancelled",
                "status": "FAIL",
                "return_code": 130,
                "environment": "windows",
                "elapsed_seconds": 0,
                "evidence_key": "",
                "cached": False,
                "reason": "USER_CANCELLED",
                "original_reason": "USER_CANCELLED",
                "owned_pid": None,
                "cleanup_status": "PASS",
                "orphan_count": 0,
                "timed_out": False,
                "script": None,
                "args": [],
                "skip_policy": [],
                "inputs": [],
            })
            manifest["final_head"] = git_head()
            manifest["identity_verified"] = False
            write_evidence(args.mode, run_id, output_dir, records, manifest, candidate_id, network_events if "network_events" in locals() else [])
        else:
            (output_dir / "summary.txt").write_text("OPENKILL_TEST_GATES=FAIL\nRUNNER_ERROR=USER_CANCELLED\n", encoding="utf-8")
        print(f"OPENKILL_TEST_GATES=FAIL run_id={run_id} error=USER_CANCELLED")
        return 130
    except (OSError, subprocess.CalledProcessError, ValueError, RuntimeError) as error:
        (output_dir / "summary.txt").write_text(f"OPENKILL_TEST_GATES=FAIL\nRUNNER_ERROR={error}\n", encoding="utf-8")
        if not network_events:
            network_events.append({"point": "suite-error", "status": "FAIL", "reason": str(error)})
        (output_dir / "network-guard.json").write_text(json.dumps(network_events, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OPENKILL_TEST_GATES=FAIL run_id={run_id} error={error}")
        return 1
    write_evidence(args.mode, run_id, output_dir, records, manifest, candidate_id, network_events)
    overall = gate_overall(args.mode, records)
    if args.mode == "device-preflight":
        print(f"DEVICE_PREFLIGHT={'PASS' if overall else 'FAIL'}")
        print(f"DEVICE_CANDIDATE_ID={candidate_id}")
        print(f"DEVICE_RETRY_READY={'YES' if overall else 'NO'}")
        print("DEVICE_ACCESS=0")
    else:
        print(f"{args.mode.upper()}_GATE={'PASS' if overall else 'FAIL'}")
    print(f"EVIDENCE_RUN_ID={run_id}")
    print(f"EVIDENCE_PATH={output_dir.relative_to(ROOT).as_posix()}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
