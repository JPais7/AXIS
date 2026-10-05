# ERAP1 targeted assay-method adjudication — 2026-10-05

**Stage A = A2: BLOCKER PARTIALLY RESOLVED. Scientific reassessment remains blocked.**

Tinworth's preprint and its explicit methods chain were recovered legitimately.
BRADSHAW's decision-material potency methods were not. No DecisionState v2,
predictive model, final causal YES/NO diff or completed Decision View was created.

## Repository and scope

Branch: `codex/erap1-data-rich-evidence-integration-2026`, HEAD
`c901d3061a7f0d3d4f3169da99b7ad528834d9b9`. Remote branch matches; remote main
remains `d491ebe47ee0c40dfaa3823a44a9decd1afae29d`, verified after fetching.
The preceding closure artifacts were already untracked at task start and are
preserved. No commit, push, merge, main modification or history rewrite.

The new **assay-methods-v2** package is an evidence-method delta, not a DecisionState.
Its manifest references the complete SHA-256 file inventories of both historical
`v1` and `closure-v1`. The 34 immutable claim envelopes and 63 chemical identities
remain unchanged. Only three existing Tinworth claims receive separate,
`pending_review` provenance-delta records. No AI self-approval.

No broad review, new unrelated corpus, platform feature, UI/migration change,
commercial brief regeneration or EAST-1 prospective-freeze change was undertaken.
Raw PDFs/XML/HTML remain in the external cache; the new package contains only
small curation/provenance/audit files. Source accessibility is not a reuse licence.

## Source recovery and version relationship

The official bioRxiv API, full PDF, JATS and SI verify
[Tinworth preprint v1](https://www.biorxiv.org/content/10.1101/2025.11.17.686761v1),
posted **2025-11-17**, before the cutoff. Its 32-author sequence, title, programme,
compound labels and results support a `precursor_to` relationship to
`10.1021/acs.jmedchem.6c00029`. This relationship is a traceable AXIS inference:
the bioRxiv API's publication-link field is still `NA`.

All 21 biochemical and 17 populated primary HeLa summary pIC50 values in
preprint Tables 1–4 agree with the frozen final CSV. This is a version-consistency
check, **not independent replication**. The final SI controls its own numbers,
replicate counts and locators. Whole final-paper consistency cannot be established:
the publisher main text returned 403. No bypass was attempted.

Explicit method chain:

- Preprint p15, ref31 → Liddle 2020, DOI `10.1021/acs.jmedchem.9b02123`,
  institutionally hosted full manuscript, PDF pp8–9 (printed H–I).
- Preprint p15, ref38 → Hryczanek 2024, DOI
  `10.1021/acsmedchemlett.4c00401`, official SI S34, modified cellular normalization.
- Liddle p9, ref34 → Giastas 2019, DOI `10.1021/acsmedchemlett.9b00002`,
  PMC full text and official SI pp1–2, expression/purification inheritance.
  Liddle's full-length screening Hap2/retained 6His is not Giastas's deleted
  crystallographic construct with a removable tag.

Method obtained from preprint version; consistency with final publication assessed
only to the extent publicly possible. Preprint and final SI differ in pagination,
table numbering and content: final SI adds detailed potency replicates. Preprint
crystallographic PDB identifiers are placeholders, and its compound21 resolution
1.74 Å differs from final SI 2.00 Å; deposited 9TFN is 1.739 Å. All source versions
are retained; frozen structural records are not overwritten.

## Tinworth: recovered methods and boundaries

Human enzyme: explicit inheritance gives full-length Hap2 with retained C-terminal
6His, 1 nM enzyme, 5 μM YTAFTIPSI → TAFTIPSI, 50 mM HEPES pH7, 100 mM NaCl,
0.002% Tween20, 0.005% BSA, 60-minute incubation, RapidFire/C18–Sciex4000 Q-trap
product/internal-standard readout and four-parameter dose-response fit.
Temperature, added cofactors, preincubation and exact dose range are not guessed.
The enzyme preparation must not be identified with an engineered crystal construct.

HeLa: ER-targeted LEQLESIINFEKL, BacMam mouse H-2Kb/beta2m reporter, 40-hour
compound exposure, 25.D1.16-APC flow cytometry, GFP transduction and Zombie Violet
controls. Endogenous ERAP1 allotype, HLA genotype and ERAP2 status remain unknown.
The 95% viability threshold sets DMSO tolerance, not proof of safety at every dose.

KKSIINFEKL control and pharmacological control remain separate. Compound21 is
7.25 in the primary KK scheme versus 7.05 under modified normalization (7.26
unbound). Hryczanek S34 specifies a 50 μM FAC inhibitor control and iQue readout;
Tinworth final SI identifies compound6 in the alternate control column. Do not
pool, average or count these as independent biological observations.

CT26 immunopeptidomics: compound21 1 μM total, estimated 0.61 μM unbound, 30 days;
three biological replicates per WT, ERAAP-KO and inhibitor condition; H2-Kd/Dd
immunoprecipitation, Exploris480, FragPipe22/unspecific mouse search, IonQuant LFQ,
reported **ion-level** 1% FDR, VSN/LIMMA/BH and adjusted p<0.05 with fold change≥1.5.
Do not invent peptide/PSM FDR from software defaults. KO phenocopy is not a
compound-in-KO epistasis/rescue experiment or direct occupancy.

CIA: 70 male DBA/1OlaHsd mice; collagen induction D0/booster D21; GSK235
30/90/270 mg/kg orally BID D18–D36; Enbrel10 mg/kg IP every other day; blinded
daily paw scoring, histology, IgG, cytokines and immune flow endpoints. SI reports
treatment-effect one-way ANOVA/contrasts with BH correction. Group allocation,
per-group n and randomization remain insufficiently resolved. The preprint Results
PK dates D18/26/35 conflict with Methods D18/19/27/35/36; retain both.

Oral PK and hepatocyte protocols were recovered separately, not turned into
clinical exposure or potency records. CT26 tumour dosing begins with implantation:
this is a prophylactic mouse design, not treatment of established human disease.
CIA is not axSpA. Mouse substrate Methods spelling `YFATIPSI` conflicts with
Table7 `YTAFTIPSI`; mouse construct/concentrations are not borrowed from human data.

**Target-engagement wording:** preprint pp9–10 estimates inhibition using unbound
blood PK, biochemical potency and maximum asymptote. It does not directly measure
cellular occupancy. Structures show binding; presentation/immunopeptidomics and
MHC changes show functional pharmacology/PD. None resolves historical Maben
compound engagement at phenotype-active exposures.

## BRADSHAW: bounded negative method-chain result

DOI `10.1021/acs.jmedchem.5c03071`, PMID41973545 and official SI affiliation were
verified. All 75 SI pages were text-inspected, relevant method/reference passages
read and S60 TableS2 visually checked.

- S60 provides endpoints, means and per-compound N/SD, not the assay protocol.
- S3/ref1 points to Hryczanek **synthesis** of compounds3/4/5, not potency assays.
- S56/ref9 inherits Giastas **crystallography**, not the enzyme used for potency.
- S75's reference list does not independently establish protocol inheritance.

The explicit citation chain for BRADSHAW potency is **not demonstrated in the SI**.
This is not a claim that no chain exists in inaccessible main text. Publisher main
routes returned403; exact-title/DOI searches and OpenAlex found metadata/publisher
and PubMed locations, not an accessible author manuscript. Search snippets were
not accepted as full methods. Legitimate bounded attempts are logged with timestamps.

**Exact remaining blocker:** BRADSHAW biochemical construct/allotype, substrate,
enzyme/substrate concentrations, buffer/pH/cofactors, temperature, preincubation,
duration, readout, dose range and fitting; and its cellular reporter/precursor,
exposure, control normalization, readout/fitting and cell context. Unknown fields
are `NOT_CONFIRMED`, not claimed absent from the inaccessible article.

**Source needed:** legitimately accessible BRADSHAW main experimental methods or
an author-provided assay SOP/citation statement explicitly linking these potency
records to a protocol and documenting modifications. An analogous GSK assay or
shared authorship alone is insufficient. No author contact was sent.

## Comparability, learning and decision

Existing `axis.pharmacology.selectivity.compare` was executed on Tinworth
compound21 versus ERAP2/LNPEP. It refuses ratios/bounds: YTAFTIPSI/RapidFire versus
Arg-AMC/Leu-AMC fluorescence and incomplete construct/form/condition matching.
Qualitative source selectivity remains separate; no rule was loosened.

Within Tinworth's preprint, enzyme and within-scheme cellular contexts are
**PARTIALLY_COMPARABLE**, with explicit omissions. Across KK versus pharmacological
controls they are **NOT_COMPARABLE**. BRADSHAW within-source and BRADSHAW/Tinworth
comparisons remain **INSUFFICIENT_METHOD_INFORMATION**; neither programme is
admitted as directly comparable to historical Maben chemistry. No pooling.

Chemical Learning remains **MODEL NOT BUILT**. New normalized admission and
eligibility execution are deferred; historical numeric diagnostics are unchanged
and not relabelled numeric failures. Assay context, chemical form/stereo, replicates,
censoring/leakage and existing size/diversity rules cannot be replaced by volume.

Canonical BEFORE remains `decision-state:1:cebbae3880aeec90`, critical uncertainty
`uncertainty:target_engagement`, next experiment
`decision:exp:chemical-genetic-engagement`. AFTER is **null**. Change in critical
uncertainty, next experiment or strategy is **not assessable**, not an invented NO.
Stage B and its causal diff/Decision View are deliberately not run at A2. No new
programme-level engine outcome, question advancement or corrector-hypothesis
promotion is claimed; the historical bounded hypothesis/framing remains historical.

## R1–R19 closure answers

- R1: Tinworth preprint verified, version1, 2025-11-17.
- R2: Precursor relationship supported; not an independent study or official API link.
- R3: Human enzyme/cell core protocol, controls, CT26, CIA, PK/DMPK recovered above.
- R4: Unspecified temperature/dose/preincubation, exact cell genotype, counterscreen
  preparations and parts of animal design remain unknown; final main consistency limited.
- R5: BRADSHAW source endpoints/means/N/SD recovered, not exact potency methods.
- R6: Earlier references found for synthesis/crystallography, not proven potency inheritance.
- R7: Tinworth core chain recovered; BRADSHAW potency chain not recovered.
- R8: BRADSHAW normalized pharmacology/learning admission remains refused.
- R9: Tinworth can be contextually interpreted using a labelled preprint fallback;
  fully comparable normalized learning admission is not established.
- R10: No direct BRADSHAW/Tinworth comparison.
- R11: No direct comparison with historical Maben chemistry or engagement transfer.
- R12: No new eligibility run/model; historical result unchanged.
- R13: A2, partially resolved; remaining material blocker is BRADSHAW potency methods.
- R14: No DecisionState v2.
- R15: Critical-uncertainty change not assessable without AFTER.
- R16: Next-experiment change not assessable without AFTER.
- R17: Strategy change not assessable without AFTER.
- R18: Historical Maben engagement remains unresolved.
- R19: Not ready as a completed scientific reassessment; this methods audit can be reviewed.

## Acceptance and validation

The machine-readable `acceptance-matrix.json` reports all 13 requested gates,
without a numeric score. BRADSHAW completeness, normalized admission and external
reassessment readiness fail. Conditional passes explicitly preserve missing methods,
version limits, scientific learning refusal and conditional Stage B non-execution.

Validation: **733 passed, 2 skipped** in the full Python suite; **20 focused method
tests**, and **42 passed** in the combined method/closure/evidence audit tests.
Strict mypy passes for 163 AXIS source files; changed-file Ruff passes. Global Ruff
still has **462 pre-existing findings**, with none in the new methods code/tests.
Offline replay also passes with HTTP access explicitly disabled. Frozen parent
hashes, 34 claim roundtrips, 38 version-summary endpoint matches and no changes to
Decision/Learning/selectivity rules or canonical commercial state were verified.
No frontend/migration tests are claimed.

Source and wheel builds succeeded. All **44 frozen resource files** across v1,
closure-v1 and assay-methods-v2 match the repository byte-for-byte in both the
source archive and wheel. The new delta is approximately **141 kB**; no original
PDF/mmCIF/XLSX is included in its distributed resources. Final sealed replay passes.

Offline replay from repository root:

```sh
PYTHONPATH=. python scripts/adjudicate_erap1_assay_methods.py --replay
```

Replay verifies parent bytes, curated matrix/temporal boundaries, matching version
summary endpoints, three provenance deltas, existing selectivity rules, decision
refusal and the historical 34 claim roundtrips. It does not rerun inaccessible
experiments, raw-MS analysis or a final integrated DecisionState.

**BLOCKER PARTIALLY RESOLVED — SCIENTIFIC REASSESSMENT STILL BLOCKED**
