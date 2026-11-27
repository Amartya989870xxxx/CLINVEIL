# CLINVEIL frontend: implementation plan (Stage 1)

Status: **proposed**, awaiting design approval of the Overview screen and backend-owner approval of
`docs/api-contract/frontend-v1.md`. Branch: `frontend/editorial-ui` (from `main` at `ac37504`).

## 1. What exists today (inspected 2026-11-27)

| area | state |
|---|---|
| `frontend/` | placeholder only: README, `src/api/types.ts` (v0 draft types), `src/design/tokens.css` (navy/blue v0 palette), two `src/mocks/*.json` fixtures from the **Phase 0** engine (84% leaked; now stale), `tests/README.md`. No package.json, no build tooling, no components. |
| backend | Phases 1-2 implemented: ingestion and validation, common IR, PII detection, sanitisation, export, in-process self-check. Linking returns `None` for every record (Phase 3, not built). Privacy transformations are helpers only; applied today: DOB -> `[DOB]`, FHIR `birthDate` -> year (Phase 4, not built). |
| demo API | **does not exist** (Phase 7 in IMPLEMENTATION_PLAN.md). `docs/api-contract/README.md` is a v0 proposal with open questions. |
| PRD | `SECRET_WARDS_FRONTEND_PRD.md` (provided outside the repo). It specifies a blue brand; the newer brief replaces it with the warm editorial / obsidian-ember palette. **Decision: follow the newer brief; everything else in the PRD stands.** |
| handoff | `docs/PROJECT_HANDOFF.md` did not exist; created on this branch. |

## 2. Stack

Vite + React 18 + TypeScript (strict), as already proposed in `frontend/README.md`. Additions, each for a reason:

| package | why |
|---|---|
| `react-router-dom` | eight routes with real URLs (judge deep links, back button) |
| `@fontsource-variable/geist`, `@fontsource-variable/newsreader`, `@fontsource/ibm-plex-mono`, `@fontsource-variable/noto-sans-devanagari` | fonts bundled locally (SIL OFL 1.1); no network font loading; Devanagari for Hindi examples |
| dev: `vitest`, `@testing-library/react`, `jsdom`, `axe-core` | unit, interaction and automated accessibility checks |

No UI kit, no chart library (charts are a few honest SVG bars), no icon pack (a dozen hand-drawn 1.5 px stroke icons),
no state library, no analytics.

## 3. Information architecture

```
Overview ─► Process Dataset (1 choose · 2 policy · 3 confirm) ─► Processing Run ─► Results
                                                                     │
           Privacy & Quality · Data Preview · Architecture · About & Limitations
```

Sidebar groups: **Workflow** (Overview, Process Dataset, Processing Run, Results) and **Evidence** (Privacy & Quality,
Data Preview, Architecture, About & Limitations). Top bar: page title, data-source badge (Example data / Live
backend), mode switch, theme switch. A "Judge demo" path on the Overview walks Overview -> Process -> Run ->
Results -> Data Preview -> Privacy & Quality -> About in that order with a "next step" link at the end of each page.

## 4. Data modes

* **Demo (fixture) mode, default.** Every value comes from `src/fixtures/*`, each fixture carries
  `source: "example_fixture"` plus provenance (engine commit, dataset, command, date). The UI shows an
  "Example data" badge on every surface that renders fixture values. "Start" in demo mode opens the *recorded* run
  and says so; nothing is processed and no progress is animated.
* **Backend-connected mode.** The same screens call the service layer (`src/services/api`) against
  `VITE_API_BASE` (default `http://127.0.0.1:8765/api/v1`). Until the backend exists, health shows "Backend not
  reachable" and every panel shows an honest empty state. No value from a fixture is ever shown in this mode.

Fixture values were recorded from a real CLINVEIL run (`ac37504`, organiser practice dataset, 2026-11-27):
200 files, 193 sanitised, 7 quarantined, 822 records, 3,350 identifiers, 19 records generalised,
0/3,230 practice PII items visible, 4,855/4,855 medical values kept, 0/4 canaries, CONTRACT OK, 0.89 s, 32 MB.
Linking, pseudonyms and date shifting render as **Not available yet**.

## 5. Honesty rules applied to every screen

* No metric without a source label (dataset, run, date). Missing values read "Not measured yet".
* Unimplemented stages read "Not available yet" and are never drawn as complete.
* No progress percentages, timers or activity animation that the backend does not report.
* "Set aside safely" is primary wording for quarantine; "Quarantined" in technical detail.
* Never "anonymous"; "privacy-protected" / "de-identified", with residual risk stated.
* "No finite test can prove that re-identification is impossible." appears on Privacy & Quality.

## 6. Security

No secret, answer key, attacker fixture or identity mapping in the bundle; fixtures contain aggregates and one
invented synthetic example record. Uploads are inspected **in the browser only** (count, size, type sniffing), require
an explicit synthetic-only confirmation, and are never sent anywhere in demo mode. Errors shown to users are fixed
strings; nothing record-derived is logged to the console. No external requests at runtime (fonts bundled).

## 7. Sequence

1. Stage 1 (this document, contract draft, handoff). 2. Stage 2: tokens, typography, primitives, shell, **Overview
for approval** with screenshots in both themes. 3-4. Remaining screens. 5. Integration once the backend owner
approves the contract. 6. Review: themes, routes, buttons, responsive, axe, build, bundle scan.
