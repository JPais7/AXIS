"""Versioned, offline primary-source curation through existing AXIS repositories."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from importlib import resources
from typing import Any, cast

from axis.discovery.service import DiscoveryService, ProjectTraversal
from axis.domain import (
    Claim,
    ClaimContext,
    DiscoveryProject,
    EntityKind,
    EntityRef,
    EvidenceAssessment,
    EvidenceRole,
    InterventionStrategy,
    KnowledgeKind,
    MechanismClassification,
    MechanisticAssessment,
    OpenQuestion,
    OutcomeScenario,
    Perturbation,
    PerturbationDirection,
    PerturbationStatus,
    PerturbationType,
    ProjectStatus,
    ProposalOrigin,
    ProposalStatus,
    ProposedExperiment,
    Provenance,
    QuestionLinks,
    QuestionStatus,
    SourceKind,
    StrategyStatus,
    StrategyType,
    TargetDiseasePair,
    Transformation,
)
from axis.storage import EvidenceStore

CURATED_PROJECT = "AXIS-DD-ERAP1-CURATED-001"


def load_curated_package() -> tuple[dict[str, Any], str]:
    root = resources.files("axis").joinpath("resources/discovery/erap1-axspa/v1")
    payload = root.joinpath("manifest.json").read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != root.joinpath("manifest.sha256").read_text().split()[0]:
        raise ValueError("curated package checksum mismatch")
    manifest = cast(dict[str, Any], json.loads(payload))
    if manifest["package_version"] != "1.0.0":
        raise ValueError("unsupported curated package version")
    identifiers = [item["claim_id"] for item in manifest["claims"]]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate curated claim IDs")
    return manifest, digest


def _entity(value: dict[str, str]) -> EntityRef:
    return EntityRef(
        EntityKind(value["kind"]),
        value["identifier"],
        value["label"],
        value["namespace"],
    )


def import_curated_erap1(store: EvidenceStore) -> ProjectTraversal:
    """Explicit, atomic import; no changing network sources or demo conversion."""
    manifest, digest = load_curated_package()
    project_id = str(manifest["project_id"])
    sources = {item["source_id"]: item for item in manifest["sources"]}
    now = datetime.fromisoformat(manifest["curated_at"])
    target, disease = _entity(manifest["target"]), _entity(manifest["disease"])
    pair = TargetDiseasePair(
        manifest["pair_id"], target, disease, manifest["indication_scope"], now
    )
    project = DiscoveryProject(
        project_id, pair.pair_id, manifest["objective"], ProjectStatus.ACTIVE, now, now
    )
    package_parameters = (
        ("package_id", manifest["package_id"]),
        ("package_version", manifest["package_version"]),
        ("package_checksum", "sha256:" + digest),
        ("axis_version", "0.2.1.dev0"),
        ("curation_status", manifest["curation_status"]),
        ("corpus_scope", manifest["coverage"]),
    )
    claims: list[Claim] = []
    for item in manifest["claims"]:
        source = sources[item["source_id"]]
        if item["knowledge_kind"] != "source_assertion":
            raise ValueError("primary curation record must remain a source assertion")
        params = package_parameters + tuple(
            (key, str(value))
            for key, value in (
                ("domain", item["domain"]),
                ("statement", item["statement"]),
                ("source_title", source["title"]),
                ("source_doi", source["doi"]),
                ("source_locator", item["locator"]),
                ("source_access", source["access"]),
                ("source_metadata_retrieval_uri", source["retrieval_uri"]),
                (
                    "source_checksum_scope",
                    "retrieved Europe PMC bibliographic/abstract response",
                ),
                ("inclusion_rationale", item["inclusion_rationale"]),
                ("limitation", item["limitation"]),
            )
        )
        params += tuple(
            (key, str(source[key]))
            for key in ("fulltext_uri", "fulltext_sha256", "fulltext_retrieved_at")
            if key in source
        )
        claims.append(
            Claim(
                item["claim_id"],
                _entity(item["subject"]),
                item["predicate"],
                _entity(item["object"]),
                KnowledgeKind.SOURCE_ASSERTION,
                Provenance(
                    SourceKind.PUBLICATION,
                    source["source_id"],
                    datetime.fromisoformat(source["retrieved_at"]),
                    source["source_uri"],
                    "sha256:" + source["response_sha256"],
                    (Transformation("primary-source-atomic-curation", "1", params),),
                ),
                ClaimContext(**item["context"]),
            )
        )
    interpretation = Provenance(
        SourceKind.AXIS_PIPELINE,
        "AXIS:curated-assessment-rules:v1",
        now,
        checksum="sha256:" + digest,
        transformations=(
            Transformation(
                "curated-assessment-import",
                "1",
                package_parameters
                + (
                    (
                        "method",
                        "fixed package role/classification entries; "
                        "AI-assisted interpretation, expert review pending",
                    ),
                ),
            ),
        ),
    )
    proposal = Provenance(
        SourceKind.AI_MODEL,
        "AXIS:erap1-curated-proposals:v1",
        now,
        checksum="sha256:" + digest,
        transformations=(
            Transformation(
                "source-informed-conceptual-proposal",
                "1",
                package_parameters
                + (
                    (
                        "informing_claim_ids",
                        "|".join(claim.identifier for claim in claims),
                    ),
                ),
            ),
        ),
    )
    context = ClaimContext(
        hla_status="HLA-B27-positive context proposed; relevant subtype to be chosen",
        experimental_system="Disease-relevant cellular system not yet selected",
        endpoint="Peptide presentation, downstream phenotype and target engagement",
    )
    question = OpenQuestion(
        "AXIS-ERAP1-CURATED-QUESTION",
        project_id,
        "Does selective ERAP1 modulation alter disease-relevant HLA-B27 peptide "
        "presentation and downstream biology across relevant genotype "
        "and cell contexts?",
        "translation_and_context",
        QuestionStatus.OPEN,
        now,
        now,
        context,
    )
    strategies = tuple(
        InterventionStrategy(
            f"AXIS-ERAP1-CURATED-STRATEGY-{kind.value}",
            project_id,
            kind,
            label,
            "Competing source-informed proposal; clinical direction, relevant context "
            "and selectivity remain unresolved. No strategy is preferred.",
            StrategyStatus.PROPOSED,
            proposal,
            KnowledgeKind.AI_SUGGESTION,
        )
        for kind, label in (
            (StrategyType.INHIBIT, "Complete inhibition"),
            (StrategyType.PARTIALLY_INHIBIT, "Partial inhibition"),
            (StrategyType.ALLOSTERICALLY_MODULATE, "Allosteric modulation"),
            (
                StrategyType.ALLELE_SPECIFIC_MODULATION,
                "Allele/allotype-specific modulation",
            ),
        )
    )
    hypothesis = Claim(
        "AXIS-ERAP1-CURATED-HYPOTHESIS",
        EntityRef(
            EntityKind.PATHWAY,
            "hla-b27-peptide-presentation",
            "HLA-B27 peptide presentation",
            "AXIS-curated",
        ),
        "disease_effect_remains_hypothesized",
        disease,
        KnowledgeKind.AI_SUGGESTION,
        proposal,
        context,
    )
    experiment = ProposedExperiment(
        "AXIS-ERAP1-CURATED-EXPERIMENT",
        project_id,
        question.question_id,
        "Discriminate target engagement from disease-relevant biology",
        "The curated studies show altered peptide presentation and context-dependent "
        "surface HLA-B27 outcomes. Compare selective modulation across relevant "
        "genotypes and systems to separate biochemical activity "
        "from downstream biology.",
        "Conceptual HLA-B27-positive disease-relevant cellular system with explicit "
        "ERAP1 genotype/allotype strata; selection and feasibility require review.",
        "Compare a range of selective ERAP1 modulation concepts and suitable "
        "genetic/comparator controls. No compound, dose or operating "
        "protocol selected.",
        "Target engagement, immunopeptidome, HLA-B27 surface forms, downstream "
        "immune phenotype, viability and selectivity controls, measured separately.",
        proposal,
        ProposalOrigin.AXIS,
        KnowledgeKind.AI_SUGGESTION,
        ProposalStatus.PROPOSED,
        context,
    )
    with store._transaction():
        store.target_disease_pairs.add(pair)
        store.projects.add(project)
        for claim in (*claims, hypothesis):
            store.claims.add(claim)
            store.projects.add_claim(project_id, claim.identifier)
        store.questions.add(question)
        for strategy in strategies:
            store.strategies.add(strategy)
        for ordinal, entry in enumerate(manifest["assessments"], 1):
            subject = entry["subject"]
            store.evidence_assessments.add(
                EvidenceAssessment(
                    f"AXIS-ERAP1-CURATED-EA-{ordinal:02}",
                    project_id,
                    entry["claim_id"],
                    EvidenceRole(entry["role"]),
                    entry["reasoning"],
                    interpretation,
                    question_id=question.question_id if subject == "question" else None,
                    strategy_id=None
                    if subject == "question"
                    else f"AXIS-ERAP1-CURATED-STRATEGY-{subject}",
                )
            )
        for ordinal, entry in enumerate(manifest["mechanisms"], 1):
            store.mechanistic_assessments.add(
                MechanisticAssessment(
                    f"AXIS-ERAP1-CURATED-MA-{ordinal:02}",
                    project_id,
                    entry["claim_id"],
                    MechanismClassification(entry["classification"]),
                    entry["reasoning"],
                    interpretation,
                )
            )
        store.mechanistic_assessments.add(
            MechanisticAssessment(
                "AXIS-ERAP1-CURATED-MA-HYPOTHESIS",
                project_id,
                hypothesis.identifier,
                MechanismClassification.HYPOTHESIZED,
                "Clinical disease translation is a proposal, not directly demonstrated "
                "by the curated cellular observations.",
                proposal,
            )
        )
        perturbation_ids = []
        for number, kind in (
            (5, PerturbationType.KNOCKDOWN),
            (9, PerturbationType.INHIBITOR),
            (13, PerturbationType.KNOCKDOWN),
        ):
            observed = next(
                claim for claim in claims if claim.identifier.endswith(f"C{number:02}")
            )
            intervention = (
                EntityRef(EntityKind.DRUG, "DG013A", "DG013A", "publication-label")
                if number == 9
                else None
            )
            perturbation = Perturbation(
                f"AXIS-ERAP1-CURATED-P{number:02}",
                target,
                kind,
                PerturbationDirection.DECREASE,
                PerturbationStatus.PERFORMED,
                observed.provenance,
                KnowledgeKind.SOURCE_ASSERTION,
                observed.context,
                intervention,
                observed.identifier,
            )
            store.perturbations.add(perturbation)
            store.perturbations.add_to_project(project_id, perturbation.perturbation_id)
            perturbation_ids.append(perturbation.perturbation_id)
        store.questions.link(
            question.question_id,
            QuestionLinks(
                claim_ids=tuple(claim.identifier for claim in claims),
                strategy_ids=tuple(strategy.strategy_id for strategy in strategies),
                perturbation_ids=tuple(perturbation_ids),
            ),
        )
        store.proposed_experiments.add(experiment)
        for suffix, outcome, implication in (
            (
                "A",
                "Verified selective modulation changes relevant peptide presentation "
                "and downstream biology with interpretable controls.",
                "Would support the mechanism in that context and justify "
                "further validation; "
                "would not establish clinical benefit.",
            ),
            (
                "B",
                "Target engagement or enzyme activity changes without the intended "
                "peptide-presentation or downstream biological response.",
                "Would challenge translation from biochemical modulation in the tested "
                "context; system relevance and assay sensitivity would need review.",
            ),
        ):
            store.outcome_scenarios.add(
                OutcomeScenario(
                    f"AXIS-ERAP1-CURATED-OUTCOME-{suffix}",
                    experiment.experiment_id,
                    outcome,
                    implication,
                )
            )
    return DiscoveryService(store).inspect_project(project_id)
