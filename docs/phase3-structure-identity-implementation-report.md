# Phase 3.2 — Implementation and validation report

Date: 2026-10-04. Status: implemented; automated scientific/package gates and
manual viewer acceptance passed. Playwright execution is environment-blocked,
not reported as passed. Phase 3.3 was not started.

## Baseline

Actual checkout: /Users/joaopais7/Documents/AXIS-visual-validation.
Branch: codex/phase2-transfer. Starting HEAD: **2ddfee0**.
Phase 3.1 was committed at baseline; migration 005, models, parser, repository,
API, target workspace and source drawer were inspected. Its targeted tests
passed before development (24 tests). The older AXIS directory was not used
as the implementation baseline. Unrelated untracked .DS_Store was preserved.
No Phase 3.2 commit or push was performed.

Frozen UniProt reference verified from the actual package:
Q9NZ08 / ERAP1_HUMAN, human taxon 9606, gene ERAP1, 941 aa, sequence v3,
record v218. Sequence SHA-256:
`e7a676d4403be4bad98f60d855ac133133ae972ea93b1c2cba8d12ba8f84fb28`.
Q9NZ08-1 is the canonical displayed isoform; Q9NZ08-2 remains an annotation
without an imported sequence.

## Selected experimental object and rationale

Official records considered: [3QNF](https://www.rcsb.org/structure/3QNF) and
[3MDJ](https://www.rcsb.org/structure/3MDJ). Raw official mmCIF records were
inspected. **3QNF** was selected for explicit human Q9NZ08 anchors, documented
expression tags, exact correspondence to the pinned canonical sequence and
three chains demonstrating different coordinate completeness. 3MDJ has a more
complicated deposited sequence/difference context; it was not frozen/imported.
Selection was not a resolution competition or a ligand/therapeutic judgment.

3QNF title: Crystal structure of the open state of human endoplasmic reticulum
aminopeptidase 1 ERAP1. Method: X-RAY DIFFRACTION; resolution **3.0 Å**.
Deposited 2011-02-08; first released 2011-02-23; frozen source revision **2.2**,
2024-11-20. Raw source: https://files.rcsb.org/download/3QNF.cif.
Retrieved 2026-10-04T12:25:57Z (download-completion file timestamp, seconds).
Source experimental conditions are retained in SourceSnapshot.metadata_json.

## Construct, chains and mapping

One deposited protein entity/construct: **954 aa**:
N-terminal LRRRYT + pinned canonical 941 aa + C-terminal AENLYFQ.
All 13 added positions are explicitly described as expression tags by the source.
Mapped canonical range 1–941. Expression host reported: Trichoplusia ni.
Protein source human; host organism is not confused with protein taxon.
Fusion partners are unknown, not invented.

Three protein chains preserve separate label/auth identifiers: A/A, B/B, C/C.
Provider anchors map deposited label positions **7–947** to canonical **1–941**.
Author numbering for that anchored interval is 1–941, but that equality is not
used as the mapping algorithm. The tag positions retain author numbering and
no canonical mapping.

| Chain | Canonical mapped | With coordinates | Coordinate coverage | Unresolved mapped |
|---|---:|---:|---:|---:|
| A | 941/941 | 696 | 73.96% | 245 |
| B | 941/941 | 802 | 85.23% | 139 |
| C | 941/941 | 800 | 85.02% | 141 |

All canonical positions occur in the deposited entity sequence. Canonical
not_in_construct and substitutions/mismatches are zero for this vertical.
The absent coordinates must not be called physical construct truncations.

Unresolved canonical intervals, computed from positive-occupancy atom presence:

- A: 1–45, 111–114, 426–433, 486–514, 552–558, 758–799, 811–914, 936–941.
- B: 1–45, 110–114, 427–431, 486–514, 551–558, 821–828, 856–871, 892–908, 936–941.
- C: 1–46, 112–114, 427–434, 486–514, 552–558, 819–833, 856–869, 894–908, 938–941.

Mapping: provider-segment-projection v1, identity threshold 0.95, no alignment.
Inputs, provider categories, software/parser/importer, segment parameters and
output hashes are persisted as an AXIS-computed transformation.
Golden mapping hashes (include pinned chain/snapshot identity):

- A: `9038e56a15bb463abbc032d1a73fe87abec87d12672123de3712f02716ea9ef3`
- B: `ae0761a2ab94c3116f31866ed801196e76916da82010051992f23ba8e1dee1fb`
- C: `1ce473b3e1962983c880f2ac02ac52c363633ebd5a6b5b60d689115c20c2c7de`

The package preserves **50** other observed component instances: 39 water,
three zinc ions and eight sugar/glycan residues. No Compound, inhibitor, drug,
potency, selectivity or therapeutic claims are created from these observations.

## Frozen package and storage

Package: axis/resources/structures/erap1/3qnf/v1/, version 1.0.0.
Raw mmCIF SHA-256:
`04b29d420769a6ce405c85d90e6888289de20381e17e64c1a31c3e4f835b8f75`.
Manifest SHA-256:
`1a3162c1b7d2fe8fffb55fc881d4cf914d6edf74595a18b18057f412f6e9421f`.
Manifest pins raw bytes, canonical checksum and importer/mapping versions.
Raw file, manifest, checksum and README are included in the wheel.

Additive migration **006_structure_identity.sql**; migrations 001–005 unchanged.
Focused immutable repository, raw BLOB storage and transactional imports.
Both duplicate replay and conflict/rollback behaviour were tested.
Relations are exposed through a scoped structural identity_graph, separate
from the existing disease/mechanism graph. Curated evidence remains 14 claims.

## API and UX

Scoped GET list/detail/chains/mapping/provenance/coordinates were added beneath
/api/projects/{project}/targets/{protein}/structures. Unknown and wrong-project/
target requests fail. Coordinates are local JSON/mmCIF with raw SHA-256.
No GET/render operation initiates PDB retrieval.

The existing Target / Protein card now links to imported structures or retains
an explicit absence message when none are imported. List/detail support multiple
future structures. Construct/chain disclosures, chain selector, coverage,
canonical lookup and residue buttons preserve missing/substituted/inserted states.
The existing source drawer distinguishes provider metadata from AXIS projection
and provides keyboard close/focus restoration. A return link leads to disease
evidence without structural therapeutic implications.

NGL **2.5.0** chosen over a broader Mol* application integration for this focused
vertical: mature mmCIF/cartoon/picking/local Blob support. Gemmi **0.7.5** is the
justified reliable structural parser. Both dependencies are pinned; Python and
npm lockfiles updated. No homemade molecular renderer or security-policy bypass.

Viewer is lazy; local coordinates load on request. Rotate/zoom/pan/reset,
chain colours, sequence-to-structure highlight and structure-to-canonical picking
work. Added explicit keyboard Pan left/right controls. Reset also resets rotation,
not only camera fit. On chain change, stale selection/highlight is cleared.
Text remains available without WebGL.

Production JS: main 43.72 KB (13.85 KB gzip); lazy NGL/viewer 1,296.32 KB
(361.77 KB gzip). The >500 KB Vite warning is disclosed. NGL declarations require
skipLibCheck for upstream dependency types; AXIS application typing remains strict.
An upstream THREE useLegacyLights deprecation warning was seen, with no renderer
exception. It is not claimed fixed.

## Executed validation

| Gate | Result |
|---|---|
| Full Python suite, checkout explicitly selected | **281 passed, 2 skipped** |
| New structure tests, installed wheel outside checkout | **24 passed** |
| Ruff axis/tests and wheel verification script | Passed |
| Strict mypy | Passed, 111 source files |
| TypeScript typecheck | Passed |
| ESLint | Passed |
| Frontend DOM/string contracts | **17 passed** |
| Production build | Passed; lazy-chunk size warning retained |
| Poetry lock validation | Passed; existing metadata deprecation warnings |
| Wheel build and target-directory installation | Passed |
| Installed-wheel resource checks | Passed: CIF/manifest/README/migration/viewer assets |
| Two clean-store offline replays | Passed, identical full projections/mappings |
| Mapping golden checksums | Passed |
| HTTPX network entry point disabled during replay/API | Passed |
| Migration 5→6 and read-only reopen | Passed |
| Legacy migration/regression tests | Passed in full suite |
| Project/target-scoped API tests and wheel smoke | Passed |
| Manual 1440×1000 and 1024×1000 acceptance | Passed, screenshots saved |
| Playwright structure tests | **Blocked: Edge distribution missing** |
| git diff whitespace check | Passed for authored files; frozen CIF and generated upstream shaders retain original whitespace |

The two skipped Python tests require optional external DDX24 datasets; they are
not structure failures. An initial suite invocation resolved an older installed
AXIS package because the existing environment was not editable for this checkout.
The suite was rerun with PYTHONPATH=. and passed; the installed-wheel test later
explicitly used the new wheel from /tmp, proving it was not accidentally testing
the checkout. Loaded package path was .tmp/wheel-phase32-installed/axis/__init__.py.

Wheel verification reused the existing Python 3.12 dependency environment and
installed AXIS into an isolated package target directory with --no-deps. This is
package/resource validation, not a claim of independent third-party installation.
scripts/verify_structure_wheel.py reproduces the installed-package resource,
two-clean-store equality, no-network and API smoke checks.

## Browser/manual acceptance

Reviewed in the in-app browser against a separate, freshly imported local store,
server at http://127.0.0.1:8768. Traversal: Target / Protein → Structures →
3QNF → construct/chains → coverage/mapping → source drawer → local viewer →
return to disease evidence. Both viewports reported no document horizontal
overflow; the 1024 provenance drawer also reported no horizontal overflow.

Manual actions verified:

- local NGL initialization, cartoon and chain colour distinction;
- canonical A46 maps to author A46, deposited/label position 52;
- clicking a visible coordinate selected C887 / R / deposited position 893,
  exact_match, and synchronized the chain selector;
- 3D residue highlight, native rotation and wheel zoom;
- pan translation by explicit controls and reset to initial orientation/fit;
- canonical residue 1 unresolved, clear explanation and no invented 3D highlight;
- source drawer, Escape dismissal/focus restoration and residue inspection by Enter;
- return to persisted disease evidence.

NGL right-drag pan is supplied by the library but that gesture itself was not
exercised with the available native drag API; pan buttons were exercised.
Graphics picking/gesture acceptance is manual, not a claimed automatic WebGL test.

Screenshots under docs/screenshots/phase3-structures/. Representative captures:

- [1440 full-width list](screenshots/phase3-structures/1440-full-list.jpg)
- [1440 detail/coverage/selected residue/viewer](screenshots/phase3-structures/1440-full-selected-viewer.jpg)
- [1440 missing-residue coverage](screenshots/phase3-structures/1440-full-missing-coverage.jpg)
- [1440 source/mapping drawer](screenshots/phase3-structures/1440-full-provenance.jpg)
- [1024 list](screenshots/phase3-structures/1024-list.jpg)
- [1024 detail](screenshots/phase3-structures/1024-detail.jpg)
- [1024 coverage](screenshots/phase3-structures/1024-coverage.jpg)
- [1024 selected residue/viewer](screenshots/phase3-structures/1024-selected-viewer.jpg)
- [1024 viewer](screenshots/phase3-structures/1024-viewer.jpg)
- [1024 missing residue](screenshots/phase3-structures/1024-missing.jpg)
- [1024 drawer](screenshots/phase3-structures/1024-provenance.jpg)

Browser screenshot bytes are JPEG. At the 1440 viewport, native viewport captures
were limited to the host panel width of 1332 px; the full-page captures above
retain the actual 1440 CSS-pixel width. Full-page height naturally exceeds 1000
for the long detail. Viewports, not tall full-page screenshot heights, were the
requested 1440×1000 and 1024×1000.

Three new Playwright cases were attempted and could not launch because
/Applications/Microsoft Edge.app is absent. No Edge/Chrome browser was installed
as a workaround. Contracts and manual browser checks are reported separately.
External independent review, alternate GPUs/browsers, full no-WebGL runtime
failure injection, mixed-protein complexes and ensembles were not validated.

## Scientific limits and next scope

This is one frozen experimental entry, not exhaustive PDB discovery, clinical
validation or the disease conformation of ERAP1. Tagged deposited sequence and
unresolved coordinates do not establish physical processing or expression changes.
Missing anchors/unequal-span mappings fail rather than being solved with a guessed
alignment. Alternate conformer occupancy is used only for presence; conformer
specific mapping/quantification is not implemented.

Structural existence alone does not establish druggability, therapeutic efficacy,
selectivity or disease relevance. Protein/isoform correspondence is versioned
identity infrastructure; structural components do not become pharmacology records.

Recommended **Phase 3.3**, only with separate approval: independent CompoundIdentity,
Assay and BioactivityMeasurement objects tied to exact target/construct and
source-backed conditions/units. Explicitly supported links may then connect
chemical identities to observed structural components, without conflating
coordinate observation, binding measurement and therapeutic effect.

STOP: no ChEMBL/PubChem, chemistry ingestion, docking, MD, screening or ranking
was implemented.
