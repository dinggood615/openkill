#!/usr/bin/env python3
"""Development-only benchmark for the Phase 3B syntax model.

It measures Python IR lowering, serialization and AST diffing only.  No nft
process is started and the numbers must not be read as dataplane performance.
"""

from __future__ import annotations

import json
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from openkill_nft_ir import render_state
from openkill_nft_syntax import diff_syntax, lower_nft_ir, render_nft, serialize_nft
from openkill_shadow_adapter import validate_state_fixture


def percentile(values, fraction):
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return ordered[index]


def measure(callable_, iterations):
    samples = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        callable_()
        samples.append((time.perf_counter_ns() - start) / 1_000_000)
    return statistics.median(samples), percentile(samples, 0.95)


def main():
    fixture = json.loads((ROOT / "scripts/fixtures/openkill-shadow-states-v1.json").read_text(encoding="utf-8"))
    states = validate_state_fixture(fixture)["states"]
    state = next(item for item in states if item["id"] == "STATE-04-NODES")
    ir = render_state(state)
    ast = lower_nft_ir(ir)
    same = lower_nft_ir(render_state(state))
    render_median, render_p95 = measure(lambda: lower_nft_ir(ir), 100)
    serialize_median, serialize_p95 = measure(lambda: serialize_nft(ast), 1000)
    diff_median, diff_p95 = measure(lambda: diff_syntax(ast, same), 100)
    text = render_nft(ir)
    print("NFT_SYNTAX_BENCHMARK=DEVELOPMENT_ONLY")
    print("IR_TO_AST_RENDER_ITERATIONS=100")
    print("AST_TO_NFT_TEXT_SERIALIZE_ITERATIONS=1000")
    print("AST_DIFF_ITERATIONS=100")
    print("IR_TO_AST_RENDER_MEDIAN_MS={:.6f}".format(render_median))
    print("IR_TO_AST_RENDER_P95_MS={:.6f}".format(render_p95))
    print("NFT_TEXT_SERIALIZE_MEDIAN_MS={:.6f}".format(serialize_median))
    print("NFT_TEXT_SERIALIZE_P95_MS={:.6f}".format(serialize_p95))
    print("NFT_AST_DIFF_MEDIAN_MS={:.6f}".format(diff_median))
    print("NFT_AST_DIFF_P95_MS={:.6f}".format(diff_p95))
    print("NFT_TEXT_BYTES={}".format(len(text.encode("utf-8"))))
    print("NOT_PRODUCTION_BENCHMARK=YES")


if __name__ == "__main__":
    main()
