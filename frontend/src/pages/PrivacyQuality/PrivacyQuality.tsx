import { useDataMode } from "../../app/providers/DataModeProvider";
import { Button } from "../../components/common/Button";
import { Notice } from "../../components/common/Notice";
import { SourceBadge } from "../../components/common/SourceBadge";
import { Empty, ErrorText, Loading, NextStep, Section, RunGate } from "../../components/data/Blocks";
import d from "../../components/data/data.module.css";
import { formatMeasurement } from "../../components/data/measure";
import { PageHeader } from "../../components/layout/PageHeader";
import { DIMENSION_LABEL, DIMENSION_QUESTION } from "../../content/labels";
import { redTeam } from "../../fixtures/internalRedTeam";
import { resultJobId, useCurrentJob } from "../../hooks/useCurrentJob";
import { useResource } from "../../hooks/useResource";
import type { Dimension } from "../../services/api/types";
import { fmtDate, fmtInt } from "../../utils/format";
import s from "../pages.module.css";

function DimensionBlock({ dim }: { dim: Dimension }) {
  return (
    <Section id={`dim-${dim.id}`} title={DIMENSION_LABEL[dim.id]} intro={DIMENSION_QUESTION[dim.id]}>
      <div className={d.tableWrap}>
        <table className={`${d.table} ${d.fixed}`} style={{ minWidth: 640 }}>
          <caption className="visually-hidden">{DIMENSION_LABEL[dim.id]} measurements</caption>
          <colgroup>
            <col style={{ width: "46%" }} />
            <col style={{ width: "18%" }} />
            <col style={{ width: "36%" }} />
          </colgroup>
          <thead>
            <tr>
              <th scope="col">Measurement</th>
              <th scope="col">Result</th>
              <th scope="col">Method and date</th>
            </tr>
          </thead>
          <tbody>
            {dim.measurements.map((m) => {
              const f = formatMeasurement(m);
              return (
                <tr key={m.key}>
                  <td>
                    {m.label}
                    {m.caveat && (
                      <span className="meta" style={{ display: "block", marginTop: 4 }}>
                        {m.caveat}
                      </span>
                    )}
                  </td>
                  <td>{f.measured ? <strong style={{ fontWeight: 500 }}>{f.text}</strong> : <span className={d.notMeasured}>{f.text}</span>}</td>
                  <td className="meta">
                    {m.method}
                    {m.measured_at ? `, ${fmtDate(m.measured_at)}` : ""}
                    <span style={{ display: "block" }}>{m.dataset}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function InternalRedTeam() {
  return (
    <Section
      id="redteam"
      title="Internal red-team testing"
      badge={<SourceBadge source="example_fixture" />}
      intro="The team built its own adversarial synthetic test suite to find weaknesses before the event. These are internal development results on harder data than the practice set; they are not an official score and do not prove the system is secure."
    >
      <div className={d.tableWrap}>
        <table className={d.table} style={{ minWidth: 720 }}>
          <caption className="visually-hidden">Internal red-team results by tier</caption>
          <thead>
            <tr>
              <th scope="col">Tier</th>
              <th scope="col" className="num">Files</th>
              <th scope="col" className="num">Personal details left visible</th>
              <th scope="col" className="num">Detected in exported files</th>
              <th scope="col" className="num">Clinical values kept</th>
              <th scope="col" className="num">Files handled correctly</th>
              <th scope="col" className="num">Security flags</th>
            </tr>
          </thead>
          <tbody>
            {redTeam.tiers.map((t) => (
              <tr key={t.tier}>
                <td>
                  {t.tier}
                  <span className="meta" style={{ display: "block" }}>{t.description}</span>
                </td>
                <td className="num">{fmtInt(t.files)}</td>
                <td className="num">
                  {fmtInt(t.pii_left_visible)} of {fmtInt(t.pii_total)}
                </td>
                <td className="num">{t.recall_on_exported_pct.toFixed(1)}%</td>
                <td className="num">{t.clinical_kept_pct.toFixed(1)}%</td>
                <td className="num">{t.correct_handling_pct.toFixed(0)}%</td>
                <td className="num">{t.security_flags}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="meta" style={{ marginTop: "var(--s-3)" }}>
        {redTeam.suite}, engine {redTeam.engine_commit.slice(0, 7)}, {fmtDate(redTeam.recorded_on)}. Security flags count
        crashes, timeouts, modified inputs, executed inputs, files read outside the input, leaked secrets and leftover
        temporary files. A private holdout tier exists and is deliberately not reported here.
      </p>
      <div className={s.prose} style={{ marginTop: "var(--s-6)" }}>
        <h3 style={{ fontWeight: 500 }}>Weaknesses this run found, and where they stand now</h3>
        <ul>
          {redTeam.known_gaps.map((g) => (
            <li key={g.gap}>
              {g.gap}{" "}
              <span style={{ display: "block", fontSize: "var(--text-sm)", color: g.fixed ? "var(--ok)" : "var(--warn)" }}>
                {g.status}
              </span>
            </li>
          ))}
        </ul>
        <p className="meta">
          Fixes are as reported in the team's Phase 2.1 remediation report for engine 9205b5a. The figures in the table
          above were measured on {redTeam.engine_commit.slice(0, 7)} and have not been re-run on the updated engine.
        </p>
      </div>
    </Section>
  );
}

export function PrivacyQuality() {
  const { source } = useDataMode();
  const job = useCurrentJob();
  const id = resultJobId(job);
  const metrics = useResource(() => (id ? source.metrics(id) : Promise.resolve(null)), [source, id]);

  return (
    <>
      <PageHeader
        eyebrow="Evidence"
        title="Privacy and quality"
        lead="Measurements for the six dimensions the organisers score, each with how and when it was measured. Anything not measured says so."
        badge={metrics.status === "ready" ? <SourceBadge source={metrics.data.source} provenance={metrics.data.provenance} /> : undefined}
        actions={
          <Button variant="secondary" icon="printer" onClick={() => window.print()}>
            Print or save as PDF
          </Button>
        }
      />
      <Notice tone="info" title="How to read these numbers">
        Practice-set results come from the organiser's own checking tools run on synthetic data the team could see. The
        hidden datasets and the attack arena differ, and the browser never computes or rounds a score.
      </Notice>
      <div style={{ marginTop: "var(--s-4)" }}>
        <RunGate job={job} />
      </div>
      {(job.status === "loading" || metrics.status === "loading") && <Loading />}
      {job.status === "error" && <ErrorText message={job.message} />}
      {metrics.status === "error" && <ErrorText message={metrics.message} />}
      {job.status === "empty" && <Empty>No measurements yet: there is no processing run.</Empty>}
      {metrics.status === "ready" && metrics.data.dimensions.map((dim) => <DimensionBlock key={dim.id} dim={dim} />)}
      <InternalRedTeam />
      <NextStep fallback={{ to: "/architecture", label: "Architecture" }} />
    </>
  );
}
