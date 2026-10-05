"""Verify packaged partial-refresh integrity offline in an isolated environment.

This intentionally does NOT claim updated DecisionState or causal-diff replay.
"""

import json
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

from axis.evidence_refresh import audit

SNIPPET = """
import json, socket
def refuse(*args, **kwargs):
    raise RuntimeError('Network access forbidden during audit')
socket.socket.connect = refuse
socket.create_connection = refuse
from axis.evidence_refresh import audit
print(json.dumps(audit(), sort_keys=True))
"""


def main() -> None:
    wheel = Path(sys.argv[1]).resolve()
    expected = audit()
    with tempfile.TemporaryDirectory(prefix="axis-refresh-wheel-") as directory:
        temp = Path(directory)
        env = temp / "venv"
        venv.create(env, with_pip=True)
        binary = env / ("Scripts" if sys.platform == "win32" else "bin")
        subprocess.run(
            [str(binary / "pip"), "install", "--no-deps", str(wheel)],
            check=True,
            capture_output=True,
            text=True,
        )
        result = subprocess.run(
            [str(binary / "python"), "-I", "-c", SNIPPET],
            cwd=temp,
            capture_output=True,
            text=True,
            check=True,
        )
        actual = json.loads(result.stdout)
        if actual != expected:
            raise SystemExit("Installed-wheel partial audit differs from checkout")
        if actual["integrity_errors"]:
            raise SystemExit(str(actual["integrity_errors"]))
        if actual["verdict"] != "NOT READY FOR MERGE":
            raise SystemExit("Partial package incorrectly promoted to complete")
        print("PASS: isolated wheel, network disabled, same partial NO-GO audit")
        print("NOT RUN: DecisionState v2 and causal-diff replay (not created)")


if __name__ == "__main__":
    main()
