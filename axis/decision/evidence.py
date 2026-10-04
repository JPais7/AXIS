"""Evidence assembly in two layers.

``load_records`` is the only place that reads the Evidence Store. ``assemble_evidence``
is pure: it turns plain, JSON-serializable *records* into the mapping consumed by the
decision rules. A retrospective benchmark feeds ``assemble_evidence`` only the records
that were temporally eligible, so future evidence never reaches the engine.
"""

from typing import Any

from axis.cellular.rules import aggregate
from axis.cellular.service import CellularPharmacologyService, comparisons_of
from axis.domain.cellular import EDGES
from axis.storage import EvidenceStore

GENETIC = {"knockdown", "knockout", "CRISPR", "variant_expression"}
Records = dict[str, Any]


def load_records(store: EvidenceStore, project: str, protein: str) -> Records:
    """Read every record the assembler needs from the store (bounded, scoped)."""
    store.targets.require_member(project, protein)
    cell = CellularPharmacologyService(store)
    chain = cell.chain(project, protein)
    windows = {
        kind: store.cellular.collection(project, protein, kind, 100)
        for kind in ("experiments", "assessments", "readouts")
    }
    truncated = [kind for kind, page in windows.items() if page["has_more"]]
    if chain["has_more"] or truncated:
        raise ValueError(
            "evidence window exceeded the bounded read size ("
            + ", ".join(truncated or ["evidence chain"])
            + "); the decision engine refuses to run on truncated evidence"
        )
    selectivity_page = store.pharmacology.collection(
        project, protein, "selectivity", 100, 0
    )
    if selectivity_page["has_more"]:
        raise ValueError(
            "selectivity window exceeded the bounded read size; the decision "
            "engine refuses to run on truncated evidence"
        )
    protein_record = store.targets.protein(protein)
    return {
        "target_label": protein_record.gene_symbol
        or protein_record.recommended_name
        or protein_record.primary_accession,
        "experiments": windows["experiments"]["items"],
        "assessments": windows["assessments"]["items"],
        "readouts": windows["readouts"]["items"],
        "biochemical_measurements": [
            m
            for e in chain["edges"]
            if e["edge"] == "biochemical"
            for m in e["measurements"]
        ],
        "selectivity": [
            {"id": s["id"], "comparability_status": s["comparability_status"]}
            for s in selectivity_page["items"]
        ],
        "compounds": sorted(
            c["id"]
            for c in store.pharmacology.collection(
                project, protein, "compounds", 100, 0
            )["items"]
        ),
        "gaps": cell.gaps(project, protein)["items"],
        "structure_ids": [
            row[0]
            for row in store._connection.execute(
                "SELECT structure_id FROM project_structures WHERE project_id=? "
                "ORDER BY structure_id",
                [project],
            ).fetchall()
        ],
        "strategy_ids": sorted(
            row[0]
            for row in store._connection.execute(
                "SELECT strategy_id FROM intervention_strategies WHERE project_id=?",
                [project],
            ).fetchall()
        ),
    }


def assemble_evidence(
    records: Records,
    *,
    mode: str = "exploratory",
    assessment_reviews: dict[str, str] | None = None,
    ledger: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pure assembly of the decision evidence mapping from plain records."""
    reviews = assessment_reviews or {}

    def keep(identifier: str) -> bool:
        state = reviews.get(identifier, "pending")
        return state in ("accepted", "accepted_with_caveat") or (
            state == "pending" and mode == "exploratory"
        )

    experiments = sorted(records["experiments"], key=lambda e: e["id"])
    all_assessments = sorted(records["assessments"], key=lambda a: a["id"])
    readouts = sorted(records["readouts"], key=lambda r: r["id"])
    biochemical_items = sorted(
        records["biochemical_measurements"], key=lambda m: m["id"]
    )
    selectivity = sorted(records["selectivity"], key=lambda s: s["id"])
    gaps = sorted(records["gaps"], key=lambda g: g["id"])
    edges: dict[str, dict[str, Any]] = {}
    for edge in EDGES:
        items = [a for a in all_assessments if a["edge"] == edge]
        kept_items = [a for a in items if keep(a["id"])]
        state = aggregate([a["state"] for a in kept_items])
        if edge == "biochemical" and biochemical_items:
            state = "supported"
        edges[edge] = {
            "state": state,
            "ids": sorted(
                [a["id"] for a in kept_items]
                + (
                    [m["id"] for m in biochemical_items]
                    if edge == "biochemical"
                    else []
                )
            ),
        }
    assessments = [a for a in all_assessments if keep(a["id"])]
    pending = sum(reviews.get(a["id"], "pending") == "pending" for a in assessments)
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
        if modality[a["experiment_id"]] in GENETIC and a["dependency"] == "supported"
    )
    unresolved = sorted(
        s["id"] for s in selectivity if s["comparability_status"] != "Comparable"
    )
    comparisons = comparisons_of(experiments, readouts)["items"]
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
    by_experiment = {e["id"]: e for e in experiments}
    supported_phenotype = {
        a["experiment_id"]
        for a in assessments
        if a["edge"] in ("hla", "immune") and a["state"] == "supported"
    }
    with_phenotype = {
        e["compound_id"]
        for e in experiments
        if e.get("compound_id") and e["id"] in supported_phenotype
    }
    with_biochemical = {m["compound_id"] for m in biochemical_items}
    unresolved_identity = sorted(
        {
            e.get("reported_perturbagen") or e["label"]
            for e in experiments
            if e["modality"] == "small_molecule"
            and not e.get("compound_id")
            and e["id"] in supported_phenotype
        }
    )
    gap_scopes: dict[str, str] = {}
    for g in gaps:
        if g.get("compound_id"):
            gap_scopes[g["id"]] = f"compound:{g['compound_id']}"
        else:
            owner = by_experiment.get(g["id"].removesuffix(":gap"), {})
            label = owner.get("reported_perturbagen") or owner.get("label")
            if label:
                gap_scopes[g["id"]] = f"perturbagen:{label}"
    entries = ledger or []
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
        "required_scopes": [
            {"scope_type": "compound", "scope_id": c} for c in sorted(with_phenotype)
        ]
        + [{"scope_type": "perturbagen", "scope_id": p} for p in unresolved_identity],
        "gap_scopes": gap_scopes,
        "unexpected_results": [
            {"result_id": r, "relationship": "outside_predefined_scenarios"}
            for r in unexpected
        ],
        "context_of": {
            a["id"]: " / ".join(
                part
                for part in (
                    by_experiment[a["experiment_id"]]["context"]["cell_line"],
                    by_experiment[a["experiment_id"]]["context"]["hla_allele"]
                    or "no HLA allele reported",
                )
                if part
            )
            for a in phenotype
        },
        "target_label": records["target_label"],
        "compound_coverage": {
            "compounds": [
                {
                    "compound_id": c,
                    "biochemical": c in with_biochemical,
                    "cellular_phenotype": c in with_phenotype,
                }
                for c in sorted(records["compounds"])
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
                status: sum(s["comparability_status"] == status for s in selectivity)
                for status in sorted({s["comparability_status"] for s in selectivity})
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
            "not_comparable": sum(c["state"] == "not_comparable" for c in comparisons),
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
        "structure_ids": sorted(records["structure_ids"]),
        "strategy_ids": sorted(records["strategy_ids"]),
    }
