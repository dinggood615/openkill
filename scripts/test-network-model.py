#!/usr/bin/env python3
"""Pure tests for the Stage B network snapshot/desired-state boundary."""
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_network.sh"


def run_helper(action, *args):
    return subprocess.run(
        ["sh", "-c", f'. "{HELPER}"; {action} "$1" "$2"', "model", *map(str, args)],
        check=True, capture_output=True, text=True,
    )


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

    def test_fingerprint_is_order_independent_and_excludes_volatile_fields(self):
        with tempfile.TemporaryDirectory() as td:
            a, b, fa, fb = [pathlib.Path(td) / name for name in ("a", "b", "fa", "fb")]
            common = "WAN4_L3_DEVICE=pppoe-wan\nWAN6_L3_DEVICE=pppoe-wan\n"
            a.write_text(common + "WAN4_ADDRESSES=10.0.0.2 10.0.0.3\nWAN6_ADDRESSES=2001:db8::2\nINTERNAL_IPV6_PREFIXES=2001:db8:b::/64 2001:db8:a::/62\nDNS_SERVERS=::1 192.0.2.1\nTUN_OWNER=openkill\nIPV4_ENABLED=1\nIPV6_ENABLED=1\nPUBLIC_IPV6_HEALTH=failed\n", encoding="utf-8")
            b.write_text(common + "WAN4_ADDRESSES=10.0.0.3 10.0.0.2\nWAN6_ADDRESSES=2001:db8::2\nINTERNAL_IPV6_PREFIXES=2001:db8:a::/62 2001:db8:b::/64\nDNS_SERVERS=192.0.2.1 ::1\nTUN_OWNER=openkill\nIPV4_ENABLED=1\nIPV6_ENABLED=1\nPUBLIC_IPV6_HEALTH=ok\n", encoding="utf-8")
            run_helper("openkill_network_fingerprint", a, fa)
            run_helper("openkill_network_fingerprint", b, fb)
            self.assertEqual(fa.read_text(), fb.read_text())

    def test_pd_and_wan_changes_are_classified(self):
        with tempfile.TemporaryDirectory() as td:
            a, b = pathlib.Path(td) / "a", pathlib.Path(td) / "b"
            a.write_text("WAN4_L3_DEVICE=eth0\nWAN4_ADDRESSES=10.0.0.2\nWAN6_L3_DEVICE=eth0\nWAN6_ADDRESSES=2001:db8::2\nINTERNAL_IPV6_PREFIXES=2001:db8:a::/62\n", encoding="utf-8")
            b.write_text("WAN4_L3_DEVICE=eth0\nWAN4_ADDRESSES=10.0.0.2\nWAN6_L3_DEVICE=pppoe-wan\nWAN6_ADDRESSES=2001:db8::3\nINTERNAL_IPV6_PREFIXES=2001:db8:b::/62\n", encoding="utf-8")
            output = run_helper("openkill_classify_network_change", a, b).stdout
            self.assertIn("WAN6_CHANGED", output)
            self.assertIn("PD_CHANGED", output)

    def test_owner_modes_and_dual_owner_rejection(self):
        with tempfile.TemporaryDirectory() as td:
            good_openkill = pathlib.Path(td) / "openkill"
            good_mihomo = pathlib.Path(td) / "mihomo"
            bad = pathlib.Path(td) / "bad"
            good_openkill.write_text("TUN_OWNER=openkill\nMIHOMO_AUTO_ROUTE=0\nMIHOMO_AUTO_REDIRECT=0\n", encoding="utf-8")
            good_mihomo.write_text("TUN_OWNER=mihomo\nMIHOMO_AUTO_ROUTE=1\nMIHOMO_AUTO_REDIRECT=1\n", encoding="utf-8")
            bad.write_text("TUN_OWNER=openkill\nMIHOMO_AUTO_ROUTE=1\nMIHOMO_AUTO_REDIRECT=1\n", encoding="utf-8")
            run_helper("openkill_validate_owner_mode", good_openkill)
            run_helper("openkill_validate_owner_mode", good_mihomo)
            self.assertNotEqual(subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_validate_owner_mode "$1"', "model", str(bad)], capture_output=True).returncode, 0)

    def test_node_endpoint_diff_and_noop(self):
        with tempfile.TemporaryDirectory() as td:
            a, b = pathlib.Path(td) / "a", pathlib.Path(td) / "b"
            a.write_text("LOCALNETWORK6_PREFIXES=x\nNODE4_ENDPOINTS=192.0.2.1\nNODE6_ENDPOINTS=2001:db8::1\nTUN_OWNER=openkill\n", encoding="utf-8")
            b.write_text("LOCALNETWORK6_PREFIXES=x\nNODE4_ENDPOINTS=192.0.2.2\nNODE6_ENDPOINTS=2001:db8::2\nTUN_OWNER=openkill\n", encoding="utf-8")
            output = run_helper("openkill_desired_diff", a, b).stdout
            self.assertIn("NODE4_CHANGED", output)
            self.assertIn("NODE6_CHANGED", output)
            self.assertEqual(run_helper("openkill_desired_diff", a, a).stdout.strip(), "NO_ACTION")

    def test_single_flight_lock_and_pending_marker(self):
        with tempfile.TemporaryDirectory() as td:
            lock, pending = pathlib.Path(td) / "lock", pathlib.Path(td) / "pending"
            run_helper("openkill_reconcile_lock_acquire", lock)
            second = subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_reconcile_lock_acquire "$1"', "model", str(lock)])
            self.assertNotEqual(second.returncode, 0)
            run_helper("openkill_reconcile_request_pending", pending)
            self.assertEqual(pending.read_text().strip(), "1")
            run_helper("openkill_reconcile_lock_release", lock)


if __name__ == "__main__":
    unittest.main()
