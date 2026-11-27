// Types for the PROPOSED demo API, contract "clinveil-frontend/1" (docs/api-contract/frontend-v1.md).
// Not yet agreed with the backend owner. The evaluator CLI and its report.json are authoritative.

export type Source = "live_backend" | "example_fixture";

/** Provenance carried by every fixture so the UI can say exactly where a number came from. */
export interface FixtureProvenance {
  source: "example_fixture";
  recorded_from: string;   // what produced the values, in plain words
  engine_commit: string;   // full git SHA of the engine that produced them
  dataset: string;
  command: string;
  recorded_on: string;     // ISO date
}

interface Envelope {
  contract: "clinveil-frontend/1";
  source: Source;
  provenance?: FixtureProvenance; // present on fixtures only
}

export type Capability = "ingestion" | "detection" | "linking" | "privacy_transforms" | "export" | "validation";
export type CapabilityState = "implemented" | "partial" | "not_available";

export interface Health extends Envelope {
  status: "ok" | "degraded";
  engine_version: string;
  engine_commit: string | null;
  capabilities: Record<Capability, CapabilityState>;
}

export interface DatasetInfo {
  id: string;
  label: string;
  synthetic: true;
  description: string;
  files: number;
  bytes: number;
  formats: Record<string, number>;
  expected_unsupported: number;
}

export interface DatasetList extends Envelope {
  datasets: DatasetInfo[];
}

export type JobState = "queued" | "running" | "complete" | "complete_with_quarantine" | "failed";
export type StageId = Capability;
export type StageState = "waiting" | "in_progress" | "complete" | "needs_attention" | "failed" | "not_available";

export interface StageStatus {
  id: StageId;
  state: StageState;
  detail_code: string | null;
}

export interface JobStatus extends Envelope {
  job_id: string;
  dataset_id: string;
  dataset_label?: string; // addition to v1: human label of the dataset
  state: JobState;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  seconds: number | null;
  stages: StageStatus[];
}

export interface ReleaseCounts {
  files_total: number;
  files_sanitized: number;
  files_quarantined: number;
  records_processed: number;
  identifiers_detected: number;
  records_linked: number;
  records_generalized: number;
  records_suppressed: number;
  records_quarantined: number;
}

export interface Summary extends Envelope {
  job_id: string;
  counts: ReleaseCounts;
  timing: { seconds: number } | null;
  resources: { peak_rss_mb: number } | null;
  validation: { contract_ok: boolean | null; checker: "validate_output.py" | "internal" };
}

export type EntityType =
  | "PATIENT_NAME" | "RELATIVE_NAME" | "PHONE" | "EMAIL" | "AADHAAR" | "AADHAAR_MASKED" | "ABHA_NUMBER"
  | "ABHA_ADDRESS" | "PAN" | "MRN" | "INSURANCE_ID" | "HOUSE" | "LOCALITY" | "LANDMARK" | "VILLAGE" | "PIN" | "DOB";

export interface Findings extends Envelope {
  job_id: string;
  by_type: Partial<Record<EntityType, number>>;
  by_script: Partial<Record<"latin" | "deva" | "hinglish", number>> | null;
  by_channel: Partial<Record<"content" | "filename" | "header" | "key" | "metadata" | "base64", number>> | null;
}

export type QuarantineReason =
  | "empty_file" | "file_too_large" | "implausible_text" | "invalid_json" | "json_too_deep" | "json_too_large"
  | "undecodable_text" | "unsupported_archive" | "unsupported_attachment" | "unsupported_binary"
  | "unsupported_format" | "unsupported_image" | "unsupported_pdf" | "unsupported_xml" | "invalid_attachment"
  | "attachment_too_large" | "symlink_outside_input" | "not_a_regular_file";

export interface FileRow {
  input_sha256: string;
  output: string | null;
  status: "sanitized" | "quarantined" | "suppressed";
  format: string;
  reason: QuarantineReason | null;
}

export interface QuarantineSummary extends Envelope {
  job_id: string;
  reasons: Partial<Record<QuarantineReason, number>>;
  files: FileRow[];
}

export type DimensionId = "privacy_attacks" | "detection" | "utility" | "identity" | "integrity" | "performance";

export interface Measurement {
  key: string;
  label: string;
  value: number | null;            // null = "Not measured yet"
  unit: "count" | "ratio" | "seconds" | "mb" | "bool";
  numerator?: number;
  denominator?: number;
  dataset: string;
  method: string;
  measured_at: string | null;
  caveat: string | null;
}

export interface Dimension {
  id: DimensionId;
  measurements: Measurement[];
}

export interface Metrics extends Envelope {
  job_id: string;
  dimensions: Dimension[];
}

export interface ApiErrorBody {
  contract: "clinveil-frontend/1";
  error: {
    code:
      | "not_found"
      | "invalid_request"
      | "job_failed"
      | "unavailable"
      | "internal"
      | "forbidden"
      | "invalid_upload"
      | "unsupported_file"
      | "upload_too_large";
    message: string;
  };
}

export interface JobCreated extends Envelope {
  job_id: string;
}

export interface Span {
  start: number;
  end: number;
  kind: "removed" | "generalised" | "preserved" | "pseudonym";
}

export interface Example {
  id: string;
  title: string;
  before: string;
  after: string;
  synthetic: true;
  spans_before: Span[];
  spans_after: Span[];
}

export interface Examples extends Envelope {
  job_id: string;
  examples: Example[];
}
