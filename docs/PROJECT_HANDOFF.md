# CLINVEIL: Project handoff (source of truth for all AI coding agents)

| | |
|---|---|
| Product | **CLINVEIL**: "Privacy infrastructure for trusted medical data sharing" |
| Team | **APEX** (the name registered in `raksha.toml`; the product name stays CLINVEIL) |
| Event | Yugaantar DevForge · Track 3 · **Secret Wards** |
| Repository | https://github.com/Amartya989870xxxx/CLINVEIL (intentionally private during active development) |
| Official toolkit | https://github.com/Reinforce-SST/Secret-Wards-ToolKit (cloned read-only at `organiser-toolkit/`, git-ignored, commit `6c0a85a`) |
| Last full verification of this document | 2026-11-27, against Phase 3.3 Pass 4 security remediation (`P33-PASS3-F1` XHTML ownership, `P33-PASS3-F2` R7 before Tier 2a) on branch `phase-3-identity-resolution` (working tree on top of `4ecc67c`; uncommitted; **final independent approval pending**; not merged) |

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
   `docs/architecture/PHASE3_IDENTITY_RESOLUTION.md`, `docs/decisions/TECHNICAL_DECISIONS.md` (D1–D36),
   `docs/security/THREAT_MODEL.md`, and the phase evidence in `docs/evaluation/`.
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
3. gives each real patient one stable keyed pseudonym across files and scripts (**implemented locally on `phase-3-identity-resolution`**, Phase 3 / 3.1 / 3.2, §3; awaiting independent Phase 3.2 approval and merge);
4. generalises quasi-identifiers (dates, ages, locations) so a register-holding attacker cannot re-identify
   (**not implemented yet**, Phase 4, §3).

### 1.3 Users
- **Primary (competition):** the Secret Wards evaluator, which runs `python main.py --input … --output …`.
- **Intended (product):** research teams receiving a hospital data release; hospital data officers producing it.
- **Optional, planned:** a judge/researcher-facing local dashboard (Phase 7, not implemented).

### 1.4 Product workflow (as implemented today on `phase-3-identity-resolution`)
```
input tree ─► discover (sorted, lstat-based) ─► PASS 1: detect+build IR+seed run-local value index + extract RecordEvidence
           ─► LINK: conflict-aware 3-stage clustering + keyed HMAC-SHA256 PSN-XXXXXX assignment (in memory; evidence deleted)
           ─► PASS 2: detect format ─► build IR ─► analyse (semantics, detectors, propagation, resolution)
              ─► rename PII paths ─► sanitise (placeholders, schema-preserving PSN-XXXXXX placement, numbers→0, FHIR birthDate→year, payload re-encode)
              ─► render ─► write sanitized/ + report.json + records.jsonl + logs/detection_summary.json
              ─► self-check the release per record (false-success guard) ─► exit 0
```
Not in the workflow yet: per-patient date shifting, age banding, location generalisation,
k-anonymity suppression (Phase 4).

> **Never describe CLINVEIL as guaranteeing anonymity.** Release privacy is measured only against practice
> data and our own synthetic tests. No finite test proves anonymity. (The README's tagline "resists
> re-identification" is a *goal*; Phase 4 is where it would be earned and no adversarial score has been
> measured.)

---

## 2. Current Git state (verified 2026-11-27)

| Item | Value (verified with `git`) |
|---|---|
| Active branch | `phase-3-identity-resolution` |
| HEAD | `4ecc67c656a1f98de2278f3d458a0d86655ec2be` (`4ecc67c`: `fix(phase-3.1): remediate false patient merges found by the independent audit`) |
| Working tree | **Uncommitted Phase 3.2 + Phase 3.3 Pass 1 (Gemini) + Pass 2 (Claude) + Pass 3 (Claude, P33-F1–F5) + Pass 4 (Claude, P33-PASS3-F1/F2) remediation changes** (not staged, not committed) on top of `4ecc67c`. Modified: `detection/names.py`, `linking/{cluster,extract,matcher,models,normalize,pseudonyms}.py`, `pipeline.py`, `validation/contract.py`, this file. Untracked: `backend/tests/regression/test_phase32_adversarial_remediation.py`, `test_phase33_pass2_remediation.py`, `test_phase33_pass3_remediation.py`, `test_phase33_pass4_remediation.py`, `docs/research/` (must stay untracked). |
| Before HEAD | `32fe8fc` Phase 3 implementation → `9205b5a` Merge PR #3 (`phase-2.1-remediation`, incl. `a74851c` Python 3.10 CI fix) |
| `main` / `origin/main` | both `9205b5a` "Merge pull request #3 from …/phase-2.1-remediation" (Phase 0 + 1 + 2 + 2.1) |
| Phase 3 / 3.1 / 3.2 / 3.3 pushed / merged / approved? | **No.** `32fe8fc` and `4ecc67c` are local-only commits on `phase-3-identity-resolution`. Phase 3.1 (`4ecc67c`) and Phase 3.2 (working tree) received **REJECT — REMEDIATION REQUIRED** from the independent security audits. Phase 3.3 Pass 1 (`NEW-1`–`NEW-4`), Pass 2 (`NEW-5`–`NEW-7`, `PASS1-NEW-5`–`7`), Pass 3 (Carbon Phase 3.3 audit `P33-F1`–`F5`) and Pass 4 (`P33-PASS3-F1`/`F2`) are uncommitted in the working tree; Phase 3 is **not** independently approved (final independent approval pending). |
| Remote | `origin` → https://github.com/Amartya989870xxxx/CLINVEIL.git |
| Untracked (intentional) | `docs/research/GEMINI_PHASE2_CODE_SECURITY_AUDIT.md` (and the new `backend/tests/regression/test_phase32_adversarial_remediation.py`, `test_phase33_pass2_remediation.py` and `test_phase33_pass3_remediation.py` until committed) |
| Toolkit | `organiser-toolkit/` at `6c0a85a`, clean, git-ignored |

Commit history (verified):

| Commit | Meaning |
|---|---|
| `59c0ea8` | Phase 0 bootstrap (**published**; never rewrite) |
| `7934185` | Licensing correction: no project licence, third-party notices, team APEX (**published**) |
| `d2c4b31` → `643c95f` | Phase 1 ingestion; merged via PR #1 |
| `53ec8ff` → `ac37504` | Phase 2 detection; merged via PR #2 |
| `683074f` → `a74851c` → `9205b5a` | Phase 2.1 audit remediation, F1–F4, and Python 3.10 CI fix; merged via PR #3 |
| `32fe8fc` | Phase 3: cross-hospital patient identity resolution and cryptographic pseudonymisation (local) |
| `4ecc67c` | Phase 3.1: false-merge remediation after the independent Phase 3 audit (local; rejected by independent Phase 3.1 audit) |
| (working tree) | Phase 3.2 (F1–F9) + Phase 3.3 Pass 1 (`NEW-1`–`NEW-4`) + Pass 2 (`NEW-5`–`NEW-7`, `PASS1-NEW-5`–`7`) + Pass 3 (`P33-F1`–`F5`) + Pass 4 (`P33-PASS3-F1`/`F2`); uncommitted, unapproved |

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
| 3 Identity resolution | 🟡 Phase 3.3 Pass 1 + Pass 2 + Pass 3 + Pass 4 in working tree (all listed findings remediated and verified by the implementing agents); **uncommitted; final independent approval pending** | `4ecc67c` + working tree on `phase-3-identity-resolution` |
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

### Phase 2.1: Independent audit remediation ✅ (merged at `9205b5a`, PR #3)
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
- **Caveat (added by the independent audit):** "0 wrong merges" above held for the practice data and the original
  tests only. The audit of `32fe8fc` reproduced six false-merge classes on invented data and returned **REJECT**;
  see Phase 3.1.

### Phase 3.1: False-merge remediation (`4ecc67c`, local; rejected by independent Phase 3.1 audit)
- **Objective:** fix the false merges reproduced by the independent audit of `32fe8fc`, without redesigning the
  engine or its cryptography.
- **Reproduced first:** `tests/regression/test_phase31_false_merges.py` gave 23 failed / 18 passed on `32fe8fc`;
  after the fixes it has 46 tests, all passing.
- **Fixes:**
  - R1/R2: identifier **ownership** (relative-labelled fields and JSON keys, kinship cues in text, FHIR
    `RelatedPerson`; ambiguous owners unused) and the `conflict_relative_id_owner` veto.
  - R3: insurance/PMJAY/ESIC and e-mail are corroborators, not global IDs.
  - R4: under a shared global ID, whole names must be compatible (a surname alone no longer passes).
  - R5: the cross-hospital guard runs first and uses reliably established hospitals; short and hospital-type
    MRN prefixes are not distinctive.
  - R6: typed digit cores (patient / admission / visit / prefix).
  - R7: distinct same-issuer MRNs block weak merges, except the `DATASET.md` re-registration case
    (full name + exact DOB + one more corroborator).
  - Complete-linkage vetoes for weak merges; capped full-name blocks abstain.
  - The self-check validates pseudonyms **per record**.
  - Pseudonym bit-selection documentation corrected (low 30 bits of the first 40-bit slice).
  - `for_document()` is no longer O(files × records).
- **Files:**
  - `linking/{extract,normalize,matcher,cluster,models,pseudonyms,linker}.py`;
  - `validation/contract.py`, `privacy/pseudonym.py` (docstring only);
  - new `tests/regression/test_phase31_false_merges.py`; `tests/unit/test_linking.py` (helper API only);
  - docs.
- **Tests & validation (run 2026-11-27):**
  - `pytest` **812 passed** on Python 3.10.20, 3.12.13 and 3.13.7;
  - ruff check/format exit 0 (99 files);
  - `validate_output.py`, `check_dev.py` and `check_submission.py --run` exit 0 (READY, no warnings);
  - practice: TP 6,803 / FP 0 / FN 89, precision 1.0000, recall 0.9871, F0.5 0.9974, **0 wrong merges**
    (unchanged; the practice data has none of the fixed patterns);
  - same-secret determinism; different secret gives 0 shared pseudonyms; input unchanged; side channels clean;
    19 FHIR Bundles with 0 unresolved references;
  - 1× 2.28 s / 41 MB; 10× 22.4 s / 126 MB.
- **Details:** `docs/evaluation/PHASE3_REMEDIATION.md`.
- **Independent Phase 3.1 audit outcome:** **REJECT — REMEDIATION REQUIRED** (report saved outside the production repo as `PHASE3_1_INDEPENDENT_SECURITY_AUDIT.md`). Reproduced five high-impact false-merge vulnerabilities (F1–F5), three medium defects (F6–F8), and low-severity hardening items (F9); remediated in Phase 3.2 below.

### Phase 3.2: Adversarial remediation 🟡 (working tree on top of `4ecc67c`; uncommitted, NOT independently approved or merged)
- **Objective:** remediate findings F1–F9 from the independent Phase 3.1 security audit with minimal, root-cause fixes and permanent regression tests, without weakening existing security invariants.
- **Reproduced first:** new `backend/tests/regression/test_phase32_adversarial_remediation.py` gave **36 failed, 7 passed** on unmodified `4ecc67c`; after the fixes all **43/43 pass**.
- **Fixes implemented (uncommitted):**
  - **F1 (Critical — MRN scope bypass):** `linking/matcher.py` tracks per-MRN reliable hospital provenance (`_mrn_reliable_hospitals`, `_mrn_cross_hospital_disjoint`) so multi-hospital clusters never match Hospital A's MRN against Hospital B's identical MRN; separates true external pathology/lab docs (`is_true_external_lab_only`) from unknown-hospital exports so generic `raw_a & raw_b` never fires between non-lab files; keeps homonym vetoes, `_complete_linkage_conflicts`, and R7 (`_distinct_mrns_same_issuer`) active for all non-verified-same-hospital MRN matches (`shared_prefixed_mrn`, `shared_external_mrn*`, non-reliable scoped MRNs).
  - **F2 (High — Abbreviated-name transitive bridge):** `linking/matcher.py` adds `_full_names_have_any_conflict` enforcing complete-linkage full-name conflict checks across all stages and passes so an abbreviated name (`N. Vermeer`) never overrides a concrete full-name conflict (`Nolan Vermeer` vs `Nathan Vermeer`), while still preserving legitimate `Nolan`↔`N.` linking and strong-ID spelling variants when a concrete `EXACT_FULL`/`VARIANT_FULL` match exists.
  - **F3 (High — Multi-patient FHIR Bundle):** `linking/extract.py` extracts each FHIR `Patient` resource independently (`_extract_single_fhir_patient`) and checks pairwise identity/conflicts (`_fhir_patients_are_ambiguous`), marking multi-patient Bundles ambiguous (`ambiguous_doc=True`, `patient: null`) unless all `Patient` resources are positively confirmed to be the same person with zero conflicts.
  - **F4 (High — Relative identifier ownership):** `linking/extract.py` excludes `RelatedPerson` narratives from patient evidence (routing person-unique IDs to `relative_global_ids` veto-only); parses `RelatedPerson.identifier` for ABHA addresses, PANs, and un-systemed Aadhaars; adds `emergency_contact`, `contact_person`, and `family` ID containers (preserving `Family Name` and `Emergency Admission`); expands Hindi/Hinglish/English kinship cues; and preserves relative ownership across commas and single newlines until an explicit patient/demographic reset (`context_owner`), abstaining as `"ambiguous"` on immediately following single-line `Father: <Name>\nAadhaar:` layouts.
  - **F5 (High — Per-record hospital attribution):** `linking/extract.py` normalises `_FACILITY_LABELS` (`_norm_label`, covering `Facility Name`, `Clinic`, `Institution`, etc.) consistently across document and per-record extraction, never promotes Row 0's per-row facility to a document-wide default on multi-facility or sparse tables, and clears inherited hospital scope when a row's facility cell is blank.
  - **F6 (Medium — Issue C re-registration independence):** `linking/matcher.py` requires an unambiguous exact DOB (`_exact_dob_matches`, rejecting swapped slash dates `03/04` vs `04/03`) plus a non-DOB-derived independent corroborator (`_REREG_INDEPENDENT_CORROBS`: phone, relative, insurance, email — never `corrob_village_birth_year` or `corrob_village_age`), adds `conflict_abha_address` to `hard_conflicts`, and keys unreliable-stem distinctive-prefix UHIDs under `issuer_pfx:` so distinct same-prefix UHIDs across generic filenames trigger R7.
  - **F7 (Medium — Hospital normalisation):** `linking/normalize.py` keeps city suffixes when a hospital head is generic (`"City Hospital, Lucknow"` vs `"City Hospital, Kanpur"`), collapses contiguous single-letter initials (`"K. M. Hospital"` → `"km"`), and preserves valid generic hospital names (`"District General Hospital"`).
  - **F8 (Medium — Contract validation):** `validation/contract.py` + `pipeline.py` detect JSON/CSV by content (matching D14 for non-standard extensions like `.dat`) and scope foreign-pseudonym checks during pipeline runs to `issued_pseudonyms` so pre-existing literal `PSN-XXXXXX` clinical codes do not cause false contract failures.
  - **F9 (Low — Hardening):** `linking/models.py` adds `__reduce__` pickle refusal on `DateEvidence` and removes raw `loc` from `RecordEvidence.__repr__`; `detection/names.py` prevents period-gaps after multi-letter words and colon field labels (`Husband:`) from bleeding into `PATIENT_NAME`; `linking/pseudonyms.py` counts identical-canonical-key re-derivations in `pseudonym_collisions_resolved`.
- **Files modified / added (uncommitted):**
  - `backend/src/clinveil/linking/{models,normalize,extract,matcher,pseudonyms}.py`
  - `backend/src/clinveil/detection/names.py`
  - `backend/src/clinveil/validation/contract.py`
  - `backend/src/clinveil/pipeline.py`
  - `backend/tests/regression/test_phase32_adversarial_remediation.py` (new, 43 tests)
  - `docs/PROJECT_HANDOFF.md`
- **Tests & validation actually executed (2026-11-27):**
  - `pytest tests/regression/test_phase32_adversarial_remediation.py`: **43 passed** (exit 0; was 36 failed / 7 passed on `4ecc67c`);
  - full `pytest -q`: **855 passed** on Python **3.13.7** (21.65 s, exit 0), Python **3.10.20** offline via `uv` (21.01 s, exit 0), and Python **3.12.13** offline via `uv` (19.17 s, exit 0);
  - `ruff check src tests scripts ../main.py` (exit 0) and `ruff format --check src tests scripts ../main.py` (exit 0, 101 files);
  - `organiser-toolkit/validate_output.py`: `CONTRACT OK` (exit 0);
  - `organiser-toolkit/check_dev.py`: exit 0 — 0/3230 visible, 0/4 canaries, 4855/4855 medical values, linking precision 1.00 / recall 0.98 / F0.5 1.00, **0 wrongly merged**, 0 raw copies (note: practice clusters went from 49 to 51 because two records with spelling-variant names now conservatively abstain under `_has_competing_conflict` rather than weakening ambiguity guards; practice data is NOT evidence of hidden-dataset performance);
  - `organiser-toolkit/check_submission.py --repo . --run`: `READY TO SUBMIT` (exit 0, 2.3 s, 0 warnings);
  - Determinism & privacy checks: same-secret byte-identical `sanitized/` + `records.jsonl` + `logs/detection_summary.json`; different-secret 51 vs 51 PSNs with 0 shared and identical linkage partition; `TMPDIR` 0 files; input tree immutable; 19 FHIR Bundles with 0 unresolved references; secret absent from all outputs.
- **Status:** **NOT committed, NOT pushed, NOT merged.** The independent Phase 3.2 security audit (`PHASE3_2_INDEPENDENT_SECURITY_AUDIT.md`) returned **REJECT — REMEDIATION REQUIRED** with findings `NEW-1` through `NEW-7`.

### Phase 3.3, Pass 1: Critical identity-resolution remediation 🟡 (working tree on top of `4ecc67c`; uncommitted, NOT complete or independently approved)
- **Objective:** remediate the four High-severity vulnerabilities (`NEW-1`, `NEW-2`, `NEW-3`, `NEW-4`) from the independent Phase 3.2 security audit (`PHASE3_2_INDEPENDENT_SECURITY_AUDIT.md`) and add permanent synthetic regression tests before proceeding to Pass 2 (`NEW-5`, `NEW-6`, `NEW-7`).
- **Reproduced first:** 30 new regression test cases added to `backend/tests/regression/test_phase32_adversarial_remediation.py` reproduced 20 failures on the Phase 3.2 working tree prior to the fixes; after the fixes all **73/73 tests** in `test_phase32_adversarial_remediation.py` pass.
- **Fixes implemented in Pass 1 (uncommitted):**
  - **NEW-1 (High — Structured relative ownership leakage):** `linking/extract.py` routes relative-owned split-name fields (`emergency_contact.{first_name, middle_name, last_name}`, etc.) into `rel_split_*` → `relative_names` instead of `patient_names`; guards structured and free-text demographic extraction (`Sem.AGE`, `Sem.GENDER`, `Sem.RELATION`, `Sem.DISTRICT`, `Sem.DOB`, free-text age/gender) with `if not is_rel_field:`; and enforces relative/context ownership checks on `EntityType.PATIENT_NAME`, `EntityType.DOB`, `EntityType.VILLAGE`, and `EntityType.PIN` in `_consume_findings`.
  - **NEW-2 (High — Free-text and encoded relative ownership bypass):** `linking/extract.py` replaces the naive `\.(?=\s+[A-Z\u0900-\u097f])` sentence split with `_is_sentence_period` / `_last_boundary_cut` so dotted titles (`Mr.`, `Mrs.`, `Ms.`, `Dr.`, `Prof.`, `Smt.`, `Sh.`, `Sri.`, `श्री.`) and single-letter initials (`G.`) do not truncate relative clauses; extends `_KIN_CUE_RE` to cover compound relational phrases (`Father of patient`, `Husband of the patient`, `Guardian of patient`, `Attendant for pt`, `Patient's husband`, `Patient ke pati`, `मरीज़ के पति`, `रोगी के पिता`) and ignores `_PATIENT_OWNER_CUE_RE` matches contained inside a kinship phrase (`_non_kin_patient_cues`); and runs finding ownership attribution on a decoded ownership view (`_build_owner_view` / `_finding_owner` using `views.decoded_view` with inline tags collapsed to spaces) so tag-heavy XHTML (`Encounter.text.div`) and HTML-entity / `\uXXXX` / `%-escaped` kinship cues map accurately.
  - **NEW-3 (High — External-lab and generic MRN collisions):** `linking/normalize.py` adds generic file/register words (`ward`, `register`, `roster`, `sheet`, `table`, `list`, `record`, `visit`, `admission`, `batch`, `upload`, `data`, `file`) to `_HOSPITAL_STOP`; `linking/extract.py` inspects parent directory segments in `_infer_document_hospital_inner` so `halcyon_hospital/ward_register.csv` vs `meridian_hospital/ward_register.csv` and `dir_alpha/ward_register.csv` vs `dir_beta/ward_register.csv` never share a generic filename MRN scope; `linking/matcher.py` restricts `shared_external_mrn_with_name` / `shared_external_mrn` to pairs linking an external lab (`is_true_external_lab_only`) with a non-lab hospital cluster (`has_non_lab_hospital`), preventing two different external labs (`City Lab` vs `Horizon Lab`) from merging on a generic MRN without a shared hospital anchor; and `linking/cluster.py` adds competing-candidate ambiguity protection in `_merge_from_blocks` so a nameless external lab abstains when `>= 2` non-matching hospital clusters share the same generic MRN and either conflict or come from disjoint reliable hospitals.
  - **NEW-4 (High — Overly permissive phonetic matching):** `linking/matcher.py` replaces coarse vowel-stripped `name_key` equality and middle-token ignoring in `_names_phonetically_compatible` with `_tokens_phonetically_compatible`, preserving primary vowel distinctions (`Kiran != Karan`, `Alok != Alka`, `Sunil != Sonal`) and rejecting conflicting middle names on equal-length 3-token names (`Anil Kumar Solanki != Anil Prakash Solanki`) while still supporting cross-script transliteration (`प्रणव कुलकर्णी` ↔ `Pranav Kulkarni`, `आरवेल डनमोर` ↔ `Arvel Dunmore`), schwa (`Kamlesh` ↔ `Kamalesh`), `-e`/`-eya` suffixes (`Pande` ↔ `Pandeya`), 1-char medial vowel elision (`Zarina` ↔ `Zarna`), middle-name omission (`Anil Solanki` ↔ `Anil Kumar Solanki`), and initials (`N. Vermeer` ↔ `Nolan Vermeer`).
- **Files modified in Pass 1 (uncommitted):**
  - `backend/src/clinveil/linking/{extract,normalize,matcher,cluster}.py`
  - `backend/tests/regression/test_phase32_adversarial_remediation.py` (expanded from 43 to 73 tests)
  - `docs/PROJECT_HANDOFF.md`
- **Tests & validation actually executed (2026-11-27):**
  - `pytest -q tests/regression/test_phase32_adversarial_remediation.py`: **73 passed in 0.89 s** (exit 0);
  - full `pytest -q`: **885 passed** on Python **3.13.7** (24.83 s, exit 0), Python **3.10.20** offline via `uv` (22.37 s, exit 0), and Python **3.12.13** offline via `uv` (20.10 s, exit 0);
  - `ruff check src tests scripts ../main.py` (exit 0) and `ruff format --check src tests scripts ../main.py` (exit 0, 101 files);
  - `organiser-toolkit/validate_output.py`: `CONTRACT OK` (exit 0);
  - `organiser-toolkit/check_dev.py`: exit 0 — 0/3230 visible, 0/4 canaries, 4855/4855 medical values, linking precision 1.00 / recall 0.96 / F0.5 0.99, **0 wrongly merged**, 0 raw copies;
  - `organiser-toolkit/check_submission.py --repo . --run`: `READY TO SUBMIT` (exit 0, 2.5 s, 0 warnings).
- **Remaining vulnerabilities & architectural items for Phase 3.3 Pass 2 (NOT fixed in Pass 1).** *Naming note added in Pass 2:* the three items below are the Pass 1 review findings the Pass 2 brief calls `PASS1-NEW-5`, `PASS1-NEW-6` and `PASS1-NEW-7`. The Carbon audit's own `NEW-5`, `NEW-6A/6B` and `NEW-7A/7B` (facility metadata, contract parsing, partial evidence, E/O initials, multiple ABHA addresses) were missing from this list. All of them are handled in Pass 2 below:
  - **NEW-5 (Medium — `issuer_pfx` R7 bypass on reliable hospitals):** `_authoritative_ids_by_scope` (`linking/matcher.py:222`) only registers `issuer_pfx:<type>` when `not is_rel_hosp`, so two distinct prefixed UHIDs (`KSR-26-000111` vs `KSR-26-000222`) from the same issuer can bypass R7 when one record is in a reliable hospital file (`hosp:kesari`) and the other is in an unreliable stem export (`hosp:exportjan`).
  - **NEW-6 (Medium — Order-dependent clustering in Stage A/B):** `_merge_from_blocks` (`linking/cluster.py:180-220`) merges remaining valid pairs sequentially in `sigs[r]` order, so transitive chaining across overlapping records can still depend on record-locator ordering when a bridge record links two otherwise non-matching clusters.
  - **NEW-7 (Low — Per-record `hospital_reliable` downgrade on multi-record files):** `_extract_record` (`linking/extract.py:482`) initialises `rec_reliable = False` and only restores document-level `reliable` in `extract_document_evidence` (`extract.py:239`), leaving `rec_reliable = False` during `_extract_record` if `_extract_record` is called directly or inspected before post-adjustment.
- **Status:** **Phase 3 is NOT complete and NOT independently approved.** Pass 2 (`NEW-5`–`NEW-7`) and a fresh independent security audit are required before commit/push/merge.

### Phase 3.3, Pass 2: Final security remediation and integration 🟡 (Claude Code; working tree on top of `4ecc67c`; uncommitted; **Carbon independent approval pending**)
- **Starting state (verified):**
  - branch `phase-3-identity-resolution`, HEAD `4ecc67c`;
  - Gemini Pass 1 changes uncommitted in the working tree; 885 tests passing;
  - the Antigravity session was interrupted; its work could not be told apart from Pass 1 and was preserved as found (`detection/names.py`, `pipeline.py` and `linking/pseudonyms.py` hold the Phase 3.2 F8/F9 changes documented above);
  - the Carbon Phase 3.2 audit report and the Gemini Pass 1 report are **not present** in the repository or the user's home folders, so Pass 2 worked from the brief and reproduced every finding independently.
- **Reproduced first.** `backend/tests/regression/test_phase33_pass2_remediation.py` (62 tests, invented identities) was checked against a faithful rebuild of the Pass 1 code in a scratch copy, built by restoring every function Pass 2 changed:
  - the rebuild passes the whole pre-existing suite (873 passed + 12 toolkit-dependent skips);
  - it fails **40 of 62** new tests;
  - the 22 that pass are positive controls and invariants that already held.
- **Fixes (all uncommitted):**
  - **PASS1-NEW-5 (issuer prefix vs reliability):**
    - `matcher._authoritative_ids_by_scope` records `issuer_pfx:<type>` for every scope, reliable hospital or not;
    - so `KSR-26-004417` (reliable hospital file) vs `KSR-26-004981` (unreliable export) now triggers R7;
    - the key only vetoes and never creates a match;
    - same UHID at two hospitals, different issuers, and the `DATASET.md` re-registration exception still link.
  - **PASS1-NEW-6 (transitive bridges, order):** `cluster.py` was rewritten around `_resolve_edge_groups`, used by Stages A, B and every C1 pass.
    - Each stage first collects its candidate edges among the clusters that exist at stage start, then resolves each connected group as a set:
      - **complete linkage:** every pair in a group must be compatible (`strong_pair_conflicts` for identifier groups, plus R7 when the group has a weak MRN edge; the full `compare_profiles` verdict for name groups);
      - a cluster adjacent to two mutually conflicting clusters is an **ambiguous bridge**, as is one joining two different hospitals through a generic external-lab MRN (generalising the Pass 1 NEW-3 pre-check);
      - bridges abstain and are **frozen for all later stages**, so excluded evidence cannot re-enter (e.g. through a Stage B verified MRN or a Stage C name match);
      - if conflicts remain without a direct bridge, the non-conflicting connectors are frozen; otherwise the group abstains.
    - Groups are capped at `MAX_COMPONENT = 256` clusters (bounded work).
    - Stage C2 no longer attaches two fragmented singletons that conflict with each other to the same anchor.
    - `hard_conflicts` adds `conflict_name_fragment`: a single-token name contradicting a full name on the other side, which closed the last cross-stage complete-linkage gap found by a randomised probe.
    - Permutation invariance is shown by metamorphic tests (40 random order/file/locator permutations of an adversarial corpus, an end-to-end file-rename and row-reorder test) and on practice evidence (20/20 identical partitions).
  - **PASS1-NEW-7 / NEW-5 (facility provenance):** `extract.py` uses `_facility_label`, `_facility_from_value` and `_resolve_facilities`.
    - Facility keys are read from the full JSON path, so nested `facility.name/title/value/display` count.
    - Facilities under referral, transfer, payer or insurer containers are ignored.
    - Aggregator, exchange and vendor values are never an issuer, and a `provider` key must name a recognisable hospital or lab.
    - Several different hospitals in document metadata make the document scope ambiguous and unreliable.
    - Per-record facility values are never promoted to a document default.
    - Every record starts from the document scope and its reliability (passed into `_extract_record`; the post-hoc upgrade is removed). An explicit facility in the record overrides it, conflicting explicit facilities leave it unscoped, and a blank or missing facility keeps the document metadata but never another record's value.
  - **NEW-6A (contract parsing):** `validation/contract._ParsedOutput` picks the structure from the record locator, not the extension.
    - JSON pointers are resolved in parsed JSON even under `.csv`, `.tsv` or `.dat`.
    - `row:N` is resolved in the delimited table, with the delimiter sniffed exactly as ingestion does (`parsing.csv_format`).
    - Malformed content makes the record unlocatable instead of crashing.
    - Literal PSN-shaped clinical text is not foreign; a real issued pseudonym of another patient still is.
  - **NEW-6B (partial evidence):**
    - `RecordEvidence.has_any_evidence` considers every populated identity field.
    - `_fhir_patients_are_ambiguous` keeps partial Patients in the check. A pair is accepted only if it is a confident match or one Patient is an exact-value partial duplicate of the other (`_evidence_subset`). Evidence-free stubs are ignored, so not every multi-Patient Bundle is rejected.
  - **NEW-7A (E/O initials):**
    - `strict_name_token` applies the initial `e→i` / `o→u` fold to bare initials too.
    - `build_name_evidence` keeps capital single-letter initials that were dropped as the stop words `a`/`i`/`o` (excluding `S/O`-style pieces), so "O. Kadri" no longer collapses to a bare surname that matched every Kadri.
    - `compare_names` treats "Nolan" vs "N. Vermeer" as undecided rather than a conflict.
    - Vowel distinctions are preserved: `A.` ≠ `Evander`/`Omar`, `Kiran` ≠ `Karan`. The `E.`↔`I…` fold is inherited from `Eshaan`~`Ishaan`. *(Superseded in Pass 3, `P33-F4`: bare initials are no longer vowel-folded.)*
  - **NEW-7B (multiple ABHA addresses):** `conflict_abha_address` fires only when no validated Aadhaar or ABHA number is shared. Hard contradictions (e.g. gender) still split.
  - **Review of Gemini Pass 1 (`NEW-1`–`NEW-4`):**
    - Relative-ID ownership was spot-checked on 8 extraction paths: JSON `guardian` object, CSV `Guardian Aadhaar`, free text, base64 attachment, HTML entity, Hindi, attendant phrase, and inline `w/o … (Aadhaar)`. None leak to the patient; the inline case abstains.
    - The Pass 1 tests all still pass.
    - Pass 1's Stage B competing-candidate pre-check is superseded by the group resolver.
- **Files changed in Pass 2 (uncommitted):**
  - `backend/src/clinveil/linking/{cluster,matcher,extract,models,normalize}.py`
  - `backend/src/clinveil/validation/contract.py`
  - `backend/tests/regression/test_phase33_pass2_remediation.py` (new, 62 tests)
  - `docs/PROJECT_HANDOFF.md`
- **Verification actually executed (2026-11-27, exit codes in brackets):**
  - `ruff check src tests scripts ../main.py` [0]; `ruff format --check …` [0] (102 files);
  - `pytest -q`: **947 passed** on Python **3.13.7** [0], **3.10.20** [0] (offline `uv`) and **3.12.13** [0] (offline `uv`);
  - `validate_output.py`: CONTRACT OK [0];
  - `check_dev.py` [0]: 0/3230 visible, 0/4 canaries, 4855/4855 medical values, linking P 1.00 / R 0.97 / F0.5 0.99, **0 wrongly merged**, 0 raw copies;
  - team pairwise metrics: TP 6706 / FP 0 / FN 186, recall 0.9730 (Pass 1 ≈ 0.96, Phase 3.1 0.9871);
  - `check_submission.py --repo . --run`: READY TO SUBMIT [0];
  - same secret twice: `sanitized/`, `records.jsonl` and `logs/` byte-identical (only the `seconds` / `peak_rss_mb` telemetry in `report.json` differs);
  - different secret: 53 vs 53 PSNs, 0 shared, identical partition;
  - input tree hash unchanged; 0 files left in a dedicated `TMPDIR`; secret absent from outputs and console;
  - 19 FHIR Bundles, 459 references, 0 unresolved;
  - detection log holds counts only (no 12-digit runs, PSNs or e-mails);
  - performance: 1× 2.46 s / 41 MB; 10× (2,000 files) 27.6 s / 192 MiB peak RSS (Phase 3.1: 22.4 s / 126 MB).
- **Limitations (unchanged or new):**
  - Bridge abstention is precision-first: a record legitimately carrying two IDs whose other holders disagree stays unlinked.
  - A group above 256 clusters abstains entirely.
  - The `E.`↔`I…` initial fold can match two different people whose names start with E and I. *(Fixed in Pass 3, `P33-F4`.)*
  - Facility-container exclusion is word-based (`referral`, `transfer`, `payer`, …).
  - Practice data contains none of these adversarial patterns; the hidden dataset is untested.
- **Status:** IMPLEMENTATION COMPLETE in the working tree — **NOT committed, NOT pushed, NOT merged, and NOT independently approved. Carbon independent approval is pending.**

### Phase 3.3, Pass 3: Final targeted security fixes 🟡 (Claude Code; working tree on top of `4ecc67c`; uncommitted; **final independent audit pending**)
- **Scope:** the five findings of the independent Carbon Phase 3.3 audit (27 November 2026), `P33-F1`–`P33-F5`. Surgical: no architecture rewrite, the 256-component policy unchanged, no new dependency, no output-contract change.
- **Starting state (verified):** branch `phase-3-identity-resolution`, HEAD `4ecc67c656a1f98de2278f3d458a0d86655ec2be`, the Pass 1/Pass 2 working tree exactly as described above (9 modified source files + handoff, two untracked test files, untracked `docs/research/`), `organiser-toolkit/` clean at `6c0a85a`. `src/` and `tests/` were copied to the scratchpad **before** editing.
- **Reproduced first.** New `backend/tests/regression/test_phase33_pass3_remediation.py` (66 tests, invented identities only) was run against the unmodified snapshot laid out as the repo (import path verified to be the snapshot): **46 of 66 fail**; the 20 that pass are positive controls. All 947 earlier tests pass on the snapshot (955 passed + 12 toolkit-dependent skips with the new file). All 66 pass now.
- **Fixes:**
  - **P33-F1 (weak-MRN group homonym-veto bypass), `cluster._resolve_edge_groups` + `matcher.weak_path_conflicts`:**
    - inside an identifier group, members are labelled by their sub-component under STRONG edges only (validated global ID / verified same-hospital MRN, `_strong_edge_labels`);
    - two non-adjacent members in the same strong sub-component are checked with `strong_pair_conflicts` (unchanged: soft homonym vetoes relaxed, because strong IDs prove identity);
    - two members joined only through a WEAK edge are checked with `weak_path_conflicts` on the union profiles of their strong sub-components: exactly the Tier-2b vetoes of `compare_profiles` (IDs, gender, DOB, age, names, relative name, village, district, complete-linkage spans, R7 with the re-registration exception), with transliteration-tolerant names as for a direct weak MRN match;
    - so a partial record (MRN + name only; external lab slip or a blank CSV row) can no longer join two homonyms that a direct comparison keeps apart: it becomes an ambiguous bridge, abstains and is frozen.
    - *Why not the plain `compare_profiles(...) == CONFLICT` between lone members:* measured on practice data, that dropped recall from 0.9730 to 0.92. Every vetoed pair was the same patient: 7 Devanagari/Latin spelling pairs joined through a lab slip (a direct weak match tolerates these phonetically), and 3 where one record names the father and another the husband, joined through a verified UHID and then a prefixed UHID. Comparing strong sub-components as Stage B compares merged clusters restores TP 6706 / FN 186 with FP 0.
  - **P33-F2 (relative age/gender leakage), `extract._patient_owned_demographics`:** free-text ages and genders (`normalize.iter_free_ages` / `iter_free_genders` report positions) are kept only when `context_owner` on the decoded owner view (HTML/XHTML tags, entities, `\uXXXX`, `%XX`) says *patient*. Used in `_extract_record` free text and FHIR narratives/attachments (`Encounter.text.div`). Hindi kin words used as labels (`पत्नी: …`) are no longer read as the patient's `W/o` gender. Structured `Age`/`Gender` fields and patient-owned text demographics are unchanged.
  - **P33-F3 (relative-owned facility override), `extract._facility_label`:** a facility under a relative-owned label or JSON ancestor (`guardian`, `father`, `mother`, `spouse`, `emergency_contact`, `contact_person`, `next_of_kin`, Hindi/Hinglish kin words, family-ID containers) is ignored, through the same `_keys_relative_owned` rule as `field_is_relative_owned`. Referral / transfer / payer exclusions and aggregator rules are unchanged; unknown provenance never becomes reliable.
  - **P33-F4 (cross-letter initial folding), `normalize.strict_name_token` / `initial_key` / `_initial_matches`:** a bare one-letter initial is no longer vowel-folded (`E.` ≠ `I.`). Initials are compared with `initial_key` of the full token: the raw Latin first letter for vowel-initial Latin names (`E.` ~ `Evander`/`Eshaan`, `O.` ~ `Omar`; never `Imran`/`Indira`/`Umesh`), the transliterated vowel with its long spelling collapsed for Devanagari (`I.` ~ `ईशान`, `U.` ~ `उमेश`), and the strict consonant otherwise (consonant folds unchanged). Full-name vowel folds (`Eshaan`~`Ishaan`, `Omar`~`Umar`) are unchanged. `matcher._names_phonetically_compatible` uses the same rule.
  - **P33-F5 (oversized component re-entry), `cluster._resolve_edge_groups`:** every member of a group above `MAX_COMPONENT = 256` is added to `frozen` before continuing, and so is every member of a group that abstains as a whole (no bridge, every member in a conflict). No such record can re-enter Stage B, C1 or C2.
- **Tests (66):** F1 Carbon cases (cross-file prefixed UHID + two homonymous OPD records + external lab slip; three-row unverified-stem CSV with two conflicting homonyms and a partial row), positive controls (compatible weak group; verified same-hospital UHID with father vs husband still links), unit and 12 metamorphic order tests; F2 child + grandfather (evidence and false-split end-to-end), female patient + male father (evidence and false-merge end-to-end under a verified UHID), FHIR `Encounter.text.div` with an opposite-sex relative, explicit Patient labels, relatives before and after the patient, multiple relatives with HTML entities and Hindi, Hindi patient-owned demographics, Aadhaar continuity; F3 guardian / emergency contact / nested father / spouse / contact person, document-level guardian facility, patient-owned facility kept, referral exclusion kept, guardian facility cannot split one patient; F4 11 initial pairs (both directions and phonetic path), `E.` vs `I.`, full-name folds kept, Devanagari initials, shared household phone negative/positive, weak shared MRN negative/positive; F5 260-record component with Stage B and C2 re-entry routes plus an unrelated anchor, positive controls at 8 and exactly 256 records, whole-group abstention freezes every member; cross-finding F3×F1 (guardian hospital cannot make a weak MRN "verified"), F4×F1 (an `E.` partial record joins only the E name), F2×F1 (relative ages neither create nor hide weak-group conflicts).
- **Files changed in Pass 3 (uncommitted):** `backend/src/clinveil/linking/{cluster,matcher,extract,normalize}.py`; new `backend/tests/regression/test_phase33_pass3_remediation.py`; `docs/PROJECT_HANDOFF.md`.
- **Verification actually executed (2026-11-27, exit codes in brackets):**
  - `ruff check src tests scripts ../main.py` [0]; `ruff format --check …` [0] (103 files);
  - `pytest -q`: **1013 passed** on Python **3.13.7** [0], **3.10.20** [0] and **3.12.13** [0] (offline `uv`);
  - `validate_output.py`: CONTRACT OK [0]; `check_dev.py` [0]: 0/3230 visible, 0/4 canaries, 4855/4855 medical values, linking P 1.00 / R 0.97 / F0.5 0.99, **0 wrongly merged**, 0 raw copies; `check_submission.py --repo . --run`: READY TO SUBMIT [0] (git status and toolkit unchanged);
  - practice pairwise linkage (check_dev formula): TP 6706 / FP 0 / FN 186, recall 0.9730, identical to Pass 2;
  - same secret twice: `sanitized/`, `records.jsonl`, `logs/` identical; `report.json` identical apart from `seconds` / `peak_rss_mb`;
  - different secret: 53 vs 53 PSNs, 0 shared, identical partition;
  - input tree hash unchanged; 0 files left in a dedicated `TMPDIR`; secret absent from outputs and console;
  - 19 FHIR Bundles, 459 references, 0 unresolved;
  - logs/console: no practice PII (the only substring hit is a 4-letter name inside the word "summary", same as Pass 2);
  - abstained-component re-entry, instrumented on practice: 1 frozen cluster, 0 re-entered; 20/20 identical partitions under order/file/locator permutations;
  - random probes: 300 seeds × 6 permutations and 3000 datasets (verified MRNs) plus 3000 weak-MRN/relative/initial datasets × 4 permutations: 0 order dependence, 0 hard complete-linkage violations;
  - performance: 1× 2.49 s / 41 MiB; 10× (2,000 files) 28.1 s / 191 MiB peak RSS (Pass 2: 2.46 s / 41 MB, 27.6 s / 192 MiB);
  - added lines scanned against the practice answer key: 0 hits (one brief example name that coincides with a practice token was replaced by an invented one).
- **Limitations:**
  - Free-text demographics with an *ambiguous* owner (e.g. `Rhea W/o Idris 34 yrs` with no comma) are dropped, as for identifiers; structured fields are unaffected.
  - The relative-name homonym veto does not know relation types (father vs husband); between members linked only through weak MRNs it still applies, so such records may stay split (precision first).
  - Comparing union profiles of strong sub-components uses best-match semantics for soft vetoes, as every merged cluster does in Stage B/C.
  - Kinship detection in facility paths and free text is word-list based.
  - Practice data contains none of these adversarial patterns; the hidden dataset is untested.
- **Status:** IMPLEMENTATION COMPLETE in the working tree — **NOT committed, NOT pushed, NOT merged, and NOT independently approved. Final independent audit pending.**

### Phase 3.3, Pass 4: Security remediation and verification 🟡 (Claude Code; working tree on top of `4ecc67c`; uncommitted; **final independent approval pending**)
- **Scope:** two HIGH false-merge findings reproduced independently after Pass 3 (`PHASE3_3_PASS3_FINAL_APPROVAL_AUDIT.md`, `PHASE3_3_PASS4_F1_F2_VERIFICATION.md`, kept outside the repo): `P33-PASS3-F1` (XHTML relative ownership) and `P33-PASS3-F2` (Tier 2a bypasses R7). Also the audit's minor items: the Devanagari gender word boundary and `P33-PASS3-F3` (`ruff format` of `test_phase33_pass2_remediation.py`). Minimal changes: no architecture, normalisation, evidence-model or pseudonym redesign, no new dependency, no output-contract change.
- **Starting state (verified):** branch `phase-3-identity-resolution`, HEAD `4ecc67c656a1f98de2278f3d458a0d86655ec2be`; working tree = Pass 1–3 (9 modified source files + this file; untracked Phase 3.2 / Pass 2 / Pass 3 test files and `docs/research/`); `organiser-toolkit/` clean at `6c0a85a`. `src/` and `tests/` were copied to the scratchpad before editing.
- **P33-PASS3-F1 root cause:** `detection.views.decoded_view` turns every tag into `\n`, and `extract._build_owner_view` only turned inline tags (`<span>`, `<b>`) back into spaces. A structural tag pair (`</td><td>`, `</dt><dd>`, `</p><p>`) therefore became `\n\n`, which `_HARD_CLAUSE_RE` treats as a hard clause boundary. "Father" was cut off from "<name>, 42 yrs, Aadhaar …", so the father's age and Aadhaar became the child's (FHIR `Encounter.text.div`), and child and father got one pseudonym.
- **P33-PASS3-F1 fix (`extract._build_owner_view`):** each run of consecutive tags, with the insignificant whitespace around it (pretty-printed XHTML), becomes ONE separator, so XHTML reads like the equivalent plain text:
  - inline markup or a label/value join inside one row / entry (`</td><td>`, `</th><td>`, `</dt><dd>`): a space, so `Father | <name>, 42 yrs` reads as `Father <name>, 42 yrs` (`relative`);
  - a new section (`<h1>`–`<h6>`, `<hr>`, `<section>`, `<article>`): a hard boundary (`\n\n`, or `;` for a one-character run), so unrelated sections stay separate;
  - any other block boundary (`</p><p>`, `</tr><tr>`, `<br>`, `</dd><dt>`): a single newline, so a value on the paragraph after `Father: <name>` is `ambiguous` (not patient-owned) exactly as in plain text, and a `Patient` cue still resets ownership.
  Not a blanket `\n\n`→`\n` replacement: plain-text paragraph breaks are untouched; only tag runs change.
- **Devanagari gender boundary (confirmed, fixed in `normalize`):** Python's `\b` does not treat the vowel signs `ा`/`ी` as word characters. So `लिंग: महिला` / `लिंग: स्त्री` never matched, and `पुत्री` (daughter) matched as `पुत्र` (son), giving the wrong gender M. `_GENDER_FREE_RE` and `_RELATION_GENDER_RE` now use explicit `(?![\wऀ-ॿ])` word ends, and `पुत्री` is tried before `पुत्र`. A kin word used as a label (`पत्नी:`) is still excluded.
- **P33-PASS3-F2 root cause:** `compare_profiles` returned Tier 2a (`verified_same_hospital`) as soon as two records shared ANY local ID at a reliable hospital, including a non-authoritative OPD / IPD / admission number. This happened before the R7 check (`_distinct_mrns_same_issuer`); `weak_path_conflicts` also returned early. So two patients with different UHIDs at one hospital merged through one shared OPD number.
- **P33-PASS3-F2 fix (`matcher`, `cluster`):**
  - `compare_profiles`: the R7 check (distinct authoritative UHIDs from one issuer, re-registration exception unchanged) now runs after Tier 1 (validated global ID) and BEFORE Tier 2a;
  - `weak_path_conflicts`: R7 is enforced when a verified local ID is shared, unless a validated global ID is shared (new helper `r7_conflict`);
  - `strong_pair_conflicts(..., via_local_id=True)` + `cluster._resolve_edge_groups`: for two non-adjacent members whose strong path needs a verified local-ID edge (labelled with `_strong_edge_labels(..., global_only=True)`), R7 applies unless they share a validated global ID. Otherwise a chain `UHID-1 –OPD– record –IPD– UHID-2` could still join them. Paths made only of validated global-ID edges keep their precedence (unchanged).
- **Reproduced first.** New `backend/tests/regression/test_phase33_pass4_remediation.py` (51 tests, invented identities only) against the unmodified snapshot: **37 of 51 fail**; the 14 that pass are positive controls. All 51 pass now. Ablation: with the resolver change removed (matcher fix only), the chained-local-ID test fails, so it is covered separately.
- **Tests (51):**
  - F1, each over table / pretty-printed `<th>` table / definition list / consecutive paragraphs / inline control:
    - owner attribution;
    - child evidence (age, Aadhaar);
    - father's Aadhaar recorded as relative-owned;
    - full pipeline: child and father get different pseudonyms.
  - F1, further cases:
    - relative gender in a table and a definition list;
    - patient-owned Aadhaar, age and gender still extracted;
    - separate `<h3>` sections;
    - a heading is still a hard boundary;
    - row separation;
    - child still links to its own record by its own Aadhaar;
    - 7 Devanagari gender cases, kin-label and longer-word negatives, and a Hindi free-text note.
  - F2:
    - `compare_profiles` CONFLICT;
    - `weak_path_conflicts` R7;
    - full pipeline not merged for a shared OPD, IPD and admission number.
  - F2 positive controls:
    - same UHID (Tier 2a);
    - shared OPD without a conflicting UHID;
    - re-registration with exact DOB + phone, with and without a shared OPD;
    - shared Aadhaar keeps Tier 1 precedence.
  - F2, further cases:
    - a chain of verified local IDs cannot join two UHIDs, with a positive control;
    - F2×F1: a father's Aadhaar in an XHTML table cannot become a global ID that outranks R7.
- **Files changed in Pass 4 (uncommitted):**
  - `backend/src/clinveil/linking/extract.py` (`_build_owner_view`, two tag patterns);
  - `backend/src/clinveil/linking/normalize.py` (two gender patterns);
  - `backend/src/clinveil/linking/matcher.py` (`compare_profiles` order, `weak_path_conflicts`, `strong_pair_conflicts`, new `r7_conflict`);
  - `backend/src/clinveil/linking/cluster.py` (global-only labels, `strong_conflict`);
  - new `backend/tests/regression/test_phase33_pass4_remediation.py`;
  - `backend/tests/regression/test_phase33_pass2_remediation.py`: `ruff format` removed one trailing blank line added after Pass 3; content is otherwise byte-identical to its pre-audit state;
  - `docs/PROJECT_HANDOFF.md`.
- **Verification actually executed (2026-11-27, exit codes in brackets):**
  - `ruff format src tests scripts ../main.py` [0]; `ruff check src tests scripts ../main.py` [0] (all checks passed); `ruff format --check …` [0] (104 files);
  - `pytest -q`: **1064 passed** (1013 earlier + 51 new) on Python **3.13.7** [0], **3.10.20** [0] and **3.12.13** [0] (offline `uv`); the 490 regression tests in `tests/regression/` all run (no skips or xfails in the Phase 3 regression files);
  - `validate_output.py`: CONTRACT OK [0]; `check_submission.py --repo . --run`: READY TO SUBMIT [0] (git status and toolkit unchanged, `6c0a85a`);
  - `check_dev.py` was **not** run in Pass 4 (it includes the organiser canary checks, which the Pass 4 brief excludes). Practice pairwise linkage from the check_dev formula (linkage counts only): **TP 6706 / FP 0 / FN 186, recall 0.9730**, identical to Pass 3;
  - same secret twice: all output files identical except `report.json` `timing` / `resources`; different secret: 53 vs 53 PSNs, 0 shared, identical partition;
  - input tree hash unchanged; 0 files left in a dedicated `TMPDIR`; neither secret appears in any output or console file;
  - 19 FHIR Bundles, 459 references, 0 unresolved;
  - logs/console vs practice entity surfaces: 0 whole-word hits (1 substring-only hit, the same 4-letter name inside "summary" as in Pass 2/3);
  - random probes: 3000 reliable-hospital datasets with mixed UHIDs and shared OPD/IPD numbers × 4 permutations: 0 order dependence, **0 clusters with two different UHIDs** (the pre-fix snapshot: 1582); Pass 3 weak-MRN probe (3000 datasets): 0 order dependence, 0 hard complete-linkage violations;
  - performance (1×): 2.39 s, 41 MiB peak RSS;
  - added lines scanned against the practice answer key: 0 identity tokens (only generic field words such as "Aadhaar", "UHID", "gender").
- **Limitations:**
  - In XHTML (as in plain text), a relative's value on the NEXT paragraph/row after the label is `ambiguous` and dropped, not attributed to the relative; a demographic reset cue at the start of the next row (`Age`, `DOB`) makes it patient-owned, as in plain text.
  - Section boundaries are tag-based (`h1`–`h6`, `hr`, `section`, `article`); a `<div>`-only layout is read as single-newline blocks.
  - R7 is still relaxed between members joined only through validated global IDs (deliberate global-ID precedence), and the DATASET.md re-registration exception (name + exact DOB + one independent corroborator) still overrides R7.
  - Practice data contains none of these adversarial patterns; the hidden dataset is untested.
- **Status:** IMPLEMENTATION COMPLETE in the working tree. **NOT committed, NOT pushed, NOT merged, and NOT independently approved. Final independent approval pending.**

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
| O12 | **Phase 3 / 3.1 / 3.2 / 3.3 not pushed/merged/approved** | Phase 2.1 merged in `9205b5a` (PR #3); Phase 3 (`32fe8fc`) and 3.1 (`4ecc67c`) are local-only on `phase-3-identity-resolution`; Phase 3.2 (F1–F9), Phase 3.3 Pass 1 (`NEW-1`–`NEW-4`), Pass 2 (`NEW-5`/`6A`/`6B`/`7A`/`7B`, `PASS1-NEW-5`/`6`/`7`) Pass 3 (`P33-F1`–`F5`) and Pass 4 (`P33-PASS3-F1`/`F2`) are uncommitted in the working tree; **final independent approval is pending** before any commit/push/merge decision. |
| O14 | **Identity-linking limits (Phase 3.3 Pass 2 + 3 + 4)** | Pass 2 closed the issuer-prefix, bridge/order and per-record reliability items; Pass 3 closed the weak-group homonym bypass, relative age/gender and facility leakage, the `E.`↔`I…` / `O.`↔`U…` initial fold and oversized-group re-entry; Pass 4 closed the XHTML ownership break and the Tier-2a R7 bypass. In XHTML, a value on the paragraph/row AFTER a relative label is `ambiguous` (dropped), as in plain text; R7 between members joined only through validated global IDs is still relaxed (global-ID precedence). Ambiguous bridges and groups above 256 clusters abstain and are frozen (precision over recall); the relative-name veto ignores relation type, so weakly linked records naming different relatives can stay split; free-text demographics with an ambiguous owner are dropped. Truly unlabelled flat CSV columns (e.g., `Patient Name, Father Name, Aadhaar` where `Aadhaar` has no ownership word) cannot be deterministically attributed from schema alone. The documented `DATASET.md` Issue C re-registration exception can still link two same-name household members at the same hospital if they share an unambiguous exact DOB and a shared family phone/ESIC/email. CPython cannot guarantee physical RAM zeroing. Practice data does not contain hidden-evaluation patterns; hidden datasets remain sealed and untested. |
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
| `python3 organiser-toolkit/check_submission.py --repo . --run` | Pre-submit check: `raksha.toml`, team name, README, no hosted-AI deps, then 3 runs: exit code, contract, same-secret determinism, different-secret sensitivity (passes with 0 warnings since Phase 3), secret never written, input unchanged. |
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
  linking/      models, normalize, extract, matcher, cluster, pseudonyms, linker (Phase 3/3.1/3.2)
  metrics/      EMPTY (Phase 6)
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
(phases, next tasks), `docs/architecture/PHASE3_IDENTITY_RESOLUTION.md`, `docs/decisions/TECHNICAL_DECISIONS.md` (D1–D36), `docs/security/THREAT_MODEL.md`,
`docs/evaluation/{BASELINE,PHASE1_INGESTION,PHASE2_DETECTION,PHASE2_REMEDIATION,PHASE3_IDENTITY_RESOLUTION,PHASE3_REMEDIATION}.md`, `docs/api-contract/README.md`,
`docs/team/README.md` (working agreement; area leads not filled in).

---

## 7. Next recommended engineering steps

1. **Final independent approval of Phase 3.3 Pass 1–4** (working tree on `4ecc67c`), then the user's commit/push/merge decision. Pass 4 is implemented but NOT independently approved.
2. **Red-team re-evaluation** of the frozen red-team dataset against the Phase 3.3 implementation (the existing analysis measured
   Phase 2 `ac37504`), adding relative-ID / household-ID / cross-hospital MRN cases and profile-aggregation (A4) measurement.
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
| 2026-11-27 | Claude Code (Opus 5.5) | Phase 3.3 Pass 4 security remediation (uncommitted working tree on `4ecc67c`, Pass 1–3 preserved). `P33-PASS3-F1`: `_build_owner_view` renders each XHTML tag run as one separator (cell/term join = space, block = newline, new section = hard boundary), so `</td><td>`, `</dt><dd>`, `</p><p>` no longer cut a relative label off from the relative's age/Aadhaar; Devanagari gender word ends fixed (`महिला`, `स्त्री`, `पुत्री`). `P33-PASS3-F2`: R7 (distinct same-issuer UHIDs, re-registration exception) checked before Tier 2a in `compare_profiles`, enforced in `weak_path_conflicts`, and applied to strong resolver paths that need a verified local ID (`strong_pair_conflicts(via_local_id=True)`); global-ID precedence kept. Files: `linking/{extract,normalize,matcher,cluster}.py`, new `test_phase33_pass4_remediation.py` (51 tests: 37 fail on the pre-fix snapshot, 51 pass now), `ruff format` of `test_phase33_pass2_remediation.py` (trailing blank line only). `pytest` 1064 passed on 3.13.7 / 3.10.20 / 3.12.13; ruff check/format exit 0 (104 files); CONTRACT OK; READY TO SUBMIT; TP 6706 / FP 0 / FN 186 (unchanged); `check_dev.py` not run (canary checks excluded by the brief). **NOT committed/pushed/merged; final independent approval pending.** |
| 2026-11-27 | Claude Code (Opus 5.5) | Phase 3.3 Pass 3 targeted remediation of the Carbon Phase 3.3 audit findings `P33-F1`–`F5` (uncommitted working tree on `4ecc67c`, Pass 1/2 preserved). F1: weak-only paths inside identifier groups use `weak_path_conflicts` on strong sub-component profiles (homonym, R7, complete-linkage vetoes), so a partial record cannot bridge homonyms. F2: free-text/FHIR-narrative ages and genders only when patient-owned. F3: relative-owned facility containers ignored. F4: bare initials keep their written vowel (`initial_key`). F5: oversized and wholly abstaining groups are frozen. Files: `linking/{cluster,matcher,extract,normalize}.py`, new `test_phase33_pass3_remediation.py` (66 tests: 46 fail on the pre-fix snapshot, 66 pass now). `pytest` 1013 passed on 3.13.7 / 3.10.20 / 3.12.13; ruff exit 0; CONTRACT OK; `check_dev` P 1.00 / R 0.97, 0 wrongly merged; TP 6706 / FP 0 / FN 186 (unchanged); READY TO SUBMIT. A first F1 variant (plain `compare_profiles` between lone members) was measured at recall 0.92 and replaced. **NOT committed/pushed/merged; final independent audit pending.** |
| 2026-11-27 | Claude Code (Opus 5.5) | Phase 3.3 Pass 2 final remediation (uncommitted working tree on `4ecc67c`, preserving Gemini Pass 1 and the interrupted Antigravity session as found). Fixed `PASS1-NEW-5` (issuer prefix for reliable scopes), `PASS1-NEW-6` (set-based group resolver: complete linkage, bridge abstention frozen across stages, C2 co-attachment conflicts, `conflict_name_fragment`), `PASS1-NEW-7` / `NEW-5` (document-scope reliability per record, nested facility paths, aggregator/referral exclusion, multi-facility ambiguity), `NEW-6A` (locator-driven contract parsing), `NEW-6B` (full `has_any_evidence`, partial FHIR Patients), `NEW-7A` (E/O initials, kept vowel initials), `NEW-7B` (multiple ABHA addresses). New `test_phase33_pass2_remediation.py` (62 tests): 40 fail on a rebuild of the Pass 1 code, 62 pass now. `pytest` 947 passed on 3.13.7 / 3.10.20 / 3.12.13; ruff exit 0; CONTRACT OK; `check_dev` P 1.00 / R 0.97, 0 wrongly merged; READY TO SUBMIT. Carbon audit and Gemini Pass 1 report files not found in the repo. **NOT committed/pushed/merged; Carbon independent approval pending.** |
| 2026-11-27 | Antigravity | Phase 3.3, Pass 1 critical identity-resolution remediation on `phase-3-identity-resolution` (uncommitted working tree on top of `4ecc67c`), fixing the four High-severity findings (`NEW-1`–`NEW-4`) from the independent Phase 3.2 audit (`PHASE3_2_INDEPENDENT_SECURITY_AUDIT.md`, verdict REJECT). Reproduced first: 30 new synthetic test cases in `backend/tests/regression/test_phase32_adversarial_remediation.py` gave 20 failed before the fix; now 73/73 pass. Fixed `NEW-1` (relative-owned split-name isolation, `if not is_rel_field:` demographic guards, and `_consume_findings` ownership checks on `PATIENT_NAME`/`DOB`/`VILLAGE`/`PIN`), `NEW-2` (dotted title/initial sentence-period filtering, compound relational phrase matching in `_KIN_CUE_RE` with `_non_kin_patient_cues` span exclusion, and decoded ownership view `_build_owner_view` for XHTML and HTML-entity/`\uXXXX`/`%XX` text), `NEW-3` (generic register words in `_HOSPITAL_STOP`, parent directory hospital inference in `_infer_document_hospital_inner`, external-lab-to-hospital requirement on generic MRNs, and Stage B competing-candidate ambiguity protection in `_merge_from_blocks`), and `NEW-4` (`_tokens_phonetically_compatible` primary vowel preservation blocking `Kiran`/`Karan`, `Alok`/`Alka`, `Sunil`/`Sonal` and conflicting 3-token middle names `Anil Kumar`/`Anil Prakash` while preserving transliteration, schwa, `-eya` suffixes, 1-char medial vowel elision `Zarina`/`Zarna`, middle-name omission, and initials). Files changed in Pass 1: `linking/{extract,normalize,matcher,cluster}.py`, `tests/regression/test_phase32_adversarial_remediation.py`, `docs/PROJECT_HANDOFF.md`. Run: `pytest` 885 passed on Python 3.13.7 (24.83 s), 3.10.20 (22.37 s), and 3.12.13 (20.10 s); `ruff check` & `ruff format --check` exit 0 (101 files); `validate_output.py` CONTRACT OK; `check_dev.py` exit 0 (0/3230 leaked, 0/4 canaries, 4855/4855 medical values, linking P 1.00 / R 0.96 / F0.5 0.99, 0 wrongly merged, 0 raw copies); `check_submission.py --repo . --run` READY TO SUBMIT (exit 0, 2.5 s, 0 warnings). Open for Pass 2: `NEW-5`, `NEW-6`, `NEW-7`. NOT committed, NOT pushed, NOT merged, and NOT yet complete or independently approved. |
| 2026-11-27 | Antigravity | Phase 3.2 adversarial remediation on `phase-3-identity-resolution` (uncommitted working tree on top of `4ecc67c`), addressing findings F1–F9 from the independent Phase 3.1 audit (`PHASE3_1_INDEPENDENT_SECURITY_AUDIT.md`, verdict REJECT). Reproduced first: new `backend/tests/regression/test_phase32_adversarial_remediation.py` gave 36 failed / 7 passed on `4ecc67c`; now 43/43 pass. Fixed F1 (per-MRN reliable provenance, `is_true_external_lab_only`, homonym/complete-linkage/R7 enforcement on unverified/external MRNs), F2 (complete-linkage full-name conflict check preventing abbreviated-name bridges), F3 (per-`Patient` independent FHIR Bundle inspection and ambiguity abstention), F4 (`RelatedPerson` narrative & ABHA-address/PAN handling, `emergency_contact`/`contact_person`/`family`-ID containers, expanded Hindi/Hinglish/English kinship cues, comma/newline-preserving clause ownership with patient-cue reset), F5 (per-record `_FACILITY_LABELS` attribution without Row 0 inheritance), F6 (unambiguous exact DOB + non-DOB-derived independent corroborators for R7, `conflict_abha_address`, unreliable-stem `issuer_pfx:` R7), F7 (multi-branch city distinction & initialled/generic hospital normalisation), F8 (content-based contract locator fallback + `issued_pseudonyms` scoping), and F9 (`DateEvidence` pickle refusal, `RecordEvidence.__repr__` raw-loc redaction, `names.py` period/colon boundary fix, same-key collision telemetry). Files changed: `linking/{models,normalize,extract,matcher,pseudonyms}.py`, `detection/names.py`, `validation/contract.py`, `pipeline.py`, `tests/regression/test_phase32_adversarial_remediation.py`, `docs/PROJECT_HANDOFF.md`. Run: `pytest` 855 passed on Python 3.13.7 (21.65 s), 3.10.20 (21.01 s), and 3.12.13 (19.17 s); `ruff check` & `ruff format --check` exit 0 (101 files); `validate_output.py` CONTRACT OK (exit 0); `check_dev.py` exit 0 (0/3230 leaked, 0/4 canaries, 4855/4855 medical values, linking P 1.00 / R 0.98 / F0.5 1.00, 0 wrongly merged, 0 raw copies); `check_submission.py --repo . --run` READY TO SUBMIT (exit 0, 2.3 s, 0 warnings); determinism, different-secret (0/51 shared PSNs, identical partition), input immutability, empty `TMPDIR`, and 19 FHIR Bundles (0 unresolved refs) all verified. NOT committed, NOT pushed, NOT merged, and NOT yet independently approved. Next: independent Phase 3.2 re-audit. |
| 2026-11-27 | Claude Opus 5.5 | Phase 3.1 false-merge remediation on `phase-3-identity-resolution`, committed locally on top of `32fe8fc`. Reproduced first: the new `test_phase31_false_merges.py` gave 23 failed / 18 passed on `32fe8fc`; now 46/46. Fixed R1–R7 (identifier ownership plus a relative-ID veto; insurance/e-mail as corroborators; whole-name compatibility under global IDs; reliable-hospital cross-hospital guard; typed digit cores; same-issuer MRN rule with the documented re-registration exception), complete-linkage weak-merge vetoes, capped-block abstention, per-record pseudonym self-check, pseudonym bit-selection docs, and per-file link index. Run: pytest 812 passed on Python 3.10.20 / 3.12.13 / 3.13.7; ruff exit 0; `validate_output.py` / `check_dev.py` / `check_submission.py --run` exit 0 (READY, no warnings); practice TP 6,803 / FP 0 / FN 89, P 1.0000 / R 0.9871 / F0.5 0.9974, 0 wrong merges; 1× 2.28 s / 41 MB, 10× 22.4 s / 126 MB. Regressions: none found. Not pushed or merged. Next: fresh independent audit, then the red-team re-evaluation. |
| 2026-11-27 | Antigravity | Implemented Phase 3 (cross-hospital patient identity resolution and cryptographic pseudonymisation) on branch `phase-3-identity-resolution` from `9205b5a`. Added modular `linking/` package (`models.py`, `normalize.py`, `extract.py`, `matcher.py`, `cluster.py`, `pseudonyms.py`, `linker.py`), domain-separated versioned HMAC-SHA256 (`psn|v1|...`) with collision counter in `privacy/pseudonym.py`, single-patient JSON report locator handling in `parsing/json_format.py`, schema-preserving in-record pseudonym insertion in `sanitization/processors.py`, two-pass pipeline wiring in `pipeline.py`, pre-exit pseudonym consistency check in `validation/contract.py`, cache registration in `detection/caches.py`, and synthetic/adversarial tests (`tests/unit/test_linking.py`, `tests/integration/test_phase3_identity_resolution.py`). Removed `xfail` on `test_different_secret_changes_output`. Run: `ruff check` / `ruff format --check` exit 0 (99 files); `pytest` 766 passed / 0 xfailed across Python 3.10, 3.12, and 3.13; `validate_output.py` CONTRACT OK; `check_dev.py` 0/3230 leaked, 0/4 canaries, 4855/4855 probes, linking precision 1.00 / recall 0.99 / F0.5 1.00 / 0 wrong merges; `check_submission.py --run` READY TO SUBMIT (0 warnings); 1× 2.1 s / 37.9 MB RSS, 10× 22.4 s / 113.7 MB RSS. Not pushed or merged. Next: user review/push/merge of Phase 3, then Phase 4 privacy transformations. |
| 2026-11-27 | Antigravity | Fixed Python 3.10 GitHub Actions CI failure blocking PR #3 (`phase-2.1-remediation` → `main`), committed locally on top of `fab12fb`. Root cause: `organiser-toolkit/dev/input/misc/deep_export.json` (1,500-level nested JSON) triggers `RecursionError` in CPython 3.10 `json.loads()`, which was uncaught in `backend/scripts/dev_eval.py` (`Parsed.__init__` only suppressed `ValueError`). Files changed: `backend/scripts/dev_eval.py`, `backend/tests/regression/test_phase2_release.py`, new `backend/tests/unit/test_dev_eval.py`, `docs/evaluation/PHASE2_REMEDIATION.md` (§9), this file. Run: `ruff check` / `ruff format --check` exit 0 (91 files); `pytest` 745 passed / 1 xfailed on Python 3.10 (`uv`), Python 3.12 (`uv`), and local `.venv` (Python 3.13); Python 3.10 `validate_output.py` (CONTRACT OK), `check_dev.py` (0/3230, 0/4 canaries, 4855/4855), `dev_eval.py` (0.0/3226, 0/8 canaries, 98.8% probes, 99.8% retention), same-secret determinism, and `check_submission.py --repo . --run` (READY, known E5 warning) all exit 0. Regressions: none. Not pushed or merged. Next: user pushes CI fix to PR #3 and merges, then Phase 3 linking. |
| 2026-11-26 | Claude Opus 5.5 | Phase 2.1 final review fixes F1–F4, committed on top of `e6021fa` (the handoff commit created in the entry below). The review file was not present in the repo; findings taken from the task description and reproduced first (15 of 30 new tests failed on `e6021fa`, all 30 pass now). Files changed: `ingestion/discovery.py`, `pipeline.py`, `parsing/attachments.py`, `sanitization/processors.py`, `detection/views.py`, new `tests/regression/test_phase21_final_review.py`, docs (`PHASE2_REMEDIATION.md` §8, this file, `THREAT_MODEL.md`, `README.md`, `PHASE2_DETECTION.md`, `IMPLEMENTATION_PLAN.md`). Run: pytest 741 passed / 1 xfailed; ruff exit 0; `validate_output.py`, `check_dev.py`, `check_submission.py --run` exit 0 (READY, known E5 warning); practice output byte-identical to Phase 2. Regressions: none found. Outstanding decisions: push/merge; O1 symlink trade-off. Next: Phase 3 linking. |
| 2026-11-26 | Claude Sonnet 5.5 | Created this handoff (commit `e6021fa`). Read-only with respect to production code. Verified: branch `phase-2.1-remediation`, HEAD `5a242ab`, `main`=`origin/main`=`ac37504`, Phase 2.1 unpushed; `pytest` 711 passed / 1 xfailed; `ruff check` and `ruff format --check` clean. Not re-run for this entry: the official scripts (figures in §3 come from the preceding verification session). Could not verify: official score (sealed evaluator), Phase 2 commit's own test count, Phase 0/1 numbers (taken from repo docs). The file existed beforehand as an empty untracked placeholder. |
| 2026-11-26 | Claude Opus 5.5 | Phase 2.1: `683074f` audit remediation; `5a242ab` final security-verification fixes (S1–S5). Tests then: 711 passed, 1 xfailed; official checks passed (see §3). Details in `docs/evaluation/PHASE2_REMEDIATION.md`. |
| 2026-11-26 | Claude Opus 5.5 | Phase 2 `53ec8ff` (merged `ac37504`); Phase 1 `d2c4b31` (merged `643c95f`); licensing correction `7934185`; Phase 0 `59c0ea8`. |
