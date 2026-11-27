import type { ReactNode } from "react";

import type { JobStatus } from "../../services/api/types";
import type { Resource } from "../../hooks/useResource";
import { Notice } from "../common/Notice";
import { Link, useLocation, useNavigate } from "react-router";

import { Icon } from "../common/Icon";
import { CountUp } from "../motion/CountUp";
import c from "../common/common.module.css";
import s from "./data.module.css";

export function Section({
  id,
  title,
  badge,
  intro,
  children,
}: {
  id: string;
  title: string;
  badge?: ReactNode;
  intro?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={s.section} aria-labelledby={id}>
      <div className={s.head}>
        <h2 id={id} className={s.title}>
          {title}
        </h2>
        {badge}
      </div>
      {intro && <p className={s.intro}>{intro}</p>}
      {children}
    </section>
  );
}

export interface Fact {
  label: string;
  value: string | null; // null = shown as `missing`
  missing?: string; // wording when value is null; defaults to "Not measured yet"
  text?: boolean; // a phrase rather than a number: set at body size
  hint?: string;
}

export function Facts({ items, label }: { items: Fact[]; label: string }) {
  return (
    <dl className={s.facts} aria-label={label}>
      {items.map((f) => (
        <div key={f.label} className={s.fact}>
          <dt>{f.label}</dt>
          <dd className={f.value === null ? s.notMeasured : f.text ? s.factText : undefined}>
            {f.value === null ? (f.missing ?? "Not measured yet") : f.text ? f.value : <CountUp value={f.value} />}
            {f.hint && <small>{f.hint}</small>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function Loading() {
  return (
    <div className={c.skeleton} role="status">
      <span aria-hidden="true" />
      <span aria-hidden="true" />
      <span aria-hidden="true" />
      <span className="visually-hidden">Loading…</span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className={s.state}>{children}</p>;
}

export function ErrorText({ message }: { message: string }) {
  return (
    <p className={`${s.state} ${s.errorState}`} role="alert">
      {message}
    </p>
  );
}

export function Disclosure({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className={s.details}>
      <summary>
        <Icon name="chevronDown" size={16} />
        {summary}
      </summary>
      <div className={s.detailsBody}>{children}</div>
    </details>
  );
}

// ---- judge demo trail ---------------------------------------------------------------------------------------------

export const JUDGE_PATH: { path: string; label: string; minutes: string }[] = [
  { path: "/overview", label: "Where the system stands", minutes: "0:30" },
  { path: "/process", label: "Choose the synthetic practice dataset", minutes: "0:30" },
  { path: "/run", label: "Follow the pipeline stage by stage", minutes: "1:00" },
  { path: "/results", label: "What was removed, kept and set aside", minutes: "1:00" },
  { path: "/preview", label: "One record before and after", minutes: "0:30" },
  { path: "/privacy", label: "Measured privacy and quality", minutes: "1:00" },
  { path: "/about", label: "Limitations and threat model", minutes: "0:30" },
];

const KEY = "clinveil.judge";

export function useJudgeMode(): boolean {
  const loc = useLocation();
  if (new URLSearchParams(loc.search).get("path") === "judge") {
    try {
      sessionStorage.setItem(KEY, "1");
    } catch {
      /* ignore */
    }
    return true;
  }
  try {
    return sessionStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/** Bottom-of-page "next step". In judge mode it walks the 5-minute demo path; otherwise it suggests the next screen. */
export function NextStep({ fallback }: { fallback?: { to: string; label: string } }) {
  const judge = useJudgeMode();
  const loc = useLocation();
  const nav = useNavigate();
  const i = JUDGE_PATH.findIndex((p) => p.path === loc.pathname);
  if (judge && i >= 0) {
    const next = JUDGE_PATH[i + 1];
    return (
      <nav className={s.trail} aria-label="Judge demo">
        <span className={s.trailText}>
          Judge demo · step <b>{i + 1}</b> of {JUDGE_PATH.length}
          {next ? ` · next: ${next.label} (${next.minutes})` : " · end of the demo"}
        </span>
        <span style={{ display: "flex", gap: "var(--s-3)", alignItems: "center" }}>
          <button
            type="button"
            className="linkish"
            onClick={() => {
              try {
                sessionStorage.removeItem(KEY);
              } catch {
                /* ignore */
              }
              nav(loc.pathname);
            }}
          >
            Leave demo path
          </button>
          {next && (
            <Link to={next.path} className="next-link">
              Next step <Icon name="arrowRight" size={16} />
            </Link>
          )}
        </span>
      </nav>
    );
  }
  if (!fallback) return null;
  return (
    <nav className={s.trail} aria-label="Next step">
      <span className={s.trailText}>Next</span>
      <Link to={fallback.to} className="next-link">
        {fallback.label} <Icon name="arrowRight" size={16} />
      </Link>
    </nav>
  );
}

/** Explains why a results page is empty while a live run is still going, or after it failed. */
export function RunGate({ job }: { job: Resource<JobStatus> }) {
  if (job.status !== "ready") return null;
  const st = job.data.state;
  if (st === "queued" || st === "running")
    return (
      <Notice tone="info" title="This run is still in progress">
        Results appear here automatically when it finishes.{" "}
        <Link to={`/run?job=${encodeURIComponent(job.data.job_id)}`}>Follow the run</Link>
      </Notice>
    );
  if (st === "failed")
    return (
      <Notice tone="warn" title="This run failed">
        The engine did not produce a valid release, so there are no results to show. Start a new run from Process
        Dataset.
      </Notice>
    );
  return null;
}
