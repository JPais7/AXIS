"""Install the built wheel in a clean venv and replay both campaigns offline.

poetry build && python scripts/verify_computational_wheel.py dist/*.whl
"""

import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ERAP_SNIPPET = """
import socket, sys
def refuse(*a, **k): raise RuntimeError('network used')
socket.socket.connect = refuse
from pathlib import Path
from axis.cellular.service import CellularPharmacologyService
from axis.decision.service import DecisionService
from axis.discovery.curation import import_curated_erap1
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore
from axis.structures.service import StructureIdentityService
from axis.targets.identity import TargetIdentityService
from axis.computational.service import CampaignService
P = 'AXIS-DD-ERAP1-CURATED-001'
with EvidenceStore(Path(sys.argv[1] + '.erap')) as s:
    import_curated_erap1(s)
    p = TargetIdentityService(s).import_package(P)
    StructureIdentityService(s).import_package(P, p)
    PharmacologyService(s).import_package(P, p)
    CellularPharmacologyService(s).import_package(P, p)
    DecisionService(s).import_package(P, p)
    c = CampaignService(s)
    cid = c.register('erap1'); c.prepare(cid); r = c.run(cid)
    v = c.view(cid)['prioritization']
    print('ERAP1 campaign', r['outcome'], 'panel', len(v['panel']), 'docking', v['docking']['status'])
"""


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
        erap = subprocess.run(
            [str(bin_dir / "python"), "-c", ERAP_SNIPPET, db],
            capture_output=True,
            text=True,
        )
        if erap.returncode != 0 or "panel" not in erap.stdout:
            print(erap.stdout, erap.stderr)
            return 1
        print(erap.stdout.strip())
        print("installed wheel replays the computational campaigns offline: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
