#!/usr/bin/env python3
"""Small development-only benchmark for the Phase 2C shadow adapter."""

from __future__ import annotations

import json
import pathlib
import statistics
import time

from openkill_shadow_adapter import adapt, shadow_compare, validate_intent_fixture, validate_state_fixture


ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_FIXTURE = ROOT / "scripts/fixtures/openkill-shadow-states-v1.json"
INTENT_FIXTURE = ROOT / "scripts/fixtures/openkill-current-firewall-intent-v1.json"
ITERATIONS = 1000


def _load(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _percentile(values, fraction):
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return ordered[index]


def main():
    states = validate_state_fixture(_load(STATE_FIXTURE))["states"]
    by_id = {state["id"]: state for state in states}
    intent = validate_intent_fixture(_load(INTENT_FIXTURE))
    cases = intent["cases"]
    # Use a representative mix, including IPv4, IPv6, DNS and overlap cases.
    selected = [cases[index % len(cases)] for index in range(ITERATIONS)]

    for case in selected[:10]:
        adapt(by_id[case["state_id"]], case["packet"])
        shadow_compare(by_id[case["state_id"]], case["packet"], case)

    context_times = []
    for case in selected:
        state = by_id[case["state_id"]]
        start = time.perf_counter_ns()
        adapt(state, case["packet"])
        context_times.append((time.perf_counter_ns() - start) / 1_000_000)

    compare_times = []
    for case in selected:
        state = by_id[case["state_id"]]
        start = time.perf_counter_ns()
        shadow_compare(state, case["packet"], case)
        compare_times.append((time.perf_counter_ns() - start) / 1_000_000)

    print("SHADOW_ADAPTER_ITERATIONS={}".format(ITERATIONS))
    print("STATE_TO_CONTEXT_MEDIAN_MS={:.6f}".format(statistics.median(context_times)))
    print("STATE_TO_CONTEXT_P95_MS={:.6f}".format(_percentile(context_times, 0.95)))
    print("SHADOW_COMPARE_MEDIAN_MS={:.6f}".format(statistics.median(compare_times)))
    print("SHADOW_COMPARE_P95_MS={:.6f}".format(_percentile(compare_times, 0.95)))
    print("NOT_PRODUCTION_BENCHMARK=YES")


if __name__ == "__main__":
    main()
