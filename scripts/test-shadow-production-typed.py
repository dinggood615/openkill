#!/usr/bin/env python3
"""Local regression tests for the POSIX production typed-shadow path.

The fixtures are sanitized and checked in.  The test invokes the production
shell coordinator in a temporary shell only; it never contacts a router,
starts a service, or executes a dataplane command.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import unittest
import hashlib
import json

from openkill_shadow_semantic_model import DNS_FIELDS, OWNERSHIP_CLASSES, compare_semantic_intents


ROOT = pathlib.Path(__file__).resolve().parents[1]
SHARE = ROOT / "luci-app-openkill/root/usr/share/openkill"
HELPER = SHARE / "openkill_nft_shadow.sh"
RENDERER = SHARE / "openkill_nft_renderer.sh"
TEMPLATE_DIR = SHARE / "shadow"
AUTO_SOURCE = ROOT / "scripts/fixtures/openkill-shadow-auto-state-v1.txt"
CAPTURE = ROOT / "scripts/fixtures/openkill-legacy-runtime-capture-v1.txt"
ACTUAL = ROOT / "scripts/fixtures/openkill-shadow-typed-actual-v1.tsv"
DESIRED = ROOT / "scripts/fixtures/openkill-shadow-typed-desired-v1.tsv"
SEMANTIC_FIXTURE = ROOT / "scripts/fixtures/openkill-shadow-semantic-v1.json"


def wsl_path(path: pathlib.Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if not drive:
        return resolved.as_posix()
    tail = resolved.as_posix().split(":", 1)[-1]
    return f"/mnt/{drive}/{tail.lstrip('/')}"


def quote(value: str | pathlib.Path) -> str:
    text = str(value)
    return "'" + text.replace("'", "'\"'\"'") + "'"


def write_lf(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").replace("\r", "\n").encode())


def status_file(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


class ShellHarness:
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
        "OPENKILL_NFT_SHADOW_CAPTURE_FIXTURE",
        "OPENKILL_NFT_SHADOW_NFT_BIN",
        "OPENKILL_NFT_SHADOW_CAPTURE_NFT_BIN",
        "OPENKILL_NFT_SHADOW_CAPTURE_CHAINS",
        "OPENKILL_NFT_SHADOW_CAPTURE_SETS",
        "OPENKILL_NFT_SHADOW_CAPTURE_TRACE",
        "OPENKILL_NFT_SHADOW_RENDERER",
        "OPENKILL_NFT_SHADOW_TEMPLATE_DIR",
        "OPENKILL_NFT_SHADOW_SEMANTIC_MANIFEST",
        "OPENKILL_NFT_SHADOW_TYPED_ACTUAL_FILE",
        "OPENKILL_NFT_SHADOW_TYPED_DESIRED_FILE",
        "OPENKILL_NFT_SHADOW_TELEMETRY_DIR",
        "OPENKILL_NFT_SHADOW_FORCE",
        "OPENKILL_NFT_SHADOW_TIMEOUT",
        "OPENKILL_NETWORK_DESIRED",
        "OPENKILL_NETWORK_APPLIED_FILE",
        "OPENKILL_NETWORK_SNAPSHOT",
    )

    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="openkill-shadow-typed-")
        self.root = pathlib.Path(self.temp.name)
        self.count = 0

    def close(self) -> None:
        self.temp.cleanup()

    def run(self, body: str, env: dict[str, str | pathlib.Path | None] | None = None) -> subprocess.CompletedProcess[str]:
        self.count += 1
        case = self.root / f"case-{self.count}"
        case.mkdir(parents=True, exist_ok=True)
        runner = case / "runner.sh"
        lines = ["#!/bin/sh", "set +e"]
        lines.extend(f"unset {key}" for key in self._UNSET)
        for key, value in (env or {}).items():
            if value is None:
                lines.append(f"unset {key}")
            else:
                lines.append(f"export {key}={quote(value)}")
        lines.append(f". {quote(wsl_path(HELPER))}")
        lines.append(body)
        write_lf(runner, "\n".join(lines) + "\n")
        command = ["wsl.exe", "-u", "root", "--", "sh", wsl_path(runner)] if shutil.which("wsl.exe") else ["sh", str(runner)]
        return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)


class TypedProductionShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = ShellHarness()

    def tearDown(self) -> None:
        self.harness.close()

    def typed_env(self, actual: pathlib.Path = ACTUAL, desired: pathlib.Path = DESIRED) -> dict[str, str]:
        return {
            "OPENKILL_NFT_SHADOW_TEMPLATE_DIR": wsl_path(TEMPLATE_DIR),
            "OPENKILL_NFT_SHADOW_TYPED_ACTUAL_FILE": wsl_path(actual),
            "OPENKILL_NFT_SHADOW_TYPED_DESIRED_FILE": wsl_path(desired),
        }

    def direct(self, actual: pathlib.Path = ACTUAL, desired: pathlib.Path = DESIRED) -> tuple[subprocess.CompletedProcess[str], pathlib.Path]:
        work = self.harness.root / f"direct-{self.harness.count + 1}"
        work.mkdir(parents=True, exist_ok=True)
        env = self.typed_env(actual, desired)
        body = (
            f"openkill_shadow_compare_typed_intent {quote(wsl_path(actual))} {quote(wsl_path(desired))} {quote(wsl_path(work))}; "
            "rc=$?; printf 'RC=%s\\n' \"$rc\"; "
            "printf 'RESULT=%s\\n' \"${openkill_shadow_typed_status:-}\"; "
            "printf 'DNS=%s\\n' \"${openkill_shadow_typed_dns_parity:-}\"; "
            "printf 'MISMATCH=%s GAP=%s OUT=%s UNKNOWN=%s\\n' "
            "\"${openkill_shadow_typed_mismatch_count:-}\" \"${openkill_shadow_typed_model_gap_count:-}\" "
            "\"${openkill_shadow_typed_out_of_scope_count:-}\" \"${openkill_shadow_typed_unknown_count:-}\""
        )
        return self.harness.run(body, env), work

    @staticmethod
    def output(process: subprocess.CompletedProcess[str]) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in process.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        return values

    def coordinator(self, actual: pathlib.Path = ACTUAL, desired: pathlib.Path = DESIRED) -> tuple[subprocess.CompletedProcess[str], dict[str, str], pathlib.Path]:
        case = self.harness.root / f"coordinator-{self.harness.count + 1}"
        telemetry = case / "telemetry"
        case.mkdir(parents=True, exist_ok=True)
        env = {
            "OPENKILL_NFT_SHADOW": "1",
            "OPENKILL_NFT_SHADOW_FORCE": "1",
            "OPENKILL_NFT_SHADOW_SOURCE_FILE": wsl_path(AUTO_SOURCE),
            "OPENKILL_NFT_SHADOW_CAPTURE_FIXTURE": wsl_path(CAPTURE),
            "OPENKILL_NFT_SHADOW_RENDERER": wsl_path(RENDERER),
            "OPENKILL_NFT_SHADOW_TELEMETRY_DIR": wsl_path(telemetry),
            **self.typed_env(actual, desired),
        }
        body = f"openkill_shadow_compare_nft; printf 'RC=%s\\n' \"$?\""
        process = self.harness.run(body, env)
        return process, status_file(telemetry / "status"), telemetry

    def test_coordinator_replay_excludes_wan_from_owned_parity(self) -> None:
        process, status, telemetry = self.coordinator()
        self.assertIn("RC=0", process.stdout, process.stderr)
        self.assertEqual(status.get("status"), "MATCH")
        self.assertEqual(status.get("dns_parity"), "MATCH")
        self.assertEqual(status.get("model_gap_count"), "0")
        self.assertGreater(int(status.get("out_of_scope_observed_count", "0")), 0)
        self.assertEqual(status.get("actual_owned_hash"), status.get("desired_owned_hash"))
        self.assertTrue(status.get("actual_full_observation_hash"))
        self.assertTrue(status.get("desired_full_observation_hash"))
        self.assertNotEqual(status.get("actual_full_observation_hash"), status.get("desired_full_observation_hash"))
        self.assertEqual(status.get("dns_actual_hash"), status.get("dns_desired_hash"))
        self.assertEqual(status.get("comparison_model_version"), "1")
        self.assertEqual(status.get("ownership_model_version"), "1")
        self.assertEqual(status.get("dns_model_version"), "1")
        self.assertTrue((telemetry / "status").is_file())

    def test_owned_projection_change_is_mismatch(self) -> None:
        desired = self.harness.root / "owned-change.tsv"
        write_lf(desired, DESIRED.read_text(encoding="utf-8").replace("action=RETURN;family=IPv4", "action=DROP;family=IPv4", 1))
        process, _ = self.direct(desired=desired)
        values = self.output(process)
        self.assertIn("RC=1", process.stdout)
        self.assertEqual(values.get("RESULT"), "MISMATCH")
        self.assertEqual(values.get("DNS"), "MATCH")

    def test_unknown_ownership_fails_closed_as_model_gap(self) -> None:
        actual = self.harness.root / "unknown.tsv"
        write_lf(actual, ACTUAL.read_text(encoding="utf-8").replace("WAN_SAFETY\tLEGACY_ONLY_SAFETY", "WAN_SAFETY\tUNKNOWN", 1))
        process, _ = self.direct(actual=actual)
        values = self.output(process)
        self.assertIn("RC=12", process.stdout)
        self.assertEqual(values.get("RESULT"), "MODEL_GAP")
        self.assertEqual(values.get("DNS"), "MATCH")

    def test_coordinator_keeps_model_gap_count_separate_from_mismatch_count(self) -> None:
        actual = self.harness.root / "coordinator-unknown.tsv"
        write_lf(actual, ACTUAL.read_text(encoding="utf-8").replace("WAN_SAFETY\tLEGACY_ONLY_SAFETY", "WAN_SAFETY\tUNKNOWN", 1))
        process, status, _ = self.coordinator(actual=actual)
        self.assertIn("RC=12", process.stdout)
        self.assertEqual(status.get("status"), "MODEL_GAP")
        self.assertEqual(status.get("mismatch_count"), "0")
        self.assertGreater(int(status.get("model_gap_count", "0")), 0)
        self.assertEqual(status.get("dns_parity"), "MATCH")

    def test_dns_fields_are_independent_and_never_equated(self) -> None:
        mutations = {
            "DNS_FIREWALL_LAN_TARGET": ("53", "54"),
            "DNS_FIREWALL_ROUTER_TARGET": ("53", "54"),
            "DNSMASQ_LISTEN_TARGET": ("53", "54"),
            "DNSMASQ_UPSTREAM_TARGET": ("127.0.0.1#7874", "127.0.0.1#7875"),
            "MIHOMO_DNS_LISTENER": ("127.0.0.1:7874", "127.0.0.1:7875"),
            "DNS_LOOP_PREVENTION": ("skgid_exempt=65534", "skgid_exempt=65533"),
            "DNS_SCOPE_IPV4": ("lan=true,router=true", "lan=true,router=false"),
            "DNS_SCOPE_IPV6": ("lan=true,router=true", "lan=false,router=true"),
        }
        for field, (old, new) in mutations.items():
            desired = self.harness.root / f"dns-{field}.tsv"
            write_lf(desired, DESIRED.read_text(encoding="utf-8").replace(f"DNS\t{field}\t{old}", f"DNS\t{field}\t{new}", 1))
            process, _ = self.direct(desired=desired)
            values = self.output(process)
            self.assertIn("RC=1", process.stdout, field)
            self.assertEqual(values.get("RESULT"), "MISMATCH", field)
            self.assertEqual(values.get("DNS"), "MISMATCH", field)

    def test_missing_dns_source_is_model_gap(self) -> None:
        desired = self.harness.root / "missing-source.tsv"
        write_lf(desired, DESIRED.read_text(encoding="utf-8").replace("DNSMASQ_UPSTREAM_TARGET\t127.0.0.1#7874\tCURRENT_OWNED\tcommitted dnsmasq desired state", "DNSMASQ_UPSTREAM_TARGET\t127.0.0.1#7874\tCURRENT_OWNED\t-", 1))
        process, _ = self.direct(desired=desired)
        values = self.output(process)
        self.assertIn("RC=12", process.stdout)
        self.assertEqual(values.get("RESULT"), "MODEL_GAP")

    def test_required_and_conditional_presence_rules(self) -> None:
        actual = self.harness.root / "without-local.tsv"
        write_lf(actual, "\n".join(line for line in ACTUAL.read_text(encoding="utf-8").splitlines() if "CURRENT_LOCAL_CHAIN" not in line and "CURRENT_LOCAL_RULE" not in line) + "\n")
        process, _ = self.direct(actual=actual)
        self.assertIn("RC=1", process.stdout)

        inactive = self.harness.root / "conditional-inactive.tsv"
        write_lf(inactive, DESIRED.read_text(encoding="utf-8").replace("OPENKILL_SHADOW_TYPED_INTENT_V1=1\n", "OPENKILL_SHADOW_TYPED_INTENT_V1=1\nOBJECT\tchain\tTPROXY_ONLY_RULE\topenkill_tproxy_only\tBACKEND\tCONDITIONAL_CURRENT\tINACTIVE\taction=TPROXY;family=IPv4\n", 1))
        process, _ = self.direct(actual=ACTUAL, desired=inactive)
        self.assertIn("RC=0", process.stdout)  # inactive conditional absence is allowed
        process, _ = self.direct(actual=actual, desired=inactive)
        self.assertIn("RC=1", process.stdout)  # required current local object still missing

        active = self.harness.root / "conditional-active.tsv"
        write_lf(active, DESIRED.read_text(encoding="utf-8").replace("OPENKILL_SHADOW_TYPED_INTENT_V1=1\n", "OPENKILL_SHADOW_TYPED_INTENT_V1=1\nOBJECT\tchain\tTPROXY_ONLY_RULE\topenkill_tproxy_only\tBACKEND\tCONDITIONAL_CURRENT\tACTIVE\taction=TPROXY;family=IPv4\n", 1))
        process, _ = self.direct(actual=ACTUAL, desired=active)
        self.assertIn("RC=1", process.stdout)

    def test_unknown_and_duplicate_records_are_model_gaps(self) -> None:
        duplicate = self.harness.root / "duplicate.tsv"
        body = ACTUAL.read_text(encoding="utf-8") + "DNS\tDNSMASQ_LISTEN_TARGET\t53\tCURRENT_OWNED\tduplicate\tACTIVE\n"
        write_lf(duplicate, body)
        process, _ = self.direct(actual=duplicate)
        self.assertIn("RC=12", process.stdout)

    def test_python_oracle_and_production_shell_agree(self) -> None:
        fixture = json.loads(SEMANTIC_FIXTURE.read_text(encoding="utf-8"))
        oracle = compare_semantic_intents(
            fixture["actual_intent"],
            fixture["desired_intent"],
            mode=fixture["mode"],
            formal_inventory=fixture["formal_inventory"],
            dns_actual=fixture["dns_actual"],
            dns_desired=fixture["dns_desired"],
        )
        self.assertEqual(oracle["parity"], "MATCH")
        self.assertFalse(oracle["dns"]["dns_53_7874_direct_equivalence"])
        process, _ = self.direct()
        self.assertEqual(self.output(process).get("RESULT"), oracle["parity"])
        self.assertEqual(self.output(process).get("DNS"), oracle["dns"]["parity"])

    def test_positive_fixture_is_stable_for_five_independent_runs(self) -> None:
        actual_hashes: set[str] = set()
        desired_hashes: set[str] = set()
        for _ in range(5):
            process, work = self.direct()
            self.assertIn("RC=0", process.stdout)
            actual_bytes = (work / "typed-semantic/actual.owned.sorted").read_bytes()
            desired_bytes = (work / "typed-semantic/desired.owned.sorted").read_bytes()
            actual_hashes.add(hashlib.sha256(actual_bytes).hexdigest())
            desired_hashes.add(hashlib.sha256(desired_bytes).hexdigest())
        self.assertEqual(len(actual_hashes), 1)
        self.assertEqual(len(desired_hashes), 1)

    def test_negative_results_are_stable_for_three_runs(self) -> None:
        desired = self.harness.root / "stable-negative.tsv"
        write_lf(desired, DESIRED.read_text(encoding="utf-8").replace("DNS_FIREWALL_ROUTER_TARGET\t53", "DNS_FIREWALL_ROUTER_TARGET\t54", 1))
        for _ in range(3):
            process, _ = self.direct(desired=desired)
            self.assertIn("RC=1", process.stdout)
            self.assertEqual(self.output(process).get("RESULT"), "MISMATCH")

    def test_legacy_physical_name_is_not_an_ownership_policy(self) -> None:
        unknown = self.harness.root / "wan-unknown.tsv"
        write_lf(unknown, ACTUAL.read_text(encoding="utf-8").replace("openkill_wan_input\tWAN_SAFETY\tLEGACY_ONLY_SAFETY", "openkill_wan_input\tWAN_SAFETY\tUNKNOWN", 1))
        process, _ = self.direct(actual=unknown)
        self.assertIn("RC=12", process.stdout)

    def test_shell_is_posix_and_legacy_name_heuristic_not_final_policy(self) -> None:
        text = HELPER.read_text(encoding="utf-8")
        self.assertNotIn("owned_chain", text)
        self.assertIn("openkill_shadow_compare_typed_intent", text)
        runner = self.harness.root / "syntax.sh"
        body = f"sh -n {quote(wsl_path(HELPER))}; printf 'RC=%s\\n' \"$?\""
        process = self.harness.run(body, self.typed_env())
        self.assertIn("RC=0", process.stdout)

    def test_manifest_vocabulary_matches_python_oracle(self) -> None:
        classes: set[str] = set()
        fields: dict[str, str] = {}
        for line in (TEMPLATE_DIR / "semantic_model_v1.tsv").read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            columns = line.split("\t")
            if columns[0] == "OWNERSHIP_CLASS":
                self.assertEqual(len(columns), 2)
                classes.add(columns[1])
            elif columns[0] == "DNS_FIELD":
                self.assertEqual(len(columns), 3)
                fields[columns[1]] = columns[2]
        self.assertEqual(classes, set(OWNERSHIP_CLASSES))
        self.assertEqual(set(fields), set(DNS_FIELDS))
        self.assertTrue(all(owner == "CURRENT_OWNED" for owner in fields.values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
