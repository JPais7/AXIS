# Phase 2 final acceptance and product hardening

2026-10-03. **Hardening and non-visual validation completed; final acceptance and
release freeze remain blocked by Codex browser permission verification.** The
existing browser tab at `http://127.0.0.1:8765/home` was selected before product
changes, then retried. Browser Use reports that saved permissions cannot be
verified and prohibits an indirect workaround. No browser traversal, screenshots
or visual acceptance is claimed. Scientific expert decisions also remain pending.

## A. Visual acceptance

The manual browser workflow was attempted first, as requested. It cannot currently
inspect the existing tab. All ten requested screenshot subjects are covered by
the updated acceptance specifications: Overview, Evidence Matrix, Evidence Drawer,
Mechanism, Context Comparison, Perturbations, Strategies, Open Question, Proposed
Experiment and Source Detail. The specifications include 1440px and 1024px checks,
page overflow, modal focus, Escape, focus restoration and source→claim→project
navigation. Their intended output is `docs/screenshots/phase2-hardening`.

These browser specifications are **unexecuted** here, and no screenshots have been
produced or visually inspected. Automated rendering, palette contrast and API
tests are supplementary, not replacements for the remaining manual gates.

## B. UX changes and reasons

1. **Bounded context comparison.** Evidence permits selecting 2–4 distinct claims
   and opening a side-by-side semantic table. Sequential drawers previously made
   comparison difficult. The comparison exposes exact assertions, sources/locators,
   linked perturbations, reported comparison/treatment, system, cell type, genotype,
   HLA, allotype, endpoint, assay, original relation/direction, evidence roles with
   their subjects, classifications and recorded limitations. Missing values stay
   Not reported. There is no generated reconciliation verdict.
2. **Scoped read endpoint.** `GET /api/projects/{id}/compare?claim_ids=id1,id2`
   requires 2–4 unique project-member IDs. It uses WorkspaceService and repository
   reads. Original drawer contracts remain intact. Linked perturbations are fetched
   by exact observed-effect claim, with a 100-item bound. Frontend selection clears
   on project change; excess selection is disabled. The table's horizontal region
   is keyboard focusable at narrower widths.
3. **Overview hierarchy.** Four regions: Evidence, Mechanistic picture, Decision
   landscape, Critical uncertainty. The mechanism preview includes independently
   demonstrated edges and the existing hypothesized disease edge. Performed
   perturbations have contextual drill-down links. The question and experiment
   share a distinct uncertainty region; every source/claim is not crowded onto
   Overview. Development proposals are never shown as performed results.
4. **Strategies.** Separate compatible, explicitly contradictory and inconclusive/
   context-limited groups, missing strategy-specific evidence, relevant perturbations
   and linked unresolved questions. Empty support is explicitly not evidence against
   a strategy. Allosteric modulation remains without strategy-specific supporting
   assessment in the current records. Cards retain equal treatment and no ranking.
5. **Questions.** Labelled Unresolved Scientific Question, with actual linked
   perturbations/systems/endpoints and strategy names, informing claims, contexts
   and candidate experiment. Linked collections disclose their read bounds. No
   generated answer is added.
6. **Perturbations.** Explicit target label and observed-effect claim ID are visible,
   alongside status/type/intervention/context/endpoint/source and the drawer link.
7. **Coverage language.** Serialized state identifiers and methodology are unchanged.
   `limited_evidence` displays Limited curated coverage. Coverage descriptions
   explicitly avoid implying systematic literature review or efficacy. Empty
   states retain not assessed versus no direct evidence in the current corpus.
8. **Review status.** The project banner explicitly says AI-assisted curation ·
   pending expert review. Existing package-level metadata is sufficient; no review
   schema, automatic acceptance or scientific object mutation was introduced.
9. **Navigation/accessibility hardening.** Skip-to-content link, post-navigation
   main focus, explicit drawer-close focus after asynchronous content replacement,
   Escape/close focus restoration, stale-response guards, return-to-project link,
   semantic comparison caption/row/column headers and text/symbol status distinctions.
   Core small-text/status palettes were darkened and checked at a 4.5:1 contrast
   threshold. Live tab order, focus trapping, rendered contrast and responsiveness
   still require browser inspection.
10. **Validation correction.** A legacy CLI test expected schema 2 and could pass
    accidentally from a “2” in the database path. It now checks the displayed schema
    row and stored schema version 4. This corrects an obsolete test assertion; no
    migration or production behavior was changed for that correction.

Changed files: WorkspaceService, read API, discovery perturbation repository;
frontend components/types/navigation/styles; browser and rendering tests; CLI
schema-display test; new hardening tests; production UI assets; review generator,
review artifacts, release candidate record, workspace README and this report.

## C. Scientific review package

- Human document: `docs/reviews/erap1-evidence-vertical-v1-review.md`.
- Machine-readable companion: `docs/reviews/erap1-evidence-vertical-v1-review.json`.
- Deterministic projection/rendering: `axis/discovery/review.py`.

The packet contains 13 independent source-extraction items, 24 separate evidence
interpretation items and eight separate mechanism-classification items. All **45
reviewer decisions are blank/null**, with independent Accept / Revise / Reject
choices and notes. Source items include exact assertion, source/reference/locator,
all reported/unknown context fields, KnowledgeKind, assessment references, inclusion
rationale, limitation and provenance. Interpretation items expose role, target
strategy/question, reasoning, context limitation and original provenance. Mechanism
items expose underlying source assertion or AI proposal, classification, reasoning,
source context and provenance. The AI disease hypothesis is not merged into the
13 primary-source extraction decisions.

Reviewer procedure: verify each extraction against the primary reference; review
each interpretation independently; return the completed artifact to project owners.
The read-only app does not ingest decisions. Accepting an extraction does not
automatically accept an assessment. Scientific revisions require a new reviewed
package version. No independent expert review is represented as completed.

## D. Evidence integrity

The entire curated package, domain contract files and SQL migrations 001–004
remain **byte-identical to the pre-hardening baseline**. Version, checksum, source
IDs, project IDs, all assertions, original contexts/provenance, 24 evidence roles,
eight mechanism classifications, performed perturbations and proposals are unchanged.
There is no new schema, source expansion, inference of missing context or automatic
contradiction assessment.

Running HTTP checks also compare the original claim and mechanism/perturbation/
strategy/question/experiment/source DTOs with the pre-hardening traversal snapshot:
they are unchanged. Comparison is an additive read projection over those same
records. The development fixture remains separate and proposal-only.

## E. Validation

| Gate | Result |
| --- | --- |
| Full pytest | **235 passed**, final run 37.01s |
| `ruff check axis tests` | **Passed** |
| Strict application-wide `mypy axis` | **Passed**, 100 source files |
| Frontend TypeScript | **Passed** |
| Frontend ESLint | **Passed** |
| Frontend rendering/palette tests | **8 passed** |
| Frontend production build | **Passed** |
| Offline synthetic demo | **9/9 passed** |
| Explicit frozen ERAP1 import | **Passed**, separate disposable database |
| Installed-wheel resources, UI assets, import, API and read-only reopen | **Passed** |
| Installed-wheel schema-2 backup/upgrade/reopen | **Passed** |
| Installed-wheel legacy context/provenance/CLI/offline demo | **Passed** |
| API scientific traversal and comparison bounds/isolation | **Passed** |
| Package/domain/migration byte integrity | **Passed** |
| Browser acceptance | **Blocked** — saved-permission verification |
| Manual graphical traversal | **Blocked** |
| Manual source-provenance UI traversal | **Blocked** |
| Live keyboard/accessibility review | **Blocked**; code/palette checks only |
| 1440px / 1024px manual layout review | **Blocked** |
| Screenshot production and inspection | **Blocked** |

New tests cover comparison project isolation, 2–4 distinct bounds, untouched
contexts/provenance/roles/classifications, linked performed effects, safe rendering,
semantic table headers, package/fixture status distinction, blank review decisions,
deterministic review output and performed-versus-proposed overview language.

All databases used for validation are disposable under `.tmp`; no production
scientific database was modified. Wheel checks install without network/dependency
changes into an isolated target while using existing environment dependencies.
Ownership/locking and read-only server behavior are preserved.

## F. Frozen vertical — release pending

The scientific resource remains pinned at package **1.0.0**, SHA-256
`eb2993f83a92d19f751e5637944dbb8321c4245192538811764f452568c4cc60`.
Six primary publications; 13 source assertions plus one separate AI proposal;
24 evidence assessments; eight mechanism assessments; three performed
perturbations; four strategies; one open question; one proposed experiment with
two conditional scenarios. Application version **0.2.1.dev0**; expert review pending;
zero recorded reviewer decisions.

`docs/releases/erap1-evidence-vertical-v1-candidate.json` records this candidate.
**`frozen_release` is false and `acceptance_date` is null.** A final release freeze
would violate the requested gate condition while visual acceptance remains blocked.
Once those gates pass, create the accepted release record with the actual date,
without changing scientific package bytes. Future scientific changes need a new
package version. Neither a visual acceptance date nor expert approval is fabricated.

## G. Remaining limitations

Browser permission verification remains the concrete blocker. Live visual layout,
overflow, keyboard/focus behavior and accessible tablet rendering are unverified.
The new comparison intentionally shows original contexts rather than adjudicating
scientific conflict. Related lists remain bounded with disclosure, and four-column
comparison can require horizontal scrolling. The independent review workflow is a
document handoff; there is no review-decision ingestion or collaborative editing.

The six-publication corpus is small/non-systematic and requires expert review.
AS findings are not automatically broader axSpA findings; biochemical, viral and
cellular contexts remain separate. Selectivity, clinical efficacy and preferred
therapeutic direction are unresolved. No additional primary source was imported.

## H. Phase 3 proposal

`docs/phase3-target-structure-chemical-matter-proposal.md` is a **conditional design
draft**, prepared without implementation. Final endorsement waits for Phase 2
acceptance and separate approval. It specifies gene/protein/isoform/construct/
structure/chain/site/ligand/compound identities; experimental versus predicted
structure provenance; assessed site types; original IC50/Ki/Kd/EC50 operators,
values, units and assay context; ERAP1/ERAP2/LNPEP comparison without a score;
separate biochemical/cellular/disease layers; and complete source/retrieval ancestry.
Official UniProt, wwPDB, ChEMBL and PubChem documentation supports the proposed
identity/source distinctions. No adapter or chemistry functionality is implemented.

## I. Recommendation

Restore the browser connection and complete the prepared manual/visual gates,
then record the actual release acceptance date and obtain independent scientific
review using the blank packet. The smallest future Phase 3 slice, after separate
approval, is one pinned protein-identity snapshot with an explicit reviewed mapping
to ERAP1, offline reproducibility and a provenance drawer. Structure/chemical-matter
ingestion belongs to later independently testable slices. No Phase 3 implementation
has started.
