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
from axis.storage import EvidenceStore, RecordNotFoundError

VERSION = "axis-decision-1"
ENGINE = "AXIS deterministic decision engine"
GENETIC = {"knockdown", "knockout", "CRISPR", "variant_expression"}
TRANSITIONS = {
    "proposed": {"investigator_selected", "cancelled"},
    "investigator_selected": {"planned", "cancelled"},
    "planned": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
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

    def evidence(self, project: str, protein: str) -> rules.Evidence:
        self.store.targets.require_member(project, protein)
        cell = CellularPharmacologyService(self.store)
        chain = cell.chain(project, protein)
        edges = {
            e["edge"]: {
                "state": e["state"],
                "ids": sorted(
                    [a["id"] for a in e["assessments"]]
                    + [m["id"] for m in e["measurements"]]
                ),
            }
            for e in chain["edges"]
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
        assessments = windows["assessments"]["items"]
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
        pending = sum(
            a.get("review_status") == "pending_expert_review" for a in assessments
        )
        return {
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

    def inputs(self, project: str, protein: str) -> engine.Inputs:
        """Load every decision input from the store; the engine reads nothing else."""
        defs = self.store.decisions.explanations(project, protein)
        profiles = self.store.decisions.profiles(project, protein)
        if not defs or not profiles:
            raise ValueError("decision package not imported for this project")
        hyp = self.store.hypotheses.get(defs[0]["hypothesis_id"])
        statuses = self._statuses(project)
        results = self._results(project)
        candidates = []
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
        return {
            "evidence": self.evidence(project, protein),
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
        """Separate what changed: evidence, investigator input, or methodology."""
        constraints = inputs["constraints"]
        evidence = digest_of(inputs["evidence"])
        investigator = digest_of(
            {
                "constraints": constraints and constraints["id"],
                "statuses": inputs["statuses"],
                "promoted": inputs["promoted"],
                "results": {
                    c["experiment_id"]: c["result_claim_id"]
                    for c in inputs["candidates"]
                },
            }
        )
        methodology = digest_of(
            {
                "rules": rules.fingerprint(),
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
            "investigator_input": investigator,
            "methodology": methodology,
            "combined": digest_of(
                [project, protein, evidence, investigator, methodology]
            ),
        }

    def build(
        self,
        project: str,
        protein: str,
        *,
        created_at: datetime | None = None,
        created_by: str = ENGINE,
    ) -> dict[str, Any]:
        inputs = self.inputs(project, protein)
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
                "digest": parts["methodology"],
            },
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
        cause = [
            name
            for name in ("evidence", "investigator_input", "methodology")
            if before.get(name) != after.get(name)
        ]
        wording = {
            "evidence": "the stored evidence changed",
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
                new_evidence += [f"{key}: {i}" for i in value if i not in old]
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
        return {
            "from": previous["id"],
            "to": current["id"],
            "changes": changes,
            "new_evidence": new_evidence,
            "cause": cause,
            "cause_summary": summary,
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
        raise ValueError("unsupported question")

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
        if to == "completed":
            if not result_claim_id:
                raise ValueError(
                    "an experiment is completed only with a recorded result claim"
                )
            claim = self.store.claims.get(result_claim_id)
            if claim.knowledge_kind != KnowledgeKind.EXPERIMENTAL_RESULT:
                raise ValueError("completion requires an experimental_result claim")
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
            note,
            datetime.now(UTC),
            result_claim_id,
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
