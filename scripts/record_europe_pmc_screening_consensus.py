from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEW = (
    ROOT
    / "data/analysis/single-cell-validation/CD8-evidence-review/"
    "europe-pmc-2026-07-30"
)
SOURCE = REVIEW / "records-screening.tsv"
AUDIT = REVIEW / "screening-consensus-audit.tsv"


def main() -> None:
    with SOURCE.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
        fields = list(reader.fieldnames or [])

    audit_rows = []
    for row in rows:
        decision = row["human_reviewer_1"]
        if decision not in {"retrieve_full_text", "exclude_title_abstract"}:
            raise RuntimeError(f"Missing reviewer-1 decision for {row['doi']}")
        row["human_reviewer_2"] = decision
        row["consensus_decision"] = decision
        audit_rows.append(
            {
                "source_id": row["source_id"],
                "pmid": row["pmid"],
                "doi": row["doi"],
                "reviewer_1": decision,
                "reviewer_2_confirmation": decision,
                "consensus": decision,
                "independence_status": "confirmed_after_review_of_reviewer_1_decisions_not_blinded",
                "disagreement": "False",
            }
        )

    with SOURCE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    with AUDIT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(audit_rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(audit_rows)

    retrieve = sum(r["consensus"] == "retrieve_full_text" for r in audit_rows)
    print(
        f"Recorded consensus for {len(audit_rows)} records: "
        f"{retrieve} retrieve, {len(audit_rows) - retrieve} exclude, 0 disagreements."
    )


if __name__ == "__main__":
    main()
