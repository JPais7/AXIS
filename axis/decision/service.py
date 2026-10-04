"""Deterministic decision engine; reads stored evidence, never the network or an LLM.

Wording of explanations and candidate experiments is an imported AI suggestion
(frozen package). Evidence links, statuses, uncertainties, the critical
uncertainty and the recommendation are derived here by ``axis.decision.rules``.
"""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from axis.cellular.service import CellularPharmacologyService
from axis.decision import rules
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
        experiments = repo.collection(project, protein, "experiments", 100)["items"]
        assessments = repo.collection(project, protein, "assessments", 100)["items"]
        readouts = repo.collection(project, protein, "readouts", 100)["items"]
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
        selectivity = self.store.pharmacology.collection(
            project, protein, "selectivity", 100, 0
        )["items"]
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
        return {
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
                "total": len(selectivity),
                "comparable": len(selectivity) - len(unresolved),
                "unresolved_ids": unresolved,
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
                "non_b27_experiments": sum(
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

    # -- feasibility -------------------------------------------------------

    @staticmethod
    def feasibility(
        profile: dict[str, Any], constraints: dict[str, Any] | None
    ) -> dict[str, Any]:
        if constraints is None:
            return {
                "level": "unknown",
                "missing": [],
                "note": "Feasibility not assessed against local resource constraints.",
            }
        if profile["experiment_id"] in constraints.get("excluded_experiment_ids", []):
            return {
                "level": "blocked",
                "missing": [],
                "note": "Investigator constraints exclude this experiment.",
            }
        pool = {
            "models": constraints["available_models"],
            "reagents": constraints["available_compounds"],
            "assays": constraints["available_assays"],
        }
        missing = [
            item
            for kind, items in profile["required"].items()
            for item in items
            if item.casefold() not in {v.casefold() for v in pool.get(kind, [])}
            and item.casefold()
            not in {v.casefold() for v in constraints["available_equipment"]}
        ]
        if not missing:
            return {
                "level": "feasible_with_current_resources",
                "missing": [],
                "note": "",
            }
        covered = [
            m
            for m in missing
            if any(
                m.casefold() in c.casefold() or c.casefold() in m.casefold()
                for c in constraints["external_collaborations"]
            )
        ]
        level = (
            "external_collaboration"
            if len(covered) == len(missing)
            else "requires_new_capability"
        )
        return {
            "level": level,
            "missing": missing,
            "note": "Compared with investigator-entered resources.",
        }

    # -- build -------------------------------------------------------------

    def _statuses(self, project: str) -> dict[str, str]:
        status: dict[str, str] = {}
        for event in self.store.decisions.events(project):
            if event["event_type"] == "status":
                status[event["subject_id"]] = event["to_value"]
        return status

    def _promoted(self, project: str) -> list[str]:
        return sorted(
            {
                e["subject_id"]
                for e in self.store.decisions.events(project)
                if e["event_type"] == "promotion"
            }
        )

    def build(
        self,
        project: str,
        protein: str,
        *,
        created_at: datetime | None = None,
        created_by: str = ENGINE,
    ) -> dict[str, Any]:
        defs = self.store.decisions.explanations(project, protein)
        profiles = self.store.decisions.profiles(project, protein)
        if not defs or not profiles:
            raise ValueError("decision package not imported for this project")
        ev = self.evidence(project, protein)
        constraints = self.store.decisions.latest_constraints(project)
        statuses = self._statuses(project)
        promoted = self._promoted(project)
        digest = digest_of(
            {
                "project": project,
                "protein": protein,
                "rules": rules.RULES_VERSION,
                "evidence": ev,
                "constraints": constraints and constraints["id"],
                "statuses": statuses,
                "promoted": promoted,
                "candidates": [p["experiment_id"] for p in profiles],
            }
        )
        latest = self.store.decisions.latest_state(project, protein)
        if latest and latest["evidence_digest"] == digest:
            return latest
        hyp = self.store.hypotheses.get(defs[0]["hypothesis_id"])
        uncertainties = rules.derive_uncertainties(ev)

        # explanations: ungrounded suggestions never enter the state
        explanation_rows: list[dict[str, Any]] = []
        excluded_explanations: list[dict[str, str]] = []
        for definition in defs:
            links = rules.explanation_links(ev, definition["ground"], definition["id"])
            if not links:
                excluded_explanations.append(
                    {
                        "id": definition["id"],
                        "reason": "no grounded evidence link in the current evidence "
                        "state; not admitted to the DecisionState",
                    }
                )
                continue
            kind = (
                "researcher_hypothesis"
                if definition["id"] in promoted
                else definition["knowledge_kind"]
            )
            explanation_rows.append(
                {
                    "id": definition["id"],
                    "label": definition["label"],
                    "statement": definition["statement"],
                    "ground": definition["ground"],
                    "knowledge_kind": kind,
                    "status": rules.explanation_status(links),
                    "links": [
                        {
                            "relationship": link.relationship,
                            "evidence_type": link.evidence_type,
                            "evidence_id": link.evidence_id,
                            "rule_id": link.rule_id,
                            "rationale": link.rationale,
                        }
                        for link in links
                    ],
                    "rule_ids": [
                        rules.GROUND_RULES[definition["ground"]],
                        "DECISION-EXPL-001",
                    ],
                }
            )
        present = {e["id"] for e in explanation_rows}
        viable = {e["id"] for e in explanation_rows if e["status"] != "contradicted"}
        resolved_uncertainties = [
            replace(
                u,
                affected_explanation_ids=tuple(
                    i for i in u.affected_explanation_ids if i in present
                ),
            )
            for u in uncertainties
        ]

        candidates = []
        for profile in profiles:
            experiment = self.store.proposed_experiments.get(profile["experiment_id"])
            interpretations: dict[str, dict[str, str]] = {}
            for row in self.store.decisions.interpretations(profile["experiment_id"]):
                interpretations.setdefault(row["scenario_id"], {})[
                    row["explanation_id"]
                ] = row["effect"]
            consequences = self.store.decisions.consequences(profile["experiment_id"])
            kinds = [c["scenario_kind"] for c in consequences]
            candidates.append(
                {
                    "experiment_id": profile["experiment_id"],
                    "title": experiment.title,
                    "profile": profile,
                    "status": statuses.get(profile["experiment_id"], "proposed"),
                    "discrimination": rules.discrimination(interpretations, viable),
                    "interpretability": rules.interpretability(profile, kinds),
                    "distinct_consequences": len({c["category"] for c in consequences}),
                    "consequence_categories": sorted(
                        {c["category"] for c in consequences}
                    ),
                    "feasibility": self.feasibility(profile, constraints),
                    "cost": profile["cost"] or "not provided",
                }
            )
        info: dict[str, dict[str, int]] = {}
        for category in {c for p in profiles for c in p["considered_for"]}:
            considered = [
                x for x in candidates if category in x["profile"]["considered_for"]
            ]
            info[category] = {
                "count": len(considered),
                "consequences": len(
                    {c for x in considered for c in x["consequence_categories"]}
                ),
            }
        critical = rules.select_critical(resolved_uncertainties, viable, info)
        names = {e["id"]: e["label"] for e in explanation_rows}
        critical["reasons"] = [_named(reason, names) for reason in critical["reasons"]]
        selected = next(
            (u for u in resolved_uncertainties if u.id == critical["selected"]), None
        )
        ranked: list[dict[str, Any]] = []
        if selected is not None:
            ranked = rules.rank_candidates(
                [
                    x
                    for x in candidates
                    if selected.category in x["profile"]["considered_for"]
                ]
            )
        recommended = next((x for x in ranked if x["excluded"] is None), None)
        considered_ids = {x["experiment_id"] for x in ranked}
        for place, item in enumerate(ranked, start=1):
            item["rank"] = place
            if item["excluded"]:
                item["reason"] = item["excluded"]
            elif item is recommended:
                item["reason"] = "recommended: " + "; ".join(
                    [
                        f"separates {len(item['discrimination']['separated_pairs'])} "
                        "pair(s) of viable explanations",
                        f"{item['distinct_consequences']} distinct next actions "
                        "across outcomes",
                        f"interpretability {item['interpretability']['level']}",
                        f"{_label(item['profile']['target_proximity'])} endpoint",
                    ]
                )
            else:
                assert recommended is not None
                deciding = next(
                    i
                    for i, (a, b) in enumerate(
                        zip(recommended["rank_key"], item["rank_key"], strict=True)
                    )
                    if a != b
                )
                item["reason"] = (
                    "not recommended: lower on "
                    + CRITERIA_NAMES[deciding]
                    + (
                        "; separates no pair of explanations (low discrimination)"
                        if item["discrimination"]["low_discrimination"]
                        else ""
                    )
                )
        for item in candidates:
            if item["experiment_id"] not in considered_ids:
                item["rank"] = None
                item["reason"] = (
                    "not compared: considered for "
                    + ", ".join(_label(c) for c in item["profile"]["considered_for"])
                    + ", not for the critical uncertainty"
                )
            item["low_discrimination"] = item["discrimination"]["low_discrimination"]
            item.pop("rank_key", None)
            item["role_label"] = (
                "low discrimination — "
                + _label(item["profile"]["role"]).replace(
                    "mechanism discrimination", "not mechanism discrimination"
                )
                if item["low_discrimination"]
                else _label(item["profile"]["role"])
            )

        position = self._position(ev, resolved_uncertainties, explanation_rows)
        change_mind = self._change_mind(
            hyp.identifier, recommended, candidates, project
        )
        recommendation = self._recommendation(selected, recommended, project, critical)
        version = 1 if latest is None else latest["version"] + 1
        now = created_at or datetime.now(UTC)
        state_id = f"decision-state:{version}:{digest[:16]}"
        uncertainty_rows: list[dict[str, Any]] = [
            {
                "id": u.id,
                "category": u.category,
                "question": u.question,
                "status": u.status,
                "decision_relevance": u.decision_relevance,
                "resolvability": u.resolvability,
                "rationale": u.rationale,
                "fired_rules": list(u.fired_rules),
                "reasons": list(u.reasons),
                "source_gap_ids": list(u.source_gap_ids),
                "affected_explanation_ids": list(u.affected_explanation_ids),
                "evidence_refs": [list(r) for r in u.evidence_refs],
            }
            for u in resolved_uncertainties
        ]
        fired = sorted(
            {r for u in uncertainty_rows for r in u["fired_rules"]}
            | {r for e in explanation_rows for r in e["rule_ids"]}
            | {
                "DECISION-CRIT-001",
                "DECISION-EXP-001",
                "DECISION-EXP-002",
                "DECISION-EXP-003",
                "DECISION-EXP-004",
            }
        )
        payload: dict[str, Any] = {
            "id": state_id,
            "project_id": project,
            "protein_id": protein,
            "version": version,
            "supersedes_id": latest["id"] if latest else None,
            "status": "recorded",
            "hypothesis_id": hyp.identifier,
            "hypothesis_revision": hyp.current.revision,
            "hypothesis": {
                "title": hyp.title,
                "description": hyp.current.description,
                "state": hyp.current.state.value,
                "knowledge_kind": "researcher_hypothesis"
                if hyp.identifier in promoted
                else "ai_suggestion",
            },
            "rules_version": rules.RULES_VERSION,
            "evidence_digest": digest,
            "evidence": ev,
            "created_at": now.isoformat(),
            "created_by": created_by,
            "position": position,
            "explanations": explanation_rows,
            "excluded_explanations": excluded_explanations,
            "uncertainties": uncertainty_rows,
            "critical": critical,
            "critical_uncertainty_id": critical["selected"],
            "candidates": candidates,
            "recommended_experiment_id": recommended["experiment_id"]
            if recommended
            else None,
            "recommendation": recommendation,
            "what_would_change_our_mind": change_mind,
            "constraints": {
                "id": constraints["id"] if constraints else None,
                "note": None
                if constraints
                else "Feasibility not assessed against local resource constraints.",
            },
            "provenance": {
                "ai_generated": sorted(
                    [
                        e["id"]
                        for e in explanation_rows
                        if e["knowledge_kind"] == "ai_suggestion"
                    ]
                    + [c["experiment_id"] for c in candidates]
                ),
                "investigator_approved": sorted(
                    set(promoted) | {k for k, v in statuses.items() if v != "proposed"}
                ),
                "deterministic_rules": fired,
            },
            "disclaimer": "Decision framing given the evidence currently represented "
            "in "
            "AXIS; not scientific truth. All wording is an AI suggestion pending "
            "researcher review. No experiment has been performed.",
            "rationale": (
                f"Critical uncertainty: {selected.category.replace('_', ' ')}."
                if selected
                else "No open, testable uncertainty remains in the current evidence "
                "state."
            ),
        }
        payload["trace"] = self._trace(payload, ranked, excluded_explanations)
        payload["graph"] = self._graph(payload)
        payload["diff"] = self.diff(latest, payload) if latest else None
        state = DecisionState(
            state_id,
            project,
            protein,
            version,
            hyp.identifier,
            hyp.current.revision,
            now,
            created_by,
            digest,
            rules.RULES_VERSION,
            payload["rationale"],
            critical["selected"],
            payload["recommended_experiment_id"],
            latest["id"] if latest else None,
        )
        payload = json.loads(canonical(payload))
        with self.store._transaction():
            self.store.decisions.add_state(state, payload)
        return payload

    # -- projections -------------------------------------------------------

    @staticmethod
    def _position(
        ev: rules.Evidence, uncertainties: list[Any], explanations: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        supported, contradicted, unresolved = [], [], []
        for edge, value in ev["edges"].items():
            statement = (
                f"{_label(edge).capitalize()} evidence is {_label(value['state'])}."
            )
            row = {
                "statement": statement,
                "refs": [["edge", edge], *[["id", i] for i in value["ids"][:6]]],
            }
            if value["state"] == "supported":
                supported.append(row)
            elif value["state"] in ("contradicted", "mixed"):
                contradicted.append(row)
        for item in ev["source_disagreements"]:
            contradicted.append(
                {
                    "statement": "Sources disagree on the direction of "
                    f"{item['endpoint']} "
                    f"after ERAP1 perturbation ({' vs '.join(item['directions'])}).",
                    "refs": [["readout", i] for i in item["readout_ids"]],
                }
            )
        for u in uncertainties:
            if u.status in ("open", "partially_resolved"):
                unresolved.append(
                    {
                        "statement": u.question,
                        "refs": [
                            ["uncertainty", u.id],
                            *[list(r) for r in u.evidence_refs[:4]],
                        ],
                    }
                )
        return {
            "supported": supported,
            "contradicted": contradicted,
            "unresolved": unresolved,
        }

    def _change_mind(
        self,
        hypothesis_id: str,
        recommended: dict[str, Any] | None,
        candidates: list[dict[str, Any]],
        project: str,
    ) -> dict[str, Any]:
        weaken, strengthen = [], []
        ordered = sorted(
            candidates,
            key=lambda c: (
                c["experiment_id"] != (recommended or {}).get("experiment_id"),
                c["experiment_id"],
            ),
        )
        for item in ordered:
            interpretations = self.store.decisions.interpretations(
                item["experiment_id"]
            )
            for c in self.store.decisions.consequences(item["experiment_id"]):
                row = {
                    "hypothesis_id": hypothesis_id,
                    "experiment_id": item["experiment_id"],
                    "scenario_id": c["scenario_id"],
                    "category": c["category"],
                    "statement": c["conditional_statement"],
                    "explanation_effects": [
                        {"explanation_id": i["explanation_id"], "effect": i["effect"]}
                        for i in interpretations
                        if i["scenario_id"] == c["scenario_id"]
                        and i["effect"] != "does_not_discriminate"
                    ],
                    "prospective": True,
                }
                if c["category"] in WEAKENING:
                    weaken.append(row)
                elif c["category"] in STRENGTHENING:
                    strengthen.append(row)
        return {
            "question": "What result would make us reconsider the current strategy?",
            "would_weaken": weaken,
            "would_strengthen": strengthen,
            "label": "prospective / hypothetical — no result has been observed",
        }

    def _recommendation(
        self,
        selected: Any,
        recommended: dict[str, Any] | None,
        project: str,
        critical: dict[str, Any],
    ) -> dict[str, Any] | None:
        if selected is None or recommended is None:
            return None
        experiment = self.store.proposed_experiments.get(recommended["experiment_id"])
        profile = recommended["profile"]
        scenarios = []
        interpretations = self.store.decisions.interpretations(experiment.experiment_id)
        consequences = {
            c["scenario_id"]: c
            for c in self.store.decisions.consequences(experiment.experiment_id)
        }
        for scenario in self.store.outcome_scenarios.list_for_experiment(
            experiment.experiment_id
        ):
            cons = consequences[scenario.scenario_id]
            scenarios.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "kind": cons["scenario_kind"],
                    "outcome": scenario.possible_outcome,
                    "interpretation": scenario.interpretation,
                    "explanation_effects": [
                        {k: i[k] for k in ("explanation_id", "effect", "rationale")}
                        for i in interpretations
                        if i["scenario_id"] == scenario.scenario_id
                    ],
                    "consequence": {
                        "category": cons["category"],
                        "statement": cons["conditional_statement"],
                        "new_uncertainty": cons["new_uncertainty"],
                    },
                    "prospective": True,
                }
            )
        return {
            "question": selected.question,
            "why_now": f"{selected.category.replace('_', ' ')} is the "
            f"{_label(selected.decision_relevance)} uncertainty: "
            + "; ".join(critical["reasons"][:1] + list(selected.reasons)),
            "experiment_id": experiment.experiment_id,
            "title": experiment.title,
            "experiment": experiment.intervention_description,
            "biological_context": experiment.experimental_system,
            "controls": {
                "negative": profile["controls_negative"],
                "positive": profile["controls_positive"]
                or ["No validated positive control identified in the curated corpus."],
            },
            "primary_endpoint": profile["primary_endpoint"],
            "secondary_endpoints": profile["secondary_endpoints"],
            "outcome_scenarios": scenarios,
            "limitations": profile["limitations"],
            "remaining_after": profile["limitations"],
            "knowledge_kind": experiment.knowledge_kind.value,
            "status": recommended["status"],
            "why_this_experiment": {
                "uncertainty": selected.question,
                "explanations_separated": [
                    list(pair)
                    for pair in recommended["discrimination"]["separated_pairs"]
                ],
                "why_current_evidence_cannot_answer": "; ".join(selected.reasons),
                "why_outcome_changes_decision": " ".join(
                    s["consequence"]["statement"] for s in scenarios[:3]
                ),
                "remains_unresolved": profile["limitations"],
            },
        }

    def _trace(
        self,
        payload: dict[str, Any],
        ranked: list[dict[str, Any]],
        excluded_explanations: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "evidence_considered": {
                "digest": payload["evidence_digest"],
                "edges": {
                    k: v["state"] for k, v in payload["evidence"]["edges"].items()
                },
                "selectivity": payload["evidence"]["selectivity"],
                "concordance": payload["evidence"]["concordance"],
            },
            "rules_fired": [
                {
                    "id": r,
                    "version": rules.RULES[r].version,
                    "description": rules.RULES[r].description,
                }
                for r in payload["provenance"]["deterministic_rules"]
            ],
            "uncertainties_generated": [
                {
                    "id": u["id"],
                    "status": u["status"],
                    "relevance": u["decision_relevance"],
                    "rules": u["fired_rules"],
                }
                for u in payload["uncertainties"]
            ],
            "explanations_affected": {
                u["id"]: u["affected_explanation_ids"] for u in payload["uncertainties"]
            },
            "explanations_not_admitted": excluded_explanations,
            "candidates_considered": [
                {
                    "experiment_id": c["experiment_id"],
                    "rank": c["rank"],
                    "reason": c["reason"],
                    "low_discrimination": c["low_discrimination"],
                }
                for c in payload["candidates"]
            ],
            "critical_selection": payload["critical"],
            "outcome_logic": "Experiment -> OutcomeScenario -> OutcomeInterpretation "
            "-> CompetingExplanation -> DecisionConsequence (all prospective).",
            "ranked_for_critical": [c["experiment_id"] for c in ranked],
        }

    @staticmethod
    def _graph(payload: dict[str, Any]) -> dict[str, Any]:
        nodes: list[dict[str, str]] = [
            {
                "id": payload["hypothesis_id"],
                "type": "Hypothesis",
                "label": payload["hypothesis"]["title"],
            },
            {
                "id": payload["id"],
                "type": "DecisionState",
                "label": f"Decision state v{payload['version']}",
            },
        ]
        edges: list[dict[str, str]] = [
            {
                "from": payload["id"],
                "to": payload["hypothesis_id"],
                "kind": "frames",
                "basis": "DecisionState references this hypothesis revision.",
            }
        ]
        for e in payload["explanations"]:
            nodes.append(
                {"id": e["id"], "type": "CompetingExplanation", "label": e["label"]}
            )
            edges.append(
                {
                    "from": e["id"],
                    "to": payload["hypothesis_id"],
                    "kind": "competes_for",
                    "basis": "Alternative explanation of the same evidence.",
                }
            )
        for u in payload["uncertainties"]:
            nodes.append(
                {"id": u["id"], "type": "ScientificUncertainty", "label": u["question"]}
            )
            for gap in u["source_gap_ids"]:
                nodes.append({"id": gap, "type": "EvidenceGap", "label": gap})
                edges.append(
                    {
                        "from": gap,
                        "to": u["id"],
                        "kind": "informs",
                        "basis": "Cellular evidence gap behind this uncertainty.",
                    }
                )
            for expl in u["affected_explanation_ids"]:
                edges.append(
                    {
                        "from": u["id"],
                        "to": expl,
                        "kind": "affects",
                        "basis": "Rule " + ", ".join(u["fired_rules"]),
                    }
                )
        for c in payload["candidates"]:
            nodes.append(
                {"id": c["experiment_id"], "type": "Experiment", "label": c["title"]}
            )
            for gap in c["profile"]["addressed_gap_ids"]:
                edges.append(
                    {
                        "from": gap,
                        "to": c["experiment_id"],
                        "kind": "addressed_by",
                        "basis": "Candidate experiment is linked to this gap.",
                    }
                )
            for pair in c["discrimination"]["separated_pairs"]:
                for expl in pair:
                    edges.append(
                        {
                            "from": c["experiment_id"],
                            "to": expl,
                            "kind": "discriminates",
                            "basis": "Outcomes move this explanation opposite to "
                            "another viable one.",
                        }
                    )
        return {"nodes": nodes, "edges": edges}

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
                    if e["id"] == "explanation:on_target"
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
