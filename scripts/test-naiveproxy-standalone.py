"""Functional offline fixture for the independent NaiveProxy bridge."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import hashlib
import json


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
        (root / "ports").write_text("n1 11080\n", encoding="utf-8")
        (fake / "jsonfilter").write_text("""#!/bin/sh
expr=
file=
while [ "$#" -gt 0 ]; do
  if [ "$1" = -e ]; then expr=$2; shift 2; continue; fi
  if [ "$1" = -i ]; then file=$2; shift 2; continue; fi
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
  @.listen) printf '%s' 'socks://127.0.0.1:11080' ;;
  @.proxy) printf '%s' 'https://fixture-user:fixture-secret@example.invalid:443' ;;
  @.generation) sed -n 's/.*"generation":\\([0-9][0-9]*\\).*/\\1/p' "$file" ;;
esac
""", encoding="utf-8")
        (fake / "ss").write_text("#!/bin/sh\nprintf '%s\\n' 'LISTEN 0 128 127.0.0.1:11080 0.0.0.0:*'\n", encoding="utf-8")
        # Keep the fixture offline.  Git for Windows may expose the host
        # nslookup executable through PATH; invoking it would make prepare
        # depend on the host network and can leave a captured pipe open.
        (fake / "nslookup").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (fake / "curl").write_text("#!/bin/sh\nprintf '204\\t0.123\\n'\n", encoding="utf-8")
        for path in fake.iterdir():
            os.chmod(path, 0o755)
        env = os.environ.copy()
        env.update({"NAIVEPROXY_ROOT": git_path(root), "NAIVEPROXY_RUN": git_path(run_dir),
                    "NAIVEPROXY_BIN": git_path(root / "naive"),
                    "NAIVEPROXY_TEST_ALLOW_NON_ELF": "1",
                    "PATH": git_path(fake) + ":" + env.get("PATH", "")})
        bash_env = Path(temp) / "bash_env"
        bash_env.write_text(f"export PATH={git_path(fake)}:$PATH\n", encoding="utf-8")
        env["BASH_ENV"] = git_path(bash_env)
        probe = subprocess.run([BASH, "-c", "command -v curl"], env=env, text=True,
                               capture_output=True, check=True).stdout.strip()
        assert probe.startswith(git_path(fake)), probe
        run(["prepare", "n1"], env)
        config_path = run_dir / "config" / "n1.json"
        config_before = config_path.stat().st_mtime_ns
        # Git for Windows can keep a pipeline child attached to captured pipes
        # after the shell has exited (notably the fake ss/grep health probe).
        # Redirect these read-only status commands and inspect the manifest
        # file they atomically write, avoiding a false test hang on Windows.
        health_result = subprocess.run([BASH, git_path(SCRIPT), "health", "all"], env=env, text=True,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        manifest_result = subprocess.run([BASH, git_path(SCRIPT), "manifest"], env=env, text=True,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if manifest_result.returncode:
            raise AssertionError(f"manifest rc={manifest_result.returncode}")
        manifest = (run_dir / "manifest").read_text(encoding="utf-8")
        if health_result.returncode:
            raise AssertionError(f"health rc={health_result.returncode}")
        # The offline fixture has no real /proc socket inode to associate with
        # its fake listener.  It must therefore remain unverified instead of
        # claiming a remote probe succeeded; the authorized device test
        # covers the verified inode + SOCKS5 path.
        assert "node.n1.health=local-not-ready" in manifest, manifest
        assert "node.n1.reason=listener-ownership-unverified" in manifest, manifest
        assert config_path.stat().st_mtime_ns == config_before, "health rewrote the active runtime config"
        assert config_path.is_file()
        if os.name != "nt":
            assert config_path.stat().st_mode & 0o777 == 0o600
        # A wildcard listener owned by another process must be reported as a
        # conflict, not as an unverified Naive listener.  Restore the fixture
        # listener before continuing with the read-only-config assertions.
        fake_ss = fake / "ss"
        fake_ss.write_text("#!/bin/sh\nprintf '%s\\n' 'LISTEN 0 128 0.0.0.0:11080 0.0.0.0:* users:((\\\"foreign\\\",pid=999,fd=3))'\n", encoding="utf-8")
        os.chmod(fake_ss, 0o755)
        foreign_health = subprocess.run(
            [BASH, git_path(SCRIPT), "health", "n1"], env=env, text=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        assert foreign_health.returncode == 0
        foreign_manifest = (run_dir / "manifest").read_text(encoding="utf-8")
        assert "node.n1.health=local-not-ready" in foreign_manifest
        assert "node.n1.reason=port-owned-by-other-process" in foreign_manifest
        fake_ss.write_text("#!/bin/sh\nprintf '%s\\n' 'LISTEN 0 128 127.0.0.1:11080 0.0.0.0:*'\n", encoding="utf-8")
        os.chmod(fake_ss, 0o755)
        restored_health = subprocess.run(
            [BASH, git_path(SCRIPT), "health", "n1"], env=env, text=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        assert restored_health.returncode == 0
        manifest = (run_dir / "manifest").read_text(encoding="utf-8")
        assert "node.n1.reason=listener-ownership-unverified" in manifest
        # A health/status request must not recreate a missing runtime config
        # or allocate a new port.  Applying a changed node is an explicit
        # start/apply operation, not a side effect of detection.
        config_path.unlink()
        ports_before = (root / "ports").read_text(encoding="utf-8")
        missing_config_health = subprocess.run(
            [BASH, git_path(SCRIPT), "health", "n1"], env=env, text=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        assert missing_config_health.returncode == 0
        missing_manifest = (run_dir / "manifest").read_text(encoding="utf-8")
        assert "node.n1.health=config-invalid" in missing_manifest
        assert "node.n1.reason=config-invalid" not in missing_manifest
        assert "node.n1.reason=node-config-not-applied" in missing_manifest
        assert not config_path.exists(), "health recreated the runtime config"
        assert (root / "ports").read_text(encoding="utf-8") == ports_before
        yaml = run(["yaml"], env).stdout
        assert 'server: "127.0.0.1"' in yaml and "port: 11080" in yaml
        assert "fixture-secret" not in yaml and "example.invalid" not in yaml
        assert not (root / "openkill.config").exists()

        imported = subprocess.run(
            [BASH, git_path(SCRIPT), "control"], env=env, text=True, input=(
                "operation=import\nshare=naive+https://fixture-user:fixture-secret@import.example.test:443?security=tls&type=tcp&headerType=none#Imported\nenabled=1\n"
            ), capture_output=True,
        )
        assert imported.returncode == 0, (imported.stdout, imported.stderr)
        control_result = (run_dir / "control.result").read_text(encoding="utf-8")
        assert "stage=accepted" in control_result and "id=" in control_result
        imported_id = next((line.split("=", 1)[1] for line in imported.stdout.splitlines()
                            if line.startswith("id=")), "")
        assert imported_id, imported.stdout
        imported_file = root / "nodes" / f"{imported_id}.json"
        imported_data = json.loads(imported_file.read_text(encoding="utf-8"))
        assert imported_data["name"] == "Imported"
        assert imported_data["server"] == "import.example.test"
        assert imported_data["port"] == 443
        assert imported_data["username"] == "fixture-user"
        assert imported_data["password"] == "fixture-secret"
        assert imported_data["transport"] == "https"
        assert imported_data["generation"] == 1
        imported_port = (run(["port", imported_id], env).stdout.strip())
        assert imported_port.isdigit() and imported_port != "11080"
        assert "fixture-secret" not in (run_dir / "manifest").read_text(encoding="utf-8")
        # A reboot or interrupted install can leave a stale component line in
        # an otherwise valid manifest.  The read-only refresh must correct
        # that evidence without touching the node table or allocating ports.
        (root / "naive").unlink()
        refreshed = run(["component-status"], env).stdout
        assert "component_status=unavailable" in refreshed
        assert "component_reason=component-missing" in refreshed
        assert "node.n1.name=fixture node" in refreshed
        assert "n1 11080" in (root / "ports").read_text(encoding="utf-8")
        (root / "naive").write_text("#!/bin/sh\nprintf '%s\\n' 'naive 1.0'\n", encoding="utf-8")
        os.chmod(root / "naive", 0o755)
        read_node = subprocess.run(
            [BASH, git_path(SCRIPT), "control"], env=env,
            text=True, input=f"operation=get\nid={imported_id}\n", capture_output=True,
        )
        assert read_node.returncode == 0, (read_node.stdout, read_node.stderr)
        control_result = (run_dir / "control.result").read_text(encoding="utf-8")
        assert "stage=node-read" in control_result and "fixture-secret" not in control_result
        edited = subprocess.run(
            [BASH, git_path(SCRIPT), "control"], env=env, text=True, input=(
                f"operation=edit\nid={imported_id}\ngeneration=1\nname=Renamed\n"
                "server=import.example.test\nport=443\nusername=fixture-user\n"
                "password_mode=retain\ntransport=https\nenabled=1\n"
            ), capture_output=True,
        )
        assert edited.returncode == 0, (edited.stdout, edited.stderr)
        edited_data = json.loads(imported_file.read_text(encoding="utf-8"))
        assert edited_data["name"] == "Renamed"
        assert edited_data["password"] == "fixture-secret"
        assert edited_data["generation"] == 2
        conflict = subprocess.run(
            [BASH, git_path(SCRIPT), "control"], env=env, text=True, input=(
                f"operation=edit\nid={imported_id}\ngeneration=1\nname=Renamed\n"
                "server=import.example.test\nport=443\nusername=fixture-user\n"
                "password_mode=retain\ntransport=https\nenabled=1\n"
            ), capture_output=True,
        )
        assert conflict.returncode != 0
        invalid = subprocess.run([BASH, git_path(SCRIPT), "control"], env=env, text=True,
                                 input="operation=import\nshare=naive+https://bad\n", capture_output=True)
        assert invalid.returncode != 0
        encoded = subprocess.run(
            [BASH, git_path(SCRIPT), "control"], env=env, text=True, input=(
                "operation=import\nshare=naive+https://fixture%40user:fixture%21secret@example.test:443?security=tls&type=tcp&headerType=none#Encoded%20Name\n"
            ), capture_output=True,
        )
        assert encoded.returncode == 0, (encoded.stdout, encoded.stderr)
        quic = subprocess.run(
            [BASH, git_path(SCRIPT), "control"], env=env, text=True, input=(
                "operation=import\nshare=naive+quic://quic-user:quic-secret@quic.example.test:443#Quic\nenabled=1\n"
            ), capture_output=True,
        )
        assert quic.returncode == 0, (quic.stdout, quic.stderr)
        default_port = subprocess.run(
            [BASH, git_path(SCRIPT), "control"], env=env, text=True, input=(
                "operation=import\nshare=naive+https://user+name:pass+word@default.example#Default\nenabled=1\n"
            ), capture_output=True,
        )
        assert default_port.returncode == 0, (default_port.stdout, default_port.stderr)
        default_id = next((line.split("=", 1)[1] for line in default_port.stdout.splitlines()
                           if line.startswith("id=")), "")
        assert default_id, default_port.stdout
        default_data = json.loads((root / "nodes" / f"{default_id}.json").read_text(encoding="utf-8"))
        assert default_data["port"] == 443
        assert default_data["username"] == "user+name"
        assert default_data["password"] == "pass+word"
        duplicate = subprocess.run([BASH, git_path(SCRIPT), "control"], env=env, text=True,
                                    input=("operation=import\nshare=naive+https://fixture-user:fixture-secret@import.example.test:443?security=tls&type=tcp&headerType=none#Again\n"),
                                    capture_output=True)
        assert duplicate.returncode != 0
        unknown = subprocess.run([BASH, git_path(SCRIPT), "control"], env=env, text=True,
                                 input=("operation=import\nshare=naive+https://fixture-user:fixture-secret@unknown.example.test:443?security=tls&unknown=x#Unknown\n"),
                                 capture_output=True)
        assert unknown.returncode != 0
        malformed = subprocess.run([BASH, git_path(SCRIPT), "control"], env=env, text=True,
                                   input=("operation=import\nshare=naive+https://fixture%ZZ:fixture-secret@example.test:443#Bad\n"),
                                   capture_output=True)
        assert malformed.returncode != 0

    # Exercise the independent installer with an offline, locally staged
    # official-shaped asset.  The fake downloader exists only in this fixture.
    if Path("/bin/true").exists() and shutil.which("tar"):
        with tempfile.TemporaryDirectory(prefix="openkill-naive-install-") as temp:
            raw = Path(temp)
            archive_dir = raw / "asset"
            archive_dir.mkdir()
            shutil.copyfile("/bin/true", archive_dir / "naive")
            archive = raw / "naiveproxy.tar.xz"
            subprocess.run(["tar", "-cJf", str(archive), "-C", str(archive_dir), "naive"], check=True)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            fake = raw / "bin"
            fake.mkdir()
            (fake / "curl").write_text(
                "#!/bin/sh\nout=\nwhile [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = -o ]; then out=$2; shift 2; else shift; fi\n"
                "done\ncp \"$NAIVE_TEST_ASSET\" \"$out\"\n",
                encoding="utf-8",
            )
            os.chmod(fake / "curl", 0o755)
            root = raw / "etc-naive"
            run_dir = raw / "run-naive"
            (root / "nodes").mkdir(parents=True)
            env = os.environ.copy()
            env.update({
                "NAIVEPROXY_ROOT": git_path(root),
                "NAIVEPROXY_RUN": git_path(run_dir),
                "NAIVEPROXY_BIN": git_path(root / "naive"),
                "NAIVE_TEST_ASSET": git_path(archive),
                "PATH": git_path(fake) + ":" + env.get("PATH", ""),
            })
            good = subprocess.run(
                [BASH, git_path(SCRIPT), "install",
                 "https://github.com/klzgrad/naiveproxy/releases/download/vfixture/naiveproxy-vfixture-openwrt-x86_64.tar.xz",
                 digest, str(archive.stat().st_size)],
                env=env, text=True, capture_output=True,
            )
            assert good.returncode == 0, (good.stdout, good.stderr)
            assert (root / "naive").is_file() and (root / "component.meta").is_file()
            before = (root / "naive").read_bytes()
            bad = subprocess.run(
                [BASH, git_path(SCRIPT), "install",
                 "https://github.com/klzgrad/naiveproxy/releases/download/vfixture/naiveproxy-vfixture-openwrt-x86_64.tar.xz",
                 "0" * 64, str(archive.stat().st_size)],
                env=env, text=True, capture_output=True,
            )
            assert bad.returncode != 0
            assert (root / "naive").read_bytes() == before
    print("NAIVEPROXY_STANDALONE_FIXTURE=PASS")


if __name__ == "__main__":
    main()
