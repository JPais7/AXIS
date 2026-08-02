# First vertical slice

## Scientific question

Which genes recur in independent GEO datasets about axial
spondyloarthritis, and what evidence supports each gene–disease association?

This question is the first product acceptance test. A feature belongs in the
first slice only if it helps answer it reproducibly.

## Evidence model

The atomic unit of knowledge is a contextual claim:

`subject — predicate — object`

Every claim also records:

- the biological and experimental context in which it applies;
- whether it was asserted by a source, observed or calculated by AXIS,
  suggested by AI, or proposed by the researcher;
- its provenance and complete transformation history;
- an optional confidence value, which is never presented as proof.

For example:

`IL17A — associated_with — axial spondyloarthritis`

is insufficient on its own. Tissue, assay, comparison, population and source
are required when known, so incompatible contexts are not mistaken for
contradictions.

## Epistemic boundary

Imported metadata, author assertions, AXIS calculations, AI output and
researcher hypotheses are distinct knowledge kinds. Converting one kind into
another creates a new record; it never mutates or disguises the original.

## Provenance

Every claim must answer:

1. Where did it come from?
2. When was it retrieved or created?
3. Which version or checksum was used?
4. Which ordered transformations produced it?

Stable external identifiers are preferred. Internal identifiers must also be
stable and supplied explicitly at persistence boundaries.

## Hypotheses

A hypothesis is an identity plus an append-only sequence of revisions.
Re-evaluation appends a revision containing the evidence considered,
confidence, state and rationale. Previous revisions remain available.

## Deferred decisions

The following are intentionally not designed yet:

- GEO network and parsing details;
- gene ranking formulas and weights;
- automated contradiction detection;
- a generic ontology for every supported disease.

They will be informed by real GEO metadata rather than guessed in advance.

## Implemented persistence boundary

The domain model is persisted through a DuckDB Evidence Store with versioned
SQL migrations. Claims are immutable and idempotent, transformations preserve
their order and parameters, and hypothesis revisions are append-only.
Hypothesis evidence references are validated inside transactions so incomplete
records are rolled back.

## Implemented GEO discovery boundary

The GEO connector implements study search and metadata retrieval through the
official NCBI Entrez `gds` database. Searches are restricted to `GSE` entry
types. Results preserve study title, summary, organism, experiment type,
sample count, platform accessions, PubMed identifiers, BioProject, release
date, retrieval time and a source-record checksum.

Expression matrices, raw-file downloads, detailed sample harmonization and
refresh/version policies remain outside this slice.

## Completion criteria for this slice

- invalid or untraceable claims are rejected;
- context is represented independently from the claim triple;
- epistemic kinds cannot be confused accidentally;
- hypothesis revisions cannot overwrite history;
- the model is covered by executable tests.
