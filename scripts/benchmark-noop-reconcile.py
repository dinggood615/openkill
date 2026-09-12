#!/usr/bin/env python3
"""Measure the production manual-reload no-op entry point with local fixtures."""

import argparse
import importlib.util
import json
import pathlib
import statistics
import tempfile
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST_MODULE_PATH = ROOT / "scripts/test-network-model.py"


def load_test_module():
    spec = importlib.util.spec_from_file_location("openkill_network_model_tests", TEST_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--init", type=pathlib.Path, help="init script to profile (defaults to the working tree)")
    parser.add_argument(
        "--legacy-migration",
        action="store_true",
        help="measure the first legacy-baseline migration and the following current-schema reload",
    )
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    tests = load_test_module()
    if args.init is not None:
        tests.INIT = args.init

    if args.legacy_migration:
        first_samples = []
        second_samples = []
        first_traces = []
        second_traces = []
        first_rewrites = 0
        second_rewrites = 0
        for _ in range(args.iterations):
            with tempfile.TemporaryDirectory() as directory:
                state = pathlib.Path(directory)
                applied = state / "fingerprint.applied"
                started = time.perf_counter_ns()
                result, trace = tests.run_manual_reload_harness(state, legacy=True)
                first_samples.append((time.perf_counter_ns() - started) / 1_000_000)
                if result.returncode != 0:
                    raise SystemExit(result.stderr or "legacy migration harness failed")
                first_traces.append(trace)
                if applied.read_text(encoding="utf-8").startswith("SCHEMA=2\n"):
                    first_rewrites += 1
                migrated_mtime = applied.stat().st_mtime_ns
                started = time.perf_counter_ns()
                result, trace = tests.run_manual_reload_harness(state, initialize=False)
                second_samples.append((time.perf_counter_ns() - started) / 1_000_000)
                if result.returncode != 0:
                    raise SystemExit(result.stderr or "current-schema no-op harness failed")
                second_traces.append(trace)
                if applied.stat().st_mtime_ns != migrated_mtime:
                    second_rewrites += 1

        def summary(samples):
            ordered = sorted(samples)
            return {
                "iterations": args.iterations,
                "median_ms": statistics.median(samples),
                "p95_ms": ordered[max(0, int(args.iterations * 0.95) - 1)],
            }

        print(json.dumps({
            "scenario": "LEGACY_HEALTHY_MIGRATION",
            "first_reload": {
                **summary(first_samples),
                "baseline_atomic_replacements": first_rewrites,
                "no_apply": sum(trace == "run-mode\n" for trace in first_traces),
            },
            "second_reload": {
                **summary(second_samples),
                "baseline_atomic_replacements": second_rewrites,
                "no_apply": sum(trace == "run-mode\n" for trace in second_traces),
            },
        }, indent=2, sort_keys=True))
        return

    samples = []
    apply_traces = []
    for _ in range(args.iterations):
        with tempfile.TemporaryDirectory() as directory:
            started = time.perf_counter_ns()
            result, trace = tests.run_manual_reload_harness(pathlib.Path(directory), changed=False)
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            if result.returncode != 0:
                raise SystemExit(result.stderr or "manual reload harness failed")
            samples.append(elapsed_ms)
            apply_traces.append(trace)

    ordered = sorted(samples)
    print(json.dumps({
        "scenario": "MANUAL_RELOAD_NOOP",
        "iterations": args.iterations,
        "median_ms": statistics.median(samples),
        "p95_ms": ordered[max(0, int(args.iterations * 0.95) - 1)],
        "apply_trace_counts": {
            "no_apply": sum(trace == "run-mode\n" for trace in apply_traces),
            "apply_path": sum(trace != "run-mode\n" for trace in apply_traces),
        },
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
