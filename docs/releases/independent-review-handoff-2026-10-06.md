# AXIS — Independent scientific review handoff

Status: READY FOR INDEPENDENT SCIENTIFIC REVIEW; not scientifically validated.
Evidence cutoff: 2026-10-05. Handoff date: 2026-10-06 (Europe/Lisbon).

## Frozen release identity

- Main: `d11128538a2723737eced46be73d40cef56f43db`.
- Previous main: `d491ebe47ee0c40dfaa3823a44a9decd1afae29d`.
- Scientific reference: `84ecc56e74747bdee12ecdf15b9a80bc760798f4`.
- Original consolidation candidate: `d4c42b262c7c7f3d9ff1b3db3562bee145d05304`.
- Final candidate: `0dc0ac13746f2e7107abc128d1471a7a99e3f64e`.
- [PR #1](https://github.com/JPais7/AXIS/pull/1) merged with a merge commit, preserving history and branches.
- [Published machine-readable freeze and acceptance matrix](https://github.com/JPais7/AXIS/pull/1#issuecomment-6004993577).
- [Post-merge CI](https://github.com/JPais7/AXIS/actions/runs/37384615921): Linux, macOS and Windows passed; each reports 785 passed and 2 skipped.

The only final CI repair preserves immutable audit bytes in Windows checkouts. It changes no scientific evidence, rules or conclusions. Main and candidate trees are identical; post-merge semantic replay reports no scientific differences.

## Decision requiring review

Canonical v1 `decision-state:1:cebbae3880aeec90` remains intact. Reproduced v2 `decision-state:2:212f995ecc55c989` correctly supersedes it. Classification remains DECISION STABLE. Critical uncertainty is `uncertainty:target_engagement`; recommended experiment is `decision:exp:chemical-genetic-engagement`.

The integrated scientific additions concern the BRADSHAW main-paper/assay-method provenance chain (including reference 22), context-specific biochemical and cellular evidence, and the existing v2 causal reassessment. This publication adds no evidence. Maben remains UNRESOLVED; compound-specific cellular occupancy and human axSpA efficacy have not been established. BRADSHAW learning remains MODEL_ELIGIBLE_WITH_CONDITIONS; no model was trained.

## Reviewer priorities

### Strongest supporting evidence and strongest concerns

The [frozen reassessment](https://github.com/JPais7/AXIS/blob/d11128538a2723737eced46be73d40cef56f43db/docs/erap1-bradshaw-final-reassessment-2026.md) links primary-source locators for BRADSHAW biochemical potency, cellular antigen presentation, the verified assay-method inheritance chain, and chemical/structural tractability. These support programme-level tractability and constrained within-context SAR, not human efficacy. Tinworth supports related biochemical SAR under partially comparable methods; structures support binding/construct interpretations within their recorded scope, not cellular occupancy.

The strongest concern is the gap between programme-level tractability and direct engagement of the historical Maben phenotype-producing compounds. Missing context, allotype/substrate dependence and non-interchangeable endpoints restrict quantitative transfer. The 2026 reassessment resolves the BRADSHAW main-method access blocker and improves tractability/context curation; it does not resolve this engagement-driven decision.

The exact recommended experiment is reproduced from `decision-state-v2.json` below in the review snapshot. Review its endpoint, matched-genotype design, exposure alignment and controls rather than interpreting its title alone.

1. Verify source provenance, assay-method inheritance and the legitimacy of each context-specific inference against accessible primary sources.
2. Review missing assay context, censoring, singleton measurements, numerical reconciliation, source conflicts and fitting exclusions.
3. Review allotype/substrate restrictions and cross-programme comparability: within-BRADSHAW biochemical comparisons are COMPARABLE; biochemical-versus-cellular and pooled allotype panels are NOT_COMPARABLE; BRADSHAW–Tinworth biochemical comparisons are PARTIALLY_COMPARABLE; BRADSHAW–Maben is NOT_COMPARABLE.
4. Check that biochemical/cellular SAR does not become a claim of occupancy, target engagement or clinical efficacy. Review the causal diff and proposed engagement experiment independently.
5. Adjudicate the six new claims currently marked source_assertion/pending_review. Automated tests are not scientific approval.

## Immutable reading pack

- [Current scientific state](https://github.com/JPais7/AXIS/blob/d11128538a2723737eced46be73d40cef56f43db/docs/erap1-current-scientific-state.md).
- [Consolidation closure](https://github.com/JPais7/AXIS/blob/d11128538a2723737eced46be73d40cef56f43db/docs/axis-repository-consolidation-2026.md).
- [BRADSHAW final reassessment](https://github.com/JPais7/AXIS/blob/d11128538a2723737eced46be73d40cef56f43db/docs/erap1-bradshaw-final-reassessment-2026.md).
- [Frozen evidence package](https://github.com/JPais7/AXIS/tree/d11128538a2723737eced46be73d40cef56f43db/axis/resources/evidence-integration/erap1-data-rich/2026/bradshaw-main-v3): inspect the manifest, assay matrix, uncertainty, numerical reconciliation, learning eligibility, claim delta, DecisionState v2 and causal diff.

## Reproduction and conditions

Use a fresh checkout of the exact main SHA above, Python 3.12 and the repository installation instructions. Run `PYTHONPATH=. python scripts/audit_axis_consolidation.py`. Frozen semantic replay needs neither licensed PDFs nor new scientific acquisition. Reviewing underlying licensed sources requires legitimate access; those PDFs are not redistributed.

Independent scientific approval remains pending. Historical source provenance retains personal paths and expired signed download URLs; these are not runtime prerequisites and need care before broader redistribution. The 462 inherited script lint findings outside the relevant CI scope remain documented, not silently repaired. Commercial v1 retains its historical coverage and known limitations. EAST-1 stays separate and unchanged.

No tag or PyPI release was created. Integration, consolidation and EAST-1 branches remain preserved. A possible future `axis-erap1-independent-review-2026` tag requires explicit authorization. The next action is independent scientific review, not another development phase or evidence refresh.

## Explicit independent-review questions

Critique factual accuracy; unsupported or overstated claims; material missing evidence within the cutoff and corpus scope; provenance quality; assay normalization/comparability; allotype/substrate handling; separation of biochemical activity, cellular phenotype and direct engagement; separation of historical Maben evidence from later programme-level tractability; defensibility of the critical uncertainty; whether the next experiment follows from the evidence; whether DECISION STABLE is defensible; and whether any material conclusion depends on an epistemic overclaim. This is a critique of the scientific decision and provenance, not a request to declare AXIS validated.

## Reviewer response template

Repeat for each issue (no numerical score):

| Field | Reviewer response |
|---|---|
| Severity | CRITICAL / MAJOR / MINOR / NO_ISSUE |
| Affected claim/artifact and locator | |
| Evidence/source and locator | |
| Rationale | |
| Recommended correction | |
| Changes the decision? | Yes / No / Uncertain, with explanation |

## Non-recursive freeze model

The scientific/runtime state is the immutable merge SHA `d11128538a2723737eced46be73d40cef56f43db`. One later closure commit carries only freeze records and review documentation. Its SHA is reported separately after commit, not embedded into its own hashed payload. The original freeze and checksum remain unchanged. The closure supplement binds current verification outputs and the reviewer snapshot by SHA-256. No runtime resource is added and no scientific state is updated.

## Exact repository-derived review snapshot

```json
{
  "critical_uncertainty": {
    "affected_explanation_ids": [
      "explanation:indirect",
      "explanation:off_target",
      "explanation:on_target"
    ],
    "category": "target_engagement",
    "decision_relevance": "decision_blocking",
    "epistemic_kind": "axis_inference",
    "evidence_refs": [
      [
        "edge",
        "biochemical"
      ],
      [
        "edge",
        "engagement"
      ],
      [
        "gap",
        "cellular:chen-dg013a-C1R.B27:gap"
      ],
      [
        "gap",
        "cellular:chen-dg013a-HeLa.B27:gap"
      ],
      [
        "gap",
        "cellular:maben-2:gap"
      ],
      [
        "gap",
        "cellular:maben-3:gap"
      ],
      [
        "cellular_assessment",
        "brad-v3:2025-b3p-design:hla"
      ],
      [
        "cellular_assessment",
        "brad-v3:bradshaw-21:hla"
      ],
      [
        "cellular_assessment",
        "brad-v3:bradshaw-40:hla"
      ],
      [
        "cellular_assessment",
        "brad-v3:hry-presentation:hla"
      ],
      [
        "cellular_assessment",
        "brad-v3:temponeras-mode:hla"
      ],
      [
        "cellular_assessment",
        "brad-v3:tinworth-21-KK:hla"
      ],
      [
        "cellular_assessment",
        "brad-v3:tinworth-21-compound6:hla"
      ],
      [
        "cellular_assessment",
        "brad-v3:tinworth-CT26:hla"
      ],
      [
        "cellular_assessment",
        "cellular:chen-dg013a-C1R.B27:hla"
      ],
      [
        "cellular_assessment",
        "cellular:chen-dg013a-HeLa.B27:hla"
      ],
      [
        "cellular_assessment",
        "cellular:maben-2:hla"
      ],
      [
        "cellular_assessment",
        "cellular:maben-3:hla"
      ]
    ],
    "fired_rules": [
      "DECISION-GAP-001",
      "DECISION-GAP-002"
    ],
    "id": "uncertainty:target_engagement",
    "question": "Do the phenotype-producing compounds directly engage ERAP1 in cells at those exposures?",
    "rationale": "Engagement is the missing link between biochemical activity and the cellular phenotype.",
    "reasons": [
      "biochemical activity is supported",
      "a compound-treated cellular phenotype is supported",
      "direct cellular engagement is not assessed",
      "selectivity is unresolved, so an off-target explanation remains viable",
      "5 of 66 compounds have both biochemical activity and a cellular phenotype; evidence is not pooled across compounds",
      "4 phenotype-producing perturbagen(s) have unresolved chemical identity and cannot be linked to any compound's biochemical data"
    ],
    "resolvability": "directly_testable",
    "scope_breakdown": [],
    "scope_id": null,
    "scope_type": "target",
    "source_gap_ids": [
      "cellular:chen-dg013a-C1R.B27:gap",
      "cellular:chen-dg013a-HeLa.B27:gap",
      "cellular:maben-2:gap",
      "cellular:maben-3:gap"
    ],
    "status": "open"
  },
  "recommended_experiment": {
    "consequence_categories": [
      "change_mechanistic_model",
      "investigate_context_dependence",
      "require_replication",
      "strengthen_current_strategy",
      "weaken_current_strategy"
    ],
    "cost": "not provided",
    "discrimination": {
      "low_discrimination": false,
      "rule": "DECISION-EXP-001",
      "separated_pairs": [
        [
          "explanation:indirect",
          "explanation:off_target"
        ],
        [
          "explanation:indirect",
          "explanation:on_target"
        ],
        [
          "explanation:off_target",
          "explanation:on_target"
        ]
      ]
    },
    "distinct_consequences": 5,
    "epistemic_kind": "ai_suggestion",
    "excluded": null,
    "experiment_id": "decision:exp:chemical-genetic-engagement",
    "falsification": {
      "falsifying": true,
      "preferred_explanations": [
        "explanation:on_target"
      ],
      "rule": "DECISION-EXP-005",
      "weakening_scenarios": [
        "decision:exp:chemical-genetic-engagement:s2",
        "decision:exp:chemical-genetic-engagement:s3"
      ]
    },
    "feasibility": {
      "level": "unknown",
      "missing": [],
      "note": "Feasibility not assessed against local resource constraints."
    },
    "interpretability": {
      "level": "high",
      "met": [
        "at least three interpretable outcome scenarios",
        "endpoint is direct or target-proximal",
        "a negative control is specified",
        "a stated confounder is addressed"
      ],
      "rule": "DECISION-EXP-002"
    },
    "low_discrimination": false,
    "profile": {
      "addressed_gap_ids": [
        "cellular:chen-dg013a-HeLa.B27:gap",
        "cellular:chen-dg013a-C1R.B27:gap",
        "cellular:maben-2:gap",
        "cellular:maben-3:gap"
      ],
      "complexity": "high",
      "confounders_addressed": [
        "off-target activity (genetic comparison)",
        "exposure-dependent toxicity (viability measured separately)"
      ],
      "considered_for": [
        "target_engagement",
        "target_dependency"
      ],
      "context_requirements": {
        "erap1_allotype": "report and match across arms",
        "hla": "HLA-B27 subtype to be chosen and reported"
      },
      "controls_negative": [
        "vehicle",
        "ERAP1-null or ERAP1-depleted arm of the same background",
        "structurally related inactive analogue, if one is established (none identified in the curated corpus)"
      ],
      "controls_positive": [
        "none established in the curated corpus; a reference ERAP1 ligand with demonstrated cellular engagement would be required"
      ],
      "cost": null,
      "disease_relevance": "molecular HLA-B27 context only; not disease rescue",
      "experiment_id": "decision:exp:chemical-genetic-engagement",
      "limitations": [
        "Does not resolve selectivity against other proteins",
        "Single cellular system; disease relevance and patient-derived cells are not addressed",
        "A null or rescue model does not reproduce partial pharmacological inhibition"
      ],
      "prerequisites": [
        [
          "validated compound identity (the DG013A label is not resolved to one substance)",
          "not_established"
        ],
        [
          "cellular target-engagement readout",
          "not_established"
        ],
        [
          "ERAP1-null and rescue HLA-B27 model",
          "not_established"
        ],
        [
          "HLA-B27-positive cell line",
          "available_in_corpus"
        ]
      ],
      "primary_endpoint": "Compound-dependent ERAP1 engagement at the exposures that produce the phenotype, together with phenotype attenuation in ERAP1-null cells",
      "purpose": "discriminate_mechanism",
      "required": {
        "assays": [
          "cellular engagement assay",
          "HLA-B27 surface phenotype assay"
        ],
        "models": [
          "HLA-B27-positive ERAP1-null and rescue cells"
        ],
        "reagents": [
          "engagement readout reagent",
          "inactive analogue"
        ]
      },
      "role": "mechanism_discrimination",
      "secondary_endpoints": [
        "HLA-B27 free-heavy-chain surface phenotype",
        "cell viability at the tested exposures",
        "restoration of phenotype after ERAP1 re-expression"
      ],
      "target_proximity": "target_proximal",
      "time_estimate": "unknown"
    },
    "rank": 1,
    "reason": "recommended: separates 3 pair(s) of viable explanations; able to weaken a preferred explanation; 5 distinct next actions across outcomes; interpretability high; target proximal endpoint",
    "result_claim_id": null,
    "role_label": "mechanism discrimination",
    "status": "proposed",
    "tied_with": [],
    "title": "Matched-genotype chemical-genetic experiment with an engagement readout"
  }
}
```
