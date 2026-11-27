import { useState } from "react";

import { Icon } from "../../components/common/Icon";
import { StatusTag } from "../../components/common/StatusTag";
import { NextStep, Section } from "../../components/data/Blocks";
import { PageHeader } from "../../components/layout/PageHeader";
import type { CapabilityState } from "../../services/api/types";
import s from "../pages.module.css";

interface Part {
  id: string;
  name: string;
  one: string;
  state: CapabilityState;
  does: string;
  code: string;
  safeguards: string;
  limits: string;
}

// Describes the engine at ac37504. Module paths are real; statuses match the Overview.
const PARTS: Part[] = [
  {
    id: "ingest",
    name: "Ingestion",
    one: "Find, decode and parse every export safely",
    state: "implemented",
    does: "Walks the input folder, identifies each file by content, decodes UTF-8, UTF-16 and Windows-1252 text and parses CSV, TSV, JSON, FHIR R4 and text into one document model.",
    code: "ingestion/, parsing/",
    safeguards: "Size, depth and count limits; links outside the input refused; anything unreadable is set aside with a reason, never copied.",
    limits: "PDF, images, XML and archives are not opened.",
  },
  {
    id: "detect",
    name: "Detection",
    one: "Find personal information wherever it hides",
    state: "implemented",
    does: "Labelled values, field meaning and name lexicons with transliteration across Latin, Devanagari and Hinglish. Two passes: a value confirmed in one file is found again in notes, file names, JSON keys and attachments elsewhere.",
    code: "detection/",
    safeguards: "Clinical vocabulary is protected from redaction; doctors' names are kept.",
    limits: "Unseen date formats and names with no context at all can still be missed (see Privacy and quality).",
  },
  {
    id: "link",
    name: "Linking",
    one: "Connect records of the same patient",
    state: "not_available",
    does: "Planned: link records across files only when strong evidence agrees, and give each patient one consistent pseudonym.",
    code: "linking/linker.py (placeholder)",
    safeguards: "Design rule: uncertain records stay unlinked.",
    limits: "Not built. Every record is currently unlinked.",
  },
  {
    id: "protect",
    name: "Privacy transforms",
    one: "Reduce indirect identifiers",
    state: "partial",
    does: "Dates of birth are removed (reduced to the year in FHIR). Planned: age bands, place generalisation, consistent date shifts.",
    code: "privacy/",
    safeguards: "Keyed pseudonym and date-shift functions exist but are not yet applied. The key is read from the engine's environment, never written out, and there is no default key.",
    limits: "Exact ages, villages, districts and visit dates are still released.",
  },
  {
    id: "export",
    name: "Sanitisation and export",
    one: "Replace details in place and write the release",
    state: "implemented",
    does: "Rewrites each document with placeholders, keeping its format, columns and structure, and writes the report and record list.",
    code: "sanitization/, export/",
    safeguards: "Nothing is copied: every exported byte is rendered from the parsed document. No temporary files; inputs are opened read-only.",
    limits: "Very large single files have not been re-measured since the Phase 2.1 speed-up.",
  },
  {
    id: "validate",
    name: "Validation",
    one: "Check the release before reporting success",
    state: "implemented",
    does: "Checks the output contract, report counts and that no set-aside file was copied.",
    code: "validation/contract.py, pipeline.py",
    safeguards: "The release is re-checked on disk before the engine exits successfully; an incomplete release exits with code 1.",
    limits: "It checks structure, not re-identification risk.",
  },
];

function PartRow({ p, i }: { p: Part; i: number }) {
  const [open, setOpen] = useState(false);
  const bodyId = `arch-${p.id}`;
  return (
    <li className={s.archItem}>
      <button type="button" className={s.archBtn} aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen((o) => !o)}>
        <span className={s.stageIdx}>{String(i + 1).padStart(2, "0")}</span>
        <span>
          <span className={s.archName}>{p.name}</span>
          <span className={s.archOne}>{p.one}</span>
        </span>
        <StatusTag state={p.state} />
        <Icon name="chevronDown" size={18} />
      </button>
      {/* grid-rows 0fr -> 1fr animates the height; inert keeps closed content out of the tab order and AT */}
      <div id={bodyId} className={s.archClip} data-open={open ? "" : undefined} {...(open ? {} : { inert: "" })}>
      <div className={s.archBody}>
        <div>
          <h4>What it does</h4>
          <p>{p.does}</p>
        </div>
        <div>
          <h4>Where</h4>
          <p className="mono">{p.code}</p>
        </div>
        <div>
          <h4>Safeguards</h4>
          <p>{p.safeguards}</p>
        </div>
        <div>
          <h4>Limits today</h4>
          <p>{p.limits}</p>
        </div>
      </div>
      </div>
    </li>
  );
}

export function Architecture() {
  return (
    <>
      <PageHeader
        eyebrow="Evidence"
        title="Architecture"
        lead="How hospital exports become a research-ready release: one offline command, six stages, no network and no language models."
      />
      <Section id="zones" title="What runs where">
        <div className={s.zones}>
          <div className={`${s.zone} ${s.zonePrimary}`}>
            <span className="eyebrow">Required</span>
            <h3>CLINVEIL engine</h3>
            <p>
              A Python command run by the organisers: <span className="mono">python main.py --input … --output …</span>.
              Offline, CPU only, within 2 CPUs, 4 GB and 15 minutes. This is what is scored.
            </p>
          </div>
          <div className={`${s.zone} ${s.zoneFuture}`}>
            <span className="eyebrow">Planned · Phase 7</span>
            <h3>Local demo API</h3>
            <p>A thin local wrapper that runs allowlisted synthetic datasets and serves results to this interface. Not built.</p>
          </div>
          <div className={s.zone}>
            <span className="eyebrow">Optional</span>
            <h3>This interface</h3>
            <p>Explains and evidences a run. Never on the evaluator's path; the engine does not need it.</p>
          </div>
        </div>
      </Section>
      <Section id="pipeline" title="The pipeline" intro="Select a stage for what it does, where the code lives, its safeguards and its limits today.">
        <ol className={s.arch}>
          {PARTS.map((p, i) => (
            <PartRow key={p.id} p={p} i={i} />
          ))}
        </ol>
      </Section>
      <Section id="principles" title="Design rules">
        <div className={s.prose}>
          <ul>
            <li><strong>Fail closed.</strong> A file that cannot be checked is set aside, never copied.</li>
            <li><strong>Replace in place.</strong> Formats, columns and structure are preserved so the data stays usable.</li>
            <li><strong>Keep clinical meaning.</strong> Medical vocabulary is protected from redaction.</li>
            <li><strong>No outside calls.</strong> No network, no hosted AI, no telemetry; the secret key never leaves the engine.</li>
          </ul>
        </div>
      </Section>
      <NextStep fallback={{ to: "/about", label: "About and limitations" }} />
    </>
  );
}
