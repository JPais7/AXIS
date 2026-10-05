# Prospective Validation Case #001 — EAST-1 / GRWD0715

## Outcome

**TECHNICALLY FROZEN; SCIENTIFIC CONTENT PENDING INDEPENDENT REVIEW.**
Long-horizon prospective decision validation, not a prediction of trial success
or failure and not a commercialization blocker. No future patient results were
identified in the bounded public sources used here. Private or undiscovered
results cannot be excluded. No Case #002 or new product phase was implemented.

Scientific cutoff: **2026-10-05**. Exact freeze:
**2026-10-05T17:46:36.536094+00:00**.

- Case: `AXIS-PROSPECTIVE-ERAP1-EAST1-001`
- T0 fingerprint: `382ca252aa26afbb94df16e77a9c88268824191ae430e006027a03311e1f051e`
- Manifest SHA-256: `7048400a3d71934ba0dd3cf407503b5020c8e1b9d432bf4351a78f7fea0834d7`
- Package: `axis/resources/validation/prospective/erap1-east1/v1/`
- Scientific inputs: six JSON files, 52,987 bytes including manifest/checksum;
  55,230 bytes including documentation. No bulk retrieval responses included.

This is a local recorded freeze, not a claim of independently timestamped public
preregistration or completed independent scientific validation. Preserve its
hashes, source files and pinned software when publishing or sharing it for review.

## Starting state and scope

Baseline main and branch HEAD before edits:
`d491ebe47ee0c40dfaa3823a44a9decd1afae29d`.
Dedicated branch: `validation/prospective-east1-erap1-axspa`, created from main,
not the failed exhaustive refresh. Working tree was clean after archiving three
pre-existing untracked caches and before implementation (17:32:04 UTC).
AXIS `0.2.1.dev0`; Python `3.12.13`; frontend package `0.2.0`.

The Recent Evidence Addendum **is not on baseline main**. This was disclosed
before choosing T0 content. Branch
`codex/erap1-recent-evidence-addendum-2020-2026` at
`8702046a995ce7f09b9c15b3bd9cd004e4d8cd21` was not imported. The failed refresh
is not a scientific input. Consequently this is not a claim to include a complete
2020–2026 literature refresh. Substrate/variant/cellular-context sensitivity from
main remains explicit; ERAP1 allotype, HLA subtype, ERAP2, tissue, substrate,
inhibitor mechanism, intensity, duration and disease stage remain required
context variables. Latest allotype literature was not newly adjudicated here.

Canonical DecisionState:
`decision-state:1:cebbae3880aeec90`, evidence digest
`cebbae3880aeec9084784f9f8df4a89abfe71a6058e3c924ce78651beaa44541`.
Snapshot `reports/commercial/erap1-axspa/v1/state-snapshot.json` SHA-256:
`83b2bcff0b58daccfeda58126d918d593e002e1499382f1ddfa450fe2737ee68`.
Its historical critical uncertainty remains `uncertainty:target_engagement`;
recommendation remains `decision:exp:chemical-genetic-engagement`.

Rules `axis-decision-3`, fingerprint
`184a1e2949a61e362545e897de43890014bcdcac7191f621c84fb2b739cecd33`.
Case metadata additionally pins the adapter implementation fingerprint, ten
relevant main resource manifests/versions and validation dependency versions.
No historical package was changed: SHA-256 comparison against baseline checked
**102 scientific resource/commercial files, zero changes**. Generated web assets
are excluded from that scientific-history count.

## Source verification and limitations

| Source | What can enter T0 | Limits |
|---|---|---|
| [ClinicalTrials.gov NCT07047703](https://clinicaltrials.gov/api/v2/studies/NCT07047703) | Official protocol, recruiting status, A–D design, planned outcomes; first posting 2025-07-02, actual global start 2025-07-28, public update 2026-09-18 | `hasResults=false`; enrollment is estimated; endpoints and completion dates are plans, not results |
| [EU CTIS 2025-521315-39-00](https://euclinicaltrials.eu/ctis-public/view/2025-521315-39-00) | Identifier correspondence in official public metadata | Partial access: retrieved body is an app shell; no structured EU protocol or experimental results adjudicated; shell hash is labelled as such |
| [Greywolf programme](https://www.greywolftherapeutics.com/grwd0715) | Programme identity/context observed by cutoff | Undated mutable sponsor page; no invented publication date; not independent replication |
| [Sponsor update, 8 September 2026](https://rss.globenewswire.com/news-release/2026/09/08/3357312/0/en/greywolf-therapeutics-doses-first-participants-with-axspa-in-novel-erap1-inhibitor-trial.html) | Healthy-volunteer SAD qualitative PK/engagement/tolerability claims; first patient MAD dosing | Sponsor-authored. No quantitative engagement, method, exposure–engagement curve or full safety dataset; no efficacy demonstrated |
| [FOCIS 2025 W146](https://focis-2025.eventscribe.net/fsPopup.asp?PresentationID=1615278&mode=presInfo) | Conference-reported biochemical processing inhibition, cellular HLA peptide changes and HLA/peptide-dependent CD8 responses | Official HTML abstract accessible through web retrieval; direct HTTP returned 403; full poster not obtained; limited methods; not an adjudicated experimental result |
| Main primary-source packages | Inherited genetics/processing/HLA/cellular context evidence | Frozen AI curation remains pending review; not silently upgraded by this case |

Registry response SHA-256 and source response hashes are in `source-index.json`.
FOCIS has **no claimed raw-body hash**: the retained paraphrases are pinned by the
evidence-snapshot checksum. Publication, study, presentation, registry-update,
sponsor-announcement, retrieval and freeze dates are separate. Unknown dates stay
null. Main source years are conservative availability upper bounds, not invented
publication days. CTIS/programme first publication is unknown; their retained
public observation is bounded by retrieval before the freeze.

The FOCIS abstract reports IC50 **60–400 pM** for precursor processing involving
GLRB, HelQ and SEC14L2, reduced 7–9-residue HLA-B*27 peptides, and suppressed
axSpA-associated-TCR-positive CD8 activation. These remain conference source
assertions. Construct/allotype, substrate sequences, HLA subtype, cell identity,
concentration/time/free exposure, replicates, quantitative uncertainty, selectivity,
TCR sequences and full functional controls are not reconstructed from assumptions.
The P2-anchor explanation is in silico, not independently demonstrated causation.

Human engagement classification: **preliminary human target engagement — sponsor
reported; independent methodological adjudication unavailable**. Single-dose
healthy-volunteer observations do not establish sustained patient coverage or
clinical benefit. The registry's Part B dose-selection threshold (Cavg ≥1166
ng/mL) refers to a predicted relative IC50 informed by oncology GRWD5769 modelling.
That proxy is not measured GRWD0715 engagement. Neither programme validates
Maben compounds, DG013A or unrelated historical chemistry.

Europe PMC exact-name/variant query, restricted to first-publication dates through
2026-10-05, returned **0 indexed hits** (query/date/response checksum retained).
This does not prove no publication exists. No additional material presentation
was identified in the focused public search; FOCIS programme/book entries duplicate
W146. A sponsor-reported US patent grant did not provide a verified chemical
identity/method mapping needed for this freeze; no patent example was guessed to
be GRWD0715. No exhaustive literature or patent review was launched.

## Scientific position and prospective test

Working hypothesis: pharmacological ERAP1 modulation may alter HLA-B27-associated
processing and immune recognition in biologically defined axSpA contexts.
Genetic/processing rationale is supported; programme pharmacological feasibility
and disease-relevant molecular signals receive preliminary support. Human PK and
engagement are qualitative sponsor reports. Human disease PD, therapeutic benefit
and axSpA efficacy remain unestablished; optimal subgroup and sustained window
remain unresolved. No arbitrary scores, probabilities or trial-success prediction.

H1 on-target therapeutic chain; H2 engagement/PD without clinical benefit;
H3 context-restricted benefit; H4 incomplete disease-mechanistic bridge;
H5 therapeutic-window limitation. Specificity controls remain required; missing
selectivity methods are not proof of an off-target mechanism.

U1 sustained human engagement → U2 human PD → U3 disease-relevant immune bridge
→ U4 clinical translation. U5 biological context modifies the chain; U6 safety
gates sustainable pharmacology. All six remain open at T0. U1 is the first
unadjudicated programme gate, not a replacement for the historical chemistry gap.

Five discriminators predefine measurement, tested uncertainties/hypotheses,
strengthening, weakening, ambiguous and non-interpretable outcomes and explicit
consequences. Seven scenarios A–G separate full-chain support, PD without benefit,
engagement without PD, systemic exposure without engagement, subgroup effects,
safety-limited pharmacology and invalid/ambiguous data. Inadequate engagement
does not universally falsify target biology; uncontrolled signals/underpowered
nulls do not force directional updates. Acceptable effect size, assays, power,
duration, multiplicity and clinical meaning need independent adjudication against
the released protocol/data, not invented numerical thresholds.

## Architecture and future reveals

The retrospective schema expects a sealed `future.json` already to exist, known
case horizons and retrospective adjudication. Using it unchanged here would
require inventing future observations or mislabelling an open-future case.
A single target-neutral adapter therefore reuses `KnowledgeKind`, temporal
canonicalization/digests, package checksums, `core.state_diff` and decision-rule
fingerprints. Scientific hypotheses/discriminators live in the resource, not a
new predictive engine. Replay reproduces the **curated, source-linked proposed
case state**, not an autonomous fresh adjudication of live literature.

No new domain model, enum, table, migration, service, endpoint, CLI command or
frontend page. The existing read-only `/api/benchmarks` list/detail includes the
case; the existing Validation view adds a small prospective rendering. T0 is
read-only. No reveal/approval HTTP endpoint exists. The historical CLI stays
retrospective; offline verification uses the supplied script/Python helper.

`prospective.reveal` accepts actual future release dates and T0 discriminator IDs,
checks intervention/provenance and chronological hash-chain integrity, and returns
newly supplied evidence, tested uncertainties/hypotheses, interpretation,
consequence, a **review-gated proposed case state** and causal diff. It performs
no persistence or approval. Retain each returned JSON as a new artifact and pass
the chain for the next reveal. T1 PK/engagement can inform a partial case update
without T4 clinical efficacy. T1–T4 are nominal evidence layers, not promised dates
or a mandatory release sequence. No real reveals exist yet.

Caller must verify source authenticity and curate methods/interpretability; a
boolean or provenance label alone is not independent scientific validation.
Sponsor-only or methods-unavailable signals do not resolve uncertainty. Ambiguous
or technically invalid inputs cause no forced positive/negative state change.
The canonical update field remains null: after independent review, an accepted
update must be explicitly versioned through the existing Experimental Results
Loop. The future display currently shows **None yet**; persistent reveal-history
integration is deferred until real public evidence exists, not fabricated now.

## Conservative cleanup audit

No scientific file, module, result, frozen package or historical DecisionState was
deleted. No duplicate evidence packages were inferred to be redundant merely
because they cover the same target. Builders remain necessary for reproducibility.

| Path/action | Reason and proof | Replacement / compatibility |
|---|---|---|
| `scripts/build_ddx24_pilot_documents_pt.py`: remove `pathlib.Path` import only | Ruff F401; name never referenced | None; document-generation logic unchanged |
| `scripts/build_ddx24_word.py`: remove `WD_SECTION` import only | Ruff F401; name never referenced | None; document-generation logic unchanged |
| `axis/resources/evidence-refresh/erap1-axspa/2020-2026/v1/records.json`: move out of repository | Pre-existing untracked raw failed-refresh cache, no tracked main reference | Recoverable local archive; scientific main history untouched |
| Same root, `continuation/openalex.json`: move | Same untracked raw-cache proof | Same recoverable archive |
| Same root, `continuation/openalex-partial.json`: move | Same untracked partial-cache proof | Same recoverable archive |
| `axis/resources/workspace/assets/index-C2dbb2dJ.js`: generated asset superseded by rebuilt index bundle | Generated runtime asset; rebuilt HTML/module imports reference its replacement | New generated index bundle; no scientific input/history deleted |

Archive: `/Users/joaopais7/Documents/axis-cache-archive-XG9RoM/`, preserving the
original relative paths. Total **130,384,875 bytes**. Original cache checksums:

- `records.json` (78,899,963 bytes): `43cef37f3488bb3a9e442e3369012a480fbe8888eadbecc79c4bdafe88a3c654`
- `openalex.json` (27,604,224 bytes): `088199b2f8f22c9f8d4f60289fe78368cab6cd6ea4eeb7c1b6f98b651a83f4df`
- `openalex-partial.json` (23,880,688 bytes): `cb41caad7bd3f2f7dc88514bf23a43b8c8e4a4a81f746136fc749ed4350befe3`

Incidental generated shader trailing whitespace was normalized to avoid unrelated
churn; the NGL viewer remains byte-identical to baseline. No manual NGL logic
changes. No large cache was included in the built wheel.

## Executed validation

| Check | Result |
|---|---|
| Focused prospective tests | **25 passed** |
| Full Python suite | **716 passed, 2 skipped**, 246.60 s |
| Ruff `axis tests` and new verification scripts | **PASS** |
| Global Ruff | **460 inherited findings**, versus baseline 462; two unused imports removed, no new diagnostic debt |
| Strict mypy `axis` | **PASS**, 163 source files |
| Frontend unit tests | **63 passed**, including prospective rendering |
| TypeScript and ESLint | **PASS** |
| Vite production build | **PASS**; inherited large NGL chunk warning retained, not redesigned |
| Browser prospective acceptance | **2 passed**, widths 1440 and 1024; no page errors or horizontal overflow; discriminator disclosure tested |
| sdist and wheel build | **PASS**, isolated build backend poetry-core 2.5.0 |
| Installed wheel, external temporary venv, socket connections blocked | **PASS**, pinned manifest/T0 equal offline |
| Historical scientific/commercial files | **102 checked, zero changed** |
| Database migrations | Not required: no schema changes; existing migration tests included in full suite |

Final wheel SHA-256:
`f4cf7365b17908412b8f3ab468127f9c6924920a70368d98c222fdea68f01e6b`.
Frontend runtime: Node `26.9.0`, npm `11.19.1`; build graph from the unchanged
`package-lock.json` (Vite `8.3.2`, TypeScript `5.9.3`, ESLint `10.0.3`).

Commands run from the active repository with explicit source import path:

```sh
PYTHONPATH=. python -m pytest tests/test_prospective.py -q
PYTHONPATH=. python -m pytest -q
ruff check axis tests scripts/freeze_east1.py scripts/verify_prospective_wheel.py
mypy axis
PYTHONPATH=. python scripts/freeze_east1.py
python -m build
PYTHONPATH=. python scripts/verify_prospective_wheel.py dist/axis_bio-0.2.1.dev0-py3-none-any.whl
```

Frontend: `npm ci`, `npm test`, `npm run typecheck`, `npm run lint`,
`npm run build`; focused Playwright tests used the new source server on a temporary
free loopback port and existing Chromium. Screenshots were inspected visually.
The existing user's servers/database were not modified. Installed-wheel AXIS was
isolated outside the checkout; existing runtime dependencies were reused after
that venv's package path. This is offline replay validation, **not** an independent
fresh dependency-installation or independent scientific review.

Initial checks encountered missing source import path, missing frontend packages,
an unavailable non-isolated build backend and an occupied UI port. Explicit
`PYTHONPATH`, locked `npm ci`, isolated build and an exclusively allocated port
resolved those environment issues; only successful final runs are counted above.
The initial UI run on an occupied port is not counted as acceptance.

## Acceptance V1–V14

| Criterion | Status | Basis / conditions |
|---|---|---|
| V1 — pre-cutoff evidence only | PASS WITH CONDITIONS | Dated/bounded public inputs, separate dates, no later evidence. Partial CTIS/abstract access, inherited curation and bounded search completeness explicitly limited; independent source review pending. |
| V2 — immutable T0 | PASS | Pinned files/manifest/state/software; reveal does not write or mutate; tampering rejected; no overwrite by freeze builder. Preserve the original version/commit; hashes are not an external timestamp service. |
| V3 — epistemic classes distinct | PASS | Sponsor, conference, registry and inherited primary sources retain classes; source assertions never promoted to performed experimental results. |
| V4 — intervention specificity | PASS | GRWD0715 ≠ Maben/DG013A/GRWD5769; cross-compound evidence rejected; canonical gap unchanged. |
| V5 — no trial prediction | PASS | Conditional hypothesis and unresolved competing explanations; no probabilities/scores/success call. |
| V6 — prospective discriminators | PASS | Five frozen measurements/uncertainty/hypothesis/consequence definitions. |
| V7 — directional/ambiguous/invalid outcomes | PASS | Each discriminator has all four classes; A–G map uncertainty and consequence. |
| V8 — partial reveals | PASS WITH CONDITIONS | T1/T2 synthetic tests pass without efficacy results. Real source verification and append-only artifact retention by caller required; no invented future evidence or automatic persistence. |
| V9 — causal comparison without T0 rewrite | PASS WITH CONDITIONS | Hash chain and existing causal-diff helper; future state is a pending proposal, not an approved canonical update. Human adjudication/versioned results-loop import required. |
| V10 — long horizon, no commercial block | PASS | Explicit status and future short-horizon design-partner criteria; Case #002 not implemented. |
| V11 — minimal reuse | PASS | One adapter; existing domain knowledge, temporal/hash/diff and API/UI surfaces; no new schema/service/page/model. |
| V12 — conservative cleanup | PASS | Two demonstrably unused imports; three recoverable untracked caches; superseded generated bundle only; 102 scientific files unchanged. |
| V13 — review gate | PASS | All new scientific curation/proposals pending; helper refuses self-approval; technical freeze is not scientific acceptance. |
| V14 — offline reproduction | PASS | Source and installed wheel reproduce exact state/manifest with networking blocked; compact frozen inputs retained. |

## Commercial boundary and next external work

Commercial brief untouched. Separate proposed scientific changes are documented in
`erap1-east1-commercial-proposed-diff-2026-10-05.md`, not silently applied.

Next priorities: independent scientific review, an external historical benchmark,
design-partner acquisition and a separate short-horizon prospective case owned or
executed by an external organization. AXIS must receive only pre-result inputs;
the outcome must be genuinely unknown at freeze and expected within months.
Use the existing Experimental Results Loop later. No additional product phase,
chemistry expansion or predictive model is part of this task.

**STOP condition reached after the checks above. No commit/push/merge performed
by this task; publication is a separate authorized action.**
