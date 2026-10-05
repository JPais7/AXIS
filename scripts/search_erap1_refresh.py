"""Explicit network search; freezes metadata and pagination/error logs for review."""

import concurrent.futures
import gzip
import json
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "axis/resources/evidence-refresh/erap1-axspa/2020-2026/v1"
P = json.loads((OUT / "protocol.json").read_text())
LOG = []
RECORDS = []


def get(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AXIS-EvidenceRefresh/1.0 (scientific metadata assessment)"
        },
    )
    with urllib.request.urlopen(request, timeout=45) as r:
        return json.loads(r.read())


def search(family, query):
    log = {
        "source": "Europe PMC",
        "family": family,
        "query": query + " AND FIRST_PDATE:[2020-01-01 TO 2026-10-05]",
        "executed_at": datetime.now(UTC).isoformat(),
        "date_filters": P["date_window"],
        "pagination": "incomplete",
        "retrieved_identifiers": [],
        "errors": [],
        "api": "REST search resultType=core",
    }
    records = []
    cursor = "*"
    pages = 0
    try:
        while True:
            params = urllib.parse.urlencode(
                {
                    "query": log["query"],
                    "format": "json",
                    "resultType": "core",
                    "pageSize": 1000,
                    "cursorMark": cursor,
                }
            )
            url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + params
            payload = get(url)
            pages += 1
            log["result_count"] = payload["hitCount"]
            items = payload["resultList"]["result"]
            for item in items:
                records.append(
                    {"database": "Europe PMC", "family": family, "metadata": item}
                )
                log["retrieved_identifiers"].append(
                    item.get("source", "") + ":" + item.get("id", "")
                )
            next_cursor = payload.get("nextCursorMark")
            if (
                not items
                or not next_cursor
                or next_cursor == cursor
                or len(records) >= payload["hitCount"]
            ):
                log["pagination"] = "complete"
                break
            cursor = next_cursor
        log["pages"] = pages
    except Exception as e:
        log["errors"].append(str(e))
    return log, records


with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    for log, records in pool.map(
        lambda item: search(*item), P["query_families"].items()
    ):
        LOG.append(log)
        RECORDS.extend(records)
        print(
            log["source"],
            log["family"],
            log.get("result_count"),
            log["pagination"],
            flush=True,
        )
for family, query in P["query_families"].items():
    log = {
        "source": "PubMed",
        "family": family,
        "query": query
        + ' AND ("2020/01/01"[Date - Publication] : "2026/10/05"[Date - Publication])',
        "executed_at": datetime.now(UTC).isoformat(),
        "errors": [],
        "pagination": "incomplete",
        "api": "NCBI ESearch JSON",
        "retrieved_identifiers": [],
    }
    try:
        params = urllib.parse.urlencode(
            {"db": "pubmed", "term": log["query"], "retmode": "json", "retmax": 9999}
        )
        data = get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + params
        )["esearchresult"]
        log["result_count"] = int(data["count"])
        log["retrieved_identifiers"] = data["idlist"]
        log["pagination"] = (
            "complete" if len(data["idlist"]) == int(data["count"]) else "incomplete"
        )
    except Exception as e:
        log["errors"].append(str(e))
    LOG.append(log)
    print("PubMed", family, log.get("result_count"), log["errors"], flush=True)
    time.sleep(0.4)
log = {
    "source": "Crossref",
    "query": "query.title=ERAP1",
    "date_filters": "from-pub-date:2020-01-01,until-pub-date:2026-10-05",
    "api": "REST /works cursor",
    "executed_at": datetime.now(UTC).isoformat(),
    "retrieved_identifiers": [],
    "errors": [],
    "pagination": "incomplete",
}
try:
    cursor = "*"
    while True:
        params = urllib.parse.urlencode(
            {
                "query.title": "ERAP1",
                "filter": log["date_filters"],
                "rows": 1000,
                "cursor": cursor,
            }
        )
        data = get("https://api.crossref.org/works?" + params)["message"]
        log["result_count"] = data["total-results"]
        for item in data["items"]:
            RECORDS.append({"database": "Crossref", "family": "all", "metadata": item})
            log["retrieved_identifiers"].append(item.get("DOI"))
        if (
            not data["items"]
            or len(log["retrieved_identifiers"]) >= data["total-results"]
        ):
            log["pagination"] = "complete"
            break
        cursor = data["next-cursor"]
except Exception as e:
    log["errors"].append(str(e))
LOG.append(log)
print("Crossref", log.get("result_count"), log["pagination"], flush=True)
(OUT / "search-log.json").write_text(json.dumps(LOG, indent=2) + "\n")
with gzip.open(OUT / "records.json.gz", "wt", encoding="utf-8") as handle:
    json.dump(RECORDS, handle, indent=2)
print("Frozen record occurrences", len(RECORDS), flush=True)
