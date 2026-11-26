# Phase 2.1: remediation of the independent Phase 2 audit

Branch `phase-2.1-remediation`, from `ac37504` (Phase 2 merged). This document maps every finding of the
independent code and security audit of Phase 2 ("Gemini 4 Carbon" audit) to what we reproduced, the root
cause, the fix, the regression test and the measured result. It is honest about what is only partly
fixed or deferred.

**About the audit file.** The audit report is at `docs/research/GEMINI_PHASE2_CODE_SECURITY_AUDIT.md`
in the working tree. It is **deliberately not committed**: it quotes practice-dataset canary names and
practice patient first names, and practice answer-key material must not enter the repository. If the team
wants it versioned, commit a redacted copy (canary and patient names replaced by placeholders) instead.
Nothing below quotes practice values. All test identities are invented.

## 1. Method

1. **Reproduce first.** `backend/tests/regression/test_phase21_audit.py` was written from the audit text
   and run against the unmodified Phase 2 code (`ac37504`) before any fix: **85 failed, 10 passed**
   (95 tests; the suite has since grown to 102 with regressions for issues found during remediation).
   Each failure was then inspected to separate a real reproduction from a test that failed
   only because a new interface did not exist yet (C4 strict key, E2 cache registry). Those two were
   verified directly instead (`cache_info()` after a run; key collisions printed). Findings that do not
   reproduce are reported as such, and their tests stay as guards.
2. **Fix the root cause, not the example.** Every fix is structural (a classification rule, a decoding
   layer, an ordering change), not a word added for one test sentence.
3. **Generalise.** A new, independent adversarial generator (`tests/generalization/adversarial.py`, 7
   attack classes × 25 seeds) uses its own syllable inventory, unseen FHIR resources, unseen clinical
   columns, other digit scripts and encodings. On the original Phase 2 code it fails **125 / 175** cases.
   On Phase 2.1 it passes **175 / 175**. It found two further real bugs during this phase (§4).
4. **Re-measure everything** on the practice data with the official, unmodified tools and the rewritten
   `dev_eval.py`, and compare Phase 1, Phase 2 and Phase 2.1 on identical inputs (§5).

Classification vocabulary: **Confirmed and reproduced** · **Partially reproduced** · **Not reproduced** ·
**Already fixed** · **Deferred with justification**.

## 2. Summary

| ID | Finding | Classification | Status after 2.1 |
|---|---|---|---|
| M | dev evaluator approximations; protection count 96 vs 55 | Confirmed and reproduced | fixed (evaluator rewritten, doc corrected to 55) |
| B1 | non-Patient FHIR free text treated as clinical and skipped | Confirmed and reproduced | fixed |
| B2 | address regex eats XHTML markup; entities hide PII | Confirmed and reproduced | fixed |
| B3 | fuzzy labels map to PRESERVED semantics, so no detection runs | Confirmed and reproduced | fixed |
| B4 | %-encoding, non-Devanagari digits, URL-safe / short base64 | Partially reproduced (URL-safe: corruption, not a leak; declared digit-only base64 already handled) | fixed |
| C1 | patient name *before* S/o, W/o, पत्नी missed; royal/Sikh tokens generic | Confirmed and reproduced | fixed |
| C2 | contiguous ABHA and STD landlines missed | Confirmed and reproduced (no false-positive part reproduced) | fixed |
| C3 | `Dr. Md. Tarif` etc. lose protection; local propagation before protection | Partially reproduced (`Dr. Shri …`, lower-case `dr.` were fine) | fixed |
| C4 | transliteration gaps; phonetic collisions | Confirmed and reproduced | gaps fixed; collisions addressed by a new strict key (coarse key kept by design) |
| C5 | phone-adjacent always RELATIVE; timeline always PATIENT | Confirmed and reproduced (with a different root cause, see below) | fixed; WhatsApp sender role deferred |
| C6 | FHIR ids / fullUrls / references embed hospital IDs | Confirmed and reproduced | fixed (coordinated rewrite) |
| D1 | clinical columns classified as PII and seeding the index | Confirmed and reproduced (34 of 40 audit labels) | fixed |
| D2 | `C/O Left …` treated as care-of and seeded | Confirmed and reproduced | fixed |
| D3 | Devanagari names swallow clinical words | Confirmed and reproduced | fixed |
| D4 | assorted false positives; binary attachment quarantines a Bundle | Confirmed and reproduced (all eight sub-items) | fixed |
| E1 | report counts unchanged values; generalised > processed | Confirmed and reproduced | fixed |
| E2 | memo caches retain input fragments after a run | Confirmed (verified directly) | fixed |
| E3 | escaping symlink targets hashed; broken symlinks dropped | Partially reproduced | partly fixed; hashing kept (contract-constrained, evidence below) |
| E4 | quadratic resolution; double parse | Partially reproduced (resolver yes; end-to-end at 6k findings no) | resolver fixed; two-pass parse kept by design |
| E5 | `RAKSHA_SECRET` unused | Confirmed | deferred to Phase 3/4 (by design) |
| F1 | gazetteer depleted to 47 surnames | Confirmed | accepted (contamination removal), documented |
| F2 | missing tests | Confirmed | 102 audit regressions + 175 adversarial + resolver equivalence tests |

## 3. Finding by finding

Paths are relative to `backend/src/clinveil/`. Tests are in `backend/tests/` (`R` =
`regression/test_phase21_audit.py`, `A` = `generalization/test_phase21_adversarial.py`).

### M. Measurement and evaluator notes
- **Reproduced:** yes. The old `scripts/dev_eval.py` searched the whole file, ignored numbers and 1–2
  letter words in retention, let placeholder words count as retained tokens, skipped canaries, and
  checked probes anywhere in the file. `PHASE2_DETECTION.md` said 96 candidates were protected. The
  committed Phase 2 code reports **55** (`logs/detection_summary.json`, re-run on `ac37504`).
- **Fix:** `dev_eval.py` rewritten to mirror `organiser-toolkit/docs/SCORING.md`:
  - record-level units with whole-file fallback;
  - `allowed` / `pii_occ` / clamped fractional leak per key;
  - base64 (standard and URL-safe), hex, `\uXXXX`, HTML-entity and %-decoding;
  - homoglyph folding, and Indic digits in every script;
  - canaries scored;
  - field-level probes (1.0 / 0.8 / 0);
  - all-token retention with dates, ages, PII and placeholder words excluded.

  The doc now says 55.
- **Limitations:** still an approximation (record location for `@file` falls back to the whole file).
  The independence concern about `synth.py` is answered by the new adversarial generator, which shares no
  vocabulary with it.

### B1. Non-Patient FHIR resources
- **Where:** `detection/engine.py::_fhir_semantic`.
- **Reproduced:** yes (`R::test_B1_*`): note, conclusion, title, description and `subscriberId` leaked.
- **Root cause:** the fallback returned `CLINICAL` for every non-Patient element, and `CLINICAL` was a
  *skip-detection* semantic.
- **Fix:**
  - Any remaining element of any resource is free text (detectors run; clinical keep spans protect
    medical content).
  - Code and enumeration keys (`system`, `code`, `unit`, `status`, `intent`…) are *guarded* (B3), not
    skipped.
  - `resourceType` is the only fully structural key.
  - `subscriberId` is INSURANCE_ID.
- **Result:** `R::test_B1` passes, as do 25 seeds of `A::fhir_unseen_resources`: Procedure,
  Immunization, ServiceRequest, CarePlan, AllergyIntolerance and Communication, with references still
  resolving.

### B2. XHTML narrative
- **Where:** `detection/addresses.py::ADDRESS_LABEL_RE`, new `detection/views.py`, `engine.analyze`.
- **Reproduced:** yes. `Address: …</p></div>` was consumed up to the line end, producing invalid XHTML.
  Entity-encoded names and digits were not seen.
- **Fix:**
  - A *decoded view* layer for values containing markup, HTML character references or %-escapes.
  - Detectors run on the decoded text, where each tag becomes a line break.
  - Every hit is mapped back to exact original offsets and split at tag boundaries, so markup and
    escaping survive.
  - `ADDRESS_LABEL_RE` also stops at `<`.
- **Result:** the output parses with ElementTree, keeps `xmlns`, and `&amp;` stays escaped (`R::test_B2_*`).

### B3. PRESERVED bypass
- **Where:** `semantics.PRESERVED`, `engine._detect_field`.
- **Reproduced:** yes. A `Diet`/`Mode` column (fuzzy matches of `dist`/`code`) containing
  `S/o Kelvan Vexpal 98…` leaked.
- **Root cause:** preserved semantics skipped *all* detection.
- **Fix:** preserved fields are now **guarded**. Their value is kept, but inside it the engine still
  removes:
  - validated identifiers (phone, Aadhaar, ABHA, e-mail, PAN, insurance, labelled MRN, landline);
  - names behind explicit cues (`S/o`, `brought by`, `Name:`, patient-before-marker);
  - names next to a phone number;
  - exact run-confirmed values.

  Two guards limit false positives:
  - Doctor, staff and organisation fields never take name propagation.
  - A bare MRN *digit core* is not evidence inside a guarded ID. A visit number such as
    `OPD/…/00418` shares digits with some MRN by chance. This was found by diffing the practice output
    and pinned by `R::test_B3_guarded_ids_do_not_take_mrn_digit_cores`.

  A cheap pre-filter skips values that cannot hold an identifier (one word, short numbers). The fuzzy
  matcher itself is fixed under D1.

### B4. Encoded and Indic channels
- **Where:**
  - `detection/text.py` (`UNICODE_DIGITS`);
  - `detection/identifiers.py::_scan`;
  - `detection/views.py` (%-decoding);
  - `parsing/attachments.py`;
  - `sanitization/processors.py::_reencode`.
- **Reproduced:**
  - %-encoded path: yes.
  - Bengali, Gurmukhi, Gujarati, Tamil and Telugu digits: yes (5/5). The generator later added
    full-width, Kannada, Malayalam and Odia, which also failed on Phase 2.
  - URL-safe base64: **partially**. Phase 2 split the token at `-`/`_` and decoded and re-encoded the
    standard-alphabet fragments. Over 305 random URL-safe payloads carrying a labelled name and phone,
    no PII stayed recoverable, but **28 (9%) were corrupted** into undecodable base64 (an integrity and
    utility defect). The original reproduction test for this item failed for a different reason: its
    name had no cue (`Referral for <Name>`), a recall limitation that is unrelated to encoding and still
    exists (§6). The test now uses a labelled name, and a property test pins decodability
    (`R::test_B4_url_safe_payloads_stay_decodable_and_clean`, fails on Phase 2, passes now).
  - Short undeclared digit-only base64: yes (a bare 10-digit number is a 14-character run, below the
    old 24-character minimum).
  - Declared digit-only base64: **not reproduced** (already handled).
- **Fix:**
  - Every Unicode decimal digit is folded to ASCII. This is length-preserving, so offsets stay exact.
  - Percent-escapes are decoded in the view layer.
  - The URL-safe alphabet is accepted and re-encoded URL-safe.
  - Runs of 12+ characters count when they decode to an identifier-length number (8+ digits);
    24+-character runs still need clean text.
- **Limitations:** hex and `\uXXXX` encodings inside *text* are not decoded by the engine (the scorer
  does decode them; JSON `\u` escapes are already decoded by the JSON parser). Nested base64 is not scanned.

### C1. Name before the relationship marker
- **Where:** `detection/names.py::detect_names`, `lexicon.GENERIC_NAME_TOKENS`.
- **Reproduced:** yes, ×3.
- **Fix:**
  - After `S/o`, `D/o`, `W/o`, `son/daughter/wife of` and the Devanagari relation words, the name
    *before* the marker (comma allowed) is the patient (`name_before_relation`).
  - `rani raja kunwar nath das chand` are no longer generic: they are given names.
- **Generator-found bug:** the Devanagari relation regex's lookahead `(?!का|की|के)` also rejected every
  name *starting* with के (केशव). It now only excludes the particles. Pinned by
  `R::test_C1_devanagari_names_starting_with_ka_ki_ke…`.

### C2. ABHA and landlines
- **Where:** `identifiers.ABHA_LABEL_RE`, `identifiers.LANDLINE_RE`.
- **Reproduced:** all 6 positives; **no** false-positive case reproduced (ranges, counts and times were
  already fine).
- **Fix:**
  - A labelled 14-digit ABHA (contiguous or grouped).
  - STD landlines `0XX(X)-NNNNNN(NN)` and `(0522) 2234567`: 0.92 with a label, 0.75 without (redacted,
    never seeded).
- **Result:** positives removed; negatives unchanged.

### C3. Doctor protection order
- **Where:** `clinical.py` (`_NAMEPART`, doctor patterns), `engine._doc_local_propagation`.
- **Reproduced:** `Dr. Md. Tarif`, `Dr. Mohd. Zuvair`, `चिकित्सक: केलवन`, `डॉक्टर: अरुण` (yes).
  `Dr. Shri Kelvan` and lower-case `dr. kelvan` were **not reproduced**.
- **Root cause:**
  - Multi-letter abbreviations (`Md.`) ended the doctor span.
  - Hindi doctor labels were missing.
  - Document-local propagation was seeded from hits inside doctor spans.
- **Fix:**
  - Name parts accept a trailing period.
  - `डॉक्टर` and `चिकित्सक` labels added; the longest alternative is matched first.
  - Hits inside doctor keep spans never seed local propagation.
  - Contextual weak cues (`care_of`, possessive, timeline, loose names) never seed it either.
- **Generator-found regression in my own fix:** making name parts case-insensitive let `Dr. X Y saw
  Makita` extend over the sentence and hide a patient. Name parts are capitalised again, and a separate
  one-word pattern handles all-lower-case notes. Pinned by `R::test_C3_doctor_span_does_not_swallow…`.

### C4. Transliteration
- **Where:** `detection/translit.py`.
- **Reproduced:**
  - `ज्ञान` → `jn`, which did not match `Gyan` → `gn`.
  - `Umar` ≠ `Omar`, `Ishaan` ≠ `Eshaan`, `Bimla` ≠ `Vimla`.
  - Collisions `Kiran`/`Karan` = `krn`, `Sita`/`Satya` = `st`, `Alok`/`Alka` = `alk` (printed directly).
- **Fix:**
  - ज्ञ → `gy`; an initial vowel is one class; b/v fold.
  - New `name_key_strict` keeps vowel qualities (Kiran ≠ Karan, Neeta = Nita = नीता) **for Phase 3
    linking**.
- **Why the coarse key still collides:** `name_key` is the *redaction* key, where a collision costs at
  most an over-redaction and a miss costs a leak. Linking must use the strict key and corroborating
  identifiers (D7).

### C5. Patient vs relative roles
- **Where:** `engine._names_near_phones`, `engine._phone_owner_role`, `names._timeline_role`.
- **Reproduced:** yes, with a **different root cause** than stated. `Tarun Vexpal, Mob: 98…` produced
  *no* name finding at all, because the phone-keyword group was case-sensitive (`Mob` never matched).
  With lower-case `mob`, the role was always RELATIVE.
- **Fix:**
  - The keyword match is case-insensitive.
  - The role comes from cues:
    - relative words around the name (`Attendant`, `W/o`, `(relative, bed 4)`, `brought by`) give
      RELATIVE;
    - a name opening its line or followed by patient cues (`admitted`, `aged`) gives PATIENT;
    - otherwise the conservative default is RELATIVE.
  - Timeline lines become RELATIVE when the line says so.
- **Deferred:** WhatsApp senders stay RELATIVE. The sender's role cannot be decided from the line, and the
  placeholder type does not change leak scoring. Phase 3 can re-type with record context.

### C6. FHIR ids carrying hospital IDs
- **Where:** `engine._fhir_id_hits`, `sanitization/processors.py::fhir_id_rewrites`.
- **Reproduced:** yes. `Patient/UHID-004417` survived in `id`, `fullUrl` and `reference`.
- **Fix:**
  - An id segment (not a UUID) carrying a 5+ digit run, an ID-shaped token or a run-confirmed value is
    flagged.
  - The sanitiser rewrites the entry's `id` to `rid-<entry>`, its `fullUrl` (same base, or a `urn:uuid`
    derived only from the entry index), and every reference that resolved to it, so the Bundle still
    resolves.
  - A flagged reference that resolved to nothing gets `rid-x<n>`.
- **Result:** `R::test_C6` (valid id, references resolve, UUIDs untouched).

### D1. Clinical columns classified as PII
- **Where:** `semantics.py` (`classify_label`, `_fuzzy`), `engine.seed`.
- **Reproduced:** yes. 34 of the audit's 40 labels were PII semantics: `urea`→`area`,
  `cell_count`→PHONE, `birth_weight`→DOB, `mother_tongue`→RELATIVE, `Disease Name`→PERSON. Their values
  seeded the run-wide index.
- **Root cause:**
  - Any single PII word anywhere in a label decided the class.
  - Fuzzy matching ran on every 4+ letter word towards every vocabulary word.
- **Fix:**
  - **Purity rule:** a PII class is assigned only if *all* label tokens belong to that class plus neutral
    modifiers (`Patient`, `No`, `Primary`, `by`…), so `Patient Mobile No` is PHONE but `cell_count` is not.
  - `<X> Name` is a person only when X is a person word; with a clinical X it is clinical.
  - Location labels may carry note, line or details qualifiers (`address_note`). That regression was
    caught on the practice data and pinned by a unit test.
  - Fuzzy matching only applies to 6+ letter words at distance 1, towards distinctive PII words. Short
    words are only corrected by an adjacent swap (`Nmae`).
  - Seeds are validated per type: a name seed must be person-shaped.
- **Self-check:** all 199 distinct practice headers and keys were classified with the old and the new code
  and the 23 changes reviewed. Two recall risks (`by_name`/`by_uhid` mapping containers; bare
  `first`/`last`/`given`) were restored.

### D2. `C/O` complaint vs care-of
- **Where:** `names.detect_names`, `lexicon.SEVERITY_WORDS`, `ANATOMY_WORDS`.
- **Reproduced:** yes. `C/O Left knee pain` redacted `Left` and seeded it.
- **Fix:**
  - `C/O` followed by a complaint, severity, anatomy or procedure word is a complaint.
  - `C/O <Name>` is a new non-strong `care_of` detector that never seeds the run-wide or local index.
    Address fields still remove it.

### D3. Devanagari over-consumption
- **Where:** `names._is_name_token`, `lexicon.DEVA_CLINICAL_WORDS`, `value_index._NON_IDENTIFYING`.
- **Reproduced:** ×6.
- **Fix:** a Devanagari name stops at clinical words, function words and known places (compared on
  normalised keys, so nukta variants match). These words are also never indexed.

### D4. Assorted false positives and binary attachments
- **Reproduced:** all eight sub-items.
- **Fixes:**
  - **Timelines:** `14:00 - Blood Transfusion started` is an action. Procedure or anatomy words, or a
    following action verb, mean it is not a name.
  - **Eponyms:** `Crohn's`, `Cushing's` (`EPONYM_ROOTS`) are never possessive names.
  - **Hardware:** `fixator pin: 210045` is not a PIN (orthopaedic hardware context).
  - **12-digit numbers:** a contiguous 12-digit number with no Verhoeff checksum and no Aadhaar label is
    not an Aadhaar. A checksum-valid one next to `Serial/Batch/Lot…` is not either.
  - **Districts:** Devanagari UP districts and major states and cities are kept as places (`KNOWN_PLACES`).
  - **Date-shaped codes:** `LAB-20261015`, `Batch-202601` in filenames and headers are not IDs.
  - **Schema keys:** `Blood Group` under `patient` stays a schema key, because the purity rule no longer
    lets `patient` + anything be a person.
  - **Binary attachments:** a binary FHIR attachment is **withheld** instead of quarantining the Bundle.
    Its `data` member is removed (optional in FHIR R4); `contentType` and the rest stay. In text, a
    binary payload becomes `[ATTACHMENT-WITHHELD]`. The count is reported as `attachments_withheld` in
    `logs/detection_summary.json`.

### E1. Honest report counts
- **Where:** `sanitization/processors.py` (`effective`, `RunStats.generalized_in`), `engine.analyze`.
- **Reproduced:** yes. An unchanged `birthDate: "1980"` was counted, and DOB 3 ≠ changed 2.
- **Fix:**
  - Only findings whose replacement changes the text are counted.
  - `records_generalized` counts distinct records.
  - Base64 parents are masked before document-local propagation (no stray hits inside payloads).
  - Sub-threshold candidates are recorded (`candidates_below_threshold`).

### E2. Caches
- **Where:** new `detection/caches.py`, `pipeline.run`.
- **Verified directly** on Phase 2: after one run, `normalize_token` held 7 entries, `name_key` and
  `latin_name_form` 250, plus the label caches. These contain input fragments (patient names).
- **Fix:** a registry of every memo cache, cleared in a `finally` around the run (also on failure).
- **Test:** `R::test_E2` (0 entries after `run()`).

### E3. Symlinks
- **Where:** `ingestion/discovery.py`, `pipeline.py`, `security/errors.py`.
- **Reproduced:**
  - The escaping target's SHA-256 appears in `report.json`: yes.
  - The target was hashed before the size cap: yes (code).
  - Broken symlinks were silently skipped by `is_file()`: yes.
- **Fix:**
  - Broken symlinks are reported as quarantined `broken_symlink` (SHA-256 of zero bytes).
  - An escaping target is stream-hashed only if it is a regular file within `max_file_bytes`;
    otherwise it is not read at all.
  - Targets are never parsed, exported or used for seeding.
- **Why the hash stays:** the official contract identifies inputs by the SHA-256 of the bytes behind the
  path. We verified it with the official validator on an escaping link:
  - target hashed: `CONTRACT OK`;
  - hash replaced: `ERROR 1 input files are neither exported (same path) nor declared in report.files`.

  Dropping the hash would therefore fail validation. The hash reveals no content beyond what the contract
  already exposes for every input file. Note also that `validate_output.py` itself crashes
  (`FileNotFoundError`) on an input folder containing a dangling symlink. That is outside our control.
- **Test:** `R::test_E3_escaping_and_broken_symlinks`.

### E4. Performance
- **Where:** `detection/resolve.py`.
- **Reproduced:** the resolver was quadratic (16,000 hits: 10.0 s, measured directly). The audit's
  end-to-end scale (6,000 name/phone pairs) did **not** exceed 20 s.
- **Fix:** sorted keep spans plus bisection, and a sorted disjoint list of accepted spans. 64,000 hits
  now take 0.1 s. A property test checks 3,000 random inputs against the original algorithm
  (`unit/test_resolve_scaling.py`).
- **Not changed:** the double parse. Two passes re-read files so memory stays flat (D18); documents are
  not held between passes.

### E5. `RAKSHA_SECRET` unused
- **Confirmed.** The secret is required (exit 2 without it) but only Phase 3 pseudonyms and Phase 4 date
  shifts use it.
- **Deferred:** different secrets currently give identical sanitised output (measured), because nothing
  secret-dependent is written yet.

### F1. Gazetteer size
- **Confirmed.** 198 given names and 47 surnames remain after removing every practice-overlapping token
  (Phase 2 contamination check).
- **Accepted:** the gazetteer is weak evidence by design (0.75 pair; single token 0.60, never redacted).
  Context, structure and propagation carry detection. Re-growing it from public sources is a Phase 6 option.

## 4. Issues found during remediation (not in the audit)

1. **Case-sensitive phone keyword** (C5 root cause): `Mob:` never matched the name-near-phone rule.
2. **URL-safe payload corruption** (B4): the real Phase 2 defect was corrupted payloads, not a leak.
3. **Devanagari relation lookahead** rejected names starting with का/की/के. Found by the adversarial
   generator.
4. **Over-broad doctor span** introduced by my own first C3 fix. Found by the generator, fixed before commit.
5. **`address_note` demoted to free text** by the new purity rule. Found on the practice data, fixed
   before commit.
6. **Visit numbers sharing an MRN digit core** redacted in guarded fields. Found by diffing practice
   outputs, fixed before commit.

## 5. Measured results

Practice data (200 files), identical inputs, `RAKSHA_SECRET` fixed. "Official tools" are the
organiser's unmodified scripts. The `dev_eval` rows use the rewritten Phase 2.1 evaluator for all three
versions.

| Metric | Phase 1 (`643c95f`) | Phase 2 (`ac37504`) | Phase 2.1 |
|---|---:|---:|---:|
| `validate_output.py` | OK | OK | **OK** |
| `check_dev.py` PII still visible | 2714 / 3230 | 0 / 3230 | **0 / 3230** |
| `dev_eval` record-level fractional leak | 2684.2 / 3226 (83.2%) | 0 / 3226 | **0 / 3226** |
| `dev_eval` leak by script (deva / hinglish / latin) | 96.5 / 93.7 / 82.2% | 0 / 0 / 0% | **0 / 0 / 0%** |
| canaries leaked (`dev_eval`, 8 mentions) | 4 / 8 | 0 / 8 | **0 / 8** |
| preserve probes, field-level weighted | 98.8% | 98.8% | **98.8%** |
| non-PII token retention (all tokens) | 99.5% | 99.8% | **99.8%** |
| findings / protected by clinical rules | n/a | 3350 / 55 | **3350 / 55** |
| runtime, 200 files / peak RSS | 0.34 s / 28 MB | 1.66 s / 33 MB | **2.1 s / 32 MB** |
| runtime, 2,000 files (10×) / peak RSS | n/a | 13.9 s / 38 MB | **19.8 s / 39 MB** |
| adversarial generator (7 classes × 25 seeds) | n/a | 50 / 175 pass | **175 / 175 pass** |

- **Practice output unchanged.** The Phase 2.1 sanitised practice output is **byte-identical** to Phase 2
  (`diff -r`). All remediation changes act on patterns the practice set does not contain. This is the
  expected outcome for a generalisation fix; it also means the practice set cannot show the gains, which
  is why the adversarial generator exists.
- **Probe artifacts.** Probes at 98.8% are identical for Phase 1, which redacted nothing. The "elsewhere"
  and "lost" probe counts are evaluator approximations, not losses caused by sanitisation.
- **Runtime.** The extra time (+25% at 1×) comes from guarded detection of preserved fields (B3), the
  price of not skipping them. It is linear, with flat memory.
- **Other checks** (all measured):
  - two runs with the same secret give identical `sanitized/`, `records.jsonl`, `logs/` and `report.json`
    (excluding timing and resources);
  - the input tree hash is unchanged;
  - nothing is written to `TMPDIR`;
  - no PII surface appears as a whole word in `report.json`, `records.jsonl`, `logs/`, stdout/stderr or
    output paths;
  - the memo caches are empty after the run.
- **Tests:** 695 passed, 1 xfailed (the pre-existing, documented Phase 3 xfail); `ruff check` and
  `ruff format --check` are clean.

## 6. What is still open

- Free-text names with **no cue at all** that never appear in a structured field (unchanged from Phase 2).
- Hex and `\uXXXX`-encoded PII inside plain text; nested base64.
- WhatsApp sender role (C5); phonetic-key collisions in the coarse key (by design, C4).
- E3 target hashing (contract-constrained); E5 (Phase 3/4); F1 gazetteer size.
- The adversarial generator, like `synth.py`, was written by the team that wrote the engine. It is
  broader and independent of the practice vocabulary, but it is not a substitute for the sealed dataset.
