#!/usr/bin/env python3
"""Compare two openkill-benchmark.sh JSON reports without third-party modules."""

import argparse
import json
import sys
from pathlib import Path


METRICS = (
    ("IPv4 TCP", ("iperf", "ipv4", "tcp")),
    ("IPv6 TCP", ("iperf", "ipv6", "tcp")),
    ("CPU %", ("cpu", "utilization_percent")),
    ("Mihomo CPU %", ("cpu", "mihomo_percent")),
    ("Softirq delta", ("cpu", "softirq_delta")),
    ("Mem available", ("memory", "mem_available")),
    ("DNS overseas", ("connectivity", "dns_overseas")),
)


def load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def value(report, path):
    if path[0] == "iperf":
        family = "4" if path[1] == "ipv4" else "6"
        for item in report.get("iperf", []):
            if item.get("family") == family and item.get("protocol") == path[2] and item.get("streams") == "1":
                return item.get("summary", "N/A")
        return "N/A"
    current = report
    for key in path:
        if not isinstance(current, dict):
            return "N/A"
        current = current.get(key, "N/A")
    return current


def numeric(raw):
    try:
        return float(str(raw).split()[0].replace("%", ""))
    except (ValueError, TypeError, IndexError):
        return None


def metadata(report, *path):
    current = report
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def meaningful(raw):
    return raw not in (None, "", "N/A", "unavailable", "unknown")


def main():
    parser = argparse.ArgumentParser(description="Compare two OpenKill benchmark JSON files")
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    args = parser.parse_args()
    before = load(args.before)
    after = load(args.after)
    warnings = []
    for label, path in (
        ("architecture", ("device", "architecture")),
        ("CPU model", ("device", "cpu_model")),
        ("OpenWrt", ("device", "openwrt")),
        ("kernel", ("device", "kernel")),
        ("Mihomo", ("device", "mihomo_version")),
        ("OpenKill", ("device", "openkill_version")),
    ):
        old = metadata(before, *path)
        new = metadata(after, *path)
        if meaningful(old) and meaningful(new) and str(old) != str(new):
            warnings.append(f"{label} mismatch: {old} -> {new}")

    before_context = metadata(before, "iperf_context") or {}
    after_context = metadata(after, "iperf_context") or {}
    for label, key in (("iperf duration", "duration_seconds"), ("UDP setting", "udp_requested"), ("UDP rate", "udp_rate")):
        old = before_context.get(key)
        new = after_context.get(key)
        if meaningful(old) and meaningful(new) and str(old) != str(new):
            warnings.append(f"{label} mismatch: {old} -> {new}")

    def iperf_signature(report):
        return sorted((item.get("family"), item.get("streams"), item.get("protocol"))
                      for item in report.get("iperf", []) if isinstance(item, dict))

    if iperf_signature(before) != iperf_signature(after):
        warnings.append("iperf server/protocol/stream coverage mismatch")

    if warnings:
        print("Warnings:", file=sys.stderr)
        for warning in warnings:
            print(f"- {warning}", file=sys.stderr)
    print("Metric\tBefore\tAfter\tChange")
    for label, path in METRICS:
        old = value(before, path)
        new = value(after, path)
        old_num = numeric(old)
        new_num = numeric(new)
        if old_num is not None and new_num is not None:
            change = f"{new_num - old_num:+.2f}"
        else:
            change = "N/A"
        print(f"{label}\t{old}\t{new}\t{change}")


if __name__ == "__main__":
    main()
