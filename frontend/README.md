# CLINVEIL frontend (research dashboard)

**Status:** placeholder. Architecture and contracts only; no build tooling yet.
**Never on the evaluator path.** The CLI works without this directory.

## Responsibilities

A research-facing dashboard that explains and evidences what a CLINVEIL release did:
counts, quarantine, privacy, utility and linking metrics, and architecture. It reads **only**
release artefacts and aggregate metrics through the local demo API. It never sees raw records or
`RAKSHA_SECRET`.

## Proposed stack **[NEEDS APPROVAL]**

Vite + React + TypeScript, CSS variables from `src/design/tokens.css`, no heavy UI kit. Tests with
Vitest + Testing Library, and axe for accessibility.

```bash
# once approved (frontend team):
npm create vite@latest . -- --template react-ts
npm install
npm run dev
```

## Directory layout

```
src/
  api/types.ts        API types (mirror report.json / records.jsonl), see docs/api-contract
  design/tokens.css   colour, type and spacing tokens (light + slate-navy dark)
  mocks/*.json        fixtures; every one carries "mock": true and its provenance
public/               static assets
tests/                component and accessibility tests
```

## Screens

1. Overview · 2. Dataset ingestion · 3. Processing progress · 4. Sanitisation results ·
5. Privacy metrics · 6. Clinical preservation · 7. Patient linking · 8. Quarantined files ·
9. Before/after (synthetic only, demo flag) · 10. Architecture · 11. Security and limitations

## Design direction

- White and off-white surfaces, deep navy text, blue primary. Teal for safe or success, amber for warning,
  red **only** for real failures or risk. Dark mode uses deep slate/navy, never pure black.
- No neon gradients, no heavy glassmorphism, no "AI dashboard" chrome.
- Dense, legible data tables; every metric shows its unit, its source and its dataset.
- Responsive; keyboard-navigable; WCAG AA contrast; supports Devanagari (Noto Sans Devanagari).

## Data rules (non-negotiable)

- Display **actual backend metrics only**. Mock fixtures (`"mock": true`) must render a visible
  "sample data" badge. Numbers are never invented in components.
- Files are shown by SHA-256 prefix and *output* path, never by original input name.
- No secrets in `VITE_*` variables or anywhere in the bundle.
- Before/after examples come only from synthetic datasets, and only when the API exposes them.

## Expected API integration

See [docs/api-contract/README.md](../docs/api-contract/README.md). Start against `src/mocks/`, then
switch to `http://127.0.0.1:<port>/api/v1` once the demo API exists (Phase 7).
