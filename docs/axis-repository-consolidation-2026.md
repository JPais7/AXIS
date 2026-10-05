# AXIS repository consolidation — 2026-10-05

## Scope and immutable reference

Starting/scientific SHA: `84ecc56e74747bdee12ecdf15b9a80bc760798f4`
(`Resolve BRADSHAW assay provenance and record stable ERAP1 decision reassessment`).
Reference label: **ERAP1_DATA_RICH_SCIENTIFIC_REFERENCE_2026**.
Main/merge base: `d491ebe47ee0c40dfaa3823a44a9decd1afae29d`; reference is four
commits ahead, zero behind. Initial integration working tree was clean.
Active checkout was AXIS-evidence-refresh, not the older ambient AXIS checkout.
Consolidation branch: `codex/axis-consolidation-post-erap1-2026`.

Engineering implementation/review freeze:
`9694329295c18fe0dd177a51f81ddff51cc1e31a`.
The final candidate is this branch's documentation/validation closure commit,
whose full SHA is reported at hand-off; it adds no further runtime changes.
No push, merge, history rewrite, branch deletion, evidence acquisition, model
training, cutoff adjustment or commercial regeneration was performed.

## Inventory before refactoring

The [machine-readable inventory](consolidation/2026/repository-inventory.json)
reads every file from the exact reference Git object, not from a dirty checkout.
All **803 tracked files** receive a primary disposition: **779 KEEP, 5 GENERALIZE,
19 ARCHIVE, 0 DELETE**. Classification is deliberately conservative: unproven
redundancy is not grounds for removing provenance. Script roles and test taxonomy
are included; case-reference occurrences retain file/line/terms/classification.

The five generalized services are decision serialization, computational
serialization, learning dataset serialization, pharmacology import configuration
and cellular configuration/projection. The 19 logical archives comprise 12
historical narratives and seven one-off DDX24 authoring/screening utilities.
They remain at stable paths. **Physical moves: zero. Deleted files: zero.**
There were no deletions requiring a safety claim. Twenty duplicate hash groups
were found; required frozen snapshots/fixtures are not deduplicated by deletion.
The largest-file list distinguishes scientific/publication documents, figures and
frozen JSON. Ignored caches, dist, node_modules, test-results and a pre-existing
ignored commercial v1.1 directory are excluded, not deleted or promoted.

## Engineering changes, not scientific changes

- One canonical JSON implementation replaces three identical implementations;
  old helpers/imports and digest behavior remain compatible, including `default=str`.
- Existing primary/comparison target names and proposal wording move into an
  explicit ERAP1 case profile. Guarded ERAP1 reference imports remain guarded.
- Cellular biochemical projections query the project's registered target rather
  than using ERAP1 for every project. ERAP1 outputs remain unchanged; a synthetic
  second-target test proves that the generic projection no longer assumes ERAP1.
- Target-agnostic contracts expose inference-scoped limitations and curated
  qualitative comparability. They validate existing registry outputs; they do not
  invent an algorithm for scientific adjudication or quantitative potency ratios.
  A missing field is not automatically a global blocker; an explicit decision
  dependency is required. Numerical selectivity rules are untouched.
- Documentation now distinguishes current scientific state, architecture,
  reproduction instructions and historical phase narratives.

ERAP1-specific facts legitimately remain in named source packages, fixtures,
case import guards, curated demo/vertical import paths and checksum-bound replay
scripts. These are explicit case interfaces, not generic Decision Engine rules.
New target onboarding must supply its own sources, allotypes, substrates,
countertargets and hypotheses; a new source importer may be required. No
universal importer capability is claimed by extracting this profile.

## Golden-master equivalence

The pre-refactor reference was captured before existing production code was edited.
Historical personal source paths are bound by SHA-256 in the new audit projection,
not copied into another published provenance narrative. Original provenance bytes
remain unchanged. The projection changes audit representation, not source meaning.

[Golden comparison](consolidation/2026/golden-comparison.json): **PASS**, zero
changed dimensions. It covers evidence, uncertainties, causal diff, comparability,
allotype/substrate context, learning, claims, sources, Maben engagement, decision
classification, critical uncertainty, recommendation and replay/protected hashes.
Actual frozen replay reconstructs every reassessment output, including full
DecisionState v2 and its linkage to the actual canonical v1, not merely selected
labels. Eight mutation tests verify that material changes are refused.

**254 protected files** across resources, commercial v1 and benchmarks remain
byte-identical. The four evidence-integration versions and all existing package
manifests remain intact. The 152 existing runtime resources total 8,314,372 bytes;
each is also checked byte-for-byte in both wheel and sdist.

Scientific invariants:

- v1 `decision-state:1:cebbae3880aeec90` is not rewritten.
- v2 `decision-state:2:212f995ecc55c989` and causal diff reproduce.
- **DECISION STABLE**; critical `uncertainty:target_engagement`; next
  `decision:exp:chemical-genetic-engagement`.
- Historical Maben compound-specific engagement remains unresolved.
- BRADSHAW biochemical/cellular learning eligibility remains
  MODEL_ELIGIBLE_WITH_CONDITIONS; no model was trained, no old MODEL_NOT_BUILT
  history was overwritten, no censored/discordant values were silently repaired.
- Internal BRADSHAW biochemical SAR remains COMPARABLE under conditions;
  biochemical/cellular, Maben and pooled allotype panels remain NOT_COMPARABLE;
  BRADSHAW/Tinworth remains PARTIALLY_COMPARABLE.
- Pending review stays pending. Source assertions, calculations, AI suggestions,
  researcher hypotheses and preclinical observations retain their epistemic scope.
  No new engagement, selectivity, HLA-B27 or human clinical efficacy conclusion.

## EAST-1 and retrospective boundaries

The EAST-1 freeze is on a separate pre-existing branch,
`validation/prospective-east1-erap1-axspa`, at
`2e985b1bb2922b8bd970a24759755772d3107d09`, also verified on the remote.
It was deliberately not merged into the scientific reference. Its nine frozen
resource hashes are recorded in [related freezes](consolidation/2026/related-freezes.json).
The branch tip and scientific files remain unchanged; predictions/outcomes were
not rerun or interpreted. This audit does not claim EAST-1 prospective success.
Retrospective packages and historical temporal cutoffs remain byte-identical;
no future evidence was introduced or retrospective analyses regenerated.

## Commercial classification

**CURRENT_WITH_KNOWN_LIMITATIONS**, as a clearly versioned v1 deliverable.
Its engagement-first decision still agrees with v2 and its disclosed indexed-snapshot
scope remains valid. It is not a current full-corpus/learning summary. The
completion report's “ERAP1 predictive modelling remains refused” refers to its
historical dataset; it must not be generalized to the later eligible-with-conditions
BRADSHAW subsets. A future v2 brief would need revised source/assay coverage,
learning eligibility, DecisionState identifier/linkage and localized-method
limitations, while keeping “no model trained” and engagement-first boundaries.
No PDF or commercial source file was modified here.

## Dependencies, public interfaces and security

| Dependency | Disposition and evidence |
|---|---|
| duckdb | Runtime evidence storage, migrations and offline replay; keep |
| pytz | Indirect runtime requirement: fetching DuckDB current_timestamp loads pytz and returns pytz.tzfile; keep despite no explicit Python import |
| httpx | Runtime source connectors; keep |
| typer, rich | Runtime CLI/reporting; keep |
| numpy, scipy | Runtime analysis/learning/statistics; keep |
| matplotlib | Runtime scientific figures; keep |
| gemmi | Runtime structure parsing, pinned 0.7.5; keep |
| rdkit | Runtime chemistry/SAR, pinned 2025.9.3; keep |
| pytest, Ruff, mypy | Development-only testing/lint/type checking; keep |
| poetry-core | Build backend, not runtime; keep |

No direct dependency was verified obsolete. No versions, lock file, scientific
schemas, public CLI names, storage migrations, resource paths or API routes were
changed. Learning CLI remains `axis chemistry model/dataset/sar/prediction`, not
a top-level `axis learning`. Existing interfaces are exercised by the full suite.
Frontend files were unchanged, so no frontend rebuild was performed.

Pattern-based secret/path audit found five expired source-download URLs containing
AWS access-key identifiers, not secret keys. Each had a 2026-10-05 18:14:32 UTC
timestamp and ten-second validity; no URL/credential value is printed in the new
audit. Twenty-one personal/local-path occurrences belong to frozen provenance or
historical utilities. They are retained, not runtime prerequisites for offline
replay. No new private path, cookie/session credential, .env, cache or original
licensed PDF is included. Existing source exposure is documented, not rewritten
out of Git history. This is a hygiene audit, not a vulnerability certification.
Existing .gitignore already covers generated/cache directories; no change was needed.

## Verification and size

See [engineering checks](consolidation/2026/engineering-checks.json),
[clean-install replay](consolidation/2026/clean-install-replay.json) and
[installed versions](consolidation/2026/clean-install-requirements.txt).

- Full final suite: **785 passed, two skipped, zero failed**, 258.41 seconds.
- Focused new regression suite: 25 passed. Earlier full run: 775 passed, two skipped;
  ten subsequently added mutation/second-target tests are included in the final run.
- Strict mypy: pass, 166 source files. Ruff: pass for axis/tests and both changed
  audit tools. Global script findings remain 462, unchanged from the reference;
  they are inherited debt, outside the CI `ruff check axis tests` scope.
- Wheel/sdist build: pass. Fresh venv install: pass; pip check passes in both
  environments. Installed-wheel synthetic demo: 9/9; benchmark: two measured runs
  after one warmup; public decision/chemistry/model/benchmark help: pass.
- Clean git archive plus **installed wheel**, with socket connection disabled:
  scientific replay/equivalence pass in 8.124 seconds. This is a new environment
  on this Mac, not a claim of validation by a different person or operating system.
- Before/after resources: 8,314,372 → 8,314,795 bytes; +423 bytes of case configuration.
- Wheel: 2,162,823 → 2,165,268 bytes; sdist: 1,967,207 → 1,968,994 bytes, same
  builder. [Before](consolidation/2026/package-before.json) and
  [after](consolidation/2026/package-after.json) bind their hashes.
- Before tracked payload: 55,376,984 bytes. The added inventory/golden/proof records
  add approximately 2.7 MiB of audit documentation, not raw biomedical data.
  After tracked payload: 58249543 bytes (823 files).
  Working checkout grew from approximately 369 MB to 372 MB including ignored
  caches; those figures are not package sizes and are not source-only comparisons.

No clear replay bottleneck justified optimization. Large historical JSON and
repeated snapshots are protected records; compressing or replacing them could
break source identity. Audit occurrence records are grouped and compactly stored
to avoid repeatedly duplicating file paths and explanations.

## Closure answers (1–31)

1. Starting SHA: `84ecc56e74747bdee12ecdf15b9a80bc760798f4`.
2. Main at start: `d491ebe47ee0c40dfaa3823a44a9decd1afae29d`.
3. Kept: 779 primary KEEP components plus all retained provenance/history.
4. Generalized: five services, shared canonical JSON, explicit case configuration
   and inference-scoped registry contracts; details above.
5. Archived: 19 logically, zero physically; full list in inventory.
6. Deleted: zero.
7. Deletion safety: not applicable; none was attempted.
8. Generalized ERAP1 configuration: primary/comparison targets, proposal context/design
   and project-target biochemical projection; shared canonical serialization.
9. Legitimate case logic retained: named imports, fixtures, source data and historical replay.
10. Decision rules/semantics: unchanged.
11. Comparability semantics: unchanged; contracts validate curated categories.
12. Evidence/epistemic semantics: unchanged; no promotion to approved evidence.
13. v1: byte-identical canonical snapshot and reproduced input digest.
14. v2: actual-engine offline reproduction passes.
15. Causal diff: reconstructs exactly.
16. DECISION STABLE: reproduces.
17. Maben engagement: still unresolved, compound-specific.
18. Learning state: unchanged; no model trained.
19. Commercial artifacts: not modified; v1 coverage limitations documented.
20. EAST-1: separate frozen branch unchanged; not integrated or rerun.
21. Retrospective temporal boundaries: preserved.
22. Tests: 785 pass, two skip, zero fail; 25 focused new tests pass.
23. mypy: pass, strict, 166 files.
24. Changed-code Ruff: pass; axis/tests CI scope also passes.
25. Package build: wheel/sdist pass and 152 resource identity checks each pass.
26. Offline reproduction: pass, clean installed wheel, network blocked.
27. Golden-master equivalence: pass, zero changed dimensions.
28. Sizes: measured above; frozen resource corpus unchanged, +423-byte profile.
29. Debt: inherited script lint, retained compatibility interfaces, independently
   unreviewed curation; no new runtime or equivalence blocker identified.
30. Independent scientific review: ready to review, not already approved.
31. Main: ready with documented non-blocking debt; PR CI/review still required.

## Bounded promotion plan

Promote the four existing integration commits plus the two consolidation commits
through one reviewable PR into main. Do not merge the separate EAST-1/addendum
branches incidentally. Scientific resource modifications: none except the new
case-configuration sibling. Physical archives/deletions: zero. Runtime changes:
three shared serialization wrappers, explicit case configuration and registered
target projection. Documentation/proof changes are separate from runtime changes.

Exact next action after authorization:

```shell
git push -u origin codex/axis-consolidation-post-erap1-2026
gh pr create --base main --head codex/axis-consolidation-post-erap1-2026 --title "Consolidate AXIS with verified scientific equivalence" --body-file docs/axis-repository-consolidation-2026.md
```

Require candidate GitHub Actions on macOS/Linux/Windows to pass, review the bounded
diff and scientific conditions, then authorize a merge separately and verify
post-merge CI. Keep the original integration and EAST-1 branches. Rebase or new
main updates require rerunning equivalence; never force-push or silently alter rules.

**READY FOR MAIN WITH CONDITIONS — SCIENTIFIC EQUIVALENCE VERIFIED**
