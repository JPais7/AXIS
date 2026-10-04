"""Phase 3.8: computational discovery campaigns.

Synthetic fixtures are SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE. The ERAP1
campaign is a computational prioritization for experimental validation only.
"""

import json
import re
import shutil
import socket
import stat
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


def test_docking_runner_uses_argument_arrays_and_rejects_partial_output(
    tmp_path: Path,
) -> None:
    ok = tmp_path / "ok.sh"
    ok.write_text("#!/bin/sh\necho 'REMARK VINA RESULT:  -7.1  0.0  0.0'\n")
    ok.chmod(ok.stat().st_mode | stat.S_IEXEC)
    good = docking.run_engine([str(ok)], timeout=10, workdir=tmp_path)
    assert good["status"] == "completed" and good["poses"][0]["score_kcal_mol"] == -7.1
    bad = tmp_path / "bad.sh"
    bad.write_text("#!/bin/sh\necho 'REMARK VINA RESULT:  -7.1  0.0  0.0'\nexit 3\n")
    bad.chmod(bad.stat().st_mode | stat.S_IEXEC)
    failed = docking.run_engine([str(bad)], timeout=10, workdir=tmp_path)
    assert failed["status"] == "failed" and failed["poses"] == []
    assert (
        docking.run_engine(["/nonexistent/engine"], timeout=5, workdir=tmp_path)[
            "status"
        ]
        == "failed"
    )
    garbage = tmp_path / "g.sh"
    garbage.write_text("#!/bin/sh\necho 'REMARK VINA RESULT: nope'\n")
    garbage.chmod(garbage.stat().st_mode | stat.S_IEXEC)
    assert (
        docking.run_engine([str(garbage)], timeout=5, workdir=tmp_path)["poses"] == []
    )


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
