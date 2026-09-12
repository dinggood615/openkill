#!/usr/bin/env python3
"""Pure tests for the Stage B network snapshot/desired-state boundary."""
import pathlib
import os
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_network.sh"
INIT = ROOT / "luci-app-openkill/root/etc/init.d/openkill"


def run_helper(action, *args):
    return subprocess.run(
        ["sh", "-c", f'. "{HELPER}"; {action} "$1" "$2"', "model", *map(str, args)],
        check=True, capture_output=True, text=True,
    )


def run_helper_env(action, *args, env=None, check=True):
    script = '. "$1"; ' + action + ' ' + ' '.join('"$%d"' % (i + 2) for i in range(len(args)))
    return subprocess.run(
        ["sh", "-c", script, "model", str(HELPER), *map(str, args)],
        check=check, capture_output=True, text=True, env=env or os.environ.copy(),
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
    def test_ipv6_cidr_helper_handles_compressed_and_non_boundary_prefixes(self):
        self.assertNotEqual(
            run_helper_env("openkill_ipv6_in_cidr", "2001:db8::2", "fdfe:dcba:9876::/64", check=False).returncode,
            0,
        )
        self.assertEqual(
            run_helper_env("openkill_ipv6_in_cidr", "fdfe:dcba:9876::2", "fdfe:dcba:9876::/64").returncode,
            0,
        )
        self.assertEqual(
            run_helper_env("openkill_ipv6_in_cidr", "2001:db8:1234::2", "2001:db8::/32").returncode,
            0,
        )

    def test_interface_roles_accept_uppercase_netifd_objects(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            fixture = td / "roles"
            fixture.write_text(
                "WAN4_INTERFACE=WAN\nWAN4_L3_DEVICE=pppoe-wan\n"
                "WAN6_INTERFACE=WAN6\nWAN6_L3_DEVICE=pppoe-wan\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["OPENKILL_INTERFACE_ROLE_FIXTURE"] = str(fixture)
            result = run_helper_env("openkill_resolve_interface_roles", td / "missing", td / "out", env=env)
            self.assertEqual(result.returncode, 0)
            self.assertEqual((td / "out").read_text().splitlines(), fixture.read_text().splitlines())

    def test_interface_roles_fall_back_to_custom_default_route_devices(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            records = td / "records"
            records.write_text("internet|pppoe-wan|eth0\nv6internet|pppoe-wan6|eth1\n", encoding="utf-8")
            out4, out6 = td / "out4", td / "out6"
            run_helper_env(
                "openkill_select_interface_role", records, "", "wan", "pppoe-wan", out4
            )
            run_helper_env(
                "openkill_select_interface_role", records, "", "wan6", "pppoe-wan6", out6
            )
            self.assertIn("DEVICE=pppoe-wan", out4.read_text())
            self.assertIn("INTERFACE=internet", out4.read_text())
            self.assertIn("DEVICE=pppoe-wan6", out6.read_text())
            self.assertIn("INTERFACE=v6internet", out6.read_text())

    def test_interface_roles_disambiguate_shared_l3_device_by_family(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            records = td / "records"
            records.write_text(
                "internet|pppoe-wan|eth0|1||pppoe\n"
                "v6internet|pppoe-wan|eth0||1|dhcpv6\n",
                encoding="utf-8",
            )
            out4, out6 = td / "out4", td / "out6"
            self.assertEqual(
                run_helper_env(
                    "openkill_select_interface_role", records, "", "wan", "pppoe-wan", out4, 4
                ).returncode,
                0,
            )
            self.assertEqual(
                run_helper_env(
                    "openkill_select_interface_role", records, "", "wan6", "pppoe-wan", out6, 6
                ).returncode,
                0,
            )
            self.assertIn("INTERFACE=internet", out4.read_text())
            self.assertIn("INTERFACE=v6internet", out6.read_text())

    def test_interface_role_resolver_consumes_one_dump_and_handles_uppercase_names(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            dump = td / "dump"; out = td / "roles"; fake = td / "bin"; fake.mkdir()
            dump.write_text("{\"interface\":[{\"interface\":\"WAN\",\"l3_device\":\"pppoe-wan\",\"device\":\"eth0\"},{\"interface\":\"WAN6\",\"l3_device\":\"pppoe-wan\",\"device\":\"eth0\"},{\"interface\":\"LAN\",\"l3_device\":\"br-lan\",\"device\":\"br-lan\"}]}\n", encoding="utf-8")
            (fake / "jsonfilter").write_text(
                r"""#!/bin/sh
expr=; file=
while [ "$#" -gt 0 ]; do case "$1" in -i) file="$2"; shift 2;; -e) expr="$2"; shift 2;; *) shift;; esac; done
case "$expr" in
  *@.interface\[0\].interface) echo WAN;; *@.interface\[0\].l3_device) echo pppoe-wan;; *@.interface\[0\].device) echo eth0;;
  *@.interface\[1\].interface) echo WAN6;; *@.interface\[1\].l3_device) echo pppoe-wan;; *@.interface\[1\].device) echo eth0;;
  *@.interface\[2\].interface) echo LAN;; *@.interface\[2\].l3_device) echo br-lan;; *@.interface\[2\].device) echo br-lan;;
esac
""", encoding="utf-8")
            (fake / "ip").write_text(
                """#!/bin/sh
case "$*" in *"-4 route"*) echo 'default via 192.0.2.1 dev pppoe-wan'; echo '192.168.1.0/24 dev br-lan';; *"-6 route"*) echo 'default from 2001:db8:1::/64 via fe80::1 dev pppoe-wan'; echo '2001:db8:2::/62 dev br-lan';; esac
""", encoding="utf-8")
            for name in ("jsonfilter", "ip"):
                (fake / name).chmod(0o755)
            env = os.environ.copy(); env["PATH"] = f"{fake}:/bin:/usr/bin"
            result = run_helper_env("openkill_resolve_interface_roles", dump, out, env=env)
            self.assertEqual(result.returncode, 0)
            self.assertIn("WAN4_INTERFACE=WAN", out.read_text())
            self.assertIn("WAN6_INTERFACE=WAN6", out.read_text())
            self.assertIn("WAN4_L3_DEVICE=pppoe-wan", out.read_text())
            self.assertIn("WAN6_L3_DEVICE=pppoe-wan", out.read_text())

    def test_snapshot_uses_uppercase_wan_roles_and_keeps_wan_prefix_host_only(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            dump, lua, snapshot, fake = td / "dump", td / "network.lua", td / "snapshot", td / "bin"
            fake.mkdir()
            dump.write_text(
                '{"interface":[{"interface":"WAN","l3_device":"pppoe-wan","device":"eth0"},'
                '{"interface":"WAN6","l3_device":"pppoe-wan","device":"eth0"},'
                '{"interface":"LAN","l3_device":"br-lan","device":"br-lan"}]}\n',
                encoding="utf-8",
            )
            lua.write_text("#!/bin/sh\nprintf '%s\\n' '2001:db8:2::/62'\n", encoding="utf-8")
            (fake / "jsonfilter").write_text(
                r"""#!/bin/sh
expr=
while [ "$#" -gt 0 ]; do case "$1" in -e) expr="$2"; shift 2;; *) shift;; esac; done
case "$expr" in
  *@.interface\[0\].interface) echo WAN;; *@.interface\[0\].l3_device) echo pppoe-wan;; *@.interface\[0\].device) echo eth0;;
  *@.interface\[1\].interface) echo WAN6;; *@.interface\[1\].l3_device) echo pppoe-wan;; *@.interface\[1\].device) echo eth0;;
  *@.interface\[2\].interface) echo LAN;; *@.interface\[2\].l3_device) echo br-lan;; *@.interface\[2\].device) echo br-lan;;
  *@.interface\[*\].dns-server\[*\]) echo 2001:4860:4860::8888;;
esac
""", encoding="utf-8")
            (fake / "ip").write_text(
                """#!/bin/sh
case "$*" in
  *"-4 route"*) echo 'default via 192.0.2.1 dev pppoe-wan';;
  *"-6 route"*) echo 'default from 2001:db8:1::/64 via fe80::1 dev pppoe-wan';;
  *"-4 addr show dev pppoe-wan"*) echo '    inet 192.0.2.2/24 scope global pppoe-wan';;
  *"-6 addr show dev pppoe-wan"*) echo '    inet6 2001:db8:1::123/64 scope global';;
esac
""", encoding="utf-8")
            for path in (lua, fake / "jsonfilter", fake / "ip"):
                path.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fake}:/bin:/usr/bin"
            env["OPENKILL_INTERFACE_DUMP_FILE"] = str(dump)
            env["OPENKILL_NETWORK_LUA"] = str(lua)
            result = run_helper_env("openkill_collect_network_snapshot", snapshot, env=env)
            self.assertEqual(result.returncode, 0)
            values = dict(line.split("=", 1) for line in snapshot.read_text().splitlines() if "=" in line)
            self.assertEqual(values["SNAPSHOT_NORMALIZED"], "1")
            self.assertEqual(values["WAN4_ADDRESSES"], "192.0.2.2")
            self.assertEqual(values["WAN4_L3_DEVICE"], "pppoe-wan")
            self.assertEqual(values["WAN6_L3_DEVICE"], "pppoe-wan")
            self.assertEqual(values["WAN6_HOST_ADDRESSES"], "2001:db8:1::123/128")
            self.assertEqual(values["INTERNAL_IPV6_PREFIXES"], "2001:db8:2::/62")
            self.assertEqual(values["LOCAL_IPV6_READY"], "1")

    def test_internal_prefix_discovery_consumes_netifd_assignments(self):
        text = (ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_get_network.lua").read_text(encoding="utf-8")
        self.assertIn('ipv6-prefix-assignment', text)
        self.assertIn('Internal interfaces must consume the assignment', text)

    def test_wan_ipv6_bypass_is_host_only(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            snapshot = td / "snapshot"
            snapshot.write_text("WAN6_ADDRESSES=2001:db8:1::123/64 2001:db8:1::123 2001:db8:1::124/64\n", encoding="utf-8")
            result = run_helper_env(
                "openkill_wan6_host_addresses", env={**os.environ, "OPENKILL_NETWORK_SNAPSHOT": str(snapshot)}
            )
            self.assertEqual(result.stdout.splitlines(), ["2001:db8:1::123/128", "2001:db8:1::124/128"])

    def test_normalize_list_preserves_addresses_dns_and_crlf(self):
        cases = [
            ("192.168.10.128/24", "192.168.10.128/24\n"),
            (" 192.168.10.128/24 ", "192.168.10.128/24\n"),
            ("\t192.168.10.128/24\t", "192.168.10.128/24\n"),
            (
                "192.168.10.129/24\r\n\r\n192.168.10.128/24\r\n",
                "192.168.10.128/24 192.168.10.129/24\n",
            ),
            (
                "fd15:4ba5:5a2b:1008:20c:29ff:fe07:4ffe/64\n"
                "fd15:4ba5:5a2b:1008::1/128\n",
                "fd15:4ba5:5a2b:1008:20c:29ff:fe07:4ffe/64 "
                "fd15:4ba5:5a2b:1008::1/128\n",
            ),
            ("192.168.10.2\n2001:4860:4860::8888\n192.168.10.2\n", "192.168.10.2 2001:4860:4860::8888\n"),
            ("\n\t\r\n", ""),
        ]
        for raw, expected in cases:
            with self.subTest(raw=repr(raw)):
                result = run_helper_env("openkill_normalize_list", raw)
                self.assertEqual(result.stdout, expected)

    def test_normalize_list_does_not_require_awk(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            fake = td / "bin"
            fake.mkdir()
            marker = td / "awk-called"
            (fake / "awk").write_text(
                f"#!/bin/sh\n: > {marker}\nexit 99\n", encoding="utf-8"
            )
            (fake / "awk").chmod(0o755)
            env = {**os.environ, "PATH": f"{fake}:/bin:/usr/bin"}
            result = run_helper_env(
                "openkill_normalize_list",
                " 192.168.10.128/24; fd15:4ba5::1/64 ",
                env=env,
            )
            self.assertEqual(result.stdout, "192.168.10.128/24 fd15:4ba5::1/64\n")
            self.assertFalse(marker.exists())

    def test_normalize_list_uses_safe_delimiter_translation_for_ipv6(self):
        source = HELPER.read_text(encoding="utf-8")
        self.assertIn("tr ';' '\\n'", source)
        self.assertNotIn("tr -s '[;[:space:]]'", source)
        result = run_helper_env(
            "openkill_normalize_list",
            "fd15:4ba5:5a2b:1008:20c:29ff:fe07:4ffe/64;"
            "2001:db8::1/128;fd15:4ba5:5a2b:1008:20c:29ff:fe07:4ffe/64",
        )
        self.assertEqual(
            result.stdout,
            "2001:db8::1/128 fd15:4ba5:5a2b:1008:20c:29ff:fe07:4ffe/64\n",
        )

    def test_normalize_text_lines_preserves_internal_route_text_spaces(self):
        result = run_helper_env(
            "openkill_normalize_text_lines",
            "default from fd15:4ba5:5a2b:1008::/64 via fe80::1 dev eth1;"
            "fd15:4ba5:5a2b:1008::/64 dev eth1",
        )
        self.assertEqual(
            result.stdout,
            "default from fd15:4ba5:5a2b:1008::/64 via fe80::1 dev eth1 "
            "fd15:4ba5:5a2b:1008::/64 dev eth1\n",
        )

    def test_normalize_list_splits_whitespace_separated_tokens_without_losing_ipv6(self):
        result = run_helper_env(
            "openkill_normalize_list",
            " 192.168.10.2\t2606:4700:4700::1111\n"
            "fd15:4ba5:5a2b:1008:20c:29ff:fe07:4ffe/64 192.168.10.2",
        )
        self.assertEqual(
            result.stdout,
            "192.168.10.2 2606:4700:4700::1111 "
            "fd15:4ba5:5a2b:1008:20c:29ff:fe07:4ffe/64\n",
        )

    def test_desired_localnetwork6_keeps_wan_as_hosts_and_lan_as_prefixes(self):
        state = build("""SNAPSHOT_VERSION=1
LOCAL_IPV6_READY=1
WAN6_HOST_ADDRESSES=2001:db8:1::123/128
INTERNAL_IPV6_PREFIXES=2001:db8:2::/62
""")
        self.assertEqual(state["LOCALNETWORK6_PREFIXES"].split(), ["2001:db8:1::123/128", "2001:db8:2::/62"])
        self.assertNotIn("2001:db8:1::/64", state["LOCALNETWORK6_PREFIXES"])

    def test_invalid_ipv6_literals_are_not_rendered(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            yaml_file, v4, v6, domains = [td / name for name in ("config.yaml", "v4", "v6", "domains")]
            yaml_file.write_text("proxies:\n  - name: bad-v6\n    server: 2001:::1\n  - name: good-v6\n    server: 2001:db8::2\n  - name: bad-v4\n    server: 999.999.1.1\n", encoding="utf-8")
            subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_extract_node_endpoints "$1" "$2" "$3" "$4"', "model", str(yaml_file), str(v4), str(v6), str(domains)], check=True)
            self.assertEqual(v4.read_text(), "")
            self.assertEqual(v6.read_text().strip(), "2001:db8::2")
            self.assertEqual(domains.read_text(), "")

    def test_nft_string_quote_and_node_classifier_rule(self):
        quoted = run_helper_env("openkill_nft_string_quote", 'OpenKill "node" \\ test')
        self.assertEqual(quoted.stdout.strip(), '"OpenKill \\"node\\" \\\\ test"')
        rendered = run_helper_env("openkill_render_classifier_rule", 6, "openkill_mangle_v6", "OpenKill node underlay")
        self.assertIn('ip6 daddr @openkill_node6 counter return comment "OpenKill node underlay"', rendered.stdout)

    def test_native_resolver_works_without_getent_and_rejects_fake_ip(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            domains, v4, v6 = td / "domains", td / "v4", td / "v6"
            domains.write_text("node.example.test\n", encoding="utf-8")
            v4.write_text("\n", encoding="utf-8"); v6.write_text("\n", encoding="utf-8")
            fake = td / "bin"; fake.mkdir()
            (fake / "timeout").write_text("#!/bin/sh\nshift; exec \"$@\"\n", encoding="utf-8")
            (fake / "nslookup").write_text(
                "#!/bin/sh\nprintf '%s\\n' 'Server: 192.0.2.53' 'Address 1: 192.0.2.53' 'Name: node.example.test' 'Address 1: 192.0.2.2' 'Address 2: 2001:db8::2'\n",
                encoding="utf-8",
            )
            for name in ("timeout", "nslookup"):
                (fake / name).chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fake}:/bin:/usr/bin"
            env["OPENKILL_NODE_DNS_SERVERS"] = "192.0.2.53"
            env["OPENKILL_FAKEIP_RANGE4"] = "198.18.0.0/15"
            env["OPENKILL_FAKEIP_RANGE6"] = "fdfe:dcba:9876::/64"
            run_helper_env("openkill_resolve_node_domains", domains, v4, v6, env=env)
            self.assertEqual(v4.read_text().strip(), "192.0.2.2")
            self.assertEqual(v6.read_text().strip(), "2001:db8::2")

    def test_resolver_fake_ip_results_are_not_node_endpoints(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            domains, v4, v6 = td / "domains", td / "v4", td / "v6"
            domains.write_text("node.example.test\n", encoding="utf-8")
            v4.write_text("\n", encoding="utf-8"); v6.write_text("\n", encoding="utf-8")
            fake = td / "bin"; fake.mkdir()
            (fake / "timeout").write_text("#!/bin/sh\nshift; exec \"$@\"\n", encoding="utf-8")
            (fake / "nslookup").write_text(
                "#!/bin/sh\nprintf '%s\\n' 'Name: node.example.test' 'Address 1: 198.18.1.2' 'Address 2: fdfe:dcba:9876::2'\n",
                encoding="utf-8",
            )
            for name in ("timeout", "nslookup"):
                (fake / name).chmod(0o755)
            env = os.environ.copy(); env["PATH"] = f"{fake}:/bin:/usr/bin"; env["OPENKILL_NODE_DNS_SERVERS"] = "192.0.2.53"
            result = run_helper_env("openkill_resolve_node_domains", domains, v4, v6, env=env, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(v4.read_text(), "\n"); self.assertEqual(v6.read_text(), "\n")

    def test_resolver_filters_configured_uppercase_fake_ipv6_range(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            domains, v4, v6 = td / "domains", td / "v4", td / "v6"
            domains.write_text("node.example.test\n", encoding="utf-8")
            v4.write_text("\n", encoding="utf-8"); v6.write_text("\n", encoding="utf-8")
            fake = td / "bin"; fake.mkdir()
            (fake / "timeout").write_text("#!/bin/sh\nshift; exec \"$@\"\n", encoding="utf-8")
            (fake / "nslookup").write_text(
                "#!/bin/sh\nprintf '%s\\n' 'Name: node.example.test' 'Address 1: FD00:ABCD::2'\n", encoding="utf-8")
            for name in ("timeout", "nslookup"):
                (fake / name).chmod(0o755)
            env = {**os.environ, "PATH": f"{fake}:/bin:/usr/bin", "OPENKILL_NODE_DNS_SERVERS": "192.0.2.53", "OPENKILL_FAKEIP_RANGE6": "FD00:ABCD::/64"}
            result = run_helper_env("openkill_resolve_node_domains", domains, v4, v6, env=env, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(v6.read_text(), "\n")

    def test_resolver_filters_ipv6_fake_range_by_cidr_width(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            domains, v4, v6 = td / "domains", td / "v4", td / "v6"
            domains.write_text("node.example.test\n", encoding="utf-8")
            v4.write_text("\n", encoding="utf-8"); v6.write_text("\n", encoding="utf-8")
            fake = td / "bin"; fake.mkdir()
            (fake / "timeout").write_text("#!/bin/sh\nshift; exec \"$@\"\n", encoding="utf-8")
            (fake / "nslookup").write_text(
                "#!/bin/sh\nprintf '%s\\n' 'Name: node.example.test' 'Address 1: 2001:db8:1234::2'\n",
                encoding="utf-8")
            for name in ("timeout", "nslookup"):
                (fake / name).chmod(0o755)
            env = {**os.environ, "PATH": f"{fake}:/bin:/usr/bin", "OPENKILL_NODE_DNS_SERVERS": "192.0.2.53"}
            result = run_helper_env(
                "openkill_resolve_node_domains", domains, v4, v6, env={**env, "OPENKILL_FAKEIP_RANGE6": "2001:db8::/32"}, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(v6.read_text(), "\n")

    def test_resolution_failure_preserves_old_and_first_start_keeps_static_literals(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            static4, static6 = td / "static4", td / "static6"
            domains, applied4, applied6 = td / "domains", td / "applied4", td / "applied6"
            static4.write_text("192.0.2.10\n", encoding="utf-8")
            static6.write_text("2001:db8::10\n", encoding="utf-8")
            domains.write_text("node.example.test\n", encoding="utf-8")
            fake = td / "bin"; fake.mkdir()
            (fake / "timeout").write_text("#!/bin/sh\nexit 124\n", encoding="utf-8")
            (fake / "nslookup").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            for path in (fake / "timeout", fake / "nslookup"):
                path.chmod(0o755)
            env = {**os.environ, "PATH": f"{fake}:/bin:/usr/bin", "OPENKILL_NODE_DNS_SERVERS": "192.0.2.53"}
            self.assertEqual(
                run_helper_env("openkill_refresh_node_endpoints", static4, static6, domains, applied4, applied6, env=env).returncode,
                0,
            )
            self.assertEqual(applied4.read_text(), static4.read_text())
            self.assertEqual(applied6.read_text(), static6.read_text())
            applied4.write_text("192.0.2.20\n", encoding="utf-8")
            applied6.write_text("2001:db8::20\n", encoding="utf-8")
            failed = run_helper_env("openkill_refresh_node_endpoints", static4, static6, domains, applied4, applied6, env=env, check=False)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(applied4.read_text(), "192.0.2.20\n")
            self.assertEqual(applied6.read_text(), "2001:db8::20\n")

    def test_domain_node_noop_probe_refreshes_without_mutating_applied_set(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            static4, static6 = td / "static4", td / "static6"
            domains, applied4, applied6 = td / "domains", td / "applied4", td / "applied6"
            static4.write_text("192.0.2.10\n", encoding="utf-8")
            static6.write_text("\n", encoding="utf-8")
            domains.write_text("node.example.test\n", encoding="utf-8")
            applied4.write_text("192.0.2.10\n", encoding="utf-8")
            applied6.write_text("\n", encoding="utf-8")
            fake = td / "bin"; fake.mkdir()
            (fake / "timeout").write_text("#!/bin/sh\nshift; exec \"$@\"\n", encoding="utf-8")
            (fake / "nslookup").write_text(
                "#!/bin/sh\nprintf '%s\\n' 'Name: node.example.test' 'Address 1: 192.0.2.10'\n",
                encoding="utf-8",
            )
            for path in (fake / "timeout", fake / "nslookup"):
                path.chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{fake}:/bin:/usr/bin",
                "OPENKILL_NODE_DNS_SERVERS": "192.0.2.53",
            }
            result = run_helper_env(
                "openkill_node_underlay_ready_for_noop",
                domains,
                static4,
                static6,
                applied4,
                applied6,
                env=env,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(applied4.read_text(), "192.0.2.10\n")
            self.assertEqual(applied6.read_text(), "\n")

            (fake / "nslookup").write_text(
                "#!/bin/sh\nprintf '%s\\n' 'Name: node.example.test' 'Address 1: 192.0.2.11'\n",
                encoding="utf-8",
            )
            self.assertNotEqual(
                run_helper_env(
                    "openkill_node_underlay_ready_for_noop",
                    domains,
                    static4,
                    static6,
                    applied4,
                    applied6,
                    env=env,
                    check=False,
                ).returncode,
                0,
            )
            self.assertEqual(applied4.read_text(), "192.0.2.10\n")

    def test_network_applied_state_enables_noop_only_when_runtime_is_healthy(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            desired, applied, config, config_applied, fingerprint, fingerprint_applied = [td / n for n in ("desired", "applied", "config", "config.applied", "fingerprint", "fingerprint.applied")]
            desired.write_text("LOCALNETWORK6_PREFIXES=fd00::/8\n", encoding="utf-8")
            config.write_text("mode=redir-host\n", encoding="utf-8")
            run_helper_env("openkill_commit_applied_network_state", desired, applied, config, config_applied)
            fingerprint.write_text("WAN6_L3_DEVICE=pppoe-wan\nWAN6_ADDRESSES=2001:db8::1\n", encoding="utf-8")
            fingerprint_applied.write_text(fingerprint.read_text(), encoding="utf-8")
            env = {**os.environ, "OPENKILL_RUNTIME_HEALTHY": "1"}
            result = run_helper_env("openkill_network_noop_ready", desired, applied, "", config, config_applied, fingerprint, fingerprint_applied, env=env)
            self.assertEqual(result.stdout.strip(), "NO_ACTION")
            fingerprint.write_text("WAN6_L3_DEVICE=pppoe-wan\nWAN6_ADDRESSES=2001:db8::2\n", encoding="utf-8")
            self.assertNotEqual(run_helper_env("openkill_network_noop_ready", desired, applied, "", config, config_applied, fingerprint, fingerprint_applied, env=env, check=False).returncode, 0)
            config.write_text("mode=fake-ip\n", encoding="utf-8")
            self.assertNotEqual(run_helper_env("openkill_network_noop_ready", desired, applied, "", config, config_applied, env=env, check=False).returncode, 0)

    def test_network_snapshot_commit_is_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            source, target = td / "source", td / "target"
            source.write_text("WAN6_L3_DEVICE=pppoe-wan\nLOCAL_IPV6_READY=1\n", encoding="utf-8")
            run_helper_env("openkill_commit_network_snapshot", source, target)
            self.assertEqual(target.read_text(), source.read_text())
            self.assertFalse((td / "target.tmp").exists())

    def test_readiness_commits_reload_snapshot_before_fingerprint(self):
        text = INIT.read_text(encoding="utf-8")
        snapshot_commit = text.index("openkill_commit_network_snapshot")
        fingerprint = text.index("openkill_network_fingerprint", snapshot_commit)
        self.assertLess(snapshot_commit, fingerprint)
        self.assertIn("/tmp/openkill-network.reload.*", text)

    def test_reload_noop_gate_precedes_firewall_apply(self):
        text = INIT.read_text(encoding="utf-8")
        noop = text.index("openkill_network_noop_ready")
        first_apply = text.index("revert_firewall keep-include", noop)
        self.assertLess(noop, first_apply)
        self.assertIn("openkill_node_underlay_ready_for_noop", text)
        self.assertIn('"$OPENKILL_NETWORK_FINGERPRINT" /tmp/openkill-network.fingerprint', text)
        self.assertIn('Network state unchanged and runtime healthy; skipping firewall/DNS reapply.', text)

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
    server: "[2001:db8::10]"
  - name: domain
    server: node.example.test
""", encoding="utf-8")
            subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_extract_node_endpoints "$1" "$2" "$3"', "model", str(yaml_file), str(v4), str(v6)], check=True)
            self.assertEqual(v4.read_text().strip(), "192.0.2.10")
            self.assertEqual(v6.read_text().strip(), "2001:db8::10")
            self.assertNotIn("node.example.test", v4.read_text() + v6.read_text())

    def test_domain_resolution_refreshes_both_families_and_failure_keeps_old(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            domains, static4, static6 = td / "domains", td / "static4", td / "static6"
            applied4, applied6 = td / "applied4", td / "applied6"
            domains.write_text("node.example.test\n", encoding="utf-8")
            static4.write_text("\n", encoding="utf-8")
            static6.write_text("\n", encoding="utf-8")
            applied4.write_text("192.0.2.1\n", encoding="utf-8")
            applied6.write_text("2001:db8::1\n", encoding="utf-8")
            fake = td / "bin"
            fake.mkdir()
            (fake / "getent").write_text("#!/bin/sh\ncase \"$1\" in ahostsv4) echo '192.0.2.2 STREAM node';; ahostsv6) echo '2001:db8::2 STREAM node';; esac\n", encoding="utf-8")
            (fake / "timeout").write_text("#!/bin/sh\nshift; exec \"$@\"\n", encoding="utf-8")
            for name in ("getent", "timeout"):
                (fake / name).chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fake}:{env['PATH']}"
            subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_refresh_node_endpoints "$1" "$2" "$3" "$4" "$5"', "model", str(static4), str(static6), str(domains), str(applied4), str(applied6)], check=True, env=env)
            self.assertEqual(applied4.read_text().strip(), "192.0.2.2")
            self.assertEqual(applied6.read_text().strip(), "2001:db8::2")
            (fake / "timeout").write_text("#!/bin/sh\nexit 124\n", encoding="utf-8")
            (fake / "timeout").chmod(0o755)
            self.assertNotEqual(subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_refresh_node_endpoints "$1" "$2" "$3" "$4" "$5"', "model", str(static4), str(static6), str(domains), str(applied4), str(applied6)], env=env).returncode, 0)
            self.assertEqual(applied4.read_text().strip(), "192.0.2.2")

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

    def test_owner_runtime_apply_orders_steps_and_keeps_state_on_failure(self):
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            applied, generation, trace = td / "owner", td / "generation", td / "trace"
            applied.write_text("OWNER=openkill\n", encoding="utf-8")
            generation.write_text("g1\n", encoding="utf-8")
            env = os.environ.copy(); env["OPENKILL_OWNER_DRY_RUN"] = "1"; env["OPENKILL_OWNER_TRACE"] = str(trace)
            subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_apply_owner_transition mihomo "$1" "$2" g1 1', "model", str(applied), str(generation)], check=True, env=env)
            steps = trace.read_text().splitlines()
            self.assertEqual(steps, ["DISABLE_CLASSIFIER", "REMOVE_OPENKILL_RUNTIME", "ENABLE_MIHOMO_OWNER"])
            self.assertEqual(applied.read_text().strip(), "OWNER=mihomo")
            applied.write_text("OWNER=openkill\n", encoding="utf-8")
            env["OPENKILL_OWNER_FAIL_STEP"] = "ENABLE_MIHOMO_OWNER"
            failed = subprocess.run(["sh", "-c", f'. "{HELPER}"; openkill_apply_owner_transition mihomo "$1" "$2" g1 1', "model", str(applied), str(generation)], env=env)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(applied.read_text().strip(), "OWNER=openkill")

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

    def test_node_sets_are_installed_before_normal_proxy_classification(self):
        text = INIT.read_text(encoding="utf-8")
        self.assertIn("apply_node_endpoint_sets", text)
        self.assertIn("@openkill_node4", text)
        self.assertIn("@openkill_node6", text)
        self.assertIn('comment "OpenKill node underlay"', text)
        self.assertIn("skgid == 65534", text)
        for chain in ("openkill", "openkill_mangle", "openkill_output", "openkill_mangle_output",
                      "openkill_v6", "openkill_mangle_v6", "openkill_output_v6", "openkill_mangle_output_v6"):
            self.assertIn(chain, text)
        self.assertIn('nft "$node_rule"', text)

    def test_owner_runtime_cleanup_is_private_to_openkill_state(self):
        text = HELPER.read_text(encoding="utf-8")
        self.assertIn('ip rule del fwmark "$OPENKILL_FWMARK" table 354 pref "$OPENKILL_RULE_PREF"', text)
        self.assertIn('ip -6 rule del fwmark "$OPENKILL_FWMARK" table 354 pref "$OPENKILL_RULE_PREF"', text)
        self.assertIn("ip route del default dev utun table 354", text)
        self.assertNotIn("ip route flush table main", text)

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
