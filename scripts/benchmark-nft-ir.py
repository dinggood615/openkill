#!/usr/bin/env python3
"""Lightweight development benchmark for the Phase 3A abstract IR."""

from __future__ import annotations

import copy
import json
import pathlib
import statistics
import time

from openkill_nft_ir import diff_ir, render_context, render_state
from openkill_shadow_adapter import validate_state_fixture


ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_FIXTURE = ROOT / "scripts/fixtures/openkill-shadow-states-v1.json"
CLASSIFIER_FIXTURE = ROOT / "scripts/fixtures/openkill-classifier-semantic-v1.json"


def _percentile(values, fraction):
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _milliseconds(values):
    return [value * 1000.0 for value in values]


def main():
    with STATE_FIXTURE.open(encoding="utf-8") as handle:
        state = validate_state_fixture(json.load(handle))["states"][-4]
    with CLASSIFIER_FIXTURE.open(encoding="utf-8") as handle:
        context = json.load(handle)["cases"][0]

    iterations = 1000
    render_samples = []
    context_samples = []
    diff_samples = []
    baseline = render_state(state)
    changed_state = copy.deepcopy(state)
    changed_state["node4"] = list(changed_state.get("node4", ())) + ["203.0.113.250"]
    changed = render_state(changed_state)

    for _ in range(iterations):
        started = time.perf_counter()
        render_state(state)
        render_samples.append(time.perf_counter() - started)

        started = time.perf_counter()
        render_context(context)
        context_samples.append(time.perf_counter() - started)

        started = time.perf_counter()
        diff_ir(baseline, changed)
        diff_samples.append(time.perf_counter() - started)

    render_ms = _milliseconds(render_samples)
    context_ms = _milliseconds(context_samples)
    diff_ms = _milliseconds(diff_samples)
    print("IR_RENDER_ITERATIONS={}".format(iterations))
    print("IR_RENDER_MEDIAN_MS={:.6f}".format(statistics.median(render_ms)))
    print("IR_RENDER_P95_MS={:.6f}".format(_percentile(render_ms, 0.95)))
    print("IR_CONTEXT_RENDER_MEDIAN_MS={:.6f}".format(statistics.median(context_ms)))
    print("IR_CONTEXT_RENDER_P95_MS={:.6f}".format(_percentile(context_ms, 0.95)))
    print("IR_DIFF_MEDIAN_MS={:.6f}".format(statistics.median(diff_ms)))
    print("IR_DIFF_P95_MS={:.6f}".format(_percentile(diff_ms, 0.95)))
    print("NOT_PRODUCTION_BENCHMARK=YES")


if __name__ == "__main__":
    main()
