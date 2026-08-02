# AXIS

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Research software](https://img.shields.io/badge/use-research%20only-17365D.svg)](SCIENTIFIC_POLICY.md)
[![AXIS checks](https://github.com/JPais7/AXIS/actions/workflows/ci.yml/badge.svg)](https://github.com/JPais7/AXIS/actions/workflows/ci.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21760202.svg)](https://doi.org/10.5281/zenodo.21760202)

AXIS is a local scientific discovery system for public axial
spondyloarthritis (axSpA) data. Its first goal is deliberately narrow:

> Identify genes that recur across independent GEO studies and show the
> contextual, traceable evidence supporting every association.

The project starts with the scientific domain model. Connectors, storage and
scoring will be added only after the evidence and provenance contracts are
stable.

## Current scope

- typed references to scientific entities;
- contextual scientific claims;
- explicit separation of source assertions, AXIS calculations, AI
  suggestions and researcher hypotheses;
- immutable provenance and transformation history;
- versioned hypotheses whose history is never overwritten.
- a DuckDB Evidence Store with versioned migrations and focused repositories.

See [docs/first-vertical-slice.md](docs/first-vertical-slice.md) for the
acceptance criteria and domain decisions.

## Development

The target runtime is Python 3.12.

```shell
poetry install
poetry run pytest
poetry run ruff check .
poetry run mypy axis
```

## Five-minute synthetic demonstration

Verify a new installation without downloading biomedical data:

```shell
poetry run axis demo
```

The demonstration is offline and contains only three synthetic cohort
summaries. It verifies input integrity, participant counts, separation of
primary and sensitivity evidence, numerical synthesis and machine-readable
reporting. Successful execution reports `9/9 checks`. See
[`examples/demo/README.md`](examples/demo/README.md).

For an installation test performed by someone outside the development process,
follow the [independent validation protocol](docs/independent-installation-validation.md).

## Reproducible synthetic benchmark

Measure repeated executions of the packaged demonstration without downloading
biomedical data:

```shell
axis benchmark --repetitions 10 --warmups 1
```

The command writes `benchmark-output/benchmark-report.json`, an aggregate
machine-readable report, and `benchmark-output/benchmark-runs.tsv`, with one
row per measured run. It records elapsed time, Python-traced peak memory,
output size, platform, Python and AXIS versions. Timings cover the in-process
demonstration after the interpreter and dependencies are loaded; they do not
include installation or Python start-up time. Python-traced memory is not the
same as total process memory and is labelled accordingly in every output.

Continuous integration runs the same ten-repetition benchmark on Linux,
Windows and macOS. Each workflow run retains the aggregate JSON report and
per-run TSV values for 90 days as separately named downloadable artefacts.

## Public project information

- Apache 2.0 license: [`LICENSE`](LICENSE)
- citation metadata: [`CITATION.cff`](CITATION.cff)
- release history: [`CHANGELOG.md`](CHANGELOG.md)
- contribution guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- support and security: [`SUPPORT.md`](SUPPORT.md), [`SECURITY.md`](SECURITY.md)
- scientific-use policy: [`SCIENTIFIC_POLICY.md`](SCIENTIFIC_POLICY.md)
- community conduct: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)

AXIS generates research hypotheses. It is not a medical device, does not
provide clinical recommendations and does not establish that a candidate is a
causal or therapeutically valid target.

## Evidence Store

Application code persists scientific knowledge through `EvidenceStore`; it
does not open or query DuckDB files directly.

```python
from axis.storage import EvidenceStore

with EvidenceStore("data/axis.duckdb") as store:
    store.claims.add(claim)
    loaded = store.claims.get(claim.identifier)
```

Claims are immutable and idempotent by identifier. Hypothesis updates append a
new revision and preserve the complete history. References to evidence claims
are validated transactionally.

## GEO metadata discovery

The first connector searches only GEO Series (`GSE`) records through NCBI
E-utilities. It imports study-level metadata and does not download expression
matrices or raw files.

```python
from axis.ingestion import GeoClient, GeoIngestionService
from axis.storage import EvidenceStore

with EvidenceStore("data/axis.duckdb") as store, GeoClient() as geo:
    ingestion = GeoIngestionService(geo, store.studies)
    page = ingestion.discover(
        "axial spondyloarthritis[All Fields]",
        limit=20,
    )
```

An NCBI API key and contact email can be provided to `GeoClient` when needed.
Every imported study records its retrieval time, source URL and a SHA-256
checksum of the ESummary record.

## Command-line workflow

Run the CLI inside the Poetry environment:

```shell
poetry run axis search "axial spondyloarthritis[All Fields]" --limit 20
poetry run axis studies
poetry run axis study GSE234339
poetry run axis download GSE234339
poetry run axis prepare GSE234339 --case-pattern "axSpA|patient" --control-pattern "healthy|control"
poetry run axis info
```

The default database is `data/axis.duckdb` and is created automatically.
Use `--database` before the command or set `AXIS_DATABASE` to choose a
different location:

```shell
poetry run axis --database data/experiment.duckdb info
```

## GEO expression downloads

Download the processed Series Matrix files published by GEO for a study:

```shell
poetry run axis download GSE234339
```

Files are stored under `data/geo/GSE234339/` by default. AXIS also writes a
`manifest.json` containing the retrieval time, source URL, byte size and
SHA-256 checksum of every downloaded file. Studies with multiple platform
matrices retain every matrix. Use `--output DIRECTORY` to choose another
download root.

Some GEO studies do not publish a Series Matrix. The command reports this
explicitly; raw supplementary files remain outside the current scope.

Prepare a downloaded matrix by supplying regular expressions that identify
case and control samples in their GEO title, source and characteristics:

```shell
poetry run axis prepare GSE234339 \
  --case-pattern "axSpA|ankylosing spondylitis|patient" \
  --control-pattern "healthy|control"
```

Prepared files are written beside the download under `prepared/`. Each source
matrix produces `case-matrix.tsv.gz`, `control-matrix.tsv.gz`,
`sample-groups.tsv` and `preparation.json`. Samples matching both patterns are
marked `ambiguous`; samples matching neither are `unassigned`. Both are
excluded from the expression outputs and remain visible for manual review.
Patterns must be chosen and reviewed for each study because GEO submitters do
not use a universal vocabulary for clinical groups.

For studies containing multiple treatments or time points, restrict both
groups to samples matching an additional metadata pattern:

```shell
poetry run axis prepare GSE11886 \
  --case-pattern "ankylosing spondylitis|AS patient" \
  --control-pattern "healthy|control" \
  --include-pattern "untreated"
```

Nonmatching samples are marked `excluded` in `sample-groups.tsv` and are not
written to either expression matrix.

## Exploratory differential expression

Run probe-level differential expression after reviewing `sample-groups.tsv`:

```shell
poetry run axis analyze GSE134290 --platform GPL570
```

AXIS downloads and caches the official GEO platform annotation when necessary,
maps probes to gene symbols, calculates group means and mean differences,
and applies the Benjamini-Hochberg correction. Use `--alpha` and
`--min-difference` to set reporting thresholds.

With `--method auto` (the default), an independent microarray design contract
selects a limma-style two-group moderated t-test implemented in Python. The
backend fits group means, estimates a shared inverse-chi-squared variance
prior across features and moderates feature variances before testing. Use
`--method welch` for the previous unmoderated fallback or
`--method moderated` explicitly.

This is not native Bioconductor `limma` and does not currently fit declared
covariate values unless a sample sheet is supplied. The analysis JSON records
the selected backend, design columns, contrast, prior variance, prior degrees
of freedom and residual degrees of freedom.

Generate an editable sample sheet:

```shell
poetry run axis sample-sheet GSE25101 --output data/designs/GSE25101.tsv
```

After filling covariate values, fit a moderated general linear model:

```shell
poetry run axis analyze GSE25101 --platform GPL6947 \
  --sample-sheet data/designs/GSE25101.tsv \
  --covariate sex --covariate age --covariate batch
```

The sheet must align exactly with expression sample IDs and contain `case` or
`control` in `group`. Numeric covariates are centered; categorical covariates
use reference coding. Use `--subject-column subject` for fixed subject effects
in paired/repeated data. Missing values, duplicated samples, collinearity and
designs without residual degrees of freedom are rejected.

Results are written to `differential-expression.tsv` and
`gene-level-results.tsv` inside the prepared matrix directory. Probe effects
are aggregated per gene using the median mean difference. Probe p-values are
combined with the Simes method and corrected again across genes using
Benjamini-Hochberg. The complete method and thresholds are recorded in
`differential-analysis.json`.

These results are exploratory: study design, time points, pairing,
preprocessing, covariates and biological replication must be reviewed before
scientific interpretation.

## Expression quality control

Generate QC diagnostics before interpreting differential expression:

```shell
poetry run axis qc GSE11886
```

For every prepared matrix AXIS writes `qc-report.json`,
`sample-distributions.png`, `pca.png` and `sample-correlation.png`. PCA uses
the most variable features (up to 5,000 by default). The report records
explained variance, group association tests for the first five components,
minimum sample correlation and candidate outliers based on robust distance in
the first three PCs. Outlier flags are diagnostic and never remove samples
automatically.

Before a study can enter a cross-study ranking, record a human-reviewed
eligibility decision:

```shell
poetry run axis assess GSE11886 \
  --decision approved \
  --rationale "Case-control design and QC are suitable for recurrence." \
  --species "Homo sapiens" \
  --tissue "blood-derived macrophages" \
  --phenotype "ankylosing spondylitis" \
  --role discovery
```

Use `review` when unresolved issues remain and `excluded` when the study is
not suitable. The resulting `study-eligibility.json` captures sample counts,
QC findings, phenotype, allowed scientific roles, unmodeled covariates and a
checksum of the analyzed results. Supported roles are `discovery`,
`external_validation`, `mechanistic` and `treatment_response`. Commands reject
an approved study when it is not approved for that specific use.
Reanalysis invalidates the approval, so the study must be assessed again.

## Cross-study recurrence

After approving two or more independent studies, rank recurring genes:

```shell
poetry run axis rank GSE134290 GSE_OTHER --min-recurrence 2
```

The ranking counts significant studies per gene, records study-specific
directions and effects without pooling incompatible effect scales, combines
available gene p-values using Fisher's method, and applies
Benjamini-Hochberg across genes. Outputs are written to
`data/analysis/recurrence-ranking.tsv` and `recurrence-analysis.json`.

A gene is recurrent only when it meets the per-study adjusted p-value and
effect thresholds in at least `--min-recurrence` studies and all significant
effects have the same direction. Opposing effects are marked contradictory,
not recurrent. Ranking rejects missing, non-approved or stale eligibility
records and studies with different species. Tissue, assay, design and
confounder comparability still require scientific review.

Test whether recurrence conclusions depend on arbitrary thresholds without
changing the primary ranking:

```shell
poetry run axis sensitivity GSE25101 GSE18781
```

The default grid combines adjusted p-value thresholds 0.01, 0.05 and 0.10
with absolute effect thresholds 0, 0.25 and 0.5. Repeat `--alpha`,
`--min-difference` or `--min-recurrence` to define another grid. AXIS writes
scenario-level rankings plus `sensitivity-scenarios.tsv`,
`sensitivity-genes.tsv` and `sensitivity-analysis.json` under
`data/analysis/sensitivity`. These exploratory outputs are explicitly marked
as ineligible for publication as primary evidence claims.

Rank effects that point in the same direction even when they do not pass a
significance cutoff:

```shell
poetry run axis concordance GSE25101 GSE18781
```

The analysis uses within-study absolute-effect percentiles, so raw effect
scales from different platforms are never pooled. It reports direction,
study-specific effects, nominal support and Fisher combined p-values, but
explicitly treats the output as exploratory rather than statistical
recurrence. Results are written under `data/analysis/concordance` and are not
eligible for publication as primary claims.

Create an explicitly exploratory candidate list from that report:

```shell
poetry run axis shortlist
```

By default, candidates must be directionally concordant, have nominal support
in both studies, a Fisher combined FDR no greater than 0.05 and a mean
absolute-effect percentile of at least 0.8. The criteria are configurable,
recorded with the source checksum, and produce `exploratory-shortlist.tsv`
plus an audit JSON beside the concordance report. The list is
hypothesis-generating and cannot be published as a primary claim.

Validate the frozen shortlist in an approved study that was not used for
discovery:

```shell
poetry run axis validate-external GSE181364
```

AXIS verifies the shortlist and concordance checksums, rejects discovery
studies, tests each candidate's direction and nominal p-value, and compares
directional support with all other concordant discovery genes using a
one-sided Fisher exact test. Candidate results and an audit report are written
to `data/analysis/external-validation`. Small-cohort validation remains
exploratory and creates no primary evidence claim.

Build lightweight, cached Open Targets dossiers for the frozen shortlist:

```shell
poetry run axis target-intelligence --limit 100
```

AXIS resolves gene symbols to Ensembl targets and records disease
associations, tractability by modality, clinical candidates, safety
liabilities and target-prioritisation properties. Exact API responses are
cached locally with SHA-256 checksums, so reruns require almost no computation
or network traffic. Individual JSON dossiers and a tabular overview are
written under `data/targets`. Evidence dimensions remain separate and AXIS
does not generate an opaque aggregate target score.

Import disease-specific genetic evidence and causal direction:

```shell
poetry run axis target-genetics
```

The default disease is ankylosing spondylitis (`MONDO_0005306`). AXIS imports
GWAS credible-set, gene-burden and Genomics England evidence for each resolved
target. A therapeutic direction is proposed only when both direction on
target and direction on disease risk/protection are explicit and concordant.
Missing or conflicting direction remains `unknown`; transcript expression is
never substituted for causal genetic direction. Responses and checksums are
cached under `data/targets/genetics`.

Deepen only genetically supported targets:

```shell
poetry run axis target-context
```

This stage records independent GWAS studies, credible sets, lead variants,
fine-mapping methods, locus-to-gene predictions and molecular-QTL
colocalisations. It also adds normal baseline tissue/cell expression as
contextual annotation. A strong molecular colocalisation requires a non-GWAS
right-hand study and H4 at least 0.8. Baseline expression is never presented
as disease causality or therapeutic direction.

Integrate the supported targets into an experimental-readiness matrix:

```shell
poetry run axis target-readiness
```

This joins causal-gene assignment, discovery and external expression
direction, normal immune context and target-level clinical drug precedent.
The dimensions remain explicit. A drug is never declared actionable unless
the genetic evidence supplies a causal modulation direction; expression
direction is not used as a substitute. The resulting matrix is an experiment
prioritisation tool, not a treatment recommendation.

Prepare focused queries for the Human Cell Epigenome/4D Nucleome Atlas:

```shell
poetry run axis nucleome-plan
```

AXIS resolves GRCh38 gene coordinates, converts each credible-set lead
variant and target promoter into small BED regions, and points the plan to the
published peripheral-blood donors. This deliberately uses processed,
cell-type-level contact maps rather than downloading billions of raw
single-cell contacts. Atlas contacts are normal reference context and are not
treated as disease-specific evidence or modulation direction.

Scan a small, quality-ranked sample of annotated PBMC cells:

```shell
poetry run axis nucleome-contacts
```

By default AXIS samples three cells per donor from blood central-memory CD4
and effector-memory CD8 subtypes, caches only those contact files, and scans
contacts around the planned variant and promoter anchors. Every downloaded
cell and checksum is recorded. Because single-cell contact maps are sparse,
zero matches are reported as `not_observed_in_sparse_sample`, never as
biological absence.

Plan the disease-specific single-cell validation using GSE194315 metadata:

```shell
poetry run axis single-cell-plan
```

The default comparison is 10 axial/ankylosing-spondylitis subjects versus 29
healthy subjects, focused initially on CD2, IL2RB and IKZF3 in CD4 TCM and CD8
TEM cells. AXIS checks cell coverage separately for every subject and cell
type. The future expression test must aggregate integer counts per subject and
cell type; individual cells are never treated as independent replicates.

Run the targeted subject-level pseudobulk analysis:

```shell
poetry run axis analyze-single-cell
```

AXIS streams the 10x archive without expanding it, aggregates raw counts and
library sizes by subject and cell type, and tests predeclared CD2, IL2RB and
IKZF3 effects in CD4 TCM and CD8 TEM. It uses log-CPM subject values with a
Welch comparison and adjusts the three target p-values within each cell type.

Expand the same subject-aware analysis to the detected transcriptome:

```shell
poetry run axis analyze-single-cell-transcriptome
```

This command filters low-information genes before testing, controls the false
discovery rate separately within each cell type, evaluates predeclared immune
modules, and combines the results with bulk concordance and existing target
readiness. Its score is an auditable exploratory prioritisation, not causal
evidence. Protein-structure assessment (PDB or AlphaFold) is deliberately
reserved for candidates that first survive replication and causal review.

Run that review, including current Open Targets genetics, tractability,
essentiality and safety annotations:

```shell
poetry run axis review-single-cell-candidates
```

The command reports a rule-based decision for every transcriptomically eligible
candidate. Only candidates that pass expression, human-genetic and preliminary
safety gates are released to perturbation and subsequent PDB/AlphaFold review.

Create the independent single-cell replication contract:

```shell
poetry run axis plan-single-cell-replication
```

The registry keeps discovery, disease replication and treatment-response roles
separate. It identifies `PRJNA749866` as a small independent AS-control cohort
whose raw SRA data require substantial preprocessing, and excludes `GSE277791`
from disease-control validation because it contains pooled AS treatment samples
without healthy controls.

Audit the archived full text and supplementary files before treating a reported
cohort as downloadable:

```shell
poetry run axis audit-single-cell-publication-access
```

For the 25-subject HLA-B27 CITE-seq publication, the archived materials expose
only `GSE194315`, explicitly described as a previous validation dataset. AXIS
therefore records the new cohort's primary data access as unresolved rather
than silently reusing the discovery cohort.

When primary matrices are unavailable, use the author's independent
supplementary AS-versus-control differential table:

```shell
poetry run axis validate-published-single-cell
```

This is explicitly labelled publication-level directional validation. It does
not claim to reproduce the original analysis and cannot replace subject-level
pseudobulk because the published table was generated with cell-level testing.

Build the focused, falsifiable EWSR1 dossier:

```shell
poetry run axis build-focused-target-dossier EWSR1
```

The dossier separates expression convergence from causality and proposes
titrated CRISPRi/CRISPRa experiments in primary CD14 monocytes and CD4 TCM
cells. EWSR1 is not promoted to a therapeutic or structural target without a
replicated functional effect, acceptable cell fitness and a causal modulation
direction.

Measure focused donor stability before committing to laboratory work:

```shell
poetry run axis analyze-target-stability EWSR1
```

AXIS rebuilds the focused subject pseudobulks, reports Welch and bootstrap 95%
confidence intervals, removes every donor in turn and quantifies maximum donor
influence. A stable result must retain direction in every leave-one-donor-out
run, have at least 95% bootstrap directional support and a bootstrap interval
that excludes zero.

The default target-readiness matrix now uses three independent whole-blood
discovery cohorts (`GSE25101`, `GSE18781`, and `GSE73754`). GSE73754 contributes
51 cases and 20 controls after one predeclared QC outlier is excluded; its
linear model adjusts for sex, age, and array batch. Directional concordance
across the three cohorts remains exploratory and is kept distinct from strict
adjusted-p-value recurrence.

Create a formal design contract after analysis:

```shell
poetry run axis design GSE11886 \
  --independence independent \
  --covariate sex \
  --covariate batch
```

The resulting `experimental-design.json` records sample counts, independence,
pairing, covariates, warnings, the scientifically recommended method and the
method currently executable by AXIS.

Only recurrent ranking rows can be promoted into immutable evidence claims:

```shell
poetry run axis publish-ranking data/analysis/recurrence-ranking.tsv
```

Published claims are `AXIS_INFERENCE` records with stable identifiers,
ranking checksum, study list, thresholds and transformation provenance.
Non-recurrent rows never become claims.

## Normalized RNA-seq abundance

When GEO publishes a normalized abundance table instead of a populated Series
Matrix, download the declared supplementary file:

```shell
poetry run axis download-supplement GSE212613 --pattern "all\.mRNA"
```

Analyze it by selecting the sample columns explicitly:

```shell
poetry run axis analyze-rnaseq GSE212613 \
  --input data/geo/GSE212613/supplementary/GSE212613_H1H2H3--A2A3A4.all.mRNA.xls.gz \
  --case-columns "^A[0-9]+$" \
  --control-columns "^H[0-9]+$"
```

AXIS applies `log2(value + 1)`, a Welch test, Benjamini-Hochberg correction
and transcript-to-gene aggregation compatible with `axis rank`. This workflow
is only for non-negative normalized abundance. Integer raw counts should be
analyzed with a count model such as DESeq2 or edgeR.

The domain tests use only the Python standard library and can also be run
without Poetry:

```shell
python -m unittest discover -s tests
```
### Build a large GEO study catalog

Before downloading large expression matrices, AXIS can search several disease,
immune-context and drug-response query families, deduplicate their metadata and
create a review queue:

```powershell
poetry run axis build-study-catalog --maximum-per-query 500
```

The command writes `data/catalog/study-catalog.tsv`, a machine-readable JSON
manifest and `data/catalog/download-review-queue.tsv`. A catalog match is not
automatically valid evidence: species, tissue, assay, case definition, treatment,
design and confounders still need review before a study enters an analysis.

Prioritize the direct-disease candidates using transparent metadata rules:

```powershell
poetry run axis triage-study-catalog
```

This produces `direct-study-triage.tsv` and a smaller
`direct-study-priority-queue.tsv`. The rules identify disease, tissue, assay,
case-control and treatment signals from Series-level metadata. They never mark a
study as scientifically approved: sample labels, untreated baseline groups,
participant independence and confounders remain mandatory manual checks.

Audit the sample-level metadata of the priority queue without intentionally
downloading the expression tables:

```powershell
poetry run axis audit-priority-samples
```

AXIS streams each compressed Series Matrix only until the expression table
begins. It writes one study-level audit and one sample-level metadata table under
`data/catalog/sample-audit`, plus `design-review-queue.tsv` for studies with at
least three suggested cases and controls. Treatment, ambiguous groups, unknown
treatment status and repeated participants remain explicit blockers. Suggested
labels remain unapproved until a person verifies the resulting sample sheet.

Generate editable sample-sheet proposals and apply explicit disease, assay and
cross-study independence gates:

```powershell
poetry run axis build-proposed-sample-sheets
```

Studies from related diseases or non-expression assays remain available as
context but cannot enter the axSpA meta-analysis. Series sharing a publication
or BioProject receive the same evidence cluster and are not counted as
independent replication without participant-level verification.

Nominate the next independent cohorts without mixing incompatible tissues or
counting previously analysed studies as new evidence:

```powershell
poetry run axis select-next-cohorts --maximum 5
```

The selector requires explicit axSpA signals in proposed case samples, rejects
treated and non-mRNA cohorts, keeps at most one Series per evidence cluster and
assigns separate roles to blood replication and mechanistic tissue contexts.
The resulting selection still requires manual sample-sheet confirmation.

Search beyond GEO in the ArrayExpress collection hosted by BioStudies and in
human RNA runs from NCBI SRA:

```powershell
poetry run axis build-cross-repository-catalog
```

SRA runs are aggregated by SRA Study and BioProject before counting candidates.
The resulting catalog flags accessions, BioProjects and publications already
represented in GEO, preventing raw runs or mirrored ArrayExpress records from
being mistaken for independent cohorts.

### Reproduzir o estudo DDX24

O estudo computacional DDX24 pode ser reconstruído e verificado localmente,
sem acesso à Internet:

```powershell
.\.venv\Scripts\axis.exe reproduce ddx24-study
```

O comando verifica os hashes dos dados e do `poetry.lock`, reconstrói a
meta-análise primária e a sensibilidade com GSE163314 e executa regras
científicas contra pseudorreplicação, duplicação de coortes e inclusão de
estudos sem participantes separáveis. Os resultados ficam em
`data/reproducibility/ddx24-study`. O manifesto e as instruções de atualização
estão em `reproducibility/ddx24-study`.
