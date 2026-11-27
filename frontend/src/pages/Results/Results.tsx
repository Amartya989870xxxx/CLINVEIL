import { Fragment } from "react";

import { useDataMode } from "../../app/providers/DataModeProvider";
import { Button, LinkButton } from "../../components/common/Button";
import { CopyButton } from "../../components/common/CopyButton";
import { Icon } from "../../components/common/Icon";
import { Notice } from "../../components/common/Notice";
import { SourceBadge } from "../../components/common/SourceBadge";
import { Disclosure, Empty, ErrorText, Facts, Loading, NextStep, Section, RunGate } from "../../components/data/Blocks";
import d from "../../components/data/data.module.css";
import { PageHeader } from "../../components/layout/PageHeader";
import { ENTITY_GROUPS, REASONS } from "../../content/labels";
import { resultJobId, useCurrentJob } from "../../hooks/useCurrentJob";
import { useResource } from "../../hooks/useResource";
import { formatMeasurement } from "../../components/data/measure";
import { CountUp } from "../../components/motion/CountUp";
import type { Findings, QuarantineSummary, Summary } from "../../services/api/types";
import { fmtInt, fmtSeconds, shortSha } from "../../utils/format";

function Counts({ sum }: { sum: Summary }) {
  const c = sum.counts;
  return (
    <Facts
      label="Release counts"
      items={[
        { label: "Files received", value: fmtInt(c.files_total) },
        { label: "Files protected", value: fmtInt(c.files_sanitized), hint: "exported in their original format" },
        { label: "Files set aside", value: fmtInt(c.files_quarantined), hint: "never copied into the release" },
        { label: "Records processed", value: fmtInt(c.records_processed) },
        { label: "Personal details found", value: fmtInt(c.identifiers_detected) },
        { label: "Records linked", value: c.records_linked ? fmtInt(c.records_linked) : null, missing: "None linked", hint: "records sharing a keyed pseudonym with at least one other record" },
        { label: "Records generalised", value: fmtInt(c.records_generalized), hint: "records with at least one generalised value, such as a shifted date, an age band or a PIN prefix" },
        { label: "Processing time", value: sum.timing ? fmtSeconds(sum.timing.seconds) : null },
      ]}
    />
  );
}

const CHANNEL_LABEL: Record<string, string> = {
  content: "In the text and values",
  filename: "In file names",
  header: "In column headers",
  key: "In JSON keys",
  metadata: "In export metadata",
  base64: "Inside encoded attachments",
};
const SCRIPT_LABEL: Record<string, string> = { latin: "Latin (English)", deva: "Devanagari (Hindi)", hinglish: "Hinglish" };

/** A small table of counts with bars, from the engine's own detection summary. */
function Breakdown({ title, rows, labels }: { title: string; rows: Record<string, number | undefined>; labels: Record<string, string> }) {
  const entries = Object.entries(rows)
    .filter((e): e is [string, number] => typeof e[1] === "number")
    .sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map((e) => e[1]));
  return (
    <div className={d.tableWrap} style={{ borderTop: 0 }}>
      <table className={d.table}>
        <caption style={{ textAlign: "left", fontWeight: 500, paddingBottom: "var(--s-2)" }}>{title}</caption>
        <tbody>
          {entries.map(([k, n], i) => (
            <tr key={k}>
              <td>{labels[k] ?? k}</td>
              <td className="num">
                <CountUp value={fmtInt(n)} />
              </td>
              <td className={d.barCell} aria-hidden="true">
                <div className={d.bar}>
                  <div className={`${d.barFill} ${d.barAccent}`} style={{ width: `${(100 * n) / max}%`, animationDelay: `${i * 60}ms` }} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FindingsTable({ f }: { f: Findings }) {
  const max = Math.max(1, ...Object.values(f.by_type).map((v) => v ?? 0));
  let row = 0;
  return (
    <div className={d.tableWrap}>
      <table className={d.table}>
        <caption className="visually-hidden">Personal details found, by type</caption>
        <thead>
          <tr>
            <th scope="col">Type</th>
            <th scope="col" className="num">
              Found and removed
            </th>
            <th scope="col" className={d.barCell}>
              <span className="visually-hidden">Relative amount</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {ENTITY_GROUPS.map((g) => (
            <Fragment key={g.group}>
              <tr className={d.group}>
                <th scope="colgroup" colSpan={3} style={{ textAlign: "left" }}>
                  {g.group}
                </th>
              </tr>
              {g.types.map((t) => {
                const n = f.by_type[t.type];
                return (
                  <tr key={t.type}>
                    <td>{t.label}</td>
                    <td className="num">{n === undefined ? <span className="meta">none found</span> : <CountUp value={fmtInt(n)} />}</td>
                    <td className={d.barCell} aria-hidden="true">
                      <div className={d.bar}>
                        <div className={d.barFill} style={{ width: `${(100 * (n ?? 0)) / max}%`, animationDelay: `${row++ * 45}ms` }} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </Fragment>
          ))}
        </tbody>
      </table>
      {(f.by_script || f.by_channel) && (
        <div className={d.cols} style={{ marginTop: "var(--s-6)" }}>
          {f.by_channel && <Breakdown title="Where they were hidden" rows={f.by_channel} labels={CHANNEL_LABEL} />}
          {f.by_script && <Breakdown title="Script" rows={f.by_script} labels={SCRIPT_LABEL} />}
        </div>
      )}
      {(f.by_script === null || f.by_channel === null) && (
        <p className="meta" style={{ marginTop: "var(--s-3)" }}>
          Breakdowns by script (Latin, Devanagari, Hinglish) and by hiding place (file names, headers, keys, attachments)
          are not reported by the engine yet (contract question Q3).
        </p>
      )}
    </div>
  );
}

function SetAside({ q }: { q: QuarantineSummary }) {
  const rows = q.files.filter((r) => r.status !== "sanitized");
  if (!rows.length) return <Empty>No files were set aside.</Empty>;
  return (
    <div className={d.tableWrap}>
      <table className={d.table}>
        <caption className="visually-hidden">Files set aside</caption>
        <thead>
          <tr>
            <th scope="col">File (SHA-256 prefix)</th>
            <th scope="col">Format</th>
            <th scope="col">Reason</th>
            <th scope="col">What to do</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const reason = r.reason ? REASONS[r.reason] : null;
            return (
              // identical files share a hash (e.g. several empty files), so the position is part of the key
              <tr key={`${i}-${r.input_sha256}`}>
                <td className="mono">
                  {shortSha(r.input_sha256)}
                  <CopyButton value={r.input_sha256} label="full SHA-256" />
                </td>
                <td>{r.format.toUpperCase()}</td>
                <td>{reason?.text ?? "Set aside"}</td>
                <td className="meta">{reason?.next ?? "Check the file."}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Results() {
  const { source } = useDataMode();
  const job = useCurrentJob();
  const id = resultJobId(job);
  const summary = useResource(() => (id ? source.summary(id) : Promise.resolve(null)), [source, id]);
  const findings = useResource(() => (id ? source.findings(id) : Promise.resolve(null)), [source, id]);
  const quarantine = useResource(() => (id ? source.quarantine(id) : Promise.resolve(null)), [source, id]);
  const metrics = useResource(() => (id ? source.metrics(id) : Promise.resolve(null)), [source, id]);
  const kept =
    metrics.status === "ready"
      ? metrics.data.dimensions.flatMap((x) => x.measurements).find((m) => m.key === "medical_values_kept")
      : undefined;
  const keptText = kept ? formatMeasurement(kept) : null;
  const download = id ? source.downloadUrl(id) : null;
  const reportUrl = id ? source.indexFileUrl(id, "report.json") : null;
  const recordsUrl = id ? source.indexFileUrl(id, "records.jsonl") : null;
  const badge = summary.status === "ready" ? <SourceBadge source={summary.data.source} provenance={summary.data.provenance} /> : undefined;

  return (
    <>
      <PageHeader
        eyebrow="Workflow"
        title="Results"
        lead="What the release contains: what was removed, what was kept, and which files were set aside and why."
        badge={badge}
        actions={
          id ? (
            <Button variant="secondary" icon="printer" onClick={() => window.print()}>
              Print or save as PDF
            </Button>
          ) : undefined
        }
      />
      <RunGate job={job} />
      {job.status === "loading" && <Loading />}
      {job.status === "error" && <ErrorText message={job.message} />}
      {job.status === "empty" && (
        <Empty>
          No processing run yet.{" "}
          <LinkButton to="/process" variant="quiet" icon="arrowRight">
            Process a dataset
          </LinkButton>
        </Empty>
      )}
      {id && (
        <>
          <Section id="counts" title="The release at a glance">
            {summary.status === "loading" && <Loading />}
            {summary.status === "error" && <ErrorText message={summary.message} />}
            {summary.status === "ready" && <Counts sum={summary.data} />}
          </Section>

          <Section
            id="removed"
            title="Personal details removed"
            intro="Each detail is replaced in place with a placeholder such as [NAME] or [PHONE]; surrounding clinical text is left as it was."
          >
            {findings.status === "loading" && <Loading />}
            {findings.status === "error" && <ErrorText message={findings.message} />}
            {findings.status === "ready" && <FindingsTable f={findings.data} />}
          </Section>

          <Section id="kept" title="Clinical information kept">
            <div className={d.cols}>
              <p className={d.intro} style={{ margin: 0 }}>
                Diagnoses, medicines, doses and frequencies, vitals, laboratory values, units, doctors' names, wards and
                departments are left exactly as written.{" "}
                {keptText?.measured && kept ? (
                  <>
                    Measured with {kept.method}: <strong>{keptText.text}</strong> listed medical values survived verbatim.
                  </>
                ) : (
                  "Medical-value retention has not been measured for this run."
                )}
              </p>
              <Notice tone="warn" title="What is and is not generalised">
                Clinical dates are shifted per patient (ambiguous dates are suppressed), structured ages become 5-year
                bands and PIN codes keep a 3-digit prefix only where at least 5 records share it. Villages are removed,
                not generalised; tehsils and districts are kept; ages inside free text and JSON numbers are kept as written.
              </Notice>
            </div>
          </Section>

          <Section id="set-aside" title="Files set aside" intro="Files that cannot be checked safely are listed in the report and never copied into the release. Names are not shown; files are identified by a hash.">
            {quarantine.status === "loading" && <Loading />}
            {quarantine.status === "error" && <ErrorText message={quarantine.message} />}
            {quarantine.status === "ready" && <SetAside q={quarantine.data} />}
          </Section>

          <Section id="download" title="Download the release">
            {download ? (
              <ul className={d.downloads}>
                <li>
                  <a className="next-link" href={download} download rel="noopener">
                    <Icon name="file" size={16} /> Download sanitised release (zip)
                  </a>
                </li>
                {reportUrl && (
                  <li>
                    <a className="next-link" href={reportUrl} download rel="noopener">
                      <Icon name="file" size={16} /> report.json
                    </a>
                  </li>
                )}
                {recordsUrl && (
                  <li>
                    <a className="next-link" href={recordsUrl} download rel="noopener">
                      <Icon name="file" size={16} /> records.jsonl
                    </a>
                  </li>
                )}
              </ul>
            ) : (
              <p className={d.intro}>
                Not available in example mode: the recorded run's files are not bundled with this interface. The release
                contains only sanitised files, <span className="mono">report.json</span> and{" "}
                <span className="mono">records.jsonl</span>; set-aside files are never included.
              </p>
            )}
            <Disclosure summary="What is in report.json">
              <p>
                Counts of files, records and identifiers, every file's status and reason, processing time and peak memory.
                It contains no personal details and no key material.
              </p>
            </Disclosure>
          </Section>
        </>
      )}
      <NextStep fallback={{ to: "/preview", label: "Data preview" }} />
    </>
  );
}
