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
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = Path(__file__).resolve()
RUNNER_VERSION = "1"
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
            skip_policy=("NFT_CLI_UNAVAILABLE",) if path.stem == "test-nft-syntax" else (),
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
        Path("test-openkill-test-gates.py"),
        Path("test-ui-contract.py"),
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

WSL_TESTS: tuple[Case, ...] = (
    Case("test-installer-wsl", "scripts/test-installer.py", environment="wsl", timeout=300, skip_policy=WSL_RUBY_POLICY),
    Case("test-network-model-wsl", "scripts/test-network-model.py", environment="wsl", timeout=300, skip_policy=("WSL_UNAVAILABLE",)),
    Case("test-runtime-wsl", "scripts/test-runtime.py", environment="wsl", timeout=300, skip_policy=WSL_RUBY_POLICY),
    Case("test-snapshot-fw4-wsl", "scripts/test-snapshot-fw4.py", environment="wsl", timeout=300, skip_policy=("WSL_UNAVAILABLE",)),
    Case("test-stage-d-wsl", "scripts/test-stage-d.py", environment="wsl", timeout=300, skip_policy=("WSL_UNAVAILABLE",)),
    Case("test-core-v1_19_30-wsl", "scripts/test-core.py", ("--release", "v1.19.30"), "wsl", 600, skip_policy=("WSL_UNAVAILABLE",)),
    Case("test-core-latest-wsl", "scripts/test-core.py", ("--release", "latest"), "wsl", 600, skip_policy=("WSL_UNAVAILABLE",)),
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
    if case.name == "compileall":
        paths.extend(sorted((ROOT / "scripts").glob("*.py")))
    if case.name == "test-ui-contract":
        paths.extend(sorted((ROOT / "luci-app-openkill/luasrc/view/openkill").glob("*.htm")))
        paths.extend((
            ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/oc.css",
            ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/css/flat.css",
            ROOT / "luci-app-openkill/root/www/luci-static/resources/openkill/js/common.js",
        ))
    # The fixture directory is small and is a safer dependency boundary than
    # a commit id: changing any checked-in evidence invalidates its cache.
    paths.extend(sorted((ROOT / "scripts/fixtures").glob("*")))
    return sorted({path for path in paths if path.is_file()})


def dependency_key(case: Case) -> tuple[str, list[dict[str, str]]]:
    inputs = []
    for path in dependency_files(case):
        inputs.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)})
    versions = {
        "python": sys.version,
        "platform": platform.platform(),
        "environment": case.environment,
        "runner": RUNNER_VERSION,
        "runner_source_hash": RUNNER_SOURCE_HASH,
    }
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


def command_for(case: Case) -> list[str]:
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
    return ["wsl.exe", "-u", "root", "--", "sh", "-lc", command]


def read_version(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    return (result.stdout or result.stderr).strip().splitlines()[0][:200] if (result.stdout or result.stderr) else "ok"


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
        "test-production-shadow",
        "test-ui-contract",
    )
    native_by_name = {case.name: case for case in NATIVE_TESTS}
    if mode == "fast":
        return list(policy) + [native_by_name[name] for name in focused]
    if mode == "device-preflight":
        selected = list(policy)
        selected.extend(native_by_name.values())
        return selected
    if mode == "full":
        return list(policy) + list(NATIVE_TESTS) + list(WSL_TESTS)
    raise ValueError(mode)


def classify_output(case: Case, process: subprocess.CompletedProcess[str]) -> tuple[str, str]:
    output = (process.stdout or "") + "\n" + (process.stderr or "")
    if process.returncode == 0:
        # These are documented environment observations, not silent skips.
        if "nft CLI unavailable" in output or "nft command is unavailable" in output:
            reason = "NFT_CLI_UNAVAILABLE"
            return ("NOT_RUN_ENVIRONMENT", reason) if reason in case.skip_policy else ("FAIL", "UNDECLARED_ENVIRONMENT_SKIP")
        if "Ruby is not installed" in output or "Ruby required" in output:
            reason = "RUBY_UNAVAILABLE"
            return ("SKIP_ALLOWED", reason) if reason in case.skip_policy else ("FAIL", "UNDECLARED_ENVIRONMENT_SKIP")
        return "PASS", ""
    return "FAIL", f"RETURN_CODE_{process.returncode}"


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
                    "reason": "CACHE_HIT",
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
            "script": case.script,
            "args": list(case.args),
            "skip_policy": list(case.skip_policy),
            "inputs": inputs,
        }
        return record
    command = command_for(case)
    start = time.monotonic()
    process: subprocess.CompletedProcess[str] | None = None
    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=case.timeout,
        )
        status, reason = classify_output(case, process)
    except subprocess.TimeoutExpired as error:
        process = subprocess.CompletedProcess(command, 124, error.stdout or "", error.stderr or "timeout")
        status, reason = "FAIL", "TIMEOUT"
    except OSError as error:
        process = subprocess.CompletedProcess(command, 127, "", str(error))
        status, reason = "FAIL", "EXECUTION_ERROR"
    elapsed = round(time.monotonic() - start, 3)
    write_case_output(output_dir, case.name, process)
    record = {
        "name": case.name,
        "status": status,
        "return_code": process.returncode,
        "environment": case.environment,
        "elapsed_seconds": elapsed,
        "evidence_key": key,
        "cached": False,
        "reason": reason,
        "script": case.script,
        "args": list(case.args),
        "skip_policy": list(case.skip_policy),
        "inputs": inputs,
    }
    if status in ("PASS", "SKIP_ALLOWED", "NOT_RUN_ENVIRONMENT"):
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(record, sort_keys=True, indent=2), encoding="utf-8")
    return record


def write_evidence(mode: str, run_id: str, output_dir: Path, records: list[dict[str, object]], manifest: dict[str, object], candidate_id: str) -> None:
    summary = {
        "runner": "scripts/openkill-test-gates.py",
        "runner_version": RUNNER_VERSION,
        "runner_source_hash": RUNNER_SOURCE_HASH,
        "run_id": run_id,
        "mode": mode,
        "head": manifest.get("head"),
        "final_head": manifest.get("final_head"),
        "overall": "PASS" if all(record["status"] in ("PASS", "SKIP_ALLOWED", "NOT_RUN_ENVIRONMENT") for record in records) else "FAIL",
        "device_access": 0,
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
        f"CENTRAL_APPLY=0",
        f"PACKET_TEST=0",
        f"STAGED_OBSERVER_ACTUALLY_EXECUTED={'PASS' if summary['staged_observer_actually_executed'] else 'FAIL'}",
        f"STAGED_OBSERVER_EVIDENCE_REUSED={'YES' if summary['staged_observer_evidence_reused'] else 'NO'}",
        f"CANDIDATE_IDENTITY={'PASS' if manifest.get('identity_verified') else 'FAIL'}",
        "REPO_RUNTIME_FALLBACK=0",
        "AUTO_TYPED_SIDECARS=INTERNAL",
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
    (output_dir / "environment.txt").write_text("\n".join(environment_lines) + "\n", encoding="utf-8")
    hash_lines = [f"candidate_id={candidate_id}"]
    for record in records:
        hash_lines.append(f"{record['name']}={record['evidence_key']}")
        hash_lines.append(f"{record['name']}.inputs={json.dumps(record.get('inputs', []), sort_keys=True, separators=(',', ':'))}")
    (output_dir / "hashes.txt").write_text("\n".join(hash_lines) + "\n", encoding="utf-8")
    with (output_dir / "tests.tsv").open("w", encoding="utf-8", newline="") as stream:
        stream.write("name\tstatus\treturn_code\tenvironment\telapsed_seconds\tevidence_key\tcached\treason\tscript\targs\tskip_policy\n")
        for record in records:
            stream.write(
                "\t".join(
                    (
                        str(record.get(key, ""))
                        if key not in ("args", "skip_policy")
                        else json.dumps(record.get(key, []), separators=(",", ":"))
                    )
                    for key in ("name", "status", "return_code", "environment", "elapsed_seconds", "evidence_key", "cached", "reason", "script", "args", "skip_policy")
                )
                + "\n"
            )
    with (output_dir / "skips.tsv").open("w", encoding="utf-8", newline="") as stream:
        stream.write("name\tstatus\treason\n")
        for record in records:
            if record["status"] in ("SKIP_ALLOWED", "NOT_RUN_ENVIRONMENT") or record.get("reason") in ("NFT_CLI_UNAVAILABLE", "RUBY_UNAVAILABLE"):
                stream.write(f"{record['name']}\t{record['status']}\t{record.get('reason', '')}\n")
    (output_dir / "candidate-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fast", "full", "device-preflight"))
    parser.add_argument("--no-cache", action="store_true", help="always execute cases")
    args = parser.parse_args(argv)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{os.getpid()}"
    output_dir = EVIDENCE_ROOT / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        if working_tree_status():
            raise RuntimeError("WORKING_TREE_DIRTY")
        manifest, candidate_id = candidate_manifest(run_id)
        cases = build_cases(args.mode)
        records = []
        for index, case in enumerate(cases, start=1):
            print(f"[{index}/{len(cases)}] START {case.name}", flush=True)
            record = run_case(case, output_dir, use_cache=(args.mode == "fast" and not args.no_cache))
            records.append(record)
            print(
                f"[{index}/{len(cases)}] {record['status']} {case.name} "
                f"elapsed={record['elapsed_seconds']}s reason={record['reason']}",
                flush=True,
            )
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
    except (OSError, subprocess.CalledProcessError, ValueError, RuntimeError) as error:
        (output_dir / "summary.txt").write_text(f"OPENKILL_TEST_GATES=FAIL\nRUNNER_ERROR={error}\n", encoding="utf-8")
        print(f"OPENKILL_TEST_GATES=FAIL run_id={run_id} error={error}")
        return 1
    write_evidence(args.mode, run_id, output_dir, records, manifest, candidate_id)
    overall = all(record["status"] in ("PASS", "SKIP_ALLOWED", "NOT_RUN_ENVIRONMENT") for record in records)
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
