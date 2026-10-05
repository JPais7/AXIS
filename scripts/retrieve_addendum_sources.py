"""Bounded public retrieval; article bodies stay outside the repository."""

import hashlib
import json
import tempfile
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "axis/resources/evidence-addendum/erap1-axspa/2020-2026/v1"
QUERIES = [
    "ERAP1 AND (ankylosing OR spondyloarthritis) AND (genetic OR allotype)",
    'ERAP1 AND (HLA-B27 OR "HLA-B*27") AND (peptide OR CD8)',
    "ERAP1 AND (deficiency OR knockout OR macrophage)",
    "ERAP1 AND (immunopeptidome OR immunopeptidomics)",
    "ERAP1 AND (inhibitor OR selectivity) AND (cellular OR allosteric)",
    "ERAP1 AND (structure OR crystallography OR ligand)",
    "ERAP1 AND (engagement OR dependency OR clinical)",
    "ERAP1 AND (Mendelian OR corilagin OR carnosic)",
]
SEEDS = [
    "35954271",
    "36577442",
    "36804470",
    "37686141",
    "40349828",
    "40680611",
    "33617882",
    "39691536",
    "39024058",
]


def request(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def search(query):
    url = (
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
        + urllib.parse.urlencode(
            {"query": query, "format": "json", "resultType": "core", "pageSize": 40}
        )
    )
    raw = request(url)
    data = json.loads(raw)
    return {
        "query": query,
        "url": url,
        "hit_count": data["hitCount"],
        "returned": len(data["resultList"]["result"]),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "records": data["resultList"]["result"],
    }


def main():
    if (PACKAGE / "search-log.json").exists():
        raise SystemExit("Refusing to overwrite frozen retrieval")
    queries = [q + " AND FIRST_PDATE:[2020-01-01 TO 2026-10-05]" for q in QUERIES]
    queries += ["EXT_ID:" + seed + " AND SRC:MED" for seed in SEEDS]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(search, queries))
    records = {}
    for row in results:
        for record in row["records"]:
            records[record["source"] + ":" + record["id"]] = record
    metadata = [
        {
            k: r.get(k)
            for k in (
                "id",
                "source",
                "pmid",
                "pmcid",
                "doi",
                "title",
                "firstPublicationDate",
                "pubYear",
                "pubTypeList",
                "isOpenAccess",
                "inPMC",
                "fullTextUrlList",
            )
        }
        for r in records.values()
    ]
    (PACKAGE / "search-log.json").write_text(
        json.dumps(
            {
                "access_date": "2026-10-05",
                "comprehensive": False,
                "queries": [
                    {k: v for k, v in r.items() if k != "records"} for r in results
                ],
            },
            indent=2,
        )
        + "\n"
    )
    (PACKAGE / "discovery-metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    cache = Path(tempfile.mkdtemp(prefix="axis-addendum-primary-"))
    print("READ_ONLY_ARTICLE_CACHE", cache)
    for record in metadata:
        if record["pmcid"]:
            print(
                record["id"],
                record["pmcid"],
                record["firstPublicationDate"],
                record["title"],
            )


if __name__ == "__main__":
    main()
