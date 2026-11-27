# Frontend <-> demo API contract, v1 (PROPOSED)

**Status: proposed by the frontend, NOT agreed.** The backend owner must approve or amend every schema before
integration. Until then the frontend runs in demo mode on typed fixtures (`frontend/src/fixtures/`). Supersedes
the v0 sketch in `README.md` of this folder; endpoint paths are unchanged.

Ground rules (from `README.md`, unchanged): the CLI is authoritative and the API is an optional, read-only,
localhost-only viewer over a finished output directory; never on the evaluator path; no secret, raw record,
answer key or attacker file over HTTP; fixed-text errors only.

Base URL: `http://127.0.0.1:<port>/api/v1` (frontend reads `VITE_API_BASE`). JSON, UTF-8. Every response body
carries `contract: "clinveil-frontend/1"` and `source`:

```ts
type Source = "live_backend" | "example_fixture";   // fixtures are never served by the backend
```

## 1. `GET /health`

```ts
interface Health {
  contract: "clinveil-frontend/1"; source: Source;
  status: "ok" | "degraded";
  engine_version: string;            // e.g. "0.2.0"
  engine_commit: string | null;      // full git SHA when known
  capabilities: Record<Capability, CapabilityState>;
}
type Capability = "ingestion" | "detection" | "linking" | "privacy_transforms" | "export" | "validation";
type CapabilityState = "implemented" | "partial" | "not_available";
```
Today's truthful values: ingestion, detection, export, validation `implemented`; privacy_transforms `partial`
(DOB placeholder, FHIR birth year); linking `not_available`.

## 2. `GET /datasets`

```ts
interface DatasetList { contract; source; datasets: DatasetInfo[] }
interface DatasetInfo {
  id: string;                        // allowlisted id, e.g. "practice-synthetic"
  label: string; synthetic: true;    // only synthetic datasets are ever listed
  files: number; bytes: number;
  formats: Record<string, number>;   // "csv" | "tsv" | "json" | "fhir" | "text" | "xml" | "pdf" | "image" | "other"
  expected_unsupported: number;      // files the engine will set aside (quarantine)
}
```

## 3. `POST /jobs`

Request `{ "dataset_id": string, "policy_preset": "competition_default" }`. No paths, no secret, no policy
values beyond an allowlisted preset id. Response `202 { contract, source, job_id: string }`.
Uploads are **out of scope for v1** (open question Q2).

## 4. `GET /jobs/{job_id}`

```ts
interface JobStatus {
  contract; source; job_id: string;
  state: "queued" | "running" | "complete" | "complete_with_quarantine" | "failed";
  started_at: string | null; finished_at: string | null;   // ISO 8601
  exit_code: number | null; seconds: number | null;
  stages: StageStatus[];             // in pipeline order, always all six
}
interface StageStatus {
  id: "ingestion" | "detection" | "linking" | "privacy_transforms" | "export" | "validation";
  state: "waiting" | "in_progress" | "complete" | "needs_attention" | "failed" | "not_available";
  detail_code: string | null;        // fixed vocabulary, e.g. "files_set_aside", never free text
}
```
The backend reports a stage `complete` only when that stage actually ran; unimplemented stages are
`not_available`. No percentages (the CLI cannot report them honestly).

## 5. `GET /jobs/{job_id}/summary`  (from `report.json`)

```ts
interface Summary {
  contract; source; job_id: string;
  counts: {                          // report.json "counts", unchanged names
    files_total: number; files_sanitized: number; files_quarantined: number; records_processed: number;
    identifiers_detected: number; records_linked: number; records_generalized: number;
    records_suppressed: number; records_quarantined: number;
  };
  timing: { seconds: number } | null;
  resources: { peak_rss_mb: number } | null;
  validation: { contract_ok: boolean | null; checker: "validate_output.py" | "internal" };
}
```

## 6. `GET /jobs/{job_id}/findings`  (from `report.json` "entities")

```ts
interface Findings {
  contract; source; job_id: string;
  by_type: Record<EntityType, number>;                // counts of findings handled
  by_script: Partial<Record<"latin" | "deva" | "hinglish", number>> | null;   // null until the engine reports it
  by_channel: Partial<Record<"content" | "filename" | "header" | "key" | "metadata" | "base64", number>> | null;
}
type EntityType = "PATIENT_NAME" | "RELATIVE_NAME" | "PHONE" | "EMAIL" | "AADHAAR" | "AADHAAR_MASKED" |
  "ABHA_NUMBER" | "ABHA_ADDRESS" | "PAN" | "MRN" | "INSURANCE_ID" | "HOUSE" | "LOCALITY" | "LANDMARK" |
  "VILLAGE" | "PIN" | "DOB";
```
Counts of things *handled*, not a claim that nothing was missed.

## 7. `GET /jobs/{job_id}/files?cursor=&limit=` and `GET /jobs/{job_id}/quarantine`

```ts
interface FilePage { contract; source; job_id; files: FileRow[]; next_cursor: string | null }
interface FileRow {
  input_sha256: string;              // identifies the file; the input NAME is never returned (may hold PII)
  output: string | null;             // output path (already PII-free) or null when set aside
  status: "sanitized" | "quarantined" | "suppressed";
  format: string;                    // detected content type
  reason: QuarantineReason | null;
}
interface QuarantineSummary { contract; source; job_id; reasons: Record<QuarantineReason, number>; files: FileRow[] }
type QuarantineReason = "empty_file" | "file_too_large" | "implausible_text" | "invalid_json" | "json_too_deep" |
  "json_too_large" | "undecodable_text" | "unsupported_archive" | "unsupported_attachment" | "unsupported_binary" |
  "unsupported_format" | "unsupported_image" | "unsupported_pdf" | "unsupported_xml" | "invalid_attachment" |
  "attachment_too_large" | "symlink_outside_input" | "not_a_regular_file";   // = security/errors.py REASON_CODES
```

## 8. `GET /jobs/{job_id}/metrics`  (practice/dev datasets only)

Measured privacy and quality, one block per organiser scoring dimension. Every value is a measurement with
provenance or `null` ("Not measured yet"); the browser never computes a score.

```ts
interface Metrics { contract; source; job_id; dimensions: Dimension[] }
interface Dimension {
  id: "privacy_attacks" | "detection" | "utility" | "identity" | "integrity" | "performance";
  measurements: Measurement[];
}
interface Measurement {
  key: string;                       // e.g. "pii_visible", "medical_values_kept", "linking_f05"
  value: number | null; unit: "count" | "ratio" | "seconds" | "mb" | "bool";
  numerator?: number; denominator?: number;
  dataset: string;                   // e.g. "organiser practice set (synthetic, 200 files)"
  method: string;                    // e.g. "organiser check_dev.py", "validate_output.py"
  measured_at: string;               // ISO date
  caveat: string | null;
}
```

## 9. `GET /jobs/{job_id}/examples`  (synthetic + `--demo-examples` only)

```ts
interface Examples { contract; source; job_id; examples: { id: string; title: string; before: string; after: string;
  synthetic: true; spans_before: Span[]; spans_after: Span[] }[] }
interface Span { start: number; end: number; kind: "removed" | "generalised" | "preserved" | "pseudonym" }
```

## 10. `GET /jobs/{job_id}/download`

`200 application/zip` containing `sanitized/`, `report.json`, `records.jsonl` only (never `quarantine/`, input,
truth or attacker files). Served with `Content-Disposition: attachment; filename="clinveil-release-<job_id>.zip"`,
`Cache-Control: no-store`. Available only when the job is `complete*`.

## 11. Errors

`{ "contract": "clinveil-frontend/1", "error": { "code": "not_found" | "invalid_request" | "job_failed" |
"unavailable" | "internal", "message": "<fixed text>" } }`. Messages never contain record content, paths or
exception text.

## Open questions for the backend owner

* Q1: stdlib `http.server` or FastAPI in an optional `[demo]` extra? (frontend has no preference)
* Q2: synthetic uploads in the backend at all, or allowlisted datasets only? (frontend inspects uploads in the
  browser today and does not send them)
* Q3: can the engine report findings by script and channel (`by_script`, `by_channel`), or only by type?
* Q4: who computes `metrics` (a `metrics.json` written by a dev-only scorer next to the output)?
* Q5: is per-stage status available from the CLI (for example a progress file), or only final state?


---

## Implementation status (2026-11-27)

A reference implementation exists: `backend/scripts/demo_api.py` (standard library only, optional, not on the
evaluator path, no engine code changed). It serves every endpoint above from the real CLI's own output files.
Still **proposed**: the backend owner has not yet agreed this contract.

Additions to v1 made by that implementation (backwards compatible):

| addition | why |
|---|---|
| `GET /jobs/latest` (404 when there is no run) | the frontend needs "the most recent run" for pages opened from the sidebar |
| `JobStatus.dataset_label` (optional string) | show the dataset's name, not its id |
| `findings.by_script` / `by_channel` filled from `logs/detection_summary.json` (`by_language`, `by_channel`) | answers Q3 with data the engine already writes |
| while a job runs, built stages are `in_progress` with `detail_code: "no_stage_progress"` | the CLI reports nothing until it finishes (Q5 remains open) |
| `409` with `error.code: "unavailable"` while another run is in progress | one run at a time |

Q2 (uploads) remains unanswered: the implementation runs allowlisted synthetic datasets only.
