# Contributing to CLINVEIL

## Ground rules (competition and security)

1. **No LLMs or generative models**, hosted or local, anywhere in the engine. No pretrained transformer
   over 50M parameters. Declare every model in `README.md`.
2. **Offline at runtime.** No network calls in `backend/src`. No runtime downloads.
3. **Synthetic data only.** Never commit real patient data, the organiser answer key
   (`dev/truth/`), attacker material (`dev/attacker/`) or pipeline outputs.
4. **Never commit secrets.** `RAKSHA_SECRET` lives only in your shell. There is no default secret.
5. **Never modify `organiser-toolkit/`** or weaken its validators. It is a separate, git-ignored clone.
6. **PII hygiene in code:** never log, print or format record content, input file names or the
   secret into messages, exceptions, reports or test failure output. Use counts and fixed codes.
7. **Determinism:** no time, randomness or unordered-set iteration in anything that reaches output.

## Workflow

```bash
git checkout -b <area>/<short-description>       # e.g. detection/devanagari-labels
cd backend
../.venv/bin/pytest                               # must pass (xfails are documented gaps)
../.venv/bin/ruff check src tests ../main.py && ../.venv/bin/ruff format src tests ../main.py
cd .. && backend/scripts/official_checks.sh       # CONTRACT OK + check_dev numbers
```

PR description must include: what changed, the `check_dev.py` before and after numbers (leak %, per script,
canaries, medical kept, linking P/R/F0.5), runtime and RSS, and any new dependency with its justification.

## Tests

- New detection behaviour: add synthetic cases to `backend/tests/regression/test_contextual_detection.py`.
  If you fix an `xfail`, remove its marker (strict xfail fails the suite on XPASS).
- Use invented names and placeholder numbers. Do not paste practice records into tests.
- Tests needing the toolkit use the `toolkit` fixture and skip when it is absent.

## Commit messages

Imperative mood, scope prefix: `detection: add Devanagari name labels`, `linking: block on UHID core`.
