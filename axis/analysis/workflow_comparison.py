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

COMPARISON_WORKFLOWS = {
    "differential_expression": (
        "axis",
        "geo2r",
        "manual_statistics",
        "expressanalyst",
    ),
    "evidence_governance": ("axis", "manual_evidence_review"),
}
COMPARISON_TASKS = {
    "differential_expression": ("A", "C"),
    "evidence_governance": ("B", "D"),
}
WORKFLOWS = tuple(
    dict.fromkeys(
        workflow
        for workflows in COMPARISON_WORKFLOWS.values()
        for workflow in workflows
    )
)
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
        "sample_groups_preserved",
        "effect_estimates_exported",
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
        self._write_rows(public / "cohort-evidence.tsv", self._cohort_evidence())
        self._write_rows(public / "tasks.tsv", self._tasks())
        self._write_rows(public / "comparison-design.tsv", self._comparison_design())
        self._write_rows(public / "expression-study.tsv", self._expression_study())
        self._write_rows(
            public / "expression-sample-groups.tsv",
            self._expression_sample_groups(),
        )
        self._write_rows(public / "rating-rubric.tsv", self._rating_rubric())
        self._write_rows(public / "result-template.tsv", self._result_template())
        (public / "STANDARD-OPERATING-PROCEDURE.md").write_text(
            self._standard_operating_procedure(), encoding="utf-8"
        )

        template_rows = [
            {
                "reviewer": "",
                "comparison": comparison,
                "workflow": workflow,
                "task": task,
                "criterion": criterion,
                "rating": "",
                "elapsed_seconds": "",
                "manual_decisions": "",
                "evidence": "",
                "notes": "",
            }
            for comparison, workflows in COMPARISON_WORKFLOWS.items()
            for workflow in workflows
            for task in COMPARISON_TASKS[comparison]
            for criterion in TASK_CRITERIA[task]
        ]
        template = public / "assessment-template.tsv"
        self._write_rows(template, template_rows)
        self._write_rows(
            reference / "expected-study-decisions.tsv", self._study_reference()
        )
        self._write_rows(
            reference / "expression-assessment-policy.tsv",
            self._expression_reference(),
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
                    "schema_version": 2,
                    "protocol": "AXIS scoped workflow comparisons v2",
                    "synthetic": False,
                    "comparisons": {
                        name: {
                            "workflows": list(COMPARISON_WORKFLOWS[name]),
                            "tasks": list(COMPARISON_TASKS[name]),
                        }
                        for name in COMPARISON_WORKFLOWS
                    },
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
    def _comparison_design() -> list[dict[str, str]]:
        return [
            {
                "comparison": "differential_expression",
                "question": (
                    "Can the workflow reproduce the same unadjusted "
                    "case-control contrast?"
                ),
                "workflows": "|".join(COMPARISON_WORKFLOWS["differential_expression"]),
                "tasks": "A|C",
                "input_scope": "GSE18781; GPL570; frozen 18-case/25-control groups",
                "allowed_claim": (
                    "Agreement, usability and reproducibility for this contrast only"
                ),
            },
            {
                "comparison": "evidence_governance",
                "question": (
                    "Can the workflow preserve eligibility, independence "
                    "and evidence roles?"
                ),
                "workflows": "|".join(COMPARISON_WORKFLOWS["evidence_governance"]),
                "tasks": "B|D",
                "input_scope": "Synthetic metadata with known governance traps",
                "allowed_claim": (
                    "Guardrail detection for the supplied synthetic scenarios only"
                ),
            },
        ]

    @staticmethod
    def _expression_study() -> list[dict[str, str]]:
        return [
            {
                "accession": "GSE18781",
                "platform": "GPL570",
                "contrast": "SpA case minus healthy control",
                "cases": "18",
                "controls": "25",
                "primary_model": "unadjusted case-control",
                "secondary_model": "batch-adjusted where supported; report separately",
                "source": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE18781",
            }
        ]

    @staticmethod
    def _expression_sample_groups() -> list[dict[str, str]]:
        return [
            {
                "sample_id": f"GSM{accession}",
                "group": "case" if accession <= 465924 else "control",
            }
            for accession in range(465907, 465950)
        ]

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
                "title": "Access and environment check",
                "inputs": "Declared differential-expression workflow",
                "objective": (
                    "Open or install the workflow and record environment, "
                    "timing method, output size and manual decisions."
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
                "inputs": "GSE18781; expression-sample-groups.tsv",
                "objective": (
                    "Run the frozen primary case-control contrast, adjust for "
                    "multiplicity and export probe-level methods and results."
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
    def _rating_rubric() -> list[dict[str, str]]:
        pass_rules = {
            "installation_success": (
                "Workflow becomes usable and its version or access date is recorded."
            ),
            "wall_clock_time_recorded": (
                "Elapsed seconds use the common timing boundary."
            ),
            "memory_method_declared": (
                "A measured value and method, or an explicit unavailable "
                "measurement, is recorded."
            ),
            "output_size_recorded": (
                "Total bytes of exported result files are recorded."
            ),
            "manual_decisions_recorded": (
                "Every operator choice outside fixed instructions is counted "
                "and described."
            ),
            "disease_mismatch_detected": "SYN002 is excluded for disease mismatch.",
            "tissue_mismatch_detected": "SYN003 is excluded for tissue mismatch.",
            "treatment_detected": "SYN004 is excluded or separated as post-treatment.",
            "pooled_samples_detected": (
                "SYN005 is flagged as pooled and not counted as individual "
                "participants."
            ),
            "repeated_participants_detected": (
                "SYN008 is flagged as repeated-participant data."
            ),
            "repository_duplicate_detected": (
                "SYN007 is linked to and not double-counted with SYN006."
            ),
            "sample_groups_preserved": (
                "All frozen GSE18781 case and control assignments are preserved."
            ),
            "effect_estimates_exported": (
                "Probe-level effects and directions are exported for the primary "
                "contrast."
            ),
            "multiplicity_correction_recorded": (
                "Benjamini-Hochberg FDR is applied across the three genes and exported."
            ),
            "method_record_complete": (
                "Test, contrast, effect definition, multiplicity method and "
                "software version are recorded."
            ),
            "executable_or_machine_readable_export": (
                "A complete TSV or CSV result is exported without manual transcription."
            ),
            "participants_counted_correctly": (
                "The primary evidence contains 36 unique participants."
            ),
            "duplicate_participants_not_double_counted": (
                "The repository copy of COHORT-B adds zero participants."
            ),
            "incompatible_evidence_not_pooled": (
                "COHORT-I is excluded from the primary pooled conclusion."
            ),
            "input_output_provenance_preserved": (
                "Inputs, workflow version/access date and exports are identified."
            ),
            "conclusion_bounded_to_association": (
                "Conclusion states a same-direction association in two independent "
                "primary cohorts without causal or drug claims."
            ),
        }
        unavailable = (
            "Allowed only when structurally irrelevant to a hosted workflow; explain "
            "why. Unsupported functionality or an unsuccessful attempt is fail."
        )
        return [
            {
                "task": task,
                "criterion": criterion,
                "pass_rule": pass_rules[criterion],
                "fail_rule": "The pass rule is not met or required evidence is absent.",
                "not_applicable_rule": unavailable,
            }
            for task, criteria in TASK_CRITERIA.items()
            for criterion in criteria
        ]

    @staticmethod
    def _result_template() -> list[dict[str, str]]:
        return [
            {
                "reviewer": "",
                "comparison": comparison,
                "workflow": workflow,
                "task": task,
                "started_at_utc": "",
                "elapsed_seconds": "",
                "manual_decisions": "",
                "status": "",
                "output_files": "",
                "version_or_access_date": "",
                "deviations": "",
            }
            for comparison, workflows in COMPARISON_WORKFLOWS.items()
            for workflow in workflows
            for task in COMPARISON_TASKS[comparison]
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
            {
                "metric": "sample_assignment",
                "policy": "Exact match to expression-sample-groups.tsv",
            },
            {
                "metric": "cross_workflow_effect_agreement",
                "policy": "Report pairwise Spearman correlation on shared probes",
            },
            {
                "metric": "top_set_overlap",
                "policy": "Report overlap at prespecified top 100 and top 500 probes",
            },
            {
                "metric": "reference_truth",
                "policy": "None; no workflow output is treated as biological truth",
            },
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

This package contains two separate comparisons. Differential-expression
workflows use the real public GSE18781 accession and Tasks A/C. Evidence-governance
workflows use synthetic metadata and Tasks B/D. Never compare pass counts between
the two comparisons.
Follow `STANDARD-OPERATING-PROCEDURE.md` and `rating-rubric.tsv`. Complete
`result-template.tsv` while operating each workflow, then complete the assessment
only from frozen outputs. A failed or unavailable operation is not automatically
`not_applicable`. Freeze both reviewers' initial files before consensus.
"""

    @staticmethod
    def _standard_operating_procedure() -> str:
        return """# Standard operating procedure

## Roles and blinding

Each reviewer operates every in-scope workflow independently. Reviewers must not consult
each other or the `coordinator-reference` directory before both initial result
and assessment files are frozen. Use coded reviewer identifiers. Record all
deviations; do not repair an output after seeing a reference answer.

## Common environment and timing

Within each comparison, use the same computer and network for all workflows. Record OS,
hardware, workflow version or web access date, browser where relevant, and every
manual decision. One untimed familiarisation attempt per workflow is permitted.
For each measured task, start timing immediately before the first workflow action
after opening the required input and stop when all required exports are saved.
Include uploads and downloads; exclude the familiarisation attempt. Record failed
attempts. Measure output size as the sum of exported result files. Record peak
memory with the same OS tool where possible; if a hosted service prevents this,
record `measurement_unavailable_hosted_service` and the method attempted.

## Allowed operations

Use only the named workflow, official documentation and declared comparison
inputs. Do not use another workflow to repair or transcribe results.
`manual_statistics` may use a spreadsheet or one general-purpose statistics
environment; `manual_evidence_review` may use a spreadsheet or text editor.
Export every formula, command and version.

## Differential-expression comparison

Use `expression-study.tsv` and `expression-sample-groups.tsv`. Retrieve
GSE18781 through each workflow's normal GEO route. Run the same unadjusted
case-control contrast on GPL570 with the frozen 18 case and 25 control samples.
Report probe-level results with the workflow's standard moderated or classical
test and Benjamini-Hochberg adjustment. Batch-adjusted results are secondary and
must not replace the primary contrast. ExpressAnalyst replaces NetworkAnalyst
because the latter explicitly redirects transcriptomic tables there.

## Evidence-governance comparison

Use only `candidate-studies.tsv` and `cohort-evidence.tsv`. Compare AXIS with
a documented manual evidence review. Do not include GEO2R or ExpressAnalyst:
study eligibility, duplicate-participant detection and evidence-role separation
are outside this comparison's declared differential-expression scope.

## Required outputs

For every workflow and task, preserve a machine-readable result where the workflow
supports export, a plain-text methods record, and the corresponding row in
`result-template.tsv`. Task B must output one decision and rationale per study.
Task C must export probe identifier, effect or log fold-change, direction, raw
p-value and Benjamini-Hochberg adjusted p-value, plus the exact group assignment.
Task D must output one role per cohort, the unique primary-participant total,
excluded duplicates,
excluded incompatible evidence and one bounded conclusion.

## Task A

Start from a new local environment or private browser session. Follow official
installation/access instructions. For hosted workflows, installation is
`not_applicable` only because no local installation exists. Time Task C
separately; Task A access timing must not be presented as analysis speed.

## Rating

Apply `rating-rubric.tsv` literally to frozen evidence. `pass` requires the
stated evidence, and missing evidence is `fail`. `not_applicable` is restricted
to a criterion that is structurally irrelevant, never merely unsupported or
failed. Keep both initial assessments unchanged. Resolve disagreements later in
a separate consensus file with a rationale. Never calculate a weighted overall
score. The real-expression comparison is limited to one public contrast; the
synthetic governance comparison supports no biomedical claim.
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
        "comparison",
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

        grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(
            list
        )
        for row in rows:
            grouped[
                (
                    row["comparison"],
                    row["workflow"],
                    row["task"],
                    row["criterion"],
                )
            ].append(row)
        expected_keys = {
            (comparison, workflow, task, criterion)
            for comparison, workflows in COMPARISON_WORKFLOWS.items()
            for workflow in workflows
            for task in COMPARISON_TASKS[comparison]
            for criterion in TASK_CRITERIA[task]
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
                        "comparison": key[0],
                        "workflow": key[1],
                        "task": key[2],
                        "criterion": key[3],
                        "rating_1": items[0]["rating"],
                        "rating_2": items[1]["rating"],
                        "consensus": "" if resolved == "unresolved" else resolved,
                        "rationale": rationale,
                    }
                )
            combined.append(
                {
                    "comparison": key[0],
                    "workflow": key[1],
                    "task": key[2],
                    "criterion": key[3],
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
                "comparison\tworkflow\ttask\tcriterion\trating_1\trating_2"
                "\tconsensus\trationale\n",
                encoding="utf-8",
            )

        article_rows: list[dict[str, object]] = []
        for comparison, workflows in COMPARISON_WORKFLOWS.items():
            for workflow in workflows:
                relevant = [
                    item
                    for item in combined
                    if item["comparison"] == comparison and item["workflow"] == workflow
                ]
                counts = {
                    rating: sum(item["consensus"] == rating for item in relevant)
                    for rating in RATINGS
                }
                article_rows.append(
                    {
                        "comparison": comparison,
                        "workflow": workflow,
                        "criteria": len(relevant),
                        "pass": counts["pass"],
                        "fail": counts["fail"],
                        "not_applicable": counts["not_applicable"],
                        "unresolved": sum(
                            item["consensus"] == "unresolved" for item in relevant
                        ),
                        "weighted_score": "not_calculated",
                        "cross_comparison_ranking": "prohibited",
                    }
                )
        article_path = output / "article-table.tsv"
        WorkflowComparisonPreparer._write_rows(article_path, article_rows)
        report_path = output / "comparison-report.json"
        unresolved = sum(item["consensus"] == "unresolved" for item in combined)
        report_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "status": "complete" if unresolved == 0 else "consensus_required",
                    "mixed_real_and_synthetic_inputs": True,
                    "reviewers": reviewers,
                    "comparisons": {
                        name: list(workflows)
                        for name, workflows in COMPARISON_WORKFLOWS.items()
                    },
                    "cross_comparison_ranking": "prohibited",
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
    ) -> dict[tuple[str, str, str, str], tuple[str, str]]:
        if consensus_path is None:
            return {}
        with Path(consensus_path).open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            required = {
                "comparison",
                "workflow",
                "task",
                "criterion",
                "consensus",
                "rationale",
            }
            if not required.issubset(reader.fieldnames or []):
                raise ValueError("consensus file is missing required columns")
            result: dict[tuple[str, str, str, str], tuple[str, str]] = {}
            for row in reader:
                key = (
                    row["comparison"],
                    row["workflow"],
                    row["task"],
                    row["criterion"],
                )
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
            comparison = row["comparison"]
            if comparison not in COMPARISON_WORKFLOWS:
                raise ValueError(f"unknown comparison: {comparison}")
            if row["workflow"] not in COMPARISON_WORKFLOWS[comparison]:
                raise ValueError("workflow is outside the declared comparison scope")
            if row["task"] not in COMPARISON_TASKS[comparison]:
                raise ValueError("task is outside the declared comparison scope")
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
