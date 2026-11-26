# CLINVEIL: Project handoff (source of truth for all AI coding agents)

| | |
|---|---|
| Product | **CLINVEIL**: "Privacy infrastructure for trusted medical data sharing" |
| Team | **APEX** (the name registered in `raksha.toml`; the product name stays CLINVEIL) |
| Event | Yugaantar DevForge · Track 3 · **Secret Wards** |
| Repository | https://github.com/Amartya989870xxxx/CLINVEIL (public) |
| Official toolkit | https://github.com/Reinforce-SST/Secret-Wards-ToolKit (cloned read-only at `organiser-toolkit/`, git-ignored, commit `6c0a85a`) |
| Last full verification of this document | 2026-11-27, against Phase 3 identity resolution & cryptographic pseudonymisation on branch `phase-3-identity-resolution` (see §2 and the changelog) |

> **How to read this file.** Every statement is marked by where it comes from: *verified* (a command was run
> or a file was read while writing this), *documented* (taken from a repository document, not re-run), or
> *planned* (not implemented). **Planned work is never described as done.** If you find a mismatch with the
> repository, the repository wins: fix this file (§7).

---

## 0. Instructions for Every AI Coding Agent

These apply to Claude Opus, Claude Sonnet, Gemini and any other agent. They override convenience.

1. **Read this whole document before starting work.**
2. **Read the relevant architecture and decision documents** for the area you touch:
   `docs/architecture/SYSTEM_ARCHITECTURE.md`, `docs/architecture/IMPLEMENTATION_PLAN.md`,
   `docs/decisions/TECHNICAL_DECISIONS.md` (D1–D28), `docs/security/THREAT_MODEL.md`, and the phase evidence
   in `docs/evaluation/`.
3. **Inspect Git first:** `git branch --show-current`, `git status --short`, `git log --oneline -5`.
4. **Never assume the current branch or commit.** §2 may be stale; check.
5. **Never modify `organiser-toolkit/`** (no edits, commits, pulls with local changes, or "fixes" to its scripts).
6. **Never copy answer keys or attacker fixtures into production code, tests, docs or fixtures.** That means
   anything from `organiser-toolkit/dev/truth/`, `dev/attacker/`, practice patient/relative/canary names,
   practice IDs and phone numbers, or practice file lines. Use invented identities. Coincidental overlap with
   practice values (even common names) must be replaced by invented ones (this was done in Phase 2.1).
7. **Never push, merge, force-push or rewrite published history without explicit approval from the user.**
   Commits `59c0ea8` and `7934185` are published: never rewrite them.
8. **Work only on the branch designated for your task.** Do not switch to or commit on `main`.
9. **Add a regression test for every confirmed bug**, reproduced *before* the fix.
10. **Run the official validation** (§5.4) after any change that can affect output.
11. **Update this handoff after meaningful work** (protocol in §9).
12. **Record commit hashes and actual test results.** Copy numbers from real command output only.
13. **Disclose unresolved issues and incomplete work** in the report and here. Do not mark an issue solved
    unless a test or measurement shows it.
14. **Never invent test results or claim verification without running the check.** If you could not run it,
    say so.

Also standing user rules (from the project's history): no LLM or hosted API in the engine, no network at
runtime, no committed secrets, never print PII/secret in logs or errors, keep the team name APEX and the
no-licence/third-party-notice arrangements (§8).

---

## 1. What CLINVEIL is

### 1.1 The problem
Hospitals hold messy, multilingual (English, Devanagari Hindi, romanised Hindi "Hinglish") exports: CSV/TSV
registries, JSON visit logs, FHIR R4 bundles, free-text notes, WhatsApp forwards, base64 "scanned" forms,
filenames and metadata that embed patient identity. Researchers need the clinical content; they must not get
the identities. Naive redaction either leaks (names in a filename, a base64 attachment, a Devanagari note) or
destroys clinical meaning (redacting a clinician's name, a "C/O fever" complaint, or a "Dolo 650 1-0-1" dose).

### 1.2 What the product is meant to do
An **offline, CPU-only, deterministic, LLM-free** de-identification engine that:
1. removes personal data from every channel (content, headers, keys, metadata, base64, filenames);
2. keeps clinical values intact (drugs, doses, vitals, labs, diagnoses, wards, doctors);
3. gives each real patient one stable keyed pseudonym across files and scripts (**not implemented yet**, §3);
4. generalises quasi-identifiers (dates, ages, locations) so a register-holding attacker cannot re-identify
   (**not implemented yet**, §3).

### 1.3 Users
- **Primary (competition):** the Secret Wards evaluator, which runs `python main.py --input … --output …`.
- **Intended (product):** research teams receiving a hospital data release; hospital data officers producing it.
- **Optional, planned:** a judge/researcher-facing local dashboard (Phase 7, not implemented).

### 1.4 Product workflow (as implemented today)
```
input tree ─► discover (sorted, lstat-based) ─► PASS 1: detect+build IR+seed run-local value index
           ─► PASS 2: detect format ─► build IR ─► analyse (semantics, detectors, propagation, resolution)
              ─► rename PII paths ─► sanitise (placeholders, numbers→0, FHIR birthDate→year, payload re-encode)
              ─► render ─► write sanitized/ + report.json + records.jsonl + logs/detection_summary.json
              ─► self-check the release (false-success guard) ─► exit 0
```
Not in the workflow yet: patient linking, per-patient date shifting, age banding, location generalisation,
k-anonymity suppression (Phases 3–4).

> **Never describe CLINVEIL as guaranteeing anonymity.** Release privacy is measured only against practice
> data and our own synthetic tests. No finite test proves anonymity. (The README's tagline "resists
> re-identification" is a *goal*; Phase 4 is where it would be earned and no adversarial score has been
> measured.)

---

## 2. Current Git state (verified 2026-11-27)

| Item | Value (verified with `git`) |
|---|---|
| Active branch | `phase-3-identity-resolution` |
| HEAD | the Phase 3 identity resolution commit (its hash is recorded in the next update, because a commit cannot contain its own hash) |
| Before it | `9205b5a` Merge PR #3 (`phase-2.1-remediation`, incl. `a74851c` Python 3.10 CI fix) |
| `main` / `origin/main` | both `9205b5a` "Merge pull request #3 from …/phase-2.1-remediation" (Phase 0 + 1 + 2 + 2.1) |
| Phase 3 pushed / merged? | **No.** Exists only as a local commit on `phase-3-identity-resolution`; not pushed or merged. |
| Remote | `origin` → https://github.com/Amartya989870xxxx/CLINVEIL.git |
| Untracked (intentional) | `docs/research/GEMINI_PHASE2_CODE_SECURITY_AUDIT.md` |
| Toolkit | `organiser-toolkit/` at `6c0a85a`, clean, git-ignored |

Commit history (verified):

| Commit | Meaning |
|---|---|
| `59c0ea8` | Phase 0 bootstrap (**published**; never rewrite) |
| `7934185` | Licensing correction: no project licence, third-party notices, team APEX (**published**) |
| `d2c4b31` → `643c95f` | Phase 1 ingestion; merged via PR #1 |
| `53ec8ff` → `ac37504` | Phase 2 detection; merged via PR #2 |
| `683074f` → `a74851c` → `9205b5a` | Phase 2.1 audit remediation, F1–F4, and Python 3.10 CI fix; merged via PR #3 |
| (next commit) | Phase 3: cross-hospital patient identity resolution and cryptographic pseudonymisation (local) |

**The Gemini audit report is deliberately untracked.** It quotes practice canary and patient names. Never
commit it; if it must be versioned, commit a *redacted* copy. Its findings and our responses are in
`docs/evaluation/PHASE2_REMEDIATION.md`.

---

## 3. Phase-by-phase record

Legend: ✅ completed and verified · 🟡 partial · 📋 planned (not implemented) · ⏸ deferred.

| Phase | Status | Latest commit |
|---|---|---|
| 0 Foundation | ✅ | `59c0ea8` (+ `7934185` licensing) |
| 1 Ingestion + common IR | ✅ | `d2c4b31` (merged `643c95f`) |
| 2 Contextual PII detection | ✅ (with known limits, §4) | `53ec8ff` (merged `ac37504`) |
| 2.1 Audit remediation | ✅ merged | `9205b5a` (PR #3) |
| 3 Identity resolution | ✅ locally, **unpushed/unmerged** | local on `phase-3-identity-resolution` |
| 4 Privacy transformations | 📋 not started (only `age_band()` helper exists) | n/a |
| 5 Secure export / final validation | 🟡 partial (see below) | n/a |
| 6 Adversarial testing / optimisation | 🟡 partial (dev evaluators and generators exist) | n/a |
| 7 Frontend + demo | 📋 placeholder only | n/a |

Backend paths are under `backend/src/clinveil/`. Package size at time of writing: about 5.7k lines of Python.

### Phase 0: Repository foundation ✅
- **Objective:** a contract-correct repo around the official starter, with hardening.
- **Completed:** toolkit cloned separately; starter split into modules; fail-closed secret (exit 2); input/output
  overlap guard; PII-free reason codes; pre-exit release self-check; CI (`.github/workflows/ci.yml`); ruff; tests.
  Licensing correction: removed a project-wide MIT licence; third-party MIT portions kept (§8).
- **Decisions:** D1–D12 (`docs/decisions/TECHNICAL_DECISIONS.md`): evaluator entry at repo root and code under
  `backend/`; stdlib-only runtime; fail closed without `RAKSHA_SECRET`; allowlisted reason codes; typed `Finding`;
  conservative linking with abstention; no intermediate files; frontend/API optional; no project licence; team APEX.
- **Modules:** `main.py`, `raksha.toml`, `requirements.txt` (no runtime dependencies), `config/policy.yaml`,
  `cli.py`, `pipeline.py`, `config/policy.py`, `security/` (`secrets.py`, `errors.py`, `paths.py`),
  `privacy/pseudonym.py`, `export/release.py`, `validation/contract.py`, `utils/resources.py`.
- **Tests (documented, `docs/evaluation/BASELINE.md`):** 65 passed, 7 xfailed at that commit; baseline leak was
  about 84% (starter regexes only). Not re-run.
- **Remaining:** none for the phase itself.

### Phase 1: Reliable ingestion and common IR ✅
- **Objective:** parse every input safely into one representation, quarantine what cannot be handled.
- **Completed:** content-based format detection (signatures, JSON-first, markup, delimiter sniffing; extension is
  only evidence); validated decoding (BOM/UTF-16/UTF-8/cp1252 with mojibake and binary checks); bounded JSON
  (depth/size/node limits); CSV/TSV/JSON/FHIR/text IR with field kinds, channels and addresses; FHIR enumeration
  (entries, references, roles); base64 payload discovery.
- **Decisions:** D13–D16 (typed IR; content beats extension; stable limits and reason codes; base64 handling).
- **Modules:** `ingestion/{detect,decoding,plausibility,signatures,limits,discovery}.py`,
  `parsing/{builder,csv_format,json_format,json_safety,fhir,attachments}.py`, `models/{document,channels,findings,records}.py`.
- **Tests (documented, `PHASE1_INGESTION.md`):** 164 passed, 7 xfailed; practice run 0.31 s / 27 MB (200 files),
  2.76 s / 34 MB (2,000 files). Not re-run.
- **Remaining:** XML, PDF and images as whole files are quarantined, not parsed (by design so far).

### Phase 2: Multilingual contextual PII detection ✅ (limits in §4)
- **Objective:** find personal data in Latin, Devanagari and Hinglish text and structure without removing
  clinical meaning.
- **Completed:** semantic field classification (headers, key paths, FHIR roles); validated Indian identifiers
  (phone, Aadhaar with Verhoeff, masked Aadhaar, ABHA, PAN, e-mail, insurance, labelled MRN); contextual names
  (labels, relation markers `S/o` `D/o` `W/o` `C/O`, honorifics, kinship, titles, "by" cues, timelines,
  WhatsApp senders, possessives, Muslim name prefixes, small gazetteer); address components; clinical/doctor
  protection ("keep spans"); run-wide Sensitive Value Index (two passes); document-local propagation;
  deterministic resolution (threshold 0.70); typed offset-only `Finding`s; filename/header/key/metadata/base64
  channels; transliteration name keys.
- **Decisions:** D17–D22 (deterministic layered detection, no statistical NER; two-pass run-local index;
  offsets-only findings and placeholders `[NAME] [RELATIVE] [PHONE] [MRN] …`; DOB interim treatment: `[DOB]`,
  FHIR `birthDate` → year; schema labels never redacted, values in labels are; starter regex removed).
- **Modules:** `detection/{engine,semantics,identifiers,names,addresses,clinical,value_index,resolve,text,translit,lexicon}.py`,
  `sanitization/{processors,render}.py`.
- **Tests:** the Phase 2 commit's own count was not recorded in a repository document (not invented here).
- **Documented practice measurements (`PHASE2_DETECTION.md`):** `check_dev.py` 0/3230 visible, 0/4 canaries,
  4855/4855 medical values kept; 1.63 s / 31 MB (200 files), 14.6 s / 39 MB (2,000 files). The doc originally
  said "96 candidates protected"; the committed code gives **55** and the doc was corrected in Phase 2.1.
- **Remaining:** see §4.

### Phase 2.1: Independent audit remediation ✅ (local, unpushed)
- **Objective:** reproduce and fix every finding of the independent Gemini audit of Phase 2, then verify the
  remediation itself (`docs/evaluation/PHASE2_REMEDIATION.md` is the per-finding mapping).
- **Completed in `683074f`:** non-Patient FHIR text detected; preserved fields *guarded* instead of skipped (D23);
  label classification by purity with restricted fuzzy matching (D24); decoded views for XHTML/HTML-entities/%-escapes
  (D25); every Unicode digit script; URL-safe and short base64; names before relationship markers; labelled ABHA and
  STD landlines; doctor-protection ordering; C/O complaint vocabulary; Devanagari clinical stop words; FHIR
  `id`/`fullUrl`/`reference` rewriting (`rid-N`); honest report counts; run-scoped cache clearing
  (`detection/caches.py`); near-linear resolver; `name_key_strict` for Phase 3 (D27); rewritten `scripts/dev_eval.py`;
  independent adversarial generator (`tests/generalization/adversarial.py`).
- **Completed in `5a242ab` (final verification):** escaping symlink targets are **never opened** (S1, D28);
  array elements keep their slot when a binary payload is withheld, and `hash`/`size` are dropped with the data (S2);
  `Test Name:`-style labels no longer seed clinical values (S3); weakly classified fields no longer seed the index (S4);
  FIFOs/devices reported unopened (S5); one practice resource UUID replaced in tests.
- **New modules:** `detection/views.py`, `detection/caches.py`; discovery rewritten in `ingestion/discovery.py`.
- **Tests (actually run 2026-11-26 while writing this):** `pytest` **711 passed, 1 xfailed**; `ruff check` clean;
  `ruff format --check` clean (88 files). The single xfail is `test_different_secret_changes_output` (Phase 3/4).
- **Measured at `5a242ab` (earlier in the same session, not re-run for this document):** practice output
  byte-identical to Phase 2; `check_dev.py` 0/3230, 0/4 canaries, 4855/4855; `validate_output.py` CONTRACT OK;
  `check_submission.py --run` READY with one warning (different secret → identical output); 200 files 2.1 s / 32 MB;
  2,000 files 20.2 s / 39 MB; adversarial suite 175/175 (Phase 2 code: 50/175).
- **Final review fixes F1–F4 (commit after `e6021fa`):** an independent final review approved Phase 2.1 with
  minor changes and reported four findings. **The review file was not in the repository**
  (`docs/research/` holds only the original audit); the findings were taken from the user's task description and
  each was reproduced on `e6021fa` first (`regression/test_phase21_final_review.py`: 15 failed / 15 passed before,
  30 passed after):
  - F1: no empty `input_sha256` (internal links to FIFOs flagged in discovery; `unread_id` on failed reads);
  - F2: `hash`/`size` removed whenever a payload is rewritten or withheld, with or without `contentType`; short
    payloads under a binary declaration withheld;
  - F3: %-escapes decoded in spaced text when there is evidence of an escape; `\uXXXX` in plain text decoded
    (exact span mapping);
  - F4: zero-valued JSON numbers are neither replaced nor counted.

  Details: `docs/evaluation/PHASE2_REMEDIATION.md` §8.
- **Tests after F1–F4 (run 2026-11-26):** `pytest` **741 passed, 1 xfailed**; ruff check/format exit 0.
  `official_checks.sh --submit`, `validate_output.py`, `check_dev.py` and `check_submission.py --run` all exit 0:
  CONTRACT OK, 0/3230, 0/4 canaries, 4855/4855, READY with the known E5 warning. Practice output is still
  byte-identical to Phase 2; same-secret determinism and input immutability hold; side-channel scan clean.
  Performance: 200 files 2.35 s / 32 MB; 2,000 files 22.2 s / 40 MB; back-to-back timing equal to `e6021fa`
  within noise.
- **Python 3.10 CI fix (commit after `fab12fb`):** GitHub Actions PR #3 failed on Python 3.10 (`test_dev_eval_script_runs`)
  while passing on Python 3.12 because `organiser-toolkit/dev/input/misc/deep_export.json` has 1,500 levels of JSON
  nesting; CPython 3.10's `json.loads()` raises `RecursionError` at 1,000 frames, whereas `backend/scripts/dev_eval.py`
  (`Parsed.__init__`) only suppressed `ValueError`. Fixed by catching `(ValueError, RecursionError)` in `dev_eval.py`,
  adding an optional backward-compatible `--input` flag and clean PII-free error handling for missing/malformed truth or
  report JSON, updating `test_dev_eval_script_runs` to surface stdout/stderr on failure, and adding 4 isolated synthetic
  tests in `tests/unit/test_dev_eval.py`. Details: `docs/evaluation/PHASE2_REMEDIATION.md` §9.
- **Tests after Python 3.10 CI fix (run 2026-11-27):** `pytest` **745 passed, 1 xfailed** on Python 3.10 (`uv`, 18.61 s),
  Python 3.12 (`uv`, 16.72 s), and local `.venv` Python 3.13 (19.89 s); `ruff check` and `ruff format --check` exit 0
  (91 files). On Python 3.10: `main.py`, `validate_output.py` (CONTRACT OK), `check_dev.py` (0/3230, 0/4 canaries,
  4855/4855), `dev_eval.py` (0.0/3226, 0/8 canaries, 98.8% probes, 99.8% retention), and same-secret determinism all
  exit 0; `check_submission.py --repo . --run` exits 0 (READY, known E5 warning).
- **Remaining:** push CI fix commit and merge PR #3 (user decision); open issues in §4.

### Phase 3: Patient identity resolution ✅ (local, unpushed)
- **Objective:** link records belonging to the same real-world patient across hospitals, scripts, and formats without
  false merges, and emit one stable keyed HMAC-SHA256 pseudonym inside each exported record and `records.jsonl`.
- **Completed:**
  - Modular `backend/src/clinveil/linking/` package: `models.py`, `normalize.py`, `extract.py`, `matcher.py`,
    `cluster.py`, `pseudonyms.py`, `linker.py` (all memory-only, redacting `repr`, unpicklable, caches cleared in `finally`).
  - Cross-script strict name normalisation (`Kiran != Karan`, `Sita != Satya`, `Alok != Alka`, schwa-only tolerance,
    abbreviations, order inversion, split `FirstName`/`LastName` & FHIR `given`/`family` assembly) and cross-script
    village/DOB/age/gender extraction.
  - Tiered evidence & hard conflict vetoes: Verhoeff-valid Aadhaar (never masked), 14-digit ABHA, hospital-namespaced
    MRNs (`Hospital-A / MRN-12345` never matches `Hospital-B / MRN-12345`), explicit conflict vetoes (disjoint global IDs,
    gender, DOB, age > 3, incompatible full names, relative/village/district homonym guards).
  - Bounded blocking (`MAX_ID_BLOCK=128`, `MAX_NAME_BLOCK=64`) and 3-stage conflict-aware conservative clustering
    (Stage A global IDs, Stage B hospital-scoped MRNs, Stage C1 corroborated full names with ambiguity check, Stage C2
    unique fragmented attachments; never naive transitive connected components).
  - Domain-separated versioned HMAC-SHA256 pseudonyms (`psn|v1|<canonical_cluster_key>`) derived from traversal-order-
    independent sorted evidence, with deterministic collision counter re-derivation (D8).
  - Schema-preserving in-record pseudonym placement (CSV/TSV/JSON/FHIR/text), single-patient JSON report locator fix
    (`parsing/json_format.py`), and pre-exit pseudonym consistency self-checks (`validation/contract.py`).
  - Removed the Phase 3/4 `xfail` on `test_different_secret_changes_output`.
- **Tests & validation (run 2026-11-27):** `ruff check` / `ruff format --check` exit 0 (99 files); `pytest`
  **766 passed, 0 failed, 0 xfailed** on Python 3.10 (20.04 s), Python 3.12 (18.03 s), and Python 3.13 (20.31 s);
  `validate_output.py` `CONTRACT OK`; `check_dev.py` `0/3230` leaked, `0/4` canaries, `4855/4855` medical values,
  **linking precision 1.00, recall 0.99, F0.5 1.00, 0 wrong merges** (B-cubed F1 `0.9936`, language trap `96.3%`,
  fragmented trap `100%`, homonym separation `2/2`, pseudonym consistency `772/772 = 100%`); `check_submission.py --run`
  **`READY TO SUBMIT` with 0 warnings**; 1× runtime 2.1 s / 37.9 MB RSS; 10× (2,000 files) 22.4 s / 113.7 MB RSS.
- **Details:** `docs/architecture/PHASE3_IDENTITY_RESOLUTION.md`, `docs/evaluation/PHASE3_IDENTITY_RESOLUTION.md`.
- **Remaining:** push/merge decision belongs to the user; Phase 4 privacy transformations (date shifting, age bands,
  generalisation, k-anonymity).

### Phase 4: Privacy transformations 📋 not started
- **Exists today:** `privacy/generalize.py::age_band()` only; `config/policy.yaml` carries `age_band_years`,
  `date_shift_max_days`, `min_group_size`.
- **Planned (not done):** per-patient keyed date shift (intervals and length-of-stay preserved), truthful age bands,
  village→tehsil/district, PIN→3-digit prefix, k-anonymity with rare-cell suppression only. DOB is currently `[DOB]`
  (FHIR `birthDate` → year only).

### Phase 5: Secure export and final validation 🟡 partial
- **Done:** report/records writers, filename renaming declared by SHA-256, honest counts, pre-exit contract check,
  FHIR reference rewriting, binary-attachment withholding, side-channel scans in tests.
- **Planned:** FHIR R4 structural validator of our own (organiser's FHIR scorer is sealed), final side-channel
  self-scan against the release's own known-PII set, `entities` counts review.

### Phase 6: Adversarial testing and optimisation 🟡 partial
- **Done:** `scripts/dev_eval.py` (SCORING.md-style record-level leak, probes, retention); `tests/generalization/{synth,adversarial}.py`;
  scaling measurements.
- **Planned:** `metrics/` package (currently an empty `__init__.py`), linking P/R/F0.5, uniqueness estimate,
  mutated-practice-copy harness, 10× scaling-exponent tracking.

### Phase 7: Frontend integration and demonstration 📋 placeholder only
- **Exists:** `frontend/` contains READMEs, `src/api/types.ts`, `src/design/tokens.css`, two mock JSON fixtures
  (each flagged `"mock": true`) and empty `public/`/`tests/`. **No build tooling, no app.** Proposed stack
  (Vite + React + TypeScript) is **[NEEDS APPROVAL]**. `docs/api-contract/README.md` describes a *proposed*
  read-only local API (localhost, no secret, synthetic-only examples); nothing is implemented.
- **Rule:** frontend and API are never on the evaluator path and never in `requirements.txt`.

---

## 4. Outstanding issues (none silently solved)

| # | Issue | Status / detail |
|---|---|---|
| O1 | **External symlink vs official validator** | Escaping symlink targets are never opened; the path is exported as an empty placeholder declared `suppressed` under a synthetic id (D28). `validate_output.py` accepts this with one WARN. **Conflict:** if the link's *own filename* contains PII, the placeholder is renamed and cannot be declared without the target's hash, so the validator reports one "neither exported nor declared" ERROR. Privacy + no-read were chosen over that error. Separately, the official validator itself reads link targets (blocks on a FIFO, crashes on a dangling link). **User decision pending** if the trade-off should change. |
| O2 | **Hard links and filesystem races** | Hard links to files outside the root look like regular files and are read. Directory components swapped for symlinks *during* a run are not defended (only the final component is, via `O_NOFOLLOW`). Assumes the evaluator's read-only input copy. |
| O3 | **Context-free patient names** | A name with no label, honorific, marker, phone, timeline or gazetteer pair that never appears in a structured field can be missed. Documented ablation: without cross-file propagation the practice leak was 1.3% (Phase 2). |
| O4 | **Hex escapes in plain text** | Still not decoded by the engine (the official scorer decodes them); ambiguous with hashes and IDs. **Partly resolved (F3):** `\uXXXX` in plain text and %-escapes in spaced text are now decoded; JSON `\u` escapes are handled by the JSON parser; HTML entities and base64 *are* decoded. |
| O5 | **Nested base64** | Base64 inside a decoded payload is not scanned. |
| O6 | **WhatsApp sender role** | Senders are always typed RELATIVE_NAME. Redaction is unaffected; the typed placeholder/entity may be wrong. |
| O7 | **Small gazetteer** | 198 given names and 47 surnames after removing every practice-overlapping token (contamination control). Weak evidence by design (pair 0.75; single token 0.60, never redacted). |
| O8 | **Different-secret output** | **Resolved for pseudonyms in Phase 3.** Different `RAKSHA_SECRET` values now produce distinct pseudonyms in `sanitized/` and `records.jsonl`; `test_different_secret_changes_output` passes (xfail removed) and `check_submission.py --run` reports 0 warnings. Date shifting remains Phase 4. |
| O9 | **Coarse name key collisions** | `name_key` merges e.g. Kiran/Karan by design (recall for redaction). Must not be used for linking (use `name_key_strict`). |
| O10 | **Evidence limits** | Practice data contains none of the patterns fixed in Phase 2.1 (its output is byte-identical to Phase 2); the new protections are evidenced by team-written tests and a team-written generator, not by the sealed dataset. No official score has ever been computed. |
| O11 | **No Project Brief PDF in the repo** | `check_submission.py` reports finding one only because a practice input contains a PDF. The 2-page brief (planned at `docs/brief/`, which does not exist yet) does not exist. |
| O12 | **Phase 3 not pushed/merged** | Phase 2.1 merged in `9205b5a` (PR #3); Phase 3 committed locally on `phase-3-identity-resolution`, awaiting user push/merge. |
| O13 | **No date shifting or quasi-identifier generalisation** | Phase 4 privacy transformations (per-patient date shift, age bands, location generalisation, k-anonymity) remain to be implemented. |

Other known behaviours: DOB is replaced by `[DOB]`; binary attachments are withheld (JSON member removed, or
`[ATTACHMENT-WITHHELD]`), invalid declared base64 payloads still quarantine the file; XML/PDF/images quarantined.

---

## 5. Competition and security requirements (prominent)

### 5.1 Non-negotiable constraints (documented in `organiser-toolkit/README.md`, `organiser-toolkit/docs/SPEC.md`, `organiser-toolkit/docs/SANDBOX.md`)
- **Offline:** no network during `run` (empty network namespace). No runtime internet, no hosted APIs.
- **CPU-only:** no GPU. **2 CPUs**, **4,096 MB** peak RSS for the whole process tree, **15-minute** wall-clock limit.
- **No LLMs, no generative models, no pretrained transformers above 50M parameters.** `check_submission.py`
  rejects hosted-AI packages in `requirements.txt`. CLINVEIL uses **no models at all** and no runtime dependencies.
- **Contract:** `raksha.toml` at repo root with `run = "python main.py --input {input} --output {output}"`;
  outputs `sanitized/`, `report.json` (schema `raksha-report/1`, every input listed by SHA-256, honest counts),
  `records.jsonl`; optional `logs/` (scanned for PII) and `quarantine/` (not scanned).
- **Environment checks by the evaluator:** the input is re-hashed after the run (modification is penalised);
  `TMPDIR`/`HOME` are scanned for PII.

### 5.2 Official scoring categories (documented, `organiser-toolkit/docs/SCORING.md` and `scoring.toml`)
| Category | Weight |
|---|---:|
| Multilingual PII detection and contextual intelligence (F2 of contextual precision and recall) | 20% |
| Cross-document identity resolution | 15% |
| Adversarial privacy and re-identification resistance, **coupled to utility**: `(1 − attack risk) × min(1, utility/0.40)` | 25% |
| Clinical utility preservation (probes 0.35, temporal 0.20, generalisation 0.10, statistics 0.15, token retention 0.10, record retention 0.10) | 20% |
| Data integrity and secure export | 10% |
| CPU efficiency and reliability | 10% |
Critical penalties apply (e.g. canaries −3 each, raw copy of a broken file −5, input modification −5; per `check_dev.py` text).
Leaks are scored by identifying name tokens, digit cores across separators, exact text and DOB in any format,
after the scorer decodes base64/hex/`\u`/HTML-entities/%-encoding and folds Indic digits and homoglyphs.

### 5.3 Security requirements the code must keep
1. **No source PII** in logs, reports, stdout/stderr, exception messages, `repr`s, file names in output, or caches.
   Reasons are allowlisted codes or exception type names. `Finding` stores offsets only.
2. **Safe file handling:** every read opens the verified real path inside the input root with `O_NOFOLLOW|O_NONBLOCK`
   and requires a regular file; escaping/broken links and FIFOs/devices are never opened; size caps; output paths via `safe_join`.
3. **Fail closed:** missing `RAKSHA_SECRET` → exit 2; any per-file exception → quarantine with a code; nothing is ever
   copied raw; the release is re-verified on disk before exit 0.
4. **FHIR structural integrity:** references must still resolve after id rewriting; `Binary`/`Attachment` stay valid.
5. **Input immutability:** input opened read-only; overlap guard; tests hash the input before/after.
6. **Deterministic output:** sorted file order; no time/randomness/locale in output; same secret → same bytes
   (timing/resources in `report.json` excluded).
7. **Cryptographic secret handling:** `RAKSHA_SECRET` from the environment only; wrapped in `ReleaseSecret`
   (refuses `repr`, `str`, format, pickle); all keyed derivations are HMAC-SHA256; never written to output/logs
   (test scans every output byte). Never commit a secret or a default secret.
8. **No intermediate files; memo caches cleared at the end of every run; the value index is memory-only and refuses pickling.**

### 5.4 Official validation commands (run from the repo root; toolkit unmodified)
| Command | What it validates |
|---|---|
| `python3 organiser-toolkit/validate_output.py --input organiser-toolkit/dev/input --output OUT` | Output contract: `sanitized/` exists, `report.json` valid, every input exported at the same path or declared by SHA-256, statuses legal, declared outputs exist, UTF-8, `records.jsonl` well-formed. Prints `CONTRACT OK`. |
| `python3 organiser-toolkit/check_dev.py --output OUT` | Practice self-check (rough guide, **not** the official score): PII still visible by type/language/channel, canaries, medical values kept, linking P/R/F0.5, raw copies. Reads the practice answer key; dev only. |
| `python3 organiser-toolkit/check_submission.py --repo . --run` | Pre-submit check: `raksha.toml`, team name, README, no hosted-AI deps, then 3 runs: exit code, contract, same-secret determinism, different-secret sensitivity (currently warns, O8), secret never written, input unchanged. |
| `backend/scripts/official_checks.sh [--submit]` | Wrapper: run + `validate_output.py` + `check_dev.py` (+ `check_submission.py --run`). Env: `CLINVEIL_OUT`, `CLINVEIL_TOOLKIT`, `PYTHON`. |
| `python backend/scripts/dev_eval.py --output OUT` | **Ours** (dev only): SCORING.md-style record-level leak, field-level probes, token retention. An approximation, never an official score. |

Developer commands: `cd backend && ../.venv/bin/pytest`; `../.venv/bin/ruff check src tests scripts ../main.py`;
`../.venv/bin/ruff format --check src tests scripts`. Test suites: `unit/`, `integration/`, `regression/`,
`generalization/`, `security/` (tests marked `toolkit` need the toolkit checkout). CI runs lint + tests + contract
checks on Python 3.10 and 3.12. Run with the repo's `.venv` (Python 3.13 locally; runtime supports 3.10+).

---

## 6. Architecture and structure (verified by reading the tree)

```
raksha.toml  main.py  requirements.txt  config/policy.yaml     evaluator contract (repo root)
backend/src/clinveil/
  cli.py pipeline.py                      entry point, two-pass pipeline
  config/       policy loading (flat key: value, no PyYAML)
  ingestion/    discovery (lstat, safe reads), detect, decoding, plausibility, signatures, limits
  parsing/      builder (IR), csv_format, json_format, json_safety, fhir, attachments (base64)
  models/       Document/Field IR, Channel, Finding/Evidence/Action/EntityType, RecordRef
  detection/    engine, semantics, identifiers, names, addresses, clinical, value_index, resolve,
                text, translit, lexicon, views, caches
  sanitization/ processors (placeholders, FHIR id rewrite, withholding, counts), render
  export/       release writers (report.json, records.jsonl)
  security/     secrets, errors (reason codes), paths
  privacy/      pseudonym (HMAC), generalize (age_band only)
  linking/      STUB (Phase 3)        metrics/  EMPTY (Phase 6)
  validation/   pre-exit release check
backend/tests/{unit,integration,regression,generalization,security}   backend/scripts/{dev_eval.py,official_checks.sh}
frontend/       PLACEHOLDER (types, tokens, mock fixtures only; no tooling)
docs/           architecture/ decisions/ evaluation/ security/ api-contract/ team/ research/ PROJECT_HANDOFF.md
organiser-toolkit/   official kit, git-ignored, read-only
```
Key facts: Python standard library only at runtime; two-pass design so a name confirmed in one file is removed
everywhere; detectors work on IR fields, not by re-parsing formats; placeholders `[NAME] [RELATIVE] [PHONE]
[EMAIL] [AADHAAR] [ABHA] [PAN] [MRN] [INSURANCE_ID] [HOUSE] [LOCALITY] [LANDMARK] [VILLAGE] [PIN] [DOB]`;
JSON numbers holding PII become `0`; filenames use bare words.

**Frontend status:** a placeholder. Do not describe it as built.

Document map: `docs/architecture/SYSTEM_ARCHITECTURE.md` (pipeline, trust boundaries), `IMPLEMENTATION_PLAN.md`
(phases, next tasks), `docs/decisions/TECHNICAL_DECISIONS.md` (D1–D28), `docs/security/THREAT_MODEL.md`,
`docs/evaluation/{BASELINE,PHASE1_INGESTION,PHASE2_DETECTION,PHASE2_REMEDIATION}.md`, `docs/api-contract/README.md`,
`docs/team/README.md` (working agreement; area leads not filled in).

---

## 7. Next recommended engineering steps

1. **User decision:** push and merge `phase-2.1-remediation` (or request changes); decide the O1 symlink trade-off.
2. **Phase 3:** evidence graph and pseudonym insertion (see §3), using `name_key_strict` + corroborators.
3. **Phase 4:** keyed per-patient date shifting, truthful age bands, location generalisation, k-anonymity.
4. Phase 5/6: own FHIR structural validator, `metrics/`, mutated practice copy, hex decoding in text (O4).
5. Write the 2-page Project Brief PDF from measured numbers only.
6. Phase 7 only after the above, and only with frontend stack approval.

---

## 8. Licensing and third-party obligations (documented; do not change without the user)
- **No project-wide open-source licence.** Original CLINVEIL material is all rights reserved; making the repo
  public does not grant use/copy/modify/redistribute rights (see `README.md`, "Copyright and licensing").
- **Third-party:** portions adapted from the Secret Wards starter are MIT, Copyright (c) 2026 kartikeyajay2006.
  Full text in `third_party_licenses/secret-wards-toolkit.MIT.txt`; per-file extent in `THIRD_PARTY_NOTICES.md`.
  Files adapted from the starter carry a header comment. If you adapt more third-party code, add the header and
  update the notices. The MIT licence covers those portions only.
- **Contributor IP is unsettled:** no contributor licence or IP-assignment agreements exist; never claim they do
  (`CONTRIBUTING.md`, `docs/team/README.md`).
- Team name stays **APEX**; product name stays **CLINVEIL**.

---

## 9. Handoff update protocol

Every agent updates this file after meaningful work. Do **not** overwrite another agent's entries or delete
history; add to it. At the end of a task update:

- §2 branch/commit table and commit list (real `git` output);
- §3 phase status for the phases you touched;
- §4 outstanding issues (add new ones, change status only with evidence);
- files modified, functionality implemented, tests **actually run** (command and result), validation outcomes;
- known regressions; outstanding decisions; next recommended task (§7);
- a dated entry in the changelog below.

**Read-only reviews:** record findings and recommendations only; state clearly that nothing was fixed.
Keep numbers traceable to a command you ran. A commit cannot contain its own hash: record the hash in the
*next* update.

---

## 10. Changelog (newest first; append, never rewrite)

| Date | Agent | Entry |
|---|---|---|
| 2026-11-27 | Antigravity | Implemented Phase 3 (cross-hospital patient identity resolution and cryptographic pseudonymisation) on branch `phase-3-identity-resolution` from `9205b5a`. Added modular `linking/` package (`models.py`, `normalize.py`, `extract.py`, `matcher.py`, `cluster.py`, `pseudonyms.py`, `linker.py`), domain-separated versioned HMAC-SHA256 (`psn|v1|...`) with collision counter in `privacy/pseudonym.py`, single-patient JSON report locator handling in `parsing/json_format.py`, schema-preserving in-record pseudonym insertion in `sanitization/processors.py`, two-pass pipeline wiring in `pipeline.py`, pre-exit pseudonym consistency check in `validation/contract.py`, cache registration in `detection/caches.py`, and synthetic/adversarial tests (`tests/unit/test_linking.py`, `tests/integration/test_phase3_identity_resolution.py`). Removed `xfail` on `test_different_secret_changes_output`. Run: `ruff check` / `ruff format --check` exit 0 (99 files); `pytest` 766 passed / 0 xfailed across Python 3.10, 3.12, and 3.13; `validate_output.py` CONTRACT OK; `check_dev.py` 0/3230 leaked, 0/4 canaries, 4855/4855 probes, linking precision 1.00 / recall 0.99 / F0.5 1.00 / 0 wrong merges; `check_submission.py --run` READY TO SUBMIT (0 warnings); 1× 2.1 s / 37.9 MB RSS, 10× 22.4 s / 113.7 MB RSS. Not pushed or merged. Next: user review/push/merge of Phase 3, then Phase 4 privacy transformations. |
| 2026-11-27 | Antigravity | Fixed Python 3.10 GitHub Actions CI failure blocking PR #3 (`phase-2.1-remediation` → `main`), committed locally on top of `fab12fb`. Root cause: `organiser-toolkit/dev/input/misc/deep_export.json` (1,500-level nested JSON) triggers `RecursionError` in CPython 3.10 `json.loads()`, which was uncaught in `backend/scripts/dev_eval.py` (`Parsed.__init__` only suppressed `ValueError`). Files changed: `backend/scripts/dev_eval.py`, `backend/tests/regression/test_phase2_release.py`, new `backend/tests/unit/test_dev_eval.py`, `docs/evaluation/PHASE2_REMEDIATION.md` (§9), this file. Run: `ruff check` / `ruff format --check` exit 0 (91 files); `pytest` 745 passed / 1 xfailed on Python 3.10 (`uv`), Python 3.12 (`uv`), and local `.venv` (Python 3.13); Python 3.10 `validate_output.py` (CONTRACT OK), `check_dev.py` (0/3230, 0/4 canaries, 4855/4855), `dev_eval.py` (0.0/3226, 0/8 canaries, 98.8% probes, 99.8% retention), same-secret determinism, and `check_submission.py --repo . --run` (READY, known E5 warning) all exit 0. Regressions: none. Not pushed or merged. Next: user pushes CI fix to PR #3 and merges, then Phase 3 linking. |
| 2026-11-26 | Claude Opus 5.5 | Phase 2.1 final review fixes F1–F4, committed on top of `e6021fa` (the handoff commit created in the entry below). The review file was not present in the repo; findings taken from the task description and reproduced first (15 of 30 new tests failed on `e6021fa`, all 30 pass now). Files changed: `ingestion/discovery.py`, `pipeline.py`, `parsing/attachments.py`, `sanitization/processors.py`, `detection/views.py`, new `tests/regression/test_phase21_final_review.py`, docs (`PHASE2_REMEDIATION.md` §8, this file, `THREAT_MODEL.md`, `README.md`, `PHASE2_DETECTION.md`, `IMPLEMENTATION_PLAN.md`). Run: pytest 741 passed / 1 xfailed; ruff exit 0; `validate_output.py`, `check_dev.py`, `check_submission.py --run` exit 0 (READY, known E5 warning); practice output byte-identical to Phase 2. Regressions: none found. Outstanding decisions: push/merge; O1 symlink trade-off. Next: Phase 3 linking. |
| 2026-11-26 | Claude Sonnet 5.5 | Created this handoff (commit `e6021fa`). Read-only with respect to production code. Verified: branch `phase-2.1-remediation`, HEAD `5a242ab`, `main`=`origin/main`=`ac37504`, Phase 2.1 unpushed; `pytest` 711 passed / 1 xfailed; `ruff check` and `ruff format --check` clean. Not re-run for this entry: the official scripts (figures in §3 come from the preceding verification session). Could not verify: official score (sealed evaluator), Phase 2 commit's own test count, Phase 0/1 numbers (taken from repo docs). The file existed beforehand as an empty untracked placeholder. |
| 2026-11-26 | Claude Opus 5.5 | Phase 2.1: `683074f` audit remediation; `5a242ab` final security-verification fixes (S1–S5). Tests then: 711 passed, 1 xfailed; official checks passed (see §3). Details in `docs/evaluation/PHASE2_REMEDIATION.md`. |
| 2026-11-26 | Claude Opus 5.5 | Phase 2 `53ec8ff` (merged `ac37504`); Phase 1 `d2c4b31` (merged `643c95f`); licensing correction `7934185`; Phase 0 `59c0ea8`. |
