import { useState, type ReactNode } from "react";

import { Icon } from "../../components/common/Icon";

import { useDataMode } from "../../app/providers/DataModeProvider";
import { Notice } from "../../components/common/Notice";
import { SourceBadge } from "../../components/common/SourceBadge";
import { Empty, ErrorText, Loading, NextStep, Section, RunGate } from "../../components/data/Blocks";
import { PageHeader } from "../../components/layout/PageHeader";
import { resultJobId, useCurrentJob } from "../../hooks/useCurrentJob";
import { useResource } from "../../hooks/useResource";
import type { Example, Span } from "../../services/api/types";
import s from "../pages.module.css";

const KIND_TEXT: Record<Span["kind"], string> = {
  removed: "Personal detail removed",
  preserved: "Clinical information kept",
  generalised: "Indirect identifier, not generalised yet",
  pseudonym: "Consistent pseudonym",
};
const KIND_SR: Record<Span["kind"], string> = {
  removed: "removed",
  preserved: "kept",
  generalised: "kept exactly, not generalised yet",
  pseudonym: "pseudonym",
};

/** Renders text with non-overlapping highlighted spans. Each mark carries a screen-reader label, so colour is never the only cue. */
export function Highlighted({ text, spans }: { text: string; spans: Span[] }) {
  const out: ReactNode[] = [];
  let at = 0;
  let k = 0;
  for (const sp of [...spans].sort((a, b) => a.start - b.start)) {
    if (sp.start < at || sp.end > text.length) continue;
    if (sp.start > at) out.push(text.slice(at, sp.start));
    out.push(
      <mark key={sp.start} className={s[`m_${sp.kind}`]} style={{ ["--k" as string]: k++ }}>
        {text.slice(sp.start, sp.end)}
        <span className="visually-hidden"> ({KIND_SR[sp.kind]})</span>
      </mark>,
    );
    at = sp.end;
  }
  out.push(text.slice(at));
  return <>{out}</>;
}

function Legend({ kinds }: { kinds: Span["kind"][] }) {
  return (
    <ul className={s.legend} aria-label="Highlight legend">
      {kinds.map((k) => (
        <li key={k}>
          <span className={`${s.swatch} ${s[`sw_${k}`]}`} aria-hidden="true" />
          {KIND_TEXT[k]}
        </li>
      ))}
    </ul>
  );
}

function Panes({ ex }: { ex: Example }) {
  const [run, setRun] = useState(0);
  const kinds = (["removed", "preserved", "generalised", "pseudonym"] as const).filter((k) =>
    [...ex.spans_before, ...ex.spans_after].some((sp) => sp.kind === k),
  );
  const count = (k: Span["kind"]) => ex.spans_before.filter((sp) => sp.kind === k).length;
  return (
    <>
      <Legend kinds={kinds} />
      <p className="meta" style={{ marginBottom: "var(--s-4)" }}>
        In this record:{" "}
        {[
          `${count("removed")} personal details removed`,
          kinds.includes("preserved") ? `${count("preserved")} clinical items checked and kept` : null,
          kinds.includes("generalised") ? `${count("generalised")} indirect identifiers kept exactly` : null,
        ]
          .filter(Boolean)
          .join(", ")}
        .
      </p>
      <div className={s.panes}>
        <section className={s.pane} aria-labelledby={`${ex.id}-before`}>
          <div className={s.paneHead}>
            <h3 id={`${ex.id}-before`} className={s.paneTitle}>
              Before: as exported by the hospital
            </h3>
          </div>
          <pre className={s.record} tabIndex={0} aria-label="Original synthetic record">
            <Highlighted text={ex.before} spans={ex.spans_before} />
          </pre>
        </section>
        <section className={`${s.pane} ${s.after}`} aria-labelledby={`${ex.id}-after`}>
          <div className={s.paneHead}>
            <h3 id={`${ex.id}-after`} className={s.paneTitle}>
              After: research-ready release
            </h3>
            <button type="button" className={s.replay} onClick={() => setRun((x) => x + 1)}>
              <Icon name="replay" size={14} /> Replay
            </button>
          </div>
          <pre key={run} className={`${s.record} ${s.playing}`} tabIndex={0} aria-label="Processed record">
            <Highlighted text={ex.after} spans={ex.spans_after} />
          </pre>
        </section>
      </div>
    </>
  );
}

export function DataPreview() {
  const { source } = useDataMode();
  const job = useCurrentJob();
  const id = resultJobId(job);
  const examples = useResource(() => (id ? source.examples(id) : Promise.resolve(null)), [source, id]);
  const [sel, setSel] = useState(0);
  const list = examples.status === "ready" ? examples.data.examples : [];
  const ex = list[Math.min(sel, list.length - 1)];

  return (
    <>
      <PageHeader
        eyebrow="Evidence"
        title="Data preview"
        lead="One synthetic record before and after processing. Personal details are replaced in place; the clinical content around them is untouched."
        badge={examples.status === "ready" ? <SourceBadge source={examples.data.source} provenance={examples.data.provenance} /> : undefined}
      />
      <Notice tone="info" title="Synthetic record, real engine output">
        The patient, family, address and numbers are invented. The "after" text is the unedited output of CLINVEIL for
        this record; nothing was adjusted by hand.
      </Notice>
      <div style={{ marginTop: "var(--s-4)" }}>
        <RunGate job={job} />
      </div>
      {(job.status === "loading" || examples.status === "loading") && <Loading />}
      {job.status === "error" && <ErrorText message={job.message} />}
      {examples.status === "error" && <ErrorText message={examples.message} />}
      {(job.status === "empty" || (examples.status === "ready" && !list.length)) && (
        <Empty>No example records are available for this run.</Empty>
      )}
      {ex && (
        <Section id="example" title={list.length > 1 ? "Example records" : ex.title}>
          {list.length > 1 && (
            <div className={s.tabs} role="tablist" aria-label="Example records">
              {list.map((e, i) => (
                <button key={e.id} type="button" role="tab" className={s.tab} aria-selected={i === sel} onClick={() => setSel(i)}>
                  {e.title}
                </button>
              ))}
            </div>
          )}
          <Panes ex={ex} />
        </Section>
      )}
      {examples.status === "ready" && examples.data.source === "example_fixture" && (
      <Section id="reading" title="What to notice">
        <div className={s.prose}>
          <ul>
            <li>
              <strong>The doctor stays, the relative goes.</strong> "Dr. Ramesh Iyengar" is a clinician and is kept;
              "Ramesh Awasthi", the patient's husband and attendant, shares the first name and is removed both times.
            </li>
            <li>
              <strong>Medicines and doses are intact.</strong> "Tab Dolo 650 BD x 5 days" keeps its number, which looks
              like a PIN fragment but is a dose.
            </li>
            <li>
              <strong>Two hospital numbers in two formats</strong> (UHID and IPD) both become [MRN]. The mobile number is
              removed in both of its spellings.
            </li>
            <li>
              <strong>Not done yet.</strong> The exact age (58), tehsil and district are still in the release. Age bands
              and place generalisation are planned (Phase 4); without them a rare combination could identify someone.
            </li>
          </ul>
        </div>
      </Section>
      )}
      {examples.status === "ready" && examples.data.source === "live_backend" && list.length > 0 && (
        <p className="meta" style={{ marginTop: "var(--s-5)" }}>
          Highlights in a live run come from comparing the input with the engine's output word by word: everything
          that changed is marked as removed. File names are not shown.
        </p>
      )}
      <NextStep fallback={{ to: "/privacy", label: "Privacy and quality" }} />
    </>
  );
}
