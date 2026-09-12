#!/usr/bin/env python3
"""Regression tests for resolved netifd snapshots and the fw4 hook lifecycle."""

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHARE = ROOT / "luci-app-openkill/root/usr/share/openkill"
NETWORK = SHARE / "openkill_network.sh"
FW4_HOOK = SHARE / "openkill_fw4_reload.sh"
FIXTURE = ROOT / "scripts/fixtures/openwrt-network-interface-dump-uppercase.json"
FIXTURE_102 = ROOT / "scripts/fixtures/openwrt-network-interface-dump-102.json"


def write_jsonfilter(path):
    """Write a small jsonfilter-compatible fixture shim with bracket support."""
    path.write_text(
        r'''#!/usr/bin/env python3
import json
import os
import re
import sys

expr = ""
source = os.environ["OPENKILL_JSONFILTER_FIXTURE"]
args = sys.argv[1:]
while args:
    item = args.pop(0)
    if item == "-e" and args:
        expr = args.pop(0)
    elif item == "-i" and args:
        args.pop(0)

with open(source, encoding="utf-8") as handle:
    value = json.load(handle)

match = re.fullmatch(r"@\.interface\[(\d+)\](.*)", expr)
if not match:
    sys.exit(1)
index = int(match.group(1))
try:
    value = value["interface"][index]
except (KeyError, IndexError, TypeError):
    sys.exit(1)

tail = match.group(2)
position = 0
while position < len(tail):
    if tail[position] == ".":
        token = re.match(r"\.([A-Za-z_][A-Za-z0-9_-]*)", tail[position:])
        if not token:
            sys.exit(1)
        key = token.group(1)
        position += len(token.group(0))
        if not isinstance(value, dict) or key not in value:
            sys.exit(1)
        value = value[key]
    elif tail[position:position + 2] == '["':
        token = re.match(r'\["([^"]+)"\]', tail[position:])
        if not token:
            sys.exit(1)
        key = token.group(1)
        position += len(token.group(0))
        if not isinstance(value, dict) or key not in value:
            sys.exit(1)
        value = value[key]
    elif tail[position] == "[":
        token = re.match(r"\[(\d+)\]", tail[position:])
        if not token:
            sys.exit(1)
        item_index = int(token.group(1))
        position += len(token.group(0))
        if not isinstance(value, list) or item_index >= len(value):
            sys.exit(1)
        value = value[item_index]
    else:
        sys.exit(1)

if isinstance(value, list):
    for item in value:
        if isinstance(item, bool):
            print(str(item).lower())
        elif isinstance(item, (dict, list)):
            print(json.dumps(item, separators=(",", ":")))
        else:
            print(item)
elif isinstance(value, bool):
    print(str(value).lower())
elif isinstance(value, (dict, list)):
    print(json.dumps(value, separators=(",", ":")))
else:
    print(value)
''', encoding="utf-8")
    path.chmod(0o755)


def write_executable(path, content):
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


class SnapshotTests(unittest.TestCase):
    def test_real_uppercase_dump_populates_selected_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dump = root / "dump.json"
            dump.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            output = root / "snapshot"
            desired = root / "desired"
            lua = root / "network.lua"
            bindir = root / "bin"
            bindir.mkdir()
            write_jsonfilter(bindir / "jsonfilter")
            write_executable(
                bindir / "ip",
                """#!/bin/sh
case "$*" in
  *"-4 route show table main"*) echo 'default via 198.51.100.1 dev eth1' ;;
  *"-6 route show table main"*) echo 'default from 2409:8a20:fe0:90::/64 via fe80::1 dev eth1' ;;
  *"-6 rule show"*) echo '0: from all lookup local' ;;
esac
""",
            )
            write_executable(
                lua,
                """#!/bin/sh
[ "$1" = lan_cidr6 ] && printf '%s\\n' '2409:8a20:fe0:94::/62' '2001:db8:10::/64'
""",
            )
            env = os.environ.copy()
            env["PATH"] = f"{bindir}:/bin:/usr/bin"
            env["OPENKILL_INTERFACE_DUMP_FILE"] = str(dump)
            env["OPENKILL_JSONFILTER_FIXTURE"] = str(dump)
            env["OPENKILL_NETWORK_LUA"] = str(lua)
            roles = root / "roles"
            subprocess.run(
                ["sh", "-c", f'. "{NETWORK}"; openkill_resolve_interface_roles "$1" "$2"',
                 "model", str(dump), str(roles)],
                capture_output=True, text=True, check=True, env=env,
            )
            role_values = dict(line.split("=", 1) for line in roles.read_text().splitlines() if "=" in line)
            self.assertEqual(role_values["WAN4_INDEX"], "2")
            self.assertEqual(role_values["WAN6_INDEX"], "3")
            result = subprocess.run(
                ["sh", "-c", f'. "{NETWORK}"; openkill_collect_network_snapshot "$1"',
                 "model", str(output)],
                capture_output=True, text=True, check=True, env=env,
            )
            self.assertEqual(result.returncode, 0)
            values = dict(line.split("=", 1) for line in output.read_text().splitlines() if "=" in line)
            self.assertEqual(values["WAN4_INTERFACE"], "WAN")
            self.assertEqual(values["WAN6_INTERFACE"], "WAN6")
            self.assertEqual(values["WAN4_L3_DEVICE"], "eth1")
            self.assertEqual(values["WAN6_L3_DEVICE"], "eth1")
            self.assertEqual(values["WAN4_ADDRESSES"], "198.51.100.223")
            self.assertEqual(
                set(values["WAN6_ADDRESSES"].split()),
                {
                    "2409:8a20:fe0:90::f4c/128",
                    "2409:8a20:fe0:90:20c:29ff:fe13:c205/64",
                },
            )
            self.assertEqual(
                set(values["WAN6_HOST_ADDRESSES"].split()),
                {
                    "2409:8a20:fe0:90::f4c/128",
                    "2409:8a20:fe0:90:20c:29ff:fe13:c205/128",
                },
            )
            self.assertEqual(set(values["DNS_SERVERS"].split()), {"9.9.9.9", "2001:4860:4860::8888"})
            self.assertEqual(values["LOCAL_IPV6_READY"], "1")
            self.assertIn("default from", values["NATIVE_IPV6_ROUTES"])
            self.assertNotIn("default dev", values["NATIVE_IPV6_ROUTES"])

            subprocess.run(
                ["sh", "-c", f'. "{NETWORK}"; openkill_build_desired_state "$1" "$2"',
                 "model", str(output), str(desired)],
                capture_output=True, text=True, check=True, env=env,
            )
            local6 = dict(line.split("=", 1) for line in desired.read_text().splitlines() if "=" in line)[
                "LOCALNETWORK6_PREFIXES"
            ]
            self.assertIn("2409:8a20:fe0:94::/62", local6.split())
            self.assertIn("2001:db8:10::/64", local6.split())
            self.assertIn("2409:8a20:fe0:90::f4c/128", local6.split())
            self.assertIn("2409:8a20:fe0:90:20c:29ff:fe13:c205/128", local6.split())
            self.assertNotIn("2409:8a20:fe0:90::/64", local6.split())

    def test_real_102_fixture_populates_addresses_dns_and_source_specific_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dump = root / "dump.json"
            dump.write_text(FIXTURE_102.read_text(encoding="utf-8"), encoding="utf-8")
            output = root / "snapshot"
            output2 = root / "snapshot.2"
            desired = root / "desired"
            desired2 = root / "desired.2"
            fingerprint = root / "fingerprint"
            fingerprint2 = root / "fingerprint.2"
            bindir = root / "bin"
            bindir.mkdir()
            write_jsonfilter(bindir / "jsonfilter")
            write_executable(
                bindir / "ip",
                """#!/bin/sh
case "$*" in
  *"-4 route show table main"*) echo 'default via 192.168.10.2 dev eth1' ;;
  *"-6 route show table main"*) echo 'default from fd15:4ba5:5a2b:1008::/64 via fe80::250:56ff:fec0:2222 dev eth1' ;;
  *"-6 rule show"*) echo '0: from all lookup local' ;;
esac
""",
            )
            lua = root / "network.lua"
            write_executable(lua, "#!/bin/sh\nexit 0\n")
            env = os.environ.copy()
            env["PATH"] = f"{bindir}:/bin:/usr/bin"
            env["OPENKILL_INTERFACE_DUMP_FILE"] = str(dump)
            env["OPENKILL_JSONFILTER_FIXTURE"] = str(dump)
            env["OPENKILL_NETWORK_LUA"] = str(lua)
            result = subprocess.run(
                ["sh", "-c", f'. "{NETWORK}"; openkill_collect_network_snapshot "$1"',
                 "model", str(output)],
                capture_output=True, text=True, check=True, env=env,
            )
            self.assertEqual(result.returncode, 0)
            values = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines() if "=" in line)
            self.assertEqual(values["WAN4_INTERFACE"], "WAN")
            self.assertEqual(values["WAN6_INTERFACE"], "WAN6")
            self.assertEqual(values["WAN4_L3_DEVICE"], "eth1")
            self.assertEqual(values["WAN6_L3_DEVICE"], "eth1")
            self.assertEqual(values["WAN4_ADDRESSES"], "192.168.10.128")
            self.assertEqual(values["WAN6_ADDRESSES"], "fd15:4ba5:5a2b:1008:20c:29ff:fe07:4ffe/64")
            self.assertEqual(values["WAN6_HOST_ADDRESSES"], "fd15:4ba5:5a2b:1008:20c:29ff:fe07:4ffe/128")
            self.assertEqual(values["DNS_SERVERS"], "192.168.10.2")
            self.assertEqual(values["LOCAL_IPV6_READY"], "1")
            self.assertIn("default from", values["NATIVE_IPV6_ROUTES"])
            self.assertNotIn("default dev", values["NATIVE_IPV6_ROUTES"])

            subprocess.run(
                ["sh", "-c", f'. "{NETWORK}"; openkill_collect_network_snapshot "$1"',
                 "model", str(output2)],
                capture_output=True, text=True, check=True, env=env,
            )
            self.assertEqual(output.read_bytes(), output2.read_bytes())
            subprocess.run(
                ["sh", "-c", f'. "{NETWORK}"; openkill_build_desired_state "$1" "$2"',
                 "model", str(output), str(desired)],
                capture_output=True, text=True, check=True, env=env,
            )
            subprocess.run(
                ["sh", "-c", f'. "{NETWORK}"; openkill_build_desired_state "$1" "$2"',
                 "model", str(output2), str(desired2)],
                capture_output=True, text=True, check=True, env=env,
            )
            subprocess.run(
                ["sh", "-c", f'. "{NETWORK}"; openkill_network_fingerprint "$1" "$2"',
                 "model", str(output), str(fingerprint)],
                capture_output=True, text=True, check=True, env=env,
            )
            subprocess.run(
                ["sh", "-c", f'. "{NETWORK}"; openkill_network_fingerprint "$1" "$2"',
                 "model", str(output2), str(fingerprint2)],
                capture_output=True, text=True, check=True, env=env,
            )
            self.assertEqual(desired.read_bytes(), desired2.read_bytes())
            self.assertEqual(fingerprint.read_bytes(), fingerprint2.read_bytes())


class Fw4LifecycleTests(unittest.TestCase):
    def _run_hook(self, root, mode="success", state=None):
        state = state or root / "state"
        state.mkdir(parents=True, exist_ok=True)
        trace = root / "init.trace"
        flag = root / "requeue.once"
        init = root / "openkill-init"
        mode_file = root / "mode"
        mode_file.write_text(mode, encoding="utf-8")
        write_executable(
            init,
            f'''#!/bin/sh
printf '%s\\n' "$*" >> "{trace}"
mode=$(cat "{mode_file}")
case "$mode" in
  success) exit 0 ;;
  fail) exit 1 ;;
  requeue)
    if [ ! -f "{flag}" ]; then
      : > "{flag}"
      : > "{state / 'pending'}"
    fi
    exit 0
    ;;
esac
exit 1
''',
        )
        env = os.environ.copy()
        env.update({
            "OPENKILL_FW4_LOCK_DIR": str(root / "lock"),
            "OPENKILL_FW4_STATE_DIR": str(state),
            "OPENKILL_FW4_INIT_SERVICE": str(init),
            "OPENKILL_NETWORK_HELPER": str(NETWORK),
            "OPENKILL_START_TOKEN_FILE": str(root / "start.token"),
            "OPENKILL_READY_TOKEN_FILE": str(root / "ready.token"),
            "OPENKILL_FW4_SETTLE_DELAY": "0",
            "OPENKILL_FW4_RETRY_DELAY": "0",
            "OPENKILL_FW4_PENDING_DELAY": "0",
        })
        subprocess.run(["sh", str(FW4_HOOK)], capture_output=True, text=True, check=True, env=env)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if not (root / "lock").exists() and trace.exists():
                break
            time.sleep(0.01)
        return state, trace.read_text(encoding="utf-8").splitlines() if trace.exists() else []

    def test_pending_uses_reconcile_state_and_rc0_settles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, calls = self._run_hook(root)
            self.assertFalse((state / "pending").exists())
            self.assertEqual(calls, ['reload firewall-deferred'])
            source = FW4_HOOK.read_text(encoding="utf-8")
            self.assertIn('PENDING_FILE="$NETWORK_STATE_DIR/pending"', source)
            self.assertNotIn('/tmp/openkill-network-reconcile.pending', source)

    def test_external_fw4_rc1_with_healthy_openkill_still_settles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fw4 = root / "fw4"
            write_executable(fw4, "#!/bin/sh\nexit 1\n")
            self.assertEqual(subprocess.run([str(fw4), "reload"]).returncode, 1)
            state, calls = self._run_hook(root)
            self.assertFalse((state / "pending").exists())
            self.assertEqual(calls, ['reload firewall-deferred'])

    def test_classifier_loss_requeues_one_bounded_reapply(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, calls = self._run_hook(root, "requeue")
            self.assertFalse((state / "pending").exists())
            self.assertEqual(calls, ['reload firewall-deferred', 'reload firewall-deferred'])

    def test_apply_failure_leaves_retryable_marker_with_bounded_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, calls = self._run_hook(root, "fail")
            self.assertTrue((state / "pending").exists())
            self.assertLessEqual(len(calls), 9)
            self.assertFalse((root / "lock").exists())
            self._run_hook(root, "success", state=state)
            self.assertFalse((state / "pending").exists())


if __name__ == "__main__":
    unittest.main()
