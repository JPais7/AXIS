# ERAP1 x axSpA decision package v1

Frozen, checksummed wording for the Phase 3.5 decision engine: one working
hypothesis formulation, four competing explanations and six candidate
experiments with outcome scenarios, effects and conditional consequences.

It contains **no evidence, statuses, uncertainties or recommendation**; those
are derived at build time by `axis.decision.rules` from the Evidence Store.
Everything here is an AI suggestion pending researcher review; no experiment has
been performed. Import requires discovery, protein identity and cellular
packages first:

```sh
axis --database study.duckdb decision import-package --project AXIS-DD-ERAP1-CURATED-001 --protein '<imported protein ID>'
axis --database study.duckdb decision build AXIS-DD-ERAP1-CURATED-001
```
