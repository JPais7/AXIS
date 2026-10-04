# Phase 3.7 — Temporal leakage audit

| Vector | Control | Residual risk |
|---|---|---|
| Records after T in the window | build-time partition + run-time recheck of every record's source date | none known |
| Unknown/uncertain dates | excluded from window **and** future | evidence silently dropped (disclosed count) |
| Nominal vs accessible date | first public accessibility used | PubMed listing date bounds, not proves, earliest access |
| Future file read early | single `read_future` door, recorded; tests assert not called in `run` | the audit itself reads future identities to search outputs |
| Template naming future records | `addressed_gap_ids` filtered per window; future ids/tokens scanned | template wording is post-hoc AI text |
| Hindsight names | recorded redaction (DG013A) | other implicit hindsight not detectable |
| Curation timestamps | 2026 `created_at` are curation dates, not availability | AI-assisted curation of assessments saw later literature |
| Project scaffolding (strategy ids) | kept in every window, disclosed | design-time context |
| Baseline after reveal | internal baseline frozen in the run; external import refused after reveal | external baseline provenance is the user's word |
| Tampering | manifest/protocol/window checksums, sealed fingerprint | none known |
| Rule drift | fingerprint recorded; mismatch labelled post-benchmark revision | — |

Any finding → `INVALID — TEMPORAL LEAKAGE`, case status `invalid`, reveal refused.
