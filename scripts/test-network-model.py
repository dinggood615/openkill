#!/usr/bin/env python3
"""Pure tests for the Stage B network snapshot/desired-state boundary."""
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_network.sh"


def build(snapshot: str):
    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / "snapshot"
        out = pathlib.Path(td) / "desired"
        src.write_text(snapshot, encoding="utf-8", newline="\n")
        subprocess.run(
            ["sh", "-c", f'. "{HELPER}"; openkill_build_desired_state "$1" "$2"', "model", str(src), str(out)],
            check=True,
        )
        return dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines() if "=" in line)


class NetworkModelTests(unittest.TestCase):
    def test_source_specific_native_routes_are_untouched(self):
        state = build("""SNAPSHOT_VERSION=1
LOCAL_IPV6_READY=1
INTERNAL_IPV6_PREFIXES=2001:db8:10::/62 2001:db8:20::/64
NATIVE_IPV6_ROUTES=default from 2001:db8:10::/62 via fe80::1
""")
        self.assertEqual(state["NATIVE_IPV6_ROUTE_MUTATIONS"], "0")
        self.assertEqual(state["IPV6_TUN_ROUTE"], "1")
        self.assertEqual(state["LOCALNETWORK6_PREFIXES"], "2001:db8:10::/62 2001:db8:20::/64")

    def test_ipv4_only_and_no_wan6(self):
        state = build("SNAPSHOT_VERSION=1\nLOCAL_IPV6_READY=0\nINTERNAL_IPV6_PREFIXES=\n")
        self.assertEqual(state["IPV4_PROXY_RULE"], "1")
        self.assertEqual(state["IPV6_PROXY_RULE"], "0")
        self.assertEqual(state["IPV6_TUN_ROUTE"], "0")

    def test_multiple_pd_and_pppoe_are_data_not_interface_assumptions(self):
        state = build("""SNAPSHOT_VERSION=1
WAN4_L3_DEVICE=pppoe-wan
WAN6_L3_DEVICE=pppoe-wan
LOCAL_IPV6_READY=1
INTERNAL_IPV6_PREFIXES=2001:db8:a::/60 2001:db8:b::/64 2001:db8:c::/64
""")
        self.assertEqual(state["LOCALNETWORK6_PREFIXES"].split(), ["2001:db8:a::/60", "2001:db8:b::/64", "2001:db8:c::/64"])
        self.assertEqual(state["OPENKILL_ROUTE_TABLE"], "0x162")
        self.assertEqual(state["OPENKILL_RULE_PREF"], "1888")

    def test_public_probe_does_not_disable_local_ipv6(self):
        state = build("SNAPSHOT_VERSION=1\nLOCAL_IPV6_READY=1\nPUBLIC_IPV6_HEALTH=failed\n")
        self.assertEqual(state["IPV6_PROXY_RULE"], "1")
        self.assertEqual(state["NATIVE_IPV6_ROUTE_MUTATIONS"], "0")


if __name__ == "__main__":
    unittest.main()
