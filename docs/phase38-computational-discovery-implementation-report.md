# Phase 3.8 implementation report

Baseline `origin/main` `42bd276c842cca37fe2e3d427728c33ab38620c0`; branch
`phase38-computational-discovery` (no use of `codex/phase2-transfer` or the phase-3.7
branch). See the final message for gate results and the publication SHA.

## ERAP1 campaign

Question: which molecules of a bounded space justify experimental testing of
specific ERAP1 binding/modulation hypotheses. Structure PDB:3QNF chain A (sha256
`04b29d42…`), ZN retained, metal-centred 8 Å region (21 residues). Space: Maben
compounds 1–3 (indexed identities, verified against the store) + bestatin,
captopril, vorinostat (researcher-supplied, unverified). Outcome: panel of three
**exploration** candidates, all testing `hypothesis:erap1:zinc-binding-chemotype`;
exploitation role empty (maximum similarity 0.17 < 0.4); `maben-series-analog`
hypothesis untested by this space. Docking not executed. Every candidate: pending
review, no indexed ERAP1 evidence, experimental package attached.

## Generic fixture

`synthetic-generic` (SYNTHETIC / TEST ONLY): 7 invented compounds, one unparseable
(excluded and reported), exploitation + exploration panel, deterministic ordering,
no ERAP1 text anywhere.

## Limits

No docking evidence; single structural state; six-molecule space; no external
validation; no independent medicinal-chemistry review; no held-out set.
