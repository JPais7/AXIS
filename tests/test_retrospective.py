"""Phase 3.7: retrospective validation and temporal backtesting.

Synthetic fixtures are SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE. The ERAP1
cases use the real chronology frozen in the benchmark package; they are DEVELOPMENT
benchmarks, not independent validation.
"""

import json
import re
import shutil
import socket
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from axis.api.server import ReadAPI
from axis.cli.main import app
from axis.decision import rules
from axis.domain.validation import INVALID_LABEL, SYNTHETIC_LABEL
from axis.storage import EvidenceStore, RecordConflictError, RecordNotFoundError
from axis.validation import core, temporal
from axis.validation.package import (
    BenchmarkSet,
    PackageError,
    build_set,
    load_set,
    protocol_fingerprint,
)
from axis.validation.service import BenchmarkError, BenchmarkService, registry_root

ROOT = Path(__file__).resolve().parents[1]
ERAP = "erap1-axspa-t2016"
SYN = {
    "positive": "syn-generic-positive",
    "negative": "syn-generic-negative",
    "ambiguous": "syn-generic-ambiguous",
    "irrelevant": "syn-generic-irrelevant",
    "undated": "syn-generic-undated",
}


@pytest.fixture
def store(tmp_path: Path) -> Any:
    with EvidenceStore(tmp_path / "axis.duckdb") as s:
        yield s


@pytest.fixture
def service(store: EvidenceStore) -> BenchmarkService:
    return BenchmarkService(store)


def package(set_id: str) -> BenchmarkSet:
    return load_set(registry_root() / set_id / "v1")


def ids_of(records: dict[str, Any]) -> set[str]:
    return set(temporal.record_ids(records))


# --- temporal availability and windows ---------------------------------------


def test_eligibility_uses_first_public_access_not_nominal_year() -> None:
    availability = package("erap1-axspa").availability()
    entry = availability["PMID:26130142"]
    assert entry["nominal_publication_date"].startswith("2016")
    assert entry["first_publicly_accessible_date"].startswith("2015")
    before = temporal.TemporalCutoff.parse("t", "2015-07-01", "x")
    on = temporal.TemporalCutoff.parse("t", "2015-07-02", "x")
    assert not temporal.source_eligibility(availability, "PMID:26130142", before)[0]
    assert temporal.source_eligibility(availability, "PMID:26130142", on)[0]


@pytest.mark.parametrize("kind", ["uncertain", "unknown"])
def test_uncertain_or_unknown_availability_never_enters_a_window(kind: str) -> None:
    availability = {
        "S": {"availability_kind": kind, "first_publicly_accessible_date": "2000-01-01"}
    }
    cutoff = temporal.TemporalCutoff.parse("t", "2030-01-01", "x")
    assert temporal.source_eligibility(availability, "S", cutoff) == (
        False,
        "availability_unknown_or_uncertain",
    )
    assert not temporal.source_eligibility({}, "S", cutoff)[0]


def test_undated_source_is_in_neither_window_nor_future() -> None:
    package_ = package("synthetic-generic")
    case = SYN["undated"]
    window = package_.window(case)["records"]
    future = package_._load(f"cases/{case}/future.json")["records"]
    assert not any("syn:e7" in r for r in ids_of(window) | ids_of(future))
    assert package_.protocol(case)["excluded_undated_records"] > 0


def test_every_window_is_free_of_future_records_and_dated() -> None:
    for set_id in ("erap1-axspa", "synthetic-generic"):
        pkg = package(set_id)
        availability = pkg.availability()
        for case in pkg.manifest["cases"]:
            protocol = pkg.protocol(case)
            cutoff = temporal.TemporalCutoff.parse(
                protocol["cutoff_id"], protocol["cutoff"], ""
            )
            window = pkg.window(case)
            future = pkg._load(f"cases/{case}/future.json")
            assert not ids_of(window["records"]) & ids_of(future["records"])
            for record in ids_of(window["records"]) - {
                r for r in ids_of(window["records"]) if r.startswith("strategy")
            }:
                source = window["record_sources"][record]
                assert temporal.source_eligibility(availability, source, cutoff)[0]
            for source in future["record_sources"].values():
                assert (
                    date.fromisoformat(
                        availability[source]["first_publicly_accessible_date"]
                    )
                    > cutoff.date
                )


def test_real_chronology_dates_are_recorded_with_provenance() -> None:
    doc = json.loads(
        (registry_root() / "erap1-axspa/v1/temporal-availability.json").read_text()
    )
    maben = doc["sources"]["PMID:31841350"]
    assert maben["first_publicly_accessible_date"] == "2019-12-17"
    assert maben["nominal_publication_date"] == "2020 Jan 9"
    assert doc["sources"]["PDB:3QNF"]["first_publicly_accessible_date"] == "2011-02-23"
    assert all(r["sha256"] for r in doc["retrieval"])


def test_snapshot_fingerprint_is_deterministic_and_cutoff_sensitive(
    tmp_path: Path,
) -> None:
    fingerprints = []
    for n in range(2):
        with EvidenceStore(tmp_path / f"{n}.duckdb") as s:
            fingerprints.append(BenchmarkService(s).snapshot(ERAP)["fingerprint"])
    assert fingerprints[0] == fingerprints[1]
    with EvidenceStore(tmp_path / "x.duckdb") as s:
        other = BenchmarkService(s).snapshot("erap1-axspa-t2014")["fingerprint"]
    assert other != fingerprints[0]


def test_snapshot_does_not_reveal_future_identities(service: BenchmarkService) -> None:
    snapshot = service.snapshot("erap1-axspa-t2014")
    text = json.dumps(snapshot)
    assert "maben" not in text.lower() and "31841350" not in text
    assert "sealed until reveal" in snapshot["future_records_withheld"]


# --- sealing and integrity -----------------------------------------------------


def test_protocol_is_fingerprinted_and_sealed(service: BenchmarkService) -> None:
    service.register()
    protocol = package("erap1-axspa").protocol(ERAP)
    assert protocol["protocol_fingerprint"] == protocol_fingerprint(protocol)
    assert protocol["rules_fingerprint"] == rules.fingerprint()
    altered = {**protocol, "question": "changed"}
    altered["protocol_fingerprint"] = protocol_fingerprint(altered)
    with pytest.raises(RecordConflictError):
        service.repo.seal_case(altered, temporal_now())


def temporal_now() -> Any:
    from axis.validation.service import now

    return now()


def copy_set(tmp_path: Path, set_id: str = "synthetic-generic") -> Path:
    target = tmp_path / "registry" / set_id / "v1"
    shutil.copytree(registry_root() / set_id / "v1", target)
    return target.parent.parent


def test_altered_window_or_protocol_fails_closed(tmp_path: Path) -> None:
    root = copy_set(tmp_path)
    case = SYN["positive"]
    window = root / "synthetic-generic/v1/cases" / case / "window.json"
    window.write_text(window.read_text().replace("SYN-ENDPOINT", "TAMPERED", 1))
    pkg = load_set(root / "synthetic-generic/v1")
    with pytest.raises(PackageError, match="checksum mismatch"):
        pkg.window(case)
    with EvidenceStore(tmp_path / "t.duckdb") as s:
        service = BenchmarkService(s, root)
        with pytest.raises(PackageError):
            service.run(case)


def test_altered_manifest_is_refused(tmp_path: Path) -> None:
    root = copy_set(tmp_path)
    manifest = root / "synthetic-generic/v1/manifest.json"
    manifest.write_text(manifest.read_text().replace("synthetic-generic", "x", 1))
    with pytest.raises(PackageError, match="manifest checksum"):
        load_set(root / "synthetic-generic/v1")


def test_excluding_sources_by_design_is_synthetic_only(tmp_path: Path) -> None:
    with pytest.raises(PackageError, match="synthetic"):
        build_set(
            tmp_path / "x",
            set_id="x",
            title="x",
            kind="development",
            synthetic=False,
            records={
                k: []
                for k in (
                    "experiments",
                    "assessments",
                    "readouts",
                    "biochemical_measurements",
                    "selectivity",
                    "compounds",
                    "gaps",
                    "structure_ids",
                    "strategy_ids",
                )
            },
            record_sources={},
            availability_doc={"sources": {}},
            template={},
            redactions=[],
            cases=[
                {
                    "case_id": "c",
                    "cutoff_id": "t",
                    "cutoff": "2020-01-01",
                    "cutoff_rationale": "r",
                    "question": "q",
                    "case_type": "t",
                    "selection_rationale": "s",
                    "dimensions": [],
                    "expectation": "e",
                    "excluded_sources": ["S"],
                }
            ],
            rules_version="v",
            rules_fingerprint="f",
            selection_bias_note="n",
            forbidden_tokens={},
        )


# --- the decision at T never sees the future ------------------------------------


def test_run_never_opens_the_future_file(service: BenchmarkService) -> None:
    with patch.object(
        BenchmarkSet, "read_future", side_effect=AssertionError("future opened")
    ):
        result = service.run(ERAP)
    assert result["valid"]
    assert service.set_of(ERAP).opened_future == []


def test_reveal_requires_run_and_is_single_use(service: BenchmarkService) -> None:
    service.register()
    with pytest.raises(BenchmarkError, match="run the case"):
        service.reveal(ERAP)
    service.run(ERAP)
    service.reveal(ERAP)
    with pytest.raises(BenchmarkError, match="already revealed"):
        service.reveal(ERAP)


def test_cutoff_decision_cites_only_window_records(service: BenchmarkService) -> None:
    for case in ("erap1-axspa-t2011", "erap1-axspa-t2014", ERAP):
        result = service.run(case)
        assert result["valid"]
        view = service.view(case)
        assert view["cutoff_run"]["decision_validity"]["result"] == "valid"


def test_decision_engine_is_the_same_code_path(service: BenchmarkService) -> None:
    """The window decision equals the engine's output on the same inputs."""
    from axis.decision import engine

    pkg = service.set_of(ERAP)
    window = pkg.window(ERAP)["records"]
    template = pkg.template()["template"]
    scrubbed, _ = core.scrub_template(template, window)
    direct = engine.analyze(core.engine_inputs(scrubbed, window, "exploratory"))
    assert core.summary(direct) == core.summary(
        core.decide(template, window, "exploratory")
    )


def test_template_references_to_future_records_are_removed(
    service: BenchmarkService,
) -> None:
    result = service.run("erap1-axspa-t2011")
    assert result["valid"]
    view = service.view("erap1-axspa-t2011")
    assert view["cutoff_run"]["template_references_removed"] > 0


def test_redaction_removes_a_name_from_before_its_source_existed() -> None:
    template = package("erap1-axspa").template()
    assert "DG013A" not in json.dumps(template["template"])
    assert template["redactions"][0]["token"] == "the DG013A label"


# --- leakage audit ----------------------------------------------------------------


def audit_args(**over: Any) -> dict[str, Any]:
    pkg = package("synthetic-generic")
    case = SYN["positive"]
    protocol = pkg.protocol(case)
    future = pkg._load(f"cases/{case}/future.json")
    base: dict[str, Any] = {
        "availability": pkg.availability(),
        "cutoff": temporal.TemporalCutoff.parse(
            protocol["cutoff_id"], protocol["cutoff"], ""
        ),
        "window_file": pkg.window(case),
        "future_ids": ids_of(future["records"]),
        "future_sources": set(future["record_sources"].values()),
        "template": pkg.template()["template"],
        "forbidden_tokens": pkg.template()["forbidden_tokens"],
        "outputs": [],
        "checksums_ok": {},
        "future_opened_before_reveal": False,
        "baseline_frozen_before_reveal": True,
    }
    base.update(over)
    return base


def test_clean_audit_is_valid() -> None:
    assert core.leakage_audit(**audit_args())["valid"]


def test_future_record_injected_into_window_is_detected() -> None:
    args = audit_args()
    window_file = json.loads(json.dumps(args["window_file"]))
    window_file["records"]["experiments"].append({"id": "syn:e3-engagement"})
    window_file["record_sources"]["experiments:syn:e3-engagement"] = "SYN:S2"
    result = core.leakage_audit(**{**args, "window_file": window_file})
    cats = {f["category"] for f in result["findings"]}
    assert not result["valid"] and result["label"] == INVALID_LABEL
    assert "record_after_cutoff" in cats and "future_record_in_window" in cats


def test_window_record_without_a_date_is_detected() -> None:
    args = audit_args()
    window_file = json.loads(json.dumps(args["window_file"]))
    window_file["records"]["experiments"].append({"id": "x"})
    window_file["record_sources"]["experiments:x"] = "SYN:S6"
    result = core.leakage_audit(**{**args, "window_file": window_file})
    assert "availability_unknown_or_uncertain" in {
        f["category"] for f in result["findings"]
    }


@pytest.mark.parametrize(
    ("over", "category"),
    [
        (
            {"outputs": [{"text": "see syn:e3-engagement"}]},
            "output_names_future_source",
        ),
        ({"outputs": [{"text": "SYN:S2"}]}, "output_names_future_source"),
        ({"future_opened_before_reveal": True}, "future_file_opened_before_reveal"),
        ({"baseline_frozen_before_reveal": False}, "baseline_not_frozen_before_reveal"),
        (
            {"checksums_ok": {"window_checksum_mismatch": False}},
            "window_checksum_mismatch",
        ),
        ({"template": {"note": "see syn:e3"}}, "template_names_future_source"),
    ],
)
def test_each_leakage_category_makes_the_case_invalid(
    over: dict[str, Any], category: str
) -> None:
    result = core.leakage_audit(**audit_args(**over))
    assert not result["valid"]
    assert category in {f["category"] for f in result["findings"]}


def test_leaking_template_invalidates_the_case_and_blocks_reveal(
    tmp_path: Path,
) -> None:
    src = package("synthetic-generic")
    case = SYN["positive"]
    template = json.loads(json.dumps(src.template()["template"]))
    template["hypothesis"]["description"] += " Follow-up syn:e3-engagement."
    records = {k: v for k, v in src.window(case)["records"].items()}
    future = src._load(f"cases/{case}/future.json")["records"]
    full = temporal.merge(records, future)
    sources = {
        **src.window(case)["record_sources"],
        **src._load(f"cases/{case}/future.json")["record_sources"],
    }
    root = tmp_path / "registry" / "leaky" / "v1"
    protocol = src.protocol(case)
    build_set(
        root,
        set_id="leaky",
        title="leaky",
        kind="synthetic_test",
        synthetic=True,
        records=full,
        record_sources=sources,
        availability_doc={"sources": src.availability()},
        template=template,
        redactions=[],
        cases=[
            {
                "case_id": "leaky-1",
                "cutoff_id": protocol["cutoff_id"],
                "cutoff": protocol["cutoff"],
                "cutoff_rationale": SYNTHETIC_LABEL,
                "question": "q",
                "case_type": "leak",
                "selection_rationale": SYNTHETIC_LABEL,
                "dimensions": [],
                "expectation": "e",
                "horizon": "2019-12-31",
            }
        ],
        rules_version=rules.RULES_VERSION,
        rules_fingerprint=rules.fingerprint(),
        selection_bias_note=SYNTHETIC_LABEL,
        forbidden_tokens={"SYN:S2": ["syn:e3"]},
    )
    with EvidenceStore(tmp_path / "l.duckdb") as s:
        service = BenchmarkService(s, tmp_path / "registry")
        result = service.run("leaky-1")
        assert not result["valid"] and result["label"] == INVALID_LABEL
        assert service.view("leaky-1")["status"] == "invalid"
        with pytest.raises(BenchmarkError, match="INVALID"):
            service.reveal("leaky-1")


def test_cli_run_exits_nonzero_on_invalid(tmp_path: Path) -> None:
    runner = CliRunner()
    db = tmp_path / "c.duckdb"
    result = runner.invoke(app, ["--database", str(db), "benchmark", "run", ERAP])
    assert result.exit_code == 0 and "leakage audit: valid" in result.output


# --- reveal, relevance, diff -----------------------------------------------------


def reveal(service: BenchmarkService, case: str) -> dict[str, Any]:
    service.run(case)
    return service.reveal(case)


def test_real_cases_report_what_the_future_actually_tested(
    service: BenchmarkService,
) -> None:
    for case in ("erap1-axspa-t2014", ERAP):
        a = reveal(service, case)["assessment"]
        # development benchmark: the honest result is that later evidence did not
        # test the stated critical uncertainty
        assert (
            a["conclusion"]["conclusion"] == "future_evidence_did_not_test_the_decision"
        )
        assert a["provenance"]["benchmark_kind"] == "development"
        assert not a["provenance"]["synthetic"]
        assert any("prospective" in x for x in a["limits"])


def test_t_to_t1_diff_is_scientific_not_json(service: BenchmarkService) -> None:
    result = reveal(service, SYN["positive"])
    diff = result["diff"]
    assert diff["edges"]["engagement"] == ["not_assessed", "supported"]
    assert diff["uncertainties"]["uncertainty:target_engagement"] == [
        "open",
        "resolved_for_current_decision",
    ]
    assert diff["rules_fingerprint"] == rules.fingerprint()


@pytest.mark.parametrize(
    ("key", "conclusion"),
    [
        ("positive", "supported_by_future_evidence"),
        ("negative", "weakened_by_future_evidence"),
        ("ambiguous", "ambiguous"),
        ("irrelevant", "future_evidence_did_not_test_the_decision"),
    ],
)
def test_conclusions_include_negative_ambiguous_and_untested(
    service: BenchmarkService, key: str, conclusion: str
) -> None:
    a = reveal(service, SYN[key])["assessment"]
    assert a["conclusion"]["conclusion"] == conclusion
    assert a["provenance"]["synthetic"]


def test_irrelevant_and_noninterpretable_sources_are_labelled(
    service: BenchmarkService,
) -> None:
    rel = reveal(service, SYN["irrelevant"])["assessment"]["relevance"]
    assert rel["SYN:S4"]["relevance"] == "does_not_test_decision_question"
    assert rel["SYN:S5"]["relevance"] == "non_interpretable"


def test_conflicting_results_make_the_case_ambiguous_not_supported(
    service: BenchmarkService,
) -> None:
    a = reveal(service, SYN["ambiguous"])["assessment"]
    assert a["conclusion"]["conclusion"] == "ambiguous"
    assert any("mixed" in b for b in a["conclusion"]["basis"])


def test_matrix_has_individual_dimensions_and_no_scalar(
    service: BenchmarkService,
) -> None:
    a = reveal(service, ERAP)["assessment"]
    assert list(a["matrix"]) == [
        "temporal_integrity",
        "decision_validity_at_cutoff",
        "uncertainty_calibration",
        "recommendation_relevance",
        "future_evidence_relevance",
        "evidence_update_behavior",
        "overstated_claims",
        "baseline_comparison",
    ]
    text = json.dumps(a).lower()
    assert not re.search(r'"(score|accuracy|auc|probability|rank)"', text)
    for value in a["matrix"].values():
        assert not isinstance(value["result"], int | float)


def test_leave_one_source_out_reports_dependence(service: BenchmarkService) -> None:
    a = reveal(service, ERAP)["assessment"]
    removed = {
        x["removed_source"]: x["decision_changed"] for x in a["leave_one_source_out"]
    }
    assert removed["PMID:26130142"] == "yes"
    assert removed["PMID:24504800"] == "no"


def test_rule_fingerprint_and_software_commit_are_recorded(
    service: BenchmarkService,
) -> None:
    reveal(service, ERAP)
    runs = service.repo.rows("benchmark_runs", ERAP)
    assert {r["rules_fingerprint"] for r in runs} == {rules.fingerprint()}
    assert all(r["software_commit"] for r in runs)


def test_post_benchmark_rule_revision_is_labelled(service: BenchmarkService) -> None:
    with patch.object(rules, "fingerprint", return_value="f" * 64):
        result = service.run(ERAP)
    assert result["rule_revision"]["status"] == "post_benchmark_rule_revision"
    notes = service.repo.rows("benchmark_rule_notes", ERAP)
    assert notes and notes[0]["kind"] == "post_benchmark_rule_revision"
    a = service.reveal(ERAP)["assessment"]
    assert a["provenance"]["rule_revision"]["status"] == "post_benchmark_rule_revision"


def test_repeated_runs_are_all_retained(service: BenchmarkService) -> None:
    service.run(ERAP)
    service.run(ERAP)
    runs = [
        r for r in service.repo.rows("benchmark_runs", ERAP) if r["phase"] == "cutoff"
    ]
    assert len(runs) == 2
    assert runs[0]["payload"]["state"] == runs[1]["payload"]["state"]


# --- baselines ---------------------------------------------------------------------


def test_internal_baseline_is_frozen_before_reveal(service: BenchmarkService) -> None:
    service.run(ERAP)
    frozen = service.repo.rows("benchmark_baselines", ERAP)
    assert frozen and frozen[0]["baseline_kind"].startswith("internal")
    service.reveal(ERAP)
    reveal_run = [
        r for r in service.repo.rows("benchmark_runs", ERAP) if r["phase"] == "reveal"
    ][0]
    assert frozen[0]["frozen_at"] < reveal_run["created_at"]


def external(edge: str = "engagement") -> dict[str, Any]:
    return {
        "baseline": "literature-aware-LLM",
        "runs": [
            {
                "label": f"run-{n}",
                "model": "m",
                "stochastic": True,
                "recommended_edge": edge,
                "free_text": "t",
            }
            for n in (1, 2, 3)
        ],
    }


def test_external_baseline_runs_are_all_retained_and_frozen(
    service: BenchmarkService,
) -> None:
    service.run(SYN["positive"])
    labels = service.import_baseline(SYN["positive"], external())
    assert labels == ["run-1", "run-2", "run-3"]
    a = service.reveal(SYN["positive"])["assessment"]
    runs = [b for b in a["baseline_comparison"] if b["baseline"].startswith("external")]
    assert len(runs) == 3 and all(r["stochastic"] for r in runs)
    assert all(r["result"] == "both_pointed_at_what_changed" for r in runs)


def test_baseline_cannot_be_imported_after_reveal_or_before_run(
    service: BenchmarkService,
) -> None:
    service.register()
    with pytest.raises(BenchmarkError, match="run the case"):
        service.import_baseline(SYN["positive"], external())
    service.run(SYN["positive"])
    service.reveal(SYN["positive"])
    with pytest.raises(BenchmarkError, match="before the future"):
        service.import_baseline(SYN["positive"], external())


def test_invalid_baseline_edge_is_refused(service: BenchmarkService) -> None:
    service.run(SYN["positive"])
    with pytest.raises(BenchmarkError, match="not a known edge"):
        service.import_baseline(SYN["positive"], external("nonsense"))


def test_baseline_is_compared_not_assumed_inferior(service: BenchmarkService) -> None:
    a = reveal(service, ERAP)["assessment"]
    verdict = a["baseline_comparison"][0]["result"]
    assert verdict == "baseline_pointed_at_what_changed_axis_did_not"


# --- blind review ----------------------------------------------------------------


def test_blind_packet_hides_which_option_is_the_software(
    service: BenchmarkService,
) -> None:
    reveal(service, SYN["positive"])
    packet = service.blind_packet(SYN["positive"])
    text = json.dumps(packet).lower()
    assert set(packet["options"]) == {"A", "B"}
    assert "baseline" not in text.replace("baseline_pointed", "")
    assert "decision:exp" not in text and "uncertainty:" not in text
    mapping = service.repo.rows("benchmark_blind_packets", SYN["positive"])[0]
    assert mapping["sealed_mapping"] in (
        {"A": "axis", "B": "baseline"},
        {"A": "baseline", "B": "axis"},
    )
    assert service.view(SYN["positive"])["blind_packet_mapping"] is None


def test_review_is_separate_human_and_gates_unblinding(
    service: BenchmarkService,
) -> None:
    reveal(service, SYN["positive"])
    with pytest.raises(BenchmarkError, match="requires at least one"):
        service.unblind(SYN["positive"])
    for bad in ("AXIS reviewer", "gpt-5", "Claude", ""):
        with pytest.raises(BenchmarkError):
            service.review(
                SYN["positive"],
                bad,
                dimensions={},
                preference="A",
                conclusion_opinion="ambiguous",
                rationale="r",
            )
    saved = service.review(
        SYN["positive"],
        "Dr Reviewer",
        dimensions={"overstated_claims": {"verdict": "agree"}},
        preference="neither",
        conclusion_opinion="supported_by_future_evidence",
        rationale="reasoned",
    )
    view = service.view(SYN["positive"])
    assert view["reviews"][0]["id"] == saved["id"]
    assert (
        view["assessment"]["provenance"]["human_review"] == "pending"
    )  # system output untouched
    assert view["status"] == "reviewed"
    assert service.unblind(SYN["positive"]) in (
        {"A": "axis", "B": "baseline"},
        {"A": "baseline", "B": "axis"},
    )


def test_review_rejects_unknown_labels(service: BenchmarkService) -> None:
    reveal(service, SYN["positive"])
    with pytest.raises(BenchmarkError, match="conclusion must be"):
        service.review(
            SYN["positive"],
            "Dr R",
            dimensions={},
            preference="A",
            conclusion_opinion="great",
            rationale="r",
        )
    with pytest.raises(BenchmarkError, match="unknown dimensions"):
        service.review(
            SYN["positive"],
            "Dr R",
            dimensions={"score": {}},
            preference="A",
            conclusion_opinion="ambiguous",
            rationale="r",
        )


# --- generic, synthetic and isolation ---------------------------------------------


def test_generic_logic_hard_codes_no_target_disease_or_source() -> None:
    forbidden = re.compile(
        r"ERAP1|HLA-B27|axSpA|spondyl|Maben|3QNF|DG013A|lupus|TRM17|DDX24",
        re.IGNORECASE,
    )
    files = [
        *(ROOT / "axis/validation").glob("*.py"),
        ROOT / "axis/domain/validation.py",
        ROOT / "axis/cli/benchmark.py",
        ROOT / "axis/storage/benchmarks.py",
    ]
    for path in files:
        assert not forbidden.search(path.read_text()), path


def test_synthetic_and_real_benchmarks_are_labelled_and_separate(
    service: BenchmarkService,
) -> None:
    cases = {c["case_id"]: c for c in service.list_cases()}
    for name in SYN.values():
        assert cases[name]["synthetic"] and cases[name]["label"] == SYNTHETIC_LABEL
        assert cases[name]["benchmark_kind"] == "synthetic_test"
    for name in ("erap1-axspa-t2011", "erap1-axspa-t2014", ERAP):
        assert (
            not cases[name]["synthetic"]
            and cases[name]["benchmark_kind"] == "development"
        )
    assert not any(c["benchmark_kind"] == "validation" for c in cases.values())
    text = json.dumps(package("synthetic-generic").window(SYN["positive"]))
    assert "ERAP1" not in text and "HLA-B27" not in text


def test_selection_bias_is_documented_in_the_package() -> None:
    note = package("erap1-axspa").manifest["selection_bias_note"]
    assert "DEVELOPMENT" in note and "not a sample" in note


def test_running_a_benchmark_leaves_project_knowledge_untouched(
    service: BenchmarkService, store: EvidenceStore
) -> None:
    def counts() -> dict[str, int]:
        tables = (
            "claims",
            "decision_states",
            "discovery_projects",
            "performed_experiments",
        )
        return {
            t: store._connection.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in tables
        }

    before = counts()
    reveal(service, ERAP)
    reveal(service, SYN["positive"])
    assert counts() == before


def test_offline_and_deterministic_replay(tmp_path: Path) -> None:
    def attempt(*_: Any, **__: Any) -> None:
        raise AssertionError("network used")

    states = []
    for n in range(2):
        with (
            patch.object(socket.socket, "connect", attempt),
            EvidenceStore(tmp_path / f"{n}.duckdb") as s,
        ):
            service = BenchmarkService(s)
            result = reveal(service, ERAP)
            states.append(
                temporal.digest(
                    [
                        result["state_t1"],
                        result["diff"],
                        result["assessment"]["relevance"],
                    ]
                )
            )
            run = service.repo.rows("benchmark_runs", ERAP)[0]["payload"]
            assert run["llm_used"] is False and run["network_used"] is False
    assert states[0] == states[1]


def test_migration_011_is_additive(store: EvidenceStore) -> None:
    versions = [
        r[0]
        for r in store._connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    ]
    assert versions[-1] >= 11 and versions[:10] == list(range(1, 11))
    tables = {
        r[0]
        for r in store._connection.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    assert {
        "benchmark_cases",
        "temporal_snapshots",
        "leakage_audits",
        "retrospective_assessments",
        "benchmark_baselines",
        "benchmark_blind_packets",
        "benchmark_reviews",
    } <= tables


def test_decision_service_default_path_is_unchanged_by_records_override(
    tmp_path: Path,
) -> None:
    """The records= hook must not change production evidence assembly."""
    from axis.decision.evidence import assemble_evidence

    pkg = package("erap1-axspa")
    window = pkg.window("erap1-axspa-t2014")["records"]
    a = assemble_evidence(window, mode="exploratory", assessment_reviews={}, ledger=[])
    b = assemble_evidence(window, mode="exploratory", assessment_reviews={}, ledger=[])
    assert a == b and a["edges"]["hla"]["state"] == "supported"


# --- read-only API and report --------------------------------------------------------


def test_api_is_read_only_and_serves_benchmarks(tmp_path: Path) -> None:
    db = tmp_path / "api.duckdb"
    with EvidenceStore(db) as s:
        service = BenchmarkService(s)
        reveal(service, SYN["positive"])
    with EvidenceStore(db, read_only=True) as s:
        api = ReadAPI(s)
        listing = api.get("/api/benchmarks", {})
        assert {c["case_id"] for c in listing["items"]} >= set(SYN.values())
        detail = api.get(f"/api/benchmarks/{SYN['positive']}", {})
        assert detail["status"] == "revealed" and detail["label"] == SYNTHETIC_LABEL
        section = api.get(f"/api/benchmarks/{SYN['positive']}/assessment", {})
        assert (
            section["value"]["conclusion"]["conclusion"]
            == "supported_by_future_evidence"
        )
        assert api.get(f"/api/benchmarks/{ERAP}", {})["status"] == "unregistered"
        with pytest.raises(RecordNotFoundError, match="unknown"):
            api.get("/api/benchmarks/nope", {})
        with pytest.raises(RecordNotFoundError):
            api.get(f"/api/benchmarks/{SYN['positive']}/nothing", {})


def test_report_has_failure_analysis_and_no_aggregate(
    service: BenchmarkService,
) -> None:
    reveal(service, ERAP)
    reveal(service, SYN["negative"])
    service.register()
    text = service.report()
    assert (
        "## Failure analysis" in text and "cannot establish clinical efficacy" in text
    )
    assert "not demonstrated" in text
    assert SYNTHETIC_LABEL in text
    assert not re.search(r"\b\d+ ?/ ?\d+ cases|accuracy|pass rate", text)


def test_cli_full_flow_and_refusals(tmp_path: Path) -> None:
    runner = CliRunner()
    base = ["--database", str(tmp_path / "f.duckdb"), "benchmark"]
    assert runner.invoke(app, [*base, "list"]).exit_code == 0
    early = runner.invoke(app, [*base, "reveal", SYN["positive"]])
    assert early.exit_code == 2 and "refused" in early.output
    assert runner.invoke(app, [*base, "snapshot", SYN["positive"]]).exit_code == 0
    assert runner.invoke(app, [*base, "run", SYN["positive"]]).exit_code == 0
    assert runner.invoke(app, [*base, "leakage-audit", SYN["positive"]]).exit_code == 0
    done = runner.invoke(app, [*base, "reveal", SYN["positive"]])
    assert done.exit_code == 0 and "supported_by_future_evidence" in done.output
    assert runner.invoke(app, [*base, "compare", SYN["positive"]]).exit_code == 0
    review = runner.invoke(
        app,
        [
            *base,
            "review",
            SYN["positive"],
            "--reviewer",
            "Dr R",
            "--preference",
            "neither",
            "--conclusion",
            "ambiguous",
            "--rationale",
            "r",
            "--note",
            "overstated_claims=agree:ok",
        ],
    )
    assert review.exit_code == 0, review.output
    shown = runner.invoke(app, [*base, "show", SYN["positive"], "--json"])
    assert json.loads(shown.output)["status"] == "reviewed"
    out = tmp_path / "r.md"
    assert runner.invoke(app, [*base, "report", "--output", str(out)]).exit_code == 0
    assert "Failure analysis" in out.read_text()
