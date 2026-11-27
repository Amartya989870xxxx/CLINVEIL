import { Notice } from "../../components/common/Notice";
import { NextStep, Section } from "../../components/data/Blocks";
import { PageHeader } from "../../components/layout/PageHeader";
import s from "../pages.module.css";

export function About() {
  return (
    <>
      <PageHeader
        eyebrow="Evidence"
        title="About and limitations"
        lead="What CLINVEIL is, the conditions it runs under, and what it does not yet guarantee."
      />
      <Section id="what" title="What CLINVEIL is">
        <div className={s.prose}>
          <p className={s.statement}>Remove who the patient is. Keep what happened to them.</p>
          <p>
            Indian hospitals export the same patients through registration systems, OPD software, lab systems, FHIR
            servers and typed discharge summaries, in English, Hindi and Hinglish. CLINVEIL turns those exports into a
            release that researchers can use: personal details are removed wherever they appear, and the clinical record
            is kept intact and in its original format.
          </p>
          <p>It is a prototype, not a certified medical system.</p>
        </div>
      </Section>
      <Section id="constraints" title="How it runs">
        <div className={s.prose}>
          <ul>
            <li><strong>Offline.</strong> No network access during a run, no hosted services, no telemetry.</li>
            <li><strong>No language models.</strong> Detection uses rules, lexicons and field meaning, so every decision can be traced.</li>
            <li><strong>Small machine.</strong> 2 CPUs, 4 GB of memory and 15 minutes per release, CPU only.</li>
            <li><strong>One command.</strong> <span className="mono">python main.py --input … --output …</span>; this interface is optional.</li>
          </ul>
        </div>
      </Section>
      <Section id="limits" title="Limitations today">
        <Notice tone="warn" title="Read this before relying on a release">
          A release from this version removes direct identifiers but can still contain information that identifies
          someone indirectly.
        </Notice>
        <div className={s.prose} style={{ marginTop: "var(--s-5)" }}>
          <ul>
            <li><strong>Conservative linking.</strong> Records are linked only on strong evidence; some records of the same patient stay unlinked. A relative's age or Aadhaar written in a later block than their name can still be attributed to the patient (OBS-1).</li>
            <li><strong>Partial indirect-identifier protection.</strong> Dates are shifted per patient, structured ages are banded and PIN prefixes are kept only in groups of 5 or more. Villages are removed, not generalised; ages in free text and JSON numbers are kept; there is no formal k-anonymity.</li>
            <li><strong>Unsupported files are set aside.</strong> PDF, images, XML and archives are not opened, so their content is missing from the release.</li>
            <li><strong>Known detection gaps.</strong> Unseen ID and date formats, and names that appear with no label or context anywhere; see Privacy and quality.</li>
            <li><strong>Large files.</strong> Very large single files have not been re-measured since the Phase 2.1 speed-up.</li>
            <li><strong>Not measured against the attacker.</strong> Re-identification resistance is only measured by the official evaluator.</li>
          </ul>
        </div>
      </Section>
      <Section id="threats" title="What it is designed to resist">
        <div className={s.prose}>
          <ul>
            <li><strong>Hidden identifiers</strong> in file names, column headers, JSON keys, export metadata and base64 attachments.</li>
            <li><strong>Hostile files</strong>: oversized, deeply nested, malformed or mislabelled inputs, and links pointing outside the input. They are set aside, never executed or copied.</li>
            <li><strong>Leaking the key.</strong> The release secret is read from the environment and cannot be printed into any output.</li>
          </ul>
          <p>
            It does not protect against an attacker who already holds outside data that matches the indirect identifiers
            it still releases.
          </p>
        </div>
      </Section>
      <Section id="interface" title="About this interface">
        <div className={s.prose}>
          <ul>
            <li>Example data is recorded from real engine runs on synthetic data and is always labelled as such.</li>
            <li>It never shows real patient data, answer keys, attacker data or identity mappings, and cannot reverse a pseudonym.</li>
            <li>No analytics, no third-party requests; fonts are bundled. Your theme and data-source choice are stored only in this browser.</li>
            <li>Fonts: Geist, Newsreader, IBM Plex Mono and Noto Sans Devanagari, under the SIL Open Font License 1.1.</li>
          </ul>
        </div>
      </Section>
      <NextStep fallback={{ to: "/overview", label: "Back to the overview" }} />
    </>
  );
}
