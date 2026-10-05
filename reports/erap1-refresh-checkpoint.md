# ERAP1 × axSpA refresh — incomplete checkpoint

Baseline: `d491ebe47ee0c40dfaa3823a44a9decd1afae29d`.
Frozen protocol commit: `b84df9f`.
Window: 2020-01-01 through 2026-10-05.

This is a progress record, not a completed systematic review or refreshed commercial recommendation. No DecisionState v2, no commercial v1.1 and no scientific self-approval have been produced.

Raw retrieved records are preserved losslessly in `records.json.gz`. Run `scripts/screen_erap1_refresh.py` to regenerate the automated triage from this archive without network access. Retrieval scripts query live sources and are not guaranteed to reproduce a historical snapshot; the committed archive preserves that snapshot.

## Search and screening

PubMed, Europe PMC and Crossref retrievals are logged. Supplemental attempts and access failures are retained. The current first-pass corpus contains 1,531 unique records: 1,183 **proposed**, not confirmed, exclusions; 265 awaiting detailed screening/full text; 82 missing sufficient metadata; and one indexed baseline source. These are automated triage counts, not final inclusion counts. Review/preprint deduplication and citation expansion remain outstanding.

WHO HTML retrieval is not successful registry searching. OpenAlex retrieval is incomplete; Semantic Scholar was rate-limited. These limitations cannot be represented as zero findings.

## Material evidence requiring resolution

The 2024 cyclohexyl-acid inhibitor paper supplies newer chemical matter and experimental structures. Its antigen-presentation cellular assay is not itself a direct intracellular target-occupancy assay. The 2021 allotype paper shows that substrate and genotype can change apparent activity and inhibitor response.

The corilagin paper (DOI `10.1016/j.intimp.2025.115180`) explicitly reports interactions at cellular and protein levels in accessible publisher text. Full methods were not accessible through the attempted publisher, SSRN or publisher API endpoints. The carnosic-acid paper (DOI `10.1021/acs.jafc.4c00957`) also reports binding and cellular phenotype effects, but full methods were not accessible. Obtain lawful copies and supplements before deciding whether these findings resolve, narrow or leave the baseline engagement uncertainty unchanged.

All observations in `review-checkpoint.json` are pending review and are not imported scientific claims. The baseline recommendation remains the historical baseline, not a newly validated conclusion.

## Remaining work

Complete source pagination, article/preprint relationships and citation expansion; finish study-level screening and extraction (including contradictory/null findings); verify structures, assay conditions and chemical identities; import supported claims and assessments; generate immutable v2 and causal comparison; reassess chemical learning only if eligibility is met; run regressions/offline/wheel validation; only then generate and visually verify brief v1.1.
