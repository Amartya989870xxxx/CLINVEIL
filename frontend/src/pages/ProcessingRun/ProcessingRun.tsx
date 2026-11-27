import { useDataMode } from "../../app/providers/DataModeProvider";
import { LinkButton } from "../../components/common/Button";
import { Notice } from "../../components/common/Notice";
import { SourceBadge } from "../../components/common/SourceBadge";
import { StatusTag } from "../../components/common/StatusTag";
import { Empty, ErrorText, Facts, Loading, NextStep, Section } from "../../components/data/Blocks";
import { PageHeader } from "../../components/layout/PageHeader";
import { DETAIL_TEXT, STAGES } from "../../content/labels";
import { jobQuery, useCurrentJob } from "../../hooks/useCurrentJob";
import type { JobState, JobStatus } from "../../services/api/types";
import { fmtSeconds, fmtTime } from "../../utils/format";
import s from "../pages.module.css";

const OUTCOME: Record<JobState, string> = {
  queued: "Waiting to start",
  running: "Running",
  complete: "Completed",
  complete_with_quarantine: "Completed, some files set aside safely",
  failed: "Failed: no release was produced",
};

function Timeline({ job }: { job: JobStatus }) {
  const stages = [...job.stages].sort((a, b) => STAGES[a.id].order - STAGES[b.id].order);
  return (
    <ol className={s.timeline} aria-label="Pipeline stages">
      {stages.map((st) => {
        const meta = STAGES[st.id];
        return (
          <li key={st.id} className={`${s.stageRow} ${st.state === "not_available" ? s.stageUnavailable : ""}`}>
            <span className={s.stageIdx} aria-hidden="true">
              {String(meta.order).padStart(2, "0")}
            </span>
            <div>
              <div className={s.stageTitle}>{meta.title}</div>
              <p className={s.stagePlain}>{meta.plain}</p>
              {st.detail_code && <p className={s.stageDetail}>{DETAIL_TEXT[st.detail_code] ?? st.detail_code}</p>}
            </div>
            <span className={s.stageState}>
              <StatusTag state={st.state} />
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function ProcessingRun() {
  const { mode } = useDataMode();
  const job = useCurrentJob();

  return (
    <>
      <PageHeader
        eyebrow="Workflow"
        title="Processing run"
        lead="Each stage of the pipeline, with its real status. Stages that are not built yet are shown as not available, never as complete."
        badge={job.status === "ready" ? <SourceBadge source={job.data.source} provenance={job.data.provenance} /> : undefined}
      />
      {job.status === "loading" && <Loading />}
      {job.status === "error" && <ErrorText message={job.message} />}
      {job.status === "empty" && (
        <Empty>
          No processing run yet. {mode === "backend" ? "Start one from Process Dataset." : ""}{" "}
          <LinkButton to="/process" variant="quiet" icon="arrowRight">
            Process a dataset
          </LinkButton>
        </Empty>
      )}
      {job.status === "ready" && (
        <>
          {job.data.source === "example_fixture" && (
            <Notice tone="warn" title="This is a recorded run, not a live one">
              The statuses below were recorded when the real engine processed the practice dataset. Example mode does not
              run anything or animate progress. Per-stage progress during a live run is contract question Q5.
            </Notice>
          )}
          <Section id="run-facts" title="Run">
            <Facts
              label="Run facts"
              items={[
                { label: "Outcome", value: OUTCOME[job.data.state], text: true },
                {
                  label: job.data.state === "running" || job.data.state === "queued" ? "Elapsed" : "Duration",
                  value: job.data.seconds === null ? null : fmtSeconds(job.data.seconds),
                },
                {
                  label: "Exit code",
                  value: job.data.exit_code === null ? null : String(job.data.exit_code),
                  missing: job.data.state === "running" || job.data.state === "queued" ? "When the run finishes" : undefined,
                  hint: "0 means a valid release was written",
                },
                { label: "Started", value: job.data.started_at ? fmtTime(job.data.started_at) : null, missing: "Not recorded", text: true },
              ]}
            />
          </Section>
          <Section id="stages" title="Stages">
            <Timeline job={job.data} />
          </Section>
          {job.data.state !== "queued" && job.data.state !== "running" && (
            <div style={{ marginTop: "var(--s-6)" }}>
              <LinkButton to={`/results${jobQuery(job.data)}`} variant="primary" icon="arrowRight">
                View results
              </LinkButton>
            </div>
          )}
        </>
      )}
      <NextStep fallback={{ to: "/results", label: "Results" }} />
    </>
  );
}
