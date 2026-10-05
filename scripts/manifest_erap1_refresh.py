"""Freeze checksums for the partial continuation, without modifying v1."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "axis/resources/evidence-refresh/erap1-axspa/2020-2026/v1"
MANIFEST = BASE / "continuation/integrity-manifest.json"
EXCLUDED = {
    "records.json",
    "continuation/openalex.json",
    "continuation/openalex-partial.json",
    "continuation/integrity-manifest.json",
}
entries = []
for path in sorted(BASE.rglob("*")):
    name = path.relative_to(BASE).as_posix()
    if not path.is_file() or name in EXCLUDED or path.name == ".gitignore":
        continue
    if "__pycache__" in path.parts:
        continue
    raw = path.read_bytes()
    entries.append(
        {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    )
MANIFEST.write_text(
    json.dumps(
        {
            "status": "partial_refresh_not_scientific_closure",
            "path_semantics": "relative_to_packaged_refresh_root",
            "files": entries,
        },
        indent=2,
    )
    + "\n"
)
print(len(entries), "files", sum(entry["bytes"] for entry in entries), "bytes")
