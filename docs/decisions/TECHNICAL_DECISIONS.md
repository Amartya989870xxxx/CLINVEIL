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

## D8. Domain-separated, versioned HMAC-SHA256 pseudonyms with collision protection (updated in Phase 3)
- `PSN-` plus 6 Crockford base32 characters from `HMAC-SHA256(RAKSHA_SECRET, "psn|v1|" + canonical_cluster_key)`
  (30 bits). The date shift uses `HMAC-SHA256(RAKSHA_SECRET, "shift|" + patient_key)`.
- Domain separation (`psn|v1|`) and deterministic counter re-derivation (`|#<attempt>`) were implemented in
  Phase 3 (`privacy/pseudonym.py`, `linking/pseudonyms.py`), guaranteeing zero pseudonym collisions between
  distinct clusters even at large scale and full traversal-order independence.

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

## D23. Preserved fields are guarded, never skipped (Phase 2.1)
A semantic class such as *clinical*, *doctor*, *relation* or *date* used to switch detection off for the
field. The audit showed PII inside such fields leaked (a mis-classified `Diet` column, non-Patient FHIR
notes). Now no semantic disables detection. Preserved fields keep their value but still lose:
- validated identifiers;
- names behind explicit cues;
- names next to phone numbers;
- exact run-confirmed values.

Doctor/staff/organisation fields never take name propagation, and short digit cores are not evidence
inside an ID field. Cost: about +25% runtime on the practice set. The practice output is unchanged.

## D24. Label classification by purity, with restricted fuzzy matching (Phase 2.1)
A label gets a PII class only if all of its tokens belong to that class (plus neutral modifiers such as
`Patient`, `No`, `Primary`, `by`). Fuzzy correction applies only to 6+ letter words at edit distance 1
towards distinctive PII words; shorter words only get an adjacent-letter swap (`Nmae`). This trades a few
exotic misspellings for never turning `urea`, `Diet`, `Mode`, `cell_count` or `birth_weight` into PII.

## D25. Decoded views instead of pre-decoding the input (Phase 2.1)
HTML entities, XHTML markup and %-escapes are decoded *per field for detection only*, with an exact
character map back to the original. The output keeps its original encoding and markup; only the detected
spans are replaced, split at tag boundaries. Pre-decoding the whole file would have changed bytes the
scorer compares (schema, format validity) and broken XHTML.

## D26. Binary attachments are withheld, not quarantined with their container (Phase 2.1)
A scan or photo cannot be sanitised, but quarantining a whole FHIR Bundle for one attachment loses every
other resource. The `data` member is removed (optional in R4), so the Bundle stays valid and is
exported. Inside text, the payload becomes `[ATTACHMENT-WITHHELD]`. Invalid declared payloads still
quarantine the file.

## D27. Coarse key for redaction, strict key for linking (Phase 2.1)
`translit.name_key` is recall-oriented: a collision such as `Kiran`/`Karan` costs at most an
over-redaction. `translit.name_key_strict` keeps vowel qualities and is the key Phase 3 must use, together
with corroborating identifiers (D7), because a false merge corrupts two patients' records.

## D28. Escaping symlinks are never opened; their path gets a declared placeholder (Phase 2.1)
Reading a target outside the input root, even only to hash it and even under a size cap, lets an input
tree make the process read arbitrary files (secrets, FIFOs, devices). The official contract, however,
identifies inputs by the SHA-256 of the bytes behind the path, and `validate_output.py` fails a run in
which an input path is neither exported nor declared. We therefore export an empty, content-free
placeholder at the (filename-sanitised) path, declared `suppressed` with reason
`symlink_outside_input` under a non-identifying synthetic id. The validator accepts this with one WARN.
The one residual conflict is a link whose own filename holds PII: the placeholder is renamed and cannot be
declared without the target's hash, so the validator reports one undeclared input. Privacy and no-read
win over that error. All other reads open the verified real path with `O_NOFOLLOW | O_NONBLOCK` and require
a regular file.

## D29. Schema-preserving in-record pseudonym placement (Phase 3)
`SPEC.md` §6 and `SCORING.md` §5 require each linked pseudonym in `records.jsonl` to appear inside the
exported record while preserving CSV column counts, JSON key paths and value types, FHIR R4 structure, and
text line counts. Rather than appending new columns or JSON keys (which breaks schema preservation), CLINVEIL
places `PSN-XXXXXX` into one existing patient-identifier or patient-name string slot per linked record
(`UHID`/`patient_ref` cell, JSON string MRN/name field, FHIR `Patient.identifier.value`, or the first `MRN`/
`PATIENT_NAME` span in text; text-only fallback prepends `Patient: PSN-XXXXXX\n` only when no in-body span
exists). Single-patient JSON reports containing a top-level `patient` object and sub-lists like `panels` are
enumerated as `doc` in `parsing/json_format.py`.

## D30. Hospital-scoped local MRNs and 3-stage conflict-aware clustering (Phase 3)
Local identifiers (`MRN`, `UHID`, `IPD`, registration numbers) are namespaced by their inferred issuing
hospital scope (`hosp:<slug>`) unless carrying a distinctive non-generic hospital prefix, so identical
numeric/generic MRNs issued by two different hospitals (`Hospital-A / MRN-12345` vs `Hospital-B / MRN-12345`)
never merge. Clustering runs in three bounded-block stages (validated global IDs → hospital-scoped MRNs →
corroborated full names + unique fragmented singleton attachments), re-checking cluster-level hard conflicts
(disjoint global IDs, gender, DOB, age > 3, incompatible names, relative/village/district homonym vetoes)
before every merge so weak similarities can never transitively bridge conflicting clusters.

## D31. Order-independent canonical cluster keys (Phase 3)
Each resolved cluster's HMAC input key is built strictly from its sorted normalised identity evidence
(`aadhaar` > `abha` > `abhaa` > `pan` > `mrn` > `demo`; insurance and e-mail removed in 3.1, see D33), never from file traversal order or
temporary cluster indices. Cleartext evidence, clusters, and canonical keys are discarded in memory right
after pseudonym assignment and never logged or serialised.

## D32. Identifier ownership: patient, relative or ambiguous (Phase 3.1)
An identifier's position inside a patient record does not make it the patient's. A relative-labelled field
(`Father Aadhaar`, `पिता आधार`, `Guardian UID`), a relative JSON container (`guardian: {aadhaar}`), FHIR
`RelatedPerson.identifier`, or a kinship cue in the value's own text segment (`Husband's Aadhaar …`,
`Aadhaar of husband: …`, `पति का आधार …`) makes it the relative's. A relation marker in that segment
(`W/o <Name> Aadhaar …`) makes the owner ambiguous, and the value is not used. Relative-owned person-unique IDs
are kept apart and serve only as a veto: if one record's own ID is another record's relative ID, they are
different people. Trade-off: some patient-owned IDs written after a relation marker are no longer used (recall),
in exchange for never merging relatives.

## D33. Insurance and e-mail are corroborators, not identities (Phase 3.1)
ESIC, PMJAY and other family policy IDs, and household e-mail addresses, are routinely shared by several
people. They now corroborate a matching full name (like phone or DOB) and never trigger a merge on their own.
They are not used as canonical pseudonym key material.

## D34. Reliable issuers and typed identifiers (Phase 3.1)
The same MRN string from two *reliably known* hospitals is no evidence of identity, whatever its prefix.
"Reliable" means one of:
- a FHIR system or Organization;
- a facility field;
- a letterhead;
- a file name containing a hospital word;
- a file-stem slug corroborated by one of the above elsewhere in the run.

Guesses from other file stems (`master`, `nursing_adm900001`) still namespace MRNs, but cannot prove "different
issuer". Two-letter and hospital-type prefixes (UH, GH, DH, CHC, PHC) are not issuer-distinctive. Digit cores
carry an identifier type (patient / admission / visit / prefix), so an IPD number never matches a UHID by suffix.

## D35. Same-issuer MRN rule with the documented re-registration exception (Phase 3.1)
Different patient MRNs from the same issuer usually mean different patients and block weak merges. `DATASET.md`
states that "some re-register at the same hospital with a new ID", and the practice data contains such a case,
so this is not an absolute veto. A full-name match with an exact DOB plus at least one more independent
corroborator still links. Rejected alternative: a hard veto, which split a correct practice cluster.

## D36. Complete-linkage vetoes and abstention for weak merges (Phase 3.1)
Cluster evidence is the union of its members, and "closest value" vetoes become more permissive as a cluster
grows. Merges that rest only on names and corroborators therefore require every member pair to agree (age span
≤ 3, birth-year span ≤ 1, compatible DOBs, one gender). Strong-ID merges keep per-visit tolerance. A full-name
block above the cap is a dense homonym group: its members abstain from name-based merging instead of being
reached through phone or DOB blocks.

