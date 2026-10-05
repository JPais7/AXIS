"""Additive retrieval continuation; never edits frozen protocol or checkpoint.

This collects metadata, not scientific acceptance. Responses carry access logs;
the output remains separate from the original automated screening decisions.
"""

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "axis/resources/evidence-refresh/erap1-axspa/2020-2026/v1"
OUT = BASE / "continuation"
LOG: list[dict] = []


def retrieve(source: str, url: str) -> dict | None:
    """Record every attempt, including unsuccessful access; no bypasses."""
    entry = {
        "source": source,
        "url": url,
        "method": "GET",
        "executed_at": datetime.now(UTC).isoformat(),
    }
    LOG.append(entry)
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "AXIS-EvidenceRefresh/1.0"}
        )
        with urllib.request.urlopen(req, timeout=25) as response:
            raw = response.read()
            entry["http_status"] = response.status
        entry["sha256"] = hashlib.sha256(raw).hexdigest()
        result = json.loads(raw)
        entry["status"] = "retrieved"
        return result
    except (OSError, ValueError) as error:
        entry["status"] = "unavailable"
        entry["error"] = str(error)
        if isinstance(error, urllib.error.HTTPError):
            entry["http_status"] = error.code
        return None


def epmc(query: str) -> dict | None:
    params = urllib.parse.urlencode(
        {"query": query, "format": "json", "resultType": "core", "pageSize": 1000}
    )
    return retrieve(
        "Europe PMC metadata resolution",
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + params,
    )


def save(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n")
    save_log = OUT / "access-log.json"
    save_log.write_text(json.dumps(LOG, indent=2) + "\n")


def main() -> None:
    if OUT.exists():
        raise SystemExit("Continuation exists: preserve it; select a new version.")
    OUT.mkdir()
    unique = json.loads((BASE / "unique-records.json").read_text())
    missing = [record for record in unique if not record["abstract"]]
    resolved = []
    dois = [record["doi"] for record in missing if record["doi"]]
    for start in range(0, len(dois), 20):
        query = " OR ".join('DOI:"' + doi + '"' for doi in dois[start : start + 20])
        response = epmc("(" + query + ")")
        if response:
            resolved.extend(response["resultList"]["result"])
    save("metadata-resolution.json", resolved)
    print("Metadata resolution", len(resolved), flush=True)

    preprints = epmc("ERAP1 AND SRC:PPR AND FIRST_PDATE:[2020-01-01 TO 2026-10-05]")
    save("preprints.json", preprints)
    print("Preprints", preprints.get("hitCount") if preprints else None, flush=True)

    works = []
    cursor = "*"
    complete = False
    expected = None
    seen = set()
    while cursor and cursor not in seen:
        seen.add(cursor)
        params = urllib.parse.urlencode(
            {
                "search": "ERAP1",
                "filter": "from_publication_date:2020-01-01,"
                "to_publication_date:2026-10-05",
                "per-page": 200,
                "cursor": cursor,
            }
        )
        response = retrieve("OpenAlex", "https://api.openalex.org/works?" + params)
        if response is None:
            break
        expected = response["meta"]["count"]
        # Keep identity and scientific metadata, not redundant author profiles.
        fields = (
            "id",
            "doi",
            "title",
            "publication_date",
            "type",
            "ids",
            "abstract_inverted_index",
            "referenced_works",
        )
        works.extend(
            {key: work.get(key) for key in fields} for work in response["results"]
        )
        cursor = response["meta"].get("next_cursor")
        if not response["results"] or len(works) >= expected:
            complete = True
            break
        save("openalex-partial.json", works)
        print("OpenAlex", len(works), "/", expected, flush=True)
    save(
        "openalex.json",
        {
            "records": works,
            "expected": expected,
            "pagination": "complete" if complete else "incomplete",
        },
    )

    trials = []
    token = None
    complete = False
    seen = set()
    while token not in seen:
        seen.add(token)
        params = {"query.term": "ERAP1", "pageSize": 100, "countTotal": "true"}
        if token:
            params["pageToken"] = token
        response = retrieve(
            "ClinicalTrials.gov",
            "https://clinicaltrials.gov/api/v2/studies?"
            + urllib.parse.urlencode(params),
        )
        if response is None:
            break
        trials.extend(response.get("studies", []))
        token = response.get("nextPageToken")
        if not token:
            complete = True
            break
    save(
        "clinical-trials.json",
        {
            "studies": trials,
            "pagination": "complete" if complete else "incomplete",
        },
    )
    print("Trials", len(trials), complete, flush=True)

    # One-layer bibliographic expansion: candidates only, not automatic inclusion.
    expansion = []
    for pmid in ("39691536", "33617882", "36577442", "40680611", "39024058"):
        for relation in ("references", "citations"):
            url = (
                "https://www.ebi.ac.uk/europepmc/webservices/rest/MED/"
                + pmid
                + "/"
                + relation
                + "?format=json&pageSize=1000"
            )
            response = retrieve("Europe PMC one-layer " + relation, url)
            expansion.append(
                {
                    "seed_pmid": pmid,
                    "relation": relation,
                    "response": response,
                    "inclusion": "not_assessed",
                }
            )
    save("citation-expansion.json", expansion)

    structures = []
    identifiers = [
        record["doi"].split("/")[1][3:].upper()
        for record in missing
        if record["doi"].startswith("10.2210/pdb")
    ]
    for pdb in identifiers:
        data = retrieve(
            "RCSB entry " + pdb, "https://data.rcsb.org/rest/v1/core/entry/" + pdb
        )
        structures.append(
            {
                "pdb_id": pdb,
                "entry_metadata": data,
                "sequence_ligand_mapping": "not_assessed",
            }
        )
    save("structure-metadata.json", structures)
    print("Structure metadata", len(structures), flush=True)


if __name__ == "__main__":
    main()
