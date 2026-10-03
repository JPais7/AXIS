"""Persist and inspect the minimum evidence-to-proposal discovery loop."""

from dataclasses import dataclass
from datetime import UTC, datetime

from axis.domain.discovery import (
    DiscoveryProject,
    EvidenceAssessment,
    InterventionStrategy,
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
    QuestionLinks,
    QuestionStatus,
    StrategyStatus,
    StrategyType,
    TargetDiseasePair,
)
from axis.domain.models import (
    Claim,
    ClaimContext,
    EntityKind,
    EntityRef,
    KnowledgeKind,
    Provenance,
    SourceKind,
    Transformation,
)
from axis.storage import EvidenceStore


@dataclass(frozen=True)
class ProjectTraversal:
    project: DiscoveryProject
    pair: TargetDiseasePair
    claims: tuple[Claim, ...]
    mechanisms: tuple[MechanisticAssessment, ...]
    perturbations: tuple[Perturbation, ...]
    strategies: tuple[InterventionStrategy, ...]
    questions: tuple[OpenQuestion, ...]
    experiments: tuple[ProposedExperiment, ...]
    outcomes: tuple[OutcomeScenario, ...]
    assessments: tuple[EvidenceAssessment, ...]
    question_links: tuple[tuple[str, QuestionLinks], ...]


class DiscoveryService:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    def project_identity(
        self, project_id: str
    ) -> tuple[DiscoveryProject, TargetDiseasePair]:
        """Read project identity without materializing its evidence neighborhood."""
        project = self.store.projects.get(project_id)
        return project, self.store.target_disease_pairs.get(project.target_disease_pair)

    def inspect_project(self, project_id: str) -> ProjectTraversal:
        project = self.store.projects.get(project_id)
        experiments = self.store.proposed_experiments.list_for_project(project_id)
        questions = self.store.questions.list_for_project(project_id)
        return ProjectTraversal(
            project=project,
            pair=self.store.target_disease_pairs.get(project.target_disease_pair),
            claims=self.store.projects.claims(project_id),
            mechanisms=self.store.mechanistic_assessments.list_for_project(project_id),
            perturbations=self.store.perturbations.list_for_project(project_id),
            strategies=self.store.strategies.list_for_project(project_id),
            questions=questions,
            experiments=experiments,
            outcomes=tuple(
                outcome
                for experiment in experiments
                for outcome in self.store.outcome_scenarios.list_for_experiment(
                    experiment.experiment_id
                )
            ),
            assessments=self.store.evidence_assessments.list_for_project(project_id),
            question_links=tuple(
                (question.question_id, self.store.questions.links(question.question_id))
                for question in questions
            ),
        )

    def create_erap1_demo(self) -> ProjectTraversal:
        """Atomic, repeatable DEVELOPMENT fixture. Contains no source facts/results.

        The suggested mechanistic edge is explicitly a hypothesis for exercising
        storage. It is not imported literature evidence or verified AXIS biology.
        """
        now = datetime(2026, 10, 3, tzinfo=UTC)
        project_id = "AXIS-DD-ERAP1-001"
        target = EntityRef(EntityKind.GENE, "ERAP1", "ERAP1", "HGNC-symbol")
        disease = EntityRef(
            EntityKind.DISEASE, "axSpA", "axial spondyloarthritis", "AXIS"
        )
        provenance = Provenance(
            SourceKind.AI_MODEL,
            "axis-development-demo:erap1-axspa:v1",
            now,
            transformations=(
                Transformation(
                    "development-proposal-fixture",
                    "1",
                    (
                        ("scientific_evidence_imported", "false"),
                        ("purpose", "storage traversal demonstration"),
                    ),
                ),
            ),
        )
        context = ClaimContext(
            hla_status="HLA-B27-positive (proposed context)",
            experimental_system="axSpA-relevant cellular context; not yet selected",
            endpoint="peptide presentation and downstream biology",
        )
        pair = TargetDiseasePair(
            "AXIS-TD-ERAP1-AXSPA",
            target,
            disease,
            "axial spondyloarthritis; subtype applicability unassessed",
            now,
        )
        project = DiscoveryProject(
            project_id,
            pair.pair_id,
            "Evaluate the evidence for pharmacological modulation of ERAP1 as a "
            "therapeutic strategy in axial spondyloarthritis.",
            ProjectStatus.DRAFT,
            now,
            now,
        )
        mechanism_claim = Claim(
            "AXIS-DEMO-ERAP1-MECHANISM",
            target,
            "hypothesized_modulation_may_alter",
            EntityRef(
                EntityKind.PATHWAY,
                "hla-b27-peptide-presentation",
                "HLA-B27-associated peptide presentation",
                "AXIS-demo",
            ),
            KnowledgeKind.AI_SUGGESTION,
            provenance,
            context,
        )
        question = OpenQuestion(
            "AXIS-DEMO-ERAP1-QUESTION",
            project_id,
            "Does pharmacological modulation of ERAP1 produce a disease-relevant "
            "alteration in HLA-B27-associated peptide presentation and downstream "
            "biology in an axSpA-relevant context?",
            "mechanism_translation",
            QuestionStatus.OPEN,
            now,
            now,
            context,
        )
        perturbation = Perturbation(
            "AXIS-DEMO-ERAP1-PERTURBATION",
            target,
            PerturbationType.ALLOSTERIC_MODULATOR,
            PerturbationDirection.MODULATE,
            PerturbationStatus.PROPOSED,
            provenance,
            KnowledgeKind.AI_SUGGESTION,
            context,
        )
        strategies = tuple(
            InterventionStrategy(
                f"AXIS-DEMO-ERAP1-{kind.value}",
                project_id,
                kind,
                description,
                "Competing development proposal; supporting and contradictory "
                "source evidence has not been curated. No strategy is preferred.",
                StrategyStatus.PROPOSED,
                provenance,
                KnowledgeKind.AI_SUGGESTION,
            )
            for kind, description in (
                (StrategyType.INHIBIT, "Complete inhibition (proposal)"),
                (StrategyType.PARTIALLY_INHIBIT, "Partial inhibition (proposal)"),
                (
                    StrategyType.ALLOSTERICALLY_MODULATE,
                    "Allosteric modulation (proposal)",
                ),
                (
                    StrategyType.ALLELE_SPECIFIC_MODULATION,
                    "Allele/allotype-specific modulation (proposal)",
                ),
            )
        )
        experiment = ProposedExperiment(
            "AXIS-DEMO-ERAP1-EXPERIMENT",
            project_id,
            question.question_id,
            "Compare ERAP1 modulation across relevant contexts",
            "Discriminate a change in enzyme activity alone from a change in "
            "disease-relevant peptide presentation and downstream biology. "
            "Context, selectivity controls and feasibility require expert review.",
            "Conceptual HLA-B27-positive cellular system with relevant ERAP1 "
            "genotype/allotype contexts; system selection is unresolved.",
            "Compare candidate modulation strategies with suitable comparator "
            "contexts; no compound or operating protocol has been selected.",
            "Separate biochemical activity, peptide repertoire, downstream "
            "phenotype and viability/selectivity readouts.",
            provenance,
            ProposalOrigin.AXIS,
            KnowledgeKind.AI_SUGGESTION,
            ProposalStatus.PROPOSED,
            context,
        )
        outcomes = (
            OutcomeScenario(
                "AXIS-DEMO-ERAP1-OUTCOME-A",
                experiment.experiment_id,
                "Relevant peptide presentation and downstream biology change "
                "alongside verified modulation, with interpretable controls.",
                "Would support further investigation of the proposed mechanism "
                "in the tested context; would not establish therapeutic benefit.",
            ),
            OutcomeScenario(
                "AXIS-DEMO-ERAP1-OUTCOME-B",
                experiment.experiment_id,
                "Biochemical activity changes without the relevant peptide "
                "presentation or downstream biological change.",
                "Would challenge translation from enzyme modulation to the "
                "proposed mechanism in the tested context; alternative contexts "
                "and assay sensitivity would remain questions.",
            ),
        )
        with self.store._transaction():
            self.store.target_disease_pairs.add(pair)
            self.store.projects.add(project)
            self.store.claims.add(mechanism_claim)
            self.store.projects.add_claim(project_id, mechanism_claim.identifier)
            self.store.mechanistic_assessments.add(
                MechanisticAssessment(
                    "AXIS-DEMO-ERAP1-MECHANISM-ASSESSMENT",
                    project_id,
                    mechanism_claim.identifier,
                    MechanismClassification.HYPOTHESIZED,
                    "Unverified development proposal, not demonstrated evidence.",
                    provenance,
                )
            )
            self.store.perturbations.add(perturbation)
            self.store.perturbations.add_to_project(
                project_id, perturbation.perturbation_id
            )
            for strategy in strategies:
                self.store.strategies.add(strategy)
            self.store.questions.add(question)
            self.store.questions.link(
                question.question_id,
                QuestionLinks(
                    claim_ids=(mechanism_claim.identifier,),
                    strategy_ids=tuple(strategy.strategy_id for strategy in strategies),
                    perturbation_ids=(perturbation.perturbation_id,),
                ),
            )
            self.store.proposed_experiments.add(experiment)
            for outcome in outcomes:
                self.store.outcome_scenarios.add(outcome)
        return self.inspect_project(project_id)
