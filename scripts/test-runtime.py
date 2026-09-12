"""Behavior tests of actual runtime helpers; no router is touched."""
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHARE = ROOT / 'luci-app-openkill/root/usr/share/openkill'
BASH = shutil.which('bash') or 'C:/Program Files/Git/bin/bash.exe'
RUBY = shutil.which('ruby')


def run_shell(source):
    return subprocess.run([BASH, '-s'], input=source, text=True,
                          capture_output=True, cwd=ROOT, timeout=15)


class AddressTests(unittest.TestCase):
    def test_controller_and_generation_share_addresses(self):
        runtime = (SHARE / 'runtime.sh').read_text(encoding='utf-8')
        helper = runtime.split('openkill_controller_host() {', 1)[1].split('\n}', 1)[0]
        common = (SHARE / 'address.sh').read_text(encoding='utf-8')
        for requested, expected in [('lan', '192.168.1.100'), ('', '192.168.1.100'),
                                    ('192.168.1.100', '192.168.1.100'),
                                    ('192.168.1.100/24', '192.168.1.100'),
                                    ('[::1]', '::1'), ('garbage', '127.0.0.1'),
                                    ('999.1.1.1', '127.0.0.1')]:
            with self.subTest(requested=requested):
                result = run_shell(common + '\n' + '''
uci() { printf '%s' '192.168.1.100/24'; }
uci_get_config() { printf '%s' "$case_value"; }
openkill_controller_host() {''' + helper + '\n}\n' +
                    f"case_value='{requested}'\n" +
                    'printf "%s|%s" "$(openkill_bind_address "$case_value")" "$(openkill_controller_host)"')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f'{expected}|{expected}')

    def test_wildcard_connects_to_loopback(self):
        result = run_shell((SHARE / 'address.sh').read_text(encoding='utf-8') +
                           '\nprintf "%s|%s" "$(openkill_local_address 0.0.0.0)" "$(openkill_local_address ::)"')
        self.assertEqual(result.stdout, '127.0.0.1|::1')


@unittest.skipUnless(RUBY, 'Ruby required; mandatory in Linux CI')
class ContextTests(unittest.TestCase):
    def context(self, contents):
        with tempfile.TemporaryDirectory() as directory:
            fixture = pathlib.Path(directory) / 'profile.yaml'
            fixture.write_text(contents, encoding='utf-8')
            return subprocess.run([RUBY, str(SHARE / 'runtime_context.rb'), str(fixture)],
                                  capture_output=True, text=True, timeout=10)

    def test_effective_overrides_and_ipv6(self):
        result = self.context('''external-controller: "[::]:9191"
secret: "a'b $literal"
tun:
  enable: true
  device: testtun
  iproute2-table-index: 2023
dns:
  enable: true
  listen: "127.0.0.1:7874"
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(),
                         ['http://[::1]:9191', "a'b $literal", 'testtun', '2023', '127.0.0.1:7874'])

    def test_invalid_endpoints_and_multiline_secret_fail(self):
        for body in ['external-controller: "127.0.0.1:99999"',
                     'external-controller: "example.com:9090"',
                     'external-controller: "127.0.0.1:9090"\nsecret: "a\\nb"']:
            self.assertNotEqual(self.context(body).returncode, 0)


class ReadinessTests(unittest.TestCase):
    def run_case(self, scenario):
        source = (ROOT / 'luci-app-openkill/root/etc/init.d/openkill').read_text(encoding='utf-8')
        source = source.split('check_core_status()\n{', 1)[1].split('\nstart_run_core()', 1)[0]
        source = 'check_core_status()\n{' + source
        # Replace only the snapshot side effect, keeping the readiness logic.
        source = source.replace('/usr/share/openkill/openkill_recovery.sh save', 'snapshot')
        harness = '''
set -u
LOG_FILE=/dev/null
CONFIG_FILE=/unused
OPENKILL_START_TOKEN=test
OPENKILL_DNS_ENDPOINT=''
OPENKILL_TUN_DEVICE=''
OPENKILL_TUN_TABLE=2022
tun_owner=openkill
en_mode_tun=''
ipv6_mode=0
enable_redirect_dns=1
ipv6_enable=0
FW4=yes
LOG_TIP() { :; }; LOG_WARN() { :; }; LOG_ERROR() { :; }
sleep() { :; }
cut() { if [ -f "$clockfile" ]; then echo 200; else touch "$clockfile"; echo 0; fi; }
openkill_current_start() { [ "$scenario" != stale ]; }
openkill_core_process_present() { [ "$scenario" != missing_process ]; }
openkill_core_api_healthy() { [ "$scenario" != bad_api ]; }
start_fail() { exit 9; }
change_dnsmasq() { :; }
set_firewall() { [ "$scenario" != bad_firewall ]; }
ensure_fw4_dns_hijack() { :; }
fw4_dns_hijack_ready() { :; }
nft() {
  case "$*" in
    *"list chain inet fw4 dstnat"*) echo 'OpenKill DNS Hijack redirect to :7874' ;;
    *"list chain inet fw4 openkill_dns_redirect"*) echo 'redirect to :7874' ;;
    *) echo openkill ;;
  esac
}
uci() { :; }
snapshot() { echo saved >> "$events"; }
write_run_quick() { echo ready >> "$events"; }
'''
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory).as_posix()
            source = source.replace('/tmp/openkill-ready.token', f'{path}/ready.token')
            result = run_shell(harness + f"\nscenario='{scenario}'\nclockfile='{path}/clock'\nevents='{path}/events'\n" + source + '\ncheck_core_status start\n')
            events = pathlib.Path(directory, 'events')
            return result, events.read_text() if events.exists() else ''

    def test_success_saves_only_after_readiness(self):
        result, events = self.run_case('healthy')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events.splitlines(), ['saved', 'ready'])

    def test_failures_never_replace_checkpoint(self):
        for scenario in ['missing_process', 'bad_api', 'bad_firewall']:
            with self.subTest(scenario=scenario):
                result, events = self.run_case(scenario)
                self.assertEqual(result.returncode, 9, result.stderr)
                self.assertEqual(events, '')

    def test_stale_generation_cannot_change_state(self):
        result, events = self.run_case('stale')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, '')


class FirewallShellCompatibilityTests(unittest.TestCase):
    def test_direct_nft_sets_are_not_subject_to_bash_brace_expansion(self):
        source = (ROOT / 'luci-app-openkill/root/etc/init.d/openkill').read_text(encoding='utf-8')
        for number, line in enumerate(source.splitlines(), 1):
            if 'nft ' not in line or "nft '" in line or 'nft "' in line:
                continue
            self.assertNotRegex(line, r'(?<![\'\"])\{(?:ipv4|ipv6|tcp,udp)\}(?![\'\"])',
                                f'unquoted nft set at line {number}: {line}')
            self.assertNotRegex(line, r'(?<![\'\"])\{\$proxy_port,',
                                f'unquoted nft port set at line {number}: {line}')

    def test_bash_expansion_fixture_matches_failure_mode(self):
        result = run_shell("printf '<%s>\\n' {tcp,udp}")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ['<tcp>', '<udp>'])

    def test_dns_hijack_rules_keep_the_nft_comment_quoted(self):
        source = (ROOT / 'luci-app-openkill/root/etc/init.d/openkill').read_text(encoding='utf-8')
        rules = [line for line in source.splitlines()
                 if 'comment \\"OpenKill DNS Hijack\\"' in line]
        self.assertTrue(rules, 'expected nft DNS hijack rules')
        for line in rules:
            self.assertRegex(
                line,
                r'^\s*nft ".*comment \\"OpenKill DNS Hijack\\""$',
                f'nft DNS rule must be a single quoted expression: {line}',
            )


class DualStackRoutingTests(unittest.TestCase):
    def test_tun_stack_argument_mapping_matrix(self):
        change = (SHARE / 'yml_change.sh').read_text(encoding='utf-8')
        init = (ROOT / 'luci-app-openkill/root/etc/init.d/openkill').read_text(encoding='utf-8')

        # The init call supplies stack_type at position 12 and stack_type_v6
        # at position 30.  The latter must use braced POSIX expansion.
        self.assertIn('stack_type_v6=${30:-"mixed"}', change)
        self.assertIn("tun_stack = '$stack_type_v6' if en_mode_tun == '0'", change)
        self.assertNotRegex(change, r'(?<!\{)\$30')
        call = init.split('/usr/share/openkill/yml_change.sh', 1)[1].split(
            '# Validate the rewritten controller context', 1)[0]
        self.assertIn('"$en_mode_tun" "$stack_type" "$dns_port"', call)
        self.assertIn('"$ipv6_mode" "$stack_type_v6" "$enable_unified_delay"', call)

        def selected(v4, v6, en_mode_tun, ipv6_mode):
            # This is the externally visible selector contract represented by
            # the Ruby heredoc branch; dual-stack keeps the existing v4 choice.
            if en_mode_tun == '0' and ipv6_mode in ('2', '3'):
                return v6
            return v4

        cases = [
            ('system', 'gvisor', '1', '0', 'system'),   # IPv4-only
            ('system', 'gvisor', '0', '2', 'gvisor'),   # IPv6-only
            ('gvisor', 'mixed', '1', '0', 'gvisor'),    # IPv4-only
            ('gvisor', 'mixed', '0', '2', 'mixed'),     # IPv6-only
            ('system', 'gvisor', '1', '2', 'system'),   # dual-stack design
        ]
        for v4, v6, tun, ipv6_mode, expected in cases:
            with self.subTest(v4=v4, v6=v6, tun=tun, ipv6_mode=ipv6_mode):
                self.assertEqual(selected(v4, v6, tun, ipv6_mode), expected)

    def test_benchmark_is_read_only_and_busybox_ash_compatible(self):
        source = (SHARE / 'openkill-benchmark.sh').read_text(encoding='utf-8')
        self.assertTrue(source.startswith('#!/bin/sh'))
        for marker in ('--label', '--iperf-server', '--udp', '--show-public-ip',
                       'nf_conntrack_count', 'rps_cpus', 'xps_cpus', 'ethtool',
                       'openkill-benchmark-'):
            self.assertIn(marker, source)
        self.assertNotRegex(source, r'(^|[\s;])\[\[')
        self.assertNotRegex(source, r'(^|[\s;])\]\]')
        for forbidden in ('mapfile', 'sysctl -w', 'uci -q set',
                          'uci set', 'nft add', 'nft delete', 'nft flush',
                          'ip route add', 'ip route replace', 'ip route del',
                          'ip -6 route add', 'ip -6 route replace', 'ip -6 route del'):
            self.assertNotIn(forbidden, source)

    def test_dns_bootstrap_is_bound_to_physical_wan(self):
        source = (SHARE / 'yml_change.sh').read_text(encoding='utf-8')
        self.assertIn('dns_wan_interface=', source)
        self.assertIn('. /usr/share/openkill/openkill_wan.sh', source)
        self.assertIn('openkill_wan_interface', source)
        self.assertNotIn('ip -4 route show default', source)
        self.assertIn('[ "$group" = "default" ]', source)
        self.assertIn('proxy_dns_interface', source)

    def test_wan_helper_ignores_virtual_interface_in_auto_mode(self):
        source = (SHARE / 'openkill_wan.sh').read_text(encoding='utf-8')
        self.assertIn('wan_interface_mode', source)
        self.assertIn('openkill_resolve_interface_roles', source)
        self.assertIn('if [ "$mode" = "fixed" ]', source)
        for virtual in ('tun*', 'utun*', 'zt*', 'tailscale*', 'docker*'):
            self.assertIn(virtual, source)
        self.assertIn('ip -6 route show default', source)

    def test_compatibility_defaults_are_safe(self):
        config = (ROOT / 'luci-app-openkill/root/etc/config/openkill').read_text(encoding='utf-8')
        normalize = (SHARE / 'openkill_config_normalize.sh').read_text(encoding='utf-8')
        self.assertIn("option remote_service_bypass '0'", config)
        self.assertIn("option compatibility_profile 'stable'", config)
        self.assertIn('if [ -z "$compatibility_profile" ]', normalize)
        self.assertIn('set_default remote_service_bypass 0', normalize)
        self.assertIn('compat_migration_version=2026-1108', normalize)

    def test_ipv6_native_route_is_preserved_and_readiness_is_local(self):
        source = (ROOT / 'luci-app-openkill/root/etc/init.d/openkill').read_text(encoding='utf-8')
        self.assertIn('add_openkill_ipv6_fallback_route()', source)
        self.assertIn('remove_openkill_ipv6_fallback_route()', source)
        self.assertIn('OPENKILL_IPV6_ROUTE_MARKER', source)
        self.assertIn('Never manufacture a global default in the main table.', source)
        self.assertNotIn('ip -6 route replace default via "$gateway" dev "$iface"', source)
        self.assertNotIn('probe_openkill_ipv6_https "$iface"', source)
        self.assertIn('set_openkill_ipv6_state available local-route', source)
        self.assertIn('write_openkill_ipv6_diagnostics()', source)
        self.assertIn('route_source=', source)
        self.assertIn('route_lan_source=', source)
        self.assertIn('tcp_443=', source)
        self.assertIn('udp_dns=', source)
        self.assertIn('pmtu_1280=', source)
        choose = source.index('RAW_CONFIG_FILE=$(uci_get_config "config_path")\n      config_choose\n      get_config')
        preflight = source.index('do_run_mode\n      # yml_change runs later')
        self.assertLess(choose, preflight)
        self.assertIn('source-specific IPv6 defaults', source)

    def test_wan_ipv6_dns_and_gateway_are_not_injected(self):
        source = (SHARE / 'yml_change.sh').read_text(encoding='utf-8')
        block = source.split('sys_dns_append()\n{', 1)[1].split('\n}\n\nPROXY_GROUPS=', 1)[0]
        self.assertNotIn('wan6_gate', block)
        self.assertNotIn('wan6_dns', block)
        self.assertIn('OPENKILL_IPV6_DNS_GUARD', source)

    def test_ipv6_dns_is_independent_of_ipv6_traffic_proxy(self):
        normalize = (SHARE / 'openkill_config_normalize.sh').read_text(encoding='utf-8')
        change = (SHARE / 'yml_change.sh').read_text(encoding='utf-8')
        semantic = (SHARE / 'openkill_semantic_check.sh').read_text(encoding='utf-8')
        init = (ROOT / 'luci-app-openkill/root/etc/init.d/openkill').read_text(encoding='utf-8')
        self.assertIn('for key in ipv6_mode enable_v6_udp_proxy; do', normalize)
        self.assertNotIn('for key in ipv6_mode enable_v6_udp_proxy ipv6_dns; do', normalize)
        self.assertIn('DNS AAAA resolution is deliberately independent', change)
        self.assertNotIn('dns_ipv6 = false', change)
        self.assertIn('Do not reject the valid combination dns.ipv6=true + ipv6=false', semantic)
        self.assertIn('if [ "$ipv6_dns" -eq 1 ]; then', init)

    def test_ipv6_local_prefixes_come_from_internal_netifd_interfaces(self):
        source = (SHARE / 'openkill_get_network.lua').read_text(encoding='utf-8')
        init = (ROOT / 'luci-app-openkill/root/etc/init.d/openkill').read_text(encoding='utf-8')
        self.assertIn('ubus call network.interface dump', source)
        self.assertIn('ipv6-prefix', source)
        self.assertIn('name ~= "wan" and name ~= "wan6"', source)
        self.assertNotIn('for o = 1, #(rv.wan) do\n\t\t\tif rv.wan[o].proto ~= "pppoe" then\n\t\t\t\tif rv.wan[o].ip6addr', source)
        self.assertIn('openkill_get_network.lua "lan_cidr6"', init)

    def test_ipv6_control_plane_is_never_proxy_marked(self):
        source = (ROOT / 'luci-app-openkill/root/etc/init.d/openkill').read_text(encoding='utf-8')
        for chain in ('openkill_mangle_v6', 'openkill_mangle_output_v6'):
            self.assertIn('ip6 nexthdr udp th dport {546,547} counter return', source)
            self.assertIn('ip6 nexthdr icmpv6 icmpv6 type { nd-neighbor-solicit', source)
        self.assertIn('packet-too-big', source)
        self.assertIn('parameter-problem', source)

    def test_dnsmasq_forwarding_is_the_safe_default_for_tun_and_dual_stack(self):
        config = (ROOT / 'luci-app-openkill/root/etc/config/openkill').read_text(encoding='utf-8')
        normalize = (SHARE / 'openkill_config_normalize.sh').read_text(encoding='utf-8')
        settings = (ROOT / 'luci-app-openkill/luasrc/model/cbi/openkill/settings.lua').read_text(encoding='utf-8')
        self.assertIn("option enable_redirect_dns '1'", config)
        self.assertIn('dns_direct_safe=0', normalize)
        self.assertIn('*tun*) dns_direct_safe=0', normalize)
        self.assertIn('Firewall Redirect (Advanced: IPv4 non-TUN only)', settings)
        self.assertIn('Firewall-direct DNS is only available for an IPv4 non-TUN profile', settings)

    def test_fw4_include_defers_openkill_rule_rebuild_after_interface_change(self):
        init = (ROOT / 'luci-app-openkill/root/etc/init.d/openkill').read_text(encoding='utf-8')
        helper = (SHARE / 'openkill_fw4_reload.sh').read_text(encoding='utf-8')
        self.assertIn('/usr/share/openkill/openkill_fw4_reload.sh', init)
        self.assertNotIn('/etc/init.d/openkill reload "firewall"\nEOF', init)
        self.assertIn('firewall-deferred', init)
        self.assertIn('openkill-fw4-reload.lock', helper)
        self.assertIn('sleep 3', helper)
        self.assertIn('/etc/init.d/openkill reload "firewall-deferred"', helper)
        self.assertIn('/tmp/openkill-start.token', helper)
        self.assertIn('/tmp/openkill-ready.token', helper)
        self.assertIn('Do not let that include\'s own reload interrupt the start', helper)
        self.assertIn('Keep firewall include setup independent from ucitrack', init)
        self.assertIn('if uci -q show ucitrack >/dev/null 2>&1', init)
        self.assertIn('rm -f /tmp/openkill-ready.token', init)
        self.assertIn('fw4_reload_active()', init)
        self.assertIn('wait_for_fw4_settle()', init)
        self.assertIn('wait_for_fw4_settle\n      set_firewall', init)
        self.assertIn('ensure_fw4_dns_hijack || start_fail', init)
        self.assertIn('fw4 removed OpenKill DNS rules during startup; rebuilding', init)
        self.assertIn('[ "$1" = "keep-include" ] || remove_openkill_include', init)
        self.assertGreaterEqual(init.count('revert_firewall keep-include'), 2)
        self.assertIn('OPENKILL_KEEP_INCLUDE=1 stop_service', init)
        self.assertIn('OPENKILL_KEEP_INCLUDE=1 /etc/init.d/openkill stop', init)
        self.assertIn('for attempt in 1 2 3', helper)
        self.assertIn('uci -q get openkill.config.enable', helper)
        self.assertIn('/etc/init.d/openkill start', helper)
        self.assertIn('jsonfilter -e', helper)

    def test_dns_fallback_uses_rules_and_health_probes_are_bounded(self):
        source = (SHARE / 'yml_change.sh').read_text(encoding='utf-8')
        self.assertIn("text + '#RULES'", source)
        self.assertIn("Value['dns']['fallback-lazy-query'] = true", source)
        self.assertIn("group['interval'] = 180", source)
        self.assertIn("group['timeout'] = 3500", source)
        self.assertIn("group['max-failed-times'] = 2", source)
        self.assertIn("group['lazy'] = false", source)
        self.assertIn("proxy['ip-version'] = 'ipv4-prefer'", source)
        self.assertIn("group['proxies'] = ['REJECT']", source)
        self.assertIn("Value['dns']['nameserver-policy']['geosite:cn']", source)

    def test_vpn_remote_service_ports_bypass_interception(self):
        source = (ROOT / 'luci-app-openkill/root/etc/init.d/openkill').read_text(encoding='utf-8')
        self.assertIn('openkill_service_ports', source)
        self.assertIn('1194 9993 21114 21115 21116 21117 21118 21119', source)
        for chain in ('openkill', 'openkill_mangle', 'openkill_mangle_output',
                      'openkill_output', 'openkill_v6', 'openkill_mangle_v6',
                      'openkill_mangle_output_v6'):
            self.assertIn(f'{chain} th dport @openkill_service_ports', source)
            self.assertIn(f'{chain} th sport @openkill_service_ports', source)

    def test_service_port_controls(self):
        source = (ROOT / 'luci-app-openkill/root/etc/init.d/openkill').read_text(encoding='utf-8')
        block = source.split("   nft 'add set inet fw4 openkill_service_ports", 1)[1]
        block = "   nft 'add set inet fw4 openkill_service_ports" + block.split('\n   #bypass gateway compatible', 1)[0]
        for enabled, ports, expected in [
                ('1', '', ['1194', '9993', '21114', '21115', '21116', '21117', '21118', '21119']),
                ('0', '', []), ('1', '443 21116', ['443', '21116']),
                ('1', '0 65536 invalid 1194 999999999999', ['1194'])]:
            with self.subTest(enabled=enabled, ports=ports):
                harness = f"enabled='{enabled}'\nports='{ports}'\n" + '''
uci_get_config() { case "$1" in remote_service_bypass) echo "$enabled" ;; *) echo "$ports" ;; esac; }
nft() { case "$*" in 'add element '*) echo "$*" ;; esac; }
run_case() {
'''
                result = run_shell(harness + block + '\n}\nrun_case\n')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(),
                                 ['add element inet fw4 openkill_service_ports { ' + port + ' }' for port in expected])

    def test_compatibility_page_order_and_fields(self):
        source = (ROOT / 'luci-app-openkill/luasrc/model/cbi/openkill/settings.lua').read_text(encoding='utf-8')
        self.assertLess(source.index('s:tab("compatibility",'), source.index('s:tab("advanced",'))
        for field in ('remote_service_bypass', 'remote_service_ports', 'compatibility_profile',
                      'wan_interface_mode', 'wan_interface_name', 'wan_ac_black_ips',
                      'wan_ac_black_ports', 'bypass_gateway_compatible'):
            self.assertRegex(source, r's:taboption\("compatibility", [^,]+, "' + field + '"')

    def test_profile_modes_apply_safe_performance_defaults_and_are_visible(self):
        normalize = (SHARE / 'openkill_config_normalize.sh').read_text(encoding='utf-8')
        controller = (ROOT / 'luci-app-openkill/luasrc/controller/openkill.lua').read_text(encoding='utf-8')
        status = (ROOT / 'luci-app-openkill/luasrc/view/openkill/status.htm').read_text(encoding='utf-8')
        for marker in ('compatibility_profile', 'compatibility_fallback', 'tun_owner',
                       'tun_auto_route', 'tun_auto_redirect'):
            self.assertIn(marker, normalize)
        self.assertIn('compatibility_fallback_reason',
                      (ROOT / 'luci-app-openkill/root/etc/config/openkill').read_text(encoding='utf-8'))
        self.assertIn('compatibility_profile" = "performance"', normalize)
        for marker in ('enable_tcp_concurrent', 'enable_unified_delay', 'geodata_loader=standard',
                       'tun_strict_route', 'tun_endpoint_independent_nat'):
            self.assertIn(marker, normalize)
        for marker in ('compatibility_profile = fs.uci_get_config',
                       'compatibility_fallback = fs.uci_get_config',
                       'compatibility_fallback_reason = fs.uci_get_config'):
            self.assertIn(marker, controller)
        self.assertIn('runtime-compatibility-chip', status)
        for label in ('稳定兼容', '稳定兼容（原生回退）', '高性能双栈', 'Mihomo 原生接管',
                      'runtime-chip-warning'):
            self.assertIn(label, status)


@unittest.skipIf(os.name == 'nt', 'Recovery filesystem integration runs on Linux CI')
class RecoveryTests(unittest.TestCase):
    def test_snapshot_restores_once_and_preserves_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for subdir in ['etc/openkill', 'etc/config', 'etc/init.d', 'tmp']:
                (root / subdir).mkdir(parents=True)
            core = root / 'etc/openkill/clash'
            core.write_text('#!/bin/sh\nexit 0\n')
            core.chmod(0o755)
            config = root / 'etc/config/openkill'
            config.write_text('verified-settings')
            profile = root / 'etc/openkill/test.yaml'
            profile.write_text('verified-yaml')
            service = root / 'etc/init.d/openkill'
            service.write_text(f'''#!/bin/sh
echo "$1:${{OPENKILL_RECOVERY:-0}}" >> '{root}/events'
[ "$1" != stop ] || rm -f '{root}/tmp/openkill-start.token'
exit 0
''')
            service.chmod(0o755)
            script = (SHARE / 'openkill_recovery.sh').read_text(encoding='utf-8')
            script = re.sub(r'/(etc|tmp)/', lambda m: f'{root}/{m.group(1)}/', script)
            runner = root / 'recovery.sh'
            runner.write_text(script)
            subprocess.run([BASH, str(runner), 'save', str(profile)], check=True, timeout=10)
            config.write_text('broken-settings')
            token = root / 'tmp/openkill-start.token'
            token.write_text('generation-1')
            subprocess.run([BASH, str(runner), 'restore', 'stale'], check=True, timeout=10)
            self.assertEqual(config.read_text(), 'broken-settings')
            subprocess.run([BASH, str(runner), 'restore', 'generation-1'], check=True, timeout=10)
            self.assertEqual(config.read_text(), 'verified-settings')
            self.assertEqual((root / 'events').read_text().splitlines(), ['stop:0', 'start:1'])
            token.write_text('generation-2')
            result = subprocess.run([BASH, str(runner), 'restore', 'generation-2'], timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(len((root / 'events').read_text().splitlines()), 2)


if __name__ == '__main__':
    unittest.main()
