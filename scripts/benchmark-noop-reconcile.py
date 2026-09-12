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
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    tests = load_test_module()
    if args.init is not None:
        tests.INIT = args.init

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
