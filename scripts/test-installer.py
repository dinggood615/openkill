"""Host-only checks: dependency fallback never installs through the old source."""
import pathlib
import subprocess
import shutil
import unittest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASH = shutil.which("bash") or "C:/Program Files/Git/bin/bash.exe"
SOURCE = (ROOT / "scripts/install-openkill.sh").read_text(encoding="utf-8")

class InstallerTests(unittest.TestCase):
    def test_repository_is_reused_after_download_failure(self):
        functions = SOURCE[SOURCE.index("pm_run(){"):SOURCE.index("install_dependencies(){")]
        harness = """
set -eu
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
PM=opkg
FEED_CONFIG=original
FEED_CANDIDATES="original mirror"
opkg(){
  if [ "$1" = status ]; then return 1; fi
  printf '%s\\n' "$*" >> "$WORK_DIR/calls"
  [ "$2" = mirror ]
}
""" + functions + """
install_dependency curl
[ "$FEED_CONFIG" = mirror ]
pm_run install local.ipk
grep -q -- '-f mirror update' "$WORK_DIR/calls"
grep -q -- '-f mirror install curl' "$WORK_DIR/calls"
grep -q -- '-f mirror install local.ipk' "$WORK_DIR/calls"
"""
        subprocess.run([BASH, "-c", harness], check=True)

    def test_formats_publish_inside_their_own_job(self):
        data = yaml.safe_load((ROOT / ".github/workflows/compile_new_ipk.yml").read_text(encoding="utf-8"))
        job = data["jobs"]["Compile"]
        self.assertFalse(job["strategy"]["fail-fast"])
        self.assertTrue(any(s.get("run") == "bash scripts/publish-package.sh" for s in job["steps"]))
        self.assertNotIn("Post-Process", data["jobs"])

    def test_shell_syntax(self):
        for name in ("install-openkill.sh", "publish-package.sh"):
            subprocess.run([BASH, "-n", str(ROOT / "scripts" / name)], check=True)

if __name__ == "__main__":
    unittest.main()
