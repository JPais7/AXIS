"""Phase 3.8: computational discovery campaigns.

Synthetic fixtures are SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE. The ERAP1
campaign is a computational prioritization for experimental validation only.
"""

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
from axis.computational import chem, docking, prioritize, structure
from axis.computational.service import (
    CampaignError,
    CampaignService,
    digest,
    registry_root,
)
from axis.decision.service import DecisionService
from axis.discovery.curation import import_curated_erap1
from axis.pharmacology.service import PharmacologyService
from axis.storage import EvidenceStore, RecordConflictError, RecordNotFoundError
from axis.structures.service import StructureIdentityService
from axis.targets.identity import TargetIdentityService

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "AXIS-DD-ERAP1-CURATED-001"
ERAP = "campaign:erap1:bounded-chemistry-v1"
SYN = "campaign:synthetic:generic-v1"
CIF = ROOT / "axis/resources/structures/erap1/3qnf/v1/structure.cif"
SYNTHETIC = "SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE"


@pytest.fixture(scope="module")
def erap_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("c38") / "erap.duckdb"
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
    copy = tmp_path / "e.duckdb"
    shutil.copy(erap_db, copy)
    with EvidenceStore(copy) as s:
        yield CampaignService(s)


@pytest.fixture
def syn(tmp_path: Path) -> Any:
    with EvidenceStore(tmp_path / "s.duckdb") as s:
        yield CampaignService(s)


def finish(service: CampaignService, package: str) -> str:
    cid = service.register(package)
    service.prepare(cid)
    service.run(cid)
    return cid


# --- compound preparation and identity ----------------------------------------


def test_prepared_compound_never_changes_identity_or_smiles() -> None:
    p = chem.prepare_compound(
        "c",
        "CC(=O)Nc1ccc(O)cc1",
        compound_identity="compound:x",
        input_stereo="not_applicable",
    )
    assert (
        p["compound_identity"] == "compound:x"
        and p["input_smiles"] == "CC(=O)Nc1ccc(O)cc1"
    )
    assert "stereochemistry assignment" in p["operations_not_performed"]
    assert p["tool_version"] == chem.rdkit_version()


def test_unspecified_stereo_stays_unspecified_and_salts_are_kept() -> None:
    p = chem.prepare_compound(
        "c", "CC(N)C(=O)O.Cl", compound_identity=None, input_stereo=None
    )
    assert p["stereochemistry"]["status"] == "unspecified"
    assert p["fragments"] == 2
    assert any("none was chosen" in w for w in p["warnings"])
    assert any("multiple fragments" in w for w in p["warnings"])
    assert "@" not in p["canonical_smiles"]


def test_unparseable_compound_fails_without_output() -> None:
    p = chem.prepare_compound(
        "c", "not-a-smiles", compound_identity=None, input_stereo=None
    )
    assert p["status"] == "failed" and "canonical_smiles" not in p


def test_descriptors_are_descriptive_flags_never_rejection() -> None:
    values = chem.descriptors("CCCCCCCCCCCCCCCCCCCC(=O)O")
    flags = chem.descriptor_flags(values, {"rotatable_bonds": [None, 5]})
    assert flags and flags[0]["descriptor"] == "rotatable_bonds"


def test_similarity_records_fingerprint_and_is_symmetric() -> None:
    assert chem.similarity("CCO", "CCO") == 1.0
    assert chem.similarity("CCO", "c1ccccc1") == chem.similarity("c1ccccc1", "CCO")
    assert chem.FINGERPRINT["radius"] == 2 and chem.METRIC == "tanimoto"


def test_clustering_is_deterministic() -> None:
    members = {"a": "CCO", "b": "CCCO", "c": "c1ccccc1", "d": "c1ccccc1C"}
    assert chem.cluster(members, 0.6) == chem.cluster(
        dict(reversed(members.items())), 0.6
    )


# --- structure provenance --------------------------------------------------------


def test_prepared_structure_traces_to_source_checksum_and_records_every_choice() -> (
    None
):
    p = structure.prepare_structure(CIF, source_structure_id="PDB:3QNF", chain="A")
    assert p["source_sha256"] == structure.sha256_file(CIF)
    assert p["retained_components"] == {"ZN": 1}
    assert p["waters"] == "removed" and p["hydrogens"] == "not added"
    assert "coordination not modelled" in p["metals"]
    assert p["removed_components"]["HOH"] > 0
    assert any("redocking" in x for x in p["limitations"])


def test_wrong_source_checksum_or_chain_is_refused() -> None:
    with pytest.raises(ValueError, match="checksum"):
        structure.prepare_structure(
            CIF, source_structure_id="x", chain="A", expected_sha256="0" * 64
        )
    with pytest.raises(ValueError, match="chain"):
        structure.prepare_structure(CIF, source_structure_id="x", chain="Z")


def test_site_is_a_defined_region_not_a_druggable_pocket() -> None:
    site = structure.define_site(CIF, chain="A", around="ZN", radius=8.0, site_id="s")
    assert site["status"] == "defined" and site["residues"]
    assert "not a druggable pocket" in site["druggability"]
    assert "AXIS choice" in site["type_note"]


# --- campaign flow: ERAP1 ---------------------------------------------------------


def test_erap1_campaign_end_to_end_and_no_aggregate_score(
    erap: CampaignService,
) -> None:
    cid = finish(erap, "erap1")
    view = erap.view(cid)
    prio = view["prioritization"]
    assert view["campaign"]["status"] == "completed" and prio["outcome"] == "panel"
    assert prio["aggregate_score"] is None
    assert not re.search(
        r"\bscore\b",
        json.dumps([e["dimensions"] for e in prio["panel"]])
        .lower()
        .replace("aggregate_score", ""),
    )
    assert {e["role"] for e in prio["panel"]} == {"exploration"}
    assert any("exploitation role is empty" in s for s in prio["statements"])
    assert "hypothesis:erap1:maben-series-analog" in prio["untested_hypotheses"]


def test_erap1_identities_structure_and_zinc_are_preserved(
    erap: CampaignService,
) -> None:
    cid = finish(erap, "erap1")
    view = erap.view(cid)
    ps = view["prepared_structure"]
    assert ps["source_structure_id"] == "PDB:3QNF" and ps["chain"] == "A"
    assert (
        ps["retained_components"] == {"ZN": 1}
        and "coordination not modelled" in ps["metals"]
    )
    refs = {m["ref"]: m for m in view["chemical_space"]["members"]}
    store = erap.store
    for ref in ("compound:maben-1", "compound:maben-2", "compound:maben-3"):
        assert (
            refs[ref]["smiles"]
            == store.pharmacology.record("compounds", ref)["original_smiles"]
        )
        assert refs[ref]["compound_identity"] == ref
    text = json.dumps(view)
    assert (
        "CHEMBL" not in text
    )  # the rejected compound-2 ChEMBL mapping is never reintroduced


def test_erap1_does_not_claim_efficacy_engagement_or_disease_conformation(
    erap: CampaignService,
) -> None:
    cid = finish(erap, "erap1")
    report = erap.report(cid)
    low = report.lower()
    assert "requires external experimental validation" in low
    assert "not shown to be disease-relevant" in low
    for banned in (
        "active compound",
        "validated binder",
        "confirmed hit",
        "lead compound",
        "drug candidate",
    ):
        assert banned not in low.replace("nor a drug candidate", "").replace(
            "an active compound or a drug candidate", ""
        )
    assert "binds zinc" not in low and "forms a hydrogen bond" not in low


def test_known_chemistry_stays_separate_from_prediction(erap: CampaignService) -> None:
    prio = erap.view(finish(erap, "erap1"))["prioritization"]
    refs = {r["compound_ref"]: r["evidence"] for r in prio["reference_chemistry"]}
    assert set(refs) == {"compound:maben-1", "compound:maben-2", "compound:maben-3"}
    assert all(
        e["has_experimental_evidence"] and e["measurements"] > 0 for e in refs.values()
    )
    assert not {e["compound_ref"] for e in prio["panel"]} & set(refs)
    for e in prio["panel"]:
        assert (
            e["dimensions"]["known_experimental_evidence"]["has_experimental_evidence"]
            is False
        )
        assert e["dimensions"]["cellular_evidence"] == "none indexed"


def test_every_candidate_answers_the_audit_questions(erap: CampaignService) -> None:
    prio = erap.view(finish(erap, "erap1"))["prioritization"]
    for e in prio["panel"]:
        assert e["why_this_molecule"] and e["strongest_reason_against"]
        assert e["hypotheses_tested"] and e["what_would_change_our_mind"]
        pkg = e["experimental_package"]
        assert pkg["requires"].startswith("external experimental validation")
        assert pkg["outcomes"].keys() == {"positive", "negative", "non_interpretable"}
        assert "no experimentally supported inactive control" in pkg["negative_control"]
        assert pkg["decision_link"]["critical_uncertainty_id"]
        assert (
            e["epistemic_status"] == "ai_suggestion"
            and e["review_state"] == "pending_review"
        )


def test_decision_link_reads_the_current_decision_without_writing_state(
    erap: CampaignService,
) -> None:
    before = erap.store._connection.execute(
        "SELECT count(*) FROM decision_states"
    ).fetchone()[0]
    prio = erap.view(finish(erap, "erap1"))["prioritization"]
    link = prio["panel"][0]["experimental_package"]["decision_link"]
    assert link["critical_uncertainty_id"].startswith("uncertainty:")
    assert (
        erap.store._connection.execute(
            "SELECT count(*) FROM decision_states"
        ).fetchone()[0]
        == before
    )


def test_docking_is_not_executed_and_nothing_is_fabricated(
    erap: CampaignService,
) -> None:
    view = erap.view(finish(erap, "erap1"))
    dock = view["prioritization"]["docking"]
    assert dock["status"] == "not_executed"
    assert (
        "docking method validation not established" in " ".join(dock["reasons"]).lower()
    )
    assert "metal coordination" in " ".join(dock["reasons"])
    assert not [
        o
        for o in view["observations"]
        if o["method"] == "docking" and o["output"].get("poses")
    ]
    assert all(
        e["dimensions"]["docking"]["status"] == "not_executed"
        for e in view["prioritization"]["panel"]
    )


def test_project_isolation(erap: CampaignService) -> None:
    cid = finish(erap, "erap1")
    with pytest.raises(CampaignError, match="not part of project"):
        erap.view(cid, "OTHER-PROJECT")
    assert erap.list_campaigns("OTHER-PROJECT") == []


# --- generic synthetic campaign ----------------------------------------------------


def test_generic_synthetic_campaign_is_target_independent(syn: CampaignService) -> None:
    cid = finish(syn, "synthetic-generic")
    view = syn.view(cid)
    assert view["campaign"]["label"] == SYNTHETIC and view["campaign"]["synthetic"]
    prio = view["prioritization"]
    assert prio["outcome"] == "panel" and prio["failed_preparation"] == [
        "synthetic:cmpd-7"
    ]
    assert {e["role"] for e in prio["panel"]} == {"exploitation", "exploration"}
    text = json.dumps(view)
    assert "ERAP1" not in text and "Q9NZ08" not in text


def test_panel_is_diverse_and_deterministic(
    syn: CampaignService, tmp_path: Path
) -> None:
    prio = syn.view(finish(syn, "synthetic-generic"))["prioritization"]
    clusters = [e["cluster"] for e in prio["panel"]]
    assert len(clusters) == len(set(clusters))
    with EvidenceStore(tmp_path / "again.duckdb") as s2:
        again = CampaignService(s2).view(
            finish(CampaignService(s2), "synthetic-generic")
        )["prioritization"]
    assert [e["compound_ref"] for e in again["panel"]] == [
        e["compound_ref"] for e in prio["panel"]
    ]
    assert (
        again["rules_fingerprint"]
        == prio["rules_fingerprint"]
        == prioritize.fingerprint()
    )


def base_inputs() -> dict[str, Any]:
    members = [
        {"ref": "k", "smiles": "CCO", "name": "known", "hypothesis_ids": []},
        {"ref": "a", "smiles": "CCCO", "name": "a", "hypothesis_ids": ["h"]},
        {"ref": "b", "smiles": "CCCCO", "name": "b", "hypothesis_ids": ["h"]},
        {"ref": "c", "smiles": "c1ccccc1", "name": "c", "hypothesis_ids": ["h"]},
    ]
    usable = {m["ref"]: m["smiles"] for m in members}
    return {
        "members": members,
        "prepared": {r: {"status": "prepared"} for r in usable},
        "known": {"k": {"has_experimental_evidence": True, "summary": "x"}},
        "descriptors": {r: chem.descriptors(s) for r, s in usable.items()},
        "flags": {r: [] for r in usable},
        "similarities": {
            r: {"k": chem.similarity(usable[r], "CCO")} for r in usable if r != "k"
        },
        "clusters": chem.cluster(usable, 0.9),
        "scaffolds": {r: chem.scaffold(s) for r, s in usable.items()},
        "structure_available": False,
        "docking": {"status": "not_executed", "reasons": []},
        "constraints": {
            "exploit_threshold": 0.2,
            "panel": {"exploitation": 5, "exploration": 5, "per_cluster": 1},
        },
        "hypotheses": [{"id": "h", "statement": "s", "falsification": ["f"]}],
        "assay_options": ["assay"],
        "decision_link": None,
    }


def test_near_duplicates_are_not_selected_unless_configured() -> None:
    args = base_inputs()
    one = prioritize.prioritize(**args)
    assert len({e["cluster"] for e in one["panel"]}) == len(one["panel"])
    args["constraints"] = {
        **args["constraints"],
        "panel": {"exploitation": 5, "exploration": 5, "per_cluster": 5},
    }
    many = prioritize.prioritize(**args)
    assert len(many["panel"]) >= len(one["panel"])


def test_empty_space_and_all_failed_preparation_produce_no_candidates() -> None:
    args = base_inputs()
    empty = prioritize.prioritize(
        **{**args, "members": [], "prepared": {}, "clusters": {"clusters": []}}
    )
    assert (
        empty["outcome"] == "failed"
        and "chemical space empty" in empty["failure_states"]
    )
    assert empty["panel"] == []
    bad = prioritize.prioritize(
        **{**args, "prepared": {r: {"status": "failed"} for r in args["prepared"]}}
    )
    assert bad["outcome"] == "failed" and bad["panel"] == []


def test_structure_requirement_without_structure_fails_without_fake_candidates() -> (
    None
):
    args = base_inputs()
    args["constraints"] = {**args["constraints"], "require_structure": True}
    result = prioritize.prioritize(**args)
    assert (
        result["outcome"] == "failed"
        and "no usable structure" in result["failure_states"]
    )
    assert result["panel"] == []


def test_required_structural_compatibility_without_docking_selects_nothing() -> None:
    args = base_inputs()
    args["constraints"] = {
        **args["constraints"],
        "require_structural_compatibility": True,
    }
    result = prioritize.prioritize(**args)
    assert result["outcome"] == "failed" and result["panel"] == []


def test_no_candidate_is_a_valid_stated_outcome() -> None:
    args = base_inputs()
    args["members"] = [args["members"][0]]
    args["prepared"] = {"k": {"status": "prepared"}}
    args["clusters"] = chem.cluster({"k": "CCO"}, 0.9)
    result = prioritize.prioritize(**args)
    assert result["outcome"] == "no_candidate"
    assert any("insufficient evidence" in s for s in result["statements"])


def test_method_disagreement_is_shown_not_averaged() -> None:
    args = base_inputs()
    args["flags"] = {
        **args["flags"],
        **{r: [{"descriptor": "tpsa", "value": 1, "range": [None, 0]}] for r in "abc"},
    }
    result = prioritize.prioritize(**args)
    assert result["method_disagreements"]
    assert "aggregate_score" in result and result["aggregate_score"] is None


def test_rule_set_is_fingerprinted_and_documented() -> None:
    assert len(prioritize.fingerprint()) == 64 and prioritize.RULES_VERSION
    assert all(re.match(r"PRIO-\d{3}", k) for k in prioritize.RULES)
    with patch.dict(prioritize.RULES, {"PRIO-099": "changed"}):
        assert prioritize.fingerprint() != digest("x")


# --- observations, provenance, immutability ----------------------------------------


def test_observations_are_computational_never_experimental(
    syn: CampaignService,
) -> None:
    view = syn.view(finish(syn, "synthetic-generic"))
    assert view["observations"]
    for o in view["observations"]:
        assert o["epistemic_class"] == "axis_observation" and o["experimental"] is False
        assert "tool_version" in o and "parameters" in o
    sim = next(o for o in view["observations"] if o["method"] == "similarity")
    assert "not evidence of similar activity" in sim["interpretation_boundary"]


def test_experimental_class_is_refused_for_observations(syn: CampaignService) -> None:
    cid = syn.register("synthetic-generic")
    syn.prepare(cid)
    real = syn._observations

    def tainted(*a: Any, **k: Any) -> list[dict[str, Any]]:
        rows = real(*a, **k)
        rows[0]["epistemic_class"] = "experimental_result"
        return rows

    with (
        patch.object(syn, "_observations", tainted),
        pytest.raises(CampaignError, match="cannot be experimental"),
    ):
        syn.run(cid)
    assert syn.campaign(cid)["status"] == "prepared"


def test_provenance_chain_candidate_to_observation_to_source(
    erap: CampaignService,
) -> None:
    view = erap.view(finish(erap, "erap1"))
    ref = view["prioritization"]["panel"][0]["compound_ref"]
    obs = [o for o in view["observations"] if o["compound_ref"] == ref]
    assert {o["method"] for o in obs} >= {
        "descriptors",
        "similarity",
        "scaffold",
        "clustering",
    }
    prepared = [p for p in view["prepared_compounds"] if p["compound_ref"] == ref]
    assert prepared and prepared[0]["input_smiles"]
    assert view["campaign"]["prepared_structure_id"] == view["prepared_structure"]["id"]
    assert view["prepared_structure"]["source_sha256"] == structure.sha256_file(CIF)
    artifacts = erap.repo.rows(
        "campaign_artifacts", "WHERE campaign_id=?", [view["campaign"]["campaign_id"]]
    )
    assert artifacts[0]["sha256"] == digest(artifacts[0]["payload"]["content"])


def test_chemical_space_is_frozen_and_reproducible(syn: CampaignService) -> None:
    cid = syn.register("synthetic-generic")
    space = syn.repo.get("chemical_spaces", syn.campaign(cid)["space_id"])
    assert space is not None and space["size_after_filtering"] == 7
    assert syn.register("synthetic-generic") == cid  # idempotent
    members = syn.members(syn.campaign(cid)["space_id"])
    assert [m["ref"] for m in members] == sorted(m["ref"] for m in members)


def test_changed_plan_makes_a_new_revision_and_keeps_the_old(tmp_path: Path) -> None:
    root = tmp_path / "reg"
    shutil.copytree(registry_root() / "synthetic-generic", root / "synthetic-generic")
    with EvidenceStore(tmp_path / "r.duckdb") as store:
        service = CampaignService(store, root)
        first = service.register("synthetic-generic")
        plan_path = root / "synthetic-generic/v1/campaign-plan.json"
        plan = json.loads(plan_path.read_text())
        plan["constraints"]["panel"]["exploration"] = 1
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
        manifest_path = root / "synthetic-generic/v1/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        import hashlib

        manifest["files"]["campaign-plan.json"] = hashlib.sha256(
            plan_path.read_bytes()
        ).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        (root / "synthetic-generic/v1/manifest.sha256").write_text(
            hashlib.sha256(manifest_path.read_bytes()).hexdigest() + "\n"
        )
        second = service.register("synthetic-generic")
        assert first.endswith("@r1") and second.endswith("@r2")
        assert service.campaign(first)["constraints"]["panel"]["exploration"] == 2


def test_immutable_records_refuse_silent_change(syn: CampaignService) -> None:
    cid = finish(syn, "synthetic-generic")
    pid = f"prepared:{syn.campaign(cid)['space_id']}:synthetic:cmpd-1"
    with pytest.raises(RecordConflictError):
        syn.repo.put(
            "prepared_compounds",
            pid,
            {"project_id": "x", "compound_ref": "y", "output_sha256": ""},
            {"changed": True},
        )


def test_tampered_package_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "reg"
    shutil.copytree(registry_root() / "synthetic-generic", root / "synthetic-generic")
    plan = root / "synthetic-generic/v1/campaign-plan.json"
    plan.write_text(plan.read_text().replace("hydroxy", "x") + " ")
    with (
        EvidenceStore(tmp_path / "t.duckdb") as s,
        pytest.raises(CampaignError, match="checksum"),
    ):
        CampaignService(s, root).register("synthetic-generic")


def test_oversized_space_fails_safely(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "o.duckdb") as s:
        service = CampaignService(s)
        plan = service.plan_for("synthetic-generic")
        plan["space"]["members"] = plan["space"]["members"] * 200
        with (
            patch.object(service, "plan_for", return_value=plan),
            pytest.raises(CampaignError, match="bound"),
        ):
            service.register("synthetic-generic")


def test_state_machine_blocks_out_of_order_steps(syn: CampaignService) -> None:
    cid = syn.register("synthetic-generic")
    with pytest.raises(CampaignError, match="prepare it first"):
        syn.run(cid)
    syn.prepare(cid)
    syn.run(cid)
    with pytest.raises(CampaignError, match="preparation is closed"):
        syn.prepare(cid)


# --- review ---


def test_review_is_human_only_and_validated(syn: CampaignService) -> None:
    cid = finish(syn, "synthetic-generic")
    for bad in ("AXIS", "gpt-5", "Claude", ""):
        with pytest.raises(CampaignError):
            syn.review(cid, "panel", bad, "accepted", "r")
    with pytest.raises(CampaignError, match="conditions"):
        syn.review(cid, "panel", "Dr R", "accepted_with_conditions", "r")
    with pytest.raises(CampaignError, match="decision"):
        syn.review(cid, "panel", "Dr R", "pending_review", "r")
    rid = syn.review(
        cid, "panel", "Dr R", "accepted_with_conditions", "reasoned", "needs chemist"
    )
    assert syn.view(cid)["reviews"][0]["id"] == rid
    assert (
        syn.view(cid)["prioritization"]["panel"][0]["review_state"] == "pending_review"
    )


# --- docking orchestration (stub engine; test only) -----------------------------------


def _stub(tmp_path: Path, name: str, body: str) -> list[str]:
    """A portable stub engine: a Python script run by the current interpreter."""
    import sys

    script = tmp_path / f"{name}.py"
    script.write_text(body)
    return [sys.executable, str(script)]


def test_docking_runner_uses_argument_arrays_and_rejects_partial_output(
    tmp_path: Path,
) -> None:
    line = "print('REMARK VINA RESULT:  -7.1  0.0  0.0')\n"
    good = docking.run_engine(_stub(tmp_path, "ok", line), timeout=30, workdir=tmp_path)
    assert good["status"] == "completed" and good["poses"][0]["score_kcal_mol"] == -7.1
    failed = docking.run_engine(
        _stub(tmp_path, "bad", line + "raise SystemExit(3)\n"),
        timeout=30,
        workdir=tmp_path,
    )
    assert failed["status"] == "failed" and failed["poses"] == []
    missing = docking.run_engine(["/nonexistent/engine"], timeout=5, workdir=tmp_path)
    assert missing["status"] == "failed"
    garbage = docking.run_engine(
        _stub(tmp_path, "g", "print('REMARK VINA RESULT: nope')\n"),
        timeout=30,
        workdir=tmp_path,
    )
    assert garbage["poses"] == []
    slow = docking.run_engine(
        _stub(tmp_path, "slow", "import time\ntime.sleep(5)\n"),
        timeout=1,
        workdir=tmp_path,
    )
    assert slow["status"] == "failed" and "timeout" in slow["failure"]


def test_docking_boundaries_are_stated() -> None:
    assert any("not a binding affinity" in b for b in docking.BOUNDARIES)
    assert any("not an observed binding mode" in b for b in docking.BOUNDARIES)


# --- generic code, offline, surfaces ---


def test_generic_logic_hard_codes_no_target_or_compound() -> None:
    forbidden = re.compile(
        r"ERAP1|HLA-B27|axSpA|Maben|3QNF|Q9NZ08|bestatin|captopril", re.I
    )
    for path in (ROOT / "axis/computational").glob("*.py"):
        assert not forbidden.search(path.read_text()), path


def test_offline_deterministic_replay(tmp_path: Path) -> None:
    def refuse(*_: Any, **__: Any) -> None:
        raise AssertionError("network used")

    outputs = []
    for n in range(2):
        with (
            patch.object(socket.socket, "connect", refuse),
            EvidenceStore(tmp_path / f"{n}.duckdb") as s,
        ):
            service = CampaignService(s)
            view = service.view(finish(service, "synthetic-generic"))
            outputs.append(
                digest(
                    {
                        k: view["prioritization"][k]
                        for k in ("panel", "not_selected", "diversity", "statements")
                    }
                )
            )
    assert outputs[0] == outputs[1]


def test_migration_012_is_additive(syn: CampaignService) -> None:
    db = syn.store._connection
    versions = [
        r[0]
        for r in db.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    ]
    assert versions[-1] >= 12 and versions[:11] == list(range(1, 12))
    tables = {
        r[0]
        for r in db.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    assert {
        "chemical_hypotheses",
        "prepared_structures",
        "prepared_compounds",
        "chemical_spaces",
        "computational_campaigns",
        "computational_observations",
        "candidate_molecules",
        "candidate_prioritizations",
        "campaign_artifacts",
        "campaign_reviews",
    } <= tables


def test_api_is_read_only_and_project_isolated(erap_db: Path, tmp_path: Path) -> None:
    copy = tmp_path / "a.duckdb"
    shutil.copy(erap_db, copy)
    with EvidenceStore(copy) as s:
        cid = finish(CampaignService(s), "erap1")
    with EvidenceStore(copy, read_only=True) as s:
        api = ReadAPI(s)
        base = f"/api/projects/{PROJECT}"
        assert api.get(f"{base}/campaigns", {})["items"][0]["campaign_id"] == cid
        assert len(api.get(f"{base}/chemical-hypotheses", {})["items"]) == 2
        assert api.get(f"{base}/chemical-spaces", {})["items"]
        cands = api.get(f"{base}/campaigns/{cid}/candidates", {})["value"]
        assert cands and "aggregate_score" not in cands[0]
        assert api.get(f"{base}/campaigns/{cid}/rationale", {})["value"][0]["why"]
        assert (
            "Requires external experimental validation"
            in api.get(f"{base}/campaigns/{cid}/report", {})["value"]["markdown"]
        )
        assert api.get("/api/projects/OTHER/campaigns", {})["items"] == []
        with pytest.raises(RecordNotFoundError):
            api.get(f"/api/projects/OTHER/campaigns/{cid}", {})
        with pytest.raises(RecordNotFoundError):
            api.get(f"{base}/campaigns/{cid}/nothing", {})


def test_cli_flow(tmp_path: Path) -> None:
    runner = CliRunner()
    base = ["--database", str(tmp_path / "c.duckdb")]
    reg = runner.invoke(app, [*base, "campaign", "register", "synthetic-generic"])
    assert reg.exit_code == 0, reg.output
    cid = reg.output.strip()
    early = runner.invoke(app, [*base, "campaign", "run", cid])
    assert early.exit_code == 2 and "refused" in early.output
    assert runner.invoke(app, [*base, "campaign", "prepare", cid]).exit_code == 0
    assert runner.invoke(app, [*base, "campaign", "run", cid]).exit_code == 0
    shown = runner.invoke(app, [*base, "campaign", "candidates", cid])
    assert "no aggregate score" in shown.output and "synthetic:cmpd-2" in shown.output
    assert runner.invoke(app, [*base, "chemistry", "hypothesis", "list"]).exit_code == 0
    assert "sha256" in runner.invoke(app, [*base, "chemistry", "space", "list"]).output
    assert (
        "none is an experimental result"
        in runner.invoke(
            app, [*base, "compound", "computational", "synthetic:cmpd-2"]
        ).output
    )
    out = tmp_path / "r.md"
    assert (
        runner.invoke(
            app, [*base, "campaign", "report", cid, "--output", str(out)]
        ).exit_code
        == 0
    )
    assert SYNTHETIC in out.read_text()
    assert (
        runner.invoke(app, [*base, "campaign", "list"]).output.count("SYNTHETIC") >= 1
    )


# --- Phase 3.8 acceptance hardening ---------------------------------------------------


def _obs(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "epistemic_class": "axis_observation",
        "experimental": False,
        "method": "similarity",
        "tool": "RDKit",
        "tool_version": "x",
        "parameters": {},
        "input_sha256": "a",
        "output_sha256": "b",
    }
    return {**base, **over}


@pytest.mark.parametrize(
    "bad",
    [
        {
            "epistemic_class": "experimental_result"
        },  # docking score -> experimental result
        {"epistemic_class": "source_assertion"},  # similarity -> source assertion
        {"epistemic_class": "accepted_experimental_evidence"},
        {"epistemic_class": "validated_binding"},
        {"experimental": True},
    ],
)
def test_invalid_epistemic_transitions_are_refused(bad: dict[str, Any]) -> None:
    from axis.computational.epistemics import EpistemicError, validate_observation

    validate_observation(_obs())
    with pytest.raises(EpistemicError):
        validate_observation(_obs(**bad))


@pytest.mark.parametrize(
    "missing",
    ["tool", "tool_version", "parameters", "input_sha256", "output_sha256", "method"],
)
def test_observation_without_method_provenance_is_not_trusted(missing: str) -> None:
    from axis.computational.epistemics import EpistemicError, validate_observation

    o = _obs()
    del o[missing]
    with pytest.raises(EpistemicError, match="provenance"):
        validate_observation(o)


def test_every_stored_observation_carries_method_provenance_and_hashes(
    syn: CampaignService,
) -> None:
    view = syn.view(finish(syn, "synthetic-generic"))
    for o in view["observations"]:
        assert o["input_sha256"] and o["output_sha256"] == digest(o["output"])
        assert o["tool"] and o["tool_version"] and "parameters" in o


def test_overclaim_scanner_flags_assertions_but_allows_negations() -> None:
    from axis.computational.epistemics import overclaims

    assert overclaims("Captopril is active and inhibits ERAP1; a confirmed hit.")
    assert not overclaims(
        "Nothing here is an experimental result, nor a drug candidate."
    )
    assert not overclaims(
        "A docking score is not a binding affinity; no validated binder exists."
    )


def test_no_surface_overclaims_computational_prioritization(
    erap: CampaignService,
) -> None:
    from axis.computational.epistemics import overclaims

    cid = finish(erap, "erap1")
    texts = [erap.report(cid), json.dumps(erap.view(cid)["prioritization"])]
    for path in [
        ROOT / "web/src/campaign.ts",
        ROOT / "axis/cli/campaign.py",
        ROOT / "docs/phase38-computational-discovery.md",
        ROOT / "docs/phase38-computational-method-audit.md",
        ROOT / "axis/resources/computational-discovery/erap1/v1/campaign-plan.json",
    ]:
        texts.append(path.read_text())
    for text in texts:
        found = overclaims(text)
        assert found == [], [
            text[max(0, text.find(f) - 160) : text.find(f) + 40] for f in found
        ]


def test_no_hidden_aggregate_scoring_in_prioritization() -> None:
    source = (ROOT / "axis/computational/prioritize.py").read_text()
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith(("#", '"'))
    )
    assert not re.search(r"weighted|composite|\bweights?\b|\* ?0\.\d", code)
    args = base_inputs()
    result = prioritize.prioritize(**args)
    assert result["aggregate_score"] is None
    for e in result["panel"]:
        assert not any(k in e for k in ("score", "rank", "total", "probability"))


def test_ordering_ties_are_deterministic_and_identifier_is_display_only() -> None:
    args = base_inputs()
    args["clusters"] = {
        "clusters": [
            {"representative": r, "members": [r]} for r in ("k", "a", "b", "c")
        ]
    }
    args["constraints"] = {
        **args["constraints"],
        "panel": {"exploitation": 1, "exploration": 1, "per_cluster": 1},
    }
    first = prioritize.prioritize(**args)
    shuffled = {**args, "members": list(reversed(args["members"]))}
    assert [e["compound_ref"] for e in first["panel"]] == [
        e["compound_ref"] for e in prioritize.prioritize(**shuffled)["panel"]
    ]
    assert "display tie-break only" in prioritize.RULES["PRIO-007"]


# identity ---------------------------------------------------------------------------


def test_external_identity_is_frozen_matches_and_is_identity_only() -> None:
    doc = json.loads((registry_root() / "erap1/v1/external-identity.json").read_text())
    assert "not evidence of ERAP1" in doc["scope"] and doc["retrieved_at"]
    for e in doc["entries"].values():
        assert (
            e["identity_check"] == "match"
            and e["provider_inchikey"] == e["campaign_inchikey"]
        )
        assert len(e["response_sha256"]) == 64 and e["provider_record"].startswith(
            "CID "
        )
    manifest = json.loads((registry_root() / "erap1/v1/manifest.json").read_text())
    assert (
        "external-identity.json" in manifest["files"]
        and "manifest.json" not in manifest["files"]
    )


def test_captopril_stereochemistry_regression() -> None:
    plan = json.loads((registry_root() / "erap1/v1/campaign-plan.json").read_text())
    smiles = next(
        m["smiles"] for m in plan["space"]["members"] if m["ref"].endswith("captopril")
    )
    assert (
        chem.prepare_compound("c", smiles, compound_identity=None, input_stereo=None)[
            "inchi_key"
        ]
        == "FAKRSMQSSFJEIM-RQJHMYQMSA-N"
    )


def test_identity_provenance_distinguishes_provider_supplied_and_external(
    erap: CampaignService,
) -> None:
    cid = finish(erap, "erap1")
    prio = erap.view(cid)["prioritization"]
    for e in prio["panel"]:
        ident = e["dimensions"]["identity"]
        assert ident["identity_provenance"] == "researcher_supplied"
        assert ident["external_identity"]["status"] == "externally_verified_identity"
        assert "identity only" in ident["external_identity"]["scope"]
        assert (
            ident["chemical_space_origin"] == "researcher_supplied"
            and ident["inchi_key"]
        )
        assert (
            e["dimensions"]["known_experimental_evidence"]["has_experimental_evidence"]
            is False
        )
    prepared = {p["compound_ref"]: p for p in erap.view(cid)["prepared_compounds"]}
    assert prepared["compound:maben-1"]["identity_provenance"] == "indexed_provider"
    assert prepared["compound:maben-1"]["external_identity"]["status"] == "unverified"


def test_synthetic_identity_is_unverified(syn: CampaignService) -> None:
    for e in syn.view(finish(syn, "synthetic-generic"))["prioritization"]["panel"]:
        assert (
            e["dimensions"]["identity"]["external_identity"]["status"] == "unverified"
        )


def test_prepared_compound_identity_fields_are_recorded() -> None:
    p = chem.prepare_compound(
        "c", "C[C@H](N)C(=O)O", compound_identity=None, input_stereo=None
    )
    assert (
        p["molecular_formula"] == "C3H7NO2" and p["inchi_key"] and p["isomeric_smiles"]
    )
    assert p["stereochemistry"]["status"] == "specified_in_input"
    assert "@" not in p["canonical_smiles"] and "@" in p["isomeric_smiles"]


# similarity and missing states -------------------------------------------------------


def test_similarity_invalid_and_missing_reference_states() -> None:
    assert (
        chem.similarity("not-a-smiles", "CCO") is None
        and chem.similarity("CCO", "bad") is None
    )
    assert (
        chem.fingerprint("CCO").ToBitString() == chem.fingerprint("CCO").ToBitString()
    )
    args = base_inputs()
    args["known"] = {}
    args["similarities"] = {r: {} for r in "abc"}
    result = prioritize.prioritize(**args)
    assert {e["role"] for e in result["panel"]} == {"exploration"}
    assert any("No reference chemistry" in s for s in result["statements"])


# hypothesis diversity ----------------------------------------------------------------


def test_erap1_chemical_diversity_is_not_hypothesis_diversity(
    erap: CampaignService,
) -> None:
    cid = finish(erap, "erap1")
    prio = erap.view(cid)["prioritization"]
    div = prio["diversity"]
    assert (
        div["chemical_diversity"]["distinct_scaffolds"] == 2
    )  # bestatin and vorinostat share a phenyl Murcko scaffold
    assert div["hypothesis_diversity"]["hypotheses_tested"] == [
        "hypothesis:erap1:zinc-binding-chemotype"
    ]
    assert div["hypothesis_diversity"]["hypotheses_total"] == 2
    assert prio["hypothesis_coverage"]["hypothesis:erap1:maben-series-analog"] == []
    assert any(
        "chemical diversity is not hypothesis diversity" in s
        for s in prio["statements"]
    )
    plan = json.loads((registry_root() / "erap1/v1/campaign-plan.json").read_text())
    assert (
        plan["constraints"]["exploit_threshold"] == 0.4
    )  # not relaxed to force coverage
    report = erap.report(cid)
    assert (
        "1 of 2 hypotheses tested" in report
        and "externally_verified_identity" in report
    )


def test_exploration_is_rule_based_not_lower_quality(erap: CampaignService) -> None:
    prio = erap.view(finish(erap, "erap1"))["prioritization"]
    assert (
        "PRIO-003" in prio["rules"]
        and "similarity to reference" in prio["rules"]["PRIO-003"]
    )
    assert all(e["role"] == "exploration" for e in prio["panel"])
    assert not any(
        "lower" in e["why_this_molecule"].lower()
        and "score" in e["why_this_molecule"].lower()
        for e in prio["panel"]
    )


# docking states ------------------------------------------------------------------------


def test_docking_states_are_representable(tmp_path: Path) -> None:
    plan = docking.docking_plan({"centre_component": "ZN"}, receptor_validated=False)
    assert plan["states"] == {
        "method": plan["states"]["method"],
        "validation": "validation_not_established",
        "execution": "execution_not_attempted",
        "result": "no_result",
    }
    assert plan["states"]["method"] in docking.METHOD_STATES
    assert (
        docking.docking_plan({}, receptor_validated=True)["states"]["validation"]
        == "validation_established"
    )
    assert docking.classify({"status": "completed", "poses": [{"rank": 1}]}) == {
        "execution": "execution_attempted",
        "result": "result_available",
    }
    assert (
        docking.classify({"status": "failed", "exit_code": 0, "poses": []})["result"]
        == "result_invalid"
    )
    assert (
        docking.classify({"status": "failed", "exit_code": 3, "poses": []})["execution"]
        == "execution_failed"
    )
    assert set(docking.EXECUTION_STATES) >= {
        "execution_not_attempted",
        "execution_attempted",
        "execution_failed",
    }


def test_erap1_docking_rationale_is_stated(erap: CampaignService) -> None:
    cid = finish(erap, "erap1")
    dock = erap.view(cid)["prioritization"]["docking"]
    text = " ".join(dock["reasons"]).lower()
    assert dock["states"]["validation"] == "validation_not_established"
    assert "metal coordination" in text and "validation not established" in text
    prepared = erap.view(erap.list_campaigns()[0]["campaign_id"])["prepared_structure"]
    assert any("redocking" in x for x in prepared["limitations"])


# structure / site ---------------------------------------------------------------------


def test_site_is_deterministic_and_zinc_is_context_not_computed_coordination(
    erap: CampaignService,
) -> None:
    a = structure.define_site(CIF, chain="A", around="ZN", radius=8.0, site_id="s")
    b = structure.define_site(CIF, chain="A", around="ZN", radius=8.0, site_id="s")
    assert a == b and a["radius_angstrom"] == 8.0 and a["chain"] == "A"
    ps = erap.view(finish(erap, "erap1"))["prepared_structure"]
    assert "coordination not modelled" in ps["metals"]
    assert (
        ps["site"]["site_type"] == "known_catalytic_site"
        and "AXIS choice" in ps["site"]["type_note"]
    )
    assert (
        ps["entity_sequence_length"] > ps["resolved_polymer_residues"]
    )  # missing residues stay explicit
    assert "not shown to be disease-relevant" in " ".join(ps["limitations"])


# decision boundary, GET purity, determinism, offline ----------------------------------


def test_campaign_does_not_change_decision_evidence_or_claims(
    erap: CampaignService,
) -> None:
    db = erap.store._connection
    ids = erap.store.targets.project_ids(PROJECT)
    ds = DecisionService(erap.store)
    before = (
        ds.evidence(PROJECT, ids[0])["edges"],
        db.execute("SELECT count(*) FROM claims").fetchone()[0],
        db.execute("SELECT count(*) FROM decision_states").fetchone()[0],
        db.execute("SELECT count(*) FROM experimental_results").fetchone()[0],
    )
    finish(erap, "erap1")
    after = (
        ds.evidence(PROJECT, ids[0])["edges"],
        db.execute("SELECT count(*) FROM claims").fetchone()[0],
        db.execute("SELECT count(*) FROM decision_states").fetchone()[0],
        db.execute("SELECT count(*) FROM experimental_results").fetchone()[0],
    )
    assert before == after
    assert after[0]["engagement"]["state"] != "supported"


def test_api_get_never_mutates(erap_db: Path, tmp_path: Path) -> None:
    copy = tmp_path / "g.duckdb"
    shutil.copy(erap_db, copy)
    with EvidenceStore(copy) as s:
        cid = finish(CampaignService(s), "erap1")

        def counts() -> tuple[int, ...]:
            return tuple(
                s._connection.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in (
                    "computational_campaigns",
                    "computational_observations",
                    "candidate_prioritizations",
                    "campaign_reviews",
                    "prepared_compounds",
                    "claims",
                )
            )

        before = counts()
        api = ReadAPI(s)
        base = f"/api/projects/{PROJECT}"
        for suffix in (
            "campaigns",
            f"campaigns/{cid}",
            f"campaigns/{cid}/observations",
            f"campaigns/{cid}/report",
            "chemical-hypotheses",
            "chemical-spaces",
        ):
            api.get(f"{base}/{suffix}", {})
        assert counts() == before


def test_erap1_deterministic_across_clean_stores_and_offline(
    erap_db: Path, tmp_path: Path
) -> None:
    def refuse(*_: Any, **__: Any) -> None:
        raise AssertionError("network used")

    digests = []
    for n in range(2):
        copy = tmp_path / f"d{n}.duckdb"
        shutil.copy(erap_db, copy)
        with patch.object(socket.socket, "connect", refuse), EvidenceStore(copy) as s:
            service = CampaignService(s)
            view = service.view(finish(service, "erap1"))
            prio = view["prioritization"]
            digests.append(
                digest(
                    {
                        "panel": prio["panel"],
                        "clusters": prio["clusters"],
                        "rules": prio["rules_fingerprint"],
                        "obs": {
                            o["id"]: o["output_sha256"] for o in view["observations"]
                        },
                        "site": view["prepared_structure"]["site"],
                        "structure": view["prepared_structure"]["output_sha256"],
                        "space": view["chemical_space"]["checksum"],
                    }
                )
            )
    assert digests[0] == digests[1]


def test_migration_012_upgrades_from_the_phase_37_schema(tmp_path: Path) -> None:
    import hashlib
    import subprocess
    from importlib import resources as res

    import duckdb

    root = ROOT / "axis/storage/migrations"
    sql = (root / "012_computational_discovery.sql").read_text()
    assert not re.search(r"\b(DROP|ALTER|DELETE|UPDATE|CASCADE)\b", sql, re.I)
    assert sql.count("CREATE TABLE") == 11
    for path in sorted(root.glob("0*_*.sql")):
        if int(path.name[:3]) > 11:
            continue
        original = subprocess.run(
            ["git", "show", f"42bd276:axis/storage/migrations/{path.name}"],
            capture_output=True,
            cwd=ROOT,
        )
        if original.returncode == 0:
            assert (
                hashlib.sha256(original.stdout).hexdigest()
                == hashlib.sha256(path.read_bytes()).hexdigest()
            ), path.name
    db = tmp_path / "v11.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name VARCHAR, applied_at TIMESTAMPTZ DEFAULT current_timestamp)"
        )
        for item in sorted(
            res.files("axis.storage.migrations").iterdir(), key=lambda i: i.name
        ):
            if item.name.endswith(".sql") and int(item.name[:3]) <= 11:
                con.execute(item.read_text())
                con.execute(
                    "INSERT INTO schema_migrations(version,name) VALUES (?,?)",
                    [int(item.name[:3]), item.name],
                )
        con.execute(
            "INSERT INTO benchmark_sets VALUES ('s','x','development',false,'t',current_timestamp)"
        )
    with EvidenceStore(db) as store:
        assert store.statistics().schema_version == 13
        assert (
            store._connection.execute("SELECT count(*) FROM benchmark_sets").fetchone()[
                0
            ]
            == 1
        )  # Phase 3.7 data intact
        cid = finish(CampaignService(store), "synthetic-generic")
    with EvidenceStore(db, read_only=True) as store:
        assert store.statistics().schema_version == 13
        assert CampaignService(store).view(cid)["prioritization"]["outcome"] == "panel"


def test_committed_resources_match_their_manifests() -> None:
    import hashlib

    for package in registry_root().glob("*/v1"):
        manifest = json.loads((package / "manifest.json").read_text())
        for name, checksum in manifest["files"].items():
            assert (
                hashlib.sha256((package / name).read_bytes()).hexdigest() == checksum
            ), name
        assert "manifest.json" not in manifest["files"]
        assert (
            hashlib.sha256((package / "manifest.json").read_bytes()).hexdigest()
            == (package / "manifest.sha256").read_text().strip()
        )
    assert SYNTHETIC in (registry_root() / "synthetic-generic/v1/README.md").read_text()


def test_synthetic_never_leaks_into_production_evidence(erap: CampaignService) -> None:
    finish(erap, "erap1")
    finish(erap, "synthetic-generic")
    assert {c["project_id"] for c in erap.list_campaigns()} == {
        PROJECT,
        "SYNTHETIC-PROJECT",
    }
    prod = erap.view(f"{ERAP}@r1", PROJECT)
    assert SYNTHETIC not in json.dumps(prod)
    assert erap.list_campaigns(PROJECT)[0]["synthetic"] is False


def test_cli_help_and_refusals(tmp_path: Path) -> None:
    runner = CliRunner()
    base = ["--database", str(tmp_path / "e.duckdb")]
    for group in (
        ["campaign"],
        ["chemistry"],
        ["chemistry", "hypothesis"],
        ["compound"],
    ):
        assert runner.invoke(app, [*base, *group, "--help"]).exit_code == 0
    unknown_package = runner.invoke(app, [*base, "campaign", "register", "nope"])
    assert (
        unknown_package.exit_code == 2
        and "unknown campaign package" in unknown_package.output
    )
    for args in (
        ["campaign", "show", "x@r1"],
        ["campaign", "prepare", "x@r1"],
        ["campaign", "run", "x@r1"],
        ["campaign", "report", "x@r1"],
    ):
        result = runner.invoke(app, [*base, *args])
        assert result.exit_code == 2 and "unknown campaign" in result.output, args
    assert (
        runner.invoke(app, [*base, "chemistry", "hypothesis", "show", "nope"]).exit_code
        == 2
    )
    assert (
        runner.invoke(app, [*base, "chemistry", "space", "show", "nope"]).exit_code == 2
    )
    # ERAP1 campaign without the indexed project: indexed identities cannot be verified
    erap_run = runner.invoke(app, [*base, "campaign", "register", "erap1"])
    assert erap_run.exit_code != 0


def test_cli_uses_the_same_service_as_the_api(tmp_path: Path) -> None:
    runner = CliRunner()
    db = tmp_path / "same.duckdb"
    base = ["--database", str(db)]
    cid = runner.invoke(
        app, [*base, "campaign", "register", "synthetic-generic"]
    ).output.strip()
    runner.invoke(app, [*base, "campaign", "prepare", cid])
    runner.invoke(app, [*base, "campaign", "run", cid])
    cli_json = json.loads(
        runner.invoke(app, [*base, "campaign", "show", cid, "--json"]).output
    )
    with EvidenceStore(db, read_only=True) as s:
        api = ReadAPI(s).get(f"/api/projects/SYNTHETIC-PROJECT/campaigns/{cid}", {})
    assert digest(cli_json["prioritization"]) == digest(api["prioritization"])
