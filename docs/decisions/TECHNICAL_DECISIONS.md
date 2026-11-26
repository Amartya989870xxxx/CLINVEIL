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

## D11. Licence: MIT **[NEEDS APPROVAL]**
- Matches the organiser kit. The repository is public and the event requires original work.

## D12. Team name in `raksha.toml` is "CLINVEIL" **[NEEDS APPROVAL]**
- `check_submission.py` rejects the placeholder. Set this to the registered team name if it differs.
