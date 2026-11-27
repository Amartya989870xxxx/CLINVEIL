// One interface, two implementations. Pages depend on DataSource only, never on fetch or fixtures directly.

import {
  exampleDatasets,
  exampleFindings,
  exampleHealth,
  exampleJob,
  exampleMetrics,
  exampleQuarantine,
  exampleSummary,
} from "../fixtures/recordedPracticeRun";
import { exampleRecord } from "../fixtures/exampleRecord";
import { API_BASE, getJson, postJson, SafeError } from "./api/client";
import { uploadBody } from "./upload";
import type {
  DatasetList,
  Examples,
  Findings,
  Health,
  JobCreated,
  JobStatus,
  Metrics,
  QuarantineSummary,
  Summary,
} from "./api/types";

export type DataMode = "demo" | "backend";

export interface DataSource {
  mode: DataMode;
  health(): Promise<Health>;
  datasets(): Promise<DatasetList>;
  /** Latest finished job, or null when none exists. */
  latestJob(): Promise<JobStatus | null>;
  job(jobId: string): Promise<JobStatus>;
  summary(jobId: string): Promise<Summary>;
  findings(jobId: string): Promise<Findings>;
  quarantine(jobId: string): Promise<QuarantineSummary>;
  metrics(jobId: string): Promise<Metrics>;
  examples(jobId: string): Promise<Examples>;
  /** Demo mode never processes anything: it returns the id of the recorded run. */
  startJob(datasetId: string): Promise<JobCreated>;
  /** Uploads synthetic files to the local backend and starts a real run. Demo mode cannot process files. */
  startUpload(files: File[]): Promise<JobCreated>;
  /** URL of one engine index file (report.json / records.jsonl), or null when no safe download exists. */
  indexFileUrl(jobId: string, name: "report.json" | "records.jsonl"): string | null;
  /** URL of the sanitised release zip, or null when no safe download exists in this mode. */
  downloadUrl(jobId: string): string | null;
}

const resolved = <T,>(v: T) => Promise.resolve(structuredClone(v));

export const demoSource: DataSource = {
  mode: "demo",
  health: () => resolved(exampleHealth),
  datasets: () => resolved(exampleDatasets),
  latestJob: () => resolved(exampleJob),
  job: () => resolved(exampleJob),
  summary: () => resolved(exampleSummary),
  findings: () => resolved(exampleFindings),
  quarantine: () => resolved(exampleQuarantine),
  metrics: () => resolved(exampleMetrics),
  examples: () => resolved(exampleRecord),
  startJob: () =>
    resolved({ contract: "clinveil-frontend/1" as const, source: "example_fixture" as const, job_id: exampleJob.job_id }),
  downloadUrl: () => null,
  startUpload: () => Promise.reject(new SafeError("unreachable")),
  indexFileUrl: () => null,
};

const enc = encodeURIComponent;

export const backendSource: DataSource = {
  mode: "backend",
  health: () => getJson<Health>("/health"),
  datasets: () => getJson<DatasetList>("/datasets"),
  latestJob: async () => {
    // addition to v1: GET /jobs/latest (404 = no run yet)
    try {
      return await getJson<JobStatus>("/jobs/latest");
    } catch (e) {
      if (e instanceof SafeError && e.code === "not_found") return null;
      throw e;
    }
  },
  job: (id) => getJson<JobStatus>(`/jobs/${enc(id)}`),
  summary: (id) => getJson<Summary>(`/jobs/${enc(id)}/summary`),
  findings: (id) => getJson<Findings>(`/jobs/${enc(id)}/findings`),
  quarantine: (id) => getJson<QuarantineSummary>(`/jobs/${enc(id)}/quarantine`),
  metrics: (id) => getJson<Metrics>(`/jobs/${enc(id)}/metrics`),
  examples: (id) => getJson<Examples>(`/jobs/${enc(id)}/examples`),
  startJob: (datasetId) => postJson<JobCreated>("/jobs", { dataset_id: datasetId, policy_preset: "competition_default" }),
  downloadUrl: (id) => `${API_BASE}/jobs/${enc(id)}/download`,
  startUpload: async (files) => postJson<JobCreated>("/jobs", await uploadBody(files), 120000),
  indexFileUrl: (id, name) => `${API_BASE}/jobs/${enc(id)}/${name}`,
};
