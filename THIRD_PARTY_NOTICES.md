# Third-party notices

CLINVEIL is **not** released under an open-source licence. Original CLINVEIL material is
protected by default copyright, and no general permission to use, copy, modify, redistribute or
commercialise it is granted (see [README.md § Copyright and licensing](README.md#copyright-and-licensing)).

This repository also contains portions adapted from third-party software. Those portions remain
under their **own** licences, which are reproduced in full in [`third_party_licenses/`](third_party_licenses/).
A third-party licence applies only to the third-party portions. It does **not** extend to original
CLINVEIL code in the same files or elsewhere in the repository.

---

## 1. Secret Wards team kit (Yugaantar DevForge, Track 3)

| | |
|---|---|
| Copyright | Copyright (c) 2026 kartikeyajay2006 |
| Licence | MIT. Full text: [`third_party_licenses/secret-wards-toolkit.MIT.txt`](third_party_licenses/secret-wards-toolkit.MIT.txt) |
| Upstream | `https://github.com/Reinforce-SST/Secret-Wards-ToolKit` (the kit's own docs also reference `https://github.com/kartikeyajay2006/Secret-Wards`) |
| Version used | commit `6c0a85a` ("Final review: keep sealed details out of the public kit") |
| Material reused | `starter/main.py`, `starter/raksha.toml`, `starter/config/policy.yaml`, `.github/workflows/kit-check.yml` |

The starter's single file `starter/main.py` was **split, reorganised and modified** into the modules
below. Some functions are reproduced verbatim or near-verbatim (marked "verbatim"); others were
restructured or extended with CLINVEIL code (marked "adapted"). Each listed source file carries a
header comment pointing to this notice.

| CLINVEIL file | Derived from (`starter/main.py` unless noted) | Extent |
|---|---|---|
| `backend/src/clinveil/privacy/pseudonym.py` | `pseudonym()`, `date_shift_days()`, `shift_date()`, `_ALPHABET` | derivations verbatim; wrapped in a class with an injected secret |
| `backend/src/clinveil/privacy/generalize.py` | `age_band()` | adapted (explicit width, negative-age check) |
| `backend/src/clinveil/detection/baseline_regex.py` | `PATTERNS`, `clean_text()` | verbatim patterns; adapted function |
| `backend/src/clinveil/ingestion/decoding.py` | `decode()` | verbatim logic |
| `backend/src/clinveil/ingestion/discovery.py` | sorted `rglob` file walk in `main()` | adapted (symlink, size and streamed-hash additions are original) |
| `backend/src/clinveil/parsing/csv_format.py` | CSV read/write in `process_csv()` | adapted |
| `backend/src/clinveil/parsing/json_format.py` | record detection and JSON-pointer escaping in `process_json()` | adapted |
| `backend/src/clinveil/sanitization/processors.py` | `clean_value()`, `process_csv()`, `process_json()`, `process_text()`, `Stats` | adapted |
| `backend/src/clinveil/export/release.py` | `report.json` / `records.jsonl` construction in `main()` | adapted |
| `backend/src/clinveil/pipeline.py` | per-file loop, quarantine handling and record filtering in `main()` | adapted (guards and self-check are original) |
| `backend/src/clinveil/security/errors.py` | quarantine-reason expression in `main()` | adapted (allowlist and type-name rule are original) |
| `backend/src/clinveil/config/policy.py` | `load_policy()` | adapted (typed `Policy`, validation) |
| `backend/src/clinveil/utils/resources.py` | `peak_rss_mb()` | verbatim |
| `backend/src/clinveil/cli.py` | `--input` / `--output` argument handling in `main()` | adapted |
| `raksha.toml` | `starter/raksha.toml` | adapted (team name, comments) |
| `config/policy.yaml` | `starter/config/policy.yaml` | adapted (first three keys and their comments; `max_file_bytes` is original) |
| `.github/workflows/ci.yml` | `.github/workflows/kit-check.yml` | adapted (step pattern; lint, test, matrix and secret handling are original) |

Not copied: the organiser's practice dataset, answer key (`dev/truth/`), attacker material
(`dev/attacker/`), validators and documentation. Tests and scripts **invoke** the organiser's
validators from a separate, git-ignored checkout. They are not included in this repository.
Documentation in `docs/` summarises and cites the organiser's published rules; it does not reproduce
them.

**Licence condition:** the MIT licence requires that its copyright notice and permission notice be
included in all copies or substantial portions of that software. Anyone redistributing the files
above must keep this notice and `third_party_licenses/secret-wards-toolkit.MIT.txt` with them.

---

## Adding third-party material

Before merging any copied or adapted third-party code: confirm that its licence permits the use, add the
verbatim licence to `third_party_licenses/`, add a row to this file, and put a header comment in each
affected file. Runtime dependencies installed by `pip` are not vendored and are not listed here.
Record them in `requirements.txt` and `docs/decisions/TECHNICAL_DECISIONS.md`.
