# Independent scientific review pack

External artifact: `AXIS_ERAP1_Independent_Scientific_Review_Pack.pdf`.
Version 1.0, 2026-10-06; seven pages, 12 selected primary-publication chains.
Seven pages were used to preserve readable references rather than compress the pack.

Scientific/runtime state: `d11128538a2723737eced46be73d40cef56f43db`.
Scientific reference: `84ecc56e74747bdee12ecdf15b9a80bc760798f4`.
Consolidation candidate: `0dc0ac13746f2e7107abc128d1471a7a99e3f64e`.
Starting closure commit: `54ea4ef1fe3e53c34a405b9dc98ba41f5a4d6996`.
Source branch: `codex/independent-review-freeze-2026`.
Evidence cutoff: **2026-10-05**. Independent scientific review remains pending.

## Editable source and reproduction

The content and layout source is `generate_review_pack.py`, which reads scientific
inputs from fixed Git objects, not mutable working resources. It requires Python,
ReportLab and pypdf; the generation versions and input SHA-256 values are recorded
in `review-pack-audit.json`. The repository must contain the frozen objects and the
closure commit. The PDF uses deterministic ReportLab serialization.

Run from a checkout containing this source:

```sh
python docs/review/independent-scientific-review/generate_review_pack.py
```

Render with Poppler and manually inspect all seven pages. Only after inspecting the
latest render, use `--visual-qa-pass` to record that manual inspection. The flag is
an explicit operator assertion, not an automated scientific or visual validation.
Generation resets the visual status to pending unless this assertion is supplied.

## QA and scope

The final seven-page render was manually inspected, including the revised outcome
and response tables. No clipped text, table overflow, missing glyphs or accidental
blank pages was observed. Page numbering, footer cutoff/state, readable references
and immutable link annotations were checked. Byte-identical repeated generation
was checked after final content edits.

The audit binds v1/v2, causal diff, comparability, uncertainty, learning, context,
source manifests, current-state documentation and the review handoff. It records
internal statement/row classifications and checks identifiers in extracted PDF text.
The seven repository drill-down links resolve to existing immutable Git objects;
this does not claim fresh HTTP availability or acquire new primary evidence.
Twelve DOI links reproduce recorded provenance. Liddle is identified by its verified
DOI/method locator without inventing a bibliographic title. Tinworth's final title
is recorded, but method access is explicitly limited to the accessible preprint/SI.

The post-generation scientific replay remains the existing semantic gate, not a
new reassessment. No scientific/runtime resource, DecisionState, rule, cutoff,
learning eligibility, commercial artifact or EAST-1 result was changed. Licensed
paper PDFs, raw source downloads and local personal-path provenance are not packaged.

## Handoff

The PDF is a request for scientific criticism, not endorsement. Send it to an
independent domain expert and collect the structured issue responses on page 6.
Do not treat engineering CI or this packaging QA as independent scientific approval.
No automatic merge, push, tag, model training or further development is part of this
artifact commit. The resulting documentation SHA is reported after committing,
outside its own payload, to avoid self-reference.

REVIEW PACK READY WITH CONDITIONS - FROZEN SCIENTIFIC STATE PRESERVED
