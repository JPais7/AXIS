"""Retrieve public PMC XML for reading, outside versioned resources."""

import hashlib
import json
import tempfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "axis/resources/evidence-refresh/erap1-axspa/2020-2026/v1/continuation"


def main() -> None:
    log_path = OUT / "additional-fulltext-access.json"
    if log_path.exists():
        raise SystemExit("Access log exists; do not overwrite historical attempts.")
    cache = Path(tempfile.mkdtemp(prefix="axis-refresh-reading-"))
    log = []
    for pmcid in ("9892207", "11647717", "8024916"):
        url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            "?db=pmc&id=" + pmcid
        )
        entry = {
            "id": "PMC" + pmcid,
            "url": url,
            "method": "GET",
            "executed_at": datetime.now(UTC).isoformat(),
            "cache_semantics": "historical_local_reading_only_not_replay_input",
        }
        try:
            with urllib.request.urlopen(url, timeout=25) as response:
                raw = response.read()
                entry["http_status"] = response.status
            # A 200 response with an error body is not successful full-text access.
            if b"<body>" not in raw:
                raise ValueError("No article body returned")
            path = cache / ("PMC" + pmcid + ".xml")
            path.write_bytes(raw)
            entry.update(
                status="retrieved_for_reading_not_redistributed",
                sha256=hashlib.sha256(raw).hexdigest(),
                bytes=len(raw),
            )
            print(entry["id"], path, flush=True)
        except (OSError, ValueError) as error:
            entry.update(status="unavailable", error=str(error))
        log.append(entry)
    log_path.write_text(json.dumps(log, indent=2) + "\n")


if __name__ == "__main__":
    main()
