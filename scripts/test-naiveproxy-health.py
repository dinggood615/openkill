"""Compatibility entry point for the independent NaiveProxy health fixture.

Health state is now owned by ``naiveproxy-standalone.sh`` rather than the
retired OpenKill/UCI worker.  Keep this named gate for downstream callers,
but execute the isolated bridge fixture used by the integration suite.
"""

from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    runpy.run_path(str(ROOT / "scripts/test-naiveproxy-standalone.py"), run_name="__main__")
    print("NAIVEPROXY_HEALTH_FIXTURE=PASS")


if __name__ == "__main__":
    main()
