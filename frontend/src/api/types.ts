// Types for the proposed local demo API (docs/api-contract/README.md, v0).
// The evaluator CLI is authoritative; these mirror report.json / records.jsonl shapes.

export type FileStatus = "sanitized" | "quarantined" | "suppressed";

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

/** Present (true) on every fixture not served by a live backend; the UI must badge it. */
interface MaybeMock {
  mock?: boolean;
  provenance?: string;
}

export interface Health {
  status: "ok";
  version: string;
  engine_phase: number;
}

export interface DatasetInfo {
  id: string;
  label: string;
  synthetic: boolean;
  files: number;
}

export type JobState = "queued" | "running" | "done" | "failed";

export interface JobStatus {
  job_id: string;
  state: JobState;
  exit_code: number | null;
  seconds: number | null;
}

export interface JobSummary extends MaybeMock {
  job_id: string;
  engine_phase: number;
  counts: ReleaseCounts;
  status_histogram: Partial<Record<FileStatus, number>>;
  quarantine_reasons: Record<string, number>;
}

/** One report.json files[] entry: identified by hash, never by input name. */
export interface FileResult {
  input_sha256: string;
  output: string | null;
  status: FileStatus;
  reason?: string;
}

export interface LinkingSummary {
  records: number;
  linked: number;
  clusters: number;
  cluster_size_histogram: Record<string, number>;
}

export interface Metrics extends MaybeMock {
  source: "practice-truth";
  detection: {
    leaked_share: number;
    leaked: number;
    total: number;
    by_script: Record<"latin" | "deva" | "hinglish", number>;
    by_channel: Record<string, number>;
  };
  canaries: { found: number; planted: number };
  utility: { medical_values_kept: number; kept: number; total: number };
  linking: { precision: number; recall: number; f05: number; false_merges: number };
  raw_copies: number;
}

export interface ApiError {
  error: { code: string; message: string };
}
