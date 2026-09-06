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
nft() { echo openkill; }
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
