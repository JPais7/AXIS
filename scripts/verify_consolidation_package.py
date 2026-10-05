"""Verify wheel/sdist resource identity against the pre-refactor audit manifest."""

import argparse
import hashlib
import json
import tarfile
import zipfile
from pathlib import Path


def verify(directory: Path, baseline: Path) -> dict[str, object]:
    expected = json.loads(baseline.read_text())["protected_hashes"]
    expected = {p: h for p, h in expected.items() if p.startswith("axis/resources/")}
    wheel = next(directory.glob("*.whl"))
    sdist = next(directory.glob("*.tar.gz"))
    with zipfile.ZipFile(wheel) as archive:
        for path, digest in expected.items():
            if hashlib.sha256(archive.read(path)).hexdigest() != digest:
                raise ValueError("wheel changed frozen resource: " + path)
        profile = "axis/resources/cases/erap1-axspa.json"
        configuration_present = profile in archive.namelist()
        resource_bytes = sum(
            entry.file_size
            for entry in archive.infolist()
            if entry.filename.startswith("axis/resources/")
        )
    with tarfile.open(sdist) as archive:
        prefix = archive.getnames()[0].split("/")[0]
        for path, digest in expected.items():
            member = archive.extractfile(prefix + "/" + path)
            if member is None or hashlib.sha256(member.read()).hexdigest() != digest:
                raise ValueError("sdist changed frozen resource: " + path)
    return {
        "status": "PASS",
        "frozen_resource_files": len(expected),
        "frozen_resource_bytes": sum(
            Path(baseline.parents[3] / path).stat().st_size for path in expected
        ),
        "wheel_bytes": wheel.stat().st_size,
        "sdist_bytes": sdist.stat().st_size,
        "wheel_resource_bytes": resource_bytes,
        "new_case_configuration_present": configuration_present,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "sdist_sha256": hashlib.sha256(sdist.read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("baseline", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.directory, args.baseline.resolve()), indent=2))
