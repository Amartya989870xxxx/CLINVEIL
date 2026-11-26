# CLINVEIL

**Privacy infrastructure for trusted medical data sharing.**

CLINVEIL is an offline, CPU-only, deterministic de-identification engine for messy,
multilingual Indian hospital exports. It removes personal data, keeps clinical values exactly
intact, gives each real patient one stable keyed pseudonym across files and scripts, and resists
re-identification by an attacker holding a voter-roll-style register.

Built by team **APEX** for **Yugaantar DevForge · Track 3 · Secret Wards**. All data handled in development and
demonstration is **synthetic**. No real patient data is used or permitted anywhere in this project.

> **Status: Phase 2 (multilingual, context-aware PII detection).** Layered detection over the Phase 1
> representation: semantic field classification (renamed and Hindi labels), validated Indian identifiers,
> contextual Latin/Devanagari/Hinglish names and relatives, address components, clinical and doctor
> protection, and run-wide propagation of confirmed values into notes, filenames, keys, headers, metadata and
> base64 payloads. On the practice data, `check_dev.py` shows 0/3230 PII visible, 0/4 canaries and 4855/4855
> medical values kept. These are development measurements, not an official score. **Not yet done:** patient
> linking (Phase 3) and quasi-identifier generalisation (Phase 4).
> Measured: [Phase 0](docs/evaluation/BASELINE.md) · [Phase 1](docs/evaluation/PHASE1_INGESTION.md) ·
> [Phase 2](docs/evaluation/PHASE2_DETECTION.md).
> Roadmap: [docs/architecture/IMPLEMENTATION_PLAN.md](docs/architecture/IMPLEMENTATION_PLAN.md).

## The challenge

Four hospital systems export registrations (CSV, UTF-16 TSV, cp1252 legacy CSV, nested JSON), OPD
visits, discharge summaries, Hindi prescriptions, Hinglish nursing notes, lab reports, WhatsApp
forwards, FHIR R4 Bundles, billing claims and deliberately broken files. The same patient appears as
"Mohammad Arif", "मोहम्मद आरिफ" and "Arif sahab". PII hides in file names, CSV headers, JSON keys,
export metadata and base64 attachments. The output is scored on privacy against automated attacks
(25), detection across three scripts (20), clinical utility (20), identity consistency (15),
output validity (10) and speed and reliability (10). Over-redaction is penalised through the utility
coupling, so deleting everything scores only about 20/100.

## Architecture

```
            ┌──────────────────────────── evaluator sandbox: no network, 2 CPU, 4 GB ────────────────────────────┐
 {input}/ ─►│ ingestion ─► parsing ─► detection ─► linking ─► privacy ─► sanitization ─► export ─► self-check   │─► {output}/
 (read-only)│  discover     CSV/TSV    findings     evidence   HMAC psn    per-format     report     validate   │    sanitized/
            │  guard        JSON/FHIR  (typed,      blocking   date shift  structure-     records    before     │    report.json
            │  decode       text       no edits)    clusters   generalise  preserving     .jsonl     exit 0     │    records.jsonl
            └─────────────────────────────────────────────────────────────────────────────────────────────────────┘
                   RAKSHA_SECRET (env only) ──► privacy keys; never written, logged or repr'd
```

Full design: [docs/architecture/SYSTEM_ARCHITECTURE.md](docs/architecture/SYSTEM_ARCHITECTURE.md).

| Stage | Module | Current state |
|---|---|---|
| Ingestion | `clinveil.ingestion` | deterministic discovery, symlink and size guards; content-based detection (signatures, JSON-first, markup, delimiter sniffing); UTF-8/BOM/UTF-16 (incl. BOM-less)/cp1252 with mojibake and binary checks |
| Parsing | `clinveil.parsing` | common IR (`Document`/`Field`: address, path, record, channel, kind, label); bounded JSON (depth 64, size, nodes); FHIR roles, entries and reference resolution; declared and embedded base64 payloads |
| Detection | `clinveil.detection` | semantics, validated identifiers, contextual names, addresses, clinical protection, value-index propagation; typed offset-only `Finding`s |
| Linking | `clinveil.linking` | interface only, links nothing (safe: a wrong link costs more than none) |
| Privacy | `clinveil.privacy` | HMAC pseudonyms, per-patient date shift, age bands (helpers, not yet applied) |
| Sanitisation | `clinveil.sanitization` | findings → typed placeholders; numbers → 0; FHIR birthDate → year; payloads re-encoded; PII paths renamed |
| Export | `clinveil.export` | `report.json`, `records.jsonl`, contained writes |
| Security | `clinveil.security` | unprintable secret, PII-free reason codes, path containment |
| Validation | `clinveil.validation` | in-process release check before exit 0 |

## Installation

Requires Python 3.10+. The runtime uses **only the standard library**.

```bash
git clone https://github.com/Amartya989870xxxx/CLINVEIL.git && cd CLINVEIL
pip install -r requirements.txt            # evaluator `setup` (currently a no-op)

# development
python3 -m venv .venv && .venv/bin/pip install -e "backend[dev]"
git clone https://github.com/Reinforce-SST/Secret-Wards-ToolKit.git organiser-toolkit   # git-ignored
```

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `RAKSHA_SECRET` | **yes** | per-release key for pseudonyms and date shifts. The run **fails closed** (exit 2) without it. Never commit, print or store it. |
| `CLINVEIL_POLICY` | no | alternative policy file (default `config/policy.yaml`) |
| `CLINVEIL_TOOLKIT` | dev only | organiser toolkit location for tests (default `./organiser-toolkit`) |

No default secret exists anywhere in the code. `practice` in examples is the organiser's public
practice value, not a release secret.

## Running

```bash
RAKSHA_SECRET=<secret> python main.py --input <input dir> --output <empty output dir>
```

This matches `raksha.toml`. Exit codes: `0` complete release, `1` incomplete release or fatal
error, `2` usage error (missing secret, overlapping directories). stdout and stderr carry counts only.

## Testing and official validation

```bash
cd backend && ../.venv/bin/pytest            # unit, integration, regression, security
../.venv/bin/ruff check src tests ../main.py

backend/scripts/official_checks.sh           # run + validate_output.py + check_dev.py
backend/scripts/official_checks.sh --submit  # + check_submission.py --run
```

The organiser's `validate_output.py`, `check_dev.py` and `check_submission.py` are used
**unmodified** from `organiser-toolkit/`.

## Models and dependencies

**No models are used.** No LLM, no generative model, no pretrained transformer, no hosted API, no
network access at runtime. Any future model or dependency must be declared here and in
[docs/decisions/TECHNICAL_DECISIONS.md](docs/decisions/TECHNICAL_DECISIONS.md), and must meet the
competition limits (offline, CPU, no model above 50M parameters).

## Security design (summary)

Every input is untrusted. Symlinks leaving the input root and oversized files are quarantined
unparsed. Any per-file failure quarantines that file, and the recorded reason is a fixed code or an
exception *type name*, never a message, because messages can echo PII. The secret is wrapped in a type
that refuses to print or pickle. Findings and file handles hide their raw text from `repr`. Nothing is
logged except counts. No intermediate files are written. The process refuses an output directory that
overlaps its input. Full model: [docs/security/THREAT_MODEL.md](docs/security/THREAT_MODEL.md).

## Known limitations (Phase 2)

- No patient linking yet (Phase 3). Output therefore does not depend on the secret, and `check_submission.py`
  warns about this.
- No date shifting, age banding, location generalisation or rare-value suppression (Phase 4). DOB is replaced
  by `[DOB]`; FHIR `birthDate` keeps only the year so it stays valid.
- Names with no context cue that never appear in a structured field can be missed. With cross-file
  propagation disabled, the practice-data leak rises to 1.3%. See
  [PHASE2_DETECTION.md](docs/evaluation/PHASE2_DETECTION.md) for all known failure cases.
- A file with an unsupported (binary) attachment is quarantined whole. XML, PDF and images are quarantined, not parsed.

## Repository layout

```
raksha.toml  main.py  requirements.txt  config/policy.yaml   ← evaluator contract (root, required)
backend/   src/clinveil/ (engine), tests/, scripts/, docs/
frontend/  research dashboard (placeholder, optional, never on the evaluator path)
docs/      architecture/ decisions/ api-contract/ security/ evaluation/ team/
organiser-toolkit/   official kit, git-ignored, never modified
```

## Copyright and licensing

CLINVEIL is a product of team **APEX** (the team name registered for Secret Wards).

**No open-source licence is granted for CLINVEIL.** Original CLINVEIL material is
Copyright © 2026 its respective contributors, all rights reserved. Making this repository
public (as the hackathon requires) lets people view it. It does **not** grant permission to use,
copy, modify, redistribute, sublicense or commercialise it, except where applicable law or
GitHub's Terms of Service (which let users view and fork public repositories on GitHub) already
allow it. Evaluation by the event organisers is covered by the hackathon's submission terms.

**Third-party portions keep their own licences.** Parts of the backend are adapted from the
organisers' Secret Wards starter (MIT, Copyright (c) 2026 kartikeyajay2006). The files concerned, the
extent of reuse and the full MIT text are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[third_party_licenses/](third_party_licenses/). That MIT licence applies to those portions only.

**Contributor IP:** no contributor licence or IP-assignment agreements exist yet. Contributors
retain whatever rights they hold in their own contributions. Ownership and assignment must be settled
in writing before CLINVEIL is commercialised (see [CONTRIBUTING.md](CONTRIBUTING.md#contributions-and-intellectual-property)).

**History note:** commit `59c0ea8` (the first published commit) contained an MIT `LICENSE` file. It
was removed in a later commit, and the published history was deliberately not rewritten.
