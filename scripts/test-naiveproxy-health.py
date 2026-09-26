"""Offline behavior fixture for the NaiveProxy per-node health worker.

The fixture provides a fake UCI database, loopback listener table and Mihomo
controller.  It exercises one successful exact-node delay probe and one
independent not-loaded result without contacting a device or an internet host.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_naive_health.sh"
HELPER = ROOT / "luci-app-openkill/root/usr/share/openkill/openkill_naive.sh"


def posix_path(path: Path) -> str:
    value = str(path).replace("\\", "/")
    if len(value) >= 2 and value[1] == ":":
        return "/" + value[0].lower() + value[2:]
    return value


def write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def main() -> None:
    bash = shutil.which("bash.exe") or shutil.which("bash")
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    if git_bash.exists():
        bash = str(git_bash)
    assert bash, "Git Bash is required for the POSIX fixture"

    with tempfile.TemporaryDirectory(prefix="openkill-naive-health-") as raw:
        root = Path(raw)
        bin_dir = root / "bin"
        runtime = root / "runtime"
        naive_root = root / "naive"
        tasks = root / "tasks"
        for path in (bin_dir, runtime, naive_root, tasks):
            path.mkdir(parents=True)

        yaml = root / "mihomo.yaml"
        yaml.write_text(
            'proxies:\n'
            '  - name: "Node One"\n'
            '    type: socks5\n'
            '  - name: "Node Bad"\n'
            '    type: socks5\n'
            'proxy-groups:\n'
            '  - name: "Proxy"\n'
            '    proxies:\n'
            '      - "Node One"\n'
            '      - "Node Bad"\n',
            encoding="utf-8",
        )
        (naive_root / "ports").write_text("node_ok 11080\nnode_bad 11081\n", encoding="utf-8")
        for sid in ("node_ok", "node_bad"):
            config = runtime / f"{sid}.json"
            config.write_text('{"listen":"socks://127.0.0.1:11080"}\n', encoding="utf-8")
            config.chmod(0o600)

        lib = root / "functions.sh"
        lib.write_text(
            """config_load() { :; }
config_get() {
    var=$1; sid=$2; option=$3; default=${4-}; value=$default
    case "$sid:$option" in
      node_ok:enabled|node_bad:enabled) value=1 ;;
      node_ok:type|node_bad:type) value=naiveproxy ;;
      node_ok:name) value='Node One' ;;
      node_bad:name) value='Node Bad' ;;
      node_ok:server|node_bad:server) value=example.test ;;
      node_ok:port|node_bad:port) value=443 ;;
      node_ok:naive_username|node_bad:naive_username) value=fixture-user ;;
      node_ok:naive_password|node_bad:naive_password) value=fixture-secret ;;
      node_ok:naive_transport|node_bad:naive_transport) value=https ;;
    esac
    eval "$var=\\\"$value\\\""
}
config_get_bool() { config_get "$@"; }
config_list_foreach() { [ "$2" = groups ] && "$3" Proxy; }
""",
            encoding="utf-8",
            newline="\n",
        )

        write_executable(
            bin_dir / "uci",
            f"""#!/bin/sh
case "$*" in
  *'-X show openkill'*) printf '%s\\n' 'openkill.node_ok=servers' 'openkill.node_bad=servers' ;;
  *'get openkill.config.naive_bridge_mode'*) printf '%s\\n' auto ;;
  *'get openkill.config.naive_health_timeout'*) printf '%s\\n' 3 ;;
  *'get openkill.config.naive_health_interval'*) printf '%s\\n' 300 ;;
  *'get openkill.config.naive_port_base'*) printf '%s\\n' 11080 ;;
  *'get openkill.config.config_path'*) printf '%s\\n' '{posix_path(yaml)}' ;;
  *) exit 1 ;;
esac
""",
        )
        write_executable(
            bin_dir / "ss",
            "#!/bin/sh\nprintf '%s\\n' 'LISTEN 0 128 127.0.0.1:11080 0.0.0.0:*' 'LISTEN 0 128 127.0.0.1:11081 0.0.0.0:*'\n",
        )
        write_executable(
            bin_dir / "naive",
            "#!/bin/sh\nprintf '%s\\n' fixture-naive\n",
        )
        write_executable(
            bin_dir / "curl",
            f"""#!/bin/sh
printf '%s\\n' "$*" >> '{posix_path(root / "curl.calls")}'
out=/dev/null
url=
for arg in "$@"; do
    case "$arg" in
      -o) next=output ;;
      http://*|https://*) url=$arg ;;
      *) if [ "${{next:-}}" = output ]; then out=$arg; next=; fi ;;
    esac
done
case "$url" in
  *Node%20One/delay) printf '%s' '{{"delay":42}}' > "$out"; printf '200' ;;
  *Node%20One) printf '%s' '{{}}' > "$out"; printf '200' ;;
  *Node%20Bad*) printf '%s' '{{}}' > "$out"; printf '404' ;;
  *) printf '%s' '{{}}' > "$out"; printf '500' ;;
esac
""",
        )
        write_executable(
            bin_dir / "jsonfilter",
            "#!/bin/sh\ncat \"$2\" 2>/dev/null | sed -n 's/.*\"delay\":\\([0-9][0-9]*\\).*/\\1/p'\n",
        )
        bash_env = root / "bash_env"
        bash_env.write_text(f'PATH="{posix_path(bin_dir)}:$PATH"\nhash -r\n', encoding="utf-8", newline="\n")

        state = root / "health.state"
        env = os.environ.copy()
        env["PATH"] = posix_path(bin_dir) + ":" + env.get("PATH", "")
        env.update(
            {
                "OPENKILL_LIB_FUNCTIONS": posix_path(lib),
                "OPENKILL_NAIVE_HELPER": posix_path(HELPER),
                "OPENKILL_NAIVE_BIN": posix_path(bin_dir / "naive"),
                "OPENKILL_NAIVE_RUNTIME": posix_path(runtime),
                "OPENKILL_NAIVE_ROOT": posix_path(naive_root),
                "OPENKILL_NAIVE_HEALTH_STATE": posix_path(state),
                "OPENKILL_NAIVE_HEALTH_LOCK": posix_path(root / "health.lock.d"),
                "OPENKILL_NAIVE_HEALTH_TASK_ROOT": posix_path(tasks),
                "BASH_ENV": posix_path(bash_env),
            }
        )
        command = [bash, posix_path(WORKER), "run"]
        result = subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        assert result.returncode == 0, repr(result.stderr or result.stdout)
        content = state.read_text(encoding="utf-8")
        assert "node.node_ok.status=available" in content
        assert "node.node_ok.latency_ms=42" in content
        assert "node.node_ok.final_yaml=loaded-candidate" in content
        assert "node.node_bad.status=mihomo-not-loaded" in content
        assert "fixture-secret" not in content
        assert "fixture-user" not in content

    print("NAIVEPROXY_HEALTH_FIXTURE=PASS")


if __name__ == "__main__":
    main()
