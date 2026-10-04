"""Deterministic decision engine; reads stored evidence, never the network or an LLM.

Wording of explanations and candidate experiments is an imported AI suggestion
(frozen package). Evidence links, statuses, uncertainties, the critical
uncertainty and the recommendation are derived here by ``axis.decision.rules``.
"""

import hashlib
import json
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from axis.cellular.rules import aggregate
from axis.cellular.service import CellularPharmacologyService
from axis.decision import engine, rules
from axis.domain.decision import (
    CandidateExperimentProfile,
    CompetingExplanation,
    DecisionConsequence,
    DecisionConstraints,
    DecisionState,
    OutcomeInterpretation,
)
from axis.domain.discovery import (
    OutcomeScenario,
    ProposalOrigin,
    ProposalStatus,
    ProposedExperiment,
)
from axis.domain.models import (
    Hypothesis,
    HypothesisRevision,
    HypothesisState,
    KnowledgeKind,
    Provenance,
    SourceKind,
)
from axis.experiments import policy
from axis.experiments.results import ResultsService
from axis.storage import EvidenceStore, RecordNotFoundError

VERSION = "axis-decision-1"
ENGINE = "AXIS deterministic decision engine"
GENETIC = {"knockdown", "knockout", "CRISPR", "variant_expression"}
TRANSITIONS = {
    "proposed": {"investigator_selected", "cancelled"},
    "investigator_selected": {"planned", "cancelled"},
    "planned": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled", "failed_technical"},
    "completed": {"completed_interpretable", "completed_non_interpretable"},
    "completed_interpretable": set(),
    "completed_non_interpretable": set(),
    "failed_technical": set(),
    "cancelled": set(),
}
WEAKENING = {
    "weaken_current_strategy",
    "deprioritize_current_strategy",
    "change_mechanistic_model",
    "stop_for_now",
}
STRENGTHENING = {"strengthen_current_strategy", "advance_to_next_evidence_layer"}
CRITERIA_NAMES = (
    "explanation pairs separated",
    "distinct next actions across outcomes",
    "interpretability",
    "target proximity",
    "unestablished prerequisites",
    "identifier tie-break",
)


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest_of(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _label(value: str) -> str:
    return value.replace("_", " ")


def _named(text: str, names: dict[str, str]) -> str:
    for identifier, name in names.items():
        text = text.replace(identifier, name)
    return text


class DecisionService:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    # -- import ------------------------------------------------------------

    def import_package(
        self, project: str, protein: str, directory: Path | None = None
    ) -> dict[str, Any]:
        target = self.store.targets.require_member(project, protein)
        if target.primary_accession != "Q9NZ08" or target.taxon_id != 9606:
            raise ValueError("reference package requires human ERAP1")
        root = directory or resources.files("axis").joinpath(
            "resources/decision/erap1-axspa/v1"
        )
        raw = root.joinpath("manifest.json").read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != root.joinpath("manifest.sha256").read_text().strip():
            raise ValueError("decision package checksum mismatch")
        package = json.loads(raw)
        if package["importer_version"] != VERSION:
            raise ValueError("unsupported decision importer")
        now = datetime.fromisoformat(package["curated_at"])
        provenance = Provenance(SourceKind.AI_MODEL, VERSION, now, checksum=digest)
        hyp = package["hypothesis"]
        with self.store._transaction():
            self.store.hypotheses.add(
                Hypothesis(
                    hyp["id"],
                    hyp["title"],
                    (
                        HypothesisRevision(
                            1,
                            now,
                            HypothesisState.DRAFT,
                            hyp["description"],
                            hyp["rationale"],
                            tuple(hyp["evidence_ids"]),
                        ),
                    ),
                )
            )
            for item in package["explanations"]:
                self.store.decisions.add_explanation(
                    protein,
                    CompetingExplanation(
                        item["id"],
                        project,
                        hyp["id"],
                        1,
                        item["ground"],
                        item["label"],
                        item["statement"],
                    ),
                )
            for item in package["candidate_experiments"]:
                self._import_candidate(project, protein, package, item, provenance)
        return {
            "manifest_sha256": digest,
            "hypothesis": hyp["id"],
            "explanations": len(package["explanations"]),
            "candidate_experiments": len(package["candidate_experiments"]),
            "review_status": package["review_status"],
        }

    def _import_candidate(
        self,
        project: str,
        protein: str,
        package: dict[str, Any],
        item: dict[str, Any],
        provenance: Provenance,
    ) -> None:
        grounds = {e["ground"]: e["id"] for e in package["explanations"]}
        self.store.proposed_experiments.add(
            ProposedExperiment(
                item["id"],
                project,
                package["question_id"],
                item["title"],
                item["rationale"],
                item["experimental_system"],
                item["intervention_description"],
                item["endpoint_description"],
                provenance,
                ProposalOrigin.AXIS,
                KnowledgeKind.AI_SUGGESTION,
                ProposalStatus.PROPOSED,
            )
        )
        raw = item["profile"]
        profile = CandidateExperimentProfile(
            experiment_id=item["id"],
            purpose=raw["purpose"],
            role=raw["role"],
            target_proximity=raw["target_proximity"],
            disease_relevance=raw["disease_relevance"],
            considered_for=tuple(raw["considered_for"]),
            addressed_gap_ids=tuple(raw["addressed_gap_ids"]),
            controls_negative=tuple(raw["controls_negative"]),
            controls_positive=tuple(raw["controls_positive"]),
            primary_endpoint=raw["primary_endpoint"],
            secondary_endpoints=tuple(raw["secondary_endpoints"]),
            limitations=tuple(raw["limitations"]),
            prerequisites=tuple((a, b) for a, b in raw["prerequisites"]),
            required={k: tuple(v) for k, v in raw["required"].items()},
            confounders_addressed=tuple(raw["confounders_addressed"]),
            context_requirements=raw["context_requirements"],
            complexity=raw["complexity"],
            time_estimate=raw["time_estimate"],
        )
        affected: set[str] = set()
        for scenario in item["scenarios"]:
            affected |= {
                grounds[g]
                for g, (effect, _) in scenario["effects"].items()
                if effect != "does_not_discriminate"
            }
        self.store.decisions.add_profile(
            project, protein, profile, tuple(sorted(affected))
        )
        for scenario in item["scenarios"]:
            identifier = f"{item['id']}:{scenario['key']}"
            self.store.outcome_scenarios.add(
                OutcomeScenario(
                    identifier,
                    item["id"],
                    scenario["outcome"],
                    scenario["interpretation"],
                )
            )
            for ground, (effect, why) in scenario["effects"].items():
                self.store.decisions.add_interpretation(
                    OutcomeInterpretation(identifier, grounds[ground], effect, why)
                )
            cons = scenario["consequence"]
            self.store.decisions.add_consequence(
                DecisionConsequence(
                    identifier,
                    scenario["kind"],
                    cons["category"],
                    cons["statement"],
                    cons.get("new_uncertainty"),
                )
            )

    # -- evidence ----------------------------------------------------------

    def _review_states(self, project: str, object_type: str) -> dict[str, str]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for review in self.store.results.reviews(project, object_type):
            grouped.setdefault(review["object_id"], []).append(review)
        return {k: policy.review_state(v)["state"] for k, v in grouped.items()}

    def evidence(
        self,
        project: str,
        protein: str,
        mode: str = "exploratory",
        ledger: list[dict[str, Any]] | None = None,
    ) -> rules.Evidence:
        self.store.targets.require_member(project, protein)
        cell = CellularPharmacologyService(self.store)
        chain = cell.chain(project, protein)
        assessment_reviews = self._review_states(project, "evidence_assessment")

        def keep(identifier: str) -> bool:
            state = assessment_reviews.get(identifier, "pending")
            return state in ("accepted", "accepted_with_caveat") or (
                state == "pending" and mode == "exploratory"
            )

        edges = {}
        for e in chain["edges"]:
            kept = [a for a in e["assessments"] if keep(a["id"])]
            state = e["state"]
            if len(kept) != len(e["assessments"]):
                state = aggregate([a["state"] for a in kept])
                if e["edge"] == "biochemical" and e["measurements"]:
                    state = "supported"
            edges[e["edge"]] = {
                "state": state,
                "ids": sorted(
                    [a["id"] for a in kept] + [m["id"] for m in e["measurements"]]
                ),
            }
        repo = self.store.cellular
        windows = {
            kind: repo.collection(project, protein, kind, 100)
            for kind in ("experiments", "assessments", "readouts")
        }
        truncated = [kind for kind, page in windows.items() if page["has_more"]]
        if chain["has_more"] or truncated:
            raise ValueError(
                "evidence window exceeded the bounded read size ("
                + ", ".join(truncated or ["evidence chain"])
                + "); the decision engine refuses to run on truncated evidence"
            )
        experiments = windows["experiments"]["items"]
        all_assessments = windows["assessments"]["items"]
        assessments = [a for a in all_assessments if keep(a["id"])]
        pending_assessments = sum(
            assessment_reviews.get(a["id"], "pending") == "pending" for a in assessments
        )
        readouts = windows["readouts"]["items"]
        modality = {e["id"]: e["modality"] for e in experiments}
        phenotype = [a for a in assessments if a["edge"] in ("hla", "immune")]

        def pick(compound: bool, **match: str) -> list[str]:
            return sorted(
                a["id"]
                for a in phenotype
                if (modality[a["experiment_id"]] == "small_molecule") == compound
                and all(a[k] == v for k, v in match.items())
            )

        genetic = sorted(
            a["id"]
            for a in phenotype
            if modality[a["experiment_id"]] in GENETIC
            and a["dependency"] == "supported"
        )
        selectivity_page = self.store.pharmacology.collection(
            project, protein, "selectivity", 100, 0
        )
        if selectivity_page["has_more"]:
            raise ValueError(
                "selectivity window exceeded the bounded read size; the decision "
                "engine refuses to run on truncated evidence"
            )
        selectivity = selectivity_page["items"]
        unresolved = sorted(
            s["id"] for s in selectivity if s["comparability_status"] != "Comparable"
        )
        comparisons = cell.comparisons(project, protein)["items"]
        gaps = cell.gaps(project, protein)["items"]
        by_endpoint: dict[str, list[dict[str, Any]]] = {}
        sources = {e["id"]: e["source_id"] for e in experiments}
        for r in readouts:
            if modality[r["experiment_id"]] in GENETIC and r["direction"] in (
                "increase",
                "decrease",
            ):
                by_endpoint.setdefault(r["endpoint"], []).append(r)
        disagreements = []
        for endpoint, items in sorted(by_endpoint.items()):
            if (
                len({sources[r["experiment_id"]] for r in items}) > 1
                and len({r["direction"] for r in items}) > 1
            ):
                disagreements.append(
                    {
                        "endpoint": endpoint,
                        "directions": sorted({r["direction"] for r in items}),
                        "readout_ids": sorted(r["id"] for r in items),
                    }
                )
        structure_ids = [
            row[0]
            for row in self.store._connection.execute(
                "SELECT structure_id FROM project_structures WHERE project_id=? "
                "ORDER BY structure_id",
                [project],
            ).fetchall()
        ]
        protein_record = self.store.targets.protein(protein)
        experiment_by_id = {e["id"]: e for e in experiments}
        biochemical_items = [
            m
            for e in chain["edges"]
            if e["edge"] == "biochemical"
            for m in e["measurements"]
        ]
        compounds = sorted(
            c["id"]
            for c in self.store.pharmacology.collection(
                project, protein, "compounds", 100, 0
            )["items"]
        )
        with_phenotype = {
            modality_compound
            for e in experiments
            for modality_compound in [e.get("compound_id")]
            if modality_compound
            and any(
                a["experiment_id"] == e["id"]
                and a["edge"] in ("hla", "immune")
                and a["state"] == "supported"
                for a in assessments
            )
        }
        with_biochemical = {m["compound_id"] for m in biochemical_items}
        unresolved_identity = sorted(
            {
                e.get("reported_perturbagen") or e["label"]
                for e in experiments
                if e["modality"] == "small_molecule"
                and not e.get("compound_id")
                and any(
                    a["experiment_id"] == e["id"]
                    and a["edge"] in ("hla", "immune")
                    and a["state"] == "supported"
                    for a in assessments
                )
            }
        )
        pending = pending_assessments
        by_experiment = {e["id"]: e for e in experiments}
        gap_scopes = {}
        for g in gaps:
            if g.get("compound_id"):
                gap_scopes[g["id"]] = f"compound:{g['compound_id']}"
            else:
                owner = by_experiment.get(g["id"].removesuffix(":gap"), {})
                label = owner.get("reported_perturbagen") or owner.get("label")
                if label:
                    gap_scopes[g["id"]] = f"perturbagen:{label}"
        coverage_rows = [
            {"scope_type": "compound", "scope_id": c} for c in sorted(with_phenotype)
        ] + [{"scope_type": "perturbagen", "scope_id": p} for p in unresolved_identity]
        entries = (
            ledger
            if ledger is not None
            else ResultsService(self.store).ledger(project, mode)
        )
        contributions = [
            {
                "id": x["interpretation_id"],
                "result_id": x["result_id"],
                "result_row": x["result_row"],
                "experiment_id": x["experiment_id"],
                "edge": x["edge"],
                "scope_type": x["scope_type"],
                "scope_id": x["scope_id"],
                "state": x["state"],
                "statement": x["statement"],
                "context": x["context"],
                "caveats": [
                    c
                    for c in x["eligibility"]["caveats"]
                    if c not in x["eligibility"].get("review_caveats", [])
                ],
                "review_caveats": x["eligibility"].get("review_caveats", []),
                "review_state": x["interpretation_review"],
                "eligibility_state": x["eligibility"]["state"],
                "independent_replicates": x["independent_replicates"],
                "synthetic": x["synthetic"],
            }
            for x in entries
            if x["eligibility"]["eligible"]
        ]
        unexpected = sorted(
            {
                x["result_id"]
                for x in entries
                if x["scenario_match"] == "outside_predefined_scenarios"
                and x["eligibility"]["state"]
                not in ("withdrawn", "superseded", "ineligible_qc_failure")
            }
        )
        return {
            "contributions": contributions,
            "required_scopes": coverage_rows,
            "gap_scopes": gap_scopes,
            "unexpected_results": [
                {"result_id": r, "relationship": "outside_predefined_scenarios"}
                for r in unexpected
            ],
            "context_of": {
                a["id"]: " / ".join(
                    part
                    for part in (
                        experiment_by_id[a["experiment_id"]]["context"]["cell_line"],
                        experiment_by_id[a["experiment_id"]]["context"]["hla_allele"]
                        or "no HLA allele reported",
                    )
                    if part
                )
                for a in phenotype
            },
            "target_label": protein_record.gene_symbol
            or protein_record.recommended_name
            or protein_record.primary_accession,
            "compound_coverage": {
                "compounds": [
                    {
                        "compound_id": c,
                        "biochemical": c in with_biochemical,
                        "cellular_phenotype": c in with_phenotype,
                    }
                    for c in compounds
                ],
                "unresolved_identity_perturbagens": unresolved_identity,
            },
            "review": {
                "pending_expert_review": pending,
                "accepted": len(assessments) - pending,
            },
            "review_mode": mode,
            "edges": edges,
            "biochemical_ids": [
                i for i in edges["biochemical"]["ids"] if i.startswith("measurement")
            ],
            "compound_phenotype_ids": pick(True, state="supported"),
            "genetic_phenotype_ids": pick(False, state="supported"),
            "genetic_dependency_ids": genetic,
            "compound_dependency_uncertain_ids": sorted(
                a["id"]
                for a in phenotype
                if modality[a["experiment_id"]] == "small_molecule"
                and a["dependency"] in ("uncertain", "not_assessed")
            ),
            "compound_dependency_supported_ids": pick(True, dependency="supported"),
            "functional_insufficient_ids": sorted(
                a["id"]
                for a in assessments
                if a["edge"] == "functional" and a["state"] == "insufficient"
            ),
            "gap_ids": sorted(g["id"] for g in gaps)
            if edges["engagement"]["state"] != "supported"
            else [],
            "selectivity": {
                "by_status": {
                    status: sum(
                        s["comparability_status"] == status for s in selectivity
                    )
                    for status in sorted(
                        {s["comparability_status"] for s in selectivity}
                    )
                },
                "total": len(selectivity),
                "comparable": len(selectivity) - len(unresolved),
                "unresolved_ids": unresolved,
                "comparable_ids": sorted(
                    s["id"]
                    for s in selectivity
                    if s["comparability_status"] == "Comparable"
                ),
            },
            "concordance": {
                "concordant": sum(c["state"] == "concordant" for c in comparisons),
                "discordant": sum(c["state"] == "discordant" for c in comparisons),
                "not_comparable": sum(
                    c["state"] == "not_comparable" for c in comparisons
                ),
                "discordant_ids": sorted(
                    ":".join(c["experiment_ids"])
                    for c in comparisons
                    if c["state"] == "discordant"
                ),
            },
            "source_disagreements": disagreements,
            "contexts": {
                "allotype_reported": any(
                    e["context"]["erap1_allotype"] for e in experiments
                ),
                "unmatched_context_experiments": sum(
                    not e["context"]["hla_allele"] for e in experiments
                ),
                "hla_alleles": sorted(
                    {
                        e["context"]["hla_allele"]
                        for e in experiments
                        if e["context"]["hla_allele"]
                    }
                ),
            },
            "structure_ids": structure_ids,
            "strategy_ids": sorted(
                row[0]
                for row in self.store._connection.execute(
                    "SELECT strategy_id FROM intervention_strategies "
                    "WHERE project_id=?",
                    [project],
                ).fetchall()
            ),
        }

    # -- build -------------------------------------------------------------

    def _statuses(self, project: str) -> dict[str, str]:
        status: dict[str, str] = {}
        for event in self.store.decisions.events(project):
            if event["event_type"] == "status":
                status[event["subject_id"]] = event["to_value"]
        return status

    def _results(self, project: str) -> dict[str, str]:
        return {
            e["subject_id"]: e["result_claim_id"]
            for e in self.store.decisions.events(project)
            if e["event_type"] == "status" and e["result_claim_id"]
        }

    def _promoted(self, project: str) -> list[str]:
        return sorted(
            {
                e["subject_id"]
                for e in self.store.decisions.events(project)
                if e["event_type"] == "promotion"
            }
        )

    def inputs(
        self,
        project: str,
        protein: str,
        mode: str = "exploratory",
        overrides: dict[str, str] | None = None,
    ) -> engine.Inputs:
        """Load every decision input from the store; the engine reads nothing else.

        ``overrides`` (interpretation id -> hypothetical review state) exists only for
        the decision-impact preview and is never persisted.
        """
        if mode not in policy.MODES:
            raise ValueError(f"unknown review mode {mode!r}")
        defs = self.store.decisions.explanations(project, protein)
        profiles = self.store.decisions.profiles(project, protein)
        if not defs or not profiles:
            raise ValueError("decision package not imported for this project")
        hyp = self.store.hypotheses.get(defs[0]["hypothesis_id"])
        statuses = self._statuses(project)
        results = self._results(project)
        candidates: list[dict[str, Any]] = []
        for profile in profiles:
            experiment = self.store.proposed_experiments.get(profile["experiment_id"])
            consequences = {
                c["scenario_id"]: c
                for c in self.store.decisions.consequences(profile["experiment_id"])
            }
            effects: dict[str, dict[str, dict[str, str]]] = {}
            for row in self.store.decisions.interpretations(profile["experiment_id"]):
                effects.setdefault(row["scenario_id"], {})[row["explanation_id"]] = {
                    "effect": row["effect"],
                    "rationale": row["rationale"],
                }
            scenarios = []
            for scenario in self.store.outcome_scenarios.list_for_experiment(
                experiment.experiment_id
            ):
                cons = consequences.get(scenario.scenario_id)
                if cons is None:
                    raise ValueError(
                        f"outcome scenario {scenario.scenario_id!r} of "
                        f"{experiment.experiment_id!r} has no stored "
                        "DecisionConsequence; an incomplete scenario cannot be "
                        "interpreted"
                    )
                scenarios.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "kind": cons["scenario_kind"],
                        "outcome": scenario.possible_outcome,
                        "interpretation": scenario.interpretation,
                        "effects": effects.get(scenario.scenario_id, {}),
                        "consequence": {
                            "category": cons["category"],
                            "statement": cons["conditional_statement"],
                            "new_uncertainty": cons["new_uncertainty"],
                        },
                    }
                )
            candidates.append(
                {
                    "experiment_id": experiment.experiment_id,
                    "title": experiment.title,
                    "rationale": experiment.rationale,
                    "experimental_system": experiment.experimental_system,
                    "intervention_description": experiment.intervention_description,
                    "endpoint_description": experiment.endpoint_description,
                    "knowledge_kind": experiment.knowledge_kind.value,
                    "profile": profile,
                    "status": statuses.get(profile["experiment_id"], "proposed"),
                    "result_claim_id": results.get(profile["experiment_id"]),
                    "scenarios": scenarios,
                }
            )
        ledger = ResultsService(self.store).ledger(project, mode, overrides)
        mapping_rows = self.store._connection.execute(
            "SELECT scenario_id, explanation_id FROM outcome_interpretations"
        ).fetchall()
        mapping_reviews = self._review_states(project, "scenario_mapping")
        design_reviews = self._review_states(project, "candidate_design")
        return {
            "evidence": self.evidence(project, protein, mode, ledger),
            "review": {
                "mode": mode,
                "policy_id": policy.POLICY_ID,
                "mappings": {
                    f"{s}|{e}": mapping_reviews.get(f"{s}|{e}", "pending")
                    for s, e in mapping_rows
                },
                "designs": {
                    c["experiment_id"]: design_reviews.get(
                        c["experiment_id"], "pending"
                    )
                    for c in candidates
                },
            },
            "results_ledger": [
                {
                    k: x[k]
                    for k in (
                        "result_row",
                        "result_id",
                        "version",
                        "interpretation_id",
                        "experiment_id",
                        "edge",
                        "scope_type",
                        "scope_id",
                        "state",
                        "scenario_match",
                        "result_review",
                        "interpretation_review",
                        "synthetic",
                        "statement",
                    )
                }
                | {
                    "eligibility": x["eligibility"]["state"],
                    "eligible": x["eligibility"]["eligible"],
                    "reasons": x["eligibility"]["reasons"],
                    "rule": x["eligibility"]["rule"],
                }
                for x in ledger
            ],
            "explanations": defs,
            "hypothesis": {
                "id": hyp.identifier,
                "title": hyp.title,
                "description": hyp.current.description,
                "state": hyp.current.state.value,
                "revision": hyp.current.revision,
            },
            "candidates": candidates,
            "constraints": self.store.decisions.latest_constraints(project),
            "promoted": self._promoted(project),
            "statuses": statuses,
        }

    @staticmethod
    def digests(project: str, protein: str, inputs: engine.Inputs) -> dict[str, str]:
        """Separate what changed: evidence, review, investigator input or methodology."""
        constraints = inputs["constraints"]
        raw = json.loads(canonical(inputs["evidence"]))
        contributions = raw.get("contributions", [])
        review_part = {
            "contributions": sorted(
                (
                    c["id"],
                    c.pop("review_state"),
                    c.pop("eligibility_state"),
                    tuple(c.pop("review_caveats")),
                )
                for c in contributions
            ),
            "mappings": inputs["review"]["mappings"],
            "designs": inputs["review"]["designs"],
            "assessments": raw.get("review", {}),
        }
        raw.pop("review", None)
        evidence = digest_of(raw)
        review = digest_of(review_part)
        review_inputs = digest_of(
            {k: review_part[k] for k in ("mappings", "designs", "assessments")}
        )
        investigator = digest_of(
            {
                "constraints": constraints and constraints["id"],
                "statuses": inputs["statuses"],
                "promoted": inputs["promoted"],
                "mode": inputs["review"]["mode"],
                "results": {
                    c["experiment_id"]: c["result_claim_id"]
                    for c in inputs["candidates"]
                },
            }
        )
        methodology = digest_of(
            {
                "rules": rules.fingerprint(),
                "review_policy": policy.policy_fingerprint(),
                "candidates": sorted(c["experiment_id"] for c in inputs["candidates"]),
                "explanations": sorted(e["id"] for e in inputs["explanations"]),
                "hypothesis": [
                    inputs["hypothesis"]["id"],
                    inputs["hypothesis"]["revision"],
                ],
            }
        )
        return {
            "evidence": evidence,
            "review": review,
            "review_inputs": review_inputs,
            "investigator_input": investigator,
            "methodology": methodology,
            "combined": digest_of(
                [project, protein, evidence, review, investigator, methodology]
            ),
        }

    def build(
        self,
        project: str,
        protein: str,
        *,
        created_at: datetime | None = None,
        created_by: str = ENGINE,
        mode: str = "exploratory",
        trigger: str = "explicit build",
    ) -> dict[str, Any]:
        inputs = self.inputs(project, protein, mode)
        parts = self.digests(project, protein, inputs)
        latest = self.store.decisions.latest_state(project, protein)
        if latest and latest["evidence_digest"] == parts["combined"]:
            return latest
        analysis = engine.analyze(inputs)
        version = 1 if latest is None else latest["version"] + 1
        now = created_at or datetime.now(UTC)
        state_id = f"decision-state:{version}:{parts['combined'][:16]}"
        hyp = inputs["hypothesis"]
        payload: dict[str, Any] = {
            "id": state_id,
            "project_id": project,
            "protein_id": protein,
            "version": version,
            "supersedes_id": latest["id"] if latest else None,
            "status": "recorded",
            "hypothesis_id": hyp["id"],
            "hypothesis_revision": hyp["revision"],
            "hypothesis": {
                "title": hyp["title"],
                "description": hyp["description"],
                "state": hyp["state"],
                "knowledge_kind": "researcher_hypothesis"
                if hyp["id"] in inputs["promoted"]
                else "ai_suggestion",
            },
            "rules_version": rules.RULES_VERSION,
            "methodology": {
                "rules_version": rules.RULES_VERSION,
                "rules_fingerprint": rules.fingerprint(),
                "review_policy": policy.POLICY_ID,
                "review_policy_fingerprint": policy.policy_fingerprint(),
                "digest": parts["methodology"],
            },
            "trigger": trigger,
            "synthetic": analysis["results"]["synthetic"],
            "digests": parts,
            "evidence_digest": parts["combined"],
            "evidence": inputs["evidence"],
            "created_at": now.isoformat(),
            "created_by": created_by,
            **analysis,
            "disclaimer": "Decision framing given the evidence currently represented "
            "in AXIS; not scientific truth. All wording is an AI suggestion pending "
            "researcher review. No experiment has been performed.",
        }
        payload["diff"] = self.diff(latest, payload) if latest else None
        state = DecisionState(
            state_id,
            project,
            protein,
            version,
            hyp["id"],
            hyp["revision"],
            now,
            created_by,
            parts["combined"],
            rules.RULES_VERSION,
            payload["rationale"],
            analysis["critical_uncertainty_id"],
            analysis["recommended_experiment_id"],
            latest["id"] if latest else None,
        )
        payload = json.loads(canonical(payload))
        with self.store._transaction():
            self.store.decisions.add_state(state, payload)
            for c in payload["results"]["contributions"]:
                self.store.results.link_state(
                    state_id,
                    c["result_row"],
                    c["id"],
                    c["eligibility_state"],
                    c["review_state"],
                )
        return payload

    # -- diff --------------------------------------------------------------

    @staticmethod
    def diff(
        previous: dict[str, Any] | None, current: dict[str, Any]
    ) -> dict[str, Any]:
        if previous is None:
            return {
                "from": None,
                "to": current["id"],
                "changes": [],
                "new_evidence": [],
            }
        changes: list[str] = []
        new_evidence: list[str] = []
        before, after = previous.get("digests", {}), current.get("digests", {})
        prev_states = {
            c["id"]: c["review_state"]
            for c in previous.get("results", {}).get("contributions", [])
        }
        review_changed = before.get("review_inputs") != after.get(
            "review_inputs"
        ) or any(
            c["id"] in prev_states and prev_states[c["id"]] != c["review_state"]
            for c in current.get("results", {}).get("contributions", [])
        )
        changed = {
            "evidence": before.get("evidence") != after.get("evidence"),
            "review": review_changed,
            "investigator_input": before.get("investigator_input")
            != after.get("investigator_input"),
            "methodology": before.get("methodology") != after.get("methodology"),
        }
        cause = [name for name, flag in changed.items() if flag]
        wording = {
            "evidence": "the stored evidence changed",
            "review": "scientific review states changed",
            "investigator_input": "investigator input (constraints, status or "
            "promotion) changed",
            "methodology": "the AXIS decision methodology (rules, candidate set or "
            "hypothesis revision) changed",
        }
        summary = (
            "This decision differs because "
            + "; and ".join(wording[c] for c in cause)
            + "."
            if cause
            else "No input digest changed."
        )
        for key, value in current["evidence"].items():
            old = previous["evidence"].get(key)
            if isinstance(value, list) and isinstance(old, list):
                new_evidence += [
                    f"{key}: {i}" for i in value if isinstance(i, str) and i not in old
                ]
        for edge, value in current["evidence"]["edges"].items():
            old = previous["evidence"]["edges"].get(edge, {}).get("state")
            if old != value["state"]:
                changes.append(
                    f"{_label(edge).capitalize()}: {_label(str(old))} → "
                    f"{_label(value['state'])}"
                )
        old_u = {u["id"]: u for u in previous["uncertainties"]}
        for u in current["uncertainties"]:
            before = old_u.get(u["id"])
            if before is None:
                changes.append(f"New uncertainty: {_label(u['category'])}")
            elif (before["status"], before["decision_relevance"]) != (
                u["status"],
                u["decision_relevance"],
            ):
                changes.append(
                    f"Uncertainty {_label(u['category'])}: {_label(before['status'])}/"
                    f"{_label(before['decision_relevance'])}"
                    f" → {_label(u['status'])}/{_label(u['decision_relevance'])}"
                )
        old_e = {e["id"]: e["status"] for e in previous["explanations"]}
        for e in current["explanations"]:
            if e["id"] in old_e and old_e[e["id"]] != e["status"]:
                changes.append(
                    f"Explanation {e['label']}: {_label(old_e[e['id']])} → "
                    f"{_label(e['status'])}"
                )
            elif e["id"] not in old_e:
                changes.append(
                    f"Explanation {e['label']} now admitted ({_label(e['status'])})"
                )
        if previous["critical_uncertainty_id"] != current["critical_uncertainty_id"]:
            changes.append(
                f"Critical uncertainty: {previous['critical_uncertainty_id']} → "
                f"{current['critical_uncertainty_id']}"
            )
        if (
            previous["recommended_experiment_id"]
            != current["recommended_experiment_id"]
        ):
            changes.append(
                f"Recommended experiment: {previous['recommended_experiment_id']} → "
                f"{current['recommended_experiment_id']}"
            )
        if previous["constraints"]["id"] != current["constraints"]["id"]:
            changes.append("Investigator constraints changed")
        if (
            previous["provenance"]["investigator_approved"]
            != current["provenance"]["investigator_approved"]
        ):
            changes.append("Investigator-approved components changed")
        scientific = DecisionService.scientific_diff(previous, current)
        return {
            "from": previous["id"],
            "to": current["id"],
            "changes": changes + scientific["lines"],
            "new_evidence": new_evidence,
            "cause": cause,
            "cause_summary": summary,
            "causes": scientific["causes"],
            "scientific_diff": scientific["diff"],
            "triggering_results": scientific["triggering_results"],
            "decision_changed": scientific["decision_changed"],
        }

    @staticmethod
    def scientific_diff(
        previous: dict[str, Any], current: dict[str, Any]
    ) -> dict[str, Any]:
        """Cause-attributed scientific diff (not a JSON diff).

        Every change lists what caused it: result, interpretation, review state
        and rule. Evidence change, review change and rule change stay separate.
        """
        prev_c = {
            c["id"]: c for c in previous.get("results", {}).get("contributions", [])
        }
        cur_c = {
            c["id"]: c for c in current.get("results", {}).get("contributions", [])
        }
        ledger = {
            x["interpretation_id"]: x
            for x in current.get("results", {}).get("ledger", [])
        }
        new = [cur_c[i] for i in sorted(cur_c.keys() - prev_c.keys())]
        removed = [prev_c[i] for i in sorted(prev_c.keys() - cur_c.keys())]
        reviewed = [
            {
                "interpretation_id": i,
                "result_id": cur_c[i]["result_id"],
                "before": prev_c[i]["review_state"],
                "after": cur_c[i]["review_state"],
            }
            for i in sorted(prev_c.keys() & cur_c.keys())
            if prev_c[i]["review_state"] != cur_c[i]["review_state"]
        ]
        causes: list[dict[str, Any]] = []
        if new:
            causes.append(
                {
                    "category": "new_experimental_evidence",
                    "items": [
                        {
                            "result_id": c["result_id"],
                            "interpretation_id": c["id"],
                            "scope": f"{c['scope_type']}:{c['scope_id']}",
                            "edge": c["edge"],
                            "state": c["state"],
                            "review_state": c["review_state"],
                        }
                        for c in new
                    ],
                }
            )
        if reviewed:
            causes.append({"category": "review_status_change", "items": reviewed})
        if removed:
            causes.append(
                {
                    "category": "evidence_removed",
                    "items": [
                        {
                            "result_id": c["result_id"],
                            "interpretation_id": c["id"],
                            "reason": (
                                ledger.get(c["id"], {}).get("eligibility")
                                or "no longer eligible"
                            ),
                            "rule": ledger.get(c["id"], {}).get("rule"),
                        }
                        for c in removed
                    ],
                }
            )
        before, after = previous.get("digests", {}), current.get("digests", {})
        if before.get("methodology") != after.get("methodology"):
            causes.append(
                {
                    "category": "methodology_change",
                    "items": [
                        {
                            "before": previous.get("methodology", {}).get(
                                "rules_version"
                            ),
                            "after": current.get("methodology", {}).get(
                                "rules_version"
                            ),
                        }
                    ],
                }
            )
        if before.get("investigator_input") != after.get("investigator_input"):
            causes.append({"category": "investigator_input_change", "items": []})
        if before.get("review_inputs") != after.get("review_inputs"):
            causes.append(
                {
                    "category": "review_status_change",
                    "items": [{"object": "scenario mappings, designs or assessments"}],
                }
            )
        if (before.get("evidence") != after.get("evidence")) and not (new or removed):
            causes.append({"category": "evidence_changed", "items": []})
        triggers = sorted(
            {c["result_id"] for c in new}
            | {r["result_id"] for r in reviewed}
            | {c["result_id"] for c in removed}
        )
        diff: dict[str, Any] = {
            "new_experimental_evidence": [
                c for c in causes if c["category"] == "new_experimental_evidence"
            ],
            "review_changes": reviewed,
            "removed_evidence": [
                c for c in causes if c["category"] == "evidence_removed"
            ],
            "evidence_status_changes": [],
            "explanation_changes": [],
            "uncertainty_changes": [],
            "critical": None,
            "recommendation": None,
        }
        lines: list[str] = []
        because_all = [
            {
                "result_id": c["result_id"],
                "interpretation_id": c["id"],
                "review_state": c["review_state"],
            }
            for c in (*new, *[cur_c[r["interpretation_id"]] for r in reviewed])
        ]
        old_eff = previous.get("effective_evidence") or {
            "edges": {k: v["state"] for k, v in previous["evidence"]["edges"].items()},
            "scoped_edges": {},
        }
        new_eff = current.get("effective_evidence", {"edges": {}, "scoped_edges": {}})
        for edge, state in sorted(new_eff["edges"].items()):
            if old_eff["edges"].get(edge) != state:
                diff["evidence_status_changes"].append(
                    {
                        "kind": "edge",
                        "name": edge,
                        "before": old_eff["edges"].get(edge),
                        "after": state,
                        "because": because_all,
                        "rule": "DECISION-RESULT-001",
                    }
                )
                lines.append(
                    f"Edge {_label(edge)}: {_label(str(old_eff['edges'].get(edge)))} → {_label(state)}"
                )
        for edge, scopes in sorted(new_eff.get("scoped_edges", {}).items()):
            for scope, entry in sorted(scopes.items()):
                old_state = (
                    old_eff.get("scoped_edges", {})
                    .get(edge, {})
                    .get(scope, {})
                    .get("state", "not_assessed")
                )
                if old_state != entry["state"]:
                    diff["evidence_status_changes"].append(
                        {
                            "kind": "scope",
                            "name": f"{edge} / {scope}",
                            "before": old_state,
                            "after": entry["state"],
                            "caveats": entry["caveats"],
                            "because": [
                                {"interpretation_id": i}
                                for i in entry["contribution_ids"]
                            ],
                            "rule": "DECISION-RESULT-001",
                        }
                    )
                    lines.append(
                        f"{_label(edge).capitalize()} for {scope}: {_label(old_state)} → {_label(entry['state'])}"
                    )
        old_roll = (old_eff.get("engagement_rollup") or {}).get("status")
        new_roll = (new_eff.get("engagement_rollup") or {}).get("status")
        if old_roll != new_roll and new_roll:
            diff["evidence_status_changes"].append(
                {
                    "kind": "rollup",
                    "name": "engagement across chemical matter",
                    "before": old_roll or "open",
                    "after": new_roll,
                    "because": because_all,
                    "rule": "DECISION-RESULT-002",
                }
            )
            lines.append(f"Engagement across scopes: {old_roll or 'open'} → {new_roll}")
        old_x = {e["id"]: e for e in previous["explanations"]}
        for e in current["explanations"]:
            was = old_x.get(e["id"])
            if was is not None and was["status"] != e["status"]:
                old_links = {
                    (link["evidence_type"], link["evidence_id"], link["relationship"])
                    for link in was["links"]
                }
                added = [
                    link
                    for link in e["links"]
                    if (
                        link["evidence_type"],
                        link["evidence_id"],
                        link["relationship"],
                    )
                    not in old_links
                ]
                diff["explanation_changes"].append(
                    {
                        "id": e["id"],
                        "label": e["label"],
                        "before": was["status"],
                        "after": e["status"],
                        "because": [
                            {
                                "link": link["evidence_id"],
                                "relationship": link["relationship"],
                                "rule": link["rule_id"],
                            }
                            for link in added
                        ][:12],
                        "rules": e["rule_ids"],
                    }
                )
        old_u = {u["id"]: u for u in previous["uncertainties"]}
        for u in current["uncertainties"]:
            was_u = old_u.get(u["id"])
            if was_u is not None and (was_u["status"], was_u["decision_relevance"]) != (
                u["status"],
                u["decision_relevance"],
            ):
                diff["uncertainty_changes"].append(
                    {
                        "id": u["id"],
                        "before": [was_u["status"], was_u["decision_relevance"]],
                        "after": [u["status"], u["decision_relevance"]],
                        "rules": u["fired_rules"],
                        "scope_breakdown": u.get("scope_breakdown", []),
                    }
                )
            elif was_u is None:
                diff["uncertainty_changes"].append(
                    {
                        "id": u["id"],
                        "before": None,
                        "after": [u["status"], u["decision_relevance"]],
                        "rules": u["fired_rules"],
                        "scope_breakdown": u.get("scope_breakdown", []),
                    }
                )
        winner = next(
            (
                u
                for u in current["uncertainties"]
                if u["id"] == current["critical_uncertainty_id"]
            ),
            None,
        )
        if previous["critical_uncertainty_id"] != current["critical_uncertainty_id"]:
            diff["critical"] = {
                "before": previous["critical_uncertainty_id"],
                "after": current["critical_uncertainty_id"],
                "because": {
                    "rules": winner["fired_rules"] if winner else [],
                    "triggering_results": triggers,
                },
            }
        if (
            previous["recommended_experiment_id"]
            != current["recommended_experiment_id"]
        ):
            diff["recommendation"] = {
                "before": previous["recommended_experiment_id"],
                "after": current["recommended_experiment_id"],
                "because": {
                    "critical_uncertainty": current["critical_uncertainty_id"],
                    "triggering_results": triggers,
                    "rule": "DECISION-EXP-003",
                },
            }
        core = diff["critical"] is not None or diff["recommendation"] is not None
        partial = bool(
            diff["evidence_status_changes"]
            or diff["explanation_changes"]
            or diff["uncertainty_changes"]
        )
        pending = any(c["review_state"] == "pending" for c in because_all)
        if (core or partial) and pending:
            answer, why = (
                "pending_review",
                (
                    "The decision changed only on interpretations that are still pending review "
                    "(exploratory)."
                ),
            )
        elif core:
            answer, why = (
                "yes",
                "The critical uncertainty or the recommended experiment changed.",
            )
        elif partial:
            answer, why = (
                "partially",
                (
                    "Evidence, explanation or uncertainty states changed, but the critical "
                    "uncertainty and the recommendation did not."
                ),
            )
        else:
            answer, why = (
                "no",
                "No evidence, explanation, uncertainty, critical uncertainty or recommendation changed.",
            )
        return {
            "causes": causes,
            "diff": diff,
            "lines": lines,
            "triggering_results": triggers,
            "decision_changed": {"answer": answer, "why": why},
        }

    # -- reads (never build, never network) --------------------------------

    def current(self, project: str, protein: str) -> dict[str, Any]:
        self.store.targets.require_member(project, protein)
        state = self.store.decisions.latest_state(project, protein)
        if state is None:
            raise RecordNotFoundError(
                "no DecisionState built; run `axis decision build`"
            )
        return state

    def candidate(
        self, project: str, protein: str, experiment_id: str
    ) -> dict[str, Any]:
        state = self.current(project, protein)
        analysis = next(
            (c for c in state["candidates"] if c["experiment_id"] == experiment_id),
            None,
        )
        if analysis is None:
            raise RecordNotFoundError("candidate experiment outside scope or not found")
        experiment = self.store.proposed_experiments.get(experiment_id)
        consequences = {
            c["scenario_id"]: c
            for c in self.store.decisions.consequences(experiment_id)
        }
        interpretations = self.store.decisions.interpretations(experiment_id)
        scenarios = [
            {
                "scenario_id": s.scenario_id,
                "outcome": s.possible_outcome,
                "interpretation": s.interpretation,
                "kind": consequences[s.scenario_id]["scenario_kind"],
                "consequence": {
                    "category": consequences[s.scenario_id]["category"],
                    "statement": consequences[s.scenario_id]["conditional_statement"],
                    "new_uncertainty": consequences[s.scenario_id]["new_uncertainty"],
                },
                "explanation_effects": [
                    i for i in interpretations if i["scenario_id"] == s.scenario_id
                ],
                "prospective": True,
            }
            for s in self.store.outcome_scenarios.list_for_experiment(experiment_id)
        ]
        return {
            "experiment": {
                "experiment_id": experiment.experiment_id,
                "title": experiment.title,
                "rationale": experiment.rationale,
                "experimental_system": experiment.experimental_system,
                "intervention_description": experiment.intervention_description,
                "endpoint_description": experiment.endpoint_description,
                "knowledge_kind": experiment.knowledge_kind.value,
            },
            "analysis": analysis,
            "scenarios": scenarios,
            "addressed_gap_ids": self.store.decisions.gap_links(experiment_id),
            "discriminates": self.store.decisions.discriminates(experiment_id),
            "events": self.store.decisions.events(project, experiment_id),
            "state_id": state["id"],
        }

    def answer(
        self,
        project: str,
        protein: str,
        question: str,
        experiment_id: str | None = None,
    ) -> dict[str, Any]:
        """Grounded answers read from the stored DecisionState only."""
        state = self.current(project, protein)
        if question == "why_critical":
            return {
                "question": question,
                "answer": state["critical"]["reasons"],
                "alternatives": state["critical"]["alternatives"],
            }
        if question == "evidence_against":
            return {
                "question": question,
                "answer": state["position"]["contradicted"]
                + [
                    {
                        "statement": link["rationale"],
                        "refs": [[link["evidence_type"], link["evidence_id"]]],
                    }
                    for e in state["explanations"]
                    if e["ground"] == "on_target"
                    for link in e["links"]
                    if link["relationship"] in ("contradicts", "context_limits")
                ],
            }
        if question == "why_not":
            if not experiment_id:
                raise ValueError("why_not requires an experiment id")
            item = next(
                (c for c in state["candidates"] if c["experiment_id"] == experiment_id),
                None,
            )
            if item is None:
                raise RecordNotFoundError("candidate experiment not found")
            return {
                "question": question,
                "answer": [item["reason"]],
                "experiment_id": experiment_id,
            }
        if question == "what_would_change_our_mind":
            return {"question": question, "answer": state["what_would_change_our_mind"]}
        if question in (
            "what_did_experiment_teach",
            "was_result_predicted",
            "resolution_scope",
            "what_if_not_trusted",
        ):
            return self._results_answer(
                project, protein, state, question, experiment_id
            )
        raise ValueError("unsupported question")

    # -- experimental results loop ---------------------------------------------

    def rebuild(
        self,
        project: str,
        protein: str,
        *,
        mode: str = "exploratory",
        trigger: str = "explicit rebuild",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Explicit rebuild after results or reviews changed. Never automatic."""
        return self.build(project, protein, mode=mode, trigger=trigger, **kwargs)

    def impact_preview(
        self,
        project: str,
        protein: str,
        interpretation_id: str,
        *,
        mode: str = "exploratory",
        assume: str = "accepted",
    ) -> dict[str, Any]:
        """If this interpretation were accepted, how would the decision change?

        Derived from the real rules; never stored, never the current decision.
        """
        if assume not in ("accepted", "accepted_with_caveat"):
            raise ValueError("a preview assumes acceptance")
        self.store.results.interpretation(interpretation_id)
        current = self.current(project, protein)
        inputs = self.inputs(project, protein, mode, {interpretation_id: assume})
        analysis = engine.analyze(inputs, with_sensitivity=False)
        parts = self.digests(project, protein, inputs)
        preview = {
            "id": "preview",
            "evidence": inputs["evidence"],
            "digests": parts,
            "methodology": current.get("methodology", {}),
            **analysis,
        }
        diff = self.diff(current, preview)
        return {
            "label": "Preview — not current decision",
            "applied": False,
            "assumes": f"interpretation {interpretation_id} {assume.replace('_', ' ')}",
            "against_state": current["id"],
            "diff": diff,
            "critical_after": analysis["critical_uncertainty_id"],
            "recommended_after": analysis["recommended_experiment_id"],
            "still_unresolved": [
                u["id"]
                for u in analysis["uncertainties"]
                if u["status"] in ("open", "partially_resolved")
            ],
        }

    def timeline(self, project: str) -> list[dict[str, Any]]:
        """Chronology of states, experiments, results, reviews and events."""
        items: list[dict[str, Any]] = []
        for p in self.store.targets.project_ids(project):
            for state in self.store.decisions.history(project, p, 100)["items"]:
                items.append(
                    {
                        "at": state["created_at"],
                        "kind": "decision_state",
                        "id": state["id"],
                        "label": f"DecisionState v{state['version']}",
                        "detail": state.get("trigger", ""),
                    }
                )
        for e in self.store.decisions.events(project):
            items.append(
                {
                    "at": e["created_at"],
                    "kind": "experiment_event",
                    "id": e["subject_id"],
                    "label": f"{e['subject_id']}: {e['from_value']} → {e['to_value']}",
                    "detail": e["actor"],
                }
            )
        for exp in self.store.results.experiments(project):
            if exp.get("executed_at"):
                items.append(
                    {
                        "at": str(exp["executed_at"]),
                        "kind": "experiment_performed",
                        "id": exp["id"],
                        "label": f"Experiment performed: {exp['id']}",
                        "detail": exp["scientific_status"],
                    }
                )
        for r in self.store.results.results(project):
            items.append(
                {
                    "at": str(r["recorded_at"]),
                    "kind": "result_imported",
                    "id": r["row_id"],
                    "label": f"Result imported: {r['row_id']}",
                    "detail": r["endpoint"],
                }
            )
        for rev in self.store.results.reviews(project):
            items.append(
                {
                    "at": rev["reviewed_at"],
                    "kind": "review",
                    "id": rev["id"],
                    "label": f"{rev['reviewer']}: {rev['decision'].replace('_', ' ')} "
                    f"{rev['object_type'].replace('_', ' ')} {rev['object_id']}",
                    "detail": rev["rationale"],
                }
            )
        for ev_ in self.store.results.events(project):
            items.append(
                {
                    "at": ev_["created_at"],
                    "kind": "result_event",
                    "id": ev_["result_id"],
                    "label": f"Result {ev_['event_type']}: {ev_['result_id']}",
                    "detail": ev_["actor"],
                }
            )
        return sorted(items, key=lambda x: (x["at"], x["kind"], x["id"]))

    def _first_state_with(
        self, project: str, protein: str, predicate: Any
    ) -> dict[str, Any] | None:
        for state in reversed(
            self.store.decisions.history(project, protein, 100)["items"]
        ):
            if predicate(state):
                return dict(state)
        return None

    def _results_answer(
        self,
        project: str,
        protein: str,
        state: dict[str, Any],
        question: str,
        ref: str | None,
    ) -> dict[str, Any]:
        if question == "resolution_scope":
            rows = []
            for u in state["uncertainties"]:
                if u.get("scope_breakdown"):
                    decided = [
                        b for b in u["scope_breakdown"] if b[2] != "not_assessed"
                    ]
                    rows.append(
                        {
                            "uncertainty": u["id"],
                            "status": u["status"],
                            "level": "target-level"
                            if u["status"] == "resolved_for_current_decision"
                            else "compound/scope-specific"
                            if decided
                            else "unresolved",
                            "scopes": [
                                {"scope": f"{t}:{i}", "state": s}
                                for t, i, s in u["scope_breakdown"]
                            ],
                        }
                    )
            return {
                "question": question,
                "answer": rows,
                "note": "A result resolves only its own scope; target-level resolution needs every required scope.",
            }
        if not ref:
            raise ValueError(f"{question} requires a result or experiment id")
        service = ResultsService(self.store)
        entries = [
            x
            for x in service.ledger(project, state.get("review_mode", "exploratory"))
            if ref in (x["experiment_id"], x["result_row"], x["result_id"])
        ]
        if not entries:
            raise RecordNotFoundError("no result for that experiment or result id")
        if question == "was_result_predicted":
            out = []
            for x in entries:
                matches = self.store.results.matches(x["result_row"])
                out.append(
                    {
                        "result": x["result_row"],
                        "overall": x["scenario_match"],
                        "scenarios": [
                            {
                                "scenario": m["outcome_scenario_id"],
                                "relationship": m["relationship"],
                                "rationale": m["rationale"],
                            }
                            for m in matches
                            if m["outcome_scenario_id"]
                        ],
                    }
                )
            return {
                "question": question,
                "answer": out,
                "note": "Not a yes/no question: matches, partial matches, contradiction, "
                "outside predefined scenarios or non-interpretable.",
            }
        ids = {x["interpretation_id"] for x in entries}
        if question == "what_if_not_trusted":
            earlier = self._first_state_with(
                project,
                protein,
                lambda s: not ids
                & {c["id"] for c in s.get("results", {}).get("contributions", [])},
            )
            sens = next(
                (
                    r
                    for k in (
                        "decision_sensitive",
                        "explanation_sensitive",
                        "non_decisive",
                    )
                    for r in state.get("sensitivity", {}).get(k, [])
                    if r["group"] == f"result:{entries[0]['result_id']}"
                ),
                None,
            )
            return {
                "question": question,
                "answer": {
                    "review_states": {
                        x["interpretation_id"]: x["interpretation_review"]
                        for x in entries
                    },
                    "removal_sensitivity": sens,
                    "decision_without_the_result": None
                    if earlier is None
                    else {
                        "state": earlier["id"],
                        "critical": earlier["critical_uncertainty_id"],
                        "recommended": earlier["recommended_experiment_id"],
                    },
                },
            }
        first = self._first_state_with(
            project,
            protein,
            lambda s: bool(
                ids & {c["id"] for c in s.get("results", {}).get("contributions", [])}
            ),
        )
        x = entries[0]
        sentences = [
            "The experiment observed: "
            + str(
                self.store.results.result(project, x["result_row"]).get(
                    "qualitative_result"
                )
                or x["result_row"]
            ).rstrip(".")
            + ".",
            f"Eligibility under the review policy: {x['eligibility']['state'].replace('_', ' ')} "
            f"({'; '.join(x['eligibility']['reasons'])}).",
            f"The interpretation maps this to the {x['edge']} edge for {x['scope_type']}:{x['scope_id']} "
            f"as {x['state']} (review: {x['interpretation_review']}).",
        ]
        if first is None:
            sentences.append(
                "It is not yet part of any DecisionState; run an explicit rebuild "
                "after review, or preview its impact."
            )
            return {
                "question": question,
                "answer": sentences,
                "decision_state": None,
                "eligibility": x["eligibility"],
            }
        diff = first.get("diff") or {}
        sd = diff.get("scientific_diff") or {}
        for ch in sd.get("evidence_status_changes", []):
            sentences.append(
                f"That changed {ch['name']} from {ch['before']} to {ch['after']} ({ch.get('rule')})."
            )
        for ch in sd.get("explanation_changes", []):
            sentences.append(
                f"Rules {', '.join(ch['rules'])} changed explanation {ch['label']}: {ch['before']} → {ch['after']}."
            )
        for ch in sd.get("uncertainty_changes", []):
            sentences.append(f"Uncertainty {ch['id']}: {ch['before']} → {ch['after']}.")
        if sd.get("critical"):
            sentences.append(
                f"The critical uncertainty changed from {sd['critical']['before']} to {sd['critical']['after']}."
            )
        if sd.get("recommendation"):
            sentences.append(
                f"The recommended next experiment changed from {sd['recommendation']['before']} to {sd['recommendation']['after']}."
            )
        sentences.append(
            "Did the decision change? "
            + (diff.get("decision_changed") or {}).get("answer", "n/a")
            + "."
        )
        sentences.append(
            "Still unresolved: "
            + ", ".join(
                u["id"]
                for u in first["uncertainties"]
                if u["status"] in ("open", "partially_resolved")
            )
            + "."
        )
        return {
            "question": question,
            "answer": sentences,
            "decision_state": first["id"],
            "diff": diff,
        }

    # -- investigator actions (service/CLI only; no mutation over HTTP) ----

    def set_constraints(
        self, project: str, created_by: str, **fields: Any
    ) -> dict[str, Any]:
        previous = self.store.decisions.latest_constraints(project)
        version = 1 if previous is None else previous["version"] + 1
        converted: dict[str, Any] = {
            k: (tuple(v) if isinstance(v, list) else v) for k, v in fields.items()
        }
        value = DecisionConstraints(
            f"decision-constraints:{project}:{version}",
            project,
            version,
            datetime.now(UTC),
            created_by,
            supersedes_id=previous["id"] if previous else None,
            **converted,
        )
        self.store.decisions.add_constraints(value)
        return {"id": value.id, "version": version}

    def set_experiment_status(
        self,
        project: str,
        experiment_id: str,
        to: str,
        actor: str,
        note: str = "",
        result_claim_id: str | None = None,
    ) -> dict[str, Any]:
        if self.store.proposed_experiments.get(experiment_id).project_id != project:
            raise RecordNotFoundError("experiment outside project")
        current = self._statuses(project).get(experiment_id, "proposed")
        if to not in TRANSITIONS.get(current, set()):
            raise ValueError(f"cannot move experiment from {current} to {to}")
        is_claim = True
        if to == "completed":
            if not result_claim_id:
                raise ValueError(
                    "an experiment is completed only with a recorded result claim"
                )
            stored = self.store._connection.execute(
                "SELECT 1 FROM experimental_results r JOIN performed_experiments e "
                "ON r.performed_experiment_id=e.id WHERE r.id=? AND e.proposal_id=?",
                [result_claim_id, experiment_id],
            ).fetchone()
            is_claim = stored is None
            if stored is None:
                claim = self.store.claims.get(result_claim_id)
                if claim.knowledge_kind != KnowledgeKind.EXPERIMENTAL_RESULT:
                    raise ValueError("completion requires an experimental_result claim")
        if to in ("completed_interpretable", "completed_non_interpretable"):
            performed = [
                e
                for e in self.store.results.experiments(project)
                if e.get("proposal_id") == experiment_id
            ]
            assessments = [
                (self.store.results.qc(e["id"]) or {}).get("assessment")
                for e in performed
            ]
            ok = (
                any(
                    a in ("interpretable", "interpretable_with_caveat")
                    for a in assessments
                )
                if to == "completed_interpretable"
                else "non_interpretable" in assessments
            )
            if not ok:
                raise ValueError(
                    f"{to.replace('_', ' ')} requires a matching quality assessment of a "
                    "performed experiment; completed is not the same as interpretable"
                )
        if not actor.strip():
            raise ValueError("an investigator is required")
        identifier = f"decision-event:{experiment_id}:{to}"
        self.store.decisions.add_event(
            identifier,
            project,
            "experiment",
            experiment_id,
            "status",
            current,
            to,
            actor,
            note if is_claim else f"result:{result_claim_id}; {note}".strip("; "),
            datetime.now(UTC),
            result_claim_id if is_claim else None,
        )
        return {"experiment_id": experiment_id, "from": current, "to": to}

    def promote_explanation(
        self, project: str, explanation_id: str, actor: str, note: str = ""
    ) -> dict[str, Any]:
        if not actor.strip():
            raise ValueError("an investigator is required")
        known = {
            e["id"]
            for p in self.store.targets.project_ids(project)
            for e in self.store.decisions.explanations(project, p)
        }
        if explanation_id not in known:
            raise RecordNotFoundError("explanation outside project")
        if any(
            e["subject_id"] == explanation_id
            for e in self.store.decisions.events(project, explanation_id)
        ):
            raise ValueError("explanation already promoted")
        self.store.decisions.add_event(
            f"decision-event:{explanation_id}:promotion",
            project,
            "explanation",
            explanation_id,
            "promotion",
            "ai_suggestion",
            "researcher_hypothesis",
            actor,
            note,
            datetime.now(UTC),
        )
        return {"explanation_id": explanation_id, "to": "researcher_hypothesis"}
