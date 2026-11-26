# Technical decisions

Format: decision, rationale, trade-off. **[NEEDS APPROVAL]** marks a choice a human should confirm.

## D1. Evaluator entry point at the repository root, code under `backend/`
- **Decision:** `raksha.toml`, `main.py`, `requirements.txt` and `config/policy.yaml` live at the root.
  `main.py` is a shim that prepends `backend/src` to `sys.path`.
- **Why:** SPEC §1 requires `raksha.toml` at the root (`check_submission.py`: "a sub-folder does not
  count"), and `run` executes in the root. The requested `backend/` layout is kept for maintainability.
- **Trade-off:** a `sys.path` shim instead of an installed package. It is robust, because no install step
  can fail offline. `pip install -e backend` is still supported for development.
- **Discrepancy noted:** the bootstrap brief placed the CLI in `backend/`; the official contract wins.

## D2. Standard library only at runtime (Phase 0)
- **Why:** zero install risk in an offline sandbox, and full control over determinism. The starter
  is stdlib-only.
- **Policy for additions:** each runtime dependency needs a scoring justification, an upper-bounded pin
  in **both** `requirements.txt` and `backend/pyproject.toml`, an offline wheel available on Linux,
  and an entry in the README. Candidates to evaluate when needed: `rapidfuzz` (fuzzy matching, C
  speed), `jellyfish` (phonetics), `indic-transliteration` (Devanagari↔Latin).
- **Rejected:** spaCy and transformer NER (Indian-name and Hinglish coverage is poor, the models are
  large, and there is a 50M-parameter limit), Presidio (statement: off-the-shelf PII tools "score poorly"),
  any LLM (banned).

## D3. Behaviour-preserving refactor first, pinned by a byte-parity test
- **Why:** proves the integration did not break the contract before any scoring work starts. The test runs
  the *real* starter from the toolkit.
- **Trade-off:** the test must be deleted deliberately when output is meant to change (Phase 1).

## D4. Fail closed without `RAKSHA_SECRET` (exit 2)
- **Why:** an empty HMAC key makes pseudonyms an unkeyed function of patient keys. The evaluator always
  sets the variable (SPEC §2), so this never triggers in an official run.
- **Trade-off:** the starter silently ran with an empty key; we refuse.

## D5. Quarantine reasons are allowlisted codes or exception type names
- **Why:** the starter wrote `str(ValueError)` when it looked like an identifier. A message such as
  `ValueError("<name>")` would leak into `report.json`, which is scanned.
- **Effect on parity:** none on the practice data (same three reasons).

## D6. Typed `Finding` separates detection from sanitisation
- **Why:** lets several detectors vote (confidence, method), resolves overlaps once, and keeps
  "keep" decisions (doctor, dose) explicit and testable. `surface` is excluded from `repr`.

## D7. Conservative linking with abstention
- **Why:** scoring uses pairwise F0.5 (precision weighted 2×); ambiguous records cost nothing when
  `null`; homonym separation is scored. Weak evidence must never chain transitively.

## D8. Pseudonym and date-shift derivation kept identical to the starter
- `PSN-` plus 6 Crockford base32 characters from HMAC-SHA256 (30 bits). The shift is HMAC over `"shift|"+key`.
- **Known nit:** the pseudonym derivation has no domain-separation prefix. It is harmless because cluster
  keys never start with `shift|`, but the next change should add `"psn|"` (it changes every pseudonym,
  so do it together with Phase 3).
- 30 bits gives about 1e9 codes. The birthday collision probability for 10k patients is about 5%. **Phase 3 must
  detect pseudonym collisions between distinct clusters and re-derive with a counter suffix**.

## D9. No intermediate files
- **Why:** `TMPDIR` and `HOME` are scanned for PII after the run. In-memory processing fits the budget
  (practice: about 40 MB). If spilling ever becomes necessary: AES-GCM with an ephemeral key held only
  in memory, which requires adding `cryptography` (see D2).

## D10. Frontend and demo API are strictly optional **[NEEDS APPROVAL]**
- Proposed stack: Vite + React + TypeScript, no UI kit beyond a small headless library. The demo API is
  read-only over a finished output directory (a stdlib `http.server` or FastAPI as an optional `[demo]`
  extra; neither is ever in `requirements.txt`).

## D11. No project-wide open-source licence (decided 2026-11-26; supersedes "MIT")
- **Decision:** the root MIT `LICENSE` from the bootstrap commit was removed. Original CLINVEIL material is
  under default copyright (all rights reserved). Third-party portions adapted from the organiser starter
  keep their MIT licence, reproduced verbatim in `third_party_licenses/` and mapped file by file in
  `THIRD_PARTY_NOTICES.md`. Each adapted source file carries a header comment.
- **Why:** the team does not want to grant general reuse, redistribution or derivative rights.
- **Limitation:** commit `59c0ea8` was already public with an MIT `LICENSE`. History was not rewritten
  (no amend, reset or force-push), so that commit and its licence file remain visible.
- `backend/pyproject.toml` declares no licence and carries `Private :: Do Not Upload`, so it cannot be
  published to PyPI by accident.

## D12. Team name in `raksha.toml` is "APEX" (decided 2026-11-26)
- APEX is the registered team name. CLINVEIL remains the product name in code, docs and branding.

## D13. Common IR: typed fields over the parsed structure (Phase 1)
- **Decision:** every format parses into `Document{source, records, fields, native, fhir}`. A `Field` has
  a unique address, structural path, owning record, channel, kind, label, FHIR context and base64
  segments. Sanitisation maps `address → new value`, and a per-format renderer rebuilds the file from `native`.
- **Why:** Phase 2 detectors work on one representation with channel and record context, and output keeps
  its structure. Flattening to text would lose headers, keys, pointers and FHIR roles.
- **Trade-off:** one Python object per value. Measured memory stays flat (each file's IR is freed after
  rendering), but one very large CSV or JSON costs several times its size. JSON is capped at 64 MiB.

## D14. Content beats extension; the extension is supporting evidence (Phase 1)
- Order: signature → decode and plausibility → JSON-first for `{`/`[` → markup → `.csv`/`.tsv` delimiter
  sniffing → text. A failed JSON parse degrades to text only for text-like or unknown extensions, and to
  CSV only with real tabular evidence (≥ 2 columns, ≥ 2 rows, ≥ 80% consistent). Otherwise it is quarantined.
- Unknown extensions with plausible text content are processed as text rather than quarantined, to keep
  utility on unseen formats. The output stays text at the same path.

## D15. Explicit, stable limits and reason codes (Phase 1)
- JSON depth 64 (practice peak 11; trap 1,502), 64 MiB, 2M nodes; decoded attachment 16 MiB; file 256 MiB.
  All are configurable in `config/policy.yaml`. The raised recursion limit was removed: depth is checked
  linearly *before* `json.loads`.
- Reason codes replace exception names for every expected failure (`invalid_json` instead of `JSONDecodeError`).

## D16. Base64 payloads (Phase 1)
- Declared payloads (data-like key + content-type sibling + base64 shape) must decode. Undeclared runs
  (24+ chars) count only if they decode to clean, printable UTF-8 text, so URLs, hashes and tokens are ignored.
- A payload is decoded, transformed and re-encoded (padding preserved). An unchanged payload keeps its
  original bytes. Binary or invalid payloads **quarantine the whole file**. This is simpler and safe;
  withholding only the payload (keeping FHIR valid) is a Phase 5 refinement.
- One level only: base64 inside decoded base64 is not scanned.

## D17. Deterministic, layered detection; no statistical NER model (Phase 2)
- **Decision:** rules over semantic fields, validated patterns, contextual cues, self-authored lexicons and
  run-wide propagation. No CRF or transformer.
- **Why:** offline/CPU/50M-parameter limits; explainable findings; measured 0/3230 leak with 100% preserve-probe
  survival on practice data and 0/1200 on unseen-style generated data. A small CRF remains an option if
  hidden-data feedback shows cue-less free-text names.

## D18. Two-pass pipeline with a run-local Sensitive Value Index (Phase 2)
- Pass 1 seeds only FIELD_SEMANTICS / LABEL / VALIDATED_PATTERN evidence (≥ 0.88). Pass 2 matches token
  sequences, phonetic full names, identifying single tokens and digit cores in every channel.
- Files are re-read in pass 2 (flat memory) instead of keeping all documents. The index is never serialised.
- Ablation: propagation removes the last 1.3% of practice leaks.

## D19. Offsets-only findings and typed placeholders (Phase 2)
- `Finding` holds offsets into the original field value, never the text. Placeholders are deterministic
  `[TYPE]` tokens (bare words in filenames). JSON numbers become `0` so value types are preserved.

## D20. DOB interim treatment (Phase 2)
- DOB → `[DOB]`. FHIR `birthDate` → birth year (the only non-identifying value that keeps the element a valid
  FHIR `date`). Phase 4 replaces both with per-patient shifted dates. No other date is touched in Phase 2.

## D21. Schema labels are never redacted; values in labels are (Phase 2)
- A header or key is rewritten only when it carries a value (ID-shaped token, confirmed name, dynamic key in a
  mapping). Duplicated rewritten headers get a ` #n` suffix and JSON key collisions a `~n` suffix, so no data is lost.

## D22. Starter regex removed (Phase 2)
- `detection/baseline_regex.py` (starter `PATTERNS`, verbatim) is deleted. `identifiers.py` rewrites the idea
  with validation and is recorded as "adapted" in `THIRD_PARTY_NOTICES.md` (conservative attribution).
