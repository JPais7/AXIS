# Phase 3.7 — Retrospective validation and temporal backtesting

Question: with future evidence hidden, does AXIS make scientifically defensible
decisions, and do they remain useful once that evidence is revealed?

```
sealed protocol → window at cutoff T → decision at T (ordinary engine)
→ leakage audit → frozen baselines → reveal → relevance → T→T+1 diff
→ validation matrix (per dimension) → blind human review
```

Retrospective validation cannot establish clinical efficacy or prospective validity.
No AXIS score, probability or ranking of cases exists anywhere.

## Temporal isolation (enforced at the data layer)

* Each source has a **first public accessibility** date (`temporal-availability.json`,
  retrieved from PubMed/RCSB with response checksums). Nominal year is never used: the
  Chen 2016 study is nominally 2016 but was listed 2015-07-02.
* Availability kinds: `established`, `bounded`, `uncertain`, `unknown`. Only the first
  two may enter a window. Undated sources are in **neither** window nor future.
* Windows and futures are **separate frozen files**; the window is partitioned at build
  time and re-verified at run time against the availability table. `run` only loads the
  window; `BenchmarkSet.read_future` is the single door to future evidence and its
  opening is recorded. Tests patch it to fail during `run`.
* Evidence assembly was split into `load_records` (store reads) and a pure
  `assemble_evidence`; the decision engine therefore runs on a supplied window
  (`DecisionService.inputs(records=…)`) without touching the store.
* Checksummed manifest, protocol fingerprint, window/future checksums: any mismatch
  fails closed.
* The decision *template* (explanations, candidate experiments) is frozen text
  authored after the fact. References to records outside the window are removed per
  window (`scrub_template`) and one real hindsight name (DG013A) is redacted by a
  recorded rule. It is audited for future identifiers, **not proven free of hindsight**.

## Leakage audit — “INVALID — TEMPORAL LEAKAGE”

Categories: record after cutoff, unknown/uncertain availability in window, source
missing from the table, template or output naming a future source or record,
future file opened before reveal, baseline not frozen before reveal, protocol/window
checksum mismatch, future record in window. Any finding marks the case `invalid`;
reveal and the matrix are then refused. See `phase37-temporal-leakage-audit.md`.

## Objects

Protocol (sealed, fingerprinted; rules fingerprint and software commit recorded),
snapshot, cutoff run, audits, baselines (internal least-evidence edge; external model
runs imported **before** reveal, all runs kept, stochasticity flagged), reveal,
per-source relevance (`changes_critical_uncertainty`, `changes_other_uncertainty`,
`adds_evidence_to_open_uncertainty`, `addresses_unassessed_edge`,
`adds_to_assessed_edge`, `does_not_test_decision_question`, `non_interpretable`),
conclusion (`supported`, `weakened`, `contradicted`, `ambiguous`,
`future_evidence_did_not_test_the_decision`, `not_interpretable`,
`invalid_due_to_leakage`), eight-dimension matrix, leave-one-source-out, blind packet
(A/B, sealed mapping), append-only human review (AI reviewer names refused), post-
benchmark rule-revision notes. Migration `011_retrospective_validation.sql` is additive;
benchmarks never write to projects, claims or decision states (tested).

## Surfaces

CLI `axis benchmark list | show | snapshot | run | leakage-audit | import-baseline |
reveal | compare | blind-packet | review | unblind | report` (bare `axis benchmark`
keeps its earlier performance-benchmark meaning). Read-only API `/api/benchmarks`,
`/api/benchmarks/{case}[/snapshot|run|audit|baselines|reveal|assessment|reviews]`,
`/api/benchmarks/report`. Workspace page **Retrospective Validation**.

## Benchmarks

* `erap1-axspa` (**development**, real chronology): cutoffs 2011-12-31, 2014-12-31,
  2016-12-31 (identical to any date up to 2019-12-16). ERAP1×axSpA is the data the
  rules were developed on, so these are not independent validation. Selection bias is
  documented in the package.
* `synthetic-generic` (**SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE**): non-ERAP1
  target; positive, negative, ambiguous, irrelevant/non-interpretable and undated cases.
  Cases may exclude sources by design only in synthetic sets.
* No `validation`-kind (independent) benchmark exists yet.

## Results

All three real cases conclude **future evidence did not test the decision**: the
critical uncertainty stated at T never changed status. The naive least-evidence
baseline pointed at what later changed at least as often as AXIS in these cases.
No real case is positive, weakened or contradicted; those outcomes are exercised only
by synthetic fixtures. Product value over a literature-aware LLM baseline is **not
demonstrated** (none was run).

## Limits

Small, developer-selected set; hindsight in template and 2026 AI-assisted curation
of assessments cannot be excluded; “tests” is judged by uncertainty status change,
a coarse yardstick; one reviewer identity is free text.
