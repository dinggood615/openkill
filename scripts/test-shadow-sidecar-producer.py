#!/usr/bin/env python3
"""Regression tests for the self-contained automatic typed shadow path.

The harness uses only checked-in sanitized fixtures and a temporary shell
environment.  It never contacts a device and never supplies typed sidecars to
the automatic coordinator.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
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
        "OPENKILL_DNS_ENDPOINT", "OPENKILL_MIHOMO_DNS_LISTENER", "MIHOMO_DNS_LISTENER",
        "mihomo_dns_listener", "OPENKILL_DNSMASQ_LISTEN_TARGET", "DNSMASQ_LISTEN_TARGET",
        "dnsmasq_listen_target", "OPENKILL_DNSMASQ_UPSTREAM_TARGET", "DNSMASQ_UPSTREAM_TARGET",
        "dnsmasq_upstream_target", "DNSPORT", "FAKE_UCI_COUNT",
    )

    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="openkill-shadow-sidecar-")
        self.root = Path(self.temp.name)
        self.counter = 0
        self.last_runner: Path | None = None

    def close(self) -> None:
        self.temp.cleanup()

    def run(
        self,
        env: dict[str, str | Path | None],
        timeout: int = 60,
        body: str | None = None,
        helper: Path = HELPER,
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        self.counter += 1
        case = self.root / f"case-{self.counter}"
        case.mkdir(parents=True, exist_ok=True)
        telemetry = case / "telemetry"
        runner = case / "runner.sh"
        self.last_runner = runner
        lines = ["#!/bin/sh", "set +e"]
        lines.extend(f"unset {key}" for key in self._UNSET)
        for key, value in env.items():
            if value is None:
                lines.append(f"unset {key}")
            else:
                lines.append(f"export {key}={quote(value)}")
        # The helper path is an explicit execution input.  Staging tests pass
        # a temporary copy here so a repository helper cannot be loaded by a
        # hidden fallback while the candidate is being exercised.
        lines.append(f". {quote(wsl_path(helper))}")
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

    def run_auto(
        self,
        capture: Path = CAPTURE,
        helper: Path = HELPER,
        body: str | None = None,
        **extra: str | Path | None,
    ):
        process, telemetry = self.harness.run(
            self.harness.env(capture, **extra), helper=helper, body=body
        )
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
        write_lf(
            fake_bin / "netstat",
            """#!/bin/sh
printf 'Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name\\n'
printf 'tcp        0      0 127.0.0.1:7874          0.0.0.0:*               LISTEN      123/mihomo\\n'
""",
        )
        (fake_bin / "netstat").chmod(0o700)
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

    def test_mihomo_listener_uses_live_process_evidence_not_endpoint_intent(self) -> None:
        fake_bin = self.harness.root / "runtime-dns-bin"
        fake_bin.mkdir()
        write_lf(
            fake_bin / "uci",
            """#!/bin/sh
case "$*" in
    *port) printf '53\\n' ;;
    *server) printf '127.0.0.1#7874\\n' ;;
    *) exit 1 ;;
esac
""",
        )
        write_lf(
            fake_bin / "netstat",
            """#!/bin/sh
printf 'Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name\\n'
printf 'tcp        0      0 127.0.0.1:7874          0.0.0.0:*               LISTEN      123/mihomo\\n'
""",
        )
        (fake_bin / "uci").chmod(0o700)
        (fake_bin / "netstat").chmod(0o700)
        state_dir = self.harness.root / "runtime-dns-state"
        process, _ = self.harness.run(
            {
                "PATH": f"{wsl_path(fake_bin)}:/usr/bin:/bin",
                # This is readiness/configuration intent and must not win over
                # the process-owned socket evidence.
                "OPENKILL_DNS_ENDPOINT": "127.0.0.1:9999",
                "OPENKILL_MIHOMO_DNS_LISTENER": "127.0.0.1:9999",
            },
            body=(
                f"mkdir -p {quote(wsl_path(state_dir))}; "
                f"openkill_shadow_capture_runtime_dns {quote(wsl_path(state_dir))}; rc=$?; "
                "printf 'RC=%s\\n' \"$rc\"; "
                "printf 'LISTENER=%s\\n' \"${OPENKILL_NFT_SHADOW_FROZEN_MIHOMO_DNS_LISTENER:-}\"; "
                "printf 'SOURCE=%s\\n' \"${OPENKILL_NFT_SHADOW_FROZEN_MIHOMO_DNS_SOURCE:-}\""
            ),
        )
        self.assertIn("RC=0", process.stdout, process.stderr)
        self.assertIn("LISTENER=127.0.0.1:7874", process.stdout, process.stderr)
        self.assertIn("SOURCE=netstat-mihomo", process.stdout, process.stderr)

    def test_missing_live_mihomo_evidence_does_not_fallback_to_endpoint(self) -> None:
        fake_bin = self.harness.root / "missing-runtime-dns-bin"
        fake_bin.mkdir()
        write_lf(
            fake_bin / "uci",
            """#!/bin/sh
case "$*" in
    *port) printf '53\\n' ;;
    *server) printf '127.0.0.1#7874\\n' ;;
    *) exit 1 ;;
esac
""",
        )
        # A successful but empty process table is still a source gap.  The
        # endpoint intent below must never be accepted as live evidence.
        write_lf(fake_bin / "netstat", "#!/bin/sh\nexit 0\n")
        (fake_bin / "uci").chmod(0o700)
        (fake_bin / "netstat").chmod(0o700)
        state_dir = self.harness.root / "missing-runtime-dns-state"
        process, _ = self.harness.run(
            {
                "PATH": f"{wsl_path(fake_bin)}:/usr/bin:/bin",
                "OPENKILL_DNS_ENDPOINT": "127.0.0.1:7874",
            },
            body=(
                f"mkdir -p {quote(wsl_path(state_dir))}; "
                f"openkill_shadow_capture_runtime_dns {quote(wsl_path(state_dir))}; rc=$?; "
                "printf 'RC=%s\\n' \"$rc\""
            ),
        )
        self.assertIn("RC=11", process.stdout, process.stderr)

    def test_dns_endpoint_is_intent_only_in_runtime_capture(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        capture = source.split("openkill_shadow_capture_runtime_dns()", 1)[1].split("\nopenkill_shadow_auto_continuity_snapshot()", 1)[0]
        self.assertNotIn("runtime_dns_mihomo=${OPENKILL_DNS_ENDPOINT", capture)
        self.assertIn("netstat-mihomo", capture)

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
        staged_helper = staged / "openkill_nft_shadow.sh"
        staged_renderer = staged / "openkill_nft_renderer.sh"
        staged_manifest = staged_shadow / "semantic_model_v1.tsv"
        staged_template = staged_shadow / "input_tun_v1.tsv"
        # The marker is appended only to this temporary candidate.  It makes
        # the executed shell provenance observable and turns a hidden source
        # fallback into a deterministic test failure.
        with staged_helper.open("ab") as stream:
            stream.write(b"\nOPENKILL_SHADOW_STAGED_EXECUTION=1\n")
        identity_inputs = (staged_helper, staged_manifest, staged_renderer, staged_template)
        identity = hashlib.sha256(
            "\n".join(
                f"{path.name}:{hashlib.sha256(path.read_bytes()).hexdigest()}"
                for path in identity_inputs
            ).encode()
        ).hexdigest()
        # Deliberately make the repository helper unavailable to the staged
        # runner.  The explicit helper argument above is the only source of
        # production shell code for these cycles; a fallback would fail.
        staged_processes = []
        statuses = []
        for _ in range(5):
            process, rc, status = self.run_auto(
                helper=staged_helper,
                body=(
                    "openkill_shadow_compare_nft; rc=$?; "
                    "printf 'RC=%s\\n' \"$rc\"; "
                    "printf 'STAGED_MARKER=%s\\n' \"${OPENKILL_SHADOW_STAGED_EXECUTION:-0}\"; "
                    f"printf 'OBSERVER_PATH=%s\\n' {quote(wsl_path(staged_helper))}; "
                    f"printf 'MANIFEST_PATH=%s\\n' {quote(wsl_path(staged_manifest))}; "
                    f"printf 'RENDERER_PATH=%s\\n' {quote(wsl_path(staged_renderer))}; "
                    f"printf 'TEMPLATE_PATH=%s\\n' {quote(wsl_path(staged_template))}; "
                    f"printf 'EXECUTION_IDENTITY_HASH=%s\\n' {quote(identity)}"
                ),
                OPENKILL_NFT_SHADOW_RENDERER=wsl_path(staged_renderer),
                OPENKILL_NFT_SHADOW_TEMPLATE_DIR=wsl_path(staged_shadow),
            )
            staged_processes.append((process, rc))
            statuses.append(status)
        for process, rc in staged_processes:
            self.assertEqual(rc, 0, process.stderr)
            self.assertIn("STAGED_MARKER=1", process.stdout)
            self.assertIn(f"OBSERVER_PATH={wsl_path(staged_helper)}", process.stdout)
            self.assertIn(f"MANIFEST_PATH={wsl_path(staged_manifest)}", process.stdout)
            self.assertIn(f"RENDERER_PATH={wsl_path(staged_renderer)}", process.stdout)
            self.assertIn(f"TEMPLATE_PATH={wsl_path(staged_template)}", process.stdout)
            self.assertIn(f"EXECUTION_IDENTITY_HASH={identity}", process.stdout)
        self.assertIsNotNone(self.harness.last_runner)
        runner_text = self.harness.last_runner.read_text(encoding="utf-8")
        self.assertIn(wsl_path(staged_helper), runner_text)
        self.assertNotIn(wsl_path(HELPER), runner_text)
        self.assertNotIn(wsl_path(RENDERER), runner_text)
        self.assertNotIn(wsl_path(TEMPLATE_DIR), runner_text)
        self.assertTrue(all(status.get("status") == "MATCH" for status in statuses))
        self.assertEqual({status.get("actual_owned_hash") for status in statuses}, {statuses[0].get("actual_owned_hash")})
        self.assertEqual({status.get("desired_owned_hash") for status in statuses}, {statuses[0].get("desired_owned_hash")})
        self.assertEqual({status.get("dns_actual_hash") for status in statuses}, {statuses[0].get("dns_actual_hash")})
        self.assertEqual({status.get("dns_desired_hash") for status in statuses}, {statuses[0].get("dns_desired_hash")})
        self.assertTrue(identity)
        self.assertNotEqual(staged_helper.resolve(), HELPER.resolve())


if __name__ == "__main__":
    unittest.main()
