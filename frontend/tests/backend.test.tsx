import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/app/App";

// A fake of backend/scripts/demo_api.py, answering on the same paths the real one serves.
const C = { contract: "clinveil-frontend/1", source: "live_backend" };
const stages = (state: string) =>
  ["ingestion", "detection", "linking", "privacy_transforms", "export", "validation"].map((id) => ({
    id,
    state: id === "linking" ? "not_available" : state,
    detail_code: null,
  }));
function api(jobState: "running" | "complete_with_quarantine") {
  const job = { ...C, job_id: "0123456789abcdef", dataset_id: "practice", dataset_label: "Practice set", state: jobState,
    started_at: "2026-11-27T04:00:00+00:00", finished_at: null, exit_code: jobState === "running" ? null : 0, seconds: 1.2,
    stages: stages(jobState === "running" ? "in_progress" : "complete") };
  const routes: Record<string, unknown> = {
    "/api/v1/health": { ...C, status: "ok", engine_version: "0.1.0", engine_commit: "9205b5a755c433d9d6134d104adc68840867b9bc",
      capabilities: { ingestion: "implemented", detection: "implemented", linking: "not_available", privacy_transforms: "partial", export: "implemented", validation: "implemented" } },
    "/api/v1/datasets": { ...C, datasets: [
      { id: "practice", label: "Practice set", synthetic: true, description: "d1", files: 200, bytes: 1000, formats: { text: 2 }, expected_unsupported: 4 },
      { id: "stress_unseen_names", label: "Stress test: unseen names", synthetic: true, description: "d2", files: 200, bytes: 1000, formats: { text: 2 }, expected_unsupported: 4 },
    ] },
    "/api/v1/jobs/latest": job,
    "/api/v1/jobs/0123456789abcdef": job,
    "/api/v1/jobs/0123456789abcdef/summary": { ...C, job_id: job.job_id, counts: { files_total: 200, files_sanitized: 193, files_quarantined: 7, records_processed: 822, identifiers_detected: 3350, records_linked: 0, records_generalized: 19, records_suppressed: 0, records_quarantined: 0 }, timing: { seconds: 1.2 }, resources: { peak_rss_mb: 31.8 }, validation: { contract_ok: true, checker: "validate_output.py" } },
    "/api/v1/jobs/0123456789abcdef/findings": { ...C, job_id: job.job_id, by_type: { PATIENT_NAME: 1022 }, by_script: { latin: 2500, deva: 173 }, by_channel: { content: 3205, filename: 48 } },
    "/api/v1/jobs/0123456789abcdef/quarantine": { ...C, job_id: job.job_id, reasons: {}, files: [] },
    "/api/v1/jobs/0123456789abcdef/metrics": { ...C, job_id: job.job_id, dimensions: [] },
  };
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (init?.method === "POST") return new Response(JSON.stringify({ ...C, job_id: "0123456789abcdef" }), { status: 202 });
    const body = routes[url];
    return body ? new Response(JSON.stringify(body), { status: 200 }) : new Response("{}", { status: 404 });
  });
  return calls;
}

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener() {}, removeEventListener() {} });
  localStorage.setItem("clinveil.mode", "backend");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.removeItem("clinveil.mode");
});

describe("connected to the local demo API", () => {
  it("talks to its own origin (proxied), never to another host", async () => {
    const calls = api("complete_with_quarantine");
    window.history.pushState({}, "", "/overview");
    render(<App />);
    await screen.findByText("Backend connected");
    expect(calls.length).toBeGreaterThan(0);
    for (const c of calls) expect(c.url.startsWith("/api/v1/")).toBe(true);
  });

  it("lists every dataset and starts the chosen one", async () => {
    const calls = api("complete_with_quarantine");
    window.history.pushState({}, "", "/process");
    render(<App />);
    fireEvent.click(await screen.findByRole("radio", { name: /Stress test: unseen names/ }));
    expect(screen.getByRole("radio", { name: /Practice set/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
    fireEvent.click(screen.getByRole("button", { name: /Start privacy processing/ }));
    await screen.findByRole("heading", { level: 1, name: "Processing run" });
    const post = calls.find((c) => c.init?.method === "POST");
    expect(post?.url).toBe("/api/v1/jobs");
    expect(JSON.parse(String(post?.init?.body))).toEqual({ dataset_id: "stress_unseen_names", policy_preset: "competition_default" });
  });

  it("explains a run that is still going instead of showing an error", async () => {
    api("running");
    window.history.pushState({}, "", "/results");
    render(<App />);
    expect(await screen.findByText("This run is still in progress")).toBeTruthy();
    expect(screen.queryByText(/reported an error/)).toBeNull();
  });

  it("shows the live results with the engine's own breakdowns", async () => {
    api("complete_with_quarantine");
    window.history.pushState({}, "", "/results");
    render(<App />);
    expect(await screen.findByText("3,350")).toBeTruthy();
    expect(screen.getByText("In file names")).toBeTruthy();
    expect(screen.getByText("Devanagari (Hindi)")).toBeTruthy();
    expect(screen.getAllByText("Live backend").length).toBeGreaterThan(0);
    // no "Example data" badge anywhere (the data-source switch in the top bar has a button with that label)
    expect(screen.queryAllByText("Example data").filter((el) => !el.closest("fieldset"))).toHaveLength(0);
    expect(screen.getByRole("link", { name: /Download sanitised release/ }).getAttribute("href")).toBe("/api/v1/jobs/0123456789abcdef/download");
  });
});
