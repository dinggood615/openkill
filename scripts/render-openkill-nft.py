#!/usr/bin/env python3
"""Render a development ``NFT_IR_V1`` fixture to deterministic nft text.

This command is intentionally offline.  It only reads a checked-in state
fixture and writes the rendered text to stdout (or an explicitly requested
development output path); it never calls nft and never touches production
configuration.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from openkill_nft_ir import render_state
from openkill_nft_syntax import render_check_file, render_nft
from openkill_shadow_adapter import validate_state_fixture


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_STATES = ROOT / "scripts/fixtures/openkill-shadow-states-v1.json"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="development-only OpenKill NFT syntax renderer")
    parser.add_argument("--state-file", type=pathlib.Path, default=DEFAULT_STATES)
    parser.add_argument("--state-id", default="STATE-01-BASIC-V4")
    parser.add_argument("--profile", choices=("current", "target"), default="current")
    parser.add_argument("--development-preview", action="store_true")
    parser.add_argument("--scaffold", action="store_true", help="prepend TEST_ONLY FW4 parser scaffold")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    if args.profile == "target" and not args.development_preview:
        parser.error("--profile target requires --development-preview")
    with args.state_file.open(encoding="utf-8") as handle:
        fixture = validate_state_fixture(json.load(handle))
    states = {state["id"]: state for state in fixture["states"]}
    if args.state_id not in states:
        parser.error("unknown state id: {}".format(args.state_id))
    ir = render_state(states[args.state_id], profile=args.profile, target_preview=args.development_preview)
    text = render_check_file(ir) if args.scaffold else render_nft(ir)
    if args.output:
        args.output.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
