"""One-time reviewed-input freeze; default invocation verifies offline only.

Inputs below are bounded, source-linked AI curation, not researcher acceptance.
--freeze refuses to overwrite an existing package and only runs on cutoff day.
No downloads, fabricated future results, historical package changes or DB writes.
"""

import argparse
import importlib.metadata
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from axis.decision import rules
from axis.validation import prospective
from axis.validation.package import sha256_file, write_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "axis/resources/validation/prospective/erap1-east1/v1"
BASE = "d491ebe47ee0c40dfaa3823a44a9decd1afae29d"
CUTOFF = "2026-10-05"
CASE = "AXIS-PROSPECTIVE-ERAP1-EAST1-001"
RETRIEVED = "2026-10-05T17:33:06+00:00"


def source(
    identifier: str,
    category: str,
    url: str,
    public: str,
    access: str,
    *,
    dates: dict[str, str | None] | None = None,
    checksum: str | None = None,
    checksum_scope: str = "response_bytes",
) -> dict:
    return {
        "id": identifier,
        "evidence_class": category,
        "url": url,
        "available_by": public,
        "availability_kind": "bounded",
        "availability_basis": "Dated publication/presentation or retained observation by cutoff",
        "retrieved_at": RETRIEVED,
        "access": access,
        "dates": {
            "study_date": None,
            "publication_date": None,
            "conference_presentation_date": None,
            "registry_update_date": None,
            "sponsor_announcement_date": None,
            **(dates or {}),
        },
        "response_sha256": checksum,
        "checksum_scope": checksum_scope,
        "review_status": "pending_review",
    }


def make_inputs() -> dict:
    registry = source(
        "NCT07047703",
        "trial_registry",
        "https://clinicaltrials.gov/api/v2/studies/NCT07047703",
        "2026-09-18",
        "Official structured API; protocol/outcomes only; hasResults=false",
        dates={
            "study_date": "2025-07-28",
            "publication_date": "2025-07-02",
            "registry_update_date": "2026-09-18",
        },
        checksum="a1e93c8d5ad40b09affe79efd546871dbb222b64fa1099e847d167a68a318e0e",
    )
    conference = source(
        "FOCIS2025:W146",
        "conference_evidence",
        "https://focis-2025.eventscribe.net/fsPopup.asp?PresentationID=1615278&mode=presInfo",
        "2025-06-25",
        "Official HTML abstract via web retrieval; full poster not obtained; direct HTTP 403",
        dates={"conference_presentation_date": "2025-06-25"},
        checksum_scope="No raw response retained; compact paraphrase snapshot separately hashed",
    )
    sponsor = source(
        "GREYWOLF:2026-09-08",
        "sponsor_reported",
        "https://rss.globenewswire.com/news-release/2026/09/08/3357312/0/en/greywolf-therapeutics-doses-first-participants-with-axspa-in-novel-erap1-inhibitor-trial.html",
        "2026-09-08",
        "Sponsor-authored dated release, syndicated by GlobeNewswire",
        dates={
            "sponsor_announcement_date": "2026-09-08",
            "publication_date": "2026-09-08",
        },
        checksum="b7816333792b2c4bcd25689e3ce87dac01acb5b33f7f950ff78df18f1b7d1671",
    )
    programme = source(
        "GREYWOLF:GRWD0715",
        "sponsor_reported",
        "https://www.greywolftherapeutics.com/grwd0715",
        CUTOFF,
        "Undated mutable programme page; observed by cutoff, not dated to nominal August update",
        checksum="5656826be90729d0fa1fa8ec1327cc5e258e6a25f683f14e9738f0a8a5ec3872",
    )
    ctis = source(
        "CTIS:2025-521315-39-00",
        "trial_registry",
        "https://euclinicaltrials.eu/ctis-public/view/2025-521315-39-00",
        CUTOFF,
        "PARTIAL ACCESS: official search metadata identifies trial; HTTP body is app shell, not adjudicated protocol",
        checksum="8734cbb42cde74ad98eb8a1a0eaf0965e9e15b059616a06c0ba5a2d466308d2d",
        checksum_scope="HTML app shell only; not scientific evidence body",
    )
    discovery = json.loads(
        (ROOT / "axis/resources/discovery/erap1-axspa/v1/manifest.json").read_text()
    )
    baseline_sources = []
    for s in discovery["sources"]:
        baseline_sources.append(
            source(
                s["source_id"],
                "peer_reviewed_primary",
                s["source_uri"],
                f"{s['year']}-12-31",
                "Inherited frozen main curation; no new full-text adjudication",
                checksum_scope="Referenced baseline resource checksums; year-end is availability upper bound, not publication day",
            )
        )
    claims = []

    def claim(
        identifier: str,
        src: dict,
        statement: str,
        limits: str,
        layer: str,
        intervention: str | None = "GRWD0715",
    ) -> None:
        claims.append(
            {
                "id": identifier,
                "source_id": src["id"],
                "evidence_class": src["evidence_class"],
                "knowledge_kind": "source_assertion",
                "review_status": "pending_review",
                "intervention": intervention,
                "statement": statement,
                "limits": limits,
                "layer": layer,
            }
        )

    claim(
        "R1",
        registry,
        "EAST1 / GRWD0715-AS-01 is a recruiting Phase I/II programme: A healthy-volunteer SAD, B patient MAD (28 days), C open-label safety extension, D randomized placebo-controlled patient expansion (up to 12 weeks). HLA-B27-positive axSpA is required; estimated enrollment 140; registry has no results.",
        "Planned design and enrollment, not observations; global allocation/masking fields cannot replace part-specific descriptions; selection excludes some comorbid contexts.",
        "trial",
    )
    claim(
        "R2",
        registry,
        "Part B biologically active dose can be selected using steady-state mean Cavg >=1166 ng/mL, preliminary clinical activity or supporting PD. Exposure threshold uses a predicted relative IC50 and oncology GRWD5769 PK-PD modelling.",
        "A dose-selection proxy is not measured GRWD0715 engagement; GRWD5769 and GRWD0715 are distinct compounds and indications.",
        "engagement",
    )
    claim(
        "R3",
        registry,
        "Clinical, MRI and PK outcomes are planned. Primary completion April 2028 and study completion September 2028 are estimates; no public reveal dates are promised.",
        "Registered endpoints do not establish PD, benefit or an acceptable window.",
        "clinical",
    )
    claim(
        "F1",
        conference,
        "The abstract reports inhibition of ERAP1 processing of putative GLRB, HelQ and SEC14L2 autoantigen precursors by GRWD0715, with IC50 60–400 pM.",
        "Abstract only: construct/allotype, substrate sequences, complete assay conditions, replicates, uncertainty and comparable selectivity controls unavailable. Potency is source-reported, not normalized assay evidence.",
        "biochemical",
    )
    claim(
        "F2",
        conference,
        "The abstract reports reduced 7–9-residue HLA-B*27 peptides in joint-relevant cell lines exposed to GRWD0715.",
        "Cell identities, HLA subtype, allotype, ERAP2, concentration/time, free exposure and quantitative peptide-level methods are not supplied.",
        "hla",
    )
    claim(
        "F3",
        conference,
        "The abstract reports suppression of axSpA-associated-TCR-positive CD8 activation dependent on HLA-B*27 and autopeptide; P2-anchor interpretation is in silico.",
        "TCR sequences, controls/rescue, donor counts, assay details and numerical functional results unavailable. Neither target occupancy nor disease causality is established.",
        "immune",
    )
    claim(
        "S1",
        sponsor,
        "Sponsor reports dose-proportional PK and ERAP1 engagement in the completed healthy-volunteer SAD portion, with no observed safety/tolerability concerns.",
        "No public quantitative engagement, assay methodology, tissue coverage, exposure–engagement relationship, participant-level PK or complete safety dataset. Preliminary human target engagement — sponsor reported; independent methodological adjudication unavailable.",
        "human",
    )
    claim(
        "S2",
        sponsor,
        "Sponsor announces first patient dosing in MAD, which is ongoing; PK/PD, biomarkers and preliminary clinical data are expected to inform a later placebo-controlled portion.",
        "Patient dosing and future plans are not patient efficacy results. No clinical benefit demonstrated in this release.",
        "clinical",
    )
    claim(
        "P1",
        programme,
        "The programme page identifies GRWD0715 as the oral ERAP1 autoimmunity programme.",
        "Mutable undated sponsor material; duplicate programme context, not independent replication; marketing cure wording not adopted.",
        "programme",
    )
    claim(
        "EU1",
        ctis,
        "Official CTIS public metadata associates 2025-521315-39-00 with GRWD0715-AS-01.",
        "Full structured EU protocol not accessed; EU dates/participant counts not pooled with global registry. No result claims extracted.",
        "trial",
    )
    for c in discovery["claims"]:
        s = next(x for x in baseline_sources if x["id"] == c["source_id"])
        claim(
            c["claim_id"],
            s,
            c["statement"],
            "Inherited main AI curation remains pending independent review; study-specific context does not establish clinical direction.",
            c["domain"],
            None,
        )
    positions = []

    def position(identifier: str, status: str, ids: list[str], rationale: str) -> None:
        positions.append(
            {
                "id": identifier,
                "status": status,
                "claim_ids": ids,
                "rationale": rationale,
                "knowledge_kind": "axis_inference",
                "review_status": "pending_review",
            }
        )

    position(
        "target_biology",
        "supported",
        ["AXIS-ERAP1-CURATED-C01", "AXIS-ERAP1-CURATED-C03"],
        "Genetic and processing support inherited from main; no new clinical proof.",
    )
    position(
        "erap1_hla_b27",
        "supported",
        ["AXIS-ERAP1-CURATED-C01", "AXIS-ERAP1-CURATED-C05"],
        "Genetic interaction and peptide processing in defined systems; broader axSpA extrapolation limited.",
    )
    position(
        "context_dependence",
        "supported_important",
        [
            "AXIS-ERAP1-CURATED-C04",
            "AXIS-ERAP1-CURATED-C07",
            "AXIS-ERAP1-CURATED-C08",
            "AXIS-ERAP1-CURATED-C12",
        ],
        "Substrate/variant sensitivity and divergent cell-model findings oppose a universal inhibition-benefit direction. Recent unmerged addendum excluded; latest allotype literature not newly adjudicated here.",
    )
    position(
        "pharmacological_tractability",
        "preliminary_support",
        ["F1", "S1"],
        "Programme-specific conference inhibition and sponsor human signal strengthen feasibility provisionally, not definitive tractability across tissues/allotypes.",
    )
    position(
        "molecular_pharmacology",
        "preliminary_support",
        ["F2", "F3"],
        "Conference-only peptide and CD8 observations; full methods absent.",
    )
    position(
        "human_pk",
        "preliminary_sponsor_reported",
        ["S1"],
        "Qualitative dose-proportional PK without numerical independent adjudication.",
    )
    position(
        "human_engagement",
        "preliminary_sponsor_reported",
        ["S1", "R2"],
        "Sponsor claim retained; exposure proxy not direct measurement.",
    )
    position(
        "human_disease_pd",
        "not_established",
        ["R3", "S2"],
        "Endpoints planned, no public patient PD results identified in bounded sources.",
    )
    position(
        "therapeutic_benefit",
        "not_established",
        ["S2", "R3"],
        "No disease-modifying benefit established.",
    )
    position(
        "human_axspa_efficacy",
        "not_demonstrated",
        ["S2", "R1"],
        "Registry hasResults=false and sponsor reports dosing, not efficacy; private results unknown.",
    )
    position(
        "optimal_subgroup",
        "unresolved",
        ["R1", "AXIS-ERAP1-CURATED-C07"],
        "HLA-B27 selection alone does not identify responsive allotype/subtype/ERAP2 subgroup.",
    )
    position(
        "therapeutic_window",
        "unresolved",
        ["S1", "R3"],
        "Healthy single-dose sponsor tolerability does not establish sustained patient window.",
    )

    uncertainties = [
        (
            "U1",
            "target_engagement",
            "Sufficient sustained human ERAP1 engagement at achievable exposure",
            [],
        ),
        (
            "U2",
            "assay_translation",
            "Predicted human antigen-processing/immunological PD",
            ["U1"],
        ),
        (
            "U3",
            "mechanistic_bridge",
            "PD changes alter disease-relevant immune biology",
            ["U2"],
        ),
        ("U4", "clinical_translation", "Meaningful axSpA benefit", ["U3"]),
        (
            "U5",
            "genetic_context",
            "ERAP1/HLA/ERAP2/substrate/tissue-dependent response",
            [],
        ),
        ("U6", "other", "Acceptable sustained therapeutic window", ["U1"]),
    ]
    hypotheses = [
        (
            "H1",
            "On-target therapeutic chain",
            "Engagement changes pathogenic antigen processing and meaningfully benefits defined axSpA contexts.",
        ),
        (
            "H2",
            "Engagement and PD without clinical benefit",
            "Molecular effects occur without material disease improvement.",
        ),
        (
            "H3",
            "Context-restricted benefit",
            "Effects are confined to specific biological subgroups.",
        ),
        (
            "H4",
            "Incomplete mechanistic bridge",
            "Peptide/immune effects are real but insufficiently causal for disease activity.",
        ),
        (
            "H5",
            "Therapeutic-window limitation",
            "Required intensity/duration cannot be safely sustained.",
        ),
    ]
    discriminators = []

    def discriminator(
        identifier: str,
        measurement: str,
        u: list[str],
        h: list[str],
        strong: str,
        weak: str,
        ambiguous: str,
        invalid: str,
        positive: str,
        negative: str,
    ) -> None:
        discriminators.append(
            {
                "id": identifier,
                "measurement": measurement,
                "uncertainty_ids": u,
                "hypothesis_ids": h,
                "strengthens": strong,
                "weakens": weak,
                "ambiguous": ambiguous,
                "non_interpretable": invalid,
                "consequences": {
                    "strengthens": positive,
                    "weakens": negative,
                    "ambiguous": "require_orthogonal_validation",
                    "non_interpretable": "require_replication",
                },
                "knowledge_kind": "ai_suggestion",
                "review_status": "pending_review",
            }
        )

    discriminator(
        "D1",
        "Quantitative, target-specific engagement with PK/free exposure and time coverage in relevant human compartments",
        ["U1"],
        ["H1", "H2", "H5"],
        "Validated sustained engagement at tolerable achievable exposure, controls excluding surrogate-only interpretation.",
        "Insufficient engagement despite adequate systemic exposure; question compound/distribution/coverage, not all ERAP1 biology.",
        "Sponsor qualitative claim, Cavg proxy, single time point or unknown compartment/duration.",
        "Unvalidated assay, interference, missing exposure or sampling information.",
        "advance_to_next_evidence_layer",
        "weaken_current_strategy",
    )
    discriminator(
        "D2",
        "Paired engagement and immunopeptidomics / disease-linked antigen and CD8 PD over dose/time",
        ["U2", "U3"],
        ["H1", "H2", "H4"],
        "Engagement precedes reproducible expected peptide and immune changes in disease-relevant systems, with orthogonal controls.",
        "Adequate sustained engagement repeatedly fails to produce prespecified PD, or PD lacks disease-linked immune effects.",
        "Bulk nonspecific HLA shift, surrogate-only biomarker or discordant timing/context.",
        "Batch effects, inadequate detection, missing paired exposure/engagement, unreliable controls.",
        "advance_to_next_evidence_layer",
        "change_mechanistic_model",
    )
    discriminator(
        "D3",
        "Predefined clinical outcomes (ASDAS/ASAS40 and MRI where applicable), effect size/uncertainty, concurrent engagement/PD, appropriate randomized controls",
        ["U4", "U3"],
        ["H1", "H2", "H4"],
        "Credible clinically meaningful controlled improvement coherent with prior engagement/PD; reproducible effects and timing.",
        "Adequate power/duration and confirmed engagement/PD repeatedly yield no meaningful controlled benefit.",
        "Uncontrolled preliminary signal, underpowered null, multiplicity, treatment confounding or insufficient duration.",
        "Major missingness, protocol violations, unreliable endpoints or absent comparator.",
        "strengthen_current_strategy",
        "deprioritize_current_strategy",
    )
    discriminator(
        "D4",
        "Prespecified ERAP1 allotype, HLA-B27 subtype, ERAP2, substrate/tissue and disease-stage interaction analyses",
        ["U5"],
        ["H1", "H2", "H3", "H4"],
        "Reproducible biologically coherent subgroup interaction with exposure/engagement balance and multiplicity control.",
        "Replicated adequately measured contexts fail to support proposed responsive subgroup; not universal failure by one subgroup.",
        "Post hoc small subgroup, incomplete genotyping or confounding; retain as hypothesis.",
        "Misclassified genotype, inadequate subgroup size or incompatible assays.",
        "investigate_context_dependence",
        "change_mechanistic_model",
    )
    discriminator(
        "D5",
        "Dose/time matched adverse events, reversibility and sustained target coverage in patients",
        ["U6", "U1"],
        ["H1", "H5"],
        "Meaningful sustained PD/engagement compatible with acceptable patient safety across relevant duration.",
        "Required pharmacology cannot be maintained because of safety/tolerability; distinguish target vs compound/modality risk.",
        "Healthy single-dose tolerability, insufficient follow-up or poorly attributed events.",
        "Incomplete safety capture or unknown actual exposure/dose adherence.",
        "continue_current_strategy",
        "stop_for_now",
    )
    scenarios = [
        (
            "A",
            ["U1", "U2", "U3", "U4"],
            ["H1"],
            "Adequate exposure, sustained engagement, expected PD and credible clinical improvement",
            "Strongest support for the therapeutic chain; still assess subgroup and safety.",
            "strengthen_current_strategy",
        ),
        (
            "B",
            ["U3", "U4"],
            ["H2", "H4"],
            "Engagement and PD without meaningful clinical improvement under interpretable conditions",
            "Weakens PD-to-disease translation, not target engagement.",
            "deprioritize_current_strategy",
        ),
        (
            "C",
            ["U2", "U3"],
            ["H4"],
            "Engagement without expected disease-relevant PD",
            "Weakens proposed PD bridge if assays, duration and context are adequate.",
            "change_mechanistic_model",
        ),
        (
            "D",
            ["U1"],
            ["H1", "H5"],
            "Adequate systemic exposure but insufficient engagement",
            "Questions compound, compartment exposure, assay or achievable coverage; does not universally disprove ERAP1 biology.",
            "weaken_current_strategy",
        ),
        (
            "E",
            ["U5"],
            ["H3"],
            "Engagement, PD and clinical signal confined to coherent biological subgroup",
            "Refine context-dependent hypothesis; prespecified versus exploratory interaction stays explicit.",
            "investigate_context_dependence",
        ),
        (
            "F",
            ["U6", "U1"],
            ["H5"],
            "Required sustained pharmacology limited by safety/tolerability",
            "Weakens current therapeutic strategy/modality; not automatic falsification of target biology.",
            "stop_for_now",
        ),
        (
            "G",
            ["U1", "U2", "U3", "U4", "U5", "U6"],
            ["H1", "H2", "H3", "H4", "H5"],
            "Technically or biologically non-interpretable results",
            "No forced directional change; retain/refine uncertainty.",
            "require_replication",
        ),
    ]
    return {
        "source-index.json": {
            "sources": [
                registry,
                conference,
                sponsor,
                programme,
                ctis,
                *baseline_sources,
            ],
            "search_log": [
                {
                    "database": "Europe PMC",
                    "query": '(GRWD0715 OR "GRWD 0715" OR "GRWD-0715") AND FIRST_PDATE:[1900-01-01 TO 2026-10-05]',
                    "hit_count": 0,
                    "retrieved_at": "2026-10-05T17:32:37.983962+00:00",
                    "response_sha256": "a53e46fa6c07ddba2c154d4142fa9e2dc70374a5bf72ed519e72b06ad61b4b6a",
                    "interpretation": "No indexed hits in this bounded query, not proof no publication exists.",
                }
            ],
            "other_presentations": "No additional material presentation identified in focused public search; FOCIS programme/abstract-book entries duplicate W146, not independent evidence.",
            "patents": "Sponsor reports a US grant but verified chemical identity/method mapping unavailable. No patent example is asserted to be GRWD0715. Not necessary to expand discovery search for this freeze.",
        },
        "evidence-snapshot.json": {
            "claims": claims,
            "positions": positions,
            "unavailable": [
                "FOCIS full poster/methods",
                "quantitative human engagement and assay",
                "patient PD/efficacy data",
                "independently mapped chemical structure",
                "full structured CTIS protocol",
            ],
            "historical_compound_boundary": "GRWD0715 cannot establish cellular engagement for Maben compounds, DG013A or oncology GRWD5769. The canonical historical engagement uncertainty remains unchanged.",
        },
        "prospective-discriminators.json": {"items": discriminators},
        "outcome-scenarios.json": {
            "items": [
                {
                    "id": s[0],
                    "uncertainty_ids": s[1],
                    "hypothesis_ids": s[2],
                    "observation": s[3],
                    "interpretation": s[4],
                    "consequence": s[5],
                    "review_status": "pending_review",
                    "knowledge_kind": "ai_suggestion",
                }
                for s in scenarios
            ]
        },
        "case.json": {
            "case_id": CASE,
            "target": "ERAP1",
            "disease": "axial spondyloarthritis",
            "intervention": "GRWD0715",
            "clinical_programme": "EAST-1 / GRWD0715-AS-01 / NCT07047703",
            "cutoff": CUTOFF,
            "question": "Which public evidence supports context-specific ERAP1 modulation, what remains uncertain, and which future EAST-1 observations change that position?",
            "hypothesis": "Pharmacological ERAP1 modulation may alter HLA-B27-associated peptide processing and downstream immune recognition in biologically defined axSpA contexts.",
            "knowledge_kind": "ai_suggestion",
            "hypothesis_origin": "AI-drafted working formulation, not investigator-approved",
            "review_status": "pending_review",
            "current_position": "Biological rationale and programme-specific preliminary molecular/human signals warrant discriminating tests, not a trial-success prediction. Human disease-relevant PD, therapeutic benefit and axSpA efficacy are not established; responsive context and sustained window remain unresolved.",
            "context_variables": [
                "ERAP1 allotype",
                "HLA-B27 subtype",
                "ERAP2",
                "peptide substrate",
                "cell/tissue",
                "inhibitor mechanism",
                "degree of inhibition",
                "duration of inhibition",
                "disease stage",
            ],
            "hypotheses": [
                {
                    "id": h[0],
                    "label": h[1],
                    "statement": h[2],
                    "status": "unresolved",
                    "knowledge_kind": "ai_suggestion",
                    "review_status": "pending_review",
                }
                for h in hypotheses
            ],
            "uncertainties": [
                {
                    "id": u[0],
                    "category": u[1],
                    "question": u[2],
                    "depends_on": u[3],
                    "status": "open",
                    "review_status": "pending_review",
                }
                for u in uncertainties
            ],
            "dependency_modifiers": {
                "U5": ["U1", "U2", "U3", "U4"],
                "U6": ["U1", "U2", "U3", "U4"],
            },
            "critical_uncertainty_id": "U1",
            "critical_basis": "First unadjudicated programme-level gate: sustained quantitative human engagement. PD, disease bridge, subgroup and window remain co-material, not replaced by historical compound question.",
            "off_target_boundary": "Specificity and interference controls remain required for programme attribution; absence of disclosed selectivity methods is not proof of off-target activity.",
            "strengthening_conditions": [d["strengthens"] for d in discriminators],
            "weakening_conditions": [d["weakens"] for d in discriminators],
            "falsification_scope": "Adequate sustained engagement repeatedly lacking PD or controlled benefit weakens this therapeutic chain in tested contexts; safety-limited coverage weakens modality/compound. No universal target rejection from inadequate exposure, one subgroup or invalid assays.",
            "future_reveal_layers": [
                {"label": k, "layer": v, "date": None}
                for k, v in [
                    ("T1", "new PK/engagement"),
                    ("T2", "PD/translational biomarkers"),
                    ("T3", "preliminary patient clinical data"),
                    ("T4", "randomized/controlled efficacy"),
                ]
            ],
            "reveal_policy": "Actual public sequence governs, not these nominal labels. Store each helper output as a new checksummed artifact; original T0 is read-only. Causal case-state proposals require independent adjudication before any separately versioned canonical DecisionState update through the existing Experimental Results Loop.",
            "status": "LONG-HORIZON PROSPECTIVE CASE / FROZEN BEFORE FUTURE PATIENT RESULTS",
            "future_patient_results_identified": False,
            "limit": "Bounded searched public sources only; private results and unknown undiscovered sources cannot be excluded. Scientific content pending independent review.",
            "commercialization_blocker": False,
            "short_horizon_next": "Separate future design-partner case: unresolved decision, genuinely unknown outcome, external experiment owner, pre-result-only AXIS input, resolution within months, import via existing Experimental Results Loop. Not implemented here.",
        },
    }


def freeze() -> None:
    if (OUT / "manifest.json").exists():
        raise SystemExit("Immutable package exists: verify it; never overwrite T0")
    now = datetime.now(UTC)
    if now.date().isoformat() != CUTOFF:
        raise SystemExit(
            "Freeze must be made on cutoff day, never retrospectively dated"
        )
    documents = make_inputs()
    canonical_path = ROOT / "reports/commercial/erap1-axspa/v1/state-snapshot.json"
    canonical = json.loads(canonical_path.read_text())["decision"]
    baseline = {
        "main_sha": BASE,
        "branch": "validation/prospective-east1-erap1-axspa",
        "clean_confirmed_before_edits_at": "2026-10-05T17:32:04+00:00",
        "clean_after_cache_archive": True,
        "axis_version": "0.2.1.dev0",
        "recent_evidence_addendum_on_main": False,
        "excluded_unmerged_addendum": "codex/erap1-recent-evidence-addendum-2020-2026 @ 8702046a995ce7f09b9c15b3bd9cd004e4d8cd21; no resources imported",
        "resource_manifests": {
            str(p.relative_to(ROOT)): {
                "sha256": sha256_file(p),
                "version": json.loads(p.read_text()).get(
                    "package_version", json.loads(p.read_text()).get("version")
                ),
            }
            for p in (ROOT / "axis/resources").rglob("manifest.json")
            if "erap1" in str(p) and "validation/prospective" not in str(p)
        },
        "python": sys.version,
        "dependencies": {
            n: importlib.metadata.version(n)
            for n in [
                "pytest",
                "ruff",
                "mypy",
                "numpy",
                "scipy",
                "duckdb",
                "rdkit",
                "gemmi",
                "httpx",
                "build",
            ]
        },
    }
    if (
        subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        != BASE
    ):
        raise SystemExit("Wrong baseline commit")
    case = documents["case.json"]
    case.update(
        {
            "frozen_at": now.isoformat(),
            "baseline": baseline,
            "canonical_decision": {
                "path": str(canonical_path.relative_to(ROOT)),
                "sha256": sha256_file(canonical_path),
                "id": canonical["id"],
                "evidence_digest": canonical["evidence_digest"],
                "critical_uncertainty_id": canonical["critical_uncertainty_id"],
                "recommended_experiment_id": canonical["recommended_experiment_id"],
            },
            "axis_version": "0.2.1.dev0",
            "rules_version": rules.RULES_VERSION,
            "rules_fingerprint": rules.fingerprint(),
            "adapter_version": prospective.ADAPTER_VERSION,
            "adapter_fingerprint": prospective.fingerprint(),
        }
    )
    for name, document in documents.items():
        write_json(OUT / name, document)
    bundle = {"manifest": {"package_id": CASE}, **documents}
    write_json(OUT / "t0-state.json", prospective.replay(bundle))
    files = {p.name: sha256_file(p) for p in OUT.glob("*.json")}
    write_json(
        OUT / "manifest.json",
        {
            "schema": prospective.SCHEMA,
            "package_id": CASE,
            "package_version": "1.0.0",
            "frozen_at": now.isoformat(),
            "review_status": "pending_review",
            "files": files,
        },
    )
    (OUT / "manifest.sha256").write_text(sha256_file(OUT / "manifest.json") + "\n")
    verify()


def verify() -> None:
    bundle = prospective.load(OUT)
    state = prospective.replay(bundle)
    if state != bundle["t0-state.json"]:
        raise SystemExit("Deterministic replay mismatch")
    print(
        json.dumps(
            {
                "case_id": CASE,
                "frozen_at": bundle["case.json"]["frozen_at"],
                "t0_fingerprint": state["fingerprint"],
                "manifest_sha256": sha256_file(OUT / "manifest.json"),
                "review_status": "pending_review",
                "offline_replay": "PASS",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    freeze() if args.freeze else verify()
