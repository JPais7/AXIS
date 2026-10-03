# Phase 2 — ERAP1 source-grounded vertical and read-first workspace

Date: 2026-10-03. **Implementation and code/package checks pass; visual acceptance
is blocked, so Phase 2 is not yet fully accepted.** Codex Browser Use cannot verify
saved browser permissions for the loopback workspace. Retrying and resetting the
browser connection did not resolve it. No screenshot or manual UI traversal is
claimed. The remaining acceptance work is explicitly listed below.

## 1. Scientific sources curated

Six primary publications, deliberately limited coverage:

| Reference | Identifier | Curated scope |
| --- | --- | --- |
| [Evans et al., 2011](https://pubmed.ncbi.nlm.nih.gov/21743469/) | PMID:21743469; DOI:10.1038/ng.873 | AS genetics in HLA-B27 context |
| [Cortes et al., 2015](https://pubmed.ncbi.nlm.nih.gov/25994336/) | PMID:25994336; DOI:10.1038/ncomms8146 | AS association in HLA-B*40:01 carriers without B27 |
| [Chang et al., 2005](https://pubmed.ncbi.nlm.nih.gov/16286653/) | PMID:16286653; DOI:10.1073/pnas.0500721102 | Purified-enzyme peptide processing |
| [Chen et al., 2014](https://pubmed.ncbi.nlm.nih.gov/24504800/) | PMID:24504800; DOI:10.1002/art.38249 | HLA-B27 peptidome and viral-antigen recognition |
| [Chen et al., 2016; online 2015](https://pmc.ncbi.nlm.nih.gov/articles/PMC4853590/) | PMID:26130142; DOI:10.1136/annrheumdis-2014-206996 | Cellular silencing/inhibition and AS T-cell coculture |
| [Tran et al., 2016](https://pmc.ncbi.nlm.nih.gov/articles/PMC5425939/) | PMID:27107845; DOI:10.1016/j.molimm.2016.04.002 | ERAP1 knockdown and surface HLA-B27 forms in U937 |

The versioned package is `axis/resources/discovery/erap1-axspa/v1/manifest.json`,
version **1.0.0**, checksum
`eb2993f83a92d19f751e5637944dbb8321c4245192538811764f452568c4cc60`.
It records real source metadata retrieval timestamps, primary reference URLs,
Europe PMC retrieval URLs and response hashes, atomic assertions, contexts,
locators, rationale, limitations and assessment entries. Import is frozen,
offline, explicit, transactional and idempotent. No startup literature refresh.

Metadata hashes are not full-paper hashes. Chen 2016 has a separately retrieved
full-text XML hash/timestamp. Tran 2016 experimental details were verified against
indexed primary PMC text; direct XML retrieval was unavailable. This access limit
is recorded in the package and exposed through provenance. Curation and role/
mechanism interpretation are AI-assisted and **pending scientific expert review**.

## 2. Claims imported

Thirteen atomic `source_assertion` records, with stable prefix
`AXIS-ERAP1-CURATED-`:

| Claim suffix | Atomic assertion | Source |
| --- | --- | --- |
| C01 | ERAP1 polymorphism association with AS in HLA-B27-positive individuals | 21743469 |
| C02 | rs30187 association with AS in B*40:01 carriers without B27 | 25994336 |
| C03 | Model 13-residue precursor trimmed to 9 residues in purified-enzyme assay | 16286653 |
| C04 | Processing depends on substrate C-terminal residue | 16286653 |
| C05 | Silencing decreases 9-residue HLA-B27 ligand proportion | 24504800 |
| C06 | Silencing increases longer 11–13-residue ligand proportion | 24504800 |
| C07 | K528R reduces KK10-specific CTL recognition in the viral minigene assay | 24504800 |
| C08 | Silencing lowers surface free-heavy-chain expression in tested APC models | 26130142 |
| C09 | DG013A lowers free-heavy-chain expression in HeLa.B27/C1R.B27 | 26130142 |
| C10 | APC silencing/inhibition suppresses AS CD4+ Th17 coculture expansion | 26130142 |
| C11 | DG013A also inhibits ERAP2 and LNPEP, as reported by the study | 26130142 |
| C12 | shRNA knockdown increases HC10-reactive surface free heavy chains in U937.B27 | 27107845 |
| C13 | Knockdown increases disulfide-linked surface HLA-B27 dimers in U937.B27 | 27107845 |

Each assertion retains its source, retrieval timestamp, checksum scope,
transformation version, package checksum, inclusion rationale, source locator and
reported context. Missing tissue, allotype or other context stays `None` / “Not
reported”. There are no invented patient outcomes or newly generated results.

The curated project contains **14 total claims**: these thirteen source assertions
plus `AXIS-ERAP1-CURATED-HYPOTHESIS`, an explicitly separate `ai_suggestion` for
unresolved disease translation. Project `AXIS-DD-ERAP1-CURATED-001` and its scoped
target–disease pair are separate from proposal-only `AXIS-DD-ERAP1-001`. Existing
demo IDs and epistemic types are preserved.

## 3. Evidence assessments created

Twenty-four persisted `EvidenceAssessment` objects:

- 13 `untyped_considered`, linking each source assertion to the open question;
- 4 `weakly_supports`, cellular inhibition-compatible observations linked to
  complete/partial inhibition concepts;
- 6 `inconclusive`, selectivity/context limits linked to those concepts;
- 1 `neutral`, viral variant-recognition evidence considered for allele-specific
  modulation without implying disease efficacy.

No `supports` or `contradicts` label is forced. Different measured systems do not
automatically constitute a universal contradiction. Assessment provenance records
fixed package entries, the curation method and pending expert review. Neither the
backend nor frontend ranks or selects a strategy.

## 4. Mechanism assessments created

Eight persisted `MechanisticAssessment` objects:

- Seven `directly_demonstrated` edges for C03, C05, C06, C07, C08, C10 and C13,
  each limited to its source's experimental context.
- One `hypothesized` translation edge for the AI proposal claim.

The graph displays independent edges, not an unsupported sequential causal chain.
Each edge opens its claim, context, original source and classification reasoning.
Text and distinct line symbols distinguish demonstrated, inferred and hypothesized
classes; the current corpus has no inferred edge.

Three performed, source-backed `Perturbation` records preserve study contexts:
P05 knockdown with peptidome endpoint; P09 DG013A inhibition with surface endpoint;
P13 knockdown with dimer endpoint. Each links an observed-effect claim. DG013A is
only an existing-domain intervention reference, not a compound integration.

## 5. Files changed in this phase

Additions:

- `axis/discovery/curation.py`, `axis/discovery/workspace.py`;
- `axis/api/__init__.py`, `axis/api/server.py`;
- `axis/cli/workspace.py`, `axis/storage/ownership.py`;
- versioned curated manifest, checksum and README under
  `axis/resources/discovery/erap1-axspa/v1/`;
- `web/`: pinned npm package/lock, TypeScript/compiler/lint/build configuration,
  typed DTOs, reusable components, navigation/drawer logic, CSS, developer README,
  four pure rendering tests and browser acceptance specifications;
- production HTML/JS/CSS under `axis/resources/workspace/`;
- `tests/test_curated_erap1.py`, `tests/test_workspace.py`, this report.

Extensions:

- `axis/discovery/service.py`: bounded project-identity read shared by the API;
- `axis/storage/discovery.py`: bounded repository reads and corpus/source projections;
- `axis/storage/store.py`: exclusive ownership, read-only opening and bounded
  source-to-claim navigation;
- `axis/cli/discovery.py`: explicit `discovery import-erap1`;
- `axis/cli/main.py`: register local `serve`;
- `pyproject.toml`: ship curated package and production workspace assets;
- `.gitignore`: frontend dependencies/results and persistent lock sidecars;
- `README.md`: local reference-workspace entry point.

No migrations 001–004 were edited; no new schema migration was added. Existing
domain contracts remain unchanged. The checkout already contained Foundation and
unrelated research/paper changes; those are not attributed to Phase 2, reset or
deleted. Validation uses disposable `.tmp` databases, not a production store.

## 6. API endpoints and ownership

The standard-library HTTP server binds **127.0.0.1** only. Requests are serialized
on one controlled connection opened with DuckDB `read_only=True`; no web write
endpoint exists. Explicit import finishes before serving. A resolved-path OS
lock prevents concurrent AXIS CLI/server sessions, including separate processes.
Transactions remain short during import. Persistent sidecar files are not stale
markers; OS locks release on normal exit or process termination. Do not delete
the file to override an owner. Direct non-AXIS tools must also respect DuckDB's
own locking; the cooperative lock does not replace database-native protection.

| GET endpoint | Read projection |
| --- | --- |
| `/api/projects` | Project identities and target–disease pairs |
| `/api/projects/{id}` | Objective, scope, package status, counts, deterministic matrix |
| `/api/projects/{id}/evidence` | Atomic claim summaries, optional domain filter |
| `/api/projects/{id}/mechanism` | Bounded independently classified edges |
| `/api/projects/{id}/perturbations` | Performed/proposed perturbations |
| `/api/projects/{id}/strategies` | Competing stored concepts |
| `/api/projects/{id}/assessments` | Stored evidence roles and reasoning |
| `/api/projects/{id}/questions` | Questions and bounded typed links |
| `/api/projects/{id}/experiments` | Proposals and bounded conditional outcomes |
| `/api/projects/{id}/sources` | Grouped source provenance |
| `/api/claims/{id}?project_id={id}` | Evidence Drawer contract, scoped to membership |
| `/api/sources/{id}?project_id={id}` | Source → claims → project references |

Collections accept `limit=1..100` and `offset=0..100000`; default limit 50.
Pages include total, limit, offset and `has_more`. The UI displays 20-item pages;
graph pages are bounded. Drawer assessment lists, question link categories,
experiment outcomes and source project references have explicit 100-item bounds.
Related strategy reads are bounded and show a truncation warning when applicable.
There is no whole-database browser preload. SQL stays inside storage repositories.

Read projections use `EvidenceStore`, `DiscoveryService.project_identity` and
`WorkspaceService`. Corpus-state-v1 reports coverage rather than a score: an
unindexed domain is not assessed; one-source coverage is limited; multiple-source
coverage is available; increasing/decreasing predicates across contexts are mixed
context-dependent, with an explicit explanation that this is not a contradiction
verdict. The UI only renders those service states.

Host/Origin guards reject foreign browser origins, mutations return 405, and
assets use a self-only Content Security Policy. Missing asset files and invalid
paths are rejected. Production UI assets are local/offline.

## 7. UI routes and components

Global `/home`, `/projects`, `/targets`. Under `/projects/{project_id}/`:
`overview`, `evidence`, `mechanism`, `perturbations`, `strategies`, `questions`,
`experiments`, `sources`. Evidence supports domain/offset query parameters.
Direct links work through the local server's SPA fallback.

Desktop-first light canvas, restrained dark sidebar, compact cards and teal
accents. Reusable components: AppShell, Sidebar, ProjectHeader, EvidenceState,
KnowledgeKindBadge, ProvenanceBadge, EvidenceDrawer, EvidenceMatrix,
EvidenceGraph, MechanismEdge, StrategyCard, OpenQuestionCard, ExperimentCard,
SourceCard, EmptyState, LoadingState and ErrorState.

The drawer is a native modal dialog with keyboard/Escape support. It exposes the
atomic assertion, epistemic kind, every context field, evidence role, independent
mechanism classification, rationale, source locator, primary link, retrieval date,
package version, checksum scope and ordered transformations. Source navigation
returns to derived claims. Text is escaped; external references are restricted
to HTTP(S) links.

## 8. Screenshots and visual acceptance — pending

**No verified screenshots are available.** The Codex browser reports:
“saved browser permissions could not be verified.” The preview was retried,
including after the user agreed to restore the connection and after a browser
session reset; it remained blocked. Its instruction explicitly prohibits an
indirect workaround, so a different automation channel was not used to bypass it.

`web/tests/workspace.spec.mjs` prepares browser acceptance and screenshots for
Overview, Evidence Drawer, Mechanism, Strategies and Next Experiment. It has
**not been executed** here. It supplements a still-required manual visual review.
Once browser access works, complete those two manual traversals and save/review
the actual screenshots before declaring Phase 2 fully accepted.

## 9. Test and validation results

| Gate | Result |
| --- | --- |
| Full pytest, final run | **227 passed**, 32.73 s |
| CI Ruff scope, `ruff check axis tests` | **Passed** |
| Repository-wide strict application mypy, `mypy axis` | **Passed**, 99 source files |
| Frontend `tsc --noEmit` | **Passed** |
| Frontend ESLint | **Passed** |
| Pure frontend rendering contracts | **4 passed** |
| Frontend production build | **Passed**, local HTML/JS/CSS assets |
| Offline synthetic demo | **9/9 passed** |
| Explicit curated project creation and demo separation | **Passed** |
| Installed-wheel resources/frontend/import/API/read-only reopen | **Passed** |
| Installed-wheel schema-2 backup → upgrade → reopen | **Passed** |
| Installed-wheel Study/context transformations and CLI JSON | **Passed** |
| Installed-wheel offline demo | **9/9 passed** |
| API source/project/question/experiment traversal | **Passed** |
| Separate-process ownership and read-only write rejection | **Passed** |
| Manual graphical project traversal | **Blocked by browser permission check** |
| Manual graphical source-provenance traversal | **Blocked by browser permission check** |
| Screenshots / visual layout review | **Blocked by browser permission check** |

New Python tests cover reproducibility, source IDs/provenance/context, assessments,
mechanism classifications, stable pagination/bounds, project isolation, JSON date
serialization, drawer fields, unknown demo states, source navigation, question-to-
experiment links, ownership/release/connect-failure behavior, read-only rejection,
HTTP Host/Origin guards, mutation rejection and asset path containment.

An additional root `ruff check .` scan reaches unrelated existing scripts/research
and a bundled R/Tcl runtime, producing 596 legacy/vendor diagnostics. Those files
were not rewritten. The repository's documented CI/PR gate is `ruff check axis
tests`, which passes. The strict mypy application gate is unchanged and passes.

Wheel verification installs with `--no-deps --no-index` into a separate `.tmp`
target and asserts imports originate there. It uses existing environment
dependencies, not a fresh dependency installation. The wheel includes all four
SQL migrations, curated resources and frontend assets. All validation databases
and schema-2 backups are disposable.

## 10. Persisted source-to-experiment traversal

1. Open curated project `AXIS-DD-ERAP1-CURATED-001` and inspect its AS-limited scope.
2. Human Genetics → C01 → reported HLA/population context → PMID:21743469.
3. Source → derived claims → curated project reference, with import transformations.
4. Mechanism → C05/C06 peptide-processing observations or C13 dimer observation →
   each independent demonstrated edge/context/source. The disease edge remains
   hypothesized and opens the separately labelled AI claim.
5. Perturbations → P05/P09/P13 → experimental system, HLA/genotype where reported,
   endpoint and observed-effect claim.
6. Strategies → four persisted AI proposals. Complete/partial inhibition expose
   weak compatibility plus context/selectivity uncertainty. Allosteric modulation
   has no strategy-specific assessed source support in this package. No winner.
7. Open question `AXIS-ERAP1-CURATED-QUESTION` → all thirteen informing claims,
   four strategies and three perturbations.
8. Proposed experiment `AXIS-ERAP1-CURATED-EXPERIMENT` → conceptual system,
   intervention, endpoints and unresolved feasibility.
9. Conditional A: an interpretable peptide/downstream response would support
   further context-specific validation, not clinical efficacy. Conditional B:
   target engagement without the intended downstream response would challenge
   translation in that tested context. Neither is an observed result.

This chain is reconstructed from persisted objects and tested through service/API
contracts. The graphical traversal is implemented but not yet manually verified.

## 11. Known scientific limitations

Small, non-systematic, six-publication corpus; AI-assisted extraction/interpretation
requires independent expert review. AS genetics is not generalized to non-radiographic
axSpA or every disease subtype. Purified enzymes, transformed cell lines, viral
antigen recognition and patient T-cell cocultures remain different contexts.
DG013A's reported ERAP2/LNPEP activity limits ERAP1-specific interpretation.
Opposing surface observations do not settle therapeutic direction. No clinical
efficacy, causal disease mechanism, druggability or preferred strategy is established.
Not every allotype/subtype or effect-size detail is curated. Genotype, allotype and
HLA are separate fields; absent values are not filled by inference. Source access
and hash scopes are disclosed above. Package revision/refresh policy remains future
reviewed work, with immutable IDs protected against silent replacement.

## 12. UX limitations

Visual layout, live keyboard/focus behavior and end-to-end browser interaction
remain unverified because browser access is blocked. Desktop-first layout; mobile
navigation is reduced. One local read-only user/session; no authentication,
collaborative editing, in-UI imports, global/semantic search or source refresh.
Target Explorer uses stored project identities rather than a broad external target
catalog. The graph is a bounded neighborhood, not a comprehensive causal graph.
Some related lists cap at 100 with disclosure rather than a nested paging editor.
No strategy-specific evidence is fabricated for empty groups. These limitations
must be considered during the pending visual acceptance review.

## 13. Next phase recommendation and stop

First restore browser access and finish the remaining Phase 2 visual gates. Then
obtain independent scientific review of the frozen assertions, reported contexts,
assessments and conditional experiment rationale. A separately approved next phase
could strengthen reviewed curation/versioning and refine workspace usability based
on that review. Chemistry and Ask AXIS should remain separate future decisions.

No chemistry integration, docking, QSAR, ADMET, automated white-space detection,
clinical/patent intelligence, strategy ranking, autonomous experimental design or
general assistant was implemented. Work stops within Phase 2; full acceptance is
pending only the explicitly blocked browser/visual gates.
