#!/usr/bin/env python3
"""Regression tests for the self-contained automatic typed shadow path.

The harness uses only checked-in sanitized fixtures and a temporary shell
environment.  It never contacts a device and never supplies typed sidecars to
the automatic coordinator.
"""

from __future__ import annotations

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


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    if not resolved.drive:
        return resolved.as_posix()
    drive = resolved.drive.rstrip(":").lower()
    tail = resolved.as_posix().split(":", 1)[-1]
    return f"/mnt/{drive}/{tail.lstrip('/')}"


def quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def write_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").replace("\r", "\n").encode())


def status_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


class AutoHarness:
    _UNSET = (
        "OPENKILL_NFT_SHADOW", "OPENKILL_NFT_SHADOW_STATE_FILE",
        "OPENKILL_NFT_SHADOW_INPUT_FILE", "OPENKILL_NFT_SHADOW_OLD_INTENT_FILE",
        "OPENKILL_NFT_SHADOW_OLD_INTENT_HASH", "OPENKILL_NFT_SHADOW_GENERATION",
        "OPENKILL_NFT_SHADOW_GENERATION_FILE", "OPENKILL_NFT_SHADOW_SOURCE_FILE",
        "OPENKILL_NFT_SHADOW_AUTO_STATE_FILE", "OPENKILL_NFT_SHADOW_STATE_SOURCE",
        "OPENKILL_NFT_SHADOW_CAPTURE_FIXTURE", "OPENKILL_NFT_SHADOW_NFT_BIN",
        "OPENKILL_NFT_SHADOW_CAPTURE_NFT_BIN", "OPENKILL_NFT_SHADOW_CAPTURE_CHAINS",
        "OPENKILL_NFT_SHADOW_CAPTURE_SETS", "OPENKILL_NFT_SHADOW_CAPTURE_TRACE",
        "OPENKILL_NFT_SHADOW_RENDERER", "OPENKILL_NFT_SHADOW_TEMPLATE_DIR",
        "OPENKILL_NFT_SHADOW_SEMANTIC_MANIFEST", "OPENKILL_NFT_SHADOW_TYPED_ACTUAL_FILE",
        "OPENKILL_NFT_SHADOW_TYPED_DESIRED_FILE", "OPENKILL_NFT_SHADOW_AUTO_TYPED",
        "OPENKILL_NFT_SHADOW_TYPED_OVERRIDE",
        "OPENKILL_NFT_SHADOW_TELEMETRY_DIR", "OPENKILL_NFT_SHADOW_FORCE",
        "OPENKILL_NFT_SHADOW_TIMEOUT", "OPENKILL_NETWORK_DESIRED",
        "OPENKILL_NETWORK_APPLIED_FILE", "OPENKILL_NETWORK_SNAPSHOT",
        "OPENKILL_NFT_SHADOW_NODE4_FILE", "OPENKILL_NFT_SHADOW_NODE6_FILE",
        "OPENKILL_DNS_ENDPOINT", "FAKE_UCI_COUNT",
    )

    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="openkill-shadow-sidecar-")
        self.root = Path(self.temp.name)
        self.counter = 0

    def close(self) -> None:
        self.temp.cleanup()

    def run(self, env: dict[str, str | Path | None], timeout: int = 60, body: str | None = None) -> tuple[subprocess.CompletedProcess[str], Path]:
        self.counter += 1
        case = self.root / f"case-{self.counter}"
        case.mkdir(parents=True, exist_ok=True)
        telemetry = case / "telemetry"
        runner = case / "runner.sh"
        lines = ["#!/bin/sh", "set +e"]
        lines.extend(f"unset {key}" for key in self._UNSET)
        for key, value in env.items():
            if value is None:
                lines.append(f"unset {key}")
            else:
                lines.append(f"export {key}={quote(value)}")
        lines.append(f". {quote(wsl_path(HELPER))}")
        lines.extend((body or "openkill_shadow_compare_nft; rc=$?; printf 'RC=%s\\n' \"$rc\"").splitlines())
        write_lf(runner, "\n".join(lines) + "\n")
        command = (
            ["wsl.exe", "-u", "root", "--", "sh", wsl_path(runner)]
            if shutil.which("wsl.exe")
            else ["sh", str(runner)]
        )
        return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout), telemetry

    def env(self, capture: Path = CAPTURE, **extra: str | Path | None) -> dict[str, str | Path | None]:
        # ``run`` increments the counter before creating its case directory;
        # predict that same path here so the coordinator and the assertions
        # observe one private telemetry directory.
        case = self.root / f"case-{self.counter + 1}"
        telemetry = case / "telemetry"
        values: dict[str, str | Path | None] = {
            "OPENKILL_NFT_SHADOW": "1",
            "OPENKILL_NFT_SHADOW_FORCE": "1",
            "OPENKILL_NFT_SHADOW_SOURCE_FILE": wsl_path(AUTO_SOURCE),
            "OPENKILL_NFT_SHADOW_CAPTURE_FIXTURE": wsl_path(capture),
            "OPENKILL_NFT_SHADOW_RENDERER": wsl_path(RENDERER),
            "OPENKILL_NFT_SHADOW_TEMPLATE_DIR": wsl_path(TEMPLATE_DIR),
            "OPENKILL_NFT_SHADOW_TELEMETRY_DIR": wsl_path(telemetry),
        }
        values.update(extra)
        return values

    @staticmethod
    def rc(process: subprocess.CompletedProcess[str]) -> int:
        for line in process.stdout.splitlines():
            if line.startswith("RC="):
                return int(line.split("=", 1)[1])
        raise AssertionError(f"missing RC: {process.stdout!r} {process.stderr!r}")


class SidecarProducerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = AutoHarness()

    def tearDown(self) -> None:
        self.harness.close()

    def run_auto(self, capture: Path = CAPTURE, **extra: str | Path | None):
        process, telemetry = self.harness.run(self.harness.env(capture, **extra))
        return process, self.harness.rc(process), status_file(telemetry / "status")

    def test_automatic_path_generates_typed_sidecars_and_matches(self) -> None:
        process, rc, status = self.run_auto()
        self.assertEqual(rc, 0, process.stderr)
        self.assertEqual(status.get("status"), "MATCH")
        self.assertEqual(status.get("dns_parity"), "MATCH")
        self.assertEqual(status.get("model_gap_count"), "0")
        self.assertGreater(int(status.get("out_of_scope_observed_count", "0")), 0)
        self.assertEqual(status.get("actual_owned_hash"), status.get("desired_owned_hash"))
        self.assertEqual(status.get("dns_actual_hash"), status.get("dns_desired_hash"))
        self.assertTrue(status.get("actual_owned_hash"))
        self.assertEqual(status.get("comparison_model_version"), "1")

    def test_dns_difference_is_mismatch_without_sidecar_override(self) -> None:
        capture = self.harness.root / "dns-wrong.capture"
        text = CAPTURE.read_text(encoding="utf-8")
        text = text.replace("tcp dport 53", "tcp dport 7874").replace("udp dport 53", "udp dport 7874")
        write_lf(capture, text)
        process, rc, status = self.run_auto(capture)
        self.assertEqual(rc, 1, process.stderr)
        self.assertEqual(status.get("status"), "MISMATCH")
        self.assertEqual(status.get("dns_parity"), "MISMATCH")

    def test_dns_scope_mutations_are_mismatches(self) -> None:
        source_text = CAPTURE.read_text(encoding="utf-8")
        cases = {
            "ipv4-lan-only": (
                "meta nfproto ipv4 tcp dport 53 jump openkill_dns_hijack",
                "meta nfproto ipv4 udp dport 53 jump openkill_dns_hijack",
            ),
            "ipv6-router-only": (
                "meta nfproto ipv6 tcp dport 53 jump openkill_dns_redirect_v6",
                "meta nfproto ipv6 udp dport 53 jump openkill_dns_redirect_v6",
            ),
        }
        for name, lines in cases.items():
            with self.subTest(name=name):
                capture = self.harness.root / f"{name}.capture"
                targets = {line.strip() for line in lines}
                mutated = "\n".join(
                    line for line in source_text.splitlines() if line.strip() not in targets
                ) + "\n"
                write_lf(capture, mutated)
                process, rc, status = self.run_auto(capture)
                self.assertEqual(rc, 1, process.stderr)
                self.assertEqual(status.get("status"), "MISMATCH")
                self.assertEqual(status.get("dns_parity"), "MISMATCH")

    def test_missing_runtime_dns_source_is_model_gap(self) -> None:
        source = self.harness.root / "missing-upstream.txt"
        text = "\n".join(
            line for line in AUTO_SOURCE.read_text(encoding="utf-8").splitlines()
            if not line.startswith("DNSMASQ_UPSTREAM_TARGET=")
        ) + "\n"
        write_lf(source, text)
        process, rc, status = self.run_auto(OPENKILL_NFT_SHADOW_SOURCE_FILE=wsl_path(source))
        self.assertEqual(rc, 12, process.stderr)
        self.assertEqual(status.get("status"), "MODEL_GAP")

    def test_automatic_producer_uses_frozen_snapshot_without_live_reread(self) -> None:
        desired = self.harness.root / "desired-no-reread"
        applied = self.harness.root / "applied-no-reread"
        write_lf(desired, AUTO_SOURCE.read_text(encoding="utf-8"))
        write_lf(applied, AUTO_SOURCE.read_text(encoding="utf-8"))

        fake_bin = self.harness.root / "fake-bin"
        fake_bin.mkdir()
        count_file = self.harness.root / "fake-uci-count"
        write_lf(
            fake_bin / "uci",
            """#!/bin/sh
count=${FAKE_UCI_COUNT:?}
n=0
if [ -r "$count" ]; then
    n=$(cat "$count")
fi
n=$((n + 1))
printf '%s\\n' "$n" > "$count"
[ "$n" -le 2 ] || exit 99
case "$*" in
    *port) printf '53\\n' ;;
    *) printf '127.0.0.1#7874\\n' ;;
esac
""",
        )
        (fake_bin / "uci").chmod(0o700)
        values = self.harness.env(
            OPENKILL_NFT_SHADOW_SOURCE_FILE=None,
            OPENKILL_NETWORK_DESIRED=wsl_path(desired),
            OPENKILL_NETWORK_APPLIED_FILE=wsl_path(applied),
            OPENKILL_NETWORK_SNAPSHOT=wsl_path(self.harness.root / "missing-snapshot"),
            OPENKILL_NFT_SHADOW_NODE4_FILE=wsl_path(self.harness.root / "missing-node4"),
            OPENKILL_NFT_SHADOW_NODE6_FILE=wsl_path(self.harness.root / "missing-node6"),
            OPENKILL_DNS_ENDPOINT="127.0.0.1:7874",
            FAKE_UCI_COUNT=wsl_path(count_file),
            PATH=(
                f"{wsl_path(fake_bin)}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            ),
        )
        process, telemetry = self.harness.run(values)
        rc = self.harness.rc(process)
        self.assertEqual(rc, 0, process.stderr)
        self.assertEqual(status_file(telemetry / "status").get("status"), "MATCH", process.stderr)
        self.assertEqual(count_file.read_text(encoding="utf-8").strip(), "2", process.stderr)

    def test_actual_mark_difference_is_mismatch(self) -> None:
        capture = self.harness.root / "mark-wrong.capture"
        write_lf(capture, CAPTURE.read_text(encoding="utf-8").replace("meta mark set 0x162", "meta mark set 0x163"))
        process, rc, status = self.run_auto(capture)
        self.assertEqual(rc, 1, process.stderr)
        self.assertEqual(status.get("status"), "MISMATCH")

    def test_actual_mutation_cannot_change_desired_projection(self) -> None:
        _, positive_rc, positive = self.run_auto()
        self.assertEqual(positive_rc, 0)
        capture = self.harness.root / "independent-actual.capture"
        mutated = CAPTURE.read_text(encoding="utf-8")
        mutated = mutated.replace("192.0.2.0/24", "192.0.2.1/32")
        mutated = mutated.replace("meta mark set 0x162", "meta mark set 0x163")
        write_lf(capture, mutated)
        process, rc, status = self.run_auto(capture)
        self.assertEqual(rc, 1, process.stderr)
        self.assertEqual(status.get("status"), "MISMATCH")
        self.assertEqual(status.get("desired_owned_hash"), positive.get("desired_owned_hash"))

    def test_desired_projection_consumes_renderer_output(self) -> None:
        renderer = self.harness.root / "renderer-wrong-dns.sh"
        write_lf(
            renderer,
            "\n".join(
                (
                    "#!/bin/sh",
                    "set -e",
                    "tmp=$(mktemp)",
                    "trap 'rm -f \"$tmp\"' EXIT",
                    f"{quote(wsl_path(RENDERER))} \"$1\" \"$tmp\"",
                    "sed 's/dport 53/dport 54/g' \"$tmp\" > \"$2\"",
                )
            )
            + "\n",
        )
        renderer.chmod(0o700)
        process, rc, status = self.run_auto(OPENKILL_NFT_SHADOW_RENDERER=wsl_path(renderer))
        self.assertEqual(rc, 1, process.stderr)
        self.assertEqual(status.get("status"), "MISMATCH")
        self.assertEqual(status.get("dns_parity"), "MISMATCH")

    def test_missing_desired_dns_source_is_model_gap(self) -> None:
        staged = self.harness.root / "missing-desired-source"
        staged.mkdir()
        staged_manifest = staged / "semantic_model_v1.tsv"
        manifest = (TEMPLATE_DIR / "semantic_model_v1.tsv").read_text(encoding="utf-8")
        manifest = "\n".join(
            line for line in manifest.splitlines() if "DNS_EXPECTED\tDNSMASQ_UPSTREAM_TARGET" not in line
        ) + "\n"
        write_lf(staged_manifest, manifest)
        process, rc, status = self.run_auto(OPENKILL_NFT_SHADOW_SEMANTIC_MANIFEST=wsl_path(staged_manifest))
        self.assertEqual(rc, 12, process.stderr)
        self.assertEqual(status.get("status"), "MODEL_GAP")

    def test_external_sidecars_are_rejected_by_automatic_mode(self) -> None:
        for override in (None, "1"):
            with self.subTest(override=override):
                process, rc, status = self.run_auto(
                    OPENKILL_NFT_SHADOW_TYPED_ACTUAL_FILE=wsl_path(CAPTURE),
                    OPENKILL_NFT_SHADOW_TYPED_DESIRED_FILE=wsl_path(CAPTURE),
                    OPENKILL_NFT_SHADOW_TYPED_OVERRIDE=override,
                )
                self.assertEqual(rc, 12, process.stderr)
                self.assertEqual(status.get("status"), "MODEL_GAP")
                self.assertEqual(status.get("reason"), "external-typed-sidecar-disallowed")

    def test_unknown_inventory_ownership_fails_closed(self) -> None:
        staged = self.harness.root / "unknown-component"
        staged.mkdir()
        manifest = (TEMPLATE_DIR / "semantic_model_v1.tsv").read_text(encoding="utf-8")
        manifest += "INVENTORY\tchain\topenkill_dns_hijack\tUNKNOWN\tDNS\n"
        write_lf(staged / "semantic_model_v1.tsv", manifest)
        process, rc, status = self.run_auto(OPENKILL_NFT_SHADOW_SEMANTIC_MANIFEST=wsl_path(staged / "semantic_model_v1.tsv"))
        self.assertEqual(rc, 12, process.stderr)
        self.assertEqual(status.get("status"), "MODEL_GAP")

    def test_positive_path_is_stable_for_five_cycles(self) -> None:
        rows = [self.run_auto()[2] for _ in range(5)]
        self.assertTrue(all(row.get("status") == "MATCH" for row in rows))
        self.assertEqual({row.get("actual_owned_hash") for row in rows}, {rows[0].get("actual_owned_hash")})
        self.assertEqual({row.get("desired_owned_hash") for row in rows}, {rows[0].get("desired_owned_hash")})
        self.assertEqual({row.get("dns_actual_hash") for row in rows}, {rows[0].get("dns_actual_hash")})
        self.assertEqual({row.get("dns_desired_hash") for row in rows}, {rows[0].get("dns_desired_hash")})

    def test_staged_observer_manifest_and_templates_are_self_contained(self) -> None:
        staged = self.harness.root / "staged"
        staged.mkdir()
        staged_shadow = staged / "shadow"
        staged_shadow.mkdir()
        shutil.copy2(HELPER, staged / "openkill_nft_shadow.sh")
        shutil.copy2(RENDERER, staged / "openkill_nft_renderer.sh")
        for name in ("semantic_model_v1.tsv", "input_tun_v1.tsv"):
            shutil.copy2(TEMPLATE_DIR / name, staged_shadow / name)
        process, rc, status = self.run_auto(
            OPENKILL_NFT_SHADOW_RENDERER=wsl_path(staged / "openkill_nft_renderer.sh"),
            OPENKILL_NFT_SHADOW_TEMPLATE_DIR=wsl_path(staged_shadow),
        )
        self.assertEqual(rc, 0, process.stderr)
        self.assertEqual(status.get("status"), "MATCH")


if __name__ == "__main__":
    unittest.main()
