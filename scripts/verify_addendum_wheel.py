"""Clean wheel install and isolated, network-denied frozen-package audit."""

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "axis/resources/evidence-addendum/erap1-axspa/2020-2026/v1/"


def run(args, cwd):
    return subprocess.run(
        args, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def main():
    task = Path(tempfile.mkdtemp(prefix="axis-addendum-wheel-"))
    run([sys.executable, "-m", "build", "--outdir", str(task / "dist")], ROOT)
    wheel = next((task / "dist").glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert not any("resources/evidence-refresh/" in n for n in names)
        manifest = json.loads(archive.read(PREFIX + "manifest.json"))
        assert all(PREFIX + e["path"] in names for e in manifest["files"])
    run([sys.executable, "-m", "venv", str(task / "venv")], task)
    python = task / "venv/bin/python"
    run(
        [str(python), "-m", "pip", "install", "--no-deps", "--no-index", str(wheel)],
        task,
    )
    snippet = (
        "import socket,json; "
        "socket.socket=lambda *a,**k:(_ for _ in ()).throw(AssertionError('network')); "
        "from axis.evidence_addendum import audit; "
        "print(json.dumps(audit(),sort_keys=True))"
    )
    source = json.loads(run([sys.executable, "-c", snippet], ROOT))
    installed = json.loads(run([str(python), "-I", "-c", snippet], task))
    assert source == installed
    assert installed["integrity_errors"] == []
    result = {
        "build": "PASS wheel and sdist",
        "install": "PASS clean venv, wheel only --no-deps --no-index",
        "offline_audit": "PASS network denied, isolated Python, non-repository cwd",
        "source_equals_installed": True,
        "raw_failed_refresh_excluded": True,
        "wheel_resources": len(manifest["files"]),
        "note": "This stdlib audit does not exercise the complete dependency CLI.",
        "audit": installed,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
