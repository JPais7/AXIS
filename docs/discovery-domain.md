# Discovery domain foundation

AXIS persists a minimal source-to-proposed-experiment reasoning chain through
the existing DuckDB EvidenceStore. Claims remain the atomic knowledge record.
There is no web application or second scientific database in this phase.

## Domain objects

| Object | Meaning and persistence boundary |
|---|---|
| TargetDiseasePair | Gene/protein EntityRef × disease EntityRef plus indication scope. Stored identity uses kinds, namespaces, identifiers and whitespace-normalized, case-folded scope; labels and dates do not change identity. A different pair ID for the same identity is rejected. Gene and protein references are distinct, not automatically merged. |
| DiscoveryProject | Persistent workspace referencing a pair by ID, objective, controlled status and timestamps. Claim membership references existing claims without copying them. Separate from AxisProjectPipeline. |
| Perturbation | Target, typed perturbation/direction, context, optional intervention EntityRef and provenance. Proposed and performed are separate statuses. An observed effect references a stored observational claim, never inline result prose. |
| InterventionStrategy | Project-scoped intervention concept, rationale, proposal/review/archive status, provenance and knowledge kind. Several competing strategies can coexist without ranking. |
| OpenQuestion | Project-scoped uncertainty, controlled status, context and timestamps. Links to project claims, hypotheses, strategies and perturbations are inspectable. A question is not a claim or evidence. |
| EvidenceAssessment | Immutable project-scoped assessment of one claim against exactly one strategy, question or hypothesis revision. Carries role, reasoning and provenance. Roles: supports, weakly_supports, contradicts, neutral, inconclusive and untyped_considered. |
| MechanisticAssessment | Classification and reasoning/provenance attached to a project-member Claim, whose subject/predicate/object remains the mechanistic relationship. Classifications: directly_demonstrated, inferred, computationally_predicted and hypothesized. Context belongs to the underlying claim. |
| ProposedExperiment | Conceptual proposal addressing a question in the same project. Stores rationale, system, intervention and endpoint descriptions, context, origin, status and provenance. Contains no actual results. |
| OutcomeScenario | Possible outcome and interpretation linked to a proposed experiment. Its proposal origin/provenance is inherited from that experiment. It does not record an observed outcome. |

All new records are immutable/idempotent by identifier in this first version.
There is no project/question/strategy editing endpoint. Timestamps and status
fields describe the recorded state. Future editing must introduce append-only
revisions and explicit supersession; do not overwrite these scientific records.
Existing hypotheses continue to use their existing append-only revisions.

## Scientific boundaries

- A proposed experiment is not evidence.
- An evidence gap is not proof of absence. No automated gap detector is included.
- An intervention strategy is not a therapeutic recommendation.
- An AXIS inference is not a source fact.
- A mechanistic relationship can depend on genotype, HLA, allotype, system,
  cell type and endpoint.
- A project-member claim is not automatically supporting evidence. Read its
  knowledge kind and assessment role.
- Historical hypothesis `evidence_ids` remain untyped evidence considered.
  No migration retrospectively assigns support or contradiction.
- Proposed perturbations cannot have an observed-effect link. Performed
  perturbations may have unknown/unreported effects, represented by None.
- Observed-effect links require source assertions, AXIS observations or
  experimental results and reject AI sources. Performed status does not prove
  a favorable result.
- AI suggestions and researcher hypotheses cannot be promoted to observational
  evidence by a support/contradiction assessment. They can be recorded as
  untyped_considered. An AI mechanism can only be assessed as hypothesized.
- Experimental-result claims cannot have an AI-model source. Existing legacy
  knowledge values and meanings are not changed.

The current mechanism compatibility checks conservatively distinguish claim
kinds. Curating an author-reported prediction or inference may require a
separate AXIS interpretation claim referencing the source; no automatic
reclassification of published assertions occurs.

## Context and provenance compatibility

ClaimContext retains all six old optional fields and adds optional cell_type,
genotype, hla_status, allotype, experimental_system and endpoint. Unknown values
remain None, including when old stores are read. No constructor positional
arguments were reordered.

KnowledgeKind keeps source_assertion, axis_observation, axis_inference,
ai_suggestion and researcher_hypothesis unchanged, and adds experimental_result.
`axis_observation` is not relabelled or migrated into an experimental result.
No additional SourceKind is required for this phase.

Study provenance now preserves ordered transformations and ordered parameters,
including duplicate parameter keys. Claims retain their existing normalized
transformation tables. New discovery records use JSON only for nested context
and provenance; scalar fields and scientific relationships are relational and
foreign-key backed. Provenance JSON stores timezone-aware dates and reconstructs
immutable ordered transformations.

## Migrations

001 and 002 are unchanged. Two additive migrations are packaged:

- `003_provenance_context.sql`: nullable claim context columns; study
  transformation and parameter tables. Existing study records load with an
  empty transformation history. History lost before this fix cannot be recovered
  automatically.
- `004_discovery_foundation.sql`: pair/project/claim-membership tables,
  perturbations and project membership, strategies, questions and links,
  evidence/mechanism assessments, proposed experiments and outcome scenarios.

EvidenceStore applies pending migrations transactionally on opening, as before.
Tests build a schema-2 database with a legacy observation and hypothesis, back
it up before upgrade, migrate/reopen it, and inspect the unchanged backup.
Production database files are not modified by running the test suite. Back up a
real database while it is closed before opening it with an upgraded AXIS.
Rollback to older AXIS software should use that backup; no downgrade migration
is provided.

Compound project/question foreign keys prevent cross-project experiment and
assessment links. Repository checks enforce project claim/perturbation scope,
target compatibility and epistemic constraints. Batched question links and demo
creation are atomic. Nested repository transactions join the outer transaction;
an inner failure makes the whole operation rollback-only even if caught.

## Using the repositories and services

```python
from axis.discovery import DiscoveryService
from axis.storage import EvidenceStore

with EvidenceStore("development.duckdb") as store:
    # Explicit opt-in fixture creation, never implicit data ingestion.
    traversal = DiscoveryService(store).create_erap1_demo()
    loaded = DiscoveryService(store).inspect_project(traversal.project.project_id)
    assert loaded == traversal
```

EvidenceStore exposes target_disease_pairs, projects, perturbations, strategies,
questions, evidence_assessments, mechanistic_assessments, proposed_experiments
and outcome_scenarios alongside the existing claims/studies/hypotheses.
Repositories provide add/get/list operations, project-scoped lists where
applicable and explicit membership/link methods. DiscoveryService returns a
presentation-independent ProjectTraversal containing persisted objects and
question links. A future API can serialize these without Rich dependencies.

## DEVELOPMENT ERAP1 fixture and CLI traversal

Use a dedicated database:

```shell
axis --database .tmp/erap1-development.duckdb discovery demo
axis --database .tmp/erap1-development.duckdb discovery project list
axis --database .tmp/erap1-development.duckdb discovery project show AXIS-DD-ERAP1-001
axis --database .tmp/erap1-development.duckdb discovery project show AXIS-DD-ERAP1-001 --json
axis --database .tmp/erap1-development.duckdb discovery question list AXIS-DD-ERAP1-001
axis --database .tmp/erap1-development.duckdb discovery strategy list AXIS-DD-ERAP1-001
axis --database .tmp/erap1-development.duckdb discovery perturbation list AXIS-DD-ERAP1-001
```

The development fixture is repeatable and atomic. It creates:

1. ERAP1 × axSpA pair and draft DiscoveryProject AXIS-DD-ERAP1-001.
2. One **AI suggestion Claim**, with a hypothetical relationship to
   HLA-B27-associated peptide presentation; no source assertion is imported.
3. One **hypothesized** mechanism assessment referencing that claim.
4. One **proposed** modulation perturbation, with no observed effect.
5. Four competing **AI suggestion** strategies: complete inhibition, partial
   inhibition, allosteric modulation and allele/allotype-specific modulation.
6. A central OpenQuestion asking whether modulation changes relevant peptide
   presentation and downstream biology in an axSpA-relevant context.
7. One conceptual **AXIS suggestion** experiment separating biochemical activity
   from peptide repertoire and downstream readouts.
8. Two possible outcomes: relevant biology changes, or biochemical activity
   changes without the proposed downstream change; each has a conditional
   interpretation.

Every proposal with provenance uses an AI-model source labelled
`axis-development-demo:erap1-axspa:v1` and a fixture transformation explaining
that no scientific evidence was imported. The fixed fixture timestamp identifies
its version, not a literature retrieval date. This is a storage/reasoning demo,
not a source-grounded ERAP1 dossier. The fixture does not create new hypothesis
revisions or supporting-evidence assessments, and never chooses a strategy.

Human CLI output labels kinds and proposed status. The JSON traversal includes
the complete contextual claim, source identity, timestamps, transformations,
membership-derived records, mechanism reasoning, question links and possible
outcomes. These objects are loaded from the database, not generated at display
time. No compound, structure, source-backed performed perturbation or experimental
result is fabricated. Literature curation remains a separate future task.

## Deliberate remaining limits

No frontend, structures/chemistry adapters, Ask AXIS, result workspace or automated
gap detection is included. Project queries currently load small collections;
pagination and bounded API response models should precede a large web workspace.
Gene-to-protein mappings, ontology harmonization, complete artifact ancestry,
source refresh/version policy and reviewed author-reported mechanism adaptation
remain future work. A local CLI/server writer-ownership policy is still needed
before introducing a concurrent web server.

Next recommended phase: review these contracts, curate a small source-grounded
ERAP1 evidence package, then build a read-first graphical project workspace
against the existing services. Review that scope separately.
