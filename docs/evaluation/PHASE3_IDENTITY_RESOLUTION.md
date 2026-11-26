# Phase 3 Evaluation: Cross-Hospital Identity Resolution and Cryptographic Pseudonymisation

Branch: `phase-3-identity-resolution` (based on `main` at `9205b5a`).
Architecture & threat analysis: [PHASE3_IDENTITY_RESOLUTION.md](../architecture/PHASE3_IDENTITY_RESOLUTION.md).

All numbers below come from commands actually executed on 2026-11-27. Practice-dataset metrics are a
rough self-check, not an official hidden-dataset score (`organiser-toolkit/docs/SCORING.md`).

---

## 1. Practice Dataset Measurements (200 files, 822 records)

### Official Unmodified Validators & Self-Checks
| Command | Exit | Observed Result |
|---|---:|---|
| `python organiser-toolkit/validate_output.py --input organiser-toolkit/dev/input --output OUT` | 0 | `CONTRACT OK` |
| `python organiser-toolkit/check_dev.py --output OUT` | 0 | `PERSONAL DATA: 0 of 3230` (0.0% leaked across Latin/Devanagari/Hinglish and all 6 channels); `CANARIES: 0 of 4`; `MEDICAL DATA KEPT: 4855 of 4855` (100.0%); `PATIENT LINKING: precision 1.00, recall 0.99, F0.5 1.00 (pseudonyms that wrongly merge different people: 0)`; `RAW COPIES: 0` |
| `python backend/scripts/dev_eval.py --output OUT --truth organiser-toolkit/dev/truth/truth.json` | 0 | Fractional record-level leak `0.0/3226 (0.00%)`, canaries `0/8`, preserve probes `98.8%` (`4591` at field / `263` elsewhere / `1` lost), non-PII token retention `64228/64335 (99.8%)` |
| `python organiser-toolkit/check_submission.py --repo . --run` | 0 | **`READY TO SUBMIT`** (0 warnings, 0 failures): exit 0 in 2.2 s, `CONTRACT OK`, same-secret byte-identical, different-secret produces different output, `RAKSHA_SECRET` never written, input folder unchanged |

### Detailed Identity-Resolution Metrics (`SCORING.md` §2 & §5 definitions)
| Metric | Measured Value |
|---|---:|
| True positives (pairwise, required units) | `6,803` |
| False positives (pairwise, including ambiguous units) | `0` |
| False negatives (pairwise, required units) | `89` |
| Pairwise precision | `1.0000` |
| Pairwise recall | `0.9871` |
| Pairwise F0.5 | `0.9974` |
| B-cubed precision / recall / F1 | `1.0000` / `0.9873` / `0.9936` |
| Wrongly merged patients (false merges) | `0` |
| Language trap pair recall | `786 / 816` (`96.3%`) |
| Fragmented trap pair recall | `258 / 258` (`100.0%`) |
| Homonym separation | `2 / 2` (`100.0%`) |
| Pseudonym consistency (`records.jsonl` claims present in exported records) | `772 / 772` (`100.0%`) |
| Clusters resolved (ground-truth linkable components = `49`) | `49` (`22` of size 16+, `27` of size 5–15, `0` singletons) |
| Linked / unlinked records | `772` linked / `50` unlinked (`822` total) |
| Merges by evidence strength | `strong_scoped_id: 639`, `strong_global: 42`, `corroborated_name: 24`, `fragmented_unique: 18` |
| Merges blocked by hard conflict vetoes | `58` |
| Blocks capped as ambiguous | `0` |
| Pseudonym collisions resolved | `0` |

---

## 2. Synthetic, Adversarial, and Generalisation Suite

All test fixtures use 100% invented names, numbers, and hospital names (zero practice answer-key overlap,
verified by automated contamination scan: `0` hits across all Phase 3 source and test files).

- **`backend/tests/unit/test_linking.py`** (16 tests):
  - Cross-script strict name normalisation (Devanagari/Latin/Hinglish, schwa-only tolerance, abbreviations,
    order inversion, split-column reassembly).
  - Coarse-transliteration collision separation (`Kiran`/`Karan`, `Sita`/`Satya`, `Alok`/`Alka`, `Rohan`/`Mohan`,
    `Sunita`/`Anita`).
  - Verhoeff Aadhaar validation (rejects bad checksum and masked Aadhaar), ABHA, phone formats, hospital-scoped MRNs.
  - Hard conflict vetoes (family sharing phone, twins sharing surname/DOB/address/relative, homonyms, conflicting
    Aadhaar, cross-hospital generic `MRN-12345`).
  - Non-transitive clustering (A strongly matches B, B shares name+phone with C, A conflicts with C → never merged).
  - Pathological block capping (`MAX_NAME_BLOCK`), traversal-order independence across random permutations,
    collision counter re-derivation, secret sensitivity, redacting `repr`, unpicklability, and cache clearing.
- **`backend/tests/integration/test_phase3_identity_resolution.py`** (4 end-to-end suites):
  - 4-hospital cross-format/cross-script suite (CSV BOM, UTF-16 TSV, JSON OPD, FHIR R4 Bundle, Hinglish note,
    external lab JSON) + all false-merge traps + 5 ambiguous record types (first name only, initials only,
    phone only, address only, name+village without age/DOB/relative) + side-channel & secret hygiene.
  - Same-secret determinism and different-secret unlinkability across `sanitized/` and `records.jsonl`.
  - FHIR R4 `RelatedPerson`, `Practitioner` exclusion, `contained` Patient, nested Bundle, and multi-patient
    conflicting Bundle abstention (`patient: null`).
  - Unseen-schema generalisation & 1,000-record scaling (200 invented patients × 5 records across unseen headers
    and hospital names): `200/200` patients linked cleanly, `0` false merges.

---

## 3. Multi-Version Test Suite & Scaling Performance

| Check | Result |
|---|---|
| `ruff check` & `ruff format --check` | Clean (0 errors, 99 files formatted) |
| Full `pytest` on Python 3.10 (`uv`) | **766 passed**, 0 failed, 0 xfailed (20.04 s) |
| Full `pytest` on Python 3.12 (`uv`) | **766 passed**, 0 failed, 0 xfailed (18.03 s) |
| Full `pytest` on Python 3.13 (`.venv`) | **766 passed**, 0 failed, 0 xfailed (20.31 s) |
| 1× practice dataset (200 files, 822 records) | **2.1 s** wall time, **37.9 MB** peak RSS (limit: 900 s / 4,096 MB) |
| 10× replica benchmark (2,000 files, 8,220 records) | **22.4 s** wall time, **113.7 MB** peak RSS (linear scaling; well within budget) |

---

## 4. Honest Status & Known Limitations

- **Implemented and tested:** IR evidence extraction, cross-script strict normalisation, hospital-scoped MRN
  namespacing, hard conflict vetoes, bounded blocking, 3-stage conflict-aware clustering, traversal-order-independent
  canonical cluster keys, domain-separated versioned HMAC-SHA256 pseudonyms (`psn|v1|...`) with collision counter
  re-derivation, schema-preserving in-record pseudonym placement (CSV/TSV/JSON/FHIR/text), `records.jsonl` export,
  and pre-exit pseudonym consistency self-checks.
- **Implemented but not independently verified on sealed data:** hidden-dataset and unseen-format official evaluator
  scores have not been run (evaluator is sealed).
- **Deferred to Phase 4:** per-patient keyed date shifting, DOB generalisation/shifting, 5-year age bands,
  village→tehsil/district generalisation, PIN 3-digit prefixing, and k-anonymity rare-cell suppression.
- **Known limitations:**
  - Python does not guarantee physical RAM wiping of cleared in-memory evidence structures.
  - Multi-patient single-document FHIR Bundles with conflicting `Patient` resources abstain (`patient: null`).
  - Records with insufficient corroborating evidence (name-only, initials-only, phone-only, address-only) are
    deliberately left unlinked (`null`) to protect precision.
