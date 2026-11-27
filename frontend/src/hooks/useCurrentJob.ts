import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import { useDataMode } from "../app/providers/DataModeProvider";
import type { JobStatus } from "../services/api/types";
import { useResource, type Resource } from "./useResource";

const TERMINAL = new Set(["complete", "complete_with_quarantine", "failed"]);

/** The run a page is about: `?job=<id>` when given, otherwise the latest run. Polls while a live run is active. */
export function useCurrentJob(): Resource<JobStatus> {
  const { source, mode } = useDataMode();
  const [params] = useSearchParams();
  const id = params.get("job");
  const [tick, setTick] = useState(0);
  const res = useResource(() => (id ? source.job(id) : source.latestJob()), [source, id], tick);
  const running = res.status === "ready" && !TERMINAL.has(res.data.state);
  useEffect(() => {
    if (mode !== "backend" || !running) return;
    const t = setTimeout(() => setTick((x) => x + 1), 1500);
    return () => clearTimeout(t);
  }, [mode, running, tick]);
  return res;
}

export const jobQuery = (job: JobStatus) => `?job=${encodeURIComponent(job.job_id)}`;

/** The id of a run whose results can be read: finished and not failed. Null while running, failed or loading. */
export function resultJobId(res: Resource<JobStatus>): string | null {
  if (res.status !== "ready") return null;
  return res.data.state === "complete" || res.data.state === "complete_with_quarantine" ? res.data.job_id : null;
}
