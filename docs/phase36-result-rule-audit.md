# Phase 3.6 — result eligibility rule audit

Review policy `decision-review-policy-v1`, fingerprint `c2ed2e59d0bc2e7c`; scenario matching `axis-scenario-match-1`. Pure functions in `axis/experiments/policy.py` (no store, clock, network or randomness). `exploratory` accepts accepted, accepted-with-caveat and *pending* (labelled); `reviewed` accepts only accepted and accepted-with-caveat. Rejected, conflicting and needs-revision are excluded in both. Tests: `tests/test_results_loop.py`.

## RESULT-QC-001

* **Rule:** A technical failure, non-interpretable result or non-interpretable QC assessment is ineligible for biological inference.
* **Rationale:** A failed control is not a biological negative.

## RESULT-REV-001

* **Rule:** A rejected result or interpretation is excluded; a review conflict or needs-revision state is excluded in every mode.
* **Rationale:** Disagreement is never resolved silently.

## RESULT-REV-002

* **Rule:** Pending review is eligible only in exploratory mode and is labelled; reviewed mode requires accepted or accepted-with-caveat.
* **Rationale:** Pending science must not look accepted.

## RESULT-EDGE-001

* **Rule:** An interpretation may update only an evidence edge that the performed experiment declares it measures.
* **Rationale:** No edge promotion through adjacency; no automatic cascade.

## RESULT-CTX-001

* **Rule:** A contribution keeps its scope (compound, perturbagen, target) and its context; it never silently generalizes.
* **Rationale:** Compound 3 evidence is not Compound 2 evidence.

## RESULT-SUP-001

* **Rule:** A superseded or withdrawn result is not eligible for the current decision.
* **Rationale:** History is preserved; the current decision uses the current record.

## RESULT-DEV-001

* **Rule:** A design deviation that limits interpretation makes the contribution eligible only with a caveat; one that invalidates comparison makes it ineligible for that comparison.
* **Rationale:** A modified experiment is not the original design.
