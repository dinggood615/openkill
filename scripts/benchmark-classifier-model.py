#!/usr/bin/env python3
"""Small, repeatable benchmark for the detached classifier oracle."""

import json
import pathlib
import statistics
import time

from openkill_classifier_model import classify


ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "scripts/fixtures/openkill-classifier-semantic-v1.json"


def main() -> None:
    with FIXTURE.open(encoding="utf-8") as handle:
        cases = json.load(handle)["cases"]
    inputs = (cases * ((2000 + len(cases) - 1) // len(cases)))[:2000]
    for case in inputs[:100]:
        classify(case, "current")
    samples = []
    for case in inputs:
        start = time.perf_counter_ns()
        classify(case, "current")
        classify(case, "target")
        samples.append((time.perf_counter_ns() - start) / 1_000_000.0 / 2.0)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, int(len(ordered) * 0.95) - 1)
    print("classifications={}".format(len(samples) * 2))
    print("median_ms={:.6f}".format(statistics.median(samples)))
    print("p95_ms={:.6f}".format(ordered[p95_index]))
    print("min_ms={:.6f}".format(ordered[0]))
    print("max_ms={:.6f}".format(ordered[-1]))


if __name__ == "__main__":
    main()
