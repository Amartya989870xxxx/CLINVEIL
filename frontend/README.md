# CLINVEIL frontend

A research and judge interface that explains and evidences what a CLINVEIL release did. **Optional and never on
the evaluator path:** the offline CLI (`python main.py --input … --output …`) does not need this directory.

Status: a standalone **landing page** at `/` (no run data, no controls) and an **eight-screen workspace** from
`/overview` (Overview, Process Dataset, Processing Run, Results, Privacy & Quality, Data
Preview, Architecture, About & Limitations). Connected to the real engine through the optional local demo API
(`backend/scripts/demo_api.py`): allowlisted synthetic datasets or uploaded synthetic files are processed by the real
CLI, and results and downloads come from that run. Plan: `docs/frontend/FRONTEND_PLAN.md`. API:
`docs/api-contract/frontend-v1.md`.

## Run

```bash
cd frontend
npm install          # exact pinned versions; `npm audit` reports 0 vulnerabilities
npm run dev          # http://127.0.0.1:5173
npm test             # 86 tests: contrast, honesty, no fixture leakage, accessibility (axe), wizard, uploads, preview fixture
npm run build        # typecheck + production build into dist/
npm run scan:bundle  # fails on external URLs, secret-like strings, ID-shaped numbers or answer-key references
npm run preview      # serve dist/ on http://127.0.0.1:4173
```

Requires Node 20+. No network access is needed at runtime: fonts are bundled, there is no analytics and no
third-party API.

## Data modes

| mode | where values come from | label shown |
|---|---|---|
| **Example data** (default) | `src/fixtures/recordedPracticeRun.ts`: values recorded from one real CLINVEIL run (`ac37504`, organiser synthetic practice set, 2026-11-27) | "Example data" badge with provenance on every data surface |
| **Local backend** | the local demo API at `VITE_API_BASE` (default `/api/v1`, proxied by Vite; see `.env.example`) | "Live backend"; when unreachable, honest empty/error states and never fixture values |

### Connect to the real engine

```bash
npm run api          # terminal 1: backend/scripts/demo_api.py on http://127.0.0.1:8765 (stdlib Python only)
npm run dev          # terminal 2: the site; /api is proxied to the demo API
```

Then choose **Local backend** in the top bar. Process Dataset lists the allowlisted synthetic datasets the API
finds (the organiser practice set from `organiser-toolkit/dev/input`, plus any generated `stress_*` sets) and also
accepts **your own synthetic files** (`.csv .tsv .tab .txt .json`, plain base names, up to 200 files and 32 MB; sent
only when you press Start). Starting runs the real CLI (`main.py`) in a subprocess. Run, Results, Privacy & Quality, Data Preview and
Overview then show that run's own `report.json`, `logs/detection_summary.json`, the organiser's
`validate_output.py` result and, for the practice set only, the aggregate numbers of `check_dev.py`. The download
is a zip of `sanitized/`, `report.json` and `records.jsonl` only; `report.json` and `records.jsonl` can also be
downloaded on their own.

The API binds to 127.0.0.1, accepts only local Host/Origin headers, takes dataset ids (never paths), generates a
random `RAKSHA_SECRET` per process that is never served, forwards no engine or checker output, runs one job at a
time, writes uploads with exclusive create into a fresh private directory, and deletes uploads and run folders when
they are evicted (five most recent runs kept) or the server stops. `npm run api` uses `python3` from `PATH`
(Python 3.10+); `.venv/bin/python backend/scripts/demo_api.py` works too. It is optional and not on the evaluator path.

## Structure

```
src/
  app/            App.tsx, routes.tsx, providers/ (theme, data mode)
  components/     layout/ (AppShell, PageHeader, BrandMark) · common/ (Button, Icon, Notice, SourceBadge, StatusTag,
                  Segmented) · data/ · diagrams/ (PipelineFlow)
  pages/          Landing (/, outside the app shell) · Overview (/overview) · ProcessDataset · ProcessingRun · Results · PrivacyQuality · DataPreview · Architecture ·
                  About · NotFound (shared styles in pages.module.css)
  content/        plain-language labels for entity types, set-aside reasons, stages and scoring dimensions
  services/       api/ (types for contract v1, fetch client with fixed-text errors) · dataSource.ts (demo | backend)
  fixtures/       recordedPracticeRun.ts (one real practice run), exampleRecord.ts (one synthetic record and the engine's
                  verbatim output), internalRedTeam.ts (aggregate internal test results; no inputs or labels)
  hooks/          useResource (loading/empty/error), useCurrentJob (?job= or latest; polls live runs)
  utils/          format.ts, inspect.ts (in-browser format check of synthetic files; nothing uploaded, names hidden)
  styles/         tokens.css (light "warm editorial", dark "obsidian & ember"), base.css (type, focus, tables)
tests/            contrast.test.ts (WCAG AA token pairs) · honesty.test.tsx (Overview) · pages.test.tsx (every page)
scripts/          scan-bundle.mjs
docs/screenshots/ every page in light and dark at 1440 px; Overview, Run, Results and Preview at 390 px
```

## Judge demo

"Follow the five-minute demo" on the landing page (or "Follow the judge demo" in the workspace) starts a seven-step, about five-minute path (Overview, Process, Run,
Results, Preview, Privacy, About); each page then shows the next step until "Leave demo path".

## Rules

* Never show a number without its source; missing values read "Not measured yet".
* Never show an unimplemented stage as complete (linking: "Not available yet"; protection: "Partly implemented").
* No secrets in `VITE_*`, no raw records, answer keys, attacker data or identity mappings in the bundle.
* Status is always text + icon, never colour alone. Contrast is asserted in tests.

Fonts: see `THIRD_PARTY_FONTS.md` (SIL OFL 1.1).
