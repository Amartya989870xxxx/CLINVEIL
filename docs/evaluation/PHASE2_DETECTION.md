# Phase 2: multilingual, context-aware PII detection

Measured 2026-11-26 on branch `phase-2-detection`, macOS (Darwin 27), Python 3.13.7, toolkit commit
`6c0a85a`. **No official score was computed.** The official evaluator is sealed. `check_dev.py` and our
`dev_eval.py` are development guides, and both are reported below.

> **Phase 2.1 update.** An independent audit of this phase was remediated on branch
> `phase-2.1-remediation`. Every finding, its reproduction, fix and measured result is in
> [PHASE2_REMEDIATION.md](PHASE2_REMEDIATION.md). In short:
> - non-Patient FHIR text is detected;
> - preserved fields are *guarded* rather than skipped;
> - label classification uses a purity rule with restricted fuzzy matching;
> - encoded values (XHTML, HTML entities, %-escapes, URL-safe/short base64, all Indic digit scripts) are
>   decoded for detection;
> - FHIR ids are rewritten consistently, binary attachments are withheld, and report counts are honest.
>
> The protection count in §8 has been corrected (55, not 96). Sections below describe Phase 2 and
> note Phase 2.1 changes inline.

## 1. Architecture

```
IR (Phase 1)
  │
  ├─ semantics      headers / key paths / FHIR roles  ──►  what each field holds
  │                  (fuzzy, Hindi labels, parent-path refinement, dynamic keys as values)
  ├─ structured     PII-typed field values  ──►  whole-value findings (names keep "S/o"/titles,
  │                  addresses split into components, DOB whole, numbers -> 0)
  ├─ free text      identifiers (validated) · names (labels, markers, honorifics, kinship, titles,
  │                  by-cues, timeline, role suffix, possessive, Muslim-name prefixes, gazetteer)
  │                  · addresses · DOB labels · names adjacent to phones
  ├─ loose channels headers / keys / filenames / metadata: ID-shaped tokens are values,
  │                  capitalised neighbours are names
  ├─ propagation    run-wide SensitiveValueIndex (pass 1 seeds) + document-local index
  ├─ protection     clinical keep spans (doctors, drugs, doses, 1-0-1, vitals, labs, eponyms,
  │                  K/C/O, H/O, C/O+complaint, wards, hospitals, ASHA)
  └─ resolve        threshold 0.7 · protection · overlap (confidence, length) · merge
        │
        ▼
  Finding(entity, start, end, confidence, detector, evidence, action, field, record, channel,
          document, clinical_conflict)       offsets only, never text
        │
        ▼
  sanitiser: placeholders [NAME] [RELATIVE] [PHONE] [MRN] … · numbers -> 0 · FHIR birthDate -> year
             · base64 rebuilt & re-encoded · PII headers de-duplicated · PII paths renamed
```

Pipeline: **pass 1** seeds the index from every ingestible file (FIELD_SEMANTICS, LABEL and
VALIDATED_PATTERN evidence ≥ 0.88 only). **Pass 2** analyses, renames, sanitises and renders.

| Module | Responsibility |
|---|---|
| `detection/text.py` | tokens with original offsets, per-token normalisation (NFKC, zero-width, Devanagari digits, nukta, casefold), script and language cues |
| `detection/translit.py` | Devanagari→Latin romanisation; phonetic name keys unifying Mohammad/Mohd/Md/मोहम्मद, Seeta/Sita/सीता, Tripathi/Tripathy/त्रिपाठी |
| `detection/lexicon.py` | self-authored vocabularies (provenance below) |
| `detection/semantics.py` | label/path classifier: 31 semantic types, Devanagari label map, acronyms (`D.O.B.`), camelCase. Phase 2.1: purity rule (all tokens must belong to one PII class plus neutral modifiers); fuzzy matching only for 6+ letter words towards distinctive PII words |
| `detection/views.py` | (2.1) decoded views of XHTML / HTML-entity / %-encoded values with an exact offset map back |
| `detection/caches.py` | (2.1) registry of memo caches, cleared after every run |
| `detection/identifiers.py` | phones (all Indian formats, digits of every script), STD landlines (2.1), Aadhaar + Verhoeff (unlabelled checksum-invalid runs ignored since 2.1), masked Aadhaar, ABHA number (labelled contiguous form, 2.1) / address, PAN (holder-type letter), e-mail, insurance, labelled MRN/UHID/IPD |
| `detection/names.py` | contextual patient/relative name detection (Latin, Devanagari, Hinglish) |
| `detection/addresses.py` | house / ward / mohalla / landmark / village / PIN; tehsil and district preserved |
| `detection/clinical.py` | clinical and doctor keep spans |
| `detection/value_index.py` | run-local Sensitive Value Index (never serialisable) |
| `detection/resolve.py` | deterministic resolution and span application |
| `detection/engine.py` | per-document orchestration, FHIR semantics, statistics |
| `models/findings.py` | typed `Finding`, `Evidence`, `Action`, `EntityType` (evaluator vocabulary + `DOCTOR_NAME`) |
| `sanitization/processors.py` | placeholders, numeric/FHIR-date handling, payload re-encoding, renaming |

## 2. Supported entities, scripts and channels

Entities (official vocabulary): PATIENT_NAME, RELATIVE_NAME, PHONE, EMAIL, AADHAAR, AADHAAR_MASKED,
ABHA_NUMBER, ABHA_ADDRESS, PAN, MRN (UHID / registration / IPD / admission), INSURANCE_ID, HOUSE,
LOCALITY, LANDMARK, VILLAGE, PIN, DOB. DOCTOR_NAME is recorded only as a *preservation* decision.

Scripts: Latin, Devanagari (including nukta forms, matras, Devanagari digits), Romanised Hindi
(Hinglish). Channels: content, header, key, metadata, base64, filename (path components).

## 3. Semantic field classification

Generalises beyond the practice headers: `tests/unit/test_semantics.py` covers about 90 labels, most of which
never occur in practice data (`Pateint Nmae`, `name_of_patient`, `रोगी का नाम`, `मरीज_का_नाम`, `Contact#`,
`संपर्क`, `WhatsApp No`, `Next of Kin`, `पति का नाम`, `CR No`, `health_id`, `Gram/Mohalla`, `Village Name`,
`postal_code`, `D.O.B.`…). Path refinement: `patients/*/name/first` is a patient, `guardian/name` a relative,
`facility/name` and `panels/*/name` organisations, `raised_by/name` a person. Schema labels are never
redacted. A label is rewritten only if it contains a value (a CSV header `<ID> <name>`, or a key under
`lookup_by_patient` that is itself a name).

## 4. Multilingual approach and transliteration

Detection works on tokens of the original text with per-token normalised keys, so offsets are always
exact. NFC/NFD, precomposed vs decomposed nukta, and zero-width joiners are tested. Names in either script
are compared through phonetic keys (aspiration folding, w/v, z/j, q/k, vowel dropping after the first
letter, repeat collapsing). A key match is **evidence for propagation**, never proof of identity. Phase 3
must corroborate links with strong identifiers. Language cues (Hinglish function words) are used for
statistics, not as a basis for redaction.

## 5. Clinical protection

Keep spans are structural (titles, units, dose grammar, eponym grammar), not an open whitelist. A doctor
span blocks every name finding, including propagated ones. Other clinical spans block weak name evidence
(gazetteer, propagation tokens, context) but not labelled or structured names. Identifiers are never
blocked: a validated phone cannot be a dose.

Mandatory regression cases (all pass, `tests/regression/test_contextual_detection.py`):

| Input | Result |
|---|---|
| `Dr. Ramesh` | preserved |
| `C/O Ramesh …` (address) | relative name removed |
| `C/O fever x 3 days` / `C/O: fever x 5 days` | preserved |
| `Dolo 650`, `BD x 5 days`, `1-0-1`, `Paracetamol 500 mg` | preserved |
| `Parkinson's disease`, `Addison's disease` | preserved |
| `Shahid sahab ka BP 117/82` | name removed, `sahab ka BP 117/82` preserved |
| `S/o Zubair` | relative name removed |
| `Patient ko fever hai` | unchanged |
| `Referred by ASHA worker`, `Ward 9 (Medicine)`, hospital names | preserved |

## 6. Cross-channel propagation

The index holds full-name phonetic sequences, *identifying* single name tokens (≥ 3 letters, not generic
such as Devi/Kumar/Singh/Md, not common or clinical words, capitalised or Devanagari in content), exact
token sequences (IDs, e-mails, PAN, insurance, multi-token villages), and digit cores (phone last 10,
Aadhaar 12, ABHA 14, MRN cores ≥ 5 digits; ≥ 6 or zero-padded in content). Separators never matter:
`Orvila_Tamsen` = `Orvila Tamsen`, `TST-26-004417` = `TST/26/004417`. Tested channels: notes, filenames,
metadata paths, JSON keys, CSV headers, base64 payloads (`tests/integration/test_propagation.py`), with
negative tests for common words (`Asha workers`, `Rose water`, `Om Sai`) and short tokens.

## 7. Confidence and redaction policy

Redact at ≥ 0.70. Seed the index at ≥ 0.88 (field, label, validated evidence only). Field values 0.90–0.97;
validated identifiers 0.90–0.97; labels 0.85–0.92; context 0.80–0.85; gazetteer pair 0.75 (single
gazetteer token 0.60, never redacted); unlabelled ID shapes 0.60 (reported only). Placeholders are
`[NAME]`, `[RELATIVE]`, `[PHONE]`, `[EMAIL]`, `[AADHAAR]`, `[ABHA]`, `[PAN]`, `[MRN]`, `[INSURANCE_ID]`, `[HOUSE]`,
`[LOCALITY]`, `[LANDMARK]`, `[VILLAGE]`, `[PIN]`, `[DOB]`. Filenames use the bare words. JSON numbers become `0`.

## 8. Measured results (practice data, 200 files, identical inputs)

| Metric | Phase 1 baseline | Phase 2 |
|---|---:|---:|
| `check_dev.py` PII still visible | 2714 / 3230 (84.0%) | **0 / 3230 (0.0%)** |
| official-style leak (`dev_eval.py`: name tokens, digit cores, exact text, DOB) | not measured | **0 / 3230 (0.0%)** |
| Latin / Devanagari / Hinglish leak (`check_dev.py`) | 82.7% / 100% / 100% | 0.0% / 0.0% / 0.0% |
| base64 channel leak | 90.0% | 0.0% |
| filename / header / key / metadata leak | 100% each | 0.0% each |
| canaries found in output (`check_dev.py` counts *leaked* canaries) | 4 / 4 | **0 / 4** |
| medical preserve probes kept | 4855 / 4855 | **4855 / 4855** |
| non-PII token retention (over-redaction detector) | n/a | **29732 / 29740 (100.0%)** |
| raw copies of broken files | 0 | 0 |
| linking F0.5 | 0.00 | 0.00 (Phase 3) |

Detection summary (`logs/detection_summary.json`, counts only): 3,350 findings, all applied. By evidence:
field semantics 2,041, address structure 332, validated pattern 318, label 278, propagation 259, context
122. By channel: content 3,205, filename 48, metadata 48, base64 29, key 12, header 8. By language of the
span: Latin 2,500, Devanagari 173, Hinglish 151, none (numeric-only spans) 526. 55 candidates were
discarded by clinical/doctor protection (this document originally said 96. Re-running the committed Phase 2
code gives 55, and Phase 2.1 gives the same), and 1 clinical conflict was overridden by strong evidence.
39 files were renamed.

### Ablation: without cross-file propagation

With an empty value index (contextual detection plus document-local propagation only): **43 / 3230 (1.3%)**
leaked (24 MRN, 19 PATIENT_NAME; all Latin; 50% of the dynamic-key channel). Contextual detection carries
about 98.7%. Run-wide propagation closes the rest, so it is load-bearing on data where a person appears
in a structured registration somewhere in the release.

### Generalisation: unseen-style synthetic data

`tests/generalization/synth.py` generates seeded datasets with invented names absent from the gazetteer,
header and key vocabularies never seen in practice data, new ID prefixes (`SVH-26-`, `RMC/2026/`, `KGM2026-`,
`CHC/UNN/`), new phone formats and Devanagari digits, and PII moved into filenames, metadata paths, dynamic
keys, base64 payloads, CSV headers, visitor logs and WhatsApp forwards.

| Run | PII values leaked | Clinical values kept |
|---|---:|---:|
| first measurement (before fixes) | 55 / 600 (9.2%) | 55 / 55 |
| after fixes, 10 seeds | **0 / 1200 (0.0%)** | **110 / 110** |

The first measurement exposed three real generalisation bugs: `D.O.B.` headers, `exported_from` paths
classified as staff, and invented surnames fuzzy-matching schema words in dynamic keys. All three are
fixed and pinned by tests. **Caveat:** this generator was written by the same team after studying the
practice data. It tests renamed vocabularies and moved channels, but it is no substitute for the sealed
chaos dataset.

## 9. Performance

| Input | Wall time | Peak RSS |
|---|---:|---:|
| practice (200 files) | 1.63 s | 31 MB |
| practice × 10 (2,000 files) | 14.6 s | 39 MB |

Linear time, flat memory (two passes re-read files rather than holding documents). Detection is about
5× the Phase 1 cost. Budget: 15 min / 4 GB.

## 10. Known failure cases and limitations

- **Free-text names with no cue at all** (no label, honorific, marker, phone, timeline, gazetteer pair)
  that never appear in a structured field are missed. The ablation shows this is where the residual risk
  lives.
- **Short or common-word names** (`Om`, `Ram`, lowercase `asha`) are deliberately not propagated as single
  tokens. A patient whose only mention is such a token in unmarked prose may leak.
- **Gazetteer** covers common pan-Indian names only. It is evidence, never sufficient alone.
- **Phonetic keys can collide** for very short names. Full-name propagation requires all tokens to match;
  single-token propagation uses exact keys only.
- **ID formats** without a label, a known shape (UHID/IPD/ADM/IP), a field, a loose channel or prior
  confirmation stay below threshold (bill and visit numbers are intentionally kept).
- **Addresses**: an unlabelled segment inside an address becomes VILLAGE/LOCALITY, so an unknown district
  written without `Distt.` would be redacted (over-redaction, not a leak). UP districts (Latin and, since
  2.1, Devanagari) plus states and major cities are known.
- **DOB** is replaced by `[DOB]` (FHIR `birthDate` keeps only the year so it stays a valid FHIR date). This
  is an interim treatment; Phase 4 replaces it with per-patient shifted dates.
- **XML / PDF / images** are still quarantined, not parsed. Since 2.1 a binary *attachment* inside JSON/FHIR
  is withheld (its `data` removed) instead of quarantining the whole file.
- **Nested base64** (base64 inside a decoded payload) is not scanned. Hex and `\uXXXX` inside plain text are
  not decoded (2.1 decodes XHTML, HTML entities, %-escapes and URL-safe/short base64).

## 11. Deferred work

- **Phase 3:** pseudonyms written into records and `records.jsonl`, using the IR plus name keys and the
  identifier findings as evidence (name-key matches only corroborate).
- **Phase 4:** per-patient date shifting (all dates, incl. DOB), age bands, village → tehsil/district and
  PIN → 3-digit generalisation, k-anonymity and rare-diagnosis suppression. Phase 2 findings already
  classify DOB, AGE-bearing fields, VILLAGE and PIN for that layer.

## 12. Lexicon provenance and licences

All vocabularies in `detection/lexicon.py` (honorifics, kinship terms, clinical vocabulary, drug and
disease words, Uttar Pradesh districts, common Indian given names and surnames) and the Devanagari label
map in `detection/semantics.py` were written by the CLINVEIL team from general knowledge. District names
are public administrative names. No external corpus, model or dataset is bundled, and nothing was
extracted from the practice data or its answer key.

**Contamination check (done, with the result).** The given-name and surname lists were written after the team
had read practice records, so exposure could have shaped them. We measured the overlap: 87 of the 142
practice patient/relative/canary name tokens were in the gazetteer. Those 87 tokens, and 6 further tokens of practice *doctor* names, were **removed** (198 given
names and 47 surnames remain). The removed tokens are not listed anywhere in the repository. Re-measured after
removal: still 0/3230 leaked, 0/4 canaries, 4855/4855 probes. The practice results therefore never depended on
the gazetteer (no gazetteer-only finding survived resolution in the detector statistics). The cost is a weaker
gazetteer for hidden data that reuses common names; context detection and propagation are unaffected. No runtime dependency was added: the engine is still
standard-library only.
