# Phase 3.8 — Computational method audit

| Method | Computes | Supports | Does NOT support | Validation | Version |
|---|---|---|---|---|---|
| Descriptors (RDKit) | MW, Crippen logP, TPSA, HBD, HBA, rotatable bonds, charge, rings, Fsp3 | descriptive position against campaign-defined ranges | ADME, drug-likeness, developability, rejection | deterministic; not benchmarked | RDKit 2025.09.3 |
| Morgan/Tanimoto | similarity under radius 2, 2048 bits | "chemically similar to X under Z" | similar activity, selectivity, binding | none claimed | RDKit |
| Butina clustering | threshold clusters, sorted ids | diversity control | activity classes | deterministic given inputs | RDKit |
| Murcko scaffold | framework | grouping | observed SAR (none is indexed beyond 3 compounds) | — | RDKit |
| Compound preparation | canonical SMILES, stereo status, ETKDG conformer (seed recorded) | traceable representation | chosen stereochemistry/tautomer/protonation (explicitly not done) | coordinates not bit-reproducible across builds | RDKit |
| Structure preparation | chain A of 3QNF, ZN retained, waters/glycans/other chains removed | a documented receptor model | disease-relevant conformation; coordination chemistry | source checksum verified | gemmi 0.7.5 |
| Site definition | residues within 8 Å of ZN | a metal-centred region | a druggable pocket or validated site (radius is an AXIS choice) | none | gemmi |
| Docking | **not executed** | — | — | **Docking method validation not established for this target/site**: 3QNF has no bound drug-like ligand (no redocking), no suitable active/inactive set, standard scoring does not model zinc coordination | none installed |

## Circular validation

No method was tuned on Maben activity data, and none is claimed to predict it. Maben
compounds appear only as reference chemistry. No held-out evaluation set exists.

## External identity

Bestatin, captopril and vorinostat were verified against PubChem by InChIKey
(frozen in `erap1/v1/external-identity.json`). The check caught a wrong hand-typed
captopril stereocentre, now corrected. Identity verification is not pharmacology: their
inclusion is a hypothesis, and AXIS indexes no ERAP1 evidence for them.

## Residual risks

Similarity depends on the fingerprint and reference set; clustering on its threshold;
chemical diversity is not hypothesis diversity (2 scaffolds, 1 of 2 hypotheses here).
