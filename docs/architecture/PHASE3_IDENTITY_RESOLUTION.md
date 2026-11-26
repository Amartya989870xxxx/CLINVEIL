# Phase 3: Cross-Hospital Patient Identity Resolution and Cryptographic Pseudonymisation

Status: Design and implementation specification for branch `phase-3-identity-resolution` (based on `main` at `9205b5a`).

> **Phase 3.1 update.** An independent audit of `32fe8fc` reproduced six false-merge classes. The
> rules below are the corrected ones; the cases, root causes and measurements are in
> [`docs/evaluation/PHASE3_REMEDIATION.md`](../evaluation/PHASE3_REMEDIATION.md). In short:
> - identifiers have an **owner** (patient, relative or ambiguous);
> - insurance IDs and e-mail are **corroborators**, not global IDs;
> - under a global ID the whole names must be compatible;
> - the cross-hospital guard runs first and uses **reliably** established hospitals;
> - digit cores are **typed**;
> - distinct same-issuer MRNs block weak merges, except documented re-registration;
> - weak merges use **complete-linkage** vetoes, and capped name blocks abstain;
> - the self-check validates pseudonyms **per record**.

Authoritative external contract: `organiser-toolkit/docs/SPEC.md`, `SCORING.md`, `DATASET.md`, `ATTACKS.md`.

---

## 1. Design Principles

1. **Precision over recall (never over-merge).** A false patient merge corrupts two real patients' clinical histories and is penalised twice as heavily as a missed link (pairwise F0.5 + homonym separation). When evidence is weak, ambiguous, or contradictory, abstain (`patient: null`).
2. **Evidence-based, conflict-aware clustering.** Never run naive connected-components over weak edges. Clusters track the union of member evidence and re-check hard conflicts before every merge so weak similarities cannot bridge incompatible clusters.
3. **Reuse the common IR and Phase 2 findings.** Pass 1 extracts identity evidence from the already-parsed `Document` IR and Phase 2 `DocumentAnalysis` without parsing files a second time.
4. **Order-independent, keyed cryptographic pseudonyms.** Pseudonyms are derived with domain-separated, versioned HMAC-SHA256 (`psn|v1|<canonical_cluster_key>`) keyed strictly by `RAKSHA_SECRET`. Canonical keys depend only on sorted normalized evidence, never on file traversal order or temporary cluster numbers.
5. **Contract and schema preservation.** Pseudonyms are placed inside existing patient-identifier / patient-name slots (keeping CSV column counts, JSON key paths and value types, FHIR R4 validity and reference resolution, and text line counts intact) and reported consistently in `records.jsonl`.
6. **Zero PII leakage and bounded memory.** Evidence objects and caches live only in memory during the run, redact `repr`, refuse pickling, and are explicitly cleared in a `finally` block.

---

## 2. Module Architecture (`backend/src/clinveil/linking/`)

```
Pass 1 (per document, streaming)
  Document + DocumentAnalysis
    └── linking/extract.py      Extract RecordEvidence per record (IR + Phase 2 findings)
          └── linking/normalize.py   Strict cross-script name/village/ID/DOB/age/gender/hospital normalization

Between Pass 1 and Pass 2 (in memory only)
  list[RecordEvidence]
    └── linking/matcher.py      Pairwise & cluster-level evidence evaluation + hard conflict vetoes
    └── linking/cluster.py      Bounded blocking + 3-stage conflict-aware conservative clustering
    └── linking/pseudonyms.py   Canonical cluster key -> keyed HMAC-SHA256 pseudonym + collision handling
    └── linking/linker.py       Public facade (IdentityLinker, LinkResult, LinkingStats)

Pass 2 (per document, streaming)
  RecordKey -> PSN-XXXXXX
    └── sanitization/processors.py   Write pseudonym inside record + emit records.jsonl
    └── validation/contract.py       Verify pseudonym format & consistency before exit 0
```

All in-memory `RecordEvidence`, blocking tables, clusters, and canonical cluster keys are deleted before Pass 2 begins; memo caches are registered in `detection/caches.py` and cleared in `pipeline.py`'s `finally` block.

---

## 3. Evidence Classification & Normalization

| Tier | Evidence Types | Normalization & Guards |
|---|---|---|
| **Tier 1: Validated Global IDs** (person-unique) | Verhoeff-valid 12-digit Aadhaar, 14-digit ABHA number, ABHA address (`@abdm`/`@sbx`/`@ndhm`), validated PAN | Any-script Unicode digits folded to ASCII. **Masked Aadhaar (`XXXX XXXX 1234`) is NEVER used as a unique identifier.** Non-Verhoeff 12-digit numbers are NEVER used as Aadhaar. Doctor/org values are excluded. **Ownership (3.1):** an ID from a relative-labelled field (`Father Aadhaar`, `पिता आधार`, `Guardian UID`), a relative JSON container (`guardian: {aadhaar}`), FHIR `RelatedPerson.identifier`, or text whose own segment has a kinship cue (`Husband's Aadhaar`, `पति का आधार`) is the relative's: it is kept apart in `relative_global_ids` (veto only). A relation marker in that segment (`W/o <Name> Aadhaar …`) makes the owner ambiguous and the value unused. |
| **Tier 2: Hospital-Scoped Local IDs** | MRN, UHID, IPD/admission no., hospital registration no. | Normalized to `(hospital_scope, canonical_mrn)` plus a **typed** `(hospital_scope, "<type>:<digit_core>")` for cores >= 5 digits; types are `patient`, `admission`, `visit`, `pfx_<prefix>`, and cores only match within one type (3.1). Hospital scope is derived from facility/org fields, FHIR `Identifier.system` host, document letterhead, or filename stem; only the first three, a file name containing a hospital word, or a stem slug corroborated by one of those elsewhere in the run are **reliable** (3.1). Generic MRNs (`MRN-12345`, `UHID-099102`, bare numbers) **never** link across two different known hospitals. External labs/pathology reports are tagged as external sources so a referring hospital's MRN can still match when patient names are compatible. |
| **Tier 3: Supporting Evidence** | Patient name, relative name, 10-digit patient phone, DOB / birth year, age, gender, village / locality, district, PIN, **insurance / PMJAY / ESIC / CGHS ID and e-mail** (household-shareable, so corroborators only since 3.1) | **Supporting signals never trigger a merge alone.** Split name fields (`FirstName` + `LastName`, FHIR `given` + `family`) are reassembled per record. Doctor, staff, relative, and clinical values never enter `patient_names`. Dates respect explicit `MM/DD/YYYY` vs `DD/MM/YYYY` header hints and ISO dates; unlabelled ambiguous slash dates record both interpretations to avoid false vetoes while preserving hard conflicts. |

### Cross-Script Name Normalization (`linking/normalize.py`)
- Uses `detection/translit.name_key_strict` (keeping vowel qualities so `Kiran != Karan`, `Sita != Satya`, `Alok != Alka`), extended with:
  - title/honorific stripping (`Mr`, `Smt`, `Shri`, `ji`, `sahab`, `didi`, Devanagari equivalents);
  - `"Last, First"` inversion handling and split-column reassembly;
  - trailing `y`/`i` and `ey`/`e` folding (`Tripathy == Tripathi == त्रिपाठी`, `Pandey == Pande`);
  - controlled schwa-only variant matching (`Kamlesh == Kamalesh == कमलेश`) that requires identical consonant skeletons and identical non-`a` vowels, preventing vowel-distinct collisions (`Kiran` vs `Karan`) and consonant-distinct collisions (`Rohan` vs `Mohan`).
- Distinguishes five match grades: `EXACT_FULL`, `VARIANT_FULL`, `ABBREVIATED_FULL` (e.g. `R. Sharma` vs `Rajesh Sharma`), `FIRST_ONLY_MATCH` (for fragmented notes), and `CONFLICT` / `NONE`.

---

## 4. Matching and Conflict Rules

Explicit decision outcomes (`MatchOutcome`):
- `CONFIDENT_MATCH`
- `DISTINCT`
- `AMBIGUOUS`
- `INSUFFICIENT_EVIDENCE`
- `CONFLICT`

### Hard Conflict Vetoes (Always Block Merge)
1. **Conflicting global IDs:** disjoint Verhoeff-valid Aadhaar, disjoint 14-digit ABHA, or disjoint PAN.
   **Relative-ID owner (3.1):** one side's own Aadhaar/ABHA/PAN equals the other side's *relative* ID.
2. **Incompatible demographics:** conflicting explicit gender (`M` vs `F`), incompatible unambiguous DOB, birth year difference > 1, or age difference > 3.
3. **Incompatible full patient names:** two full (>=2 token) names that disagree on identifying tokens (blocks family members sharing a phone/address and twins sharing surname/DOB/relative/address). **Under a global ID match (3.1)** the names must be phonetically compatible as whole names; a shared surname alone no longer passes, and when both sides have full names only full names decide.
4. **Homonym vetoes (for non-ID matches):** disjoint relative names (`S/o X` vs `S/o Y`), disjoint villages, or disjoint districts block name-based merges.
5. **Cross-hospital local ID isolation:** an identical MRN string (generic **or prefixed**) from two different **reliably known** hospitals provides zero positive match evidence; the guard runs before any MRN rule (3.1). Two-letter and hospital-type prefixes (UH, GH, DH, CHC, PHC…) are not issuer-distinctive.
6. **Distinct authoritative MRNs, same issuer (3.1):** different patient MRNs (admissions/visits excluded) from the same issuer block non-global merges, except the re-registration documented in `DATASET.md`: full-name match + exact DOB + at least one more independent corroborator.
7. **Complete linkage for weak merges (3.1):** a merge resting on names and corroborators requires EVERY member pair to agree (age span ≤ 3, birth-year span ≤ 1, all DOBs compatible, one gender), so a cluster's tolerance cannot widen as it grows.

### Confident Match Rules (Only When Zero Conflicts Exist)
1. **Strong Global ID (`STRONG_GLOBAL`):** shared patient-owned validated Aadhaar, ABHA number, ABHA address or PAN (subject to block-size cap and conflict veto). Insurance IDs and e-mail no longer qualify (3.1).
2. **Scoped Local ID (`STRONG_SCOPED_ID`):** shared `(hospital_scope, mrn)` or same-type `(hospital_scope, typed digit_core >= 5)`, or shared distinctive-prefix MRN, or external-lab MRN with compatible patient name (subject to conflict veto and never across two different reliably known hospitals).
3. **Corroborated Full Name (`CORROBORATED_NAME`):** `EXACT_FULL` / `VARIANT_FULL` / `ABBREVIATED_FULL` plus at least one of:
   - exact `dob`;
   - shared 10-digit patient `phone`;
   - compatible `relative_name`;
   - shared insurance / policy ID or e-mail (3.1, household-shareable corroborators);
   - matching normalized `village` AND `age` within ±1 year (or matching birth year ±1).
   *(Full name + village alone without age/DOB/relative/phone is insufficient and remains unlinked.)*
4. **Unique Fragmented Attachment (`FRAGMENTED_UNIQUE`):** `FIRST_ONLY_MATCH` (non-generic given token) plus `relative_name`, `phone`, `dob`, or `village + age±1`, **only** when it matches **exactly one** existing cluster with zero conflicts and zero competing matches.

---

## 5. Blocking Strategy and Performance Bounds

To prevent O(N²) all-pairs comparisons:
- **Stage A blocks:** `aadhaar`, `abha_number`, `abha_address`, `pan` (insurance and e-mail removed in 3.1).
- **Stage B blocks:** `(hospital_scope, canonical_mrn)`, `(hospital_scope, digit_core)`, and external/prefixed `canonical_mrn`.
- **Stage C blocks:** sorted strict full-name pair keys, `(surname_strict, first_initial)`, `phone`, `dob`, `(first_strict, relative_strict)`, `(first_strict, village_strict)`.
- **Pathological block cap (`MAX_BLOCK_SIZE = 128` for ID/phone/DOB blocks, `64` for name blocks):** blocks exceeding the cap are skipped rather than compared pairwise, and counted in `blocks_capped_ambiguous`. Records that cannot be safely linked within the cap remain unlinked (`null`). **Since 3.1** the members of a capped full-name block abstain from all name-based merging (they are not re-reached through phone or DOB blocks).

---

## 6. Conservative 3-Stage Clustering

1. **Stage A (Global IDs):** Merge clusters sharing validated global IDs in deterministic canonical order, verifying `cluster_conflict(c1, c2)` before every merge.
2. **Stage B (Hospital-Scoped Local IDs):** Merge clusters sharing scoped local IDs in deterministic order, re-verifying cluster-level conflicts before every merge.
3. **Stage C1 (Corroborated Full-Name Merging):** Merge remaining clusters with Tier 3 corroborated full-name evidence in strict priority order (`name+dob` → `name+phone` → `name+relative` → `name+village+age`). Before merging `(c1, c2)`, verify there is no ambiguous competing non-conflicting match to a third conflicting cluster and re-verify cluster-level conflicts.
4. **Stage C2 (Singleton/Fragmented Attachment):** Attach remaining singletons (e.g., first-name + relative, or first-name + phone) to existing clusters **only** if exactly one cluster matches with zero conflicts. Never chain weak singletons together.

Every cluster with `>= 2` members, or a singleton carrying a strong patient anchor (validated global ID or hospital-scoped MRN/UHID), receives a pseudonym. Records with no identity evidence, phone-only records, name-only records, non-Verhoeff unanchored records, or ambiguous matches remain `patient: null`.

---

## 7. Cryptographic Pseudonym Construction

- **Canonical cluster key:** derived strictly from sorted normalized evidence in fixed precedence (`aadhaar|...` > `abha|...` > `abhaa|...` > `pan|...` > `mrn|...` > `demo|...`; insurance and e-mail removed in 3.1 because they can be shared by a household). Traversal-order-independent.
- **HMAC construction (`Pseudonymizer.pseudonym`):**
  - `HMAC-SHA256(RAKSHA_SECRET, "psn|v1|" + canonical_cluster_key)` (or `"psn|v1|" + canonical_cluster_key + "|#" + attempt` on collision).
  - The first 5 digest bytes are read as a 40-bit big-endian integer and its **low 30 bits** are encoded as 6 Crockford base32 characters (least-significant 5-bit group first): `PSN-XXXXXX`. (Earlier text said "first 30 bits", which was inaccurate; the code is unchanged.) The format matches the official example `PSN-7Q2K9D`, which SPEC shows only as an example. 30 bits give ≈1.07 × 10⁹ codes; collisions inside one release are resolved deterministically (below).
- **Collision protection (D8):** Clusters are ordered canonically before assignment; if two distinct clusters produce the same 30-bit code, the second deterministically re-derives with `attempt = 1, 2, ...` so distinct clusters never share a pseudonym.
- **Security properties:**
  - Keyed by `RAKSHA_SECRET` only (no fallback secret, no machine fingerprint).
  - Different secrets yield distinct pseudonyms and distinct release bytes (defeats A7 cross-release linkage).
  - Non-invertible without `RAKSHA_SECRET` (defeats A6 pseudonym inversion).
  - No identity mapping is persisted or logged.

---

## 8. Output Integration & Contract Compliance

- **`records.jsonl`:** emits `{file, loc, patient}` for every exported record (`patient` is `PSN-XXXXXX` or `null`). Single-patient JSON reports containing a top-level `patient` object and sub-lists like `panels` are enumerated as `doc` (matching `SPEC.md` and `DATASET.md`).
- **In-record pseudonym insertion (schema-preserving):**
  - **CSV/TSV:** replaces the record's MRN/UHID cell span (fallback: `PATIENT_NAME` span; fallback: first direct-ID span) with `PSN-XXXXXX`. Column count, headers, and row shape remain 100% unchanged.
  - **JSON:** replaces the record's string MRN/patient_ref value (fallback: string `PATIENT_NAME` value; fallback: first string direct-ID value) with `PSN-XXXXXX`. Key paths and value types remain 100% unchanged.
  - **FHIR R4:** replaces `Patient.identifier[i].value` (preferring hospital MRN/UHID, fallback other `Patient.identifier.value` or `Patient.name`) with `PSN-XXXXXX`. All references, `id`/`fullUrl` rewrites, and R4 structure remain valid.
  - **Plain Text:** replaces the first `MRN` finding span (fallback: first `PATIENT_NAME` span; fallback: first direct-ID span; last resort: `Patient: PSN-XXXXXX\n` header) with `PSN-XXXXXX`. Line counts and clinical content remain intact.
- **`report.json`:** `counts.records_linked` reports the exact count of non-null `patient` entries in `records.jsonl`.
- **`logs/detection_summary.json`:** adds safe aggregate `linking` counts only (zero PII, zero cluster keys, zero file paths).

---

## 9. Privacy Boundaries & Known Limitations

- **No guaranteed memory wiping in Python:** all linking indexes, `RecordEvidence`, clusters, and canonical keys are deleted after Pass 1 and memo caches are cleared in `finally`, but Python's allocator/GC cannot guarantee physical RAM zeroing.
- **Delayed Phase 4 transformations:** per-patient date shifting, age banding, village→district generalisation, PIN prefixing, and k-anonymity rare-cell suppression remain deferred to Phase 4.
- **Uncued/context-free records:** a record containing only an unlinked first name, initials, phone number, or address without corroborating patient identity is deliberately left unlinked (`null`) rather than risked as a false merge.
- **Unseen multi-patient single-doc FHIR Bundles:** if a single FHIR Bundle contains multiple conflicting `Patient` resources with no clear primary patient, the document is conservatively marked `AMBIGUOUS` (`null`).
