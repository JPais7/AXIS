"""Conservative proposed sample sheets and cross-study independence gates."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class SampleProposalRun:
    studies: int
    axspa_candidates: int
    related_disease_exclusions: int
    non_expression_exclusions: int
    output_path: Path
    summary_path: Path
    sheets_root: Path


class ProposedSampleSheetBuilder:
    """Build editable proposals without granting scientific eligibility."""

    AXSPA = re.compile(
        r"ankylosing spondylitis|\baxspa\b|axial spondyloarthritis",
        re.IGNORECASE,
    )
    PSORIATIC = re.compile(r"psoriatic arthritis|\bpsa\b|psoriasis", re.IGNORECASE)
    NON_EXPRESSION = re.compile(
        r"\bhi[\s-]?c\b|\batac[\s-]?seq\b|chromatin accessibility|"
        r"chromatin conformation",
        re.IGNORECASE,
    )

    def build(
        self,
        *,
        design_queue_path: str | Path = Path(
            "data/catalog/sample-audit/design-review-queue.tsv"
        ),
        sample_metadata_path: str | Path = Path(
            "data/catalog/sample-audit/sample-metadata.tsv"
        ),
        catalog_path: str | Path = Path("data/catalog/study-catalog.tsv"),
        output_root: str | Path = Path("data/catalog/sample-proposals"),
    ) -> SampleProposalRun:
        queue = self._read(design_queue_path)
        samples = self._read(sample_metadata_path)
        catalog = {row["accession"]: row for row in self._read(catalog_path)}
        by_study: dict[str, list[dict[str, str]]] = {}
        for sample in samples:
            by_study.setdefault(sample["study_accession"], []).append(sample)

        destination = Path(output_root)
        sheets_root = destination / "sheets"
        sheets_root.mkdir(parents=True, exist_ok=True)
        validations: list[dict[str, object]] = []
        for queued in queue:
            accession = queued["accession"]
            study_samples = by_study.get(accession, [])
            metadata = catalog.get(accession)
            if metadata is None:
                raise ValueError(f"{accession} is missing from the study catalog")
            validation, proposed = self._validate(queued, metadata, study_samples)
            sheet_path = sheets_root / accession / "proposed-sample-sheet.tsv"
            sheet_path.parent.mkdir(parents=True, exist_ok=True)
            self._write(sheet_path, proposed)
            validation["proposed_sheet"] = str(sheet_path)
            validations.append(validation)

        self._assign_evidence_clusters(validations)
        validations.sort(
            key=lambda row: (
                row["validation_status"] != "axspa_design_review_candidate",
                str(row["accession"]),
            )
        )
        output_path = destination / "study-validation.tsv"
        summary_path = destination / "sample-proposals.json"
        self._write(output_path, validations)
        statuses = Counter(str(row["validation_status"]) for row in validations)
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "proposed_sample_sheets_and_independence_audit",
                    "created_at": datetime.now(UTC).isoformat(),
                    "studies": len(validations),
                    "validation_statuses": dict(sorted(statuses.items())),
                    "automatic_eligibility": False,
                    "independence_policy": (
                        "Series sharing a publication or BioProject are assigned "
                        "the same evidence cluster and must not be counted as "
                        "independent replication without participant verification."
                    ),
                    "warning": (
                        "All sample groups and inclusion actions are proposals. "
                        "A reviewer must confirm diagnosis, treatment, participant "
                        "identity, cell type and covariates."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return SampleProposalRun(
            studies=len(validations),
            axspa_candidates=statuses["axspa_design_review_candidate"],
            related_disease_exclusions=statuses["related_disease_context_only"],
            non_expression_exclusions=statuses["non_expression_context_only"],
            output_path=output_path,
            summary_path=summary_path,
            sheets_root=sheets_root,
        )

    def _validate(
        self,
        queue: dict[str, str],
        catalog: dict[str, str],
        samples: list[dict[str, str]],
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        study_text = f"{catalog['title']} {catalog['summary']}"
        sample_text = " ".join(
            f"{row['title']} {row['characteristics']}" for row in samples
        )
        axspa = self.AXSPA.search(f"{study_text} {sample_text}") is not None
        psoriatic = self.PSORIATIC.search(f"{study_text} {sample_text}") is not None
        non_expression = self.NON_EXPRESSION.search(catalog["title"]) is not None
        if non_expression:
            status = "non_expression_context_only"
            rationale = "Series title identifies a chromatin assay, not expression."
        elif psoriatic and not axspa:
            status = "related_disease_context_only"
            rationale = "Samples identify psoriatic disease rather than axSpA."
        elif not axspa:
            status = "diagnosis_verification_required"
            rationale = "No explicit axSpA diagnosis was found at sample level."
        else:
            status = "axspa_design_review_candidate"
            rationale = "Explicit axSpA disease signal found; manual review remains."

        proposed = [
            self._proposed_sample(
                row,
                study_status=status,
            )
            for row in samples
        ]
        actions = Counter(str(row["proposed_action"]) for row in proposed)
        return (
            {
                "accession": queue["accession"],
                "validation_status": status,
                "rationale": rationale,
                "assay_title": catalog["title"],
                "publication_ids": catalog.get("publication_ids", ""),
                "bioproject_id": catalog.get("bioproject_id", ""),
                "evidence_cluster": "",
                "cluster_members": "",
                "independence_status": "",
                "shared_publication_flag": catalog.get("shared_publication_flag", ""),
                "shared_bioproject_flag": catalog.get("shared_bioproject_flag", ""),
                "samples": len(samples),
                "proposed_include": actions["propose_include"],
                "proposed_exclude": actions["propose_exclude"],
                "requires_review": actions["review_before_inclusion"],
                "automatic_eligibility": False,
            },
            proposed,
        )

    def _proposed_sample(
        self, row: dict[str, str], *, study_status: str
    ) -> dict[str, object]:
        group = row["suggested_group"]
        treatment = row["treatment_signal"]
        if study_status != "axspa_design_review_candidate":
            action = "propose_exclude"
            reason = study_status
        elif group not in {"case", "control"}:
            action = "propose_exclude"
            reason = f"group_{group}"
        elif treatment == "treated":
            action = "propose_exclude"
            reason = "treated_sample"
        elif group == "case" and treatment == "unknown":
            action = "review_before_inclusion"
            reason = "case_treatment_unknown"
        else:
            action = "propose_include"
            reason = ""
        characteristics = self._characteristics(row["characteristics"])
        return {
            "sample_id": row["sample_accession"],
            "proposed_group": group,
            "proposed_action": action,
            "exclusion_or_review_reason": reason,
            "subject": row["subject_identifier"]
            or self._participant_from_title(row["title"]),
            "cell_or_tissue": row["source"],
            "treatment_signal": treatment,
            "sex": characteristics.get(
                "sex",
                characteristics.get("gender", self._sex_from_title(row["title"])),
            ),
            "age": characteristics.get("age", ""),
            "batch": characteristics.get("batch", ""),
            "title": row["title"],
            "characteristics": row["characteristics"],
            "reviewed": False,
        }

    @staticmethod
    def _assign_evidence_clusters(rows: list[dict[str, object]]) -> None:
        parents = {str(row["accession"]): str(row["accession"]) for row in rows}

        def find(accession: str) -> str:
            while parents[accession] != accession:
                parents[accession] = parents[parents[accession]]
                accession = parents[accession]
            return accession

        def union(left: str, right: str) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parents[max(left_root, right_root)] = min(left_root, right_root)

        for index, left in enumerate(rows):
            left_publications = set(
                filter(None, str(left["publication_ids"]).split("|"))
            )
            left_project = str(left["bioproject_id"])
            for right in rows[index + 1 :]:
                right_publications = set(
                    filter(None, str(right["publication_ids"]).split("|"))
                )
                same_publication = bool(left_publications & right_publications)
                same_project = bool(
                    left_project and left_project == str(right["bioproject_id"])
                )
                if same_publication or same_project:
                    union(str(left["accession"]), str(right["accession"]))

        clusters: dict[str, list[str]] = {}
        for accession in parents:
            clusters.setdefault(find(accession), []).append(accession)
        for row in rows:
            members = sorted(clusters[find(str(row["accession"]))])
            row["evidence_cluster"] = (
                f"cluster:{'+'.join(members)}"
                if len(members) > 1
                else f"accession:{members[0]}"
            )
            row["cluster_members"] = "|".join(members)
            row["independence_status"] = (
                "shared_source_cluster"
                if len(members) > 1
                else "no_catalog_overlap_detected"
            )

    @staticmethod
    def _participant_from_title(title: str) -> str:
        match = re.search(
            r"\b(healthy|control|hc|axspa|as|psa|patient)"
            r"[-_ ]*(?:[fm][-_ ]*)?(\d+)\b",
            title,
            re.IGNORECASE,
        )
        if match is None:
            return ""
        return f"{match.group(1).lower()}-{match.group(2)}"

    @staticmethod
    def _sex_from_title(title: str) -> str:
        match = re.search(r"(?:^|[_ -])([FM])(?:[_ -]?\d+)(?:$|[_ -])", title)
        if match is None:
            return ""
        return "female" if match.group(1) == "F" else "male"

    @staticmethod
    def _characteristics(value: str) -> dict[str, str]:
        parsed: dict[str, str] = {}
        for item in value.split("|"):
            key, separator, item_value = item.partition(":")
            if separator and key.strip() and item_value.strip():
                normalized = key.strip().lower()
                if normalized in {"age (yr)", "age (years)", "age (year)"}:
                    normalized = "age"
                parsed[normalized] = item_value.strip()
        return parsed

    @staticmethod
    def _read(path: str | Path) -> list[dict[str, str]]:
        with Path(path).open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("accession",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
