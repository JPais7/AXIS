"""Freeze one observation per participant for the SLE positive-control benchmark."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "biological" / "lupus-ifn-v1"
VISIT = re.compile(r"^(?P<subject>.+?)V(?P<visit>\d+)(?:_\d+)?$", re.IGNORECASE)


def freeze(accession: str) -> Path:
    source = (
        ROOT
        / "data"
        / "geo"
        / accession
        / "prepared"
        / f"{accession}_series_matrix"
        / "sample-groups.tsv"
    )
    with source.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    selected: dict[tuple[str, str], tuple[int, dict[str, str]]] = {}
    for row in rows:
        if row["group"] not in {"case", "control"}:
            continue
        title = row["title"].replace("SLE patient, ", "").strip()
        match = VISIT.match(title)
        if row["group"] == "case" and match:
            subject = match.group("subject")
            visit = int(match.group("visit"))
        else:
            subject = row["accession"]
            visit = 1
        key = (row["group"], subject)
        current = selected.get(key)
        if current is None or visit < current[0]:
            selected[key] = (visit, row)

    output = BENCHMARK / f"{accession}-first-visit-sample-sheet.tsv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("sample_id", "group", "subject_id", "visit_policy"),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for (group, subject), (visit, row) in sorted(selected.items()):
            writer.writerow(
                {
                    "sample_id": row["accession"],
                    "group": group,
                    "subject_id": subject,
                    "visit_policy": f"earliest_available_V{visit}",
                }
            )
    return output


if __name__ == "__main__":
    for study in ("GSE49454", "GSE61635"):
        print(freeze(study))
