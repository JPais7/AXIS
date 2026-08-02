"""Prepare and summarize a guarded human comparison of analysis workflows."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

WORKFLOWS = ("axis", "geo2r", "manual_statistics", "networkanalyst")
RATINGS = ("pass", "fail", "not_applicable")
TASK_CRITERIA = {
    "A": (
        "installation_success",
        "wall_clock_time_recorded",
        "memory_method_declared",
        "output_size_recorded",
        "manual_decisions_recorded",
    ),
    "B": (
        "disease_mismatch_detected",
        "tissue_mismatch_detected",
        "treatment_detected",
        "pooled_samples_detected",
        "repeated_participants_detected",
        "repository_duplicate_detected",
    ),
    "C": (
        "gene_identifiers_preserved",
        "effect_direction_correct",
        "multiplicity_correction_recorded",
        "method_record_complete",
        "executable_or_machine_readable_export",
    ),
    "D": (
        "participants_counted_correctly",
        "duplicate_participants_not_double_counted",
        "incompatible_evidence_not_pooled",
        "input_output_provenance_preserved",
        "conclusion_bounded_to_association",
    ),
}


@dataclass(frozen=True)
class ComparisonPreparation:
    output_root: Path
    manifest_path: Path
    assessment_template_path: Path


@dataclass(frozen=True)
class ComparisonSummary:
    report_path: Path
    ratings_path: Path
    article_table_path: Path
    consensus_template_path: Path
    disagreements: int
    unresolved_disagreements: int


class WorkflowComparisonPreparer:
    """Create public evaluator files and a separately held reference."""

    def prepare(
        self,
        *,
        output_root: str | Path = Path("workflow-comparison"),
    ) -> ComparisonPreparation:
        output = Path(output_root).resolve()
        public = output / "evaluator-package"
        reference = output / "coordinator-reference"
        public.mkdir(parents=True, exist_ok=True)
        reference.mkdir(parents=True, exist_ok=True)

        self._write_rows(public / "candidate-studies.tsv", self._candidate_studies())
        self._write_rows(public / "sample-metadata.tsv", self._sample_metadata())
        self._write_rows(public / "expression-matrix.tsv", self._expression_matrix())
        self._write_rows(public / "cohort-evidence.tsv", self._cohort_evidence())
        self._write_rows(public / "tasks.tsv", self._tasks())

        template_rows = [
            {
                "reviewer": "",
                "workflow": workflow,
                "task": task,
                "criterion": criterion,
                "rating": "",
                "elapsed_seconds": "",
                "manual_decisions": "",
                "evidence": "",
                "notes": "",
            }
            for workflow in WORKFLOWS
            for task, criteria in TASK_CRITERIA.items()
            for criterion in criteria
        ]
        template = public / "assessment-template.tsv"
        self._write_rows(template, template_rows)
        self._write_rows(
            reference / "expected-study-decisions.tsv", self._study_reference()
        )
        self._write_rows(
            reference / "expected-expression.tsv", self._expression_reference()
        )
        self._write_rows(
            reference / "expected-evidence-roles.tsv", self._evidence_reference()
        )

        instructions = public / "README.md"
        instructions.write_text(self._instructions(), encoding="utf-8")
        reference_note = reference / "README.md"
        reference_note.write_text(
            "# Coordinator reference\n\n"
            "Do not provide this directory to reviewers until both initial "
            "assessment files have been frozen. Preserve disagreements before "
            "consensus.\n",
            encoding="utf-8",
        )

        manifest_path = output / "manifest.json"
        files = sorted(
            path
            for path in output.rglob("*")
            if path.is_file() and path != manifest_path
        )
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "protocol": "AXIS workflow comparison v1",
                    "synthetic": True,
                    "created_at": datetime.now(UTC).isoformat(),
                    "workflows": list(WORKFLOWS),
                    "ratings": list(RATINGS),
                    "no_weighted_overall_score": True,
                    "files": [
                        {
                            "path": path.relative_to(output).as_posix(),
                            "sha256": self._sha256(path),
                        }
                        for path in files
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return ComparisonPreparation(output, manifest_path, template)

    @staticmethod
    def _candidate_studies() -> list[dict[str, object]]:
        return [
            {
                "study_id": "SYN001",
                "disease": "axSpA",
                "tissue": "blood",
                "treatment": "untreated",
                "design": "individual",
                "participant_source": "COHORT-A",
                "repository": "GEO",
            },
            {
                "study_id": "SYN002",
                "disease": "rheumatoid arthritis",
                "tissue": "blood",
                "treatment": "untreated",
                "design": "individual",
                "participant_source": "COHORT-C",
                "repository": "GEO",
            },
            {
                "study_id": "SYN003",
                "disease": "axSpA",
                "tissue": "synovium",
                "treatment": "untreated",
                "design": "individual",
                "participant_source": "COHORT-D",
                "repository": "GEO",
            },
            {
                "study_id": "SYN004",
                "disease": "axSpA",
                "tissue": "blood",
                "treatment": "post-treatment",
                "design": "individual",
                "participant_source": "COHORT-E",
                "repository": "GEO",
            },
            {
                "study_id": "SYN005",
                "disease": "axSpA",
                "tissue": "blood",
                "treatment": "untreated",
                "design": "pooled",
                "participant_source": "COHORT-F",
                "repository": "SRA",
            },
            {
                "study_id": "SYN006",
                "disease": "axSpA",
                "tissue": "blood",
                "treatment": "untreated",
                "design": "individual",
                "participant_source": "COHORT-B",
                "repository": "GEO",
            },
            {
                "study_id": "SYN007",
                "disease": "axSpA",
                "tissue": "blood",
                "treatment": "untreated",
                "design": "individual",
                "participant_source": "COHORT-B",
                "repository": "ArrayExpress",
            },
            {
                "study_id": "SYN008",
                "disease": "axSpA",
                "tissue": "blood",
                "treatment": "untreated",
                "design": "repeated",
                "participant_source": "COHORT-G",
                "repository": "GEO",
            },
        ]

    @staticmethod
    def _sample_metadata() -> list[dict[str, str]]:
        return [
            {"sample": f"CASE{i}", "group": "case", "participant": f"P{i}"}
            for i in range(1, 5)
        ] + [
            {"sample": f"CTRL{i}", "group": "control", "participant": f"P{i + 4}"}
            for i in range(1, 5)
        ]

    @staticmethod
    def _expression_matrix() -> list[dict[str, object]]:
        return [
            {
                "gene": "GENEA",
                "CASE1": 10,
                "CASE2": 11,
                "CASE3": 9,
                "CASE4": 10,
                "CTRL1": 5,
                "CTRL2": 6,
                "CTRL3": 4,
                "CTRL4": 5,
            },
            {
                "gene": "GENEB",
                "CASE1": 2,
                "CASE2": 3,
                "CASE3": 2,
                "CASE4": 3,
                "CTRL1": 8,
                "CTRL2": 7,
                "CTRL3": 9,
                "CTRL4": 8,
            },
            {
                "gene": "GENEC",
                "CASE1": 6,
                "CASE2": 5,
                "CASE3": 7,
                "CASE4": 6,
                "CTRL1": 6,
                "CTRL2": 5,
                "CTRL3": 7,
                "CTRL4": 6,
            },
        ]

    @staticmethod
    def _cohort_evidence() -> list[dict[str, object]]:
        return [
            {
                "cohort": "COHORT-A",
                "participants": 20,
                "effect": -0.20,
                "cell_definition": "CD8_memory",
                "role_hint": "primary",
                "participant_source": "COHORT-A",
            },
            {
                "cohort": "COHORT-B",
                "participants": 16,
                "effect": -0.12,
                "cell_definition": "CD8_memory",
                "role_hint": "primary",
                "participant_source": "COHORT-B",
            },
            {
                "cohort": "COHORT-B-REPOSITORY-COPY",
                "participants": 16,
                "effect": -0.12,
                "cell_definition": "CD8_memory",
                "role_hint": "duplicate",
                "participant_source": "COHORT-B",
            },
            {
                "cohort": "COHORT-H",
                "participants": 12,
                "effect": -0.08,
                "cell_definition": "broad_CD8",
                "role_hint": "sensitivity",
                "participant_source": "COHORT-H",
            },
            {
                "cohort": "COHORT-I",
                "participants": 18,
                "effect": 0.04,
                "cell_definition": "whole_blood",
                "role_hint": "incompatible",
                "participant_source": "COHORT-I",
            },
        ]

    @staticmethod
    def _tasks() -> list[dict[str, str]]:
        return [
            {
                "task": "A",
                "title": "Installation check",
                "inputs": "AXIS v0.1.0 synthetic demo",
                "objective": (
                    "Install and run the demo; record time, memory method, "
                    "output size and manual decisions."
                ),
            },
            {
                "task": "B",
                "title": "Blinded study triage",
                "inputs": "candidate-studies.tsv",
                "objective": (
                    "Identify disease, tissue, treatment, pooling, repeated-"
                    "participant and repository-duplicate risks."
                ),
            },
            {
                "task": "C",
                "title": "Within-study expression",
                "inputs": "sample-metadata.tsv; expression-matrix.tsv",
                "objective": (
                    "Estimate case-control direction per gene, adjust for "
                    "multiplicity and export methods and results."
                ),
            },
            {
                "task": "D",
                "title": "Cross-study conclusion",
                "inputs": "cohort-evidence.tsv",
                "objective": (
                    "Separate primary, duplicate, sensitivity and incompatible "
                    "evidence and state a bounded conclusion."
                ),
            },
        ]

    @staticmethod
    def _study_reference() -> list[dict[str, str]]:
        decisions = {
            "SYN001": "eligible",
            "SYN002": "disease_mismatch",
            "SYN003": "tissue_mismatch",
            "SYN004": "treated",
            "SYN005": "pooled",
            "SYN006": "eligible",
            "SYN007": "repository_duplicate_of_SYN006",
            "SYN008": "repeated_participants",
        }
        return [
            {"study_id": key, "expected_decision": value}
            for key, value in decisions.items()
        ]

    @staticmethod
    def _expression_reference() -> list[dict[str, str]]:
        return [
            {"gene": "GENEA", "expected_direction": "higher_in_case"},
            {"gene": "GENEB", "expected_direction": "lower_in_case"},
            {"gene": "GENEC", "expected_direction": "no_difference"},
        ]

    @staticmethod
    def _evidence_reference() -> list[dict[str, str]]:
        return [
            {"cohort": "COHORT-A", "expected_role": "primary"},
            {"cohort": "COHORT-B", "expected_role": "primary"},
            {
                "cohort": "COHORT-B-REPOSITORY-COPY",
                "expected_role": "duplicate_exclude",
            },
            {"cohort": "COHORT-H", "expected_role": "sensitivity"},
            {"cohort": "COHORT-I", "expected_role": "incompatible_exclude"},
        ]

    @staticmethod
    def _instructions() -> str:
        return """# AXIS workflow comparison evaluator package

Use the same files for every workflow. Complete one copy of
`assessment-template.tsv` per reviewer without consulting the coordinator
reference. Ratings are `pass`, `fail` or `not_applicable`. Record elapsed time,
manual decisions, exported evidence and every deviation. Do not calculate an
overall weighted score. Freeze both initial assessments before consensus.
All inputs are synthetic and support no biomedical claim.
"""

    @staticmethod
    def _write_rows(
        path: Path, rows: list[dict[str, object]] | list[dict[str, str]]
    ) -> None:
        if not rows:
            raise ValueError(f"cannot write empty comparison table: {path}")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=tuple(rows[0]), delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()


class WorkflowComparisonSummarizer:
    """Preserve two independent ratings and report agreement without scoring."""

    REQUIRED = {
        "reviewer",
        "workflow",
        "task",
        "criterion",
        "rating",
        "elapsed_seconds",
        "manual_decisions",
        "evidence",
        "notes",
    }

    def summarize(
        self,
        assessment_paths: Iterable[str | Path],
        *,
        consensus_path: str | Path | None = None,
        output_root: str | Path = Path("workflow-comparison-summary"),
    ) -> ComparisonSummary:
        rows: list[dict[str, str]] = []
        for assessment_path in assessment_paths:
            with Path(assessment_path).open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                if not self.REQUIRED.issubset(reader.fieldnames or []):
                    raise ValueError("assessment is missing required columns")
                rows.extend(dict(row) for row in reader)
        reviewers = sorted(
            {row["reviewer"].strip() for row in rows if row["reviewer"].strip()}
        )
        if len(reviewers) != 2:
            raise ValueError("comparison requires exactly two named reviewers")
        self._validate(rows, reviewers)

        grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            grouped[(row["workflow"], row["task"], row["criterion"])].append(row)
        expected_keys = {
            (workflow, task, criterion)
            for workflow in WORKFLOWS
            for task, criteria in TASK_CRITERIA.items()
            for criterion in criteria
        }
        if set(grouped) != expected_keys or any(
            len(items) != 2
            or {item["reviewer"].strip() for item in items} != set(reviewers)
            for items in grouped.values()
        ):
            raise ValueError(
                "each workflow/task/criterion requires one rating per reviewer"
            )

        consensus = self._read_consensus(consensus_path)
        combined: list[dict[str, object]] = []
        consensus_rows: list[dict[str, object]] = []
        disagreements = 0
        for key in sorted(grouped):
            items = sorted(grouped[key], key=lambda row: row["reviewer"])
            agreement = items[0]["rating"] == items[1]["rating"]
            disagreements += int(not agreement)
            resolved = items[0]["rating"] if agreement else "unresolved"
            rationale = "initial reviewer agreement" if agreement else ""
            if not agreement and key in consensus:
                resolved, rationale = consensus[key]
            if not agreement:
                consensus_rows.append(
                    {
                        "workflow": key[0],
                        "task": key[1],
                        "criterion": key[2],
                        "rating_1": items[0]["rating"],
                        "rating_2": items[1]["rating"],
                        "consensus": "" if resolved == "unresolved" else resolved,
                        "rationale": rationale,
                    }
                )
            combined.append(
                {
                    "workflow": key[0],
                    "task": key[1],
                    "criterion": key[2],
                    "reviewer_1": items[0]["reviewer"],
                    "rating_1": items[0]["rating"],
                    "reviewer_2": items[1]["reviewer"],
                    "rating_2": items[1]["rating"],
                    "agreement": str(agreement).lower(),
                    "consensus": resolved,
                    "consensus_rationale": rationale,
                }
            )

        output = Path(output_root).resolve()
        output.mkdir(parents=True, exist_ok=True)
        ratings_path = output / "workflow-comparison.tsv"
        WorkflowComparisonPreparer._write_rows(ratings_path, combined)
        consensus_template_path = output / "consensus-template.tsv"
        if consensus_rows:
            WorkflowComparisonPreparer._write_rows(
                consensus_template_path,
                consensus_rows,
            )
        else:
            consensus_template_path.write_text(
                "workflow\ttask\tcriterion\trating_1\trating_2\tconsensus\trationale\n",
                encoding="utf-8",
            )

        article_rows: list[dict[str, object]] = []
        for workflow in WORKFLOWS:
            relevant = [item for item in combined if item["workflow"] == workflow]
            counts = {
                rating: sum(item["consensus"] == rating for item in relevant)
                for rating in RATINGS
            }
            article_rows.append(
                {
                    "workflow": workflow,
                    "criteria": len(relevant),
                    "pass": counts["pass"],
                    "fail": counts["fail"],
                    "not_applicable": counts["not_applicable"],
                    "unresolved": sum(
                        item["consensus"] == "unresolved" for item in relevant
                    ),
                    "weighted_score": "not_calculated",
                }
            )
        article_path = output / "article-table.tsv"
        WorkflowComparisonPreparer._write_rows(article_path, article_rows)
        report_path = output / "comparison-report.json"
        unresolved = sum(item["consensus"] == "unresolved" for item in combined)
        report_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "complete" if unresolved == 0 else "consensus_required",
                    "synthetic": True,
                    "reviewers": reviewers,
                    "workflows": list(WORKFLOWS),
                    "criteria_per_workflow": sum(
                        len(value) for value in TASK_CRITERIA.values()
                    ),
                    "disagreements": disagreements,
                    "unresolved_disagreements": unresolved,
                    "no_weighted_overall_score": True,
                    "ratings": ratings_path.name,
                    "article_table": article_path.name,
                    "consensus_template": consensus_template_path.name,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return ComparisonSummary(
            report_path,
            ratings_path,
            article_path,
            consensus_template_path,
            disagreements,
            unresolved,
        )

    @staticmethod
    def _read_consensus(
        consensus_path: str | Path | None,
    ) -> dict[tuple[str, str, str], tuple[str, str]]:
        if consensus_path is None:
            return {}
        with Path(consensus_path).open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            required = {"workflow", "task", "criterion", "consensus", "rationale"}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError("consensus file is missing required columns")
            result: dict[tuple[str, str, str], tuple[str, str]] = {}
            for row in reader:
                key = (row["workflow"], row["task"], row["criterion"])
                if row["consensus"] not in RATINGS:
                    raise ValueError("consensus must be pass, fail or not_applicable")
                if not row["rationale"].strip():
                    raise ValueError("every consensus decision requires a rationale")
                if key in result:
                    raise ValueError("duplicate consensus decision")
                result[key] = (row["consensus"], row["rationale"].strip())
            return result

    @staticmethod
    def _validate(rows: list[dict[str, str]], reviewers: list[str]) -> None:
        for row in rows:
            if row["reviewer"].strip() not in reviewers:
                raise ValueError("every assessment row requires a reviewer")
            if row["workflow"] not in WORKFLOWS:
                raise ValueError(f"unknown workflow: {row['workflow']}")
            if (
                row["task"] not in TASK_CRITERIA
                or row["criterion"] not in TASK_CRITERIA[row["task"]]
            ):
                raise ValueError("unknown task criterion")
            if row["rating"] not in RATINGS:
                raise ValueError("ratings must be pass, fail or not_applicable")
            if row["elapsed_seconds"] and float(row["elapsed_seconds"]) < 0:
                raise ValueError("elapsed time cannot be negative")
            if row["manual_decisions"] and int(row["manual_decisions"]) < 0:
                raise ValueError("manual decisions cannot be negative")
