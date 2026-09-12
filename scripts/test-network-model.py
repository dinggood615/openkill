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

    def test_node_literals_are_split_by_family_and_stale_values_can_be_removed(self):
        with tempfile.TemporaryDirectory() as td:
            yaml_file, v4, v6 = [pathlib.Path(td) / name for name in ("config.yaml", "v4", "v6")]
            yaml_file.write_text("""proxies:
  - name: v4
    server: 192.0.2.10
  - name: v6
    server: 2001:db8::10
  - name: domain
    server: node.example.test
""", encoding="utf-8")
            subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_extract_node_endpoints "$1" "$2" "$3"', "model", str(yaml_file), str(v4), str(v6)], check=True)
            self.assertEqual(v4.read_text().strip(), "192.0.2.10")
            self.assertEqual(v6.read_text().strip(), "2001:db8::10")
            self.assertNotIn("node.example.test", v4.read_text() + v6.read_text())

    def test_applied_state_is_not_updated_when_component_apply_fails(self):
        with tempfile.TemporaryDirectory() as td:
            desired, applied = pathlib.Path(td) / "desired", pathlib.Path(td) / "applied"
            desired.write_text("LOCAL6=A B C\n", encoding="utf-8")
            applied.write_text("LOCAL6=A B\n", encoding="utf-8")
            failed = subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_apply_component_state LOCAL6 "$1" "$2" fail', "model", str(desired), str(applied)], capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(applied.read_text(), "LOCAL6=A B\n")
            subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_apply_component_state LOCAL6 "$1" "$2" ok', "model", str(desired), str(applied)], check=True)
            self.assertEqual(applied.read_text(), desired.read_text())

    def test_owner_transition_failure_keeps_previous_owner(self):
        with tempfile.TemporaryDirectory() as td:
            applied, result = pathlib.Path(td) / "applied", pathlib.Path(td) / "result"
            applied.write_text("OWNER=openkill\n", encoding="utf-8")
            failed = subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_owner_transition mihomo "$1" "$2" fail', "model", str(applied), str(result)], capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(applied.read_text(), "OWNER=openkill\n")

    def test_event_storm_is_bounded_and_pending_is_consumed(self):
        with tempfile.TemporaryDirectory() as td:
            state = pathlib.Path(td)
            for reason in ("wan", "wan6", "pd", "fw4", "watchdog"):
                subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_request_network_reconcile "$1" "$2"', "model", str(state), reason], check=True)
            subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_reconcile_worker_guard "$1" 3', "model", str(state)], check=True)
            self.assertEqual((state / "passes").read_text().strip(), "1")
            self.assertFalse((state / "pending").exists())

    def test_node_sets_are_family_specific_and_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            v4, v6, out = [pathlib.Path(td) / name for name in ("v4", "v6", "sets.nft")]
            v4.write_text("192.0.2.10\n", encoding="utf-8")
            v6.write_text("2001:db8::10\n", encoding="utf-8")
            subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_render_node_sets "$1" "$2" "$3"', "model", str(v4), str(v6), str(out)], check=True)
            text = out.read_text()
            self.assertIn("openkill_node4", text)
            self.assertIn("openkill_node6", text)
            self.assertIn("192.0.2.10", text)
            self.assertIn("2001:db8::10", text)

    def test_owner_actions_have_no_dual_owner_activation(self):
        openkill = subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_owner_actions openkill'], capture_output=True, text=True, check=True).stdout
        mihomo = subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_owner_actions mihomo'], capture_output=True, text=True, check=True).stdout
        self.assertLess(openkill.index("REMOVE_MIHOMO_AUTO_ROUTE"), openkill.index("ACTIVATE_CLASSIFIER"))
        self.assertLess(mihomo.index("DEACTIVATE_CLASSIFIER"), mihomo.index("ENABLE_MIHOMO_AUTO_ROUTE"))

    def test_runtime_divergence_requests_reapply_without_network_change(self):
        with tempfile.TemporaryDirectory() as td:
            desired, runtime = pathlib.Path(td) / "desired", pathlib.Path(td) / "runtime"
            desired.write_text("TUN_OWNER=openkill\nLOCALNETWORK6_PREFIXES=A\n", encoding="utf-8")
            runtime.write_text("NFT_CHAIN_PRESENT=0\n", encoding="utf-8")
            out = subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_runtime_integrity_action "$1" "$2"', "model", str(desired), str(runtime)], check=True, capture_output=True, text=True).stdout.strip()
            self.assertEqual(out, "REAPPLY_NFT")

    def test_enable_zero_blocks_every_event_source(self):
        with tempfile.TemporaryDirectory() as td:
            snapshot = pathlib.Path(td) / "snapshot"
            snapshot.write_text("ENABLE=0\n", encoding="utf-8")
            for reason in ("fw4", "wan", "wan6", "pd", "watchdog", "manual"):
                self.assertNotEqual(subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_event_allowed "$1"', "model", str(snapshot)]).returncode, 0, reason)

    def test_generation_invalidates_old_worker(self):
        with tempfile.TemporaryDirectory() as td:
            generation = pathlib.Path(td) / "generation"
            first = subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_generation_start "$1"', "model", str(generation)], check=True, capture_output=True, text=True).stdout.strip()
            second = subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_generation_start "$1"', "model", str(generation)], check=True, capture_output=True, text=True).stdout.strip()
            self.assertNotEqual(first, second)
            self.assertNotEqual(subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_generation_is_current "$1" "$2"', "model", str(generation), first]).returncode, 0)
            self.assertEqual(subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_generation_is_current "$1" "$2"', "model", str(generation), second]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
