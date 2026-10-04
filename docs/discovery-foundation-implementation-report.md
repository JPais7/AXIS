# Discovery foundation implementation report

Completed 3 October 2026. Scope: the approved minimum domain foundation only.
The scientific web application, chemistry, structures, Ask AXIS, experimental
result workspace and automated evidence-gap detection have not been started.

## 1. Files changed in this phase

Existing files extended:

- `axis/domain/models.py`: experimental-result classification, optional context
  fields and rejection of an AI source for the new result classification.
- `axis/domain/__init__.py`: public exports for discovery objects/enums.
- `axis/storage/store.py`: new repositories, extended claim storage, Study
  transformation persistence, nested rollback-only transaction composition.
- `axis/cli/main.py`: register the discovery command group; existing commands
  and the historical project pipeline are retained.
- `README.md`: discovery foundation usage and proposal-only fixture notice.
- `docs/first-vertical-slice.md`: link the original slice to the new documentation.

New implementation files:

- `axis/domain/discovery.py`
- `axis/storage/discovery.py`
- `axis/storage/migrations/003_provenance_context.sql`
- `axis/storage/migrations/004_discovery_foundation.sql`
- `axis/discovery/__init__.py`
- `axis/discovery/service.py`
- `axis/cli/discovery.py`

New tests/documentation:

- `tests/test_discovery_compatibility.py`
- `tests/test_discovery.py`
- `docs/discovery-domain.md`
- `docs/discovery-foundation-implementation-report.md`

Pre-existing modified/untracked analyses, benchmarks, manuscripts and research
assets were left outside the discovery-domain scope. The earlier Phase 0
assessment remains available in
`docs/drug-discovery-repository-assessment.md`. Build outputs, test databases,
backups and exported traversal were written under ignored `.tmp/`; no production
scientific database was migrated for this work.

## 2. Migrations added

`003_provenance_context.sql` adds six nullable Claim context columns and Study
transformation/parameter tables. `004_discovery_foundation.sql` adds relational
discovery objects, membership/link tables, typed assessments and conceptual
experiment/outcome tables. Nested provenance/context uses JSON; identities and
relationships remain FK-backed relational records in the existing DuckDB store.

Migrations 001 and 002 were not edited. A backed-up schema-2 store containing a
legacy AXIS observation and hypothesis was upgraded and reopened successfully.
The pre-upgrade backup remained schema 2 with its original claim.

## 3. New domain objects

TargetDiseasePair, DiscoveryProject, Perturbation, InterventionStrategy,
OpenQuestion, EvidenceAssessment, MechanisticAssessment, ProposedExperiment and
OutcomeScenario. QuestionLinks and ProjectTraversal provide typed relationship
and service-return models. Controlled enums cover statuses, perturbation types
and directions, intervention strategies, evidence roles, mechanism classes and
proposal origins.

Pair uniqueness is based on gene/protein and disease kind/namespace/ID plus
normalized indication scope. Pair IDs are explicitly supplied, and duplicate
semantic identity under another ID is rejected. Project records reference pairs
and existing claims; they do not duplicate evidence.

New records are immutable/idempotent. Future editable projects/questions and
strategies need versioning; this phase does not silently overwrite them.

## 4. Tests added

**53 new collected test cases** cover legacy knowledge values; separate
experimental-result classification; AI-source rejection; context and Study
transformation round-trip; pair uniqueness and entity-kind validation;
project persistence/membership; all initial perturbation and strategy types;
proposed/performed distinction; observed-effect reference checks; every evidence
role; unchanged historical hypothesis links; all mechanism classes; question
links and atomic rollback; cross-project rejection; proposed experiment and
outcome persistence; repeatable/reopenable ERAP1 fixture; absence of invented
results; actual FK failure rollback; nested transaction rollback-only behavior;
backed-up schema-2 migration/reopen; and CLI inspection/error flows.

Test evidence is explicitly synthetic and does not establish ERAP1 biology.

## 5. Full validation results

| Check | Result |
|---|---|
| Full existing + new pytest suite | **204 passed**, 14.16 seconds on the final run |
| Ruff, `axis` and `tests` | **Passed** |
| Strict mypy, domain/storage/discovery/new CLI | **Passed**, 10 source files |
| Repository-wide strict mypy | **Passed**, 93 source files |
| Packaged offline synthetic demo | **Passed, 9/9 checks** |
| Wheel build, without network/build isolation | **Passed** |
| Separate installed-wheel smoke check | **Passed** |
| Migration resources in installed wheel | All four SQL migrations present |
| Installed-wheel migration/reopen | Schema-2 upgrade, backup and reopen passed |
| Installed-wheel provenance/context | Study transformations and six new context fields round-tripped |
| Installed-wheel fixture and CLI JSON | Stored ERAP1 traversal reconstructed successfully |
| Installed-wheel offline demo | **Passed, 9/9 checks** |
| Diff whitespace check | **Passed** |

The final scoped validation passed after the discovery-domain changes were
isolated from unrelated research files. Full tests, Ruff and strict mypy now pass.

Wheel verification installed the local wheel into a separate target directory,
used isolated Python with that directory first on the import path, and asserted
that AXIS was imported from the installed files. Dependencies were supplied by
the existing environment without fetching packages. This is an installed-wheel
resource/migration check, not a fresh dependency-resolution test.

## 6. CLI demonstration

Executed against a dedicated development database:

```shell
axis --database .tmp/erap1-development-20261003.duckdb discovery demo
axis --database .tmp/erap1-development-20261003.duckdb discovery project list --json
axis --database .tmp/erap1-development-20261003.duckdb discovery project show AXIS-DD-ERAP1-001
axis --database .tmp/erap1-development-20261003.duckdb discovery project show AXIS-DD-ERAP1-001 --json
axis --database .tmp/erap1-development-20261003.duckdb discovery question list AXIS-DD-ERAP1-001
axis --database .tmp/erap1-development-20261003.duckdb discovery perturbation list AXIS-DD-ERAP1-001
```

Strategy listing is also available as `discovery strategy list <project_id>` and
is covered by the CLI integration test. Human inspection uses Windows-compatible
ASCII separators. JSON escapes non-ASCII characters to remain safe on older
Windows output encodings.

The fixture-creation command reports:

```text
DEVELOPMENT/DEMO: proposals only; no imported scientific evidence.
Created AXIS-DD-ERAP1-001; no strategy selected.
```

Complete stored traversal was exported to
`.tmp/erap1-development-traversal-20261003.json`.

## 7. ERAP1 stored-object traversal

1. TargetDiseasePair `AXIS-TD-ERAP1-AXSPA`: ERAP1 × axial spondyloarthritis,
   explicitly unassessed subtype applicability.
2. Draft DiscoveryProject `AXIS-DD-ERAP1-001`: the requested pharmacological
   modulation objective.
3. Project-member Claim `AXIS-DEMO-ERAP1-MECHANISM`: **ai_suggestion**, not a
   published fact. Its predicate is `hypothesized_modulation_may_alter`.
4. MechanisticAssessment `AXIS-DEMO-ERAP1-MECHANISM-ASSESSMENT`:
   **hypothesized**, with explicit unverified-development reasoning.
5. Perturbation `AXIS-DEMO-ERAP1-PERTURBATION`: **proposed**, **ai_suggestion**;
   observed-effect claim is None. No source-backed performed perturbation was
   added without sufficient curated evidence.
6. Four competing InterventionStrategy objects: complete inhibition, partial
   inhibition, allosteric modulation and allele/allotype-specific modulation.
   All are labelled AI proposals; no supporting evidence or winner is invented.
7. OpenQuestion `AXIS-DEMO-ERAP1-QUESTION`: the requested peptide-presentation/
   downstream-biology uncertainty, linked to the claim, strategies and proposed
   perturbation. It is a question, not evidence.
8. ProposedExperiment `AXIS-DEMO-ERAP1-EXPERIMENT`: conceptual comparison of
   modulation across relevant contexts, labelled **axis_suggestion** and
   **ai_suggestion**, with unresolved system selection and feasibility.
9. OutcomeScenario A: relevant peptide presentation/downstream biology changes;
   would support further mechanistic investigation, not prove therapeutic benefit.
10. OutcomeScenario B: enzyme activity changes without the relevant downstream
    change; would challenge that translation in the tested context.

All provenance-bearing proposals identify the AI demo-design source
`axis-development-demo:erap1-axspa:v1` and ordered fixture transformation.
No retrieved publication, verified source fact or experimental result is claimed.
This is a deliberately incomplete architecture fixture. Generic synthetic tests
exercise source assertions and observational claims separately.

The CLI JSON and DiscoveryService return these records and links from storage;
display does not generate scientific prose or silently enrich the fixture.

## 8. Backwards compatibility

- Original KnowledgeKind serialized values retain their meaning.
- `axis_observation` remains unchanged; `experimental_result` is additive.
- Old ClaimContext arguments retain their order and defaults; new fields are
  optional and old records reconstruct with None values.
- Claim immutability, idempotency and ordered transformations remain intact.
- Hypothesis revisions remain append-only; legacy evidence remains untyped.
- Existing GEO, analyses, CLI and project-pipeline tests pass.
- SourceKind was not expanded unnecessarily.
- Existing stores migrate additively. Keep a closed-file backup for recovery;
  no downgrade migration is supplied.
- Previously lost Study transformation history cannot be recreated automatically.

## 9. Unresolved issues

New scientific records intentionally have no editing/revision service yet. Pagination,
web-server connection/writer ownership, gene-to-protein mappings, ontology
harmonization, complete upstream artifact ancestry and source refresh/version
policies remain future work. Mechanism epistemic checks are conservative;
curated author-reported predictions/inferences may require an explicit separate
interpretation claim. The ERAP1 fixture has no source-grounded biology dossier.

## 10. Recommendation and stopping point

Review these persisted contracts and the conceptual traversal first. The next
separately reviewed phase should curate a small traceable ERAP1 evidence package
and add a read-first graphical project workspace using these services. Include
an inspectable evidence drawer and clear empty/unassessed states. Keep the full
test/type/lint and installed-wheel checks as acceptance gates for that phase.

This phase stops here. No later roadmap module was implemented or launched.
