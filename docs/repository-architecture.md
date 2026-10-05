# Repository architecture and immutable boundaries

Generic domain/storage contracts sit in `axis/domain` and `axis/storage`.
Reusable scientific rules sit in `axis/decision`, `axis/pharmacology/selectivity.py`,
`axis/cellular/rules.py`, `axis/learning` and the analysis/validation modules.
CLI and workspace projections are interfaces, not additional scientific authority.

`axis/serialization.py` shares the existing canonical JSON contract; old public
helpers still exist and produce exactly the same digest bytes. No fingerprint,
precision, Unicode behavior, threshold or unknown-value fallback was changed.

`axis/case_config.py` reads named case profiles from `axis/resources/cases`.
The ERAP1 profile contains the pre-existing target/countertarget list and proposal
wording. It is configuration, not a new evidence source or reviewed hypothesis.
The biochemical cellular overview uses the project's registered target rather
than a hard-coded gene. Historical reference importers still reject the wrong
protein/species: accepting arbitrary targets into an ERAP1 source package would
be a scientific error, not successful generalization.

`axis/assay_context.py` defines reusable contracts for **curated** qualitative
comparability and inference-scoped uncertainty. Missing fields do not automatically
become global blockers. A global blocker needs an explicit decision dependency;
local limitations still retain their missing fields, affected inference and reason.
The audit consumes the existing registry through these contracts. They do not
replace source adjudication or calculate quantitative selectivity. COMPARABLE,
PARTIALLY_COMPARABLE, NOT_COMPARABLE and INSUFFICIENT_METHOD_INFORMATION remain
qualitative, reviewable categories. No gene name supplies an implicit rule.

## Frozen case compatibility

Case packages live under `axis/resources`, with immutable versions, checksums and
source locators. The four ERAP1 evidence-integration packages stay byte-identical.
Historical replay scripts, including the source-hash-bound BRADSHAW script, are
versioned compatibility interfaces. Replacing them in place would invalidate the
reference manifest; generic contracts may validate their outputs without rewriting
their scientific history. The current v2 state does not overwrite commercial v1.

## Onboarding another target

Register its actual gene/protein/project linkage and source-backed assay contexts.
Create a separate named profile and versioned source package; never copy ERAP1
allotypes, substrates, countertargets or hypotheses as defaults. Provide scoped
limitations and source-linked curated comparison categories. Use existing generic
decision/learning inputs and synthetic regression tests. A new source importer may
be necessary: the legacy ERAP1 importer is explicitly reference-package-specific.
New target claims and new admission rules require separate scientific review.
