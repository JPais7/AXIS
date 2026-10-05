"""Check lawful public access for decision-material unresolved papers.

Retains receipts and bibliographic/access metadata only. No authentication,
paywall bypass, publisher main text redistribution or scientific self-approval.
"""

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = (
    ROOT
    / "axis/resources/evidence-refresh/erap1-axspa/2020-2026/v1"
    / "closure-attempt-1"
)
LOG = []


def fetch(source, url, payload=None):
    entry = {
        "source": source,
        "url": url,
        "method": "POST" if payload is not None else "GET",
        "executed_at": datetime.now(UTC).isoformat(),
    }
    LOG.append(entry)
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={
                "User-Agent": "AXIS-EvidenceRefresh/1.0",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            entry.update(
                http_status=response.status,
                content_type=response.headers.get("Content-Type"),
                bytes=len(raw),
                response_sha256=hashlib.sha256(raw).hexdigest(),
            )
        entry["status"] = "retrieved_response_not_automatically_full_text"
        try:
            return json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return None
    except (OSError, ValueError) as error:
        entry.update(status="unavailable", error=str(error))
        if isinstance(error, urllib.error.HTTPError):
            entry["http_status"] = error.code
        return None


def main():
    if OUT.exists():
        raise SystemExit("Preserve previous attempts; do not overwrite output.")
    OUT.mkdir()
    metadata = []
    for doi in ("10.1016/j.intimp.2025.115180", "10.1021/acs.jafc.4c00957"):
        oa = fetch(
            "OpenAlex public locations",
            "https://api.openalex.org/works/"
            + urllib.parse.quote("https://doi.org/" + doi, safe=""),
        )
        cr = fetch(
            "Crossref full-text links",
            "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe=""),
        )
        query = urllib.parse.urlencode(
            {"query": 'DOI:"' + doi + '"', "format": "json", "resultType": "core"}
        )
        ep = fetch(
            "Europe PMC public access metadata",
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + query,
        )
        metadata.append(
            {
                "doi": doi,
                "openalex": {
                    key: oa.get(key)
                    for key in ("id", "open_access", "locations", "best_oa_location")
                }
                if oa
                else None,
                "crossref": {
                    key: cr["message"].get(key)
                    for key in ("link", "license", "relation")
                }
                if cr
                else None,
                "epmc_access": [
                    {
                        key: record.get(key)
                        for key in (
                            "id",
                            "pmcid",
                            "isOpenAccess",
                            "fullTextUrlList",
                            "firstPublicationDate",
                        )
                    }
                    for record in ep["resultList"]["result"]
                ]
                if ep
                else None,
            }
        )
        print(doi, metadata[-1]["openalex"], flush=True)
    figshare = fetch(
        "ACS Figshare public supporting-information search",
        "https://api.figshare.com/v2/articles/search",
        {"search_for": '"Carnosic Acid" "ERAP1"', "limit": 100},
    )
    for source, url in (
        (
            "Corilagin publisher",
            "https://www.sciencedirect.com/science/article/pii/S1567576925011701",
        ),
        (
            "Corilagin public preprint",
            "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5093704",
        ),
        (
            "Carnosic publisher",
            "https://pubs.acs.org/doi/full/10.1021/acs.jafc.4c00957",
        ),
    ):
        fetch(source, url)
        print(source, LOG[-1]["status"], LOG[-1].get("http_status"), flush=True)
    (OUT / "public-access-metadata.json").write_text(
        json.dumps({"papers": metadata, "figshare_search": figshare}, indent=2) + "\n"
    )
    (OUT / "access-log.json").write_text(json.dumps(LOG, indent=2) + "\n")


if __name__ == "__main__":
    main()
