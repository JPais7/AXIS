"""Synthetic domain tests never stand in for real ERAP1 scientific evidence."""

import json
import shutil
from contextlib import suppress
from dataclasses import replace
from importlib import resources
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from axis.cli.main import app
from axis.discovery import DiscoveryService
from axis.domain import EntityKind, EntityRef, Hypothesis, KnowledgeKind, SourceKind
from axis.domain.discovery import (
    DiscoveryProject,
    EvidenceAssessment,
    EvidenceRole,
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
    QuestionLinks,
    QuestionStatus,
    StrategyStatus,
    StrategyType,
    TargetDiseasePair,
)
from axis.storage import EvidenceStore, RecordConflictError, RecordNotFoundError
from tests.test_storage import NOW, first_revision, make_claim


def setup_project(store: EvidenceStore) -> DiscoveryProject:
    claim = make_claim()
    pair = TargetDiseasePair(
        "pair", claim.subject, claim.object, "synthetic scope", NOW
    )
    project = DiscoveryProject(
        "project", "pair", "Synthetic objective", ProjectStatus.DRAFT, NOW, NOW
    )
    store.target_disease_pairs.add(pair)
    store.projects.add(project)
    store.claims.add(claim)
    store.projects.add_claim(project.project_id, claim.identifier)
    return project


def setup_question(store: EvidenceStore, project_id: str = "project") -> OpenQuestion:
    question = OpenQuestion(
        "question",
        project_id,
        "Synthetic question?",
        "synthetic",
        QuestionStatus.OPEN,
        NOW,
        NOW,
    )
    store.questions.add(question)
    return question


def test_pair_identity_and_entity_validation() -> None:
    claim = make_claim()
    pair = TargetDiseasePair(
        "pair", claim.subject, claim.object, " Synthetic scope ", NOW
    )
    assert (
        pair.identity_key
        == replace(
            pair, pair_id="other", indication_scope="synthetic SCOPE"
        ).identity_key
    )
    assert (
        pair.identity_key
        != replace(pair, target=replace(pair.target, namespace="other")).identity_key
    )
    with pytest.raises(ValueError, match="target"):
        replace(pair, target=claim.object)
    with pytest.raises(ValueError, match="disease"):
        replace(pair, disease=claim.subject)
    with EvidenceStore() as store:
        store.target_disease_pairs.add(pair)
        store.target_disease_pairs.add(pair)
        assert store.target_disease_pairs.get("pair") == pair
        with pytest.raises(RecordConflictError, match="already exists"):
            store.target_disease_pairs.add(replace(pair, pair_id="other"))


def test_project_and_claim_membership_are_immutable_idempotent() -> None:
    with EvidenceStore() as store:
        project = setup_project(store)
        assert store.projects.get("project") == project
        assert store.projects.list_all() == (project,)
        store.projects.add(project)
        store.projects.add_claim("project", "claim-1")
        assert store.projects.claims("project") == (make_claim(),)
        with pytest.raises(RecordConflictError):
            store.projects.add(replace(project, objective="changed"))
        with pytest.raises(RecordNotFoundError):
            store.projects.add_claim("project", "missing")
        assert len(store.projects.claims("project")) == 1
        with pytest.raises(ValueError):
            replace(project, status="arbitrary")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="timezone"):
            replace(project, created_at=NOW.replace(tzinfo=None))


def test_missing_project_pair_rolls_back() -> None:
    with EvidenceStore() as store:
        with pytest.raises(RecordNotFoundError):
            store.projects.add(
                DiscoveryProject(
                    "bad", "missing", "objective", ProjectStatus.DRAFT, NOW, NOW
                )
            )
        assert store.projects.list_all() == ()


@pytest.mark.parametrize("kind", tuple(PerturbationType))
def test_performed_perturbation_round_trip(kind: PerturbationType) -> None:
    with EvidenceStore() as store:
        setup_project(store)
        claim = make_claim()
        perturbation = Perturbation(
            "perturbation",
            claim.subject,
            kind,
            PerturbationDirection.UNKNOWN,
            PerturbationStatus.PERFORMED,
            claim.provenance,
            KnowledgeKind.SOURCE_ASSERTION,
            claim.context,
            EntityRef(EntityKind.DRUG, "synthetic", "Synthetic intervention", "test"),
            claim.identifier,
        )
        store.perturbations.add(perturbation)
        store.perturbations.add_to_project("project", "perturbation")
        assert store.perturbations.get("perturbation") == perturbation
        assert store.perturbations.list_for_project("project") == (perturbation,)


def test_proposed_perturbation_cannot_have_observed_effect() -> None:
    claim = make_claim()
    proposal = Perturbation(
        "proposal",
        claim.subject,
        PerturbationType.INHIBITOR,
        PerturbationDirection.DECREASE,
        PerturbationStatus.PROPOSED,
        claim.provenance,
        KnowledgeKind.RESEARCHER_HYPOTHESIS,
    )
    with pytest.raises(ValueError, match="observed"):
        replace(proposal, observed_effect_claim_id="claim-1")
    with pytest.raises(ValueError, match="proposal kind"):
        replace(proposal, knowledge_kind=KnowledgeKind.EXPERIMENTAL_RESULT)
    with EvidenceStore() as store:
        store.perturbations.add(proposal)
        assert store.perturbations.get("proposal") == proposal
        with pytest.raises(RecordNotFoundError):
            store.perturbations.add(
                replace(
                    proposal,
                    perturbation_id="missing-effect",
                    status=PerturbationStatus.PERFORMED,
                    knowledge_kind=KnowledgeKind.EXPERIMENTAL_RESULT,
                    observed_effect_claim_id="missing",
                )
            )
        assert store.perturbations.get_optional("missing-effect") is None


@pytest.mark.parametrize(
    "kind",
    (
        KnowledgeKind.AI_SUGGESTION,
        KnowledgeKind.RESEARCHER_HYPOTHESIS,
        KnowledgeKind.AXIS_INFERENCE,
    ),
)
def test_observed_effect_rejects_proposal_claim(kind: KnowledgeKind) -> None:
    with EvidenceStore() as store:
        claim = replace(make_claim(), knowledge_kind=kind)
        store.claims.add(claim)
        with pytest.raises(ValueError, match="observational claim"):
            store.perturbations.add(
                Perturbation(
                    "bad",
                    claim.subject,
                    PerturbationType.KNOCKDOWN,
                    PerturbationDirection.DECREASE,
                    PerturbationStatus.PERFORMED,
                    claim.provenance,
                    KnowledgeKind.SOURCE_ASSERTION,
                    observed_effect_claim_id=claim.identifier,
                )
            )
        assert store.perturbations.list_all() == ()


@pytest.mark.parametrize("role", tuple(EvidenceRole))
def test_evidence_roles_and_legacy_hypothesis_links(role: EvidenceRole) -> None:
    with EvidenceStore() as store:
        setup_project(store)
        question = setup_question(store)
        hypothesis = Hypothesis(
            "hyp", "Synthetic hypothesis", (first_revision(("claim-1",)),)
        )
        store.hypotheses.add(hypothesis)
        for subject in (
            {"question_id": question.question_id},
            {"hypothesis_id": "hyp", "hypothesis_revision": 1},
        ):
            assessment = EvidenceAssessment(
                f"assessment-{role}-{next(iter(subject))}",
                "project",
                "claim-1",
                role,
                "Synthetic assessment reasoning",
                make_claim().provenance,
                **subject,
            )
            store.evidence_assessments.add(assessment)
            assert (
                store.evidence_assessments.get(assessment.assessment_id) == assessment
            )
        assert store.hypotheses.get("hyp") == hypothesis
        assert store.hypotheses.get("hyp").current.evidence_ids == ("claim-1",)


@pytest.mark.parametrize(
    "classification,kind",
    (
        (MechanismClassification.DIRECTLY_DEMONSTRATED, KnowledgeKind.SOURCE_ASSERTION),
        (MechanismClassification.INFERRED, KnowledgeKind.AXIS_INFERENCE),
        (
            MechanismClassification.COMPUTATIONALLY_PREDICTED,
            KnowledgeKind.AXIS_OBSERVATION,
        ),
        (MechanismClassification.HYPOTHESIZED, KnowledgeKind.RESEARCHER_HYPOTHESIS),
    ),
)
def test_mechanism_assessment_round_trip(
    classification: MechanismClassification, kind: KnowledgeKind
) -> None:
    with EvidenceStore() as store:
        setup_project(store)
        claim = replace(make_claim(), identifier="mechanism", knowledge_kind=kind)
        store.claims.add(claim)
        store.projects.add_claim("project", "mechanism")
        assessment = MechanisticAssessment(
            "mechanism-assessment",
            "project",
            "mechanism",
            classification,
            "Synthetic rationale",
            claim.provenance,
        )
        store.mechanistic_assessments.add(assessment)
        assert store.mechanistic_assessments.get(assessment.assessment_id) == assessment


def test_question_links_and_batch_rollback() -> None:
    with EvidenceStore() as store:
        setup_project(store)
        question = setup_question(store)
        store.hypotheses.add(Hypothesis("hyp", "Synthetic", (first_revision(),)))
        links = QuestionLinks(claim_ids=("claim-1",), hypothesis_ids=("hyp",))
        store.questions.link(question.question_id, links)
        store.questions.link(question.question_id, links)
        assert store.questions.links(question.question_id) == links
        with pytest.raises(RecordNotFoundError):
            store.questions.link(
                question.question_id,
                QuestionLinks(claim_ids=("claim-1",), hypothesis_ids=("missing",)),
            )
        assert store.questions.links(question.question_id) == links
        assert store.questions.get(question.question_id) == question


def test_cross_project_references_and_membership_rejected() -> None:
    with EvidenceStore() as store:
        setup_project(store)
        question = setup_question(store)
        demo = DiscoveryService(store).create_erap1_demo()
        with pytest.raises(ValueError, match="different project"):
            store.questions.link(
                question.question_id,
                QuestionLinks(strategy_ids=(demo.strategies[0].strategy_id,)),
            )
        with pytest.raises(ValueError, match="target differs"):
            store.perturbations.add_to_project(
                "project", demo.perturbations[0].perturbation_id
            )
        with pytest.raises(ValueError, match="different project"):
            store.proposed_experiments.add(
                replace(demo.experiments[0], experiment_id="bad", project_id="project")
            )
        with pytest.raises(RecordNotFoundError, match="member"):
            store.mechanistic_assessments.add(
                MechanisticAssessment(
                    "bad",
                    demo.project.project_id,
                    "claim-1",
                    MechanismClassification.DIRECTLY_DEMONSTRATED,
                    "wrong scope",
                    make_claim().provenance,
                )
            )
        assert store.proposed_experiments.get_optional("bad") is None


@pytest.mark.parametrize("kind", tuple(StrategyType))
def test_strategy_evidence_assessment_round_trip(kind: StrategyType) -> None:
    with EvidenceStore() as store:
        setup_project(store)
        claim = make_claim()
        strategy = InterventionStrategy(
            "strategy",
            "project",
            kind,
            "Synthetic concept",
            "Synthetic rationale",
            StrategyStatus.PROPOSED,
            claim.provenance,
        )
        store.strategies.add(strategy)
        store.strategies.add(strategy)
        assessment = EvidenceAssessment(
            "assessment",
            "project",
            claim.identifier,
            EvidenceRole.CONTRADICTS,
            "Synthetic contradictory evidence reasoning",
            claim.provenance,
            strategy_id=strategy.strategy_id,
        )
        store.evidence_assessments.add(assessment)
        assert store.strategies.get(strategy.strategy_id) == strategy
        assert store.evidence_assessments.get("assessment") == assessment


def test_database_foreign_key_failure_rolls_back_batch() -> None:
    with EvidenceStore() as store:
        setup_project(store)
        with pytest.raises(duckdb.ConstraintException), store._transaction():
            setup_question(store)
            store._connection.execute(
                "INSERT INTO question_claims VALUES ('question', 'missing')"
            )
        assert store.questions.get_optional("question") is None
        assert len(store.projects.claims("project")) == 1


def test_unknown_context_and_protein_pair_are_generic() -> None:
    claim = make_claim()
    protein = replace(claim.subject, kind=EntityKind.PROTEIN)
    pair = TargetDiseasePair("protein-pair", protein, claim.object, "other scope", NOW)
    with EvidenceStore() as store:
        store.target_disease_pairs.add(pair)
        assert store.target_disease_pairs.get(pair.pair_id) == pair


def test_ai_suggestions_never_become_observational_evidence() -> None:
    with EvidenceStore() as store:
        demo = DiscoveryService(store).create_erap1_demo()
        claim = demo.claims[0]
        with pytest.raises(ValueError, match="AI source"):
            replace(
                demo.experiments[0], knowledge_kind=KnowledgeKind.EXPERIMENTAL_RESULT
            )
        with pytest.raises(ValueError, match="incompatible"):
            store.mechanistic_assessments.add(
                replace(
                    demo.mechanisms[0],
                    assessment_id="bad",
                    classification=MechanismClassification.DIRECTLY_DEMONSTRATED,
                    provenance=make_claim().provenance,
                )
            )
        with pytest.raises(ValueError, match="proposals"):
            store.evidence_assessments.add(
                EvidenceAssessment(
                    "bad",
                    demo.project.project_id,
                    claim.identifier,
                    EvidenceRole.SUPPORTS,
                    "Cannot turn a suggestion into evidence",
                    make_claim().provenance,
                    strategy_id=demo.strategies[0].strategy_id,
                )
            )
        considered = EvidenceAssessment(
            "considered",
            demo.project.project_id,
            claim.identifier,
            EvidenceRole.UNTYPED_CONSIDERED,
            "Proposal considered, not evidence",
            claim.provenance,
            question_id=demo.questions[0].question_id,
        )
        store.evidence_assessments.add(considered)
        assert store.evidence_assessments.get("considered") == considered


def test_demo_traversal_reopens_and_is_repeatable(tmp_path: Path) -> None:
    database = tmp_path / "demo.duckdb"
    with EvidenceStore(database) as store:
        service = DiscoveryService(store)
        traversal = service.create_erap1_demo()
        assert service.create_erap1_demo() == traversal
        assert len(traversal.strategies) == 4
        assert len(traversal.outcomes) == 2
        assert len(traversal.mechanisms) == 1
        assert (
            traversal.mechanisms[0].classification
            == MechanismClassification.HYPOTHESIZED
        )
        assert all(
            claim.knowledge_kind == KnowledgeKind.AI_SUGGESTION
            for claim in traversal.claims
        )
        assert all(
            item.status == PerturbationStatus.PROPOSED
            for item in traversal.perturbations
        )
        assert all(
            item.observed_effect_claim_id is None for item in traversal.perturbations
        )
        assert traversal.experiments[0].suggestion_origin == ProposalOrigin.AXIS
        assert all(
            item.provenance.source_kind == SourceKind.AI_MODEL
            for item in traversal.claims
        )
        assert traversal.assessments == ()
    with EvidenceStore(database) as reopened:
        assert (
            DiscoveryService(reopened).inspect_project(traversal.project.project_id)
            == traversal
        )
        assert reopened.statistics().schema_version == 11


def test_demo_creation_rolls_back_conflicting_fixture(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "conflict.duckdb") as store:
        seed = make_claim()
        store.claims.add(replace(seed, identifier="AXIS-DEMO-ERAP1-MECHANISM"))
        with pytest.raises(RecordConflictError):
            DiscoveryService(store).create_erap1_demo()
        assert store.projects.list_all() == ()
        assert store.target_disease_pairs.list_all() == ()
        assert store.statistics().claims == 1


def test_nested_transaction_failure_is_rollback_only() -> None:
    with EvidenceStore() as store:
        with pytest.raises(RuntimeError, match="nested"), store._transaction():
            setup_project(store)
            with suppress(RecordNotFoundError):
                store.projects.add_claim("project", "missing")
        assert store.projects.list_all() == ()
        assert store.statistics().claims == 0


def test_outcome_fk_and_experiment_classification() -> None:
    with EvidenceStore() as store:
        with pytest.raises(RecordNotFoundError):
            store.outcome_scenarios.add(
                OutcomeScenario("bad", "missing", "possible", "interpretation")
            )
        assert store.outcome_scenarios.list_all() == ()
        demo = DiscoveryService(store).create_erap1_demo()
        experiment = demo.experiments[0]
        with pytest.raises(ValueError, match="AI source"):
            replace(experiment, knowledge_kind=KnowledgeKind.SOURCE_ASSERTION)
        with pytest.raises(ValueError, match="compatible proposal kind"):
            replace(experiment, suggestion_origin=ProposalOrigin.RESEARCHER)


def test_version_2_migration_backup_and_reopen(tmp_path: Path) -> None:
    database = tmp_path / "legacy.duckdb"
    migration_root = resources.files("axis.storage.migrations")
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
            "name VARCHAR NOT NULL, applied_at TIMESTAMPTZ DEFAULT current_timestamp)"
        )
        for version, name in ((1, "001_initial.sql"), (2, "002_studies.sql")):
            connection.execute(migration_root.joinpath(name).read_text())
            connection.execute(
                "INSERT INTO schema_migrations(version,name) VALUES (?,?)",
                [version, name],
            )
        connection.execute(
            "INSERT INTO entities VALUES ('gene','test','g','Gene'), "
            "('disease','test','d','Disease')"
        )
        connection.execute(
            "INSERT INTO claims(identifier,subject_kind,subject_namespace,"
            "subject_identifier,"
            "predicate,object_kind,object_namespace,object_identifier,knowledge_kind,"
            "source_kind,source_identifier,retrieved_at) VALUES "
            "('legacy','gene','test','g','associated_with','disease','test','d',"
            "'axis_observation','axis_pipeline','legacy-run',?)",
            [NOW],
        )
        connection.execute("INSERT INTO hypotheses VALUES ('legacy-hyp','Legacy')")
        connection.execute(
            "INSERT INTO hypothesis_revisions VALUES "
            "('legacy-hyp',1,?,'draft','Description','Rationale',NULL)",
            [NOW],
        )
        connection.execute(
            "INSERT INTO hypothesis_evidence VALUES ('legacy-hyp',1,0,'legacy')"
        )
    backup = tmp_path / "legacy-before-upgrade.duckdb"
    shutil.copy2(database, backup)
    with EvidenceStore(database) as store:
        claim = store.claims.get("legacy")
        assert claim.knowledge_kind == KnowledgeKind.AXIS_OBSERVATION
        assert claim.context.cell_type is None
        assert claim.context.genotype is None
        assert store.hypotheses.get("legacy-hyp").current.evidence_ids == ("legacy",)
        assert store.evidence_assessments.list_all() == ()
        assert store.statistics().schema_version == 11
    with EvidenceStore(database) as reopened:
        assert reopened.claims.get("legacy") == claim
    with duckdb.connect(str(backup), read_only=True) as connection:
        assert connection.execute(
            "SELECT max(version) FROM schema_migrations"
        ).fetchone() == (2,)
        assert connection.execute("SELECT count(*) FROM claims").fetchone() == (1,)


def test_cli_demo_inspection_and_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    prefix = ["--database", str(tmp_path / "cli.duckdb"), "discovery"]
    assert runner.invoke(app, [*prefix, "demo"]).exit_code == 0
    for subgroup in ("project", "question", "strategy", "perturbation"):
        args = [*prefix, subgroup, "list"]
        if subgroup != "project":
            args.append("AXIS-DD-ERAP1-001")
        assert runner.invoke(app, args).exit_code == 0
    output = runner.invoke(
        app, [*prefix, "project", "show", "AXIS-DD-ERAP1-001", "--json"]
    )
    assert output.exit_code == 0, output.output
    data = json.loads(output.output)
    assert data["claims"][0]["knowledge_kind"] == "ai_suggestion"
    assert len(data["outcomes"]) == 2
    human = runner.invoke(app, [*prefix, "project", "show", "AXIS-DD-ERAP1-001"])
    assert "no winner selected" in human.output
    assert "hypothesized" in human.output
    assert "Observed effect claim: none" in human.output
    missing = runner.invoke(app, [*prefix, "project", "show", "missing"])
    assert missing.exit_code == 1
    assert "not found" in missing.output
