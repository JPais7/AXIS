# Phase 3.8 — implementation and acceptance report

## Git

| | |
|---|---|
| Branch | `phase38-computational-discovery` |
| Base `origin/main` | `42bd276c842cca37fe2e3d427728c33ab38620c0` |
| Merge base | `42bd276c842cca37fe2e3d427728c33ab38620c0` |
| Acceptance code commit | `4b726fd37d7e166cff040f391982b1bff369bb40` (local gates below were run on it) |
| CI-fix commit | `c63913e9d549e3146c75e588b8881f2449af8824` (portable docking-stub tests; tolerant mypy ignores in untouched `chemistry.py`) |
| Earlier published HEAD | `bd053438bc2962fd32b296749bb0376283509882` |
| Ahead / behind main | acceptance code commit: 4 / 0 (`bd05343` plus its ancestors, and the hardening commit); the documentation commit that adds this report follows it |
| Merges | none; no phase-3.7 or `codex/phase2-transfer` history |

Hygiene findings fixed during acceptance (history is not rewritten, nothing was
force-pushed):

* `web/node_modules` had been committed as an absolute symlink to a local path by
  `bd05343`; removed in the hardening commit and ignored (`web/node_modules` without a
  trailing slash, which a symlink needs).
* `structure-viewer-*.js` carried unrelated bundle noise; restored to main.
* Playwright's own `docs/screenshots/phase2-hardening/` outputs were not committed.
* No unrelated research (grep and manual inspection of every path).

Path classification of `origin/main...HEAD`: `PHASE38_CORE` (`axis/computational/*`,
`axis/storage/computational.py`, migration 012, `axis/cli/campaign.py`),
`PHASE38_RESOURCE` (two `computational-discovery` packages), `PHASE38_TEST`,
`PHASE38_DOC`, `PHASE38_UI` (`web/src/campaign.ts`, tests, rebuilt workspace bundle),
`PHASE38_BUILD` (three scripts, `pyproject.toml`, `.gitignore`),
`SHARED_REQUIRED` (`axis/api/server.py`, `axis/cli/main.py`, `axis/storage/store.py`,
`web/src/main.ts|components.ts|hardening.css`, schema-version assertions in 9 older
tests). `UNRELATED`: none. `REVIEW_REQUIRED`: none.

## Architecture

`axis/computational/`: `chem.py` (RDKit), `structure.py` (gemmi), `prioritize.py`
(rules `PRIO-001…009`, fingerprinted), `docking.py` (orchestration only),
`epistemics.py` (boundary validation), `service.py` (register, prepare, run, view,
report, review). Storage: `axis/storage/computational.py` (immutable puts; identical
re-insert is a no-op, a change is a conflict) and `012_computational_discovery.sql`
(11 tables, no DROP/ALTER/UPDATE/DELETE). CLI `axis campaign|chemistry|compound`;
read-only project-isolated API; workspace page *Computational Campaigns*. Decision
integration: each experimental package carries the *current* critical uncertainty read
through the decision rules; no decision state, claim or result is written (tested).

## Frozen methods (exact)

| Method | Parameters | Library |
|---|---|---|
| Canonical/isomeric SMILES, formula, MW, InChIKey | as written; no salt stripping, stereo assignment, tautomer or protonation change | RDKit 2025.09.3 |
| Descriptors | MW, Crippen logP, TPSA, HBD, HBA, rotatable bonds, charge, rings, Fsp3, heavy atoms; ranges are campaign data, flags only | RDKit |
| Similarity | Morgan radius 2, 2048 bits, no chirality, Tanimoto; invalid molecule → `None` | RDKit |
| Clustering | Butina, distance 1−Tanimoto, threshold from the campaign (0.7), sorted ids | RDKit |
| Scaffold | Bemis–Murcko | RDKit |
| Conformer | ETKDGv3, seed 20260101 (recorded; not used for scoring; not bit-reproducible across builds) | RDKit |
| Structure preparation | chain A of PDB:3QNF, ZN retained, water/glycans/other chains removed, no hydrogens, source sha256 `04b29d42…` checked | gemmi 0.7.5 |
| Site | residues within 8.0 Å of ZN, chain A, 21 residues (deterministic) | gemmi |
| Prioritization | `PRIO-001…009`, version `axis-prioritization-1`, persisted fingerprint | — |
| Docking | **not executed** | none |

Every stored observation carries `method`, `tool`, `tool_version`, `parameters`,
`input_sha256` and `output_sha256` (hash of its output); an observation lacking any of
them, or declaring `experimental_result`, `source_assertion` or `experimental: true`, is
refused (`epistemics.validate_observation`).

## ERAP1 campaign

* Target: `UniProt Q9NZ08` / project `AXIS-DD-ERAP1-CURATED-001` (existing identity
  reused; no competing target record).
* Structure: PDB:3QNF chain A; 696 resolved polymer residues of a 954-residue entity
  (missing residues stay explicit); ZN retained as context only (coordination not
  modelled and not used by any calculation); the 8 Å ZN region is *a
  computationally defined structural region*, not a validated or druggable pocket, and
  3QNF is not claimed to be the disease-relevant conformation.
* Chemical space (6): Maben compounds 1–3 (indexed identities verified against the
  store; reference chemistry) + bestatin, captopril, vorinostat.
* Hypotheses (2): `zinc-binding-chemotype` (researcher hypothesis) and
  `maben-series-analog` (AI suggestion).
* Panel: 3 exploration candidates (bestatin, captopril, vorinostat), 0 exploitation
  (maximum Tanimoto to reference chemistry 0.17 < 0.40; the threshold was not relaxed).
* **Chemical diversity ≠ hypothesis diversity.** Chemically: 3 clusters but only
  **2 distinct Murcko scaffolds** (bestatin and vorinostat both reduce to benzene).
  Hypothetically: **1 of 2** hypotheses tested. `maben-series-analog` has no candidate
  because the supplied space contains no analog; that is reported, not repaired.
* Docking: `method_unavailable`, `validation_not_established`, `execution_not_attempted`,
  `no_result`. Reasons: no engine installed, no PDBQT toolchain, 3QNF has no bound
  drug-like ligand (redocking impossible), no active/inactive validation set, standard
  scoring does not represent zinc coordination.
* Every candidate: pending review, `ai_suggestion`, strongest reason against, falsification
  conditions, experimental package, no indexed ERAP1 evidence.

## External compound identity audit

Verified against PubChem PUG REST by InChIKey, frozen in
`erap1/v1/external-identity.json` (response sha256, URL, retrieval time; PUG REST exposes
no release id). Result: bestatin CID 72172 — match; vorinostat CID 5311 — match;
captopril CID 44093 — **the hand-typed SMILES was wrong** (a diastereomer at the methyl
stereocentre, InChIKey `…BQBZGAKWSA-N` instead of `…RQJHMYQMSA-N`); corrected to the
PubChem structure and pinned by a regression test. Verification establishes
*identity only*; the campaign and every surface say it says nothing about ERAP1
pharmacology. The three compounds remain `researcher_supplied` with
`externally_verified_identity`.

## Validation (all run on the acceptance code commit unless stated)

| Gate | Command / scope | Result |
|---|---|---|
| Phase 3.8 tests | `pytest tests/test_computational.py` | 78 passed |
| Full Python | `pytest` | 630 passed, 2 skipped |
| Ruff, Phase 3.8 scope | computational package, storage, CLI, tests, three scripts | all checks passed |
| Ruff, `axis tests` | | 4 findings (`UP038`), identical to main |
| Ruff, global `.` | branch vs `origin/main` | 289 vs 289 (no new debt) |
| mypy strict | `mypy axis` | no issues, 153 files |
| Frontend (clean `npm ci` copy) | `tsc --noEmit`, `npm run lint`, `npm test` | pass; 56 node tests, 0 fail |
| Frontend build | `npm run build` | pass |
| Playwright | `campaign.spec` 1440/1024; `workspace.spec`, `pharmacology.spec` | campaign 2/2, pharmacology 2/2, workspace 4/5 (see below) |
| Migration 012 | clean DB; upgrade from a version-11 DB with Phase 3.7 data intact; read-only reopen; migrations 001–011 byte-identical to `42bd276` | pass |
| Deterministic replay | ERAP1 campaign from two clean store copies: panel, clusters, per-observation output hashes, site, structure and space checksums, rule fingerprint | identical |
| Offline replay | sockets blocked during ERAP1 and synthetic campaigns; installed wheel also blocks sockets for ERAP1 | pass |
| Installed wheel | built from the acceptance commit, clean venv, synthetic via CLI, ERAP1 via the package, packaged resources | pass |
| CLI / API smoke | help, refusals, full flow, CLI-vs-API equality, GET purity, project isolation | pass (in the 78) |
| Resource checksums | both packages vs manifests; manifest not self-referential | pass |

Classification of the one failing browser case: `workspace.spec` *development fixture*
needs project `AXIS-DD-ERAP1-001`, which the demo database does not contain —
ENVIRONMENTAL. A real Phase 3.8 regression found by the browser run and fixed: the
fixed sidebar had grown past the viewport (Sources unreachable); `.sidebar{overflow-y:auto}`.
Not executed: `decision.spec`, `results.spec`, `structure.spec`, `cellular.spec`
(they need separately provisioned databases/servers).

Environment: Python 3.14.6 (project target 3.12; CI covers it), Node v26.9.0, npm 11.19.1,
RDKit 2025.09.3, gemmi 0.7.5, DuckDB 1.5.5, NumPy 2.5.1, macOS-26.6.2 arm64.
Approximate runtime of the ERAP1 campaign (register, prepare, run): under 1 s.

## What Phase 3.8 does not establish

That any candidate binds, inhibits, activates, is selective for, or engages ERAP1 in
cells; that any candidate modifies HLA-B27 biology or axSpA biology, is safe, or is a hit,
lead or drug candidate; that the defined region is clinically relevant or druggable; that
docking is validated for this campaign; that computational prioritization predicts
therapeutic success. The ERAP1 chemical space is deliberately small; hypothesis coverage
is incomplete; external chemical identity does not establish ERAP1 pharmacology;
similarity depends on representation and reference set; clustering depends on method and
threshold; absence of a candidate for a hypothesis is not evidence the hypothesis is
false; AXIS performed no wet-lab validation.

## Scientific acceptance

1. Reproducible candidate panel from target/structure/chemical space: **SUPPORTED**
   (identical across clean stores, offline).
2. Explaining each selection without an aggregate score: **SUPPORTED**
   (`aggregate_score` is always null; rule-based; no weighted terms in the code).
3. Prediction versus experiment distinction: **SUPPORTED** (class guard, tested invalid
   transitions, overclaim scan of UI/CLI/docs/reports).
4. Multiple meaningful chemical hypotheses tested by ERAP1 campaign: **PARTIALLY
   SUPPORTED** — chemically diverse (3 clusters, 2 scaffolds) but one of two hypotheses.
5. Prioritized compounds experimentally active against ERAP1: **NOT DEMONSTRATED**
   (expected; no experiment exists).

Product value beyond a molecule list: **SUPPORTED IN TESTED CASES** — each candidate
exposes why it exists, the hypothesis it tests, computational evidence and its limits,
redundancy and hypothesis coverage, missing evidence, falsification conditions and the
experiment needed. Not claimed: general superiority.

## Release verdict

PASS WITH CONDITIONS — no independent medicinal-chemistry review, deliberately small
chemical space, no validated docking, incomplete hypothesis coverage, no experimental
validation; remote CI is recorded below.

## Remote CI

* `bd05343` (first publication): **failed** — Windows: docking stub test used a `#!/bin/sh` script (Phase 3.8 test defect, fixed); Ubuntu: mypy `unused-ignore` in `axis/pharmacology/chemistry.py` (pre-existing: `origin/main` CI fails identically).
* `c63913e` (GitHub Actions run 37244259181): **PASS** on Python 3.12 / ubuntu-latest, macos-latest and windows-latest.
* Local gates were not re-run after the two CI fixes; the remote run covers them.
