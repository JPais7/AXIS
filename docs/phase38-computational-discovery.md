# Phase 3.8 — Computational discovery engine

```
Hypothesis → site → chemical space → computational campaign → computational
observations → explainable panel → experimental package → (external result →
Phase 3.6 results loop → new DecisionState)
```

AXIS **computationally prioritizes molecules for experimental validation**. It does
not discover drugs, and nothing here is an experimental result, an active compound,
a hit, a lead or a drug candidate.

## Objects (migration `012_computational_discovery.sql`, additive)

| Object | Notes |
|---|---|
| ChemicalHypothesis | `researcher_hypothesis` or `ai_suggestion`; revisioned; carries falsification conditions |
| PreparedStructure | source id + sha256, chain, removed/retained components, metals, waters, hydrogens, limitations, output sha256, defined site |
| PreparedCompound | linked to, never replacing, the CompoundIdentity; records what was *not* done (no salt stripping, stereo assignment, tautomer normalisation, protonation) |
| ChemicalSpace | frozen, checksummed, bounded (≤1000); members keep origin and inclusion rationale |
| ComputationalCampaign | question, hypotheses, structure, site, methods, constraints, software; revisions are new rows; status `planned/prepared/completed/failed` |
| ComputationalObservation | generic payload; class `axis_observation`, `experimental: false`; `experimental_result`/`source_assertion` are refused |
| CandidateMolecule / CandidatePrioritization | panel with role, reasons, dimensions, flags, falsification, experimental package; rule fingerprint |
| Campaign artifacts / reviews | checksummed table; append-only human review (AI reviewer names refused) |

## Prioritization (no score)

Rules `PRIO-001…009` (`axis/computational/prioritize.py`, fingerprinted) decide only
panel membership: failed preparation excluded; indexed-experimental compounds are
*reference chemistry*, not candidates; exploitation vs exploration by similarity to
reference chemistry; role quotas and a per-cluster limit enforce diversity; fewer
descriptor flags first, then similarity direction, then stable id as a display
tie-break. Dimensions stay separate; `aggregate_score` is always `null`. An empty or
failed outcome is valid and never filled with invented candidates.

## Surfaces

CLI: `axis campaign register|list|show|prepare|run|candidates|report|review`,
`axis chemistry hypothesis|space list|show`, `axis compound computational <ref>`.
Read-only API under `/api/projects/{p}/campaigns`, `chemical-hypotheses`,
`chemical-spaces` (project-isolated). Workspace page **Computational Campaigns**.
The campaign reads (never writes) the current decision to link each experimental
package to the critical uncertainty.

## Implemented methods (and only these)

RDKit descriptors, Morgan/Tanimoto similarity, Butina clustering, Murcko scaffolds,
2D depiction, ETKDG conformer (recorded, not used for scoring); gemmi chain/site
preparation. Docking is orchestrated (`axis/computational/docking.py`, argument
arrays, timeouts, partial output = failure) but **not executed**: no engine is
installed and no PDBQT toolchain is a dependency. See the method audit.

## Not done

Pocket detection, pharmacophores, property-prediction models, live ChEMBL/PubChem
retrieval, 3D predicted-pose viewer (no poses exist), allosteric campaign (no
indexed evidence supports a specific site), independent chemistry review.
