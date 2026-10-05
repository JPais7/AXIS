"""Versioned public metadata and lawful access attempts for the bounded addendum."""

import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

PACKAGE = (
    Path(__file__).resolve().parents[1]
    / "axis/resources/evidence-addendum/erap1-axspa/2020-2026/v1"
)


def main():
    destination = PACKAGE / "context-access.json"
    if destination.exists():
        raise SystemExit("Refusing to overwrite access snapshot")
    rows = []
    urls = []
    for doi in (
        "10.1016/j.clim.2023.109268",
        "10.1016/j.lfs.2025.123682",
        "10.1016/j.intimp.2025.115180",
        "10.1021/acs.jafc.4c00957",
    ):
        urls += [
            "https://api.openalex.org/works/https://doi.org/" + doi,
            "https://api.crossref.org/works/" + doi,
        ]
    urls += [
        "https://www.sciencedirect.com/science/article/pii/S1567576925011701",
        "https://pubs.acs.org/doi/10.1021/acs.jafc.4c00957",
        "https://clinicaltrials.gov/api/v2/studies?query.term=ERAP1&pageSize=20&format=json",
    ]
    urls += [
        "https://data.rcsb.org/rest/v1/core/entry/" + p
        for p in ("9GJN", "9GK6", "9GJS", "9GKE")
    ]
    urls += [
        "https://data.rcsb.org/rest/v1/core/polymer_entity/" + p + "/1"
        for p in ("9GJN", "9GK6", "9GJS", "9GKE")
    ]
    for url in urls:
        row = {"url": url, "access_date": "2026-10-05"}
        try:
            with urllib.request.urlopen(url, timeout=45) as response:
                raw = response.read()
                row.update(
                    status=response.status,
                    bytes=len(raw),
                    sha256=hashlib.sha256(raw).hexdigest(),
                )
                if "api." in url or "/api/" in url or "data.rcsb" in url:
                    row["response"] = json.loads(raw)
                else:
                    row["response_kind"] = "publisher_html_not_methods_adjudicated"
        except Exception as exc:
            row["error"] = str(exc)
        rows.append(row)
        print(url, row.get("status", row.get("error")), flush=True)
    destination.write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
