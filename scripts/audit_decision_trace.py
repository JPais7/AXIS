"""Print the complete evidence -> consequence trace of the ERAP1 decision as markdown.

Builds from a clean in-memory store using only frozen resources; no network.
"""
# ruff: noqa: E501

import json
from datetime import UTC, datetime

from axis.cellular.service import CellularPharmacologyService
from axis.decision.service import DecisionService
from axis.discovery.curation import import_curated_erap1
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore
from axis.targets.identity import TargetIdentityService

PROJECT = "AXIS-DD-ERAP1-CURATED-001"


def main() -> None:
    with EvidenceStore() as store:
        import_curated_erap1(store)
        protein = TargetIdentityService(store).import_package(PROJECT)
        PharmacologyService(store).import_package(PROJECT, protein)
        CellularPharmacologyService(store).import_package(PROJECT, protein)
        service = DecisionService(store)
        service.import_package(PROJECT, protein)
        state = service.build(
            PROJECT, protein, created_at=datetime(2026, 10, 4, 18, tzinfo=UTC)
        )
    ev = state["evidence"]
    print(
        f"state `{state['id']}` rules `{state['rules_version']}` "
        f"methodology `{state['methodology']['digest'][:12]}` "
        f"evidence `{state['digests']['evidence'][:12]}`\n"
    )
    print("| Stage | Input | Rule / transformation | Output | Provenance |")
    print("|---|---|---|---|---|")
    for edge, value in ev["edges"].items():
        print(
            f"| Evidence | {len(value['ids'])} stored records | Phase 3.4 `aggregate` "
            f"over cellular assessments / Phase 3.3 measurements | edge `{edge}` = "
            f"`{value['state']}` | persisted assessment/measurement ids |"
        )
    print(
        f"| Evidence | {ev['selectivity']['total']} selectivity assessments "
        f"{json.dumps(ev['selectivity']['by_status'])} | Phase 3.3 comparability "
        f"(`axis.pharmacology.selectivity`) | {ev['selectivity']['comparable']} "
        "comparable | `selectivity_assessments` |"
    )
    print(
        f"| Evidence | {len(ev['source_disagreements'])} source disagreement(s) | "
        "opposite directions, same genetic endpoint, different sources | "
        f"{'; '.join(d['endpoint'] for d in ev['source_disagreements'])} | readout ids |"
    )
    for gap in ev["gap_ids"]:
        print(
            f"| Gap | open question `{gap}` | Phase 3.4 import | evidence gap | "
            "`open_questions`, `cellular_gap_links` |"
        )
    for u in state["uncertainties"]:
        print(
            f"| Uncertainty | {'; '.join(u['reasons'])} | "
            f"{', '.join(u['fired_rules'])} | `{u['category']}` "
            f"{u['status']} / {u['decision_relevance']} / {u['resolvability']} | "
            f"{len(u['evidence_refs'])} evidence refs |"
        )
    for e in state["explanations"]:
        counts = {
            r: sum(x["relationship"] == r for x in e["links"])
            for r in ("supports", "contradicts", "leaves_unresolved", "context_limits")
        }
        print(
            f"| Explanation | `{e['id']}` ({e['knowledge_kind']}) links {json.dumps(counts)} | "
            f"{', '.join(e['rule_ids'])} | status `{e['status']}` | frozen wording + derived links |"
        )
    crit = state["critical"]
    print(
        f"| Criticality | {len(state['uncertainties'])} uncertainties | DECISION-CRIT-001 | "
        f"`{crit['selected']}` ({len(crit['alternatives'])} alternatives with reasons; "
        f"ties: {crit['tied_with']}) | {'; '.join(crit['reasons'][:3])} |"
    )
    for c in state["candidates"]:
        print(
            f"| Experiment | `{c['experiment_id']}` rank {c['rank']} | DECISION-EXP-001..005 | "
            f"pairs {len(c['discrimination']['separated_pairs'])}, falsifying "
            f"{c['falsification']['falsifying']}, interpretability "
            f"{c['interpretability']['level']} | {c['reason']} |"
        )
    for s in state["recommendation"]["outcome_scenarios"]:
        effects = ", ".join(
            f"{x['explanation_id'].split(':')[1]} {x['effect']}"
            for x in s["explanation_effects"]
            if x["effect"] != "does_not_discriminate"
        )
        print(
            f"| Outcome | {s['kind']}: {s['outcome']} | frozen scenario (prospective) | "
            f"{effects or 'no discrimination'} | `outcome_interpretations` |"
        )
        print(
            f"| Consequence | {s['scenario_id'].split(':')[-1]} | frozen conditional consequence | "
            f"`{s['consequence']['category']}` | `decision_consequences` |"
        )


if __name__ == "__main__":
    main()
