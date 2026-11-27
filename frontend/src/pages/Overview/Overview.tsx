import { Link } from "react-router";

import { useDataMode } from "../../app/providers/DataModeProvider";
import { LinkButton } from "../../components/common/Button";
import { CopyButton } from "../../components/common/CopyButton";
import { Notice } from "../../components/common/Notice";
import { SourceBadge } from "../../components/common/SourceBadge";
import { StatusTag } from "../../components/common/StatusTag";
import { formatMeasurement } from "../../components/data/measure";
import { NextStep } from "../../components/data/Blocks";
import { PageHeader } from "../../components/layout/PageHeader";
import { OVERVIEW_STEPS, PipelineFlow } from "../../components/diagrams/PipelineFlow";
import { resultJobId, useCurrentJob } from "../../hooks/useCurrentJob";
import { useResource } from "../../hooks/useResource";
import { DIMENSION_LABEL } from "../../content/labels";
import type { Capability, JobStatus, Summary } from "../../services/api/types";
import { fmtDate, fmtInt, fmtSeconds, fmtTime } from "../../utils/format";
import s from "./Overview.module.css";

const CAPABILITY_TEXT: Record<Capability, { name: string; why: string }> = {
  ingestion: { name: "File reading and validation", why: "CSV, TSV, JSON, FHIR R4 and text; four encodings" },
  detection: { name: "Personal-information detection", why: "Latin, Devanagari and Hinglish; content and hidden places" },
  linking: { name: "Patient record linking", why: "Planned: Phase 3" },
  privacy_transforms: { name: "Indirect-identifier protection", why: "Only birth dates today; banding and date shifting planned" },
  export: { name: "Clinical-preserving export", why: "Same formats and structure; set-aside files never copied" },
  validation: { name: "Release validation", why: "Checked before the run reports success" },
};

function outcome(job: JobStatus): { text: string; state: "complete" | "needs_attention" | "failed" | "in_progress" } {
  switch (job.state) {
    case "complete":
      return { text: "Completed", state: "complete" };
    case "complete_with_quarantine":
      return { text: "Completed, some files set aside safely", state: "complete" };
    case "failed":
      return { text: "Failed", state: "failed" };
    default:
      return { text: "Running", state: "in_progress" };
  }
}

function LatestRun() {
  const { source } = useDataMode();
  const job = useCurrentJob();
  const id = resultJobId(job);
  const summary = useResource<Summary>(() => (id ? source.summary(id) : Promise.resolve(null)), [source, id]);
  const health = useResource(() => source.health(), [source]);
  const commit =
    job.status === "ready" && job.data.provenance
      ? job.data.provenance.engine_commit
      : health.status === "ready"
        ? health.data.engine_commit
        : null;
  return (
    <section className={s.panel} aria-labelledby="latest-run">
      <div className={s.panelHead}>
        <h3 id="latest-run" className={s.panelTitle}>
          Latest processing run
        </h3>
        {job.status === "ready" && <SourceBadge source={job.data.source} provenance={job.data.provenance} />}
      </div>
      {job.status === "loading" && <p className={s.empty}>Loading…</p>}
      {job.status === "error" && <p className={s.empty}>{job.message}</p>}
      {job.status === "empty" && (
        <p className={s.empty}>No processing run yet. Start one from Process Dataset.</p>
      )}
      {job.status === "ready" && (
        <>
          <dl className={s.dl}>
            <dt>Outcome</dt>
            <dd>
              <StatusTag state={outcome(job.data).state} label={outcome(job.data).text} />
            </dd>
            <dt>Dataset</dt>
            <dd>{job.data.provenance?.dataset ?? job.data.dataset_label ?? job.data.dataset_id}</dd>
            {summary.status === "ready" && (
              <>
                <dt>Files</dt>
                <dd className={s.counts}>
                  <span>
                    <b>{fmtInt(summary.data.counts.files_total)}</b> received
                  </span>
                  <span>
                    <b>{fmtInt(summary.data.counts.files_sanitized)}</b> protected
                  </span>
                  <span>
                    <b>{fmtInt(summary.data.counts.files_quarantined)}</b> set aside
                  </span>
                </dd>
                <dt>Records</dt>
                <dd>{fmtInt(summary.data.counts.records_processed)} processed</dd>
                <dt>Duration</dt>
                <dd>
                  {summary.data.timing ? fmtSeconds(summary.data.timing.seconds) : "Not measured yet"}
                  {summary.data.resources && (
                    <span className="meta"> · peak memory {summary.data.resources.peak_rss_mb.toFixed(0)} MB</span>
                  )}
                </dd>
              </>
            )}
            <dt>Engine</dt>
            <dd className="mono">
              {commit ? (
                <>
                  {commit.slice(0, 7)}
                  <CopyButton value={commit} label="engine commit" />
                </>
              ) : (
                "Not reported"
              )}
            </dd>
          </dl>
          <div className={s.panelFoot}>
            <span className="meta">
              {job.data.provenance
                ? `Recorded ${fmtDate(job.data.provenance.recorded_on)}, not a live job`
                : job.data.started_at
                  ? `Live run, started ${fmtTime(job.data.started_at)}`
                  : "Live run"}
            </span>
            {id ? (
              <LinkButton to="/results" variant="quiet" icon="arrowRight">
                View results
              </LinkButton>
            ) : (
              <LinkButton to={`/run?job=${encodeURIComponent(job.data.job_id)}`} variant="quiet" icon="arrowRight">
                Follow the run
              </LinkButton>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function SystemStatus() {
  const { source, mode } = useDataMode();
  const health = useResource(() => source.health(), [source]);
  return (
    <section aria-labelledby="system-status">
      <div className={s.sectionHead} style={{ marginBottom: "var(--s-3)" }}>
        <h3 id="system-status" className={s.panelTitle}>
          System capabilities
        </h3>
        {health.status === "ready" && <SourceBadge source={health.data.source} provenance={health.data.provenance} />}
      </div>
      {health.status === "error" && <p className="meta">{health.message}</p>}
      {health.status === "loading" && <p className="meta">Loading…</p>}
      {health.status === "ready" && (
        <ul className={s.capList}>
          {(Object.keys(CAPABILITY_TEXT) as Capability[]).map((c) => (
            <li key={c}>
              <span>
                <span className={s.capName}>{CAPABILITY_TEXT[c].name}</span>
                <span className={s.capWhy}>{CAPABILITY_TEXT[c].why}</span>
              </span>
              <StatusTag state={health.data.capabilities[c]} />
            </li>
          ))}
        </ul>
      )}
      <p className={s.modeLine}>
        {mode === "demo"
          ? "Showing example data recorded from a real run. Switch to Local backend to connect to a running engine."
          : "Connected mode: values come only from the local backend."}
      </p>
    </section>
  );
}

function Measured() {
  const { source } = useDataMode();
  const job = useCurrentJob();
  const id = resultJobId(job);
  const metrics = useResource(() => (id ? source.metrics(id) : Promise.resolve(null)), [source, id]);
  return (
    <section className={s.section} aria-labelledby="measured">
      <div className={s.sectionHead}>
        <h2 id="measured" className={s.sectionTitle}>
          Measured so far
        </h2>
        {metrics.status === "ready" && <SourceBadge source={metrics.data.source} provenance={metrics.data.provenance} />}
      </div>
      {metrics.status === "empty" && (
        <p className="meta">
          {job.status === "ready"
            ? "Measurements appear here when the current run finishes successfully."
            : "Not measured yet. No run is available in this mode."}
        </p>
      )}
      {metrics.status === "error" && <p className="meta">{metrics.message}</p>}
      {metrics.status === "ready" && (
        <div className={s.tableWrap}>
          <table className={s.measure}>
            <caption className="visually-hidden">
              Measurements by organiser scoring dimension, with dataset, method and date
            </caption>
            <thead>
              <tr>
                <th scope="col">Dimension</th>
                <th scope="col">Measurement</th>
                <th scope="col">Result</th>
                <th scope="col">How it was measured</th>
              </tr>
            </thead>
            <tbody>
              {metrics.data.dimensions.flatMap((d) =>
                d.measurements.slice(0, 1).map((m) => {
                  const f = formatMeasurement(m);
                  return (
                    <tr key={m.key}>
                      <td className={s.dim}>{DIMENSION_LABEL[d.id]}</td>
                      <td>
                        {m.label}
                        {m.caveat && <span className={s.caveat}>{m.caveat}</span>}
                      </td>
                      <td className={f.measured ? s.value : s.unmeasured}>{f.text}</td>
                      <td className="meta">
                        {m.method}
                        {m.measured_at ? `, ${fmtDate(m.measured_at)}` : ""}
                      </td>
                    </tr>
                  );
                }),
              )}
            </tbody>
          </table>
        </div>
      )}
      <p className={s.foot}>
        Practice-checker results are a development guide on synthetic data, not the official Secret Wards score. The
        full breakdown is on <Link to="/privacy">Privacy &amp; Quality</Link>.
      </p>
    </section>
  );
}

export function Overview() {
  const { source } = useDataMode();
  const health = useResource(() => source.health(), [source]);
  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Overview"
        lead="Where the system stands, the latest processing run, and what has been measured so far."
        actions={
          <>
            <LinkButton to="/process" variant="primary" icon="arrowRight">
              Process a dataset
            </LinkButton>
            <LinkButton to="/process?path=judge" variant="secondary">
              Follow the judge demo
            </LinkButton>
          </>
        }
      />

      <div className={s.notices}>
        <Notice title="Synthetic data only">
          Every record shown or processed here is synthetic. Do not upload or enter real patient information.
        </Notice>
        <Notice tone="warn" title="Prototype, not a certified medical system">
          Patient linking and most indirect-identifier protection are not implemented yet, so today's releases remove
          direct identifiers but keep exact ages, places and dates.
        </Notice>
      </div>

      <section className={s.section} aria-labelledby="how">
        <div className={s.sectionHead}>
          <h2 id="how" className={s.sectionTitle}>
            How a release is made
          </h2>
          <Link to="/architecture" className={s.sectionNote}>
            Full architecture
          </Link>
        </div>
        <PipelineFlow steps={OVERVIEW_STEPS} states={health.status === "ready" ? health.data.capabilities : null} />
      </section>

      <section className={s.section}>
        <div className={s.split}>
          <LatestRun />
          <SystemStatus />
        </div>
      </section>

      <Measured />
      <NextStep fallback={{ to: "/process", label: "Process a dataset" }} />
    </>
  );
}
