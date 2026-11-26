# Team working agreement

## Ownership (proposed; fill in names)

| Area | Owner | Paths |
|---|---|---|
| Ingestion and parsing (P1) | | `backend/src/clinveil/{ingestion,parsing}` |
| Detection (P2) | | `backend/src/clinveil/detection`, `tests/regression/test_contextual_detection.py` |
| Linking (P3) | | `backend/src/clinveil/linking` |
| Privacy layer (P4) | | `backend/src/clinveil/privacy` |
| Export, FHIR, security (P5) | | `backend/src/clinveil/{export,sanitization,security}` |
| Evaluation and metrics (P6) | | `backend/src/clinveil/metrics`, `backend/scripts` |
| Frontend and demo (P7) | | `frontend/`, `docs/api-contract` |
| Project Brief PDF | | `docs/brief/` (to create; 2 pages; measured numbers only) |

## Rhythm

- Every merge to `main`: CI green (lint, tests, CONTRACT OK, determinism).
- After every merged scoring change: post the `check_dev.py` delta in the team channel.
- The submission is the **last commit on `main` at the deadline**. Freeze `main` an hour early.

## Local setup checklist

1. `git clone https://github.com/Amartya989870xxxx/CLINVEIL.git && cd CLINVEIL`
2. `git clone https://github.com/Reinforce-SST/Secret-Wards-ToolKit.git organiser-toolkit`
3. `python3 -m venv .venv && .venv/bin/pip install -e "backend[dev]"`
4. `cd backend && ../.venv/bin/pytest`
5. `cd .. && backend/scripts/official_checks.sh`
