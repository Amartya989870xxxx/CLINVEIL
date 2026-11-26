# CLINVEIL

**Privacy infrastructure for trusted medical data sharing.**

CLINVEIL is an offline, CPU-only, deterministic de-identification engine for messy,
multilingual Indian hospital exports. It removes personal data, keeps clinical values exactly
intact, gives each real patient one stable keyed pseudonym across files and scripts, and resists
re-identification by an attacker holding a voter-roll-style register.

Built for **Yugaantar DevForge · Track 3 · Secret Wards**. All data handled in development and
demonstration is **synthetic**. No real patient data is used or permitted anywhere in this project.

> **Status: Phase 0 (foundation).** The pipeline is currently a modular, hardened refactor of the
> official starter. It is byte-identical to the starter on the practice data and passes
> `CONTRACT OK`, but it does **not** yet do real detection, linking or quasi-identifier handling.
> Measured baseline: [docs/evaluation/BASELINE.md](docs/evaluation/BASELINE.md).
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

| Stage | Module | Phase 0 state |
|---|---|---|
| Ingestion | `clinveil.ingestion` | deterministic discovery, symlink and size guards, UTF-8/BOM/UTF-16/cp1252 decoding |
| Parsing | `clinveil.parsing` | CSV/TSV (delimiter and header kept), JSON record locators (RFC 6901) |
| Detection | `clinveil.detection` | starter regex baseline only; typed `Finding` model defined |
| Linking | `clinveil.linking` | interface only, links nothing (safe: a wrong link costs more than none) |
| Privacy | `clinveil.privacy` | HMAC pseudonyms, per-patient date shift, age bands (helpers, not yet applied) |
| Sanitisation | `clinveil.sanitization` | per-format processors |
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

## Known limitations (Phase 0)

- Leaks about 84% of practice PII (all Devanagari and Hinglish names, relatives, MRNs, addresses,
  hidden channels) and all 4 practice canaries.
- Links no records. Output therefore does not depend on the secret, and `check_submission.py` warns about this.
- No date shifting, age banding, location generalisation or rare-value suppression is applied yet.
- No filename, header, key, metadata or base64 sanitisation. File extensions are trusted.
- FHIR validity is not actively maintained beyond preserving the JSON structure.

## Repository layout

```
raksha.toml  main.py  requirements.txt  config/policy.yaml   ← evaluator contract (root, required)
backend/   src/clinveil/ (engine), tests/, scripts/, docs/
frontend/  research dashboard (placeholder, optional, never on the evaluator path)
docs/      architecture/ decisions/ api-contract/ security/ evaluation/ team/
organiser-toolkit/   official kit, git-ignored, never modified
```

## Licence

MIT. See [LICENSE](LICENSE).
