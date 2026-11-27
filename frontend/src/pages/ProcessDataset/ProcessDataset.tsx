import { useId, useState } from "react";
import { useNavigate } from "react-router";

import { useDataMode } from "../../app/providers/DataModeProvider";
import { Button } from "../../components/common/Button";
import { Icon } from "../../components/common/Icon";
import { Notice } from "../../components/common/Notice";
import { SourceBadge } from "../../components/common/SourceBadge";
import { ErrorText, Loading, NextStep, Section } from "../../components/data/Blocks";
import d from "../../components/data/data.module.css";
import { PageHeader } from "../../components/layout/PageHeader";
import { useResource } from "../../hooks/useResource";
import { SafeError, SAFE_MESSAGES } from "../../services/api/client";
import type { DatasetInfo } from "../../services/api/types";
import { fmtBytes, fmtInt } from "../../utils/format";
import { inspectFiles, LIMITS, type Inspection } from "../../utils/inspect";
import { UPLOAD_LIMITS, UPLOAD_PROBLEM_TEXT, uploadProblem } from "../../services/upload";
import s from "../pages.module.css";

type Choice = string; // a dataset id, or "upload"
const STEP_NAMES = ["Choose data", "Review policy", "Confirm and start"];
const SUPPORTED = "CSV, TSV, JSON, FHIR R4 (JSON) and plain text";

function Steps({ step }: { step: number }) {
  return (
    <ol className={s.steps} aria-label="Progress">
      {STEP_NAMES.map((n, i) => (
        <li key={n} className={`${s.step} ${i < step ? s.stepDone : ""}`} aria-current={i === step ? "step" : undefined}>
          <span className={s.stepNum} aria-hidden="true">
            {i < step ? <Icon name="check" size={13} /> : i + 1}
          </span>
          {n}
          {i < step && <span className="visually-hidden"> (done)</span>}
        </li>
      ))}
    </ol>
  );
}

function FormatSummary({ formats }: { formats: Record<string, number> }) {
  return (
    <span className={s.choiceMeta}>
      {Object.entries(formats)
        .sort((a, b) => b[1] - a[1])
        .map(([k, v]) => (
          <span key={k}>
            {fmtInt(v)} {k.toUpperCase()}
          </span>
        ))}
    </span>
  );
}

function UploadInspector({
  confirmed,
  setConfirmed,
  inspection,
  setInspection,
  setFiles,
  live,
  error,
}: {
  confirmed: boolean;
  setConfirmed: (v: boolean) => void;
  inspection: Inspection | null;
  setInspection: (i: Inspection | null) => void;
  setFiles: (f: File[]) => void;
  live: boolean;
  error: string | null;
}) {
  const fileId = useId();
  const errId = useId();
  const [busy, setBusy] = useState(false);
  return (
    <div style={{ paddingLeft: 28 }}>
      <label className={s.check}>
        <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} aria-describedby={error ? errId : undefined} />
        <span>
          I confirm these files are <strong>synthetic</strong> and contain no real patient information.
          <span className="meta" style={{ display: "block" }}>
            Required. CLINVEIL's demonstration never accepts real patient data.
          </span>
        </span>
      </label>
      <div className={s.field}>
        <label htmlFor={fileId} className={s.fieldLabel}>
          Synthetic files
        </label>
        <input
          id={fileId}
          className={s.fileInput}
          type="file"
          multiple
          disabled={!confirmed || busy}
          onChange={async (e) => {
            const list = Array.from(e.target.files ?? []);
            setFiles(list);
            if (!list.length) return setInspection(null);
            setBusy(true);
            try {
              setInspection(await inspectFiles(list));
            } finally {
              setBusy(false);
            }
          }}
        />
        <span className={s.hint}>
          {live ? (
            <>
              Files are read in this browser to count and classify them. They are sent only when you press Start, and only
              to the local CLINVEIL backend on this computer, which deletes them when the run is evicted or the server
              stops. Upload limits: {UPLOAD_LIMITS.files} files, {fmtBytes(UPLOAD_LIMITS.totalBytes)}; .csv, .tsv, .tab,
              .txt and .json (including FHIR R4 JSON).
            </>
          ) : (
            <>
              Example mode: files are read in this browser only to count and classify them; nothing is uploaded or
              stored. Limits for inspection: {LIMITS.files} files, {fmtBytes(LIMITS.totalBytes)}.
            </>
          )}{" "}
          File names are not shown because a name can itself contain personal details.
        </span>
        {error && (
          <span id={errId} className={s.fieldError} role="alert">
            <Icon name="alert" size={15} /> {error}
          </span>
        )}
      </div>
      {busy && <Loading />}
      {inspection && (
        <div className="fade-enter" style={{ marginTop: "var(--s-5)" }}>
          <p>
            <strong>{fmtInt(inspection.files.length)}</strong> files, {fmtBytes(inspection.bytes)}.{" "}
            {inspection.setAside > 0 ? (
              <>
                <strong>{inspection.setAside}</strong> would be set aside safely.
              </>
            ) : (
              "All have a supported format."
            )}
            {inspection.truncated && " Only the first files within the inspection limits were checked."}
          </p>
          <div className={d.tableWrap} style={{ marginTop: "var(--s-3)" }}>
            <table className={d.table}>
              <caption className="visually-hidden">Selected files by detected format</caption>
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">SHA-256 prefix</th>
                  <th scope="col">Detected format</th>
                  <th scope="col" className="num">
                    Size
                  </th>
                  <th scope="col">Check</th>
                </tr>
              </thead>
              <tbody>
                {inspection.files.slice(0, 50).map((f) => (
                  <tr key={f.index}>
                    <td className="meta">{f.index}</td>
                    <td className="mono">{f.sha12}</td>
                    <td>{f.format.toUpperCase()}</td>
                    <td className="num">{fmtBytes(f.bytes)}</td>
                    <td>{f.problem ? <span style={{ color: "var(--warn)" }}>{f.problem}</span> : "Supported"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {inspection.files.length > 50 && <p className="meta">Showing the first 50 files.</p>}
        </div>
      )}
    </div>
  );
}

function PolicyReview() {
  return (
    <>
      <div className={s.policy}>
        <div>
          <h3>
            <Icon name="cross" size={16} /> Removed
          </h3>
          <ul>
            <li>Patient and relatives' names, in Latin, Devanagari and Hinglish</li>
            <li>Hospital record numbers (UHID, IPD, MRN), Aadhaar, ABHA, PAN, insurance IDs</li>
            <li>Phone numbers and e-mail addresses</li>
            <li>House numbers, localities, landmarks and villages (villages are removed: no offline mapping to tehsil or district exists)</li>
            <li>Dates of birth, and clinical dates whose day/month order cannot be established</li>
            <li>The same details hidden in file names, column headers, JSON keys, export metadata and attachments</li>
          </ul>
        </div>
        <div>
          <h3>
            <Icon name="check" size={16} /> Kept
          </h3>
          <ul>
            <li>Diagnoses and their codes, complaints and history</li>
            <li>Medicines, strengths, doses and frequencies (for example "Dolo 650 BD x 5 days")</li>
            <li>Vitals, laboratory values, units and reference ranges</li>
            <li>Doctors' names, wards and departments</li>
            <li>File formats, column structure and FHIR structure</li>
          </ul>
        </div>
        <div>
          <h3>
            <Icon name="partial" size={16} /> Generalised
          </h3>
          <ul>
            <li>Records of the same patient share one keyed pseudonym (PSN-…); uncertain records stay unlinked</li>
            <li>Clinical dates shifted by one secret offset per patient, so intervals and lengths of stay are kept</li>
            <li>Structured ages to 5-year bands (47 → 45-49, 73/F → 70-74/F)</li>
            <li>PIN codes to their 3-digit prefix, only where at least 5 records in the file share it</li>
            <li>FHIR birth dates reduced to the year</li>
            <li className={s.later}>Villages to tehsil or district: not available (no trusted offline mapping)</li>
            <li className={s.later}>Ages in JSON numbers or free text: kept as written</li>
          </ul>
        </div>
      </div>
      <fieldset className={s.choices} style={{ marginTop: "var(--s-8)" }}>
        <legend>Processing policy</legend>
        <label className={s.choice}>
          <input type="radio" name="preset" checked readOnly />
          <span className={s.choiceTitle}>Competition default</span>
          <span className={s.choiceText}>
            The only policy available. The organiser's contract fixes what a release must contain, so the demonstration
            does not expose individual settings. Files that cannot be checked safely are set aside, never copied.
          </span>
        </label>
      </fieldset>
      <p className={s.hint} style={{ marginTop: "var(--s-4)" }}>
        The secret key used for pseudonyms and date shifts stays in the engine's environment. This interface never sees,
        sends or stores it.
      </p>
    </>
  );
}

export function ProcessDataset() {
  const { source, mode } = useDataMode();
  const nav = useNavigate();
  const datasets = useResource(() => source.datasets(), [source]);
  const [step, setStep] = useState(0);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const all: DatasetInfo[] = datasets.status === "ready" ? datasets.data.datasets : [];
  const selected: DatasetInfo | undefined = all.find((d) => d.id === choice);

  function next() {
    setError(null);
    if (step === 0) {
      if (!choice) return setError("Choose a dataset to continue.");
      if (choice !== "upload" && !selected) return setError("That dataset is not available in this mode.");
      if (choice === "upload" && !confirmed) return setError("Confirm that the files are synthetic.");
      if (choice === "upload" && !inspection?.files.length) return setError("Select at least one synthetic file.");
      if (choice === "upload" && mode === "backend") {
        const problem = uploadProblem(files);
        if (problem) return setError(UPLOAD_PROBLEM_TEXT[problem]);
      }
    }
    setStep((x) => Math.min(2, x + 1));
  }

  async function start() {
    if (!selected && !(choice === "upload" && mode === "backend")) return;
    setStarting(true);
    setStartError(null);
    try {
      const job = selected ? await source.startJob(selected.id) : await source.startUpload(files);
      nav(`/run?job=${encodeURIComponent(job.job_id)}`);
    } catch (e) {
      setStartError(e instanceof SafeError ? e.message : SAFE_MESSAGES.server_error);
    } finally {
      setStarting(false);
    }
  }

  const uploadCannotRun = choice === "upload" && mode === "demo";

  return (
    <>
      <PageHeader
        eyebrow="Workflow"
        title="Process a dataset"
        lead="Choose synthetic hospital exports, review what will happen to them, and start a privacy-processing run."
      />
      <Steps step={step} />

      {step === 0 && (
        <div key="step-0" className="page-enter">
        <Section id="choose" title="Choose data" intro={`Supported formats: ${SUPPORTED}. Other files are set aside safely, never copied.`}>
          {datasets.status === "loading" && <Loading />}
          {datasets.status === "error" && <ErrorText message={datasets.message} />}
          <fieldset className={s.choices} aria-describedby={error ? "choose-error" : undefined}>
            <legend className="visually-hidden">Dataset</legend>
            {datasets.status === "ready" && all.length === 0 && (
              <p className={s.hint} style={{ padding: "var(--s-4) 0" }}>
                The backend offers no datasets. Clone the organiser toolkit next to the repository to enable the practice
                dataset.
              </p>
            )}
            {all.map((ds) => (
            <label key={ds.id} className={s.choice}>
              <input type="radio" name="dataset" checked={choice === ds.id} onChange={() => setChoice(ds.id)} />
              <span className={s.choiceTitle}>
                {ds.label}{" "}
                {datasets.status === "ready" && <SourceBadge source={datasets.data.source} provenance={datasets.data.provenance} />}
              </span>
              <span className={s.choiceText}>{ds.description}</span>
              <span className={s.choiceMeta}>
                <strong>{fmtInt(ds.files)} files</strong>
                <span>{fmtBytes(ds.bytes)}</span>
                {ds.expected_unsupported > 0 && <span>at least {ds.expected_unsupported} will be set aside safely</span>}
              </span>
              <FormatSummary formats={ds.formats} />
            </label>
            ))}
            <label className={s.choice}>
              <input type="radio" name="dataset" checked={choice === "upload"} onChange={() => setChoice("upload")} />
              <span className={s.choiceTitle}>Your own synthetic files</span>
              <span className={s.choiceText}>
                {mode === "backend"
                  ? "Upload synthetic exports to the local backend and process them with the real engine."
                  : "Inspect synthetic exports in this browser. Processing them needs the Local backend data source."}
              </span>
            </label>
          </fieldset>
          {choice === "upload" && (
            <div className="fade-enter">
            <UploadInspector
              confirmed={confirmed}
              setConfirmed={setConfirmed}
              inspection={inspection}
              setInspection={setInspection}
              setFiles={setFiles}
              live={mode === "backend"}
              error={error && choice === "upload" ? error : null}
            />
            </div>
          )}
          {error && choice !== "upload" && (
            <p id="choose-error" className={s.fieldError} role="alert" style={{ marginTop: "var(--s-3)" }}>
              <Icon name="alert" size={15} /> {error}
            </p>
          )}
        </Section>
        </div>
      )}

      {step === 1 && (
        <div key="step-1" className="page-enter">
        <Section id="policy" title="Review the processing policy" intro="What CLINVEIL does to the data today, in plain words. Items marked not available are not applied.">
          <PolicyReview />
        </Section>
        </div>
      )}

      {step === 2 && (
        <div key="step-2" className="page-enter">
        <Section id="confirm" title="Confirm and start">
          <dl className={d.facts} aria-label="Run summary">
            <div className={d.fact}>
              <dt>Dataset</dt>
              <dd style={{ fontSize: "var(--text-md)" }}>{selected ? selected.label : "Your synthetic files"}</dd>
            </div>
            <div className={d.fact}>
              <dt>Files</dt>
              <dd>{fmtInt(selected ? selected.files : (inspection?.files.length ?? 0))}</dd>
            </div>
            <div className={d.fact}>
              <dt>Policy</dt>
              <dd style={{ fontSize: "var(--text-md)" }}>Competition default</dd>
            </div>
            <div className={d.fact}>
              <dt>Runs on</dt>
              <dd style={{ fontSize: "var(--text-md)" }}>{mode === "demo" ? "Nothing: example mode" : "Local engine, offline"}</dd>
            </div>
          </dl>
          <div style={{ marginTop: "var(--s-6)", display: "grid", gap: "var(--s-4)" }}>
            {mode === "demo" && !uploadCannotRun && (
              <Notice tone="warn" title="Example mode: nothing will be processed">
                Starting opens a run that was recorded earlier with the real engine on this dataset. To process data,
                switch the data source to Local backend while the engine's demo API is running.
              </Notice>
            )}
            {uploadCannotRun && (
              <Notice tone="warn" title="Example mode cannot process your files">
                Switch the data source to Local backend while the engine's demo API is running, or process the files with
                the command-line engine.
              </Notice>
            )}
            {startError && <ErrorText message={startError} />}
          </div>
        </Section>
        </div>
      )}

      <div className={s.wizardNav}>
        {step > 0 && (
          <Button onClick={() => setStep((x) => x - 1)} variant="secondary">
            Back
          </Button>
        )}
        <span className={s.spacer} />
        {step < 2 && (
          <Button onClick={next} variant="primary" icon="arrowRight">
            Continue
          </Button>
        )}
        {step === 2 && !uploadCannotRun && (
          <Button onClick={start} variant="primary" icon="arrowRight" disabled={starting} aria-busy={starting}>
            {mode === "demo" ? "Open the recorded run" : starting ? "Starting…" : "Start privacy processing"}
          </Button>
        )}
        {step === 2 && uploadCannotRun && (
          <Button
            onClick={() => {
              setChoice(all[0]?.id ?? null);
              setStep(0);
            }}
            variant="secondary"
          >
            Choose the practice dataset
          </Button>
        )}
      </div>
      <NextStep />
    </>
  );
}
