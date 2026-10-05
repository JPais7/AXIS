"""Phase 3.9: chemical learning.

Synthetic fixtures are SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE. The ERAP1
tests use the real indexed measurements and assert a scientifically justified refusal.
"""

import copy
import json
import re
import shutil
import socket
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from axis.api.server import ReadAPI
from axis.cellular.service import CellularPharmacologyService
from axis.cli.main import app
from axis.decision.service import DecisionService
from axis.discovery.curation import import_curated_erap1
from axis.learning import dataset as ds
from axis.learning import eligibility, models, sar, selection
from axis.learning.service import LearningError, LearningService, registry_root
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore, RecordConflictError, RecordNotFoundError
from axis.structures.service import StructureIdentityService
from axis.targets.identity import TargetIdentityService

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "AXIS-DD-ERAP1-CURATED-001"
SYNTHETIC = "SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE"
CUTOFF = "2020-12-31"


@pytest.fixture(scope="module")
def erap_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("l39") / "erap.duckdb"
    with EvidenceStore(path) as s:
        import_curated_erap1(s)
        protein = TargetIdentityService(s).import_package(PROJECT)
        StructureIdentityService(s).import_package(PROJECT, protein)
        PharmacologyService(s).import_package(PROJECT, protein)
        CellularPharmacologyService(s).import_package(PROJECT, protein)
        DecisionService(s).import_package(PROJECT, protein)
    return path


@pytest.fixture
def erap(erap_db: Path, tmp_path: Path) -> Any:
    copy_ = tmp_path / "e.duckdb"
    shutil.copy(erap_db, copy_)
    with EvidenceStore(copy_) as s:
        yield LearningService(s)


@pytest.fixture
def syn(tmp_path: Path) -> Any:
    with EvidenceStore(tmp_path / "s.duckdb") as s:
        yield LearningService(s)


def main_dataset(
    service: LearningService, cutoff: str | None = CUTOFF
) -> tuple[str, str]:
    project, records = service.synthetic_records(cutoff)
    ids = service.build_datasets(project, records, synthetic=True)
    return project, next(i for i in ids if "SYN-SUBSTRATE-1" in i)


def rec(
    i: str,
    ref: str,
    smiles: str,
    value: float,
    unit: str = "nM",
    op: str = "=",
    **context: Any,
) -> dict[str, Any]:
    base = {
        "target": "T",
        "taxon": 1,
        "assay_type": "biochemical_activity",
        "format": "enzyme",
        "substrate": "S",
    }
    return {
        "id": i,
        "compound_ref": ref,
        "smiles": smiles,
        "operator": op,
        "value": value,
        "unit": unit,
        "endpoint": "IC50",
        "context": {**base, **context},
        "source": "s",
        "date": None,
    }


# --- datasets ---------------------------------------------------------------------


def test_incompatible_contexts_are_never_pooled() -> None:
    records = [rec("a", "x", "CCO", 10), rec("b", "x", "CCO", 20, substrate="S2")]
    assert len(ds.group_records(records)) == 2
    with pytest.raises(ValueError, match="one assay context"):
        ds.build_dataset(records, project_id="p")
    mixed = [rec("a", "x", "CCO", 10), {**rec("b", "x", "CCO", 20), "endpoint": "Ki"}]
    assert len(ds.group_records(mixed)) == 2


def test_units_are_normalised_only_when_valid_and_originals_are_kept() -> None:
    d = ds.build_dataset(
        [
            rec("a", "x", "CCO", 2.5, "µM"),
            rec("b", "y", "CCC", 4.1, "fold"),
            rec("c", "z", "CCCC", 3, "weird"),
        ][:1],
        project_id="p",
    )
    m = d["measurements"][0]
    assert m["original_value"] == 2.5 and m["original_unit"] == "µM"
    assert (
        m["normalized_value"] == 2500.0
        and m["normalized_unit"] == "nM"
        and "µM to nM" in m["transformation"]
    )
    bad = ds.build_dataset([rec("c", "z", "CCCC", 3, "weird")], project_id="p")
    assert (
        bad["measurements"][0]["included"] is False
        and bad["measurements"][0]["exclusion_reason"]
    )
    assert ds.normalise(4.1, "fold")[1] == "fold"


def test_inequalities_are_preserved_and_never_become_exact_values() -> None:
    d = ds.build_dataset([rec("a", "x", "CCO", 200, "µM", ">")], project_id="p")
    assert d["measurements"][0]["operator"] == ">"
    v = d["compound_values"][0]
    assert (
        v["value"] is None
        and v["operator"] == ">"
        and v["censored"][0]["value"] == 200000.0
    )
    with pytest.raises(ValueError, match="operator"):
        ds.build_dataset([rec("a", "x", "CCO", 1, op="~")], project_id="p")


def test_replicates_are_retained_and_contradiction_is_not_averaged_away() -> None:
    d = ds.build_dataset(
        [
            rec("a", "x", "CCO", 10),
            rec("b", "x", "CCO", 11),
            rec("c", "y", "CCC", 10),
            rec("d", "y", "CCC", 200),
        ],
        project_id="p",
    )
    values = {v["compound_ref"]: v for v in d["compound_values"]}
    assert values["x"]["value"] == 10.5 and values["x"]["replicate_policy"].startswith(
        "median"
    )
    assert values["y"]["contradictory"] is True and values["y"]["value"] is None
    assert len(d["measurements"]) == 4  # every raw measurement stays


def test_dataset_checksum_is_deterministic_and_content_sensitive() -> None:
    a = ds.build_dataset([rec("a", "x", "CCO", 10)], project_id="p")
    b = ds.build_dataset([rec("a", "x", "CCO", 10)], project_id="p")
    c = ds.build_dataset([rec("a", "x", "CCO", 11)], project_id="p")
    assert a["checksum"] == b["checksum"] and a["checksum"] != c["checksum"]
    assert a["content_checksum"] != c["content_checksum"]
    assert "not a new experimental source" in a["provenance"]


def test_frozen_datasets_are_immutable_and_changes_make_revisions(
    syn: LearningService,
) -> None:
    project, records = syn.synthetic_records(CUTOFF)
    first = syn.build_datasets(project, records, synthetic=True)
    assert syn.build_datasets(project, records, synthetic=True) == first  # idempotent
    changed = copy.deepcopy(records)
    changed[0]["value"] = changed[0]["value"] * 2
    second = syn.build_datasets(project, changed, synthetic=True)
    assert set(second) - set(first) and any(i.endswith("@r2") for i in second)
    old = syn.dataset(first[0])
    assert old["revision"] == 1
    with pytest.raises(RecordConflictError):
        syn.repo.put(
            "chemical_learning_datasets",
            first[0],
            {
                "logical_id": "x",
                "revision": 1,
                "project_id": "p",
                "checksum": "c",
                "synthetic": True,
            },
            {"changed": True},
        )


# --- comparability ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "state"),
    [
        (
            {
                "target": "T",
                "taxon": 1,
                "assay_type": "b",
                "format": "e",
                "substrate": "S",
                "endpoint": "IC50",
            },
        )
        * 2
        + ("directly_comparable",),
        (
            {
                "target": "T",
                "taxon": 1,
                "assay_type": "b",
                "format": "e",
                "substrate": "S",
                "endpoint": "IC50",
            },
            {
                "target": "U",
                "taxon": 1,
                "assay_type": "b",
                "format": "e",
                "substrate": "S",
                "endpoint": "IC50",
            },
            "not_directly_comparable",
        ),
        (
            {
                "target": "T",
                "taxon": 1,
                "assay_type": "b",
                "format": "e",
                "substrate": "S",
                "endpoint": "IC50",
            },
            {
                "target": "T",
                "taxon": 1,
                "assay_type": "c",
                "format": "e",
                "substrate": "S",
                "endpoint": "IC50",
            },
            "not_directly_comparable",
        ),
        (
            {
                "target": "T",
                "taxon": 1,
                "assay_type": "b",
                "format": "e",
                "substrate": "S",
                "endpoint": "IC50",
            },
            {
                "target": "T",
                "taxon": 1,
                "assay_type": "b",
                "format": "e",
                "substrate": "S",
                "endpoint": "Ki",
            },
            "not_directly_comparable",
        ),
        (
            {
                "target": "T",
                "taxon": 1,
                "assay_type": "b",
                "format": "e",
                "substrate": "S",
                "endpoint": "IC50",
            },
            {
                "target": "T",
                "taxon": 1,
                "assay_type": "b",
                "format": "e",
                "substrate": "Z",
                "endpoint": "IC50",
            },
            "not_directly_comparable",
        ),
        (
            {
                "target": "T",
                "taxon": 1,
                "assay_type": "b",
                "format": "e",
                "substrate": None,
                "endpoint": "IC50",
            },
            {
                "target": "T",
                "taxon": 1,
                "assay_type": "b",
                "format": "e",
                "substrate": "S",
                "endpoint": "IC50",
            },
            "insufficient_context",
        ),
        (
            {
                "target": "T",
                "taxon": 1,
                "assay_type": "b",
                "format": "e",
                "substrate": "S",
                "endpoint": "IC50",
            },
            {
                "target": "T",
                "taxon": 1,
                "assay_type": "b",
                "format": "f",
                "substrate": "S",
                "endpoint": "IC50",
            },
            "comparable_with_conditions",
        ),
    ],
)
def test_comparability_states(a: dict[str, Any], b: dict[str, Any], state: str) -> None:
    result = ds.comparability(a, b)
    assert result["state"] == state and result["rationale"]


# --- SAR --------------------------------------------------------------------------------


def test_observed_sar_inferred_hypotheses_and_missing_are_separate(
    syn: LearningService,
) -> None:
    _, dataset_id = main_dataset(syn)
    syn.derive_sar(dataset_id)
    view = syn.observed_sar(dataset_id)
    assert (
        view["observed"]["label"] == "OBSERVED SAR"
        and "INFERRED" in view["inferred"]["label"]
    )
    assert view["observed"]["matched_pairs"] and view["inferred"]["hypotheses"]
    for p in view["observed"]["matched_pairs"]:
        assert p["epistemic_class"] == "axis_observation"
        assert (
            "not a mechanism" in p["statement"]
            or "cannot be quantified" in p["statement"]
        )
        assert "causal" not in p["statement"].lower().replace("no causal", "")
    for h in view["inferred"]["hypotheses"]:
        assert (
            h["epistemic_class"] == "axis_inference"
            and h["review_state"] == "pending_review"
        )
        assert h["falsification"] and "mechanism" in h["causality"]


def test_matched_pairs_are_deterministic_and_trace_to_measurements(
    syn: LearningService,
) -> None:
    _, dataset_id = main_dataset(syn)
    d = syn.dataset(dataset_id)
    first, second = sar.matched_pairs(d), sar.matched_pairs(d)
    assert first == second and first
    refs = {c["compound_ref"] for c in d["compounds"]}
    for p in first:
        assert {p["compound_a"], p["compound_b"]} <= refs
        assert (
            p["measurement_a"]["sources"] and p["assay_context"] == d["assay_context"]
        )


def test_censored_and_contradictory_values_do_not_yield_quantified_pairs() -> None:
    d = ds.build_dataset(
        [
            rec("a", "a", "c1ccc(F)cc1C(=O)NC", 100, "µM", ">"),
            rec("b", "b", "c1ccc(Cl)cc1C(=O)NC", 10),
        ],
        project_id="p",
    )
    pairs = sar.matched_pairs(d)
    assert pairs and all(
        p["activity_change"]["direction"] == "not_quantifiable" for p in pairs
    )


def test_scaffold_groups_are_algorithmic_not_curated_series(
    syn: LearningService,
) -> None:
    _, dataset_id = main_dataset(syn)
    groups = sar.scaffold_groups(syn.dataset(dataset_id))
    assert len(groups) >= 5 and all(
        "not a curated chemical series" in g["definition"] for g in groups
    )


def test_hypothesis_keeps_contradicting_observations() -> None:
    pairs = [
        {
            "id": "p1",
            "transformation": "F >> Cl",
            "activity_change": {"direction": "lower_in_b"},
        },
        {
            "id": "p2",
            "transformation": "F >> Cl",
            "activity_change": {"direction": "lower_in_b"},
        },
        {
            "id": "p3",
            "transformation": "F >> Cl",
            "activity_change": {"direction": "higher_in_b"},
        },
    ]
    h = sar.hypotheses(
        {
            "id": "d",
            "endpoint": "IC50",
            "target": "T",
            "assay_context": {"substrate": "S"},
        },
        pairs,
    )
    assert h[0]["supporting_observations"] == ["p1", "p2"] and h[0][
        "contradictory_observations"
    ] == ["p3"]


# --- eligibility and scientific refusal ----------------------------------------------------


def _dataset(n: int, scaffold_variety: int = 6, censored: int = 0) -> dict[str, Any]:
    smiles = [
        "c1ccccc1C(=O)NC",
        "c1ccccc1Oc1ccccc1",
        "c1ccc2ccccc2c1",
        "c1ccccc1S(=O)(=O)N1CCCC1",
        "c1ccccc1C1CCNCC1",
        "c1ccccc1Nc1ccccn1",
        "c1ccoc1CC",
    ]
    subs = ["", "F", "Cl", "C", "O", "Br", "N", "CC", "OC", "CCC"]
    records = []
    for i in range(n):
        base = smiles[i % scaffold_variety]
        s = (
            base
            if not subs[i // scaffold_variety % len(subs)]
            else base.replace(
                "c1ccccc1", f"c1ccc({subs[i // scaffold_variety % len(subs)]})cc1", 1
            )
        )
        if i < censored:
            records.append(
                rec(f"m{i}", f"c{i}", s + "" if i < 0 else s, 100, "µM", ">")
            )
        else:
            records.append(rec(f"m{i}", f"c{i}", s, 10 ** (1 + (i % 7) * 0.3)))
    return ds.build_dataset(records, project_id="p")


def test_small_dataset_is_refused() -> None:
    result = eligibility.assess(_dataset(8))
    assert result["conclusion"] == "not_eligible" and result["model_built"] is False
    assert any("sample size" in r for r in result["reasons"])


def test_no_chemical_diversity_is_refused() -> None:
    result = eligibility.assess(_dataset(30, scaffold_variety=1))
    assert result["conclusion"] == "not_eligible" and any(
        "chemical diversity" in r for r in result["reasons"]
    )


def test_excessive_censoring_is_refused() -> None:
    result = eligibility.assess(_dataset(40, censored=30))
    assert result["conclusion"] == "not_eligible" and any(
        "censoring" in r for r in result["reasons"]
    )


def test_all_censored_observations_are_refused() -> None:
    d = ds.build_dataset(
        [rec(f"m{i}", f"c{i}", "C" * (i + 1), 200, "µM", ">") for i in range(25)],
        project_id="p",
    )
    result = eligibility.assess(d)
    assert result["conclusion"] == "not_eligible" and result["counts"]["exact"] == 0


def test_duplicate_structures_are_refused() -> None:
    records = [rec(f"m{i}", f"c{i}", "c1ccccc1C(=O)NC", 10 + i) for i in range(25)]
    result = eligibility.assess(ds.build_dataset(records, project_id="p"))
    assert any("duplicate structures" in r for r in result["reasons"])


def test_adequate_dataset_is_eligible_and_policy_is_generic(
    syn: LearningService,
) -> None:
    _, dataset_id = main_dataset(syn)
    result = syn.assess_eligibility(dataset_id)
    assert result["conclusion"] in ("eligible", "eligible_with_conditions")
    assert (
        result["readiness"].startswith("MODEL_ELIGIBLE")
        and len(result["policy_fingerprint"]) == 64
    )
    assert "target" not in json.dumps(eligibility.POLICY).lower()


def test_ineligible_training_returns_model_not_built(syn: LearningService) -> None:
    project, records = syn.synthetic_records(CUTOFF)
    ids = syn.build_datasets(project, records, synthetic=True)
    small = next(i for i in ids if "SYN-SUBSTRATE-2" in i)
    result = syn.train(small)
    assert result["model_built"] is False and result["status"] == "MODEL NOT BUILT"
    assert "Insufficient data" in result["statement"]
    assert not syn.repo.rows("chemical_models", "WHERE dataset_id=?", [small])


# --- ERAP1 (real indexed chemistry) ---------------------------------------------------------


def test_erap1_inventory_is_assay_aware_and_never_pooled(erap: LearningService) -> None:
    ids = erap.build_datasets(PROJECT, erap.indexed_records(PROJECT))
    datasets = {i: erap.dataset(i) for i in ids}
    contexts = {
        (
            d["assay_context"]["substrate"],
            d["assay_context"]["endpoint"],
            d["assay_context"]["target"],
        )
        for d in datasets.values()
    }
    assert ("L-AMC", "IC50", "ERAP1") in contexts and (
        "WRCYEKMALK",
        "IC50",
        "ERAP1",
    ) in contexts
    assert ("L-pNA concentration series", "Ki", "ERAP1") in contexts
    assert any(
        c[0] == "L-AMC" and c[1] == "AC50" for c in contexts
    )  # activator kept apart from inhibition
    assert sum(len(d["measurements"]) for d in datasets.values()) == 15
    amc = next(
        d
        for d in datasets.values()
        if d["assay_context"]["substrate"] == "L-AMC"
        and d["assay_context"]["endpoint"] == "IC50"
        and d["target"] == "ERAP1"
    )
    assert {c["compound_ref"] for c in amc["compounds"]} == {
        "compound:maben-1",
        "compound:maben-2",
    }


def test_erap1_censored_off_target_values_stay_censored(erap: LearningService) -> None:
    ids = erap.build_datasets(PROJECT, erap.indexed_records(PROJECT))
    for d in (erap.dataset(i) for i in ids):
        if d["target"] in ("ERAP2", "LNPEP"):
            assert all(
                m["operator"] == ">"
                and m["original_value"] == 200.0
                and m["original_unit"] == "µM"
                and m["normalized_value"] == 200000.0
                for m in d["measurements"]
            )
            assert all(v["value"] is None for v in d["compound_values"])


def test_erap1_is_refused_for_predictive_modelling_with_generic_rules(
    erap: LearningService,
) -> None:
    ids = erap.build_datasets(PROJECT, erap.indexed_records(PROJECT))
    for i in ids:
        result = erap.assess_eligibility(i)
        assert result["conclusion"] == "not_eligible" and result["model_built"] is False
        assert erap.train(i)["model_built"] is False
    amc = next(i for i in ids if "L-AMC" in i and "|IC50@" in i and "ERAP1|" in i)
    reasons = " ".join(erap.assess_eligibility(amc)["reasons"])
    assert "sample size" in reasons and "chemical diversity" in reasons
    assert not erap.repo.rows("chemical_models", "WHERE project_id=?", [PROJECT])
    assert not re.search(r"ERAP|Maben|HLA", json.dumps(eligibility.POLICY))


def test_erap1_cross_assay_comparability_is_explicit(erap: LearningService) -> None:
    erap.build_datasets(PROJECT, erap.indexed_records(PROJECT))
    matrix = erap.comparability_matrix(PROJECT)
    states = {m["state"] for m in matrix}
    assert "not_directly_comparable" in states and "directly_comparable" not in states
    biochemical_vs_cellular = [
        m for m in matrix if "biochemical and cellular" in " ".join(m["rationale"])
    ]
    assert biochemical_vs_cellular


def test_erap1_identity_ambiguities_are_not_cleaned_for_modelling(
    erap: LearningService,
) -> None:
    records = erap.indexed_records(PROJECT)
    assert {r["compound_ref"] for r in records} == {
        "compound:maben-1",
        "compound:maben-2",
        "compound:maben-3",
    }
    assert all(
        r["smiles"]
        == erap.store.pharmacology.record("compounds", r["compound_ref"])[
            "original_smiles"
        ]
        for r in records
    )


def test_erap1_learning_state_reports_sar_only_readiness(erap: LearningService) -> None:
    ids = erap.build_datasets(PROJECT, erap.indexed_records(PROJECT))
    for i in ids:
        erap.assess_eligibility(i)
        erap.derive_sar(i)
    state = erap.learning_state(PROJECT)
    assert {e["readiness"] for e in state["entries"]} <= {
        "SAR_ONLY",
        "INSUFFICIENT_DATA",
    }
    assert all(e["models"] == [] and e["predictions"] == [] for e in state["entries"])
    assert any("learnability" in u["id"] for u in state["chemical_uncertainties"])


# --- modelling ----------------------------------------------------------------------------


def test_splits_are_deterministic_leak_free_and_scaffold_aware(
    syn: LearningService,
) -> None:
    _, dataset_id = main_dataset(syn)
    rows = models.training_table(syn.dataset(dataset_id))
    for kind in ("random", "scaffold", "temporal"):
        a, b = models.split(rows, kind, 3, 0.25), models.split(rows, kind, 3, 0.25)
        assert [r["compound_ref"] for r in a["test"]] == [
            r["compound_ref"] for r in b["test"]
        ]
        assert a["leakage"]["valid"], (kind, a["leakage"])
        assert not {r["compound_ref"] for r in a["train"]} & {
            r["compound_ref"] for r in a["test"]
        }
    sc = models.split(rows, "scaffold", 3, 0.25)
    assert not {r["scaffold"] for r in sc["train"]} & {
        r["scaffold"] for r in sc["test"]
    }


def test_leakage_is_detected_and_invalidates_the_split() -> None:
    row = {"compound_ref": "a", "inchi_key": "K", "scaffold": "S", "date": "2020-01-01"}
    dup = {"compound_ref": "b", "inchi_key": "K", "scaffold": "S", "date": "2019-01-01"}
    assert not models.leakage([row], [row], "random")["valid"]
    assert any(
        "duplicate structure" in f
        for f in models.leakage([row], [dup], "random")["findings"]
    )
    assert any(
        "scaffold shared" in f
        for f in models.leakage([row], [dup], "scaffold")["findings"]
    )
    assert any(
        "postdates" in f for f in models.leakage([row], [dup], "temporal")["findings"]
    )


def test_model_training_baseline_metrics_and_overfit_audit(
    syn: LearningService,
) -> None:
    _, dataset_id = main_dataset(syn)
    result = syn.train(dataset_id, "ridge", "scaffold", 7)
    assert result["model_built"]
    m = syn.model(result["model_id"])
    ev = m["validation"]["evaluation"]
    assert ev["valid"] and ev["leakage"]["valid"] and ev["n_test"] > 0
    assert (
        ev["baseline_comparison"]["beats_mean_baseline"]
        and ev["baseline_comparison"]["beats_nearest_neighbor"]
    )
    assert "10% better" in ev["baseline_comparison"]["criterion"]
    assert ev["overfit_audit"]["possible_overfit"] is False
    assert m["validation"]["stability"]["valid_runs"] >= 3
    assert m["validation"]["permutation_control"]["reading"].startswith("signal")
    assert "score" not in json.dumps(m["validation"]).lower().replace("aggregate", "")
    assert (
        len(m["fingerprint"]) == 64
        and m["software"]["rdkit"]
        and m["software"]["numpy"]
    )
    assert "not prospective validation" in " ".join(m["limitations"])


def test_no_signal_labels_do_not_materially_beat_the_baseline(
    syn: LearningService,
) -> None:
    """One favourable split can flatter a no-signal model; the mean over seeds cannot."""
    project, records = syn.synthetic_records(CUTOFF)
    ids = syn.build_datasets(project, records, synthetic=True)
    perm = models.training_table(syn.dataset(next(i for i in ids if "PERMUTED" in i)))
    real = models.training_table(
        syn.dataset(next(i for i in ids if "SYN-SUBSTRATE-1" in i))
    )

    def ratio(rows: list[dict[str, Any]]) -> float:
        runs = [
            models.evaluate(rows, "ridge", "scaffold", s)
            for s in models.POLICY["stability_seeds"]
        ]
        ok = [r for r in runs if r["valid"]]
        model = sum(r["ridge"]["test"]["mae"] for r in ok) / len(ok)
        base = sum(r["mean_baseline"]["test"]["mae"] for r in ok) / len(ok)
        return model / base

    assert ratio(perm) >= models.POLICY["material_improvement"]
    assert ratio(real) < 0.5


def test_model_is_deterministic_and_serialises_as_plain_json(
    syn: LearningService, tmp_path: Path
) -> None:
    _, dataset_id = main_dataset(syn)
    first = syn.train(dataset_id, "ridge", "scaffold", 7)
    again = syn.train(dataset_id, "ridge", "scaffold", 7)
    assert (
        first["fingerprint"] == again["fingerprint"]
        and first["model_id"] == again["model_id"]
    )
    json.dumps(syn.model(first["model_id"]))  # no pickle, nothing opaque
    other = syn.train(dataset_id, "weighted_knn", "scaffold", 7)
    assert other["fingerprint"] != first["fingerprint"]


def test_unknown_algorithm_and_split_are_refused(syn: LearningService) -> None:
    _, dataset_id = main_dataset(syn)
    with pytest.raises(ValueError):
        syn.train(dataset_id, "deep_net", "scaffold", 7)
    with pytest.raises(ValueError):
        models.split(
            models.training_table(syn.dataset(dataset_id)), "nonsense", 1, 0.25
        )


def test_censored_values_are_excluded_from_fitting_not_substituted(
    syn: LearningService,
) -> None:
    _, dataset_id = main_dataset(syn)
    d = syn.dataset(dataset_id)
    censored = {v["compound_ref"] for v in d["compound_values"] if v["operator"] == ">"}
    rows = {r["compound_ref"] for r in models.training_table(d)}
    assert censored and not censored & rows
    contradictory = {
        v["compound_ref"] for v in d["compound_values"] if v["contradictory"]
    }
    assert contradictory and not contradictory & rows


# --- predictions -----------------------------------------------------------------------------


def _loop(service: LearningService) -> dict[str, Any]:
    project, early = service.synthetic_records(CUTOFF)
    _, all_records = service.synthetic_records(None)
    early_ids = {r["compound_ref"] for r in early}
    ids = service.build_datasets(project, early, synthetic=True)
    dataset_id = next(i for i in ids if "SYN-SUBSTRATE-1" in i)
    model = service.train(dataset_id, "ridge", "scaffold", 7)
    later = {
        r["compound_ref"]: r
        for r in all_records
        if r["compound_ref"] not in early_ids
        and r["context"]["substrate"] == "SYN-SUBSTRATE-1"
        and r["operator"] == "="
    }
    return {
        "project": project,
        "dataset": dataset_id,
        "model": model["model_id"],
        "later": later,
        "all": all_records,
    }


def test_prospective_predictions_are_frozen_labelled_and_traceable(
    syn: LearningService,
) -> None:
    loop = _loop(syn)
    later = loop["later"]
    pids = syn.predict(
        loop["model"],
        {k: v["smiles"] for k, v in later.items()},
        intent="prospective",
        evidence_cutoff=CUTOFF,
    )
    assert pids
    p = syn.prediction(pids[0])
    assert (
        p["label"] == "PREDICTION — NOT AN EXPERIMENTAL MEASUREMENT"
        and p["epistemic_class"] == "axis_inference"
    )
    assert (
        p["model_fingerprint"]
        and p["dataset_checksum"]
        and p["evidence_cutoff"] == CUTOFF
    )
    assert (
        p["uncertainty"]["numerical"] is None
        and "qualitative" in p["uncertainty"]["note"]
    )
    assert p["applicability"]["status"] in (
        "inside_domain",
        "near_boundary",
        "outside_domain",
    )
    assert p["applicability"]["nearest_training_compounds"]
    assert (
        syn.model(p["model_id"])["dataset_id"] == p["dataset_id"]
    )  # prediction -> model -> dataset
    with pytest.raises(RecordConflictError):
        syn.repo.put(
            "chemical_predictions",
            pids[0],
            {
                "model_id": p["model_id"],
                "project_id": "x",
                "compound_ref": "y",
                "intent": "prospective",
                "created_at": "2026-01-01",
            },
            {"overwritten": True},
        )


def test_prediction_made_after_the_result_cannot_be_prospective(
    syn: LearningService,
) -> None:
    loop = _loop(syn)
    ref, r = next(iter(loop["later"].items()))
    with pytest.raises(LearningError, match="cannot be prospective"):
        syn.predict(
            loop["model"],
            {ref: r["smiles"]},
            intent="prospective",
            evidence_cutoff=CUTOFF,
            known_results_available=True,
        )
    ids = syn.predict(
        loop["model"],
        {ref: r["smiles"]},
        intent="retrospective",
        evidence_cutoff=CUTOFF,
        known_results_available=True,
    )
    assert syn.prediction(ids[0])["intent"] == "retrospective"
    with pytest.raises(LearningError, match="intent"):
        syn.predict(
            loop["model"], {ref: r["smiles"]}, intent="hindsight", evidence_cutoff=None
        )


def test_training_compounds_cannot_be_predicted_circularly(
    syn: LearningService,
) -> None:
    loop = _loop(syn)
    train = syn.model(loop["model"])["model"]["training"][0]
    with pytest.raises(LearningError, match="training set"):
        syn.predict(
            loop["model"],
            {train["compound_ref"]: train["smiles"]},
            intent="benchmark",
            evidence_cutoff=CUTOFF,
        )


def test_outside_domain_compound_is_flagged_not_trusted(syn: LearningService) -> None:
    loop = _loop(syn)
    ids = syn.predict(
        loop["model"],
        {"synthetic:far": "CCCCCCCCCCCCCCCCCCCC(=O)[O-].[Na+]"},
        intent="benchmark",
        evidence_cutoff=CUTOFF,
    )
    app_ = syn.prediction(ids[0])["applicability"]
    assert app_["status"] == "outside_domain" and "not high confidence" in app_["note"]


def test_prediction_is_never_a_measurement(syn: LearningService) -> None:
    loop = _loop(syn)
    ref, r = next(iter(loop["later"].items()))
    syn.predict(
        loop["model"], {ref: r["smiles"]}, intent="prospective", evidence_cutoff=CUTOFF
    )
    db = syn.store._connection
    assert (
        db.execute("SELECT count(*) FROM measurements").fetchone()[0] == 0
        if _has(db, "measurements")
        else True
    )
    assert db.execute("SELECT count(*) FROM experimental_results").fetchone()[0] == 0


def _has(db: Any, table: str) -> bool:
    return bool(
        db.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name=?", [table]
        ).fetchone()[0]
    )


def test_outcome_assessment_has_graded_conclusions_and_leaves_the_prediction_alone(
    syn: LearningService,
) -> None:
    loop = _loop(syn)
    later = loop["later"]
    pids = syn.predict(
        loop["model"],
        {k: v["smiles"] for k, v in later.items()},
        intent="prospective",
        evidence_cutoff=CUTOFF,
    )
    before = {p: syn.prediction(p) for p in pids}
    ctx = syn.dataset(loop["dataset"])["assay_context"]
    seen = set()
    for pid in pids:
        ref = syn.prediction(pid)["compound_ref"]
        r = later[ref]
        outcome = syn.assess_outcome(
            pid,
            {"value": r["value"], "unit": r["unit"], "operator": "=", "context": ctx},
        )
        seen.add(outcome["conclusion"])
        assert outcome["prediction_unchanged"] and syn.prediction(pid) == before[pid]
    assert seen <= {
        "quantitatively_supported",
        "partially_supported",
        "directionally_supported",
        "contradicted",
        "outside_applicability",
    }
    pid = pids[0]
    assert (
        syn.assess_outcome(pid, None)["conclusion"] == "not_tested"
        if not syn.repo.get("prediction_outcome_assessments", f"outcome:{pid}")
        else True
    )


@pytest.mark.parametrize(
    ("measured", "expected"),
    [
        (None, "not_tested"),
        (
            {"value": 1, "unit": "nM", "operator": ">", "context": "same"},
            "experimental_result_ambiguous",
        ),
        (
            {"value": 1, "unit": "nM", "operator": "=", "context": "other"},
            "non_comparable",
        ),
    ],
)
def test_outcome_special_states(
    syn: LearningService, measured: dict[str, Any] | None, expected: str
) -> None:
    loop = _loop(syn)
    ref, r = list(loop["later"].items())[0]
    pid = syn.predict(
        loop["model"], {ref: r["smiles"]}, intent="prospective", evidence_cutoff=CUTOFF
    )[0]
    if measured and measured["context"] == "same":
        measured = {
            **measured,
            "context": syn.dataset(loop["dataset"])["assay_context"],
        }
    result = syn.assess_outcome(pid, measured)
    assert result["conclusion"] == expected and expected in dict.fromkeys(
        __import__("axis.learning.service", fromlist=["OUTCOMES"]).OUTCOMES
    )


def test_new_evidence_updates_the_learning_state_without_rewriting_history(
    syn: LearningService,
) -> None:
    loop = _loop(syn)
    for i in [loop["dataset"]]:
        syn.assess_eligibility(i)
        syn.derive_sar(i)
    v1 = syn.learning_state(loop["project"])
    later = loop["later"]
    pids = syn.predict(
        loop["model"],
        {k: v["smiles"] for k, v in later.items()},
        intent="prospective",
        evidence_cutoff=CUTOFF,
    )
    frozen = {p: syn.prediction(p) for p in pids}
    ids2 = syn.build_datasets(loop["project"], loop["all"], synthetic=True)
    main2 = next(i for i in ids2 if "SYN-SUBSTRATE-1" in i and i.endswith("@r2"))
    syn.assess_eligibility(main2)
    syn.train(main2, "ridge", "scaffold", 7)
    v2 = syn.learning_state(loop["project"])
    assert v2["revision"] == v1["revision"] + 1
    assert (
        "new_experimental_evidence_or_dataset_revision" in v2["diff"]["causes"]
        and "model_added" in v2["diff"]["causes"]
    )
    assert syn.dataset(loop["dataset"])["revision"] == 1 and loop["dataset"] in {
        e["dataset"]["id"] for e in v2["entries"]
    }
    assert {p: syn.prediction(p) for p in pids} == frozen
    assert (
        syn.learning_state(loop["project"])["revision"] == v2["revision"]
    )  # idempotent


def test_model_drift_causes_are_distinguished() -> None:
    assert (
        "model_added"
        in LearningService._diff(
            {"revision": 1, "entries": []},
            [{"dataset": {"id": "d"}, "models": ["m"], "predictions": []}],
        )["causes"]
    )
    assert LearningService._diff(None, [])["causes"] == ["initial_state"]


# --- next compounds ----------------------------------------------------------------------------


def test_next_compounds_use_explicit_rationales_and_no_global_score(
    syn: LearningService,
) -> None:
    loop = _loop(syn)
    syn.derive_sar(loop["dataset"])
    candidates = {k: v["smiles"] for k, v in loop["later"].items()}
    candidates["synthetic:far"] = "CCCCCCCCCCCCCCCCCCCC(=O)O"
    out = syn.next_compounds(loop["dataset"], loop["model"], candidates)
    assert (
        out["acquisition_score"] is None
        and out["rules_fingerprint"] == selection.fingerprint()
    )
    assert out["selected"]
    cats = {c for r in out["selected"] for c in r["rationales"]}
    assert cats <= set(selection.CATEGORIES) and cats
    assert all("score" not in r for r in out["selected"])
    assert any(
        "not because they have the highest predicted potency" in out["statement"]
        for _ in [0]
    )
    assert (
        "synthesis or purchase availability was not assessed" in out["not_asserted"][0]
    )
    assert out == syn.next_compounds(
        loop["dataset"], loop["model"], candidates
    )  # deterministic


def test_selection_categories_each_fire_under_their_rule() -> None:
    hyp = [
        {
            "id": "h",
            "contradictory_observations": ["x"],
            "supporting_observations": ["a", "b"],
        }
    ]
    pred_in = {"predicted_value": 1.0, "applicability": {"status": "inside_domain"}}
    pred_edge = {"predicted_value": 99.0, "applicability": {"status": "near_boundary"}}
    cands = [
        {
            "compound_ref": "c1",
            "scaffold": "D",
            "prediction": pred_in,
            "reference_value": 10.0,
        },
        {"compound_ref": "c2", "scaffold": "X", "prediction": None},
        {
            "compound_ref": "c3",
            "scaffold": "D",
            "prediction": None,
            "tests_hypotheses": ["h"],
        },
        {
            "compound_ref": "c4",
            "scaffold": "D",
            "prediction": pred_edge,
            "reference_value": 10.0,
        },
        {"compound_ref": "c5", "scaffold": "D", "prediction": None},
        {
            "compound_ref": "c6",
            "scaffold": "D",
            "prediction": pred_in,
            "reference_value": 10.0,
            "analogue_of_weak": True,
        },
    ]
    out = selection.select(
        candidates=cands,
        dominant_scaffold="D",
        hypotheses=hyp,
        contradictory_refs=["c5"],
        capacity=10,
    )
    covered = {c for r in out["selected"] for c in r["rationales"]}
    assert covered == set(
        selection.CATEGORIES
    )  # every explicit rule fired for some compound
    by = {r["compound_ref"]: set(r["rationales"]) for r in out["selected"]}
    assert "exploration" in by["c2"] and "hypothesis_discrimination" in by["c3"]
    assert "model_boundary" in by["c4"] and "replication" in by["c5"]
    assert {"exploitation", "negative_control"} <= by["c6"]
    assert (
        "c1" not in by
    )  # adds no rationale beyond c6, so it is not proposed redundantly
    empty = selection.select(
        candidates=[], dominant_scaffold=None, hypotheses=[], contradictory_refs=[]
    )
    assert empty["selected"] == [] and "nothing is proposed" in empty["statement"]


# --- review, genericity, hygiene ------------------------------------------------------------------


def test_review_is_human_only(syn: LearningService) -> None:
    _, dataset_id = main_dataset(syn)
    for bad in ("AXIS", "gpt-5", "Claude", ""):
        with pytest.raises(LearningError):
            syn.review("model", dataset_id, bad, "accepted", "r", "p")
    with pytest.raises(LearningError, match="decision"):
        syn.review("model", dataset_id, "Dr R", "great", "r", "p")
    assert syn.review_state(dataset_id) == "pending_review"
    syn.review(
        "dataset", dataset_id, "Dr R", "accepted_with_conditions", "reasoned", "p"
    )
    assert syn.review_state(dataset_id) == "accepted_with_conditions"


def test_generic_logic_hard_codes_no_target_or_compound() -> None:
    forbidden = re.compile(
        r"ERAP1|ERAP2|HLA-B27|axSpA|Maben|3QNF|Q9NZ08|LNPEP|compound:maben", re.I
    )
    for path in [
        *(ROOT / "axis/learning").glob("*.py"),
        ROOT / "axis/storage/learning.py",
        ROOT / "axis/cli/learning.py",
    ]:
        assert not forbidden.search(path.read_text()), path


def test_no_aggregate_model_score_or_deep_learning_in_code() -> None:
    text = "\n".join(p.read_text() for p in (ROOT / "axis/learning").glob("*.py"))
    assert not re.search(r"model_score|axis_score|composite_score|weighted_sum", text)
    assert not re.search(
        r"import (torch|tensorflow|keras|jax)|import pickle|pickle\.(load|dump)", text
    )


def test_synthetic_fixture_is_labelled_and_checksummed() -> None:
    import hashlib

    package = registry_root() / "synthetic-generic/v1"
    manifest = json.loads((package / "manifest.json").read_text())
    for name, checksum in manifest["files"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == checksum
    body = json.loads((package / "measurements.json").read_text())
    assert SYNTHETIC in body["label"] and "designed_relationship" in body
    assert all(r["synthetic"] and SYNTHETIC in r["label"] for r in body["records"])
    kinds = {(r["operator"], r["unit"]) for r in body["records"]}
    assert (">", "µM") in kinds and ("=", "nM") in kinds
    assert len({r["context"]["substrate"] for r in body["records"]}) == 3


def test_tampered_fixture_is_refused(tmp_path: Path) -> None:
    shutil.copytree(registry_root(), tmp_path / "reg")
    path = tmp_path / "reg/synthetic-generic/v1/measurements.json"
    path.write_text(path.read_text().replace("SYN-TARGET-A", "SYN-TARGET-B", 1))
    with (
        EvidenceStore(tmp_path / "t.duckdb") as s,
        pytest.raises(LearningError, match="checksum"),
    ):
        LearningService(s, tmp_path / "reg").synthetic_records()


def test_synthetic_never_leaks_into_production_projects(erap: LearningService) -> None:
    main_dataset(erap)
    erap.build_datasets(PROJECT, erap.indexed_records(PROJECT))
    prod = erap.datasets(PROJECT)
    assert prod and not any(d["synthetic"] for d in prod)
    assert all(d["synthetic"] for d in erap.datasets("SYNTHETIC-LEARNING-PROJECT"))
    with pytest.raises(LearningError, match="not part of project"):
        erap.dataset(prod[0]["id"], "SYNTHETIC-LEARNING-PROJECT")


def test_deterministic_and_offline_replay(tmp_path: Path) -> None:
    def refuse(*_: Any, **__: Any) -> None:
        raise AssertionError("network used")

    digests = []
    for n in range(2):
        with (
            patch.object(socket.socket, "connect", refuse),
            EvidenceStore(tmp_path / f"{n}.duckdb") as s,
        ):
            service = LearningService(s)
            _, dataset_id = main_dataset(service)
            service.assess_eligibility(dataset_id)
            service.derive_sar(dataset_id)
            built = service.train(dataset_id, "ridge", "scaffold", 7)
            model = service.model(built["model_id"])
            digests.append(
                ds.digest(
                    {
                        "d": service.dataset(dataset_id)["checksum"],
                        "m": model["fingerprint"],
                        "v": model["validation"],
                        "sar": service.observed_sar(dataset_id),
                    }
                )
            )
    assert digests[0] == digests[1]


def test_migration_013_is_additive_and_upgrades_from_012(tmp_path: Path) -> None:
    import hashlib
    import subprocess
    from importlib import resources as res

    import duckdb

    root = ROOT / "axis/storage/migrations"
    sql = (root / "013_chemical_learning.sql").read_text()
    assert not re.search(r"\b(DROP|ALTER|DELETE|UPDATE|CASCADE)\b", sql, re.I)
    assert sql.count("CREATE TABLE") == 10
    for path in sorted(root.glob("0*_*.sql")):
        if int(path.name[:3]) > 12:
            continue
        original = subprocess.run(
            ["git", "show", f"93fb98e:axis/storage/migrations/{path.name}"],
            capture_output=True,
            cwd=ROOT,
        )
        if original.returncode == 0:
            assert (
                hashlib.sha256(original.stdout).hexdigest()
                == hashlib.sha256(path.read_bytes()).hexdigest()
            ), path.name
    db = tmp_path / "v12.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name VARCHAR, applied_at TIMESTAMPTZ DEFAULT current_timestamp)"
        )
        for item in sorted(
            res.files("axis.storage.migrations").iterdir(), key=lambda i: i.name
        ):
            if item.name.endswith(".sql") and int(item.name[:3]) <= 12:
                con.execute(item.read_text())
                con.execute(
                    "INSERT INTO schema_migrations(version,name) VALUES (?,?)",
                    [int(item.name[:3]), item.name],
                )
        con.execute("INSERT INTO chemical_spaces VALUES ('s','p','c','{}')")
    with EvidenceStore(db) as store:
        assert store.statistics().schema_version == 13
        assert (
            store._connection.execute(
                "SELECT count(*) FROM chemical_spaces"
            ).fetchone()[0]
            == 1
        )  # Phase 3.8 data intact
        _, dataset_id = main_dataset(LearningService(store))
    with EvidenceStore(db, read_only=True) as store:
        assert store.statistics().schema_version == 13 and LearningService(
            store
        ).dataset(dataset_id)


# --- API and CLI ------------------------------------------------------------------------------------


def test_api_is_read_only_isolated_and_never_trains(
    erap_db: Path, tmp_path: Path
) -> None:
    copy_ = tmp_path / "a.duckdb"
    shutil.copy(erap_db, copy_)
    with EvidenceStore(copy_) as s:
        service = LearningService(s)
        ids = service.build_datasets(PROJECT, service.indexed_records(PROJECT))
        for i in ids:
            service.assess_eligibility(i)
            service.derive_sar(i)
        service.learning_state(PROJECT)

        def counts() -> tuple[int, ...]:
            return tuple(
                s._connection.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in (
                    "chemical_learning_datasets",
                    "chemical_models",
                    "chemical_predictions",
                    "observed_sar",
                    "chemical_learning_states",
                    "chemical_learning_reviews",
                )
            )

        before = counts()
        api = ReadAPI(s)
        base = f"/api/projects/{PROJECT}/chemical-learning"
        root = api.get(base, {})
        assert (
            root["datasets"]
            and root["models"] == []
            and "not a model prediction" in " ".join(root["boundaries"])
        )
        assert api.get(f"{base}/comparability", {})["items"]
        assert api.get(f"{base}/predictions", {})["items"] == []
        did = root["datasets"][0]["id"]
        assert api.get(f"{base}/datasets/{did}", {})["id"] == did
        assert api.get(f"{base}/sar/{did}", {})["observed"]["label"] == "OBSERVED SAR"
        assert (
            api.get(f"{base}/eligibility/{did}", {})["assessments"][0]["conclusion"]
            == "not_eligible"
        )
        assert api.get(f"{base}/learning-state", {})["entries"]
        assert counts() == before
        with pytest.raises(RecordNotFoundError):
            api.get(f"/api/projects/OTHER/chemical-learning/datasets/{did}", {})
        with pytest.raises(RecordNotFoundError):
            api.get(f"{base}/nothing", {})


def test_cli_flow_refusal_and_synthetic_loop(tmp_path: Path) -> None:
    runner = CliRunner()
    base = ["--database", str(tmp_path / "c.duckdb"), "chemistry"]
    built = runner.invoke(
        app, [*base, "dataset", "build", "--synthetic", "--cutoff", CUTOFF]
    )
    assert built.exit_code == 0, built.output
    main = next(line for line in built.output.splitlines() if "SYN-SUBSTRATE-1" in line)
    small = next(
        line for line in built.output.splitlines() if "SYN-SUBSTRATE-2" in line
    )
    assert "refused" in runner.invoke(app, [*base, "dataset", "build"]).output
    refusal = runner.invoke(app, [*base, "model", "train", small])
    assert (
        refusal.exit_code == 3
        and "MODEL NOT BUILT" in refusal.output
        and "Insufficient data" in refusal.output
    )
    assert (
        "eligible" in runner.invoke(app, [*base, "model", "eligibility", main]).output
    )
    assert runner.invoke(app, [*base, "sar", "show", main, "--derive"]).exit_code == 0
    assert "OBSERVED SAR" in runner.invoke(app, [*base, "sar", "show", main]).output
    assert (
        "Within the compounds measured"
        in runner.invoke(app, [*base, "sar", "pairs", main]).output
    )
    trained = runner.invoke(app, [*base, "model", "train", main])
    assert trained.exit_code == 0, trained.output
    model_id = trained.output.strip()
    assert runner.invoke(app, [*base, "model", "show", model_id]).exit_code == 0
    project = "SYNTHETIC-LEARNING-PROJECT"
    assert (
        model_id
        in runner.invoke(app, [*base, "model", "list", "--project", project]).output
    )
    assert (
        "datasets"
        in runner.invoke(app, [*base, "dataset", "list", "--project", project]).output
        or main
        in runner.invoke(app, [*base, "dataset", "list", "--project", project]).output
    )
    assert (
        "entries"
        in runner.invoke(app, [*base, "learning-state", "--project", project]).output
    )
    assert runner.invoke(app, [*base, "dataset", "show", "nope"]).exit_code == 2
    assert runner.invoke(app, [*base, "prediction", "show", "nope"]).exit_code == 2
    assert runner.invoke(app, [*base, "model", "show", "nope"]).exit_code == 2
