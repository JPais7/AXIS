"""Install the built wheel in a clean venv and replay a retrospective case offline.

poetry build && python scripts/verify_retrospective_wheel.py dist/*.whl
"""

import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main() -> int:
    wheel = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        env = Path(tmp) / "venv"
        venv.create(env, with_pip=True)
        bin_dir = env / ("Scripts" if sys.platform == "win32" else "bin")
        subprocess.run([str(bin_dir / "pip"), "install", "-q", str(wheel)], check=True)
        db = str(Path(tmp) / "w.duckdb")
        axis = str(bin_dir / "axis")
        for args in (
            ["benchmark", "list"],
            ["benchmark", "run", "syn-generic-positive"],
            ["benchmark", "reveal", "syn-generic-positive"],
            ["benchmark", "run", "erap1-axspa-t2016"],
            ["benchmark", "reveal", "erap1-axspa-t2016"],
        ):
            out = subprocess.run(
                [axis, "--database", db, *args], capture_output=True, text=True
            )
            if out.returncode != 0:
                print(out.stdout, out.stderr)
                return 1
        print("installed wheel replays retrospective cases offline: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
