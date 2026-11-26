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
| `pipeline.py` | two passes: (1) seed the value index; (2) detect format, build IR, analyse, rename, sanitise, render, export, self-check | |
| `config/` | `Policy` from `config/policy.yaml` (flat `key: value`) | `policy.py` |
| `ingestion/` | sorted discovery, symlink and size flags, streamed hashing; content-based detection; validated decoding; limits | `discovery.py`, `detect.py`, `signatures.py`, `decoding.py`, `plausibility.py`, `limits.py` |
| `parsing/` | the common IR builder; CSV/TSV, bounded JSON, FHIR enumeration, base64 payloads | `builder.py`, `csv_format.py`, `json_format.py`, `json_safety.py`, `fhir.py`, `attachments.py` |
| `detection/` | Phase 2 engine: semantics, validated identifiers, contextual names, addresses, clinical protection, value-index propagation, resolution | `engine.py`, `semantics.py`, `identifiers.py`, `names.py`, `addresses.py`, `clinical.py`, `value_index.py`, `resolve.py`, `text.py`, `translit.py`, `lexicon.py` |
| `linking/` | cross-document identity resolution (Phase 3) | `linker.py` |
| `privacy/` | HMAC pseudonyms, per-patient date shifts, generalisation | `pseudonym.py`, `generalize.py` |
| `sanitization/` | finding application (placeholders, numbers → 0, FHIR birthDate → year), payload re-encoding, path renaming, renderers | `processors.py`, `render.py` |
| `export/` | release writers (byte formatting matches the starter) | `release.py` |
| `security/` | `ReleaseSecret`, reason codes, path containment | `secrets.py`, `errors.py`, `paths.py` |
| `validation/` | pre-exit release check (false-success guard) | `contract.py` |
| `models/` | the IR (`Document`, `Field`, `SourceFile`, FHIR index), `Channel`, typed offset-only `Finding` (`Evidence`, `Action`, `EntityType`), `RecordRef` | `document.py`, `channels.py`, `findings.py`, `records.py` |
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
| `unit/` | detection layers (Unicode offsets, transliteration, about 90 renamed/Hindi labels, identifiers incl. Verhoeff, contextual names, addresses, value index, resolution), pseudonyms, date shifts, encodings, content detection, JSON safety, base64, FHIR, IR, policy, security primitives |
| `integration/` | full CLI on synthetic trees: statuses, reason codes, locators, attachments, base64-aware leak scan, cross-channel propagation (notes, filenames, metadata, keys, headers, payloads), no over-propagation, report/log counts |
| `regression/` | practice-data release (misc outcomes, CSV/JSON/FHIR structure, renames, official `check_dev.py` thresholds), determinism, meaning-trap spec incl. the mandatory Phase 2 cases |
| `generalization/` | seeded unseen-style datasets (invented names, renamed headers, new ID/phone formats, PII in alternate channels) through the real CLI |
| `security/` | secret never written, PII-free channels, input untouched, symlinks, size cap, fail-closed |

`xfail(strict=True)` marks a *known* gap. When a phase fixes it, the test XPASSes, the suite fails,
and the marker must be removed, so the suite always states exactly what the engine can do.
`test_phase2_release.py` replaced the Phase 1 delta test: Phase 2 legitimately changes most outputs, so it pins
structure and the official checker's thresholds instead of byte deltas.

```bash
python backend/scripts/dev_eval.py --output OUT   # official-style token/digit-core leak, probes, token retention (dev only)
```

All fixtures are synthetic and written for the tests. Practice data is read from
`../organiser-toolkit` (or `CLINVEIL_TOOLKIT`) and never copied into this repository.

## Development workflow

1. Create a branch per task.
2. Write a failing test first. For detection work, add cases to `tests/regression/test_contextual_detection.py`.
3. Run `pytest`, `ruff check`, `ruff format` and `scripts/official_checks.sh`.
4. Record the before and after `check_dev.py` numbers in the PR description.
5. Never print, log or put record content, file names or the secret into an exception message.
