# AXIS ERAP1 DATA-RICH INTEGRATION — FINAL SCIENTIFIC CLOSURE

**Outcome C — SCIENTIFIC REASSESSMENT BLOCKED.** Cutoff: 2026-10-05.

The bounded source adjudication produces an explicit refusal, not a completed
integrated reassessment. It establishes neither DECISION CHANGED nor DECISION
STABLE. Unknown AFTER values are represented as null, not a misleading NO.

## Repository state

- Branch: `codex/erap1-data-rich-evidence-integration-2026`.
- Starting SHA: `c901d3061a7f0d3d4f3169da99b7ad528834d9b9`.
- Final committed SHA at this handoff: the same `c901d3061a7f0d3d4f3169da99b7ad528834d9b9`.
- Baseline main: `d491ebe47ee0c40dfaa3823a44a9decd1afae29d`.
- Exact remote branch/main references verified with `git ls-remote`; both match.
- Starting tree clean; closure artifacts, builder, tests and this report are new,
  uncommitted changes. No commit, push, merge, main change or history rewrite.
- Frozen `2026/v1/`, historical DecisionState, Chemical Learning, commercial brief
  and EAST-1 prospective work preserved. New artifacts are in `2026/closure-v1/`.

## Evidence integrated

The existing `axis.domain.models.Claim` and `EvidenceStore.claims` roundtrip 34
immutable claims: 22 bounded source/context claims and 12 structural observations.
Each envelope preserves source class separately from epistemic kind, source
artifact hash/URL, locator, polarity, context, scope and limitations. All newly
assisted claims remain `pending_review`; storage is not review approval and generic
claims are not silently substituted for cellular Decision Engine assessments.

Admitted source facts/context:

- Hryczanek 2024, DOI `10.1021/acsmedchemlett.4c00401`: Hap2/YTAFTIPSI biochemical
  assay context, complete accessible HeLa presentation protocol, qualitative
  counterscreens and explicit compound-to-PDB associations.
- Hutchinson 2021, DOI `10.1016/j.jbc.2021.100443`: substrate-dependent allotype
  behaviour; not a universally portable enzyme-activity ordering.
- Wang 2022, DOI `10.3390/cells11152427`: Taiwanese association/discovery context,
  863 cases/1438 controls and separate 45-person coding-variant discovery subset;
  no global extrapolation or therapeutic direction from association.
- Temponeras 2023, DOI `10.1002/eji.202350449`: A375 clerodane-inhibitor versus
  KO design and source-reported differences. Importantly, although initially three
  biological replicates were grown per condition, one WT and one KO replicate were
  excluded for low signal: analysed biological n is two for WT/KO, three for inhibitor.
  The 48-hour MTT control is not a six-day exposure-matched viability experiment.
- DOI `10.1016/j.mcpro.2025.100964`: A375 B3P-site compound-3 versus KO design,
  ERAP2 context and the clone-1G5 partial-duplication limitation. Source peptide
  classifications remain distinct from independent AXIS statistics.
- Tran, DOI `10.1002/art.42327`: mixed HLA-B27-transgenic rat phenotype, including
  arthritis 12/37 versus 4/34, unchanged/worse gastrointestinal findings, reduced
  misfolding/ER stress but increased surface free heavy chains, and mixed myeloid
  effects. Genetic deficiency is not pharmacological inhibition.
- DOI `10.1111/imm.70056` / PXD066752: engineered A375 allotype-2/10 context and
  deposited processed-sequence reproduction; not HLA-B27 axSpA patient tissue.
- Tinworth 2026, DOI `10.1021/acs.jmedchem.6c00029`: accessible SI facts about
  distinct cellular normalization columns, human-hepatocyte DMPK and partial CIA
  design only. These are not admitted as complete causal pharmacology/efficacy claims.
- FOCIS W146, EAST-1 registry NCT07047703 and the 2026-09-08 sponsor release:
  bounded conference, registry and sponsor statements, separately classified.

Structures: `9GJN`, `9GJS`, `9GK6`, `9GKE`, `9TD3`, `9TD5`, `9TD4`, `9TD7`,
`9TF3`, `9TF4`, `9TF6`, `9TFN`. Existing v1 records preserve construct/chain,
residue systems, deletions, variants, component identities, coordinate coverage,
mapping checksums and source citation. Explicit deposited indels explain 9TF6/9TFN;
their mappings must not be treated as identical to earlier constructs. 3QNF remains.

Hryczanek explicitly links 9GJN/1, 9GK6/2, 9GJS/7, 9GKE/13. Do not promote
the v1 publication-level site annotation into a claim that every deposited buffer,
additive or organic component is an active allosteric inhibitor. 9TFN deposited
resolution 1.739 A differs from the SI's 2.00 A; retain both source contexts.

## Evidence refused

- Admission of BRADSHAW/Tinworth potency records into normalized comparable
  pharmacology/learning datasets: exact assay methods insufficiently accessible.
- Inferring a 2026 protocol from a 2024 reference, a standard laboratory method,
  control-column label or crystallographic construct.
- Numeric selectivity ratios across ERAP1 YTAFTIPSI versus ERAP2 Arg-AMC or
  LNPEP/IRAP Leu-AMC assays.
- Tinworth animal/cancer causal efficacy, occupancy or genetic dependency claims
  without sufficiently accessible main methods; CIA is not axSpA.
- Independently established human engagement from sponsor or conference wording.
- Transfer of GRWD0715/new-programme results to historical Maben compounds.
- Independent raw-MS/statistical replication, HLA motifs or beneficial peptide
  state from processed-table counting.

Other acquired/contextual publications are not automatically promoted because
they exist in the candidate inventory. No completeness claim or reopened broad
refresh is made. The explicit assay-source stop condition prevents further final
corpus promotion; it is not evidence against ERAP1.

## Assay normalization

`adjudication.json` records eight assay/context groups with explicit field states:
VERIFIED, PARTIALLY VERIFIED, INACCESSIBLE or NOT APPLICABLE. Inaccessible main
methods are not labelled NOT REPORTED. The accessible 2024 cellular method is
40-hour HeLa presentation of SIINFEKL by mouse H-2Kb/beta2m, not ERAP1 occupancy.
The source does not provide an independently resolved endogenous HeLa allotype.

2026 endpoints, source compound labels and summary potency/replicates are accessible.
Exact assay preparations, substrates, concentrations and durations remain unresolved.
Tinworth's KK-SIINFEKL versus compound-6 controls remain separate: compound 21
pIC50 7.25 versus 7.05 must not be averaged or substituted for one another.

Existing `axis.pharmacology.selectivity.compare` was executed on the 2024
compound-7 counter-screen inputs. Both ERAP2 and LNPEP comparisons are **Not
directly comparable**; no ratio or bound is generated. The source's censored
pIC50 <4 remains an inequality after concentration conversion, not a fake exact value.

## Chemical Learning

**MODEL NOT BUILT**, historical result unchanged. The separately versioned
candidate-v2 remains unadmitted. The previous numeric diagnostics include
BRADSHAW policy passes; this closure does not relabel them numerical failures.
Assay comparability fails scientific admission. Existing eligibility is not rerun
on unadjudicated records, thresholds are unchanged and no model is trained.

All 63 original BRADSHAW/Tinworth identities remain in frozen v1 with original
SMILES/source rows and source-assigned stereo alternatives. A resolved SI identity
does not establish an assay protocol. The 2024 source-reported SAR is not declared
a newly admitted predictive dataset.

## Decision BEFORE

Canonical baseline: `decision-state:1:cebbae3880aeec90`.
Evidence digest: `cebbae3880aeec9084784f9f8df4a89abfe71a6058e3c924ce78651beaa44541`.
Primary uncertainty: `uncertainty:target_engagement`.
Recommended experiment: `decision:exp:chemical-genetic-engagement`.
Question: do the phenotype-producing historical compounds directly engage ERAP1
in cells at their phenotype-active exposures?

## Decision AFTER

**Creation refused.** `decision-refusal.json` contains AFTER=null and
candidate_created=false, linked to the precise source-context blocker. No final
integrated engine run, new DecisionState or approved evidence state was fabricated.
The existing baseline/structural-only engine replay remains an isolated diagnostic.

## Causal Decision Diff

`causal-decision-diff.json` explicitly records that critical uncertainty, next
experiment, therapeutic strategy and integrated tractability changes are **not
assessable**, rather than YES/NO without a valid AFTER. The mandatory YES/NO
decision comparison is conditional on a defensible AFTER and cannot be supplied here.

Two bounded facts can be stated without an integrated decision: Chemical Learning
admission remains refused; historical Maben engagement remains unresolved. Twelve
additional mapped structures expand available experimental geometry. The boundary
is existing `DECISION-STRUCT-001`: structure cannot resolve engagement/dependency.
None of these observations is a final integrated-corpus decision result.

## Therapeutic Strategy

No justified new engine-selected strategy. The context-specific modulation
"ERAP1 corrector" idea is recorded as **researcher_hypothesis — PLAUSIBLE BUT
INSUFFICIENT**, supported by substrate dependence, perturbation-specific peptide
effects and mixed animal outcomes. No desired/protective axSpA peptide state or
risk-to-protective therapeutic correction has been demonstrated by this audit.

**QUESTION PARTIALLY ADVANCED** describes mechanistic framing only: mode and
biological context merit distinction. It does not imply that the engine's critical
uncertainty has moved downstream or that maximal inhibition is contraindicated.

## Critical Uncertainty

Before: `uncertainty:target_engagement`. After: unavailable because reassessment
was refused. No stable/replaced/resolved classification is claimed for the full corpus.

## Next Discriminating Experiment

Before: `decision:exp:chemical-genetic-engagement`. After: unavailable. No new
experiment was manually chosen, and no valid final Decision View is claimed.

## Historical Maben Engagement

Remains unresolved: no admitted new source directly tests those compounds at
phenotype-active exposures. New-programme crystallographic, presentation, conference
or sponsor evidence cannot resolve this compound-specific uncertainty.

## Human Evidence

FOCIS W146 is a conference abstract. NCT07047703 is a trial registry; the frozen
2026-09-18 update contains no posted results section. This is not a negative efficacy
result. The 2026-09-08 announcement reports healthy-volunteer SAD PK/engagement and
axSpA MAD dosing. Classification remains **Human target engagement — sponsor
reported, methods not independently adjudicated**. No independently adjudicated
human PK, occupancy or axSpA efficacy result is newly admitted by this closure.

## Acceptance Matrix

| Gate | Status |
|---|---|
| Data acquisition | PASS WITH CONDITIONS |
| Data provenance | PASS WITH CONDITIONS |
| Chemical identity | PASS WITH CONDITIONS |
| Assay normalization | FAIL |
| Structural integration | PASS WITH CONDITIONS |
| Immunopeptidome reproducibility | PASS WITH CONDITIONS |
| Claim-level evidence integration | PASS WITH CONDITIONS |
| Chemical Learning eligibility | PASS WITH CONDITIONS |
| Epistemic integrity | PASS WITH CONDITIONS |
| Decision causality | FAIL |
| Offline reproducibility | PASS WITH CONDITIONS |
| External-review readiness | FAIL |

Claim integration covers the defensible subset and existing Claim storage, not
complete admitted cellular decision inputs. Offline replay verifies claims, source
links, explicit refusal, selectivity and existing partial computations, **not** an
integrated AFTER decision. Chemical Learning passes the refusal audit, not admission.
No acceptance gate silently upgraded from partial data to a completed reassessment.

## Tests

Commands use the validated Python 3.12 environment and repository checkout:

```text
PYTHONPATH=. python scripts/close_erap1_data_rich.py --cache <external-cache>
PYTHONPATH=. python scripts/close_erap1_data_rich.py --replay
PYTHONPATH=. pytest -q tests/test_erap1_scientific_closure.py
PYTHONPATH=. pytest -q
mypy axis --strict
ruff check scripts/close_erap1_data_rich.py tests/test_erap1_scientific_closure.py
ruff check .
python -m build
git diff --check
```

Focused closure tests: **14 passed**. Strict mypy: 163 source files passed.
Changed-code Ruff: passed. Global Ruff: 462 inherited findings, unchanged.
Offline closure: 34 existing-domain claim roundtrips passed; processed-table and
isolated-engine replay passed; no integrated decision replay claimed.
Full Python suite: **713 passed, 2 skipped**. Source distribution and wheel build
passed. Frozen v1 was compared byte-for-byte with the starting commit; unchanged.
Closure resources were verified by checksum inside the wheel. Closure package is
approximately 0.36 MB; no raw scientific downloads, PDFs, workbooks, coordinates or
databases are included. No UI or migrations changed; frontend/migration-specific
gates are not applicable and were not run.

## Remaining blockers

**One material blocker: exact priority 2026 assay context.** Publisher requests
returned HTTP 403 in the frozen acquisition records and again during closure.
Two exact-DOI repository/method searches found public abstracts/SI and restricted
publisher pages, but no usable exact protocol; the bounded search record preserves
this outcome without claiming that no lawful copy exists anywhere. The publisher
dates Tinworth online publication June 22, whereas PubMed records June 21; both
precede cutoff and the historical metadata was not overwritten.
The complete accessible supporting PDFs contain endpoint summary tables but not
enough exact methods to normalize/admit these assays. This is INACCESSIBLE, not
proof that experiments were absent or never described.

Minimum needed: lawfully accessible, cutoff-eligible primary methods explicitly
linking BRADSHAW and Tinworth SI/CSV columns to assay protocols, including ERAP1
preparation/allotype and substrate/concentrations for enzyme assays, readout/control
and exposure/duration for cellular assays. If a field is genuinely unreported,
confirm that from accessible methods and retain it as unknown; do not invent it.
An accessible source-authored methods supplement can suffice; a whole PDF is not
mandatory if the relevant methods can otherwise be verified.

Patient efficacy, a new model, positive animal results and resolution of historical
Maben engagement are **not** requirements to unblock source adjudication. Further
experiments/reviewer acceptance are downstream questions, not new audit blockers.
Animal and sponsor-method limitations stay explicit exclusions, not additional
mandatory blockers. No paywall bypass or author contact performed.

Commercial verdict: **NO UPDATE JUSTIFIED** for a final replacement brief at this
blocked stage. A future evidence addendum requires source closure/review; the
historical commercial documents were not regenerated.

## Final verdict

**NOT READY FOR INDEPENDENT SCIENTIFIC REVIEW**
