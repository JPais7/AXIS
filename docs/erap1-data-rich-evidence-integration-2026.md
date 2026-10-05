# ERAP1 data-rich integration: bounded partial audit

Cutoff: 2026-10-05. Baseline main: `d491ebe47ee0c40dfaa3823a44a9decd1afae29d`.
Branch: `codex/erap1-data-rich-evidence-integration-2026`.

This is **not a completed scientific reassessment**. Historical commercial,
learning and decision artifacts remain unchanged. The recent addendum and EAST-1
branches were not merged into this baseline. Newly assisted records are pending_review.

## R1–R17

1. **Adjudication:** provider identities, releases and coordinates verified for
   Hryczanek 2024, BRADSHAW 2026 and Tinworth 2026 complexes. Public chemistry
   supplements acquired; this does not mean all pharmacology methods were adjudicated.
   Selected full mechanistic texts were recovered, but complete atomic curation
   and integration into existing scientific decision inputs remain unfinished.
2. **Acquisition:** seven PRIDE inventories registered. Small processed peptide
   tables acquired for PXD054491, PXD054494 and PXD066752. Public supplementary
   workbook extracted read-only. No raw mass-spectrometry files downloaded.
3. **Reanalysis:** sequence inventories; allotype 2/10 sequence overlap, lengths
   and descriptive abundance directions; counts of author-classified inhibitor/KO
   peptide sets. No independent differential-expression statistics or HLA motifs.
4. **Reproduction:** PXD066752 gives exactly 2,325 sequences, 2,162 shared,
   130 allotype-2-only and 33 allotype-10-only, matching source Figure 3A.
   Supplement Table A counts inhibitor up/unique 321 and down/WT-only 146;
   KO 263 and 238. These count source classifications, not independently fitted q-values.
5. **Not tested:** raw-MS pipeline, statistical significance, allele-specific
   binding, clinical benefit, published QSAR/FEP performance and animal causality.
6. **Structures:** 12 complexes mapped to human ERAP1, without removing 3QNF.
   Explicit deposited deletions explain unequal anchors in 9TF6/9TFN; mappings
   differ from earlier constructs. Geometry supports crystallographic binding only.
   Tinworth SI and RCSB resolution for 9TFN differ; retain both source contexts.
7. **Chemistry:** 42 BRADSHAW and 21 Tinworth source-labelled records normalized.
   Original CXSMILES, enhanced stereo and source rows preserved. SI assignments
   resolve four label-specific absolute identities while retaining conflicting CSV
   representations. Full cross-programme tractability assessment remains pending.
8. **Mode:** accessible mechanistic studies distinguish knockout from allosteric
   modulation. Their observations must not become a universal therapeutic-direction claim.
9. **Immunopeptidome:** reproducible processed-table evidence is available in
   engineered A375 cells; not patient axSpA tissue. PXD060572/PXD060575 are proteome
   datasets, not independent immunopeptidome cohorts.
10. **Human:** official FOCIS abstract, EAST-1 registry and sponsor announcement
    acquired outside Git. Their detailed atomic adjudication is incomplete. Sponsor
    engagement claims cannot be labelled independently established clinical engagement.
11. **Historical engagement:** unresolved. No new programme compound establishes
    cellular occupancy of unrelated historical Maben compounds.
12. **Learning:** candidate-v2 kept separate. BRADSHAW numeric eligibility can pass
    existing policy; numerical eligibility is not assay comparability. Exact protocol,
    construct, substrate and duration remain unadjudicated; no training admission.
13. **Model:** none built. No AXIS predictive or prospective validation claimed.
14. **Critical uncertainty:** final classification withheld. The existing engine
    was run on baseline and structural additions only; unchanged ranking there
    cannot be reported as an integrated-corpus conclusion.
15. **Next decision:** final reassessment withheld; historical recommendation not
    overwritten. No final DecisionState v2 or completed causal diff created.
16. **Review:** all new assisted scientific assertions, source identity discrepancies,
    assay mappings and biological interpretations need independent review.
17. **Readiness:** NOT READY. Missing accessible exact 2026 assay/translational
    methods prevent defensible normalization and complete reassessment. Integration
    and claim-level curation also remain unfinished; this is a partial handoff.

## Commercial Brief Decision Diff — provisional, not a replacement brief

- Remain valid: historical compound engagement unresolved; no axSpA efficacy claim.
- Should change after review: structure is no longer represented only by historical
  3QNF; newer experimental ligand-bound complexes are available.
- Qualify: Chemistry — PARTIAL refers to historical curation, not absence of newer
  source chemical matter. Engagement — MISSING/BLOCKING remains compound-specific.
- Expose: reproducible processed peptide-set comparisons, with model/HLA limitations.
- Keep absent: independently established human occupancy, universal benefit from
  inhibition, CIA-as-axSpA efficacy, published-author ML-as-AXIS performance.
- MODEL NOT BUILT remains historical fact; candidate numeric eligibility is separate
  from admission and model validation.

## Reproduction and provenance

Package: `axis/resources/evidence-integration/erap1-data-rich/2026/v1/`.
`before.json` preserves the canonical decision and hashes. `manifest.json` and
`manifest.sha256` verify frozen artifacts. `decision-inputs.json` allows isolated
baseline/structural-only engine replay, **not final reassessment replay**.

From the repository, with its declared environment:

```python
from pathlib import Path
from axis.evidence_integration import replay
replay(Path("axis/resources/evidence-integration/erap1-data-rich/2026/v1"))
```

Original PDFs/mmCIF/workbooks and retrieval provenance remain in external cache;
no raw-MS artifacts are included. ACS supplements carry CC BY-NC terms: their
accessibility does not establish permission for commercial redistribution.
No UI, schema migration, commercial PDF regeneration, commit or push performed.

## Acceptance matrix

Validation performed: full Python suite **699 passed, 2 skipped**; 32 focused
integration/structure tests passed; strict mypy
passed for 163 source files; Ruff passed on changed code; global Ruff retains 462
pre-existing findings. Source/wheel builds passed and frozen package resources were
hash-verified inside the wheel. Offline processed-table and isolated-engine replay
passed. Frozen package is approximately 2.14 MB; largest resource is under 0.45 MB.
No UI or migrations were changed; frontend and migration gates were not run.

| Gate | Status |
|---|---|
| Data acquisition | PASS WITH CONDITIONS |
| Data provenance | PASS WITH CONDITIONS |
| Chemical identity | PASS WITH CONDITIONS |
| Assay normalization | FAIL |
| Structural integration | PASS WITH CONDITIONS |
| Immunopeptidome reproducibility | PASS WITH CONDITIONS |
| Chemical Learning eligibility | PASS WITH CONDITIONS |
| Epistemic integrity | PASS WITH CONDITIONS |
| Decision causality | FAIL |
| Repository hygiene | PASS WITH CONDITIONS |
| Offline reproducibility | PASS WITH CONDITIONS |
| External-review readiness | FAIL |

The partial-audit gates do not substitute for the requested twelve-category final
acceptance test set. Remaining scientific completion requires source-supported
claim-level integration, compatible assay adjudication and a full existing-engine
reassessment. Desirable future patient experiments are not acceptance blockers.

**NOT READY FOR INDEPENDENT SCIENTIFIC REVIEW**
