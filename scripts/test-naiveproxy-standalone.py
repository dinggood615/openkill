"""Functional offline fixture for the independent NaiveProxy bridge."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "luci-app-openkill/root/usr/share/openkill/naiveproxy-standalone.sh"
BASH = "C:/Program Files/Git/bin/bash.exe" if Path("C:/Program Files/Git/bin/bash.exe").exists() else (shutil.which("bash") or "bash")


def git_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    return f"/{drive}{resolved.as_posix().split(':', 1)[-1]}"


def run(args, env):
    return subprocess.run([BASH, git_path(SCRIPT), *args], env=env, text=True,
                          capture_output=True, check=True)


def main():
    with tempfile.TemporaryDirectory(prefix="openkill-naive-") as temp:
        root = Path(temp) / "etc-naive"
        run_dir = Path(temp) / "run-naive"
        fake = Path(temp) / "bin"
        (root / "nodes").mkdir(parents=True)
        fake.mkdir()
        (root / "nodes" / "n1.json").write_text(
            '{"name":"fixture node","enabled":true,"server":"example.invalid",'
            '"port":443,"username":"fixture-user","password":"fixture-secret",'
            '"transport":"https"}\n', encoding="utf-8")
        (root / "naive").write_text("#!/bin/sh\nprintf '%s\\n' 'naive 1.0'\n", encoding="utf-8")
        os.chmod(root / "naive", 0o755)
        (fake / "jsonfilter").write_text("""#!/bin/sh
expr=
while [ "$#" -gt 0 ]; do
  if [ "$1" = -e ]; then expr=$2; shift 2; continue; fi
  shift
done
case "$expr" in
  @.name) printf '%s' 'fixture node' ;;
  @.enabled) printf '%s' 'true' ;;
  @.server) printf '%s' 'example.invalid' ;;
  @.port) printf '%s' '443' ;;
  @.username) printf '%s' 'fixture-user' ;;
  @.password) printf '%s' 'fixture-secret' ;;
  @.transport) printf '%s' 'https' ;;
esac
""", encoding="utf-8")
        (fake / "ss").write_text("#!/bin/sh\nprintf '%s\\n' 'LISTEN 0 128 127.0.0.1:11080 0.0.0.0:*'\n", encoding="utf-8")
        (fake / "curl").write_text("#!/bin/sh\nprintf '204\\t0.123\\n'\n", encoding="utf-8")
        for path in fake.iterdir():
            os.chmod(path, 0o755)
        env = os.environ.copy()
        env.update({"NAIVEPROXY_ROOT": git_path(root), "NAIVEPROXY_RUN": git_path(run_dir),
                    "NAIVEPROXY_BIN": git_path(root / "naive"),
                    "PATH": git_path(fake) + ":" + env.get("PATH", "")})
        bash_env = Path(temp) / "bash_env"
        bash_env.write_text(f"export PATH={git_path(fake)}:$PATH\n", encoding="utf-8")
        env["BASH_ENV"] = git_path(bash_env)
        probe = subprocess.run([BASH, "-c", "command -v curl"], env=env, text=True,
                               capture_output=True, check=True).stdout.strip()
        assert probe.startswith(git_path(fake)), probe
        run(["prepare", "n1"], env)
        health_result = subprocess.run([BASH, git_path(SCRIPT), "health", "all"], env=env, text=True, capture_output=True)
        manifest = subprocess.run([BASH, git_path(SCRIPT), "manifest"], env=env, text=True,
                                  capture_output=True, check=True).stdout
        if health_result.returncode:
            raise AssertionError(f"health rc={health_result.returncode} stdout={health_result.stdout!r} stderr={health_result.stderr!r}")
        assert "node.n1.health=available" in manifest, manifest
        assert "node.n1.latency_ms=123" in manifest, manifest
        yaml = run(["yaml"], env).stdout
        assert 'server: "127.0.0.1"' in yaml and "port: 11080" in yaml
        assert "fixture-secret" not in yaml and "example.invalid" not in yaml
        assert (run_dir / "config" / "n1.json").is_file()
        if os.name != "nt":
            assert (run_dir / "config" / "n1.json").stat().st_mode & 0o777 == 0o600
        assert not (root / "openkill.config").exists()
    print("NAIVEPROXY_STANDALONE_FIXTURE=PASS")


if __name__ == "__main__":
    main()
