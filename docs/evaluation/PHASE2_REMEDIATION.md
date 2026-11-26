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
| E3 | escaping symlink targets hashed; broken symlinks dropped | Partially reproduced | fixed in the final verification (§7, S1): targets are never opened; one documented contract conflict remains |
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
- **Limitations (updated in §8, F3):** `\uXXXX` escapes in text are now decoded; hex encodings inside *text* are still not decoded by the engine (the scorer
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
    The exact behaviour (after the final verification, §7 S2) is:
    - **Object members** that are entirely a binary payload are removed: `Attachment.data`,
      `Binary.data` and an undeclared binary `valueBase64Binary` (all 0..1 in R4). For a declared
      attachment, `hash` and `size` are removed too. `contentType`, `title`, `url`, ids and references
      stay.
    - **Array elements** keep their slot as the string `"[ATTACHMENT-WITHHELD]"`, so lengths and
      positions do not change.
    - **Inside text**, the payload span is replaced the same way.
    - **Text attachments** are decoded, cleaned and re-encoded, never withheld.
    - **Invalid declared payloads** still quarantine the file.

    The count is reported as `attachments_withheld` in `logs/detection_summary.json`.

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
- **Where:** `ingestion/discovery.py`, `pipeline.py`, `parsing/builder.py`, `export/release.py`.
- **Reproduced:**
  - The escaping target's SHA-256 appears in `report.json`: yes.
  - The target was hashed before the size cap: yes (code).
  - Broken symlinks were silently skipped by `is_file()`: yes.
- **First fix (in `683074f`), superseded:** the target was still stream-hashed when it was a regular file
  within the size cap. The final verification showed this still **opens the external target** (§7, S1).
- **Final behaviour:** see §7, S1. The target is never opened; broken links and special files are
  reported, not dropped.
- **Tests:**
  - `R::test_E3_escaping_and_broken_symlinks`;
  - `security/test_symlink_no_dereference.py`;
  - `security/test_channels_and_boundaries.py::test_symlink_escaping_input_is_never_read`.

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
- **Tests:** 711 passed, 1 xfailed after the final verification (§7) (the xfail is the pre-existing,
  documented Phase 3 one); `ruff check` and `ruff format --check` are clean.

## 6. What is still open

- Free-text names with **no cue at all** that never appear in a structured field (unchanged from Phase 2).
- Hex-encoded PII inside plain text; nested base64. (`\uXXXX` in plain text is decoded since §8, F3.)
- WhatsApp sender role (C5); phonetic-key collisions in the coarse key (by design, C4).
- E3/S1 contract conflict for an escaping symlink whose **own filename** holds PII (§7); E5 (Phase 3/4);
  F1 gazetteer size.
- The adversarial generator, like `synth.py`, was written by the team that wrote the engine. It is
  broader and independent of the practice vocabulary, but it is not a substitute for the sealed dataset.

## 7. Final security verification (after `683074f`)

A second, independent pass checked the remediation itself before push. It found five issues. All are
fixed in the follow-up commit and pinned by tests. Everything below was run, not inferred.

### S1. Escaping symlink targets were still opened (fixed)
- **Verified:** a Python audit hook recorded every `open` during a run. In `683074f`, `escape.txt` (a
  link to a file outside the input root) **was opened**: the target was read to hash it. The size cap
  only bounded how much was read.
- **Fix:** every input read now goes through `ingestion/discovery.py::read_input` / `sha256_input`:
  - the path is resolved and must lie inside the input root;
  - the real path is opened with `O_NOFOLLOW | O_NONBLOCK`;
  - `fstat` on the descriptor must show a regular file.

  Discovery classifies entries with `lstat` and symlink resolution only (metadata, never content).
- **Escaping link:** never opened, not even to hash it.
  - The release covers its path with an **empty, content-free placeholder** (`{}` for `.json`). The
    path still goes through filename detection and renaming.
  - It is declared `status: "suppressed"`, `reason: "symlink_outside_input"`.
  - Its id is a **non-identifying synthetic id** (`unread_id`: SHA-256 of the discovery ordinal),
    because its bytes are never read.
- **Broken link:** `quarantined` / `broken_symlink`, with a synthetic id.
- **Internal link:** read through its verified real path and exported normally.
- **Special files:** a FIFO, socket or device inside the root used to be dropped silently. It is now
  `quarantined` / `not_a_regular_file` and never opened (S5).
- **Verified with the audit hook:** links to an external regular file, to an external FIFO and to a
  missing target are never opened. The run does not block on the FIFO.
- **Official contract:**
  - `validate_output.py` gives `CONTRACT OK` for a release with escaping and internal links. Its only
    complaint is a WARN that the synthetic id matches no input file. Its silent-drop check is satisfied
    because the path is exported.
  - `files_quarantined` now counts only `quarantined` entries (a `suppressed` placeholder is neither
    sanitised nor quarantined).
- **Remaining conflict (documented, tested):** if an escaping link's **own filename** holds PII, the
  placeholder is renamed. Without the target's SHA-256 the rename cannot be declared, so
  `validate_output.py` reports exactly `ERROR 1 input files are neither exported (same path) nor
  declared`. We chose privacy plus no-read over that one contract error:
  `security/test_symlink_no_dereference.py::test_pii_named_escaping_link_trades_one_contract_error_for_privacy`.
- **Out of our control:** the official validator itself reads link targets. It blocks forever on a link
  to a FIFO and crashes on a dangling link.
- **Not covered:** hard links to files outside the root are indistinguishable from regular files.
  Directory components swapped for symlinks *during* a run (TOCTOU on intermediate directories) are not
  defended against; the final component is (`O_NOFOLLOW`). The input copy is read-only by assumption.

### S2. Binary withholding shrank JSON arrays and kept the image fingerprint (fixed)
- **Verified:** in a non-FHIR JSON, `["<jpeg>", "keep me", "<pdf>"]` became `["keep me"]`, which shifts
  positions and record locators. A withheld FHIR photo kept `Attachment.hash` (a SHA-1 of the image,
  usable to confirm a known photo) and `size`.
- **Fix:** array elements become `"[ATTACHMENT-WITHHELD]"` (the renderer no longer removes array
  elements at all), and withholding a declared attachment's `data` also removes its `hash` and `size`.
- **Verified FHIR structure** (`integration/test_attachment_withholding.py`):
  - entry count, resource types and ids are unchanged, and references resolve;
  - `Binary` keeps `contentType` (1..1);
  - every remaining `data` is valid base64 with a `contentType`;
  - the text attachment is cleaned and still valid base64.

  The official FHIR scorer is sealed, so this is a structural check, not the organisers' R4 validator.

### S3 (P1). `Test Name: Hemoglobin` seeded a clinical value as a patient (fixed; pre-existing in Phase 2)
- **Verified:** a bare `Name:` label preceded by a clinical, organisation or file word seeded the value
  into the run-wide index as a patient name:
  - examples: `Test Name:`, `Drug Name:`, `Disease Name:`, `Hospital Name:`, `Organism Name:`,
    `File Name:`, `दवा का नाम:`;
  - values seeded: hemoglobin, paracetamol, typhoid, klebsiella, arogya…;
  - the same values seed on `ac37504`.
- **Fix:** the two-word label is classified with the header classifier. A non-person result disables
  the patient-label rule; an unknown qualifier keeps it (recall).
- **First fix was quadratic:** my first version searched from the line start for every label, making a
  single-line note with 6,000 labels take minutes. The look-back is now bounded to 60 characters (E4
  timing back to 6.0 s, the same as `683074f`).

### S4 (P2). Weakly classified fields seeded the index (fixed; pre-existing in Phase 2)
- **Verified:** keys such as `family`, `given`, `client` or `holder` alone (semantic confidence below
  0.8) seeded their values ("Diabetes mellitus", "Insulin", "Walk-in", "Self"), because structured hits
  had a 0.9 confidence floor whatever the semantic confidence.
- **Fix:** such hits are still redacted in place but use the `field_weak` detector, which never seeds.

### S5. Special files silently dropped (fixed)
Covered under S1.

### Privacy-accuracy verification (`regression/test_phase21_privacy_accuracy.py`)
- Clinical free-text labels, clinical CSV columns, care-of and timeline lines, eponyms and weak fields
  seed **nothing**.
- Clinician names from CSV columns, `Consultant:` / `Doctor:` lines and FHIR `Practitioner` never enter
  the index, and stay unredacted elsewhere.
- None of these values propagate to another file. Confirmed patient names, phones and MRNs still
  propagate (recall guard).

### Git safety
The whole Phase 2.1 diff against `ac37504` (3,400 added lines) was checked:
- **No secrets** (key/token patterns).
- **No organiser material tracked** (toolkit, truth file, attacker fixtures, outputs).
- **No answer-key value:** practice name tokens, digit keys and exact keys all give 0 hits.
- **Attacker fixtures:** 1,021 values checked; the only matches are schema words and the generic term
  "typhoid fever".
- **Verbatim practice input lines** (≥ 25 chars): only FHIR boilerplate (`"resourceType": …`,
  `"system": "http://loinc.org"`) plus one practice **resource UUID** in a test. It is not PII, but it is
  practice data, so it was replaced by an invented UUID. The same UUID is also in the published Phase 1
  test `unit/test_attachments.py` (in pushed history, which is not rewritten); it is replaced there going
  forward too.
- The audit report stays untracked.

### Re-measured after the fixes
- **Official tools:**
  - `validate_output.py`: CONTRACT OK;
  - `check_dev.py`: 0/3230 leaked, 0/4 canaries, 4855/4855 probes, 0 raw copies;
  - `check_submission.py --run`: READY, with the known E5 warning only.
- **Practice output** is still byte-identical to Phase 2.
- **Same-secret determinism** holds, and the input tree is unchanged.
- **Side channels:** `TMPDIR` stays empty. No whole-word PII surface or key appears in the report,
  `records.jsonl`, logs, stdout/stderr or output paths. The memo caches are empty after a run.
- **Performance:** 2.1 s / 32 MB for 200 files; 20.2 s / 39 MB for 2,000 files.

## 8. Final review: four findings (F1–F4)

An independent final review (by "Gemini 4 Neon") approved Phase 2.1 with minor changes and reported four
findings. **The review file itself was not in the repository** when this work was done: `docs/research/`
contained only the original audit, and a search of the working tree found no other review file. The four
findings below were taken from the user's task description, which states each one concretely, and **each was
reproduced independently** against `e6021fa` before any change. `regression/test_phase21_final_review.py` was
written first and run on the unmodified code: **15 failed, 15 passed** (the passing ones are guard cases, such
as short PDF/JPEG payloads that the signature check already withheld). After the fixes: **30 passed**.

### F1. Empty `input_sha256` after a failed read (fixed)
- **Reproduced:** an internal symlink to a FIFO was reported with `"input_sha256": ""`.
- **Root cause:**
  - discovery checked only that an internal link stays inside the root, not that its target is a regular file;
  - the pipeline's failure path left the digest empty whenever the read failed before hashing (not a
    regular file, vanished, changed, I/O error).
- **Fix:**
  - an internal link to a FIFO/socket/device is flagged as special during discovery (metadata `stat` only,
    never opened) and reported `not_a_regular_file`;
  - in the failure path, an empty digest is replaced by the existing non-identifying `unread_id(f)`, derived
    from the discovery position only.

  External links are still never dereferenced or hashed.
- **Tests** (an internal link to a regular file is still read and exported):
  - internal link to a FIFO, external link to a FIFO, broken link, oversized file, internal link to a
    regular file;
  - a file vanishing between discovery and read;
  - a read error during the read.
- **Result:** no discovered entry has an empty identifier, and the practice run has 0 empty entries.

### F2. Attachment `hash`/`size` and short binary payloads (fixed)
- **Reproduced:**
  - (A) a text attachment was cleaned and re-encoded but kept its original `hash` and `size`, which
    fingerprint the PII-bearing original;
  - (B) a binary payload withheld without a `contentType` kept `hash`/`size`;
  - (C) short declared payloads under 16 base64 characters (`application/octet-stream`, the start of a PNG)
    passed through raw.
- **Root cause:**
  - metadata was dropped only for a *withheld* payload that had a *declared* type;
  - short declared values that did not decode as clean text were treated as ordinary strings whatever the
    declared type.
- **Fix:**
  - whenever a payload member (`data`, `payload`, `base64`, `blob`, `file`, `attachment`, `*Base64Binary`) is
    rewritten or withheld, its sibling `hash` and `size` are removed, with or without `contentType`;
  - an unchanged attachment keeps its metadata;
  - a short base64 value that decodes under a **binary** declaration (anything except `text/*` and JSON/XML/CSV-like
    `application/*` types) is withheld;
  - with no declaration, or a text declaration, short strings (`pending`, codes) stay ordinary strings;
  - a long, impossible base64 value under a declaration still quarantines (`invalid_attachment`);
  - an empty payload is unchanged.
- **Preserved:** `contentType`, `title`, references, and array positions (array elements become
  `"[ATTACHMENT-WITHHELD]"`).
- **Tests:**
  - text attachment with `hash`/`size`; unchanged text attachment;
  - binary with and without `contentType`;
  - short `octet-stream`, PNG, PDF and JPEG payloads; short undeclared strings;
  - empty and invalid payloads;
  - several attachments in one resource inside a FHIR Bundle (references resolve);
  - JSON arrays.

### F3. Percent-encoded values in spaced text, and `\uXXXX` (fixed)
- **Reproduced:** `Exported from /exports/Orvila%20Tamsen/report.json` became `…/[NAME]%20Tamsen/…`, so the
  surname leaked. `\uXXXX` escapes in plain text were not decoded at all.
- **Root cause:** the decoded view only decoded %-escapes when the whole value had no whitespace or
  contained `://`.
- **Fix (`detection/views.py`):** inside spaced text, a %-run is decoded only with evidence that it is an
  escape:
  - its whitespace-delimited token is path/URL/query-like (`/ \ ? = &`);
  - or the token holds two or more escapes;
  - or the escape sits between letters/digits.

  Bytes that are not valid printable UTF-8 are left as written (no replacement characters), so unrelated
  percent signs (`98%`, `20%off`, `100%ABx`, `%ZZ`) are never touched.
- **`\uXXXX`:** implemented, because it fits the same exact offset map in one bounded linear pass. Surrogate
  pairs are joined; lone surrogates and control characters are not decoded. A detected value is replaced at
  its exact encoded source span (`…/exports/[NAME]/report.json`). Text without findings is unchanged.
- **Still not decoded:** hex encodings inside text (ambiguous with hashes and IDs).
- **Tests:**
  - names, digits and encoded slashes in paths;
  - Windows paths; an encoded space between words; URL metadata fields;
  - unrelated and invalid percent signs, unchanged;
  - exact-span replacement;
  - `\uXXXX` with surrogate safety, and a Windows path `C:\users` left alone.

### F4. Zero-valued JSON numbers counted as redactions (fixed)
- **Reproduced:** `{"pin": 0, "uhid": 0}` stayed unchanged but added 2 to `identifiers_detected` and
  `entities`.
- **Root cause:** a numeric finding was counted before checking that replacing it with `0` changed anything.
- **Fix:** a PII number that is already `0` (`0` or `0.0`) is neither replaced nor counted. Detections
  (`logs/detection_summary.json` `findings_total`) stay separate from applied transformations (`report.json`).
- **Tests:**
  - zero-valued fields;
  - non-zero numbers replaced by `0` (type kept) and counted;
  - string identifiers;
  - unchanged vs changed FHIR `birthDate` generalisation;
  - the `entities` counts.

### Validation after F1–F4 (all run, 2026-11-26)
| Command | Exit | Result |
|---|---:|---|
| `cd backend && ../.venv/bin/python -m pytest -q` | 0 | 741 passed, 1 xfailed (the documented Phase 3 xfail) |
| `ruff check src tests scripts ../main.py` / `ruff format --check src tests scripts` | 0 / 0 | clean / 89 files formatted |
| `backend/scripts/official_checks.sh --submit` | 0 | runs the three official scripts below |
| `organiser-toolkit/validate_output.py --input organiser-toolkit/dev/input --output OUT` | 0 | CONTRACT OK |
| `organiser-toolkit/check_dev.py --output OUT` | 0 | 0/3230 visible, 0/4 canaries, 4855/4855 medical values, 0 raw copies |
| `organiser-toolkit/check_submission.py --repo . --run` | 0 | READY; one known warning (different secret → identical output, E5/O8) |

- Practice `sanitized/` is byte-identical to Phase 2, and `report.json` has 0 empty identifiers.
- Same-secret determinism holds (sanitized, records, logs, and the report excluding timing/resources) and
  the input tree is unchanged.
- `TMPDIR` stays empty; there are 0 whole-word PII surfaces or keys in the report, `records.jsonl`, logs,
  stdout/stderr or output paths.
- `dev_eval.py`: 0/3226 leak, 0/8 canaries, probes 98.8%, retention 99.8%.
- **Performance:** 200 files 2.35 s / 32 MB, 2,000 files 22.2 s / 40 MB, both CONTRACT OK. Timed back to back
  against `e6021fa` on the same machine, the difference is within noise (2.33–2.38 s for both).

Practice data contains none of these patterns, so its output does not change. The fixes are evidenced by the
reproduction tests. Not changed: the documented open issues in §6.

## 9. Python 3.10 CI failure fix (after `fab12fb`)

GitHub Actions run `45877028053` on PR #3 (`phase-2.1-remediation` → `main`) passed on Python 3.12 but failed on
Python 3.10 (job `140106597858`) in `backend/tests/regression/test_phase2_release.py::test_dev_eval_script_runs`
with `subprocess.CalledProcessError` (exit status 1).

### Root cause
- Reproduced locally on Python 3.10.20 (`cpython-3.10-macos-aarch64-none`): `main.py` succeeded (`files 200 sanitized 193 quarantined 7 records 822`), but `backend/scripts/dev_eval.py` crashed with:
  `RecursionError: maximum recursion depth exceeded while decoding a JSON object from a unicode string` at `dev_eval.py:159` (`self.json = json.loads(raw)`).
- `organiser-toolkit/dev/input/misc/deep_export.json` contains 1,500 levels of JSON nesting. CPython 3.10's
  `json.loads()` hits the default 1,000-frame recursion limit and raises `RecursionError`, whereas CPython 3.12+
  decodes 1,500 levels without raising `RecursionError`.
- `Parsed.__init__` in `backend/scripts/dev_eval.py` only had `with contextlib.suppress(ValueError):` around
  `json.loads(raw)`, leaving `RecursionError` unhandled. Production sanitisation (`clinveil/parsing/json_safety.py`)
  already bounded JSON depth and caught `(ValueError, RecursionError)`, so no production engine change was needed.
- The official answer key (`organiser-toolkit/dev/truth/truth.json`) was present and valid in CI; it was not the cause.

### Fixes
1. `backend/scripts/dev_eval.py`:
   - Suppress `(ValueError, RecursionError)` when parsing raw JSON in `Parsed.__init__`.
   - Add an optional backward-compatible `--input` CLI argument (falls back to `Path(truth).resolve().parents[1] / "input"` when omitted).
   - Handle missing/unreadable/malformed `--truth` and `report.json` files cleanly with PII-free `stderr` diagnostics and exit code `2`.
2. `backend/tests/regression/test_phase2_release.py`:
   - Update `test_dev_eval_script_runs` to run with `check=False` and include `stdout`/`stderr` in the failure assertion so future CI failures are immediately diagnosable.
3. `backend/tests/unit/test_dev_eval.py`:
   - Add 4 isolated synthetic tests (invented identities only, plus a 1,500-level nested JSON fixture) covering deep JSON handling, leak detection with explicit `--input`, missing truth file handling, and malformed truth JSON handling.

### Validation (all run, 2026-11-27)
| Command | Exit | Result |
|---|---:|---|
| `ruff check src tests scripts ../main.py` / `ruff format --check src tests scripts ../main.py` | 0 / 0 | All checks passed / 91 files already formatted |
| `cd backend && uv run --python 3.10 --with pytest --no-project pytest -q` | 0 | 745 passed, 1 xfailed (18.61 s) |
| `cd backend && uv run --python 3.12 --with pytest --no-project pytest -q` | 0 | 745 passed, 1 xfailed (16.72 s) |
| `cd backend && ../.venv/bin/pytest -q` (Python 3.13) | 0 | 745 passed, 1 xfailed (19.89 s) |
| Python 3.10 `main.py` + `validate_output.py` | 0 / 0 | `files 200 sanitized 193 quarantined 7 records 822`; `CONTRACT OK` |
| Python 3.10 `check_dev.py` | 0 | 0/3230 visible, 0/4 canaries, 4855/4855 medical values, 0 raw copies |
| Python 3.10 `dev_eval.py --output OUT --truth organiser-toolkit/dev/truth/truth.json` | 0 | 0.0/3226 (0.00%), 0/8 canaries, 98.8% probes, 64228/64335 (99.8%) retention |
| Python 3.10 same-secret determinism (`diff -r` + `cmp`) | 0 | Identical `sanitized/` and `records.jsonl` |
| `.venv/bin/python organiser-toolkit/check_submission.py --repo . --run` | 0 | `READY TO SUBMIT` (1 known E5/O8 warning; input unchanged; secret never written) |
