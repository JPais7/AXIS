"""Install the built wheel in a clean venv and replay both campaigns offline.

poetry build && python scripts/verify_computational_wheel.py dist/*.whl
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
        axis, db = str(bin_dir / "axis"), str(Path(tmp) / "w.duckdb")
        steps = [
            ["campaign", "register", "synthetic-generic"],
            ["campaign", "prepare", "campaign:synthetic:generic-v1@r1"],
            ["campaign", "run", "campaign:synthetic:generic-v1@r1"],
            ["campaign", "candidates", "campaign:synthetic:generic-v1@r1"],
        ]
        for args in steps:
            out = subprocess.run(
                [axis, "--database", db, *args], capture_output=True, text=True
            )
            if out.returncode != 0:
                print(out.stdout, out.stderr)
                return 1
        listing = subprocess.run(
            [axis, "--database", db, "chemistry", "space", "list"],
            capture_output=True,
            text=True,
        )
        if "campaign:synthetic" not in listing.stdout:
            print(listing.stdout, listing.stderr)
            return 1
        print("installed wheel replays the computational campaign offline: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
