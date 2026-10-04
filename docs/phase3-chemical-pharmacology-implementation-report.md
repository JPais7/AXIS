# Phase 3.3 implementation report

Date: 2026-10-04. Status: implemented, tested and visually reviewed; pending independent scientific review.

Commit note: the identifiers and “no commit/push” statements below record the completed implementation report before publication. The user subsequently requested a commit and push. The Phase 3.3 publication commit containing this report is identifiable in Git history by `feat: add Phase 3.3 chemical pharmacology layer`; publication does not change the validation results or baseline recorded here.

## 1–5. Repository and migration

- Active checkout: `/Users/joaopais7/Documents/AXIS-visual-validation`.
- Baseline branch: `codex/phase2-transfer` (not `main`).
- `baseline_commit: 8ed5e3daf5766e98236073f8cf9679fd5b14c3ab`
- `implementation_commit: none`
- `final_head: 8ed5e3daf5766e98236073f8cf9679fd5b14c3ab`
- Initial unrelated untracked `.DS_Store` was preserved. Implementation remains uncommitted; no push occurred.
- Added migration `007_chemical_pharmacology.sql`; migrations 001–006 are unchanged.
- Verified Phase 3.1 Q9NZ08 identity and Phase 3.2 constructs, chains and residue mappings. Installed-wheel structural replay preserves 3QNF, three chains and raw SHA-256 `04b29d420769a6ce405c85d90e6888289de20381e17e64c1a31c3e4f835b8f75`.

## 6. Domain and persistence

Implemented CompoundIdentity, CompoundExternalIdentifier, ChemicalForm, Assay, MeasurementCondition, BioactivityMeasurement and SelectivityAssessment. Conditions are embedded in immutable assay payloads. Chemical identity, experimental constructs, measurements, provider assertions and computed transformations remain separate.

SQLite-style assumptions are not introduced: storage uses the existing DuckDB transaction/migration architecture. Immutable writes reject conflicting records; project/target membership scopes collections and drilldowns. Exact construct relationships are validated when supplied. Original values, units, operators, uncertainty, conditions, source locators and provider pChEMBL values are preserved independently of deterministic normalization.

RDKit **2025.9.3** is pinned in the environment and transformation metadata. It generates deterministic canonical/isomeric representations, identifiers and 2D depictions without salt stripping, tautomer conversion or inventing stereochemistry. ChemicalSeries and experimental compound–structure links were not created without source justification.

## 7–9. Compounds and sources

| Primary identity | Formula | Provider mapping | Qualification |
| --- | --- | --- | --- |
| Maben compound 1 | C17H16F2N4O2S | CHEMBL1700161 | Connectivity resolved; potential double-bond stereochemistry unspecified, therefore stereo status unknown |
| Maben compound 2 | C21H30N4O3 | CHEMBL4456470 rejected | Primary urea identity conflicts with provider guanidine/formula; no provider measurements transferred |
| Maben compound 3 | C20H21F3N2O5S | CHEMBL2140832 | No potential stereochemical feature detected |

Tested salt/counterion, solvation and batch identity are not established. Forms remain unspecified; measurements do not claim an exact tested chemical form. Primary-transcribed identities require independent human chemical review.

Primary publication: Maben et al., *Discovery of Selective Inhibitors of ERAP1*, J. Med. Chem. 2020, 63, 103–121; DOI [10.1021/acs.jmedchem.9b00293](https://doi.org/10.1021/acs.jmedchem.9b00293), PMID 31841350. Schemes, Tables 1–2, figures and methods were inspected, including rendered PDF pages.

Author-hosted [primary PDF](https://biochemistry.chem.uoa.gr/fileadmin/depts/chem.uoa.gr/biochemistry/uploads/Papers/2019_Maben_JMC.pdf): SHA-256 `71d25266ab080c213dfcd3e071fd80f7807eb64c3521a52a1354a4d5489e9a6e`; retrieved `2026-10-04T13:34:20.060032+00:00`. The PDF is not redistributed.

Structured cross-reference: **ChEMBL 37**, document CHEMBL4376857. A small selected lossless extract, upstream response hashes and curation audit are frozen. The selection excludes molfile payloads; extract and upstream-response checksums describe different bytes. ChEMBL database licensing is attributed separately under CC BY-SA 3.0, not relabelled as Apache-licensed code. Provider retrieval metadata uses the curation-session timestamp; exact per-request times were unavailable and are not fabricated. PubChem ingestion was unnecessary and is not implemented.

## 10–15. Assays, mappings and measurements

Seven assays: ERAP1 L-AMC, ERAP2 R-AMC, mouse IRAP/LNPEP L-AMC, ERAP1 WK10, ERAP1 L-pNA, ERAP1 LF9 and engineered HeLa antigen presentation. Assay records retain substrate, detection, concentration, buffer, timing and expression/material descriptions where reported; missing temperature and other conditions remain unknown.

Reported targets: human ERAP1 Q9NZ08 (9606), human ERAP2 Q6P179 (9606), mouse IRAP Q8C129 (10090). Source methods describe recombinant tagged proteins and allele/variant context, but do not establish the exact construct for each measurement. Exact protein/construct foreign keys are therefore **unset**, not forced onto canonical ERAP1 or 3QNF. HeLa antigen presentation is a cellular phenotype, not direct target engagement or an axSpA phenotype.

| Compound | ERAP1 measurements | ERAP2 | Mouse LNPEP/IRAP |
| --- | --- | --- | --- |
| 1 | L-AMC IC50 = 9.2 µM; L-pNA Ki = 51.7 ± 4.3 µM | Numeric counter-screen not curated | Numeric counter-screen not curated |
| 2 | L-AMC IC50 = 6.9 µM; WK10 IC50 = 6.9 µM; L-pNA Ki = 12.8 ± 1.0 µM; cellular IC50 = 45 µM | IC50 > 200 µM | IC50 > 200 µM |
| 3 | L-AMC AC50 = 4.1 µM; fold activity = 4.1; WK10 IC50 = 5.3 µM; LF9 Ki = 3.8 ± 0.7 µM; cellular IC50 = 1 µM | IC50 > 200 µM | IC50 > 200 µM |

Totals: **15 measurements**, including **11 ERAP1** (nine enzymatic, two cellular phenotype), two ERAP2 and two mouse LNPEP. Endpoints: ten IC50, three Ki, one AC50, one fold activity. Every original value has a source locator; concentration normalization to nM is explicit and does not convert endpoints. Compound 2 WK10 inhibition was incomplete at the highest tested concentration, retained as a limitation. Compound 3 activation of an artificial substrate is not relabelled as inhibition.

## 16–17. Selectivity and deliberately rejected comparisons

**18 assessments: four “Not assessed”, fourteen “Not directly comparable”; no numeric selectivity ratios in the curated vertical.**

The four unassessed comparisons concern compound 1 numeric counter-screens omitted from this package; this does not claim the publication lacked counter-screening. For compounds 2–3, comparisons fail conservative requirements including explicit tested form, resolved constructs, known matching conditions, substrate or organism compatibility. IC50, Ki, AC50, fold activity and cellular phenotype are not treated as interchangeable.

Primary-source inspection also identified incorrect provider IRAP target annotation and conflicting off-target operators. The primary-source mouse IRAP assignment and `> 200 µM` values are used, while provider records remain visible in the audit. Compound 2 identity mismapping is quarantined. Conflicting compound 1 off-target bounds are not converted into precise measurements.

Synthetic tests demonstrate exact and bounded ratios only when compatibility is established, including strict/inclusive censoring. Those synthetic ratios are not imported as real evidence. No opaque selectivity score or therapeutic ranking was added.

## 18. Frozen package

Package: `axis/resources/pharmacology/erap1/v1/`.

Manifest SHA-256: **`4430abd5b2f7bf60b6fd55c450ad3546962284b82c58d0a85c4acb11754cdcdb`**.

The manifest covers compounds, identifiers, forms, assays, measurements, selected ChEMBL records and curation audit. Import verifies hashes and pinned transformation versions before transactional persistence. Duplicate replay preserves immutable records. The installed wheel contains the same resources and checksum.

## 19–20. API and UX

Added project/target-scoped, bounded read collections and detail/provenance routes for compounds, assays, measurements and selectivity. Filters include compound, target, endpoint, assay type and source. Details cannot expose unrelated project records. Normal reads make no provider requests. Explicit CLI package import and opt-in ChEMBL retrieval are separate from browser reads.

Chemistry, Pharmacology and Selectivity navigation connects the existing protein and disease-evidence views. Chemistry shows 2D depictions plus textual identities, forms, external mapping status and a bounded compound–assay–measurement–target identity graph. Measurement drawers show original values, operator, assay, target/material context, normalization and provenance. Selectivity displays inputs independently and explains unavailable ratios. Unknown, empty, incompatible and not-assessed states are explicit. Drawers support keyboard opening, Escape and focus return. Tables scroll within their container at narrow widths.

Existing disease claims and 3QNF structural observations were not upgraded into pharmacological or therapeutic assertions.

## 21–23. Validation and browser acceptance

| Gate | Result |
| --- | --- |
| Full Python suite | **320 passed, 2 skipped** (18.51 s); existing data-dependent skips |
| New pharmacology tests | **39 passed** |
| Scoped Ruff: axis, tests, both wheel-verification scripts | Passed |
| Global Ruff | **Not passed: 281 findings in unchanged historical scripts**; unrelated scripts not rewritten |
| Strict mypy | Passed, 119 source files |
| TypeScript / ESLint | Passed |
| Frontend contract tests | **20 passed**, including three pharmacology tests |
| Production frontend build | Passed; existing lazy NGL chunk-size warning remains |
| Wheel build and installation | Passed into fresh target directory; existing validation environment supplies dependencies |
| Installed-wheel pharmacology checks | Schema 7; frozen checksum matches; 3 compounds / 7 assays / 15 measurements / 18 assessments |
| Two-store offline replay | Passed with socket and HTTPX entry points disabled, including installed-wheel execution outside checkout |
| Migration 6→7 and legacy migration tests | Passed, including read-only refusal and scoped persistence checks |
| API smoke and scope/filter tests | Passed |
| Installed-wheel Phase 3.2 regression replay | Passed: identical structural source and chain mappings in two stores, network disabled |
| Playwright | **10 passed** (17 s), including two new pharmacology traversals and existing structural/workspace acceptance |
| Manual visual acceptance | Reviewed Chemistry → compound → Pharmacology → measurement → provenance → Selectivity → disease evidence; 1440 and 1024 widths |
| Git whitespace check | Passed |

Edge and Playwright's expected bundled headless shell were unavailable. Acceptance used the existing **Chrome for Testing 147.0.7727.15** executable through explicit `AXIS_BROWSER_EXECUTABLE`, without a browser installation or security bypass. Initial attempts failed on the missing browser and exposed navigation accessible-name/hidden-dialog selector issues; decorative icons and the existing test selector were corrected. A separate visual-test store includes the historical demo fixture and curated vertical. Final complete browser suite passed; this is not an Edge acceptance claim.

Eighteen reviewed screenshots are retained under `docs/screenshots/phase33/`:

| State | 1440 | 1024 |
| --- | --- | --- |
| Chemistry | [View](screenshots/phase33/pharmacology-1440-chemistry.png) | [View](screenshots/phase33/pharmacology-1024-chemistry.png) |
| Compound | [View](screenshots/phase33/pharmacology-1440-compound.png) | [View](screenshots/phase33/pharmacology-1024-compound.png) |
| Measurements | [View](screenshots/phase33/pharmacology-1440-measurements.png) | [View](screenshots/phase33/pharmacology-1024-measurements.png) |
| Measurement detail | [View](screenshots/phase33/pharmacology-1440-measurement-detail.png) | [View](screenshots/phase33/pharmacology-1024-measurement-detail.png) |
| Selectivity | [View](screenshots/phase33/pharmacology-1440-selectivity.png) | [View](screenshots/phase33/pharmacology-1024-selectivity.png) |
| Incompatible | [View](screenshots/phase33/pharmacology-1440-incompatible.png) | [View](screenshots/phase33/pharmacology-1024-incompatible.png) |
| Provenance | [View](screenshots/phase33/pharmacology-1440-provenance.png) | [View](screenshots/phase33/pharmacology-1024-provenance.png) |
| Not assessed | [View](screenshots/phase33/pharmacology-1440-not-assessed.png) | [View](screenshots/phase33/pharmacology-1024-not-assessed.png) |
| Unknown | [View](screenshots/phase33/pharmacology-1440-unknown.png) | [View](screenshots/phase33/pharmacology-1024-unknown.png) |

## 24–26. Limitations, unexecuted checks and recommendation

Not executed: independent installation on another computer/OS, Edge acceptance, independent chemist review, experimental replication or clinical validation. Tests use frozen source data rather than live provider queries. Wheel installation into a fresh target on this machine is not independent installation validation. Global historical-script lint remains failing as recorded above.

This is a small, purposefully selected, AI-assisted curation, not a systematic pharmacology review. Exact tested substances and assay constructs remain incompletely resolved. Cross-substrate/cross-species data cannot establish numerical selectivity here. Engineered HeLa antigen presentation does not prove cellular ERAP1 engagement, HLA-B27 mechanism, axSpA benefit, safety or clinical efficacy.

Recommended next slice, subject to review: **Cellular Pharmacology & Disease-Relevant Target Engagement**, beginning with source-backed direct engagement, genotype/construct context, HLA-B27-related molecular phenotype and immunopeptidome controls. Do not infer that this evidence already exists.

**Stop condition honored:** no Phase 3.4 implementation, docking, virtual screening, QSAR, generative chemistry, compound ranking or large-scale ingestion. Await review; no commit or push performed.

Further methodological detail: [chemical/pharmacology documentation](phase3-chemical-pharmacology.md).
