# CLINVEIL backend

The privacy engine. The evaluator runs it through the repository-root `main.py` (see
`raksha.toml`). That shim puts `backend/src` on `sys.path` and calls `clinveil.cli.main`.
No package install is needed at evaluation time.

## Responsibilities

Turn an untrusted input tree into a research release (`sanitized/`, `report.json`, `records.jsonl`)
that is PII-free, clinically faithful, consistently pseudonymised, structurally valid and
byte-deterministic. Fully offline, standard library only.

## Module map

| Package | Responsibility | Key files |
|---|---|---|
| `cli.py` | argument contract, secret and policy loading, exit codes, PII-free fatal errors | |
| `pipeline.py` | orchestration: discover, guard, decode, sanitise, export, self-check | |
| `config/` | `Policy` from `config/policy.yaml` (flat `key: value`) | `policy.py` |
| `ingestion/` | sorted discovery, symlink and size flags, streamed hashing, decoding | `discovery.py`, `decoding.py` |
| `parsing/` | CSV/TSV and JSON structure, record locators | `csv_format.py`, `json_format.py` |
| `detection/` | detectors emit typed `Finding`s (Phase 2); starter regex today | `baseline_regex.py` |
| `linking/` | cross-document identity resolution (Phase 3) | `linker.py` |
| `privacy/` | HMAC pseudonyms, per-patient date shifts, generalisation | `pseudonym.py`, `generalize.py` |
| `sanitization/` | per-format processors that apply decisions while preserving structure | `processors.py` |
| `export/` | release writers (byte formatting matches the starter) | `release.py` |
| `security/` | `ReleaseSecret`, reason codes, path containment | `secrets.py`, `errors.py`, `paths.py` |
| `validation/` | pre-exit release check (false-success guard) | `contract.py` |
| `models/` | `Finding`, `RecordRef` | `findings.py`, `records.py` |
| `metrics/` | development metrics (Phase 6) | |
| `utils/` | peak RSS | `resources.py` |

## CLI

```bash
RAKSHA_SECRET=... python main.py --input IN --output OUT [--policy config/policy.yaml]
```

## Tests

```bash
cd backend
../.venv/bin/pytest                    # everything
../.venv/bin/pytest -m "not toolkit"   # without the organiser toolkit checkout
../.venv/bin/pytest tests/security     # one suite
```

| Suite | Covers |
|---|---|
| `unit/` | pseudonyms (A6 and A7 properties), date shifts, age bands, decoding, parsing, policy, security primitives |
| `integration/` | full CLI on a synthetic tree: statuses, reasons, locators, UTF-8, official validator |
| `regression/` | **byte parity with the official starter**, determinism, meaning and language trap spec |
| `security/` | secret never written, PII-free channels, input untouched, symlinks, size cap, fail-closed |

`xfail(strict=True)` marks a *known* gap. When a phase fixes it, the test XPASSes, the suite fails,
and the marker must be removed, so the suite always states exactly what the engine can do.
`test_starter_parity.py` is deleted deliberately at the first change meant to alter output.

All fixtures are synthetic and written for the tests. Practice data is read from
`../organiser-toolkit` (or `CLINVEIL_TOOLKIT`) and never copied into this repository.

## Development workflow

1. Create a branch per task.
2. Write a failing test first. For detection work, add cases to `tests/regression/test_contextual_detection.py`.
3. Run `pytest`, `ruff check`, `ruff format` and `scripts/official_checks.sh`.
4. Record the before and after `check_dev.py` numbers in the PR description.
5. Never print, log or put record content, file names or the secret into an exception message.
