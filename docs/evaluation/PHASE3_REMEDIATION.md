# Phase 3.1: false-merge remediation

Branch `phase-3-identity-resolution`, on top of the Phase 3 implementation `32fe8fc` (base `9205b5a`).
An independent read-only audit of `32fe8fc` reproduced six false-merge classes on invented data and
returned **REJECT** for merging. This document records, for every case:
- what was reproduced;
- the root cause;
- the correction and its regression test;
- the measured result and what remains.

All test identities, IDs, hospitals and phone numbers are invented. Practice-data figures come from
the organisers' unmodified tools plus a local, uncommitted metric script over the *practice* key. No
sealed or blind answer key was used.

## 1. Method

1. **Reproduce first.** `backend/tests/regression/test_phase31_false_merges.py` was written before any
   fix and run on unmodified `32fe8fc`: **23 failed, 18 passed** (41 tests).
   - The 18 that passed were the positive counterparts (genuine links that must survive) plus cases
     that were already correct.
   - One apparent failure, the FHIR RelatedPerson case, was traced to the test helper (an output
     renamed for PII); it was fixed in the helper and kept as a guard.
2. **Fix root causes, not examples.** Each correction is a rule change in extraction or matching.
   There is no lookup table of test values, and no redesign of the engine or its cryptography.
3. **Keep recall honest.** Every negative case has a positive counterpart. Practice metrics were
   compared before and after on identical inputs.
4. **Re-run the original audit harness**, written before this work, unchanged against the fixed code
   (§4).

## 2. Cases, root causes and fixes

| ID | Reproduced false merge (invented data) | Root cause | Fix |
|---|---|---|---|
| **R1** (critical) | Two siblings merged through a `Father Aadhaar` column, also with `Mother Aadhaar`, `Guardian Aadhaar`, `पिता आधार`, `Parent UID`, and across two hospitals | `extract._consume_findings` skipped relative-owned phones and e-mails only. A relative-labelled ID column is not classified `RELATIVE_NAME`, so the father's Aadhaar became each child's global ID | **Ownership attribution** (below): an ID in a relative-labelled field, or under a relative JSON key, is the relative's. It never enters patient evidence; person-unique ones go to `relative_global_ids` |
| **R2** (critical) | A wife's note quoting her husband's Aadhaar merged with the husband. Same for `Aadhaar of husband:`, a JSON `guardian: {aadhaar}`, and `…W/o <Name> Aadhaar …` | Free-text IDs were always taken as the patient's, whatever words qualified them | Text ownership from the value's own segment (text after the last `, ; \| ।` or sentence end, ≤60 chars). A kinship cue (`Husband's`, `of husband`, `पति का`) makes it relative-owned. A relation marker (`W/o <Name>`) makes the owner ambiguous and the value is not used. `C/O` is never a cue. FHIR `RelatedPerson.identifier` goes to `relative_global_ids`. New veto `conflict_relative_id_owner`: one side's own ID equals the other side's relative ID, so they are different people |
| **R3** (high) | Family members sharing one ESIC number, one PMJAY ID or one household e-mail merged across hospitals | Insurance IDs and e-mail were person-unique `STRONG_GLOBAL` identifiers (Stage A blocks, canonical key) | Both are now **corroborators** (`corrob_insurance`, `corrob_email`): they support a matching full name and never identify alone. They were removed from Stage A blocks, `has_global_id` and the canonical key |
| **R4** (high) | `Arvel Dunmore` and `Tavin Dunmore` sharing one (patient-owned) Aadhaar merged | Under a global-ID match a name conflict was vetoed only if the names shared **no** token (`_names_share_any_token`), so a common surname passed | The helper was removed. Under a global match the names must be phonetically compatible as whole names, and when both sides have full names only full names decide (a surname-only fragment cannot vouch). Spelling, order, initial, Devanagari and missing-given-name variants still link |
| **R5** (high) | Two known hospitals both issuing `UH-2026-00451` (also `GH/26/…`, `DH-…`, `SVH-…`) merged | `shared_prefixed_mrn` returned before the cross-hospital guard | The guard now runs first and uses **reliably established** hospitals only: FHIR system or Organization, facility field, letterhead, a file name containing a hospital word, or a file-stem slug corroborated by one of those elsewhere in the run. Two-letter and hospital-type prefixes (UH, GH, DH, CHC, PHC…) are no longer "distinctive" |
| **R6** (high) | `IPD/26/0045123` linked to another patient's `UHID-0045123` | Digit cores were compared without identifier type | Typed cores `"<type>:<digits>"`. Types are `admission` (IPD/IP/ADM), `visit` (OPD/visit/token/bill), `patient` (UHID/MRN/CR/Reg, or a bare number in such a field) and `pfx_<prefix>`. Cores only match within one type |
| **R7** (medium) | Two different UHIDs from the same hospital (same name + phone) merged | Distinct authoritative MRNs from one issuer were not considered at all | Different authoritative patient MRNs from the same issuer (admissions and visits excluded) block non-global merges, **except** the re-registration case documented in `DATASET.md` ("some re-register at the same hospital with a new ID"): a full-name match + exact DOB + at least one more independent corroborator |

### Why R7 is not a hard veto
The first version made distinct same-hospital MRNs an absolute veto. On the practice data that split a
correct 27-record cluster: the Arogya legacy export re-registers a patient under a new UHID, exactly as
`DATASET.md` describes. The final rule raises the evidence bar instead. The audit's case (same name + phone
only) stays blocked; `test_R7_positive_documented_reregistration…` keeps the documented case linked.

### Cluster-level consistency
- **Evidence widening.** Cluster vetoes compared the *closest* member values (minimum age gap, any DOB
  pair), so a cluster's tolerance grew as it absorbed records. For merges that rest on names and
  corroborators only, `_complete_linkage_conflicts` now requires **every** member pair to agree: age span
  ≤ 3, birth-year span ≤ 1, all DOBs compatible, a single gender. Strong-ID merges keep the per-visit
  tolerance, because a patient's age legitimately changes across admissions.
  - Test: A~B strongly (shared Aadhaar, ages 30/33), B~C weakly (name + phone, age 36). C does not join.
- **Capped blocks.** A full-name block above the cap (64) is a dense homonym group. Its members now
  **abstain** from name-based merging instead of being re-reached through phone or DOB blocks.
  Strong-ID stages are unaffected.
  - Test: 70 same-name records sharing phones in pairs link 0 records.
  - Bounded benchmark (120 dense homonyms): 24 records were linked through DOB blocks before; 0 now.

### Output consistency (per-record validation)
`validation/contract.py` previously checked that a claimed pseudonym appeared *somewhere in the file*. It now
locates each `records.jsonl` record by its locator: `row:N` in CSV/TSV, an RFC 6901 pointer in JSON, `doc`
for the whole file. It then checks that:
- a linked record contains **its own** pseudonym;
- no record contains a **different** patient's pseudonym, and an unlinked record contains none;
- the record can be located at all;
- `records_linked` agrees with the claims.

Three new tests cover a pseudonym present only in another row, an inherited pseudonym, and a correct
placement. On the practice release, all 772 linked records pass per-record.

**Plain-text fallback** (`Patient: PSN-XXXXXX` prepended when a linked note has no in-body slot): kept.
`SPEC.md` §6 names "a `Patient:` header line of a note" as a valid placement. It never triggers on the
practice data (0 of 100 text outputs), and when it does it adds exactly one line.

### Pseudonym documentation correction
The code (unchanged) takes the first **5** digest bytes as a 40-bit integer and encodes its **low 30 bits**
as 6 Crockford base32 characters. That is not "the first 30 bits", which the Phase 3 docs and docstring
claimed. The text is corrected. The format matches the official example `PSN-7Q2K9D` and is unchanged.
SPEC shows the format only as an example; it comes from the organisers' starter helper.

The HMAC-SHA256 construction is unchanged: domain-separated `psn|v1|` message, collision counter
re-derivation, secret keying, in-memory canonical keys. The canonical key now ranks
`aadhaar > abha > abhaa > pan > mrn > demo` (insurance and e-mail removed, R3).

**Also fixed:** `LinkResult.for_document()` scanned the whole mapping once per file, which is
O(files × records). It now uses a per-file index built once.

## 3. Regression tests (`backend/tests/regression/test_phase31_false_merges.py`, 46 tests)

**Negative cases (must not merge):**
- **R1:** 6 relative column labels, plus two hospitals;
- **R2:** 4 narrative forms (English, Devanagari, ambiguous owner), a JSON relationship key, FHIR
  RelatedPerson;
- **R3:** ESIC, e-mail and PMJAY shared by family members; shared e-mail + address;
- **R4:** surname-only compatibility; identical full names with conflicting Aadhaar;
- **R5:** UH, GH, DH and SVH prefixes across two known hospitals;
- **R6:** IPD, OPD, ADM and VISIT numbers against a UHID;
- **R7:** distinct UHIDs at one hospital;
- **cluster level:** weak bridge; capped homonym block.

**Positive counterparts (must still link):**
- **identifiers:** patient-owned Aadhaar across hospitals and in a note with `S/o` + `C/O`;
- **names:** shared policy + same full name; name variants with the same Aadhaar (spelling, order,
  initial, Devanagari, missing given name);
- **MRNs:**
  - an external lab quoting a hospital-prefixed MRN;
  - the same UHID with different separators;
  - one MRN with several admission numbers;
  - different hospital MRNs joined by the patient's Aadhaar;
  - a documented re-registration;
  - a third-party note quoting an issuer-prefixed UHID.

**Per-record contract:** 3 tests.

Two existing tests now pass only because of the reliable-hospital rule:
- `test_unseen_schema_generalisation_and_1000_record_scaling`: a third hospital's visits cite the other
  hospitals' prefixed UHIDs; file-stem slugs are not proof of different issuers.
- `test_renamed_file_is_declared_by_hash_and_records_point_to_it`.

Two existing test helpers were adapted to the new evidence API, with no assertion changed:
- `test_linking._ev` reads the typed core;
- `test_linking._ev` marks an explicitly named hospital as reliably known.

## 4. Independent confirmation with the original audit harness

The audit scripts (written before this work, run unchanged) now give:

| Case | Result |
|---|---|
| R1 relative-Aadhaar siblings | separated |
| R2 spouse note | separated |
| R3 shared ESIC | separated |
| R4 shared e-mail | separated |
| R9 UH prefix across hospitals | separated |
| R10 IPD core | separated |
| Twins, doctor named like a patient, relative named like a patient, age drift, conflicting Aadhaar | unchanged, already correct |

## 5. Measured results (2026-11-27)

| Check | Exit | Result |
|---|---:|---|
| New regression suite | 0 | 46 passed (before the fixes: 23 of 41 failed) |
| `pytest`, Python 3.13.7 / 3.10.20 / 3.12.13 | 0 | **812 passed** on each |
| `ruff check` / `ruff format --check` | 0 / 0 | clean / 99 files |
| `validate_output.py` | 0 | CONTRACT OK |
| `check_dev.py` | 0 | 0/3230 visible, 0/4 canaries, 4855/4855 medical values, linking P 1.00 / R 0.99 / F0.5 1.00, 0 wrongly merged, 0 raw copies |
| `check_submission.py --repo . --run` | 0 | READY TO SUBMIT, no warnings |

**Identity metrics on the practice data** (pairwise over `link == "required"` units, as `check_dev.py`
defines them; local scratch script, not committed):

| Metric | Phase 3 (`32fe8fc`) | Phase 3.1 |
|---|---:|---:|
| True / false / missed pairs | 6,803 / 0 / 89 | 6,803 / 0 / 89 |
| Precision / recall / F0.5 | 1.0000 / 0.9871 / 0.9974 | 1.0000 / 0.9871 / 0.9974 |
| False-positive pairs incl. the 2 "ambiguous" units | 0 | 0 |
| Pseudonyms spanning > 1 true patient | 0 | 0 |
| Required units left unlinked | 2 | 2 |
| Clusters / linked / unlinked records | 49 / 772 / 50 | 49 / 772 / 50 |
| Cluster sizes | 22 of 16+, 27 of 5–15 | 22 of 16+, 27 of 5–15 |
| Merges blocked by vetoes / capped blocks / collisions | 58 / 0 / 0 | 56 / 0 / 0 |

The practice data contains **none** of the audit's false-merge patterns, so its metrics are unchanged.
"0 wrong merges" on practice data is therefore not evidence for the fixes: the regression suite and the
re-run audit harness are. Equally, it is not proof that no false merge exists on unseen data.

**Other checks (all measured):**
- same secret: identical `sanitized/`, `records.jsonl` and `logs/`;
- different secret: the same linkage partition with **0** shared pseudonyms;
- the input tree is unchanged and `TMPDIR` stays empty;
- the secret appears nowhere in the outputs;
- no whole-word PII surface or key in the report, records, logs, stdout/stderr or output paths;
- 19 FHIR Bundles with 0 unresolved references;
- forced pseudonym collisions in an 8-value space stay unique and order-independent.

**Performance:** 200 files 2.28 s / 41 MB; 2,000 files 22.4 s / 126 MB (CONTRACT OK); dense homonym
blocks of 60/120/400 records ≤ 0.12 s.

## 6. Remaining limitations

- **Ownership:** relies on labels and the value's own text segment. An ID written after a relative's
  *unlabelled* name with no kinship word (`Attendant: Arvel, 2345 …`) is attributed to the patient. A
  relation marker in the same segment makes the value unused, which costs recall.
- **Hospital reliability:** two hospitals known only from file-name stems without a hospital word count
  as "unknown", so the cross-hospital guard does not apply. Protection then rests on prefixes:
  hospital-type and short prefixes are scoped per file, but a coincidentally identical *distinctive*
  3+-letter prefixed MRN with compatible names would still link.
- **Re-registration exception:** two different patients at one hospital with the same full name, exact
  DOB and one more matching corroborator (e.g. shared family phone) would be linked. This is the
  documented trade-off of the `DATASET.md` re-registration rule.
- **Complete-linkage vetoes:** these apply to weak merges only. Clusters built from strong IDs keep
  per-visit tolerance.
- **Practice data:** none of these patterns occur in it, and the hidden datasets are untested
  (sealed). The red-team re-evaluation against Phase 2.1/Phase 3 is still outstanding.
- **Memory:** Python cannot guarantee physical erasure of in-memory identity evidence.
