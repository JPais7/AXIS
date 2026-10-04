"""Fetch real publication/availability dates for the ERAP1 benchmark sources.

Network is used ONLY by this build-time script; sealed benchmarks replay offline from
the checked-in JSON it writes. Dates are never invented: each entry records the
PubMed esummary fields, the retrieval time and the SHA-256 of the raw response.
"""

import hashlib
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

PMIDS = [
    "16286653",
    "21743469",
    "24504800",
    "25994336",
    "26130142",
    "27107845",
    "31841350",
]
OUT = Path(sys.argv[1])


def day(text: str | None) -> str | None:
    if not text:
        return None
    return text.replace("/", "-").split(" ")[0]


def main() -> None:
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id="
        + ",".join(PMIDS)
        + "&retmode=json"
    )
    raw = urllib.request.urlopen(url, timeout=30).read()
    data = json.loads(raw)
    pdb_url = "https://data.rcsb.org/rest/v1/core/entry/3QNF"
    pdb_raw = urllib.request.urlopen(pdb_url, timeout=30).read()
    pdb = json.loads(pdb_raw)
    sources = {}
    for pmid in PMIDS:
        record = data["result"][pmid]
        history = {h["pubstatus"]: day(h["date"]) for h in record.get("history", [])}
        epub = record.get("epubdate") or None
        candidates = [
            d for d in (day(history.get("pubmed")), day(history.get("entrez"))) if d
        ]
        first = min(candidates) if candidates else None
        sources[f"PMID:{pmid}"] = {
            "title": record["title"],
            "nominal_publication_date": record["pubdate"],
            "epub_date": epub,
            "history": history,
            "first_publicly_accessible_date": first,
            "availability_kind": "bounded",
            "availability_basis": (
                "earliest PubMed listing date (pubmed/entrez history); the epub date "
                "may precede it by days; no earlier public access is claimed"
            ),
        }
    info = pdb["rcsb_accession_info"]
    sources["PDB:3QNF"] = {
        "title": pdb["struct"]["title"],
        "nominal_publication_date": info["initial_release_date"][:10],
        "deposit_date": info["deposit_date"][:10],
        "first_publicly_accessible_date": info["initial_release_date"][:10],
        "availability_kind": "established",
        "availability_basis": "RCSB initial release date",
    }
    document = {
        "resource": "temporal-availability",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "retrieval": [
            {"url": url, "sha256": hashlib.sha256(raw).hexdigest()},
            {"url": pdb_url, "sha256": hashlib.sha256(pdb_raw).hexdigest()},
        ],
        "note": (
            "Publication date, online date and first public accessibility are "
            "distinct; eligibility uses first_publicly_accessible_date, never the "
            "nominal year."
        ),
        "sources": sources,
    }
    OUT.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
