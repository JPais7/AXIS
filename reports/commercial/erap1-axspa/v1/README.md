# AXIS commercial brief: ERAP1 × axial spondyloarthritis, v1.0

Source: clean `JPais7/AXIS` main, `8f4e7797075e2beb25ad80de13d90843ad4e9de2`.
Assessment date: 2026-10-05. English deliverables for the requested commercial audience.
Evidence cutoff means the frozen indexed snapshot through that date, not a systematic literature search through that date.

## Deliverables

- `executive/AXIS-ERAP1-axSpA-Executive-Brief.pdf`: 3-page standalone executive version.
- `full/AXIS-ERAP1-axSpA-Target-Decision-Brief.pdf`: 17 pages, starting with the executive version.
- `manifest.json`: inputs, package versions/hashes, state/rule fingerprints and PDF hashes.
- `state-snapshot.json`: fresh offline Evidence Store projection, including DecisionState, campaign, chemical-learning, selectivity, structural mapping and retrospective assessments.
- `traceability.json`: section map, full atomic assertions, contexts, assays, measurements, assessments and frozen references.
- `build.py`: editable scientific narrative and compact ReportLab template.
- `extract.py`: offline reconstruction from existing frozen packages; temporary database only.

## Reproduction

Use Python 3.12 and the AXIS dependencies from the source commit. From repository root:

```sh
PYTHONPATH=. python reports/commercial/erap1-axspa/v1/extract.py
python reports/commercial/erap1-axspa/v1/build.py
```

The rendering step needs ReportLab and pypdf, separate document dependencies; they are not added to AXIS dependencies. Both are available in the Codex bundled document runtime used for this delivery. Exported manifest preserves provenance. The builder verifies the core `axis/` tree against the pinned source commit, allowing the report files to be committed without making reproduction depend on the report commit SHA.

Run `validate.py` with the document runtime after generation. Scientific signature comparison uses decision/evidence/rule fingerprints, panel selection/descriptors, learning content key, structure coverage and retrospective conclusions, excluding incidental creation timestamps. PDF generation uses ReportLab invariant metadata.

## Review status and limitations

READY WITH CONDITIONS for design-partner discussion. Independent scientific and medicinal-chemistry review is pending. The report is not expert-approved investment diligence. All categorical evidence-layer positions and the decision headline are bounded editorial interpretations of the engine state, not new engine fields or validated target scores. Proposed experiment wording is AI-assisted, deterministically grounded and unperformed.

No synthetic experimental result is imported. The real ERAP1 retrospective cases retain their inconclusive result. No new scientific curation, campaign, engine redesign or Phase 3.10 was undertaken. No publication/push is implied by this artifact-generation task.
