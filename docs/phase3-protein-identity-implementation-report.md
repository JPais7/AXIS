# Phase 3.1 implementation report

2026-10-03 — **IMPLEMENTED**, with automated browser-run limitation below.
Only protein identity was implemented. Phase 3.2 has not started.

## Baseline and acceptance gate

Branch `codex/phase2-transfer`, baseline `0c2527f` (following `7f9e0a9`).
Original checkout `/Users/joaopais7/Documents/AXIS` preserved; work lives in the
separate `AXIS-visual-validation` checkout. Inspected EvidenceStore, domain,
migrations 001–004, curated ERAP1 resource, API, workspace, provenance, packaged
resource conventions, tests and CI. Baseline contained no target identity migration.

Historical hardening report records blocked visual acceptance. The subsequent
visual report records a limited manual pass at the base commit, but post-polish
verification remained pending. Release candidate JSON still has
`candidate_awaiting_visual_acceptance`, `frozen_release=false`, no acceptance date,
and pending expert review. Those files/statuses were not retroactively accepted.
The explicit Phase 3.1 user prompt authorizes proceeding despite that gate.

## Files and architecture

- Added `axis/domain/protein.py`: ProteinIdentity, ProteinIsoform,
  GeneProteinMapping, SourceSnapshot, MappingStatus and sequence integrity functions.
- Added `axis/storage/migrations/005_target_identity.sql` and
  `axis/storage/targets.py`; connected focused repository to EvidenceStore.
- Added `axis/sources/uniprot.py` (pure parser and explicit network adapter),
  `axis/targets/identity.py` (ingestion, transactions, pinned replay, read projection),
  and `axis/cli/target_identity.py`; registered target CLI commands.
- Added frozen `axis/resources/targets/erap1/uniprot/v1` package and wheel inclusion.
- Extended `axis/api/server.py` with project-scoped identity read routes.
- Added `web/src/protein.ts`; extended types/navigation/page dispatch/styles,
  clipboard status and provenance drawer; rebuilt distributed UI assets.
- Added `tests/test_protein_identity.py`, `web/tests/protein.test.mjs` and a protein
  browser acceptance specification. Updated four existing schema expectations from
  4 to 5 (five assertions including CLI output). No old migrations changed.
- Updated README, frontend test glob, identity documentation and this report.
- Saved reviewed screenshots under `docs/screenshots/phase3-identity`.

No scientific curated evidence package/domain records were changed. The existing
six publications, 14 project claims and existing interpretations remain intact.
No structure, chemical-matter or variant source was added.

## Exact imported reference

| Field | Frozen value |
| --- | --- |
| Source | https://rest.uniprot.org/uniprotkb/Q9NZ08.json |
| Namespace/accession | uniprot / Q9NZ08 |
| Entry | ERAP1_HUMAN |
| Primary gene | ERAP1 |
| Protein | Endoplasmic reticulum aminopeptidase 1 |
| Organism/taxon | Homo sapiens / 9606 |
| Provider status | UniProtKB reviewed (Swiss-Prot) |
| Entry sequence | 941 amino acids; version 3 |
| Record version | 218 |
| Displayed isoform | Q9NZ08-1; isoform-specific version unknown |
| Other annotation | Q9NZ08-2; sequence not imported |
| Retrieval | 2026-10-03T17:28:00Z; download file timestamp, one-second precision |
| Provider release | Not reported (headers not captured for frozen download) |
| Importer/package | 1 / 1.0.0 |

Sequence SHA-256:
`e7a676d4403be4bad98f60d855ac133133ae972ea93b1c2cba8d12ba8f84fb28`.

Raw response SHA-256:
`159efd863655a143aaaa821e7efab2334a1d7fd606d49586ea86bec2f9e14b65`.

Frozen manifest SHA-256 (pins raw response):
`6c0c850e37e1f148618c5b5485b908264e03b3e9a899832bb85901266e7f2c6b`.

Accession, gene and taxon were verified from the retrieved record, not copied
uncritically from the implementation prompt. Unknown isoform sequence/version and
provider release fields are not fabricated.

## API and CLI

`GET /api/projects/{project}/targets`, detail `/{identity_id}` and detail suffixes
`/protein`, `/isoforms`, `/provenance`. IDs are namespace/snapshot aware and must
be URL-encoded. No GET performs a live source request. Project membership is explicit.

CLI: `target import-package --project ... [--directory ...]`,
`target import-uniprot ACCESSION --project ... --taxon ...`, `target show ACCESSION`,
`target verify ACCESSION`. Frozen/live operations are visibly distinguished.

## Executed validation

| Check | Actual outcome |
| --- | --- |
| Full Python suite, final run | 257 passed; 2 skipped, 19.72s |
| New identity tests | 24 passed; also replayed against installed wheel |
| Ruff, whole axis/tests | Passed |
| Strict mypy, whole axis | Passed; 105 source files |
| TypeScript typecheck | Passed |
| ESLint | Passed |
| Frontend rendering contracts | 12 passed |
| Production frontend build | Passed |
| Wheel build/install, no dependencies | Passed, isolated target `.tmp/wheel-phase31` |
| Installed-wheel resource checks | Migration 005, frozen raw package and UI index found |
| Installed-wheel identity test suite | 24 passed, 6.38s; launched outside checkout with importlib test mode |
| Frozen offline replay | Passed; network client disabled; two clean stores yield equal projections |
| Migration 4→5 and read-only reopen | Passed; migration tracked once and imported identity preserved |
| Legacy schema-2 upgrade/backwards compatibility | Passed in full existing suite |
| Conflict, taxon, duplicate and rollback | Passed; immutable record retained and no partial state |
| CLI frozen import and verify | Passed in separate `.tmp/phase3-identity.duckdb` |
| Running HTTP identity list | 200; one Q9NZ08 projection, matching checksum |
| Manual browser page | Passed at 1440×1000 and 1024×1000, screenshots reviewed |
| Manual provenance keyboard | Enter opens; close receives focus; Escape restores opener focus |
| Manual copy control | Reported “Sequence copied.” after click |
| Manual disease-evidence return | Evidence page reopened with 14 claim buttons |
| Browser console inspection | No warning/error entries returned |
| Automated protein Playwright spec | Attempted; launch failed: configured Microsoft Edge executable absent |
| Diff whitespace check | Passed |

First full run failed four old schema-4 assertions, subsequently updated for additive
migration 005. Final full run passes. An initial standalone pytest executable resolved
the older installed AXIS rather than the checkout; subsequent source runs used
`python -m pytest`. Installed-wheel verification explicitly asserted the installed
package path before running its tests.

The two skipped tests need frozen DDX24 participant-level inputs that are not
distributed in the public repository; unrelated to protein identity. No skipped
test is reported as passed. The automated browser suite is not reported as passing;
the new spec could not launch. The full old browser suite was not executed.
No external expert review, cross-browser or exhaustive screen-reader audit was done.
Offline testing blocks the adapter's network entry point; no system-wide network
settings were changed.

## UX proof

Reviewed captures:

- `screenshots/phase3-identity/protein-1440.jpg`
- `screenshots/phase3-identity/protein-1024.jpg`
- `screenshots/phase3-identity/provenance-1024.jpg`

The original browser tab had synchronization failures; a fresh tab on the separate
validation server at port 8766 worked. That server remains read-only with an explicit
imported snapshot. This new traversal does not retroactively complete every Phase 2
release gate. Manual copy verification checked UI feedback, not clipboard byte readback.

## Boundaries, limitations and next slice

This tells a project exactly which imported record and sequence it refers to.
It establishes neither ERAP1 disease causality nor therapeutic efficacy, selectivity,
druggability or disease-relevant protein conformation. Verified mapping is source-backed
identity verification, distinct from scientific/therapeutic acceptance.

Sequence/version/taxon changes under a namespace/accession are rejected rather than
silently updated; explicit conflict-resolution/version-link workflow is future work.
Unchanged biological identity may retain multiple immutable retrieval snapshots;
there is no automatic latest selection. Live raw responses are not auto-archived;
use the frozen package for complete raw offline provenance. This resolver only maps
primary source gene symbols and human HGNC namespace safety, not generalized gene
ID/taxon resolution. Optional isoform sequences, isoform versions and source release
remain unknown. No constructs or variants were inferred.

Recommended Phase 3.2: one explicitly pinned experimental structure, with construct,
chain identity and residue mapping to this imported sequence, preserving truncations,
mutations, tags and missing residues. No docking or chemistry ingestion. Requires
separate approval. No commit or GitHub push was performed for Phase 3.1 in this turn.
