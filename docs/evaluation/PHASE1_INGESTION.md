# Phase 1: reliable ingestion (measured results)

Measured 2026-11-26 on branch `phase-1-ingestion`, macOS (Darwin 27), Python 3.13.7, toolkit
commit `6c0a85a`. Practice data: 200 files. **No official score was computed** (the evaluator is sealed).

## What changed in the output versus the Phase 0 / starter baseline

Pinned by `backend/tests/regression/test_phase1_delta.py`. Every other file is byte-identical to the
official starter's output.

| File(s) | Phase 0 | Phase 1 | Why |
|---|---|---|---|
| `misc/mislabeled_export.csv` (JSON content) | parsed as CSV: JSON mangled into a header row, Aadhaar leaked | detected as JSON, exported as JSON, Aadhaar redacted by the baseline rule | content beats extension |
| `misc/corrupt_bytes_note.txt` (invalid UTF-8, mid-file `FF FE`) | "decoded" as cp1252, exported as mojibake | quarantined `implausible_text` | decode plausibility |
| `misc/deep_export.json` (1,502 levels) | processed via a raised recursion limit | quarantined `json_too_deep` (limit 64; practice FHIR peaks at 11) | explicit nesting limit |
| 9 FHIR Bundles with `DocumentReference` attachments; `misc/scanned_consent_form.json` | base64 payloads exported raw | payload decoded, cleaned by the (baseline) sanitiser, re-encoded; **only the `data` leaf changes** | attachment pipeline |
| PDF / JPEG / XML / empty / truncated JSON | quarantined `unsupported_format` / `empty_file` / `JSONDecodeError` | quarantined `unsupported_pdf` / `unsupported_image` / `unsupported_xml` / `empty_file` / `invalid_json` | specific, stable reason codes |

## Practice `misc/` outcomes

| File | Outcome | Reason |
|---|---|---|
| README_export.txt | sanitized (clean text) | |
| ambulance_log.csv | sanitized | |
| corrupt_bytes_note.txt | quarantined | implausible_text |
| deep_export.json | quarantined | json_too_deep |
| empty_export.csv | quarantined | empty_file |
| helpdesk_tickets.json | sanitized | |
| hl7_cda_discharge.xml | quarantined | unsupported_xml |
| mislabeled_export.csv | sanitized **as JSON** | |
| patient_index.json | sanitized | |
| photo_rx.jpg | quarantined | unsupported_image |
| scanned_consent_form.json | sanitized (payload re-encoded) | |
| scanned_discharge.pdf | quarantined | unsupported_pdf |
| truncated_opd.json | quarantined | invalid_json |
| ward_vitals_sheet.csv | sanitized | |

All seven quarantined files are `expect: either` in the practice truth, so quarantining them is
accepted by the contract.

## Official tools (unmodified)

| Tool | Result |
|---|---|
| `validate_output.py` | **CONTRACT OK** |
| `check_submission.py --run` | **READY TO SUBMIT**, 1 warning in the working tree: output is secret-independent (expected until Phase 3/4). The "PDF found" line is a false positive from the nested toolkit; see the clean-clone run in the Phase 1 report |
| `check_dev.py` | see below |

### `check_dev.py`: Phase 0 → Phase 1

| Measure | Phase 0 | Phase 1 |
|---|---|---|
| PII still visible | 2718 / 3230 (84.1%) | **2714 / 3230 (84.0%)** |
| base64 channel leaked | 100% | **90.0%** |
| PHONE leaked | 25 / 308 | 24 / 308 |
| AADHAAR leaked | 2 / 71 | 1 / 71 |
| by script | latin 82.8%, deva 100%, hinglish 100% | latin 82.7%, deva 100%, hinglish 100% |
| canaries found | 4 / 4 | 4 / 4 |
| medical values kept | 4855 / 4855 | 4855 / 4855 |
| linking F0.5 | 0.00 | 0.00 |
| raw copies of broken files | 0 | 0 |

As expected, detection metrics barely move: Phase 1 changes *what reaches the sanitiser*, not the
sanitiser. Names inside decoded payloads still leak; that is Phase 2's job.

## Performance

| Input | Files | Wall time | Peak RSS |
|---|---:|---:|---:|
| practice data | 200 | 0.31 s | 27 MB |
| practice data ×10 (synthetic replication) | 2,000 | 2.76 s | 34 MB |

Time scales linearly, and memory stays flat because each file's IR is released after rendering.

## Tests

`pytest`: **164 passed, 7 xfailed** (the 7 strict xfails are the documented detection and linking gaps).
`ruff check` and `ruff format --check`: clean.
