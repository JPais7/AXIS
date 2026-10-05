"""Install the built wheel in a clean venv and replay the chemical-learning loop offline.

poetry build && python scripts/verify_learning_wheel.py dist/*.whl
"""

import subprocess
import sys
import tempfile
import venv
from pathlib import Path

SNIPPET = """
import socket, sys
def refuse(*a, **k): raise RuntimeError('network used')
socket.socket.connect = refuse
from pathlib import Path
from axis.storage import EvidenceStore
from axis.learning.service import LearningService
with EvidenceStore(Path(sys.argv[1])) as s:
    L = LearningService(s)
    project, early = L.synthetic_records('2020-12-31')
    ids = L.build_datasets(project, early, synthetic=True)
    main = next(i for i in ids if 'SYN-SUBSTRATE-1' in i)
    small = next(i for i in ids if 'SYN-SUBSTRATE-2' in i)
    refused = L.train(small)
    assert refused['model_built'] is False, refused
    L.assess_eligibility(main); L.derive_sar(main)
    built = L.train(main, 'ridge', 'scaffold', 7)
    assert built['model_built'], built
    m = L.model(built['model_id'])
    assert m['validation']['evaluation']['baseline_comparison']['beats_mean_baseline']
    state = L.learning_state(project)
    print('learning loop OK: refusal', refused['status'], '| model', built['fingerprint'][:12], '| state r%d' % state['revision'])
"""


def main() -> int:
    wheel = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        env = Path(tmp) / "venv"
        venv.create(env, with_pip=True)
        bin_dir = env / ("Scripts" if sys.platform == "win32" else "bin")
        subprocess.run([str(bin_dir / "pip"), "install", "-q", str(wheel)], check=True)
        db = str(Path(tmp) / "w.duckdb")
        out = subprocess.run(
            [str(bin_dir / "python"), "-c", SNIPPET, db], capture_output=True, text=True
        )
        if out.returncode != 0 or "learning loop OK" not in out.stdout:
            print(out.stdout, out.stderr)
            return 1
        cli = subprocess.run(
            [
                str(bin_dir / "axis"),
                "--database",
                db,
                "chemistry",
                "dataset",
                "list",
                "--project",
                "SYNTHETIC-LEARNING-PROJECT",
            ],
            capture_output=True,
            text=True,
        )
        if cli.returncode != 0 or "SYNTHETIC" not in cli.stdout:
            print(cli.stdout, cli.stderr)
            return 1
        print(out.stdout.strip())
        print("installed wheel replays the chemical-learning loop offline: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
