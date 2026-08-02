from __future__ import annotations

import csv
import html
import json
import re
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/analysis/single-cell-validation/CD8-evidence-review/europe-pmc-2026-07-30"
QUERY = (
    '(TITLE_ABS:"ankylosing spondylitis" OR '
    'TITLE_ABS:"axial spondyloarthritis") AND '
    '(TITLE_ABS:"single cell" OR TITLE_ABS:"single-cell") AND '
    '(TITLE_ABS:transcriptom* OR TITLE_ABS:"RNA sequencing")'
)


def clean(value: object) -> str:
    text = html.unescape(str(value or ""))
    return re.sub(r"<[^>]+>", "", text).strip()


def normalized_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def preliminary_screen(title: str, abstract: str, pub_type: str) -> tuple[str, str]:
    combined = f"{title} {abstract}".lower()
    title_lower = title.lower()
    if any(word in title_lower for word in (
        "review", "mechanistic insights", "emerging concepts",
        "evaluating methods", "systems biology", "multi-omics analysis",
    )):
        return "exclude_title_abstract", "review_or_secondary_reanalysis"
    if any(term in title_lower for term in (
        "mesenchymal stem", "fibroblast", "osteoclast", "neutrophil",
        "monocyte", "regulatory t cells", "th17 cells",
    )) and "cd8" not in combined and "pbmc" not in combined:
        return "exclude_title_abstract", "wrong_cell_or_tissue_context"
    if "crohn" in title_lower or "psoriasis" in title_lower or "uveitis" in title_lower:
        if "ankylosing" not in title_lower and "axial spondyloarthritis" not in title_lower:
            return "exclude_title_abstract", "wrong_primary_population"
    if "single" not in combined or not any(term in combined for term in (
        "rna", "transcriptom", "gene expression",
    )):
        return "exclude_title_abstract", "not_single_cell_rna_expression"
    if any(term in combined for term in (
        "healthy control", "healthy donor", "case-control", "case control",
        "control group", "controls",
    )):
        return "retrieve_full_text", "potential_human_case_control_single_cell_rna"
    if any(term in combined for term in ("patient", "ankylosing", "axial spondyloarthritis")):
        return "retrieve_full_text", "eligibility_or_control_status_unclear"
    if "preprint" in pub_type.lower():
        return "retrieve_full_text", "preprint_requires_duplicate_and_eligibility_check"
    return "exclude_title_abstract", "no_clear_eligible_human_case_control_design"


def main() -> None:
    params = urllib.parse.urlencode({
        "query": QUERY,
        "format": "json",
        "pageSize": "1000",
        "resultType": "core",
    })
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": "AXIS-systematic-review/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    results = payload.get("resultList", {}).get("result", [])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "raw-response.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    seen: dict[str, str] = {}
    rows: list[dict[str, str]] = []
    duplicates = 0
    for result in results:
        title = clean(result.get("title"))
        doi = clean(result.get("doi")).lower()
        pmid = clean(result.get("pmid"))
        key = doi or pmid or normalized_title(title)
        duplicate_of = seen.get(key, "")
        if duplicate_of:
            duplicates += 1
            decision, reason = "duplicate", f"duplicate_of_{duplicate_of}"
        else:
            seen[key] = pmid or doi or clean(result.get("id"))
            decision, reason = preliminary_screen(
                title,
                clean(result.get("abstractText")),
                clean(result.get("pubType")),
            )
        rows.append({
            "source_id": clean(result.get("id")),
            "source": clean(result.get("source")),
            "pmid": pmid,
            "pmcid": clean(result.get("pmcid")),
            "doi": doi,
            "title": title,
            "authors": clean(result.get("authorString")),
            "year": clean(result.get("pubYear")),
            "publication_type": clean(result.get("pubType")),
            "abstract": clean(result.get("abstractText")),
            "duplicate_of": duplicate_of,
            "preliminary_decision": decision,
            "preliminary_reason": reason,
            "human_reviewer_1": "",
            "human_reviewer_2": "",
            "consensus_decision": "",
            "full_text_exclusion_reason": "",
        })
    fields = list(rows[0]) if rows else []
    with (OUT / "records-screening.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    counts: dict[str, int] = {}
    for row in rows:
        decision = row["preliminary_decision"]
        counts[decision] = counts.get(decision, 0) + 1
    summary = {
        "database": "Europe PMC",
        "search_date": date.today().isoformat(),
        "coverage": "inception_to_search_date",
        "query": QUERY,
        "api_url": url,
        "records_retrieved": len(results),
        "duplicates_within_export": duplicates,
        "unique_records": len(results) - duplicates,
        "preliminary_decision_counts": counts,
        "screening_status": "automated_preliminary_triage_complete; independent_human_screening_pending",
        "protocol_role": (
            "open_second_bibliographic_source; complements but does not replace "
            "the planned Embase or Web of Science search"
        ),
    }
    (OUT / "search-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
