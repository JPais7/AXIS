"""Explicit frozen import; read-only bounded evidence-chain projections."""

import hashlib
import json
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

from axis.cellular.rules import aggregate, concordance
from axis.domain.cellular import (
    EDGES,
    BiologicalContext,
    CellularAssessment,
    CellularExperiment,
    ExperimentalReadout,
    ImmunopeptidomeObservation,
)
from axis.domain.discovery import (
    OpenQuestion,
    OutcomeScenario,
    Perturbation,
    PerturbationDirection,
    PerturbationStatus,
    PerturbationType,
    ProposalOrigin,
    ProposalStatus,
    ProposedExperiment,
    QuestionLinks,
    QuestionStatus,
)
from axis.domain.models import ClaimContext, KnowledgeKind, Provenance, SourceKind
from axis.storage import EvidenceStore, RecordConflictError

VERSION = "axis-cellular-1"


def experiment(data: dict[str, Any]) -> CellularExperiment:
    context = data["context"]
    return CellularExperiment(
        **(
            data
            | {
                "controls": tuple(data["controls"]),
                "context": BiologicalContext(
                    **(
                        context
                        | {
                            "scientific_context": ClaimContext(
                                **context["scientific_context"]
                            )
                        }
                    )
                ),
            }
        )
    )


class CellularPharmacologyService:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    def import_package(
        self, project: str, protein: str, directory: Path | None = None
    ) -> dict[str, Any]:
        target = self.store.targets.require_member(project, protein)
        if target.primary_accession != "Q9NZ08" or target.taxon_id != 9606:
            raise ValueError("reference package requires human ERAP1")
        root = directory or resources.files("axis").joinpath(
            "resources/cellular/erap1-axspa/v1"
        )
        raw = root.joinpath("manifest.json").read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != root.joinpath("manifest.sha256").read_text().strip():
            raise ValueError("cellular package checksum mismatch")
        package = json.loads(raw)
        if package["importer_version"] != VERSION:
            raise ValueError("unsupported cellular importer")
        now = datetime.fromisoformat(package["curated_at"])
        proposal_provenance = Provenance(
            SourceKind.AI_MODEL, VERSION, now, checksum=digest
        )
        pair = self.store.target_disease_pairs.get(
            self.store.projects.get(project).target_disease_pair
        )
        with self.store._transaction():
            for item in package["experiments"]:
                value = experiment(item)
                old = self.store.perturbations.get_optional(value.perturbation_id)
                if old is None:
                    link = next(
                        r for r in package["readouts"] if r["experiment_id"] == value.id
                    )
                    if link.get("claim_id"):
                        claim = self.store.claims.get(link["claim_id"])
                        provenance = claim.provenance
                    else:
                        m = self.store.pharmacology.record(
                            "measurements", link["measurement_id"]
                        )
                        snapshot = self.store.targets.snapshot(m["source_snapshot_id"])
                        provenance = Provenance(
                            SourceKind.PUBLICATION,
                            value.source_id,
                            snapshot.retrieval_timestamp,
                            snapshot.request_url,
                            snapshot.raw_content_checksum,
                        )
                    kind = {
                        "knockdown": PerturbationType.KNOCKDOWN,
                        "variant_expression": PerturbationType.GENETIC_VARIANT,
                        "small_molecule": PerturbationType.INHIBITOR,
                    }.get(value.modality, PerturbationType.OTHER)
                    self.store.perturbations.add(
                        Perturbation(
                            value.perturbation_id,
                            pair.target,
                            kind,
                            PerturbationDirection.MODULATE,
                            PerturbationStatus.PERFORMED,
                            provenance,
                            KnowledgeKind.SOURCE_ASSERTION,
                            value.context.scientific_context,
                            observed_effect_claim_id=link.get("claim_id"),
                        )
                    )
                    self.store.perturbations.add_to_project(
                        project, value.perturbation_id
                    )
                self.store.cellular.add_experiment(project, protein, value)
            for item in package["readouts"]:
                self.store.cellular.add_readout(
                    project, protein, ExperimentalReadout(**item)
                )
            for item in package["assessments"]:
                self.store.cellular.add_assessment(
                    project,
                    protein,
                    CellularAssessment(
                        **(
                            item
                            | {
                                "supporting_readout_ids": tuple(
                                    item.get("supporting_readout_ids", [])
                                ),
                                "contradicting_readout_ids": tuple(
                                    item.get("contradicting_readout_ids", [])
                                ),
                            }
                        )
                    ),
                )
            for item in package["immunopeptidome"]:
                self.store.cellular.add_immunopeptidome(
                    project, protein, ImmunopeptidomeObservation(**item)
                )
            for item in package["gaps"]:
                question = OpenQuestion(
                    item["id"],
                    project,
                    item["question"],
                    "cellular_translational_gap",
                    QuestionStatus.OPEN,
                    now,
                    now,
                )
                self.store.questions.add(question)
                self.store.questions.link(
                    question.question_id,
                    QuestionLinks(
                        claim_ids=tuple(item.get("claim_ids", [])),
                        perturbation_ids=(item["perturbation_id"],),
                    ),
                )
                payload = json.dumps(item, sort_keys=True)
                old_gap = self.store._connection.execute(
                    "SELECT payload FROM cellular_gap_links WHERE question_id=?",
                    [item["id"]],
                ).fetchone()
                if old_gap and json.loads(old_gap[0]) != item:
                    raise RecordConflictError("immutable evidence gap conflict")
                if not old_gap:
                    self.store._connection.execute(
                        "INSERT INTO cellular_gap_links VALUES (?,?,?,?,?,?,?)",
                        [
                            item["id"],
                            project,
                            protein,
                            item.get("compound_id"),
                            item["perturbation_id"],
                            item["edge"],
                            payload,
                        ],
                    )
                proposed = ProposedExperiment(
                    item["id"] + ":proposal",
                    project,
                    item["id"],
                    item["proposal_title"],
                    item["question"],
                    "Matched HLA and ERAP1 genetic context; controls required",
                    "Chemical perturbation, ERAP1 genetic depletion/rescue and "
                    "orthogonal controls; measure toxicity separately",
                    "Validated cellular engagement and proximal function, "
                    "plus the source-linked phenotype",
                    proposal_provenance,
                    ProposalOrigin.AXIS,
                    KnowledgeKind.AI_SUGGESTION,
                    ProposalStatus.PROPOSED,
                )
                self.store.proposed_experiments.add(proposed)
                for number, (outcome, interpretation) in enumerate(
                    [
                        (
                            "Engagement and phenotype track; "
                            "rescue/dependency controls agree",
                            "Supports on-target bridge in this context; "
                            "not clinical efficacy",
                        ),
                        (
                            "Phenotype without detectable engagement",
                            "Investigate assay sensitivity, indirect "
                            "and off-target mechanisms",
                        ),
                        (
                            "Engagement without phenotype",
                            "Weakens the assumed downstream bridge in this context",
                        ),
                    ]
                ):
                    self.store.outcome_scenarios.add(
                        OutcomeScenario(
                            proposed.experiment_id + f":{number}",
                            proposed.experiment_id,
                            outcome,
                            interpretation,
                        )
                    )
        return {
            "manifest_sha256": digest,
            "experiments": len(package["experiments"]),
            "readouts": len(package["readouts"]),
            "review_status": package["review_status"],
        }

    def chain(
        self, project: str, protein: str, compound: str | None = None
    ) -> dict[str, Any]:
        repo = self.store.cellular
        assessments = repo.collection(project, protein, "assessments", 100, 0, compound)
        experiments = repo.collection(project, protein, "experiments", 100, 0, compound)
        contexts = {e["id"]: e for e in experiments["items"]}
        edges = []
        for edge in EDGES:
            inputs = [
                a
                | {
                    "context": contexts.get(a["experiment_id"], {}).get("context"),
                    "experiment_label": contexts.get(a["experiment_id"], {}).get(
                        "label"
                    ),
                }
                for a in assessments["items"]
                if a["edge"] == edge
            ]
            state = aggregate([a["state"] for a in inputs])
            if edge == "biochemical":
                measurements = self.store.pharmacology.collection(
                    project,
                    protein,
                    "measurements",
                    100,
                    0,
                    {
                        **({"compound": compound} if compound else {}),
                        "target": "ERAP1",
                        "assay_type": "biochemical_activity",
                    },
                )
                if measurements["items"]:
                    state = "supported"
            else:
                measurements = {"items": [], "has_more": False}
            edges.append(
                {
                    "edge": edge,
                    "state": state,
                    "assessments": inputs,
                    "measurements": measurements["items"],
                    "has_more": measurements["has_more"],
                }
            )
        return {
            "edges": edges,
            "compound_id": compound,
            "has_more": assessments["has_more"] or experiments["has_more"],
            "boundary": "Independent evidence classes, not a causal chain or score. "
            "Missing links are not filled by phenotype. Off-target contribution "
            "cannot be excluded. Molecular/immune phenotypes are not disease rescue.",
        }

    def detail(self, project: str, protein: str, identifier: str) -> dict[str, Any]:
        value = self.store.cellular.detail(project, protein, "experiments", identifier)
        readouts = self.store.cellular.collection(project, protein, "readouts", 100)
        return {
            "experiment": value,
            "readouts": [
                r for r in readouts["items"] if r["experiment_id"] == identifier
            ],
            "has_more": readouts["has_more"],
            "review_status": "AI-assisted curation · pending expert review",
        }

    def comparisons(self, project: str, protein: str) -> dict[str, Any]:
        exps = self.store.cellular.collection(project, protein, "experiments", 20)
        reads = self.store.cellular.collection(project, protein, "readouts", 100)
        result = []
        for i, a in enumerate(exps["items"]):
            for b in exps["items"][i + 1 :]:
                if not (
                    "small_molecule" in {a["modality"], b["modality"]}
                    and (
                        {a["modality"], b["modality"]}
                        & {"knockdown", "knockout", "variant_expression", "CRISPR"}
                    )
                ):
                    continue
                for x in reads["items"]:
                    for y in reads["items"]:
                        if (
                            x["experiment_id"] == a["id"]
                            and y["experiment_id"] == b["id"]
                            and x["endpoint"] == y["endpoint"]
                        ):
                            result.append(
                                concordance(
                                    experiment(a),
                                    experiment(b),
                                    ExperimentalReadout(**x),
                                    ExperimentalReadout(**y),
                                )
                            )
                            if len(result) == 20:
                                return {"items": result, "has_more": True}
        return {"items": result, "has_more": exps["has_more"] or reads["has_more"]}

    def gaps(
        self, project: str, protein: str, compound: str | None = None
    ) -> dict[str, Any]:
        self.store.targets.require_member(project, protein)
        if compound:
            self.store.pharmacology.require_scoped(
                project, protein, "compounds", compound
            )
        rows = self.store._connection.execute(
            "SELECT payload FROM cellular_gap_links "
            "WHERE project_id=? AND protein_id=? "
            + ("AND compound_id=? " if compound else "")
            + "ORDER BY question_id LIMIT 101",
            [project, protein] + ([compound] if compound else []),
        ).fetchall()
        return {
            "items": [json.loads(r[0]) for r in rows[:100]],
            "has_more": len(rows) > 100,
            "proposal_boundary": "AXIS suggestions, not performed experiments",
        }

    def review_packet(self, project: str, protein: str) -> dict[str, Any]:
        values = self.store.cellular.collection(project, protein, "experiments", 100)
        readouts = self.store.cellular.collection(project, protein, "readouts", 100)
        assessments = self.store.cellular.collection(
            project, protein, "assessments", 100
        )
        return {
            "items": [
                {
                    "experiment": e,
                    "readouts": [
                        r for r in readouts["items"] if r["experiment_id"] == e["id"]
                    ],
                    "assessments": [
                        a for a in assessments["items"] if a["experiment_id"] == e["id"]
                    ],
                    "review_decisions": {
                        key: "pending"
                        for key in (
                            "source_extraction",
                            "context",
                            "compound_link",
                            "engagement",
                            "dependency",
                            "phenotype",
                            "disease_relevance",
                            "concordance",
                        )
                    },
                }
                for e in values["items"]
            ],
            "has_more": values["has_more"]
            or readouts["has_more"]
            or assessments["has_more"],
            "automatic_acceptance": False,
        }
