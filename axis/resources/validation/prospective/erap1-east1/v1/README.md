# Prospective Validation Case #001 — EAST-1 / GRWD0715

Scientific cutoff 2026-10-05. Technical freeze: 17:46:36.536094 UTC.
Scientific content is AI-curated and **pending independent review**.

This compact package records a conditional therapeutic hypothesis, not trial
success/failure. Sponsor/conference claims are not adjudicated human results.
GRWD0715 cannot establish engagement for historical Maben chemistry.

`manifest.json` pins the six JSON scientific/protocol/state resources;
`manifest.sha256` pins the manifest. Documentation is not a scientific input.
The state fingerprint is
`382ca252aa26afbb94df16e77a9c88268824191ae430e006027a03311e1f051e`.

Offline replay from the repository:

```sh
PYTHONPATH=. python scripts/freeze_east1.py
```

Default invocation only verifies. `--freeze` refuses to overwrite an existing
freeze, and refuses a different calendar day. Keep this version and its adapter
code intact. Changed rules require explicitly versioned artifacts, not silent
backfilling. Source response hashes establish retrieval provenance, not a claim
that live mutable pages will remain byte-identical. Retained paraphrases and
baseline resource references are the offline evidence inputs.

Future partial reveals use `axis.validation.prospective.reveal`: supply verified
public metadata, actual release date, source class and a frozen discriminator.
Retain each returned object as a new JSON artifact; pass the prior chain on the
next invocation. The helper checks hashes and order, returns a causal diff and a
**proposed case state**, and never writes a database, approves curation or changes
the canonical DecisionState. Human adjudication and explicit separately versioned
import through the existing Experimental Results Loop are required for accepted
scientific updates. No future data or reveal dates have been fabricated.

Long-horizon case, not a commercialization blocker. A separate short-horizon
design-partner experiment is a future external-validation activity, not part of
this implementation. Full-text FOCIS methods, quantitative engagement, EU protocol
body and patient results remain unavailable/unknown at this bounded freeze.
The Recent Evidence Addendum is not on baseline main and is not imported.
