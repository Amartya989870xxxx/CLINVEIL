# Baseline (Phase 0)

Measured on 2026-11-26, macOS (Darwin 27), Python 3.13.7. Toolkit commit `6c0a85a`
(`Reinforce-SST/Secret-Wards-ToolKit`). Practice dataset: 200 files, 48 patients, 815 truth records.
**No official score was computed.** The official evaluator is sealed; `check_dev.py` is a rough guide only.

## Commands executed

```bash
# 1. official starter, unmodified, run from the toolkit
RAKSHA_SECRET=practice python3 starter/main.py --input dev/input --output <tmp>/baseline_out
python3 validate_output.py --input dev/input --output <tmp>/baseline_out
python3 check_dev.py --output <tmp>/baseline_out

# 2. CLINVEIL Phase 0 (refactored starter)
RAKSHA_SECRET=practice python3 main.py --input organiser-toolkit/dev/input --output <tmp>/cv_out
diff -r <tmp>/baseline_out/sanitized <tmp>/cv_out/sanitized          # identical
cmp     <tmp>/baseline_out/records.jsonl <tmp>/cv_out/records.jsonl  # identical
python3 organiser-toolkit/validate_output.py --input organiser-toolkit/dev/input --output <tmp>/cv_out
python3 organiser-toolkit/check_submission.py --repo . --run
cd backend && ../.venv/bin/pytest && ../.venv/bin/ruff check src tests ../main.py
```

## Results

| Check | Starter | CLINVEIL P0 |
|---|---|---|
| exit code | 0 | 0 |
| `validate_output.py` | CONTRACT OK | CONTRACT OK |
| `sanitized/` + `records.jsonl` | n/a | **byte-identical to starter** |
| `report.json` `files` + `counts` | n/a | identical (timing and RSS differ, as expected) |
| `check_submission.py --run` | n/a | READY TO SUBMIT, 1 warning (see below) |
| runtime / peak RSS (report.json) | 0.11 s / 38.9 MB | same order |
| pytest | n/a | 65 passed, 7 xfailed (documented gaps) |

### `check_dev.py` (identical for both, since outputs are byte-identical)

| Measure | Value |
|---|---|
| PII still visible | **2718 / 3230 (84.1%)** |
| by script | latin 82.8%, deva 100%, hinglish 100% |
| by hiding place | content 83.5%; filename, base64, metadata, key, header: 100% each |
| worst types | RELATIVE_NAME, VILLAGE, PIN, HOUSE, DOB, LOCALITY, LANDMARK, AADHAAR_MASKED 100%; MRN 96.1%; PATIENT_NAME 94.7% |
| caught well | PHONE 8.1% leaked, AADHAAR 2.8%, ABHA/PAN/EMAIL 0% |
| canaries | **4 / 4 found** (−12 officially) |
| medical values kept | 4855 / 4855 (100%), trivially, because almost nothing is removed |
| linking | P 0.00 / R 0.00 / F0.5 0.00 (nothing linked) |
| raw copies of broken files | 0 |

The organisers state the starter scores **about 8/100** with the official evaluator. We have not
reproduced that number (the evaluator is not public).

### Quarantine on practice data
5 files: 3 × `unsupported_format` (PDF, JPEG, XML), 1 × `empty_file`, 1 × `JSONDecodeError`
(truncated JSON).

## Known deficiencies (prioritised in IMPLEMENTATION_PLAN.md)

1. Detection is regex-only: no column semantics, no Devanagari or Hinglish names, no relatives, no MRN/UHID,
   no address parts, no hidden channels.
2. `misc/mislabeled_export.csv` (JSON content) is parsed as CSV and exported, which mangles the structure.
3. `misc/corrupt_bytes_note.txt` (invalid UTF-8) is "decoded" as cp1252 and exported as mojibake.
4. `misc/deep_export.json` (1,500 levels) is processed (not quarantined). That is acceptable, but it needs a depth policy.
5. No linking. Pseudonyms are not written inside records, so the output does not depend on the secret.
6. No date shifting, age bands, location generalisation or suppression is applied.
7. Filenames with PII (`Discharge_Summary_<name>_<UHID>.txt`, `<phone>_report_*.json`) are exported unchanged.
8. FHIR: narrative `text.div`, `meta.source` and `identifier` are not handled specifically.
9. `report.json` has no `entities` block (SPEC §5 example field; report-quality completeness).

## Evaluator observations and discrepancies

- **`check_submission.py` PDF false positive:** with `organiser-toolkit/` nested inside the working
  directory, it reports `organiser-toolkit/dev/input/misc/scanned_discharge.pdf` as the Project Brief.
  The toolkit is git-ignored, so a clean clone has no PDF. **The 2-page brief is still to be written.**
- **Expected warning:** "a different RAKSHA_SECRET gave identical output". This is resolved by Phase 3/4.
- Toolkit docs reference `github.com/kartikeyajay2006/Secret-Wards`; we used the URL supplied by the
  team, `github.com/Reinforce-SST/Secret-Wards-ToolKit` (same content, commit `6c0a85a`).
- `check_submission.py` runs with the caller's Python and network. Offline behaviour must also be tested
  separately (Phase 0 has no network code and no third-party runtime dependencies).

## Evaluation constraints (from the toolkit)

2 CPUs, 4 GB process-tree RSS (sampled every 50 ms), 15 min per run (`standard`: full speed credit
≤ 60 s, memory credit ≤ 512 MB), no network during `run`, read-only input (re-hashed),
`TMPDIR`/`HOME` scanned, 3 hidden datasets (≥ 1 unseen-format "chaos"), a repeat run with the same
secret (byte-identical) and one with a different secret (must differ).
