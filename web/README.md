# AXIS read-first workspace

The TypeScript UI displays the Python service projections. It never queries
DuckDB, classifies evidence, calculates scores or selects strategies.
There are no external fonts, hosted scripts, runtime literature fetches or LLM calls.

## Run locally

Use a separate validation/reference database. From the repository root:

```powershell
.\.venv\Scripts\axis.exe --database .tmp/erap1-reference.duckdb discovery import-erap1
.\.venv\Scripts\axis.exe --database .tmp/erap1-reference.duckdb discovery demo
.\.venv\Scripts\axis.exe --database .tmp/erap1-reference.duckdb serve --port 8765
```

Open <http://127.0.0.1:8765/projects/AXIS-DD-ERAP1-CURATED-001/overview>.
The development fixture is available from Projects; it remains proposal-only.
Alternatively `serve --import-curated` explicitly imports before opening the
read-only connection. Serving alone never imports or migrates a store.

One AXIS process owns a file-backed store at a time. Stop the server before
CLI access to the same database. Lock files persist; do not delete them to
override a live owner. OS locks release when the process exits.

## Frontend checks

Node 22.14 or another Vite-supported version and npm are required for development.
The packaged Python wheel already contains the production assets.

```powershell
cd web
npm ci
npm run typecheck
npm run lint
npm test
npm run build
```

Production assets are emitted into `axis/resources/workspace` for offline serving.
`package-lock.json` pins the build dependency graph.

## Browser acceptance

With the reference server running and Microsoft Edge installed:

```powershell
npm run test:browser
```

These acceptance tests traverse genetics → claim → context → source; independently
classified mechanism edges; all four strategies; question → experiment → conditional
outcomes; and proposal-only development states. They save screenshots in
`docs/screenshots/phase2`. They supplement manual visual review, not replace it.
`AXIS_WORKSPACE_URL` can select another loopback port.

The initial Codex browser preview was blocked by the app's saved-permission
verification failure. Browser acceptance and screenshots must be marked pending
until the browser connection works and the traversal has actually been reviewed.

## Phase 2 hardening

Evidence now supports selecting 2–4 project-member claims and comparing their
original contexts, source IDs, exact reported relations, linked perturbations and
stored assessments. Selection is cleared when changing project. No comparison
verdict or missing-context inference is generated.

The question and strategy pages expose their stored relationship links. Package
review remains pending; independent review artifacts are in `docs/reviews` with
45 blank decisions separated into source extraction, evidence interpretation and
mechanism classification. Completed decisions are returned to project owners,
not automatically ingested by the read-only app.

The browser acceptance specifications now cover 1440px and 1024px layouts,
comparison, focus restoration and all requested scientific routes. Their intended
screenshots are under `docs/screenshots/phase2-hardening`. They remain unexecuted
in Codex while browser permission verification fails. Palette/rendering tests are
supplementary checks and do not establish manual accessibility or visual acceptance.
