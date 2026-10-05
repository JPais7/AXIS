# ERAP1 × axSpA evidence refresh 2020–2026 — continuation audit

**NOT READY FOR MERGE. This is an incomplete refresh, not scientific acceptance.**

Baseline main is `d491ebe47ee0c40dfaa3823a44a9decd1afae29d`; starting checkpoint is `2fbb75a3bc72bc4921878dfa12282e524f8931c3`. Repository and remote state were checked before continuing. The original tree was clean. The original protocol and checkpoint are preserved, without amendment or reset.

Protocol SHA-256: `174ea4f7bde09ab435f56655f7bbed3b97edb7813fe6f080ecff88e28fef66bc`.

Window: **2020-01-01 through 2026-10-05**. Original and continuation retrievals were executed on 2026-10-05; individual UTC timestamps are retained in logs.

## Search coverage

All eight registered families A–H were retrieved with complete pagination in PubMed and Europe PMC. Crossref retrieval completed under its recorded keyword adaptation, not Boolean equivalence. WHO returned HTML, not verified registry results; Semantic Scholar was rate-limited. Neither is a negative finding.

The continuation completed OpenAlex cursor pagination: **2,667 records**. ClinicalTrials.gov pagination returned **five registry records**. Europe PMC preprint retrieval returned **61 records**, separately preserved. Missing-abstract DOI resolution returned **36 metadata records**, not 36 scientifically resolved studies. These candidates have **not** all been deduplicated, linked and scientifically screened into the original corpus.

Bounded forward/backward citation lookup for five material seed papers returned **236 citation occurrences**. There was no recursive second layer. A zero-reference API response for carnosic acid does not establish that the article has no references; backward expansion for it remains incomplete. Expansion candidates still require date/context screening.

RCSB entry metadata were retrieved for **16 structures** discovered in the existing DOI records. This does not constitute completed construct, sequence, ligand or missing-residue mapping. In particular, the four structures associated with the 2024 cyclohexyl-acid article were released **2025-01-22**, not in 2024: article and PDB release dates remain separate.

UniProt, ChEMBL target discovery and PubChem identity attempts remain in the original source log. Target/identity retrieval alone is not exhaustive bioactivity extraction or a completed compound identity audit.

## Recalculated checkpoint counts

The original frozen record archive contains **5,890 occurrences**, **1,531 unique records** and **4,359 deduplicated occurrences**. Its automated screening contains:

| State | Count | Meaning |
|---|---:|---|
| already_indexed | 1 | Baseline DOI match |
| proposed_exclusion | 1,183 | Not a final scientific exclusion |
| awaiting_full_text | 265 | Detailed screening still required |
| awaiting_metadata_or_full_text | 82 | Metadata resolution not completed |

Therefore **1,530 checkpoint records remain without final adjudication**. These counts do not include the unintegrated supplemental candidates as extra unique studies. Summing all source hits would incorrectly imply independent records/replication.

The partial study-review file contains two eligible primary papers and one eligible trial registration, with **12 draft atomic source assertions and three draft impact assessments**, all `pending_review`, and **zero graph imports**. They do not mean the whole screening population is complete. Supplementary methods and chemical identity mapping are outstanding. Historical evidence-gap adjudication and preprint/journal relationships are not complete.

## Material evidence reviewed

- Tran et al., DOI `10.1002/art.42327`, PMID 36577442: public full main text recovered through NCBI after the prior Europe PMC failure. ERAP1 deficiency reduced peripheral arthritis frequency in HLA-B27 transgenic rats, but did not improve gastrointestinal inflammation or restore selected dendritic-cell abnormalities. Cell-surface free/dimeric heavy chains increased despite partial arthritis protection. Genetic deficiency is not drug engagement, and this model is not human axial remission.
- DOI `10.1021/acsmedchemlett.4c00401`, PMID 39691536: newer regulatory-site chemistry, ligand-bound structures and functional cellular antigen-presentation results. A biochemical hit lacking measurable cellular activity is retained, not excluded. Functional presentation is not a direct occupancy readout. Comparator assays use different substrates and limited replication; numerical selectivity ratios are not imported.
- EAST-1, **NCT07047703**: ERAP1-directed GRWD0715 phase I/II clinical development in healthy volunteers and HLA-B27-positive axSpA participants. Registry first posted 2025-07-02, updated 2026-09-18; recruiting, estimated enrollment 140, **no posted results**. This changes the known clinical development landscape, not demonstrated efficacy. The planned biologically-active-dose exposure criterion is a proxy/model-based criterion, not an observed engagement experiment.
- EMITT-1, NCT06923761, was also retrieved; oncology must not be presented as axSpA efficacy or independent replication of EAST-1.

The 2021 allotype paper, PMID 33617882, is still partially reviewed. Substrate-dependent enzymatic rankings and inhibitor responses support further context assessment, but extraction and full study-quality assessment are incomplete.

## Material full-text limitations

Corilagin (DOI `10.1016/j.intimp.2025.115180`) and carnosic acid (DOI `10.1021/acs.jafc.4c00957`) remain material unresolved methods sources. Accessible primary abstracts/publisher text report binding and cellular effects; engagement modality, exposure matching, genetic dependency and selectivity conditions are not independently resolved. The corilagin publisher, preprint and publisher API failures remain preserved. No access controls were bypassed.

No statement that qualifying engagement evidence is absent is justified while this population remains unresolved. Lawfully supplied main articles and supplements are needed for their method-level assessment.

## Anti-cherry-picking and independence

The partial extraction explicitly preserves supportive, negative, null and context-dependent outcomes. This is not an audit of the entire included set; full anti-cherry-picking screening tests remain outstanding. Reviews, registry intentions, source-reported hypotheses and primary experimental observations are not interchangeable. Shared compound series, cohorts, preprints and journal publications must still be linked before interpreting independent replication.

## Repository hygiene and storage

The original checkpoint is retained in Git history, including its large metadata files. It is not silently rewritten to save space. Raw records are retained losslessly as `records.json.gz` (10,813,616 bytes). The completed OpenAlex response is preserved as `openalex.json.gz` (4,702,063 bytes); uncompressed copies and the incomplete intermediate OpenAlex file are ignored and excluded from wheels.

Original metadata and source occurrences support reconstruction of the historical search. Live search scripts are **not** expected to reproduce the same historical search as databases change. Intermediate page caches are regenerable and are not scientific replay inputs. The original supplemental response includes redundant metadata; future storage normalization must preserve this historical snapshot/checksum rather than silently discard it.

No article main-text XML or publisher PDFs were added to Git. Public XML was used outside the repository for reading; extraction preserves factual propositions and locators. Original `/tmp` paths in historical access records are retrieval metadata only; the new audit never dereferences them. New retrieval logs do not encode local caches as portable resources.

The integrity manifest covers **21 scientific resource files / 32,576,766 bytes**, excluding the manifest itself, ignored copies and reading caches. The current wheel is approximately **19.8 MB**. These are package/working-content sizes, not a measurement of total Git history growth.

## Validation scope

The original full regression run passed: 691 tests, two skipped. The continuation's scoped acceptance/Decision Engine run passed 55 tests. The final full rerun passed **701 tests, two skipped, in 229.49 seconds**. An intermediate regression detected study-specific code in the generic retrospective-validation area; it was moved to `axis/evidence_refresh.py` without weakening the generic test, which then passed. Strict mypy passes across 163 source files. Scoped Ruff passes; global Ruff reports **462 findings on both main and the continuation, zero new findings**. No unrelated lint debt was changed.

Python sdist/wheel build passes. A clean isolated venv installs the wheel without dependencies for the standard-library resource audit, with network disabled during replay, from a directory outside the checkout. It reproduces exactly the **partial NO-GO audit** and verifies all manifest checksums. **This is not replay of DecisionState v2 or a causal diff: neither exists.** CLI help smoke passes in the development environment; that is not installed-wheel application/analysis smoke.

Frontend/API/schema were not changed; no migration was required. Frontend validation was not rerun. CI for checkpoint `2fbb75a` passed, run 37304645475; it does not cover these subsequent local changes.

## Reproduction and remaining gate

From the repository, run:

```text
python -m axis.evidence_refresh
python -m pytest -q tests/test_evidence_refresh_audit.py tests/test_decision_acceptance.py
python -m build
python -m scripts.verify_refresh_wheel dist/axis_bio-0.2.1.dev0-py3-none-any.whl
```

These commands reproduce technical integrity and **incompleteness**, not a completed scientific conclusion. Screening, supplemental deduplication, material method review, graph integration, frozen evidence-set creation, DecisionState v2, causal diff and scientific replay still block acceptance. Commercial v1.1 was not generated and no merge was performed.
