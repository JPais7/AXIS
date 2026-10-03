# AXIS — visual validation, 2026-10-03

## Result

PASS WITH MINOR OBSERVATIONS for the manually inspected ERAP1 reference workspace. No blocking visual or interaction failure was observed in the tested flows. This is not scientific acceptance, an independent installation validation, or a claim that all automated browser tests passed.

## Environment and scope

- macOS; Codex in-app browser.
- Commit: `7f9e0a97cd5e54e53b865f0992261dd8d63dfaff`.
- Branch: `codex/phase2-transfer`.
- Separate checkout: `/Users/joaopais7/Documents/AXIS-visual-validation`; original AXIS folder preserved.
- Local server: `http://127.0.0.1:8765`.
- Local validation database: `.tmp/visual-validation.duckdb`, populated with the curated ERAP1 import and discovery demo.
- Browser viewport overrides: 1440 × 1000 and 1024 × 1000.
- Method: browser navigation, DOM inspection, screenshots visually inspected in-session, and selected keyboard interactions. Screenshot files were not archived separately.

## Checks performed

| Area | Observed result |
| --- | --- |
| Overview | Readable matrix and project context; responsive layout; evidence-domain navigation works. |
| Evidence | Filtering works; atomic claims retain source and context; claim details open. |
| Comparison | C08, C12 and C13 display side by side with their distinct experimental contexts; no automatic contradiction verdict. |
| Sources | Source detail exposes derived claims, provenance and project link; six publications remain distinct from the AI provenance record. |
| Mechanism | Eight edges displayed; demonstrated and hypothesized edges visually distinct; hypothesis details explicitly labelled as AI suggestion, not experimental evidence. |
| Perturbations | Records and context readable, including at 1024 px. |
| Strategies | Four proposals displayed without an automatic ranking; evidence and uncertainty sections visible. |
| Open questions | Linked evidence, perturbations, strategies and candidate experiment accessible. |
| Next experiment | Proposal status, conditional outcomes, interpretations and provenance readable. |
| Keyboard, selected flows | Enter opens comparison; Escape closes details/comparison and restores focus to the opener. One Tab step remained inside the comparison dialog; exhaustive focus-trap testing not performed. |
| Layout | No horizontal document overflow in the measured scientific pages at the tested widths; source page also visually inspected. |
| Browser console | No warning/error entries returned by the final console inspection. |

All eight scientific sections were visually inspected at 1024 px. Most were also inspected at 1440 px; perturbations were checked for overflow at 1440 px and visually inspected at 1024 px.

## Non-blocking observations

1. **Open questions: missing separation before Endpoint.** Linked perturbation summaries concatenate the experimental system with `Endpoint:` (for example, `cellsEndpoint:`). Add spacing or a line break to improve readability. Observed at both widths.
2. **Strategies: excessive vertical length.** Repeated uncertainty/empty-state sections and generous spacing create a long page, particularly at 1024 px. Consider a more compact presentation while retaining explicit missing evidence.

## Limits and outstanding work

- This session did not execute the full Python test suite or automated browser suite; earlier reported test totals are not revalidated here.
- No cross-browser, phone-width, screen-reader, exhaustive keyboard or performance validation was performed.
- External publication links were visible but their remote destinations were not tested.
- Expert scientific review remains pending; visual correctness does not establish source fidelity, causal inference or therapeutic validity.
- The earlier browser-permission blocker is not present in this environment. This report supplements, rather than rewrites, the historical acceptance report.
- No application code changes, commits or pushes were made for this validation.

## Follow-up corrections

After the validation, the user requested corrections. CSS now separates compact-card context lines and reduces spacing within strategy cards without hiding scientific information. The distributed frontend assets were rebuilt. Type checking, lint, all nine frontend component tests and the production build passed. A CSS regression contract was added; it is not a browser layout test.

Post-change visual confirmation remains pending: browser navigation/debugger synchronization timed out during the follow-up check. The original visual pass above applies to the inspected base commit, not a visually verified patched build. The user subsequently authorized publishing these changes to GitHub.
