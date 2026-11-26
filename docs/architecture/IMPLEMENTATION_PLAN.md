# Implementation plan

Ordering principle: **scoring impact per hour, without regressing the contract.** Every phase ends
with `pytest`, `validate_output.py` = CONTRACT OK, and a recorded `check_dev.py` delta. Points
reference `organiser-toolkit/docs/SCORING.md`.

## Dependency graph

```
P0 bootstrap ─► P1 ingestion IR ─► P2 detection ─┬─► P4 privacy ─► P5 export ─► P6 eval/opt ─► P7 demo
                                   └─► P3 linking ┘
```
P2 and P3 can run in parallel once P1's IR exists. P3 consumes P2's name and ID findings as
evidence. P4 needs P3's clusters, because date shifts and pseudonyms are per patient.

---

## Phase 0: repository bootstrap ✅ (this commit)
- [x] Toolkit cloned separately (`organiser-toolkit/`, git-ignored, unmodified)
- [x] Starter refactored into `backend/src/clinveil`, **byte-parity test** against the real starter
- [x] Hardening: symlink and size guards, PII-free reasons, fail-closed secret, overlap guard, pre-exit self-check
- [x] Tests (unit, integration, regression, security), ruff, CI
- [x] Baseline measured ([BASELINE.md](../evaluation/BASELINE.md))

**Accepted when:** CONTRACT OK, parity test green, no secrets or answer keys in git. ✅

## Phase 1: reliable ingestion ✅ (branch `phase-1-ingestion`; evidence: [PHASE1_INGESTION.md](../evaluation/PHASE1_INGESTION.md))
- Content sniffing: JSON behind `.csv` (`misc/mislabeled_export.csv`), XML, PDF and JPEG magic bytes
- Decode plausibility: quarantine invalid-UTF-8 files that cp1252 "decodes" into mojibake (`corrupt_bytes_note.txt`)
- Common IR with field paths, kinds and channel tags (`content`/`header`/`key`/`metadata`/`base64`/`filename`)
- FHIR enumeration: resources, `Reference`s, `meta.source`, `identifier`, `text.div`, `Attachment.data`
- Base64 attachment extraction (decode, then sanitise as text, re-encode)

**Accepted when:** every practice `misc/` file is either correctly parsed or quarantined with a reason code;
no file in `sanitized/` is byte-identical to a broken input; parity test retired. ✅ All verified:
`test_phase1_delta.py` pins every output difference against the starter, and the Phase 0 parity test is removed.

## Phase 2: detection ✅ (branch `phase-2-detection`; evidence: [PHASE2_DETECTION.md](../evaluation/PHASE2_DETECTION.md))
1. **Column and key semantics:** classify headers and keys by token features (`naam`, `name`,
   `mobile`, `contact#`, `pita/pati`, `gaon`, `mohalla`, `uhid`, `reg no`, Devanagari forms) with fuzzy
   matching, *not* exact strings (the unseen-format round renames columns).
2. **Patterns:** Aadhaar (Verhoeff checksum), masked Aadhaar, ABHA number and address, PAN, phones
   (`+91`, `0`-prefixed, spaced, hyphenated, Devanagari digits), UHID/IPD/MRN families by shape,
   email, PIN. **Guards** for doses (`650`, `1-0-1`, `BD x 5`), lab values with units, BP, ICD codes and dates.
3. **Label and context:** `Name:`/`नाम:`/`Pt.`/`Patient:`, honorifics (`ji`, `sahab`, `didi`, `श्री`, `श्रीमती`),
   relatives (`S/o`, `D/o`, `W/o`, `C/O <Name>`, `पुत्र`, `पत्नी`), *keep* `Dr. <name>`, keep `C/O <complaint>`.
4. **Gazetteers and transliteration:** Indian given names and surnames in Latin and Devanagari, plus a
   rule-based Devanagari↔Latin transliterator with variant folding (Mohammad/Mohd/Md.). Self-built, declared.
5. **Propagation:** any value confirmed as PII anywhere (structured columns are high-precision) is
   searched for and removed everywhere: notes, filenames, keys, base64. This is the main lever for
   canaries and the hidden-channel recall.
6. **Hidden channels:** filenames (rename and record the mapping in the report), PII headers and keys,
   export metadata (`source_path`).

**Accepted when:** all `xfail` cases in `test_contextual_detection.py` pass; `check_dev` leak below 5%
overall with deva/hinglish within 2× of latin; 0/4 canaries; medical values kept ≥ 99%; also
re-measured on a **mutated practice copy** (renamed columns, swapped names, new date formats).
✅ Measured: 0/3230 leaked (`check_dev.py` and official-style `dev_eval.py`), Latin/Devanagari/Hinglish 0%,
0/4 canaries, 4855/4855 probes, 100% non-PII token retention; generated unseen-style data 0/1200 leaked.
Not measured: a mutated copy of the *practice* data (a synthetic generator was used instead).

## Phase 3: identity resolution (15 pts plus utility coupling, about 1.5 days)
- Evidence normalisation: digit cores of UHID/IPD/phone/Aadhaar/ABHA, names transliterated to one
  key space, DOB, relative, village, age at encounter
- Blocking on strong keys and phonetic name keys; pairwise scores with explicit weights
- Clustering: strong-identifier edges union; weak (name + one corroborator) edges only attach a
  singleton to a cluster with no conflicts; **conflicting** DOB/Aadhaar/gender/relative vetoes; no weak chains
- Canonical cluster key = min(sorted strong evidence) → `pseudonym()`; write the pseudonym into the record
  (`patient_ref` column, JSON field, `Patient:` line, FHIR `Patient.identifier`)
- Homonym guard: same name with different village, age or relative never merges

**Accepted when:** dev pairwise precision ≥ 0.98, F0.5 ≥ 0.9; 0 wrongly merged people; the
different-secret test XPASSes (remove the `xfail`).

## Phase 4: privacy transformation (25 pts, about 1 day)
- Per-patient date shift on every date of that patient (all formats, incl. FHIR `dateTime` and
  month-first legacy dates); exact intervals and LOS preserved
- Age → 5-year band (truthful); DOB → shifted; village → tehsil/district; PIN → 3-digit prefix
- k-anonymity check over (age band, gender, district, shifted admission week, rare diagnosis):
  widen or suppress **only** the rare cells (re-identification trap); never global
- Re-identification risk estimate reported in development metrics, not in the release

**Accepted when:** own uniqueness estimate below the target (to be set from the first measurement);
utility ≥ 0.40 coupling threshold with margin; age bands always contain the true age.

## Phase 5: secure export (10 pts, about 0.5 day)
- FHIR R4 structural validity: ids, references resolvable, date syntax
- `report.json` `entities` counts; filename mapping; honest counts
- Final side-channel self-scan against the release's own known-PII set

## Phase 6: evaluation and optimisation (ongoing from Phase 2)
- `metrics/`: dev scorer wrapping `check_dev.py` numbers, linking P/R/F0.5, uniqueness estimate
- Mutation harness: generate an unseen-format variant of the practice set for generalisation tests
- Runtime and RSS on a 10× synthetic scale-up (scaling exponent ≤ 1.15)

## Phase 7: local demonstration (lowest priority)
- Read-only local API over a completed output directory ([API contract](../api-contract/README.md))
- Frontend integration; judge-facing walkthrough on synthetic data only

## Next five tasks (in order)
1. **P3: evidence graph for linking**, built from Phase 2 findings: strong identifiers (MRN cores, phone,
   Aadhaar, ABHA) as union edges; name keys plus a corroborator (DOB, relative, village + age) as guarded edges;
   conflict vetoes; no transitive weak chains
2. **P3: pseudonym insertion**: write the cluster pseudonym *inside* each record (patient_ref column, JSON
   field, `Patient:` line, FHIR Patient.identifier) and in `records.jsonl`; add a `psn|` domain prefix
3. **P4: per-patient date shift** of every DOB, admission, visit and lab date (FHIR-valid), preserving intervals and LOS
4. **P4: generalisation**: age bands, village → tehsil/district, PIN → 3-digit, plus a k-anonymity check over
   (age band, gender, district, admission week, rare diagnosis) with rare-cell suppression
5. **P2 hardening**: mutated copy of the practice set (names swapped, labels renamed) as a second generalisation
   benchmark; widen the district/tehsil gazetteer beyond UP
