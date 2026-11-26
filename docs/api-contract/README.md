# Backend ↔ frontend API contract (v0, proposed)

## Three interfaces. Do not confuse them.

| Interface | Status | Authority | On the evaluator path? |
|---|---|---|---|
| **Evaluator CLI**: `python main.py --input … --output …` plus `report.json`/`records.jsonl` | **implemented** | `organiser-toolkit/docs/SPEC.md` | **yes, and the only thing that is** |
| **Local demo API**: read-only HTTP over a finished output directory | **proposed** (Phase 7) | this document | **no**, never imported by `clinveil.cli` |
| **Frontend data layer**: TypeScript types plus fetch client | **types drafted** (`frontend/src/api/types.ts`) | this document | no |

The CLI is authoritative. The API is a thin, optional *viewer*. It must never become a dependency of
the release, and its dependencies (if any) live in an optional `[demo]` extra, never in `requirements.txt`.

## Design rules (security)

1. **Read-only over release artefacts.** The API reads only `report.json`, `records.jsonl`, files
   under `sanitized/`, and a separately computed `metrics.json`. It never reads `{input}` except to
   run a job on an **allowlisted synthetic dataset id**. It never accepts arbitrary filesystem paths.
2. **No secret over HTTP.** `RAKSHA_SECRET` is set in the server's environment only. The frontend
   never sees, sends or stores it. No secret in `VITE_*` variables.
3. **No raw records.** Before/after examples are served only for datasets flagged `synthetic: true`,
   from a curated short excerpt list, and only when the server starts with `--demo-examples`.
4. **Localhost only** (`127.0.0.1`), no CORS wildcard, no auth because nothing is sensitive by construction.
5. **Real numbers only.** Every metric comes from a real run's artefacts. Mock fixtures carry
   `"mock": true` and the UI must show a visible "sample data" badge for them.

## Proposed endpoints (`/api/v1`)

| Method | Path | Returns | Source |
|---|---|---|---|
| GET | `/health` | `{status, version, engine_phase}` | static |
| GET | `/datasets` | allowlisted dataset ids `{id, label, synthetic, files}` | server config |
| POST | `/jobs` | `{job_id}`; body `{dataset_id}` (no paths, no secret) | runs the CLI as a subprocess |
| GET | `/jobs/{job_id}` | `{state: queued\|running\|done\|failed, exit_code, seconds}` | process state |
| GET | `/jobs/{job_id}/summary` | `report.json.counts` + `timing` + `resources` + status histogram | `report.json` |
| GET | `/jobs/{job_id}/files` | `[{input_sha256, output, status, reason}]` (paginated) | `report.json.files` |
| GET | `/jobs/{job_id}/quarantine` | quarantined subset with reason codes | `report.json.files` |
| GET | `/jobs/{job_id}/linking` | `{records, linked, clusters, cluster_size_histogram}` | `records.jsonl` |
| GET | `/jobs/{job_id}/metrics` | privacy, utility and linking metrics (dev datasets only) | `metrics.json` (Phase 6) |
| GET | `/jobs/{job_id}/examples` | curated before/after excerpts (synthetic + flag only) | Phase 7 |
| GET | `/jobs/{job_id}/download` | zip of `sanitized/` + `report.json` + `records.jsonl` | output dir |

Error shape: `{"error": {"code": "not_found", "message": "<fixed text, never record content>"}}`.

## Example responses

Mock fixtures live in [`frontend/src/mocks/`](../../frontend/src/mocks/). The **summary** fixture uses
the *real* Phase 0 baseline counts measured on the organiser practice data (see
[BASELINE.md](../evaluation/BASELINE.md)), flagged `mock: true` because it is served without a running backend.

```json
GET /api/v1/jobs/demo-practice/summary
{
  "mock": true,
  "job_id": "demo-practice",
  "engine_phase": 0,
  "counts": {"files_total": 200, "files_sanitized": 195, "files_quarantined": 5,
             "records_processed": 823, "identifiers_detected": 492, "records_linked": 0,
             "records_generalized": 0, "records_suppressed": 0, "records_quarantined": 0},
  "status_histogram": {"sanitized": 195, "quarantined": 5},
  "quarantine_reasons": {"unsupported_format": 3, "empty_file": 1, "JSONDecodeError": 1}
}
```

```json
GET /api/v1/jobs/demo-practice/metrics          (Phase 6, values from check_dev-equivalent scoring)
{
  "mock": true,
  "source": "practice-truth",
  "detection": {"leaked_share": 0.841, "by_script": {"latin": 0.828, "deva": 1.0, "hinglish": 1.0}},
  "canaries": {"found": 4, "planted": 4},
  "utility": {"medical_values_kept": 1.0},
  "linking": {"precision": 0.0, "recall": 0.0, "f05": 0.0, "false_merges": 0}
}
```

## Open questions **[NEEDS APPROVAL]**
- Stdlib `http.server` (zero deps, more code) or FastAPI (optional `[demo]` extra, faster to build)?
- Is a job runner needed at all, or is "load an existing output directory" enough for the demo?
