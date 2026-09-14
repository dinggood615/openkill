#!/usr/bin/env python3
"""Local 3E.2D0A tests for SHADOW_CONTINUITY_TOKEN_V1.

The tests use committed-state fixtures and a recorded nft transcript.  They
never contact a router and never load or mutate the host nft ruleset.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHARE = ROOT / "luci-app-openkill/root/usr/share/openkill"
HELPER = SHARE / "openkill_nft_shadow.sh"
RENDERER = SHARE / "openkill_nft_renderer.sh"
TEMPLATE_DIR = SHARE / "shadow"
AUTO_SOURCE = ROOT / "scripts/fixtures/openkill-shadow-auto-state-v1.txt"
CAPTURE = ROOT / "scripts/fixtures/openkill-legacy-runtime-capture-v1.txt"
MODEL = ROOT / "scripts/fixtures/openkill-shadow-continuity-v1.json"


def _wsl(path: Path) -> str:
    resolved = path.resolve()
    if not resolved.drive:
        return str(resolved)
    drive = resolved.drive.rstrip(":").lower()
    tail = resolved.as_posix().split(":", 1)[-1]
    return f"/mnt/{drive}/{tail.lstrip('/')}"


def _quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").replace("\r", "\n").encode())


def _status(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


class ContinuityHarness:
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
        "OPENKILL_NFT_SHADOW_NODE4_FILE",
        "OPENKILL_NFT_SHADOW_NODE6_FILE",
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
        "OPENKILL_NFT_SHADOW_TEST_HOOK",
        "OPENKILL_NFT_SHADOW_TEST_AFTER_COPY_FILE",
        "OPENKILL_NFT_SHADOW_TEST_AFTER_COPY_VALUE",
        "OPENKILL_NETWORK_DESIRED",
        "OPENKILL_NETWORK_APPLIED_FILE",
        "OPENKILL_NETWORK_SNAPSHOT",
        "OPENKILL_TUN_OWNER",
        "OPENKILL_RUN_MODE",
        "OPENKILL_PROXY_PORT",
        "OPENKILL_TPROXY_PORT",
        "OPENKILL_DNS_PORT",
        "OPENKILL_ROUTER_SELF_PROXY",
        "OPENKILL_FWMARK",
        "OPENKILL_FWMASK",
        "OPENKILL_ROUTE_TABLE",
        "OPENKILL_RULE_PREF",
        "OPENKILL_IPV6_READY",
    )

    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="openkill-shadow-continuity-")
        self.root = Path(self.temp.name)
        self.state_text = AUTO_SOURCE.read_text(encoding="utf-8").replace("GENERATION=fixture-g1\n", "")

    def close(self) -> None:
        self.temp.cleanup()

    def base_state(self) -> tuple[Path, Path]:
        desired = self.root / "desired"
        applied = self.root / "applied"
        _write(desired, self.state_text)
        _write(applied, self.state_text)
        return desired, applied

    def env(self, desired: Path, applied: Path, telemetry: Path, **extra: str | Path) -> dict[str, str | Path]:
        values: dict[str, str | Path] = {
            "OPENKILL_NFT_SHADOW": "1",
            "OPENKILL_NFT_SHADOW_FORCE": "1",
            "OPENKILL_NETWORK_DESIRED": _wsl(desired),
            "OPENKILL_NETWORK_APPLIED_FILE": _wsl(applied),
            "OPENKILL_NETWORK_SNAPSHOT": _wsl(self.root / "missing-snapshot"),
            "OPENKILL_NFT_SHADOW_NODE4_FILE": _wsl(self.root / "missing-node4"),
            "OPENKILL_NFT_SHADOW_NODE6_FILE": _wsl(self.root / "missing-node6"),
            "OPENKILL_NFT_SHADOW_CAPTURE_FIXTURE": _wsl(CAPTURE),
            "OPENKILL_NFT_SHADOW_RENDERER": _wsl(RENDERER),
            "OPENKILL_NFT_SHADOW_TEMPLATE_DIR": _wsl(TEMPLATE_DIR),
            "OPENKILL_NFT_SHADOW_TELEMETRY_DIR": _wsl(telemetry),
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
        }
        values.update(extra)
        return values

    def run(self, body: str, env: dict[str, str | Path] | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        runner = self.root / f"runner-{len(list(self.root.glob('runner-*.sh')))}.sh"
        lines = ["#!/bin/sh", "set +e"]
        for key in self._UNSET:
            lines.append(f"unset {key}")
        for key, value in (env or {}).items():
            lines.append(f"export {key}={_quote(value)}")
        lines.extend([f". {_quote(_wsl(HELPER))}", body])
        _write(runner, "\n".join(lines) + "\n")
        if shutil.which("wsl.exe"):
            command = ["wsl.exe", "-u", "root", "--", "sh", _wsl(runner)]
        else:
            command = ["sh", str(runner)]
        return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)

    @staticmethod
    def rc(process: subprocess.CompletedProcess[str]) -> int:
        for line in process.stdout.splitlines():
            if line.startswith("RC="):
                return int(line.split("=", 1)[1])
        raise AssertionError(f"missing RC: {process.stdout!r} {process.stderr!r}")

    def token_body(
        self,
        output: Path,
        work: Path,
        desired: Path,
        applied: Path,
        node4: Path | None = None,
        node6: Path | None = None,
    ) -> str:
        node4 = node4 or (self.root / "missing-node4")
        node6 = node6 or (self.root / "missing-node6")
        return (
            f"openkill_shadow_auto_continuity_token {_quote(_wsl(output))} {_quote(_wsl(work))} "
            f"{_quote(_wsl(desired))} {_quote(_wsl(applied))} "
            f"{_quote(_wsl(self.root / 'missing-snapshot'))} "
            f"{_quote(_wsl(node4))} {_quote(_wsl(node6))}; "
            "printf 'RC=%s\\n' \"$?\""
        )

    def compare(self, desired: Path, applied: Path, telemetry: Path, **extra: str | Path):
        env = self.env(desired, applied, telemetry, **extra)
        body = "openkill_shadow_compare_nft; printf 'RC=%s\\n' \"$?\""
        process = self.run(body, env)
        return process, _status(telemetry / "status")


class ContinuityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = ContinuityHarness()

    def tearDown(self) -> None:
        self.h.close()

    def test_contract_fixture_and_generation_file_are_not_production_source(self) -> None:
        model = json.loads(MODEL.read_text(encoding="utf-8"))
        self.assertEqual(model["token"], "SHADOW_CONTINUITY_TOKEN_V1")
        self.assertFalse(model["production_generation_file_required"])
        desired, applied = self.h.base_state()
        work = self.h.root / "token-work"
        token = self.h.root / "token"
        generation = self.h.root / "generation"
        _write(generation, "random-a\n")
        env = self.h.env(desired, applied, self.h.root / "unused", OPENKILL_NFT_SHADOW_GENERATION_FILE=_wsl(generation))
        process = self.h.run(self.h.token_body(token, work, desired, applied), env)
        self.assertEqual(self.h.rc(process), 0, process.stderr)
        first = token.read_text(encoding="utf-8").strip()
        _write(generation, "random-b\n")
        process = self.h.run(self.h.token_body(token, work, desired, applied), env)
        self.assertEqual(self.h.rc(process), 0, process.stderr)
        self.assertEqual(first, token.read_text(encoding="utf-8").strip())

    def test_noop_token_is_stable_for_1000_computations(self) -> None:
        desired, applied = self.h.base_state()
        output = self.h.root / "token"
        work = self.h.root / "loop-work"
        token_command = (
            f"openkill_shadow_auto_continuity_token {_quote(_wsl(output))} {_quote(_wsl(work))} "
            f"{_quote(_wsl(desired))} {_quote(_wsl(applied))} "
            f"{_quote(_wsl(self.h.root / 'missing-snapshot'))} "
            f"{_quote(_wsl(self.h.root / 'missing-node4'))} {_quote(_wsl(self.h.root / 'missing-node6'))}"
        )
        body = (
            "first=; i=0; "
            f"while [ $i -lt 1000 ]; do {token_command} >/dev/null || exit 90; "
            "current=$(sed -n '1p' " + _quote(_wsl(output)) + "); "
            "[ -n \"$first\" ] || first=$current; [ \"$first\" = \"$current\" ] || exit 91; "
            "i=$((i + 1)); done; echo COUNT=$i HASH=$first"
        )
        process = self.h.run(body, self.h.env(desired, applied, self.h.root / "unused"), timeout=180)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("COUNT=1000", process.stdout)

    def test_source_order_and_set_order_do_not_change_token(self) -> None:
        desired, applied = self.h.base_state()
        reordered = self.h.root / "reordered"
        lines = self.h.state_text.splitlines()
        _write(reordered, "\n".join(reversed(lines)) + "\n")
        first = self.h.root / "first"
        second = self.h.root / "second"
        env = self.h.env(desired, applied, self.h.root / "unused")
        for out, source in ((first, desired), (second, reordered)):
            process = self.h.run(self.h.token_body(out, self.h.root / f"work-{out.name}", source, applied), env)
            self.assertEqual(self.h.rc(process), 0, process.stderr)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_shadow_matches_without_generation_file_and_publishes_token(self) -> None:
        desired, applied = self.h.base_state()
        process, status = self.h.compare(desired, applied, self.h.root / "telemetry")
        self.assertEqual(self.h.rc(process), 0, process.stderr)
        self.assertEqual(status.get("status"), "MATCH")
        self.assertRegex(status.get("continuity_token", ""), r"^[0-9a-f]{12}$")
        self.assertNotIn("generation", status.get("reason", ""))

    def test_desired_applied_split_is_stale_before_renderer(self) -> None:
        desired, applied = self.h.base_state()
        _write(desired, self.h.state_text.replace("MARK=0x162", "MARK=0x163", 1))
        marker = self.h.root / "renderer-called"
        renderer = self.h.root / "renderer.sh"
        _write(renderer, f"#!/bin/sh\necho called > {_quote(_wsl(marker))}\nexit 0\n")
        process, status = self.h.compare(desired, applied, self.h.root / "telemetry", OPENKILL_NFT_SHADOW_RENDERER=_wsl(renderer))
        self.assertEqual(self.h.rc(process), 6)
        self.assertEqual(status.get("status"), "STALE")
        self.assertFalse(marker.exists())

    def test_pre_snapshot_race_is_stale_and_renderer_is_not_invoked(self) -> None:
        desired, applied = self.h.base_state()
        marker = self.h.root / "renderer-called"
        renderer = self.h.root / "renderer.sh"
        _write(renderer, f"#!/bin/sh\necho called > {_quote(_wsl(marker))}\nexit 0\n")
        process, status = self.h.compare(
            desired,
            applied,
            self.h.root / "telemetry",
            OPENKILL_NFT_SHADOW_RENDERER=_wsl(renderer),
            OPENKILL_NFT_SHADOW_TEST_HOOK="1",
            OPENKILL_NFT_SHADOW_TEST_AFTER_COPY_FILE=_wsl(applied),
            OPENKILL_NFT_SHADOW_TEST_AFTER_COPY_VALUE="MARK=0x163",
        )
        self.assertEqual(self.h.rc(process), 6)
        self.assertEqual(status.get("status"), "STALE")
        self.assertFalse(marker.exists())

    def test_final_race_wins_over_provisional_match(self) -> None:
        desired, applied = self.h.base_state()
        renderer = self.h.root / "race-renderer.sh"
        temp = self.h.root / "live-applied.tmp"
        _write(
            renderer,
            "#!/bin/sh\n"
            f"sed 's/^MARK=.*/MARK=0x163/' {_quote(_wsl(applied))} > {_quote(_wsl(temp))} && mv {_quote(_wsl(temp))} {_quote(_wsl(applied))}\n"
            f"exec sh {_quote(_wsl(RENDERER))} \"$1\" \"$2\"\n",
        )
        process, status = self.h.compare(desired, applied, self.h.root / "telemetry", OPENKILL_NFT_SHADOW_RENDERER=_wsl(renderer))
        self.assertEqual(self.h.rc(process), 6)
        self.assertEqual(status.get("status"), "STALE")
        self.assertEqual(status.get("reason"), "continuity-token-changed")

    def test_state_change_invalidates_token_and_owner_dns_node_changes_are_covered(self) -> None:
        desired, applied = self.h.base_state()
        node4 = self.h.root / "node4"
        node6 = self.h.root / "node6"
        _write(node4, "198.51.100.10\n")
        _write(node6, "2001:db8::10\n")
        env = self.h.env(desired, applied, self.h.root / "unused", OPENKILL_NFT_SHADOW_NODE4_FILE=_wsl(node4), OPENKILL_NFT_SHADOW_NODE6_FILE=_wsl(node6))
        first = self.h.root / "first"
        second = self.h.root / "second"
        body = self.h.token_body(first, self.h.root / "w1", desired, applied, node4, node6)
        process = self.h.run(body, env)
        self.assertEqual(self.h.rc(process), 0)
        _write(applied, self.h.state_text.replace("DNS_PORT=7874", "DNS_PORT=7875", 1))
        process = self.h.run(self.h.token_body(second, self.h.root / "w2", desired, applied, node4, node6), env)
        self.assertEqual(self.h.rc(process), 0)
        self.assertNotEqual(first.read_bytes(), second.read_bytes())

        _write(node4, "198.51.100.11\n")
        third = self.h.root / "third"
        process = self.h.run(self.h.token_body(third, self.h.root / "w3", desired, applied, node4, node6), env)
        self.assertEqual(self.h.rc(process), 0)
        self.assertNotEqual(second.read_bytes(), third.read_bytes())

        owner_token = self.h.root / "owner"
        owner_env = self.h.env(desired, applied, self.h.root / "unused", OPENKILL_TUN_OWNER="MIHOMO")
        process = self.h.run(self.h.token_body(owner_token, self.h.root / "w4", desired, applied, node4, node6), owner_env)
        self.assertEqual(self.h.rc(process), 0)
        self.assertNotEqual(third.read_bytes(), owner_token.read_bytes())

    def test_unknown_state_version_fails_closed(self) -> None:
        desired, applied = self.h.base_state()
        _write(applied, "SNAPSHOT_VERSION=2\n" + self.h.state_text.split("\n", 1)[1])
        process, status = self.h.compare(desired, applied, self.h.root / "telemetry")
        self.assertEqual(self.h.rc(process), 11)
        self.assertEqual(status.get("status"), "INPUT_SOURCE_GAP")

    def test_default_off_returns_before_token_snapshot_or_telemetry(self) -> None:
        desired, applied = self.h.base_state()
        marker = self.h.root / "renderer-called"
        renderer = self.h.root / "renderer.sh"
        _write(renderer, f"#!/bin/sh\necho called > {_quote(_wsl(marker))}\nexit 0\n")
        process, status = self.h.compare(desired, applied, self.h.root / "telemetry", OPENKILL_NFT_SHADOW="0", OPENKILL_NFT_SHADOW_RENDERER=_wsl(renderer))
        self.assertEqual(self.h.rc(process), 0)
        self.assertEqual(status, {})
        self.assertFalse(marker.exists())

    def test_unknown_generation_file_is_not_read_by_auto_path(self) -> None:
        desired, applied = self.h.base_state()
        bad_generation = self.h.root / "generation"
        _write(bad_generation, "\n")
        process, status = self.h.compare(
            desired,
            applied,
            self.h.root / "telemetry",
            OPENKILL_NFT_SHADOW_GENERATION_FILE=_wsl(bad_generation),
        )
        self.assertEqual(self.h.rc(process), 0, process.stderr)
        self.assertEqual(status.get("status"), "MATCH")


if __name__ == "__main__":
    unittest.main(verbosity=2)
