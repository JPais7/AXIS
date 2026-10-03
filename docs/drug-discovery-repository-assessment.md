# AXIS drug discovery decision engine: repository assessment

Assessment date: 3 October 2026. Scope: Phase 0 only. Implementation is intentionally deferred for review, as requested.

## Assessment basis and verification

Reviewed the repository structure, package configuration, scientific policy, domain and storage implementations, both SQL migrations, ingestion and analysis module inventory, CLI, target-intelligence and decision-support builders, documentation, reproducibility and benchmark assets, tests, and CI/release workflows. Findings describe the current working checkout, including existing uncommitted work; they do not assume that README scope statements are current.

Executed focused domain, storage, GEO, therapeutic-readiness and project-pipeline tests: **21 passed**. The first attempt encountered three temporary-directory permission errors; rerunning with a dedicated workspace temporary directory passed. This is a focused baseline, not certification of the complete test suite. No production database was migrated or opened through the auto-migrating store. Live source APIs, biomedical claims and every historical output have not been independently revalidated.

The checkout already contains modified analysis, CLI, tests, README and manuscript files, and untracked research/benchmark work. Preserve them. No applicable AGENTS.md was found in the workspace inventory or checked parent locations. No implementation files were changed for this assessment.

## A. Current architecture

AXIS is a Python 3.12 local research application distributed as `axis-bio`; the Python import and console command are `axis`. The checkout declares version `0.2.1.dev0`. Poetry manages packaging and the lockfile. Runtime dependencies include DuckDB, HTTPX, Typer/Rich, NumPy, SciPy and Matplotlib. There is no existing frontend build or web-server framework in the inspected application.

| Boundary | Current implementation | Role |
|---|---|---|
| Scientific primitives | `axis/domain/models.py` | Frozen dataclasses and explicit epistemic/source enums |
| Persistence | `axis/storage/store.py` | DuckDB connection owner, migrations, focused claim/study/hypothesis repositories |
| Source acquisition | `axis/ingestion/` | GEO metadata, matrices, platform/supplement downloads, sample audits, BioStudies and SRA discovery/audits, PMC supplements |
| Scientific computation | `axis/analysis/` | Differential expression, recurrence, QC, design/eligibility, validation, sensitivity, meta-analysis, participant-aware single-cell work and reporting |
| Target interpretation | `axis/targets/` | Cached Open Targets intelligence/genetics, causal context, readiness, candidate reviews, focused dossiers, nucleome planning/contacts |
| Orchestration | `axis/analysis/project_pipeline.py` | File-based guarded staged workflow with frozen input checks and blocked/failed stages |
| User interaction | `axis/cli/main.py` | Large Typer command module with Rich tables/panels |
| Reproducibility | `reproducibility/`, `benchmarks/`, `examples/`, `axis/resources/demo/` | Manifests, packaged synthetic demo, comparison and biological benchmark materials |
| Research/report assets | `scripts/`, `paper/`, `research/`, `workflows/` | Study-specific scripts, reports/manuscripts, exploratory research and an R DESeq2 workflow |

Two persistence patterns coexist: structured scientific records in DuckDB and much richer analytical outputs in JSON/TSV/manifests/directories. This reflects the existing architecture and should be bridged rather than replaced.

`AxisProjectPipeline` is not a persistent DiscoveryProject. It orchestrates a particular axSpA/DDX24-oriented workflow, with discovery studies GSE25101, GSE18781 and GSE73754 and study-specific downstream review stages. Its input locks and failure handling are reusable; its fixed stage definitions are not a generic project model.

Configuration is primarily CLI parameters, default paths and source-client options. `AXIS_DATABASE` or the global `--database` option chooses the store; default is `data/axis.duckdb`. Outputs generally live under ignored `data/`. There is no established multi-user/authentication configuration or web deployment model.

## B. Current domain model

Actual domain primitives:

- `EntityRef(kind, identifier, label, namespace)`: scientific identity, not a full target/disease object. Kinds include disease, dataset, study, sample, gene, protein, drug, publication, pathway and biomarker.
- `Claim(identifier, subject, predicate, object, knowledge_kind, provenance, context, confidence)`: directed contextual knowledge triple.
- `ClaimContext(tissue, assay, population, comparison, treatment, species)`: explicit unknowns represented by None.
- `Provenance(source_kind, source_identifier, retrieved_at, source_uri, checksum, transformations)` and ordered `Transformation(name, version, parameters)`.
- `Study`: metadata, source/provenance, organisms, assay type, sample count, platforms, publications, BioProject and release date.
- `Hypothesis(identifier, title, revisions)` with immutable `HypothesisRevision` records.

Persisted schema version 1 defines entities, claims, claim transformations, transformation parameters, hypotheses, hypothesis revisions and hypothesis evidence links. Version 2 adds studies with child tables for organisms, platforms and publications. `schema_migrations` tracks applied version/name/time. Entity identity is `(kind, namespace, identifier)`; claim subjects and objects reference it with foreign keys.

Gene/protein identity is already distinguishable, but there is no explicit mapping object for gene-to-protein relationships. Dataset/sample/pathway references can participate in claims; dedicated repositories for all these kinds do not exist.

No persisted DiscoveryProject, TargetDiseasePair, Perturbation, InterventionStrategy, OpenQuestion, Experiment/Result, Structure, BindingSite, Compound detail, ChemicalSeries, Assay or BioactivityMeasurement was found. A drug entity reference and Open Targets drug candidate payloads are useful precursors, not equivalents to the requested chemistry model.

## C. Existing evidence architecture

The five current `KnowledgeKind` values are `source_assertion`, `axis_observation`, `axis_inference`, `ai_suggestion` and `researcher_hypothesis`. Preserve those serialized values. UI labels can map them to Source Fact, Computed Result, AXIS Inference, AI Suggestion and User Hypothesis. Add an explicit experimental-result kind for the sixth requested category rather than reclassifying old observations.

Claims are immutable and idempotent by identifier; conflicting content is rejected. Entity labels are similarly conflict-checked. Claim context, retrieval time, checksum and ordered transformations round-trip through the store. Inserts are transactional. Existing migrations are applied transactionally on store construction.

GEO discovery imports GSE study metadata through NCBI E-utilities. It records source URLs, retrieval times and source-record checksums. The ingestion service skips previously stored studies; it does not implement a refresh/revision policy. Matrix and supplementary downloads write separate manifests with URLs, timestamps, sizes and checksums. Preparation uses reviewed case/control/include patterns, retains ambiguous/unassigned records, and creates matrices plus manifests. Audits and analysis then produce file artifacts.

`RankingPublisher` in `axis/analysis/publish.py` is an explicit bridge from a primary recurrence ranking to stored claims. It rejects sensitivity rankings as primary evidence, uses checksum-derived claim IDs, records transformation parameters and publishes `axis_inference` claims. Most other analysis and target builders do not publish into the store.

Important gaps:

- Provenance records transformations but does not model a complete graph of input artifact IDs, source versions and claim derivations.
- SourceKind has only GEO, publication, AXIS pipeline, AI model and researcher values; newer source adapters need explicit identities.
- Study provenance transformations are permitted by the domain object but are not reconstructed/persisted by StudyRepository. Address this round-trip mismatch before adapters rely on them.
- Claims have no structured numeric result payload, evidence domain or relationship polarity.
- Context omits genotype/allotype, HLA, cell type, experimental system and endpoint.
- Confidence has no mandatory methodology. RankingPublisher uses `1 - adjusted_p_value`; this must not be shown as a probability of biological truth.
- General entity/claim search, pagination, project scope and graph queries are missing. Current list methods reconstruct records individually.
- No enforced source-kind/knowledge-kind compatibility contract prevents an incorrectly classified AI source from being inserted as evidence.

## D. Existing hypothesis architecture

Preserve the identity plus append-only revision design. Revisions carry state, description, rationale, evidence IDs, confidence and timezone-aware creation time. Sequence numbers must be contiguous; timestamps must be chronological. Persistence validates referenced claims and rolls back incomplete hypothesis writes.

States are draft, active, supported, challenged, rejected and archived. These are research workflow states; they should remain human-reviewed and must not automatically change when an experimental result arrives.

Current evidence links do not distinguish supporting, contradictory, neutral or inconclusive findings and have no per-link reasoning/provenance. There are no structured alternatives, missing evidence, uncertainty or experiment links. There is also no general CLI hypothesis-editing workspace or automatic end-to-end population of revisions from the broader analysis outputs.

Extend revisions with typed assessment links. Preserve legacy `evidence_ids` and historical ordering as untyped evidence considered; do not retrospectively infer that every legacy link supports the hypothesis. Missing evidence should refer to questions/requirements, not fabricated claims.

## E. Current UX

The usable product is a console interface and generated scientific files/reports. It supports study search, downloads/preparation, audits, analyses, rankings, target dossiers, readiness and reproducibility commands. It has no inspected browser app, REST API, persistent graphical project workspace, evidence drawer or interactive graph.

Existing readiness and focused dossier outputs already separate mechanistic follow-up from therapeutic readiness and retain uncertainty. Reuse their reasoning patterns and artifacts. A focused dossier also generates proposed perturbation experiments, but these are file rows with preset contexts/design choices, not recorded experiments or evidence of performance.

The new web experience should expose the same store and scientific services. It must never recompute biological conclusions in browser components or maintain a separate knowledge database.

## F. Preserve / extend / replace

| Subsystem | Classification | Rationale |
|---|---|---|
| Frozen domain primitives and stable IDs | PRESERVE / EXTEND | Sound evidence-first foundation; add discovery objects and missing context |
| DuckDB and EvidenceStore boundary | PRESERVE / EXTEND | Existing transactions, FK relationships and recoverable files are sufficient for relational graph semantics |
| SQL migrations 001/002 | PRESERVE | Append new versions; never rewrite deployed migrations |
| Claim immutability and transformation order | PRESERVE / EXTEND | Add typed derivation/input links and evidence roles without mutating old records |
| Hypothesis revision history | PRESERVE / EXTEND | Add typed links, alternatives and experimental interpretation |
| GEO and public-source clients | PRESERVE / EXTEND | Keep tested downloads/audits; normalize provenance contracts and refresh behavior |
| Statistical and participant-aware analyses | PRESERVE | Keep independence, context, effect-scale and validation guardrails |
| File/manifests workflow | PRESERVE / EXTEND | Files remain reproducible artifacts; register references and publish selected claims explicitly |
| Target readiness/dossiers | EXTEND | Reuse evidence dimensions and reasoning; represent outputs as structured assessments |
| Fixed project orchestrator | REFACTOR incrementally | Preserve existing entry points; add project-aware configuration without changing historical frozen studies |
| Large CLI module | REFACTOR incrementally | Extract services shared by CLI/API; preserve command names and options |
| Tests, demo, benchmarks, release pipeline | PRESERVE / EXTEND | Protect installation and scientific regression baseline |
| Scientific policy | PRESERVE / EXTEND | Clarify decision-support and experiment-proposal scope |
| Scope documentation | EXTEND | README/first-slice deferred statements lag current code |
| Existing application architecture | No wholesale REPLACE | Neither another database nor a parallel scientific backend is justified |

## G. Proposed schema changes

These are design proposals, not migrations already made. Use frozen domain models in `axis/domain/`, repositories exposed through EvidenceStore, and service logic in the existing analysis/targets boundaries. All scientific records reference existing claims and provenance rather than copying evidence text.

Common conventions: stable IDs, timezone-aware timestamps, explicit missing values, revision history for editable scientific content, external identifiers with source references, FK-backed relationship tables, and evidence links carrying role, reasoning, context and provenance. Extend entity kinds only when needed for claim/graph endpoints; register new scientific identities using the existing entities table. Avoid polymorphic string links without validated endpoints.

| Proposed object | Principal fields and relationships |
|---|---|
| TargetDiseasePair | pair_id; target gene/protein entity FK; disease entity FK; explicit indication scope; uniqueness on normalized target/disease/context |
| DiscoveryProject | project_id; pair_id FK; objective; status; created_at; updated_at; project revision; claim/hypothesis/artifact membership tables |
| Perturbation | perturbation_id; target FK; type; direction; intervention reference; context FK; genotype/allotype; system; assay FK when available; endpoint; observed-effect claim ID; experiment ID when available; knowledge kind; provenance |
| InterventionStrategy | strategy_id; project FK; strategy type; description; rationale; revision; evidence links; perturbation, question and later compound/experiment links |
| OpenQuestion | question_id; project FK; question text; uncertainty type; status; revision; target/disease/context; hypothesis/strategy/mechanism links; evidence links; resolution assessment |
| ScientificContext | context_id; existing ClaimContext fields plus cell type, genotype, HLA status, allotype, system, endpoint, time/dose where relevant; provenance for asserted context |
| EvidenceAssessment | assessment_id; claim_id FK; project/pair scope; domain; role; reasoning; context; provenance; revision; reviewer/status |
| Mechanistic relationship | existing Claim triple plus relationship assessment: directly demonstrated, inferred, computationally predicted or hypothesized; links to underlying claims and context |
| SourceSnapshot / Artifact | source/artifact ID; source kind and external ID; URI; retrieval time; checksum; media/schema type; importer/AXIS versions; immutable input and output links |
| DruggabilityAssessment | target; modality/site; assertion claim; supporting/contradictory claims; context; methodology; reviewer; revision |
| Structure / BindingSite | target FK; experimental/predicted origin; external ID; structure version/model/chain; site type; residues with numbering namespace; supporting claims; ligand links; provenance |
| Compound / ChemicalSeries | compound ID; name; sourced aliases and external IDs; optional structure notation/version; series ID and membership; source references |
| Assay | assay ID; original source ID; assay type; target/system/context; protocol version; endpoint; provenance |
| BioactivityMeasurement | measurement ID; compound/target/assay FKs; measurement type; original relation, value, unit and source text; conditions; provenance; optional separately recorded normalization |
| Experiment / ExperimentRevision | experiment ID; project; origin; status; question/hypothesis/intervention links; system/context/genotype; assay/endpoint; versioned design; provenance; expected outcomes |
| OutcomeScenario | experiment revision; scenario ID; possible result; interpretation; affected hypothesis/question; provenance; suggestion kind |
| ExperimentalResult | result ID; experiment revision; actual observations; result claim IDs; input artifacts; provenance; quality assessment; interpretation recorded separately |
| HypothesisAssessment | hypothesis revision FK; claim/result FK; supports/weakly_supports/contradicts/neutral/inconclusive/untyped_considered; reasoning; provenance |
| EvidenceGapAssessment | project/question; rule ID/version; corpus snapshot; searched sources/context and coverage; matched evidence IDs; missing requirement; explanation; creation time |

Experimental origin and epistemic class are orthogonal. A proposed AXIS experiment is not an experimental result; an author-reported experiment is a source assertion unless its results are represented explicitly. Typed proposed and performed perturbations must also remain distinguishable.

Matrix states need deterministic rules and coverage metadata. `not assessed` means no assessment; `no evidence identified` requires an explicit search/index scope. Substantial/limited thresholds must be documented and account for independent sources, directness and relevant context. No arbitrary numerical truth score is proposed.

Initial migrations should be small: 003 discovery context/projects/strategies/questions/perturbations; 004 evidence membership, derivation and typed assessments; 005 structures/sites; 006 chemical matter/assays/measurements; 007 experiment revisions/results/outcomes. Exact numbering remains subject to the checkout at implementation time. Additive joins preserve legacy records. Back up existing files, test migration from schema 2, preserve old enum values/default constructors, and verify installed-wheel migration resources.

## H. Proposed UX information architecture

Add a thin local Python API under `axis/api/`, backed by EvidenceStore repositories and shared services. A proposed TypeScript web client under `web/` is a presentation layer for AXIS, not another scientific architecture. Framework/dependency versions should be checked when implementation begins. A packaged `axis serve` entry point should provide the local application; no cloud deployment is assumed.

| Routes | Purpose |
|---|---|
| `/`, `/projects`, `/projects/:id` | Home, project list, active project overview |
| `/diseases`, `/targets`, `/targets/:id` | Source-linked entity exploration |
| `/projects/:id/evidence` | Clickable nine-domain evidence matrix and filtered records |
| `/projects/:id/mechanism` | Contextual path and bounded graph with inspectable edges |
| `/projects/:id/perturbations` | Proposed/performed perturbations with observed results and context |
| `/projects/:id/questions`, `/projects/:id/next-experiments` | Uncertainties, rationales and alternative outcome implications |
| `/projects/:id/decision` | Known evidence, uncertainty, competing strategies, gaps and candidate experiments |
| `/projects/:id/druggability`, `/projects/:id/structures` | Evidence-backed modality and structural assessments |
| `/projects/:id/compounds`, `/compounds/:id`, `/assays` | Original measurements, selectivity context and compound details |
| `/projects/:id/experiments`, `/experiments/:id` | Versioned design, results and separate interpretation |
| `/sources`, `/datasets`, `/literature`, `/about`, `/documentation` | Data coverage, original sources and product scope |

Shared components: AppShell, Sidebar, GlobalSearch, ProjectHeader, EvidenceBadge, ProvenanceBadge, EvidenceCard/Drawer, EvidenceMatrix, EvidenceGraph, MechanismPath, InsightList, UncertaintyCard, CompoundTable/Card, ExperimentCard, SourceList and AskAxisPanel.

Persist sidebar and active project context. Use concise tables, semantic headings, restrained styling, text labels alongside symbols/colors, keyboard navigation, drawer focus management and loading/error/empty states. Overview graph edges must select an assessment and expose its claims, context, original source and transformation chain. Paginate searches/tables; query bounded graph neighborhoods server-side.

Ask AXIS remains a secondary panel. First implement deterministic project-scoped retrieval with cited object IDs and links. Optional generated synthesis must retain citations, disclose missing coverage and never write its response into evidence automatically. A deterministic answer is not an AI-generated answer and should be labelled accordingly.

## I. ERAP1 × axSpA smallest useful vertical

Create `AXIS-DD-ERAP1-001` with the supplied objective and a generic target-disease pair. Keep ERAP1-specific content in a curated data package and project configuration.

Deliver one inspectable chain: source snapshot → contextual claim → mechanism relationship → recorded perturbation → competing intervention strategies → unresolved question → proposed discriminating experiment with at least two outcome/interpretation scenarios.

Initial scope: project overview, evidence matrix, mechanism/perturbation view, question detail, candidate experiment and decision summary. The chemistry and structure pages can show explicit unassessed states until sourced records are available; complete chemistry is not a prerequisite for this useful slice.

Curate primary public evidence for genetics, genotype/HLA context, relevant functional perturbations and mechanism. Do not treat the supplied example mechanism as established evidence. Track disease definitions explicitly: ankylosing spondylitis data cannot silently stand for every axSpA subtype. Compare complete inhibition, partial inhibition, allosteric and allele/allotype-specific modulation as competing hypotheses, without selecting a winner.

Existing local ERAP1 rows occur in expression recurrence/concordance outputs. For example, the three-study output records mixed directions and `recurrent=False`. Those are local computed expression findings, not proof against genetic involvement or pharmacological modulation. Validate artifact provenance before importing and preserve the negative/context-specific result.

A candidate experiment can compare relevant ERAP1 contexts with selected modulation in an HLA-B27-positive system, measuring biochemical activity separately from the relevant immunopeptidome and phenotype. Store it as an AXIS proposal. Include controls, selectivity checks, alternative outcomes and feasibility uncertainties; obtain scientific review before presenting protocol details as validated. No results or potency values should be invented.

Acceptance: a scientist can open the project, inspect a mechanistic claim, reach its original source, inspect competing strategies, open the central uncertainty, and inspect the candidate experiment's rationale and alternative implications. Unknown and contradictory evidence remains visible throughout.

## J. Independently testable implementation milestones

Each milestone gets a small reviewable change and documentation update. Existing CLI/scientific regression tests remain part of the acceptance gate.

| Milestone | Goal and affected modules | Schema impact | Required tests | UX impact and completion criterion |
|---|---|---|---|---|
| 1. Provenance compatibility | Extend `axis/domain/models.py`, storage serialization/repositories, `tests/test_domain.py`, `tests/test_storage.py` | Add experimental-result kind, source identities, persisted study transformations and context extensions additively | Legacy constructors/records, classification compatibility, source/transform round-trip, schema-2 upgrade/reopen, rollback | Stable labels defined; old records reconstruct identically |
| 2. Discovery domain | New `axis/domain/discovery.py`; discovery repositories exposed through EvidenceStore; service methods shared with CLI | Projects/pairs, perturbations, strategies, questions and FK relationships | Invalid/dangling links, target-disease scope, revisions/idempotency, unknown context, suggestion versus observation | Project creation/list/detail usable through services/CLI; arbitrary targets supported |
| 3. Evidence bridge and validation | Extend `axis/analysis/publish.py`, target assessment services, provenance/artifact repository | Artifact/derivation links, project evidence membership, domains and typed assessments | Input checksums, role separation, negative/contradictory evidence, duplicate source independence, legacy hypothesis evidence | Deterministic matrix and inspectable mechanism/perturbation data; file outputs remain reproducible |
| 4. Core API and UX | `axis/api/`, shared service boundary, `web/`, package configuration and new UI tests | No separate database; repository search/pagination additions | API scope/serialization/errors, project→claim→evidence→source; accessible drawer and bounded graph | App shell, project overview, matrix, mechanism and questions operate against real store records |
| 5. First ERAP1 scientific loop | Curated `axis/resources/discovery/erap1-axspa/`, adapter fixtures, discovery documentation | Minimal proposed experiment/outcome records introduced before the full experimental workspace | Source checksums/citations, known missing states, project portability, non-ERAP1 fixture, uncertainty→proposal→rationale flow | First useful reference project completes the chain in section I |
| 6. Druggability and structures | Extend `axis/targets/`; focused UniProt/PDB adapters in `axis/ingestion/`; web views | Structures, sites, identifiers and druggability assessments | Predicted/experimental separation, residue numbering, source retention; pocket alone cannot establish druggability | Evidence-backed structures/sites inspectable, absent data explicit |
| 7. Chemical matter | Chemistry domain/repositories; focused ChEMBL/PubChem adapters; compound/assay UI | Compounds, series, assays and original bioactivity measurements | IC50/EC50/Ki/Kd, operators/bounds, units, assay conditions, source-preserving normalization, incomparable selectivity | Compound explorer/detail exposes measurements and transparent comparisons |
| 8. Full experimental loop | Extend domain/storage and hypothesis services; experiment workspace | Versioned designs, outcomes, actual results, hypothesis/question assessments | Proposed/performed separation, result provenance, immutable history, evidence roles, no automatic true/false transitions | Recording a result produces traceable evidence and a reviewed interpretation |
| 9. Decision support | Extend readiness/dossier services; new deterministic gap rules and decision endpoints/components | Gap/rule/corpus snapshots and assessment revisions | Explainable rule matches, not-assessed versus searched-empty, context mismatch, competing strategies | Decision page exposes every reason and candidate outcome; no automatic winner |
| 10. Grounded Ask AXIS and completed showcase | Structured retrieval service, optional model adapter, AskAxisPanel; full curated vertical and docs | Query/audit records if needed; no automatic evidence insertion | Citation validity, project isolation, unsupported questions, absent evidence, suggestion labelling and hallucination fixtures | Source-grounded answers and complete ERAP1 path through chemistry/experiments are reviewable |

Run full pytest, Ruff, strict mypy and the packaged offline demo at implementation gates. Add frontend checks when a frontend exists. Test an installed wheel and an old-store upgrade before release. Broad baseline failures must be distinguished from regressions because the working tree contains ongoing research changes.

## K. Risks and mitigations

| Risk | Concrete concern | Mitigation |
|---|---|---|
| Architecture | Web layer duplicates scientific reasoning or directly queries DuckDB | Shared services and EvidenceStore repositories; client receives assessments, not hidden scientific scoring |
| Concurrency | Multiple CLI/server writers and long computations compete for the local database | One owning write process, short transactions, job execution separated from request handlers; define local operation explicitly |
| Migration | Store construction upgrades immediately; packaged SQL or partially adopted enums break old installs | Additive transactions, backups, installed-wheel checks, schema-version compatibility checks and migration fixtures |
| Scientific modeling | Expression, genetics, biochemical potency and therapeutic benefit become conflated | Separate domains, original measurements, context and explicitly reviewed inference links |
| ERAP1 biology | Genotype/allotype/HLA and disease subtype determine interpretation | Store these contexts; do not encode a global inhibition preference |
| Contradictions | Different tissues, assays, doses or endpoints appear to contradict one another | Context-aware assessments; human review before contradiction labelling |
| Data quality | Cached aggregate payloads, duplicate studies and evolving external IDs inflate support | Immutable snapshots, source version/coverage, stable mappings and independent-source accounting |
| Provenance | File reports lose upstream ancestry when promoted to claims | Register input artifacts and derivation edges; never invent missing ancestry |
| LLM hallucination | Suggested protocols or answers become evidence | Preserve epistemic/source separation, citation validation and explicit review gates for promotion |
| Evidence gaps | An empty index is interpreted as absence throughout science | Store corpus/search coverage and use “No direct evidence identified in the indexed sources” |
| UX | Too many screens obscure the next scientific decision | Start with the smallest loop, shared drawer, project context and progressive detail |
| Compatibility | Fixed DDX24 workflows get generalized prematurely | Preserve existing commands/artifacts and add configuration around them incrementally |
| Validation | Focused checks mistaken for complete baseline assurance | Report the 21-test scope; run complete release checks before implementation/release claims |

## Review recommendation

Retain DuckDB, contextual claims, append-only hypotheses, source clients and scientific workflows. Begin with provenance compatibility and the discovery domain, then connect selected artifacts to the store and deliver the ERAP1 evidence-to-experiment workspace. Expand chemistry and AI interaction only after this chain is inspectable.

This assessment is the requested stopping point. No major implementation, scientific-data promotion, deployment or release has begun.
