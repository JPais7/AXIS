# Frozen ERAP1 reference corpus — 1.0.0

This is a small, AI-assisted primary-source extraction, pending scientific expert
review. It is not comprehensive coverage, a systematic review, a clinical
recommendation or an established therapeutic mechanism.

`manifest.json` has six publications, thirteen atomic source assertions, their
reported contexts and locators, inclusion rationales, limitations, twenty-four
evidence assessment entries and seven directly demonstrated mechanism entries.
`manifest.sha256` freezes the exact manifest bytes. The importer adds separately
labelled AI strategy/experiment proposals and one hypothesized translation edge.

The genetics evidence concerns ankylosing spondylitis. Applicability across the
broader axSpA spectrum is unassessed. Purified-enzyme and viral antigen assays
remain distinct from disease observations. Cell-line changes in HLA surface forms
are not clinical benefit, harm or evidence of a preferred strategy.

Bibliographic/abstract responses were retrieved on 2026-10-03 using the recorded
Europe PMC request URLs. Their response hashes identify metadata retrievals,
not a hash of every publication's full text. Chen 2016 also has a retrieved XML
hash and timestamp. Tran 2016 cell/HLA details were checked against indexed primary
PMC full text; its direct XML retrieval was unavailable. This limitation is
recorded explicitly. No complete papers or abstracts are redistributed here.

Import is explicit and offline (`axis discovery import-erap1`), atomic and
idempotent. The package never rewrites existing AI demo claims. Reusing immutable
IDs for different package content is rejected. Future revisions require a
reviewed package/version and identifier policy; do not edit a published package
in place or silently refresh it at startup.

Assessment roles are curated interpretations, not author-reported clinical
findings. Their provenance identifies the fixed package entries, AI-assisted
curation method and pending expert review. No forced contradicts verdict is
created for different cell contexts, and no strategy is selected.
