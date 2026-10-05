"""Verify the installed wheel outside the repository with networking blocked.

Dependencies are reused from the validation runtime, not freshly downloaded.
The AXIS wheel itself is installed --no-index --no-deps in an isolated venv.
This is offline package replay, not an independent scientific/install review.
"""

import json
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

SNIPPET = """
import sys, socket, json
sys.path.append(sys.argv[1])  # dependencies only, after isolated venv site-packages
def refuse(*args, **kwargs): raise RuntimeError('network forbidden')
socket.socket.connect = refuse
import axis
assert sys.argv[2] in axis.__file__, axis.__file__
from axis.validation import prospective
from axis.validation.package import sha256_file
p = next(iter(prospective.registry_root().glob('*/v*/manifest.json'))).parent
b = prospective.load(p)
s = prospective.replay(b)
assert s == b['t0-state.json']
assert sha256_file(p / 'manifest.json') == (
    '7048400a3d71934ba0dd3cf407503b5020c8e1b9d432bf4351a78f7fea0834d7'
)
assert s['fingerprint'] == (
    '382ca252aa26afbb94df16e77a9c88268824191ae430e006027a03311e1f051e'
)
assert prospective.replay(b) == prospective.replay(b)
print(json.dumps({'installed_axis': axis.__file__, 'offline_replay': 'PASS',
                  't0': s['fingerprint']}))
"""


def main() -> None:
    wheel = Path(sys.argv[1]).resolve()
    dependency_site = next(p for p in sys.path if p.endswith("site-packages"))
    with tempfile.TemporaryDirectory(prefix="axis-prospective-wheel-") as tmp:
        env = Path(tmp) / "venv"
        venv.create(env, with_pip=True)
        python = env / "bin/python"
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                str(wheel),
            ],
            cwd=tmp,
            check=True,
        )
        output = subprocess.check_output(
            [str(python), "-c", SNIPPET, dependency_site, str(env)], cwd=tmp, text=True
        )
        print(json.dumps(json.loads(output), indent=2))


if __name__ == "__main__":
    main()
