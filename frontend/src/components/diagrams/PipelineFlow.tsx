import { StatusTag } from "../common/StatusTag";
import type { Capability, CapabilityState } from "../../services/api/types";
import s from "./diagrams.module.css";

export interface FlowStep {
  key: Capability;
  title: string;
  text: string;
}

export const OVERVIEW_STEPS: FlowStep[] = [
  { key: "ingestion", title: "Import", text: "Read every export, check encodings and formats, set aside what cannot be read safely." },
  { key: "detection", title: "Detect", text: "Find personal information in text, tables, keys, file names and attachments, in three scripts." },
  { key: "linking", title: "Link", text: "Connect records of the same patient only when the evidence is strong." },
  { key: "privacy_transforms", title: "Protect", text: "Reduce information that could identify someone indirectly: ages, places, dates." },
  { key: "validation", title: "Validate", text: "Check the release format, the report and that clinical values survived." },
];

/** A compact numbered sequence; status comes from the data source, never assumed. */
export function PipelineFlow({
  steps,
  states,
}: {
  steps: FlowStep[];
  states: Partial<Record<Capability, CapabilityState>> | null;
}) {
  return (
    <ol className={s.flow}>
      {steps.map((st, i) => (
        <li key={st.key} className={s.flowStep} style={{ animationDelay: `${120 + i * 110}ms` }}>
          <div className={s.flowHead}>
            <span className={s.flowNum} aria-hidden="true">
              {String(i + 1).padStart(2, "0")}
            </span>
            <h3 className={s.flowTitle}>{st.title}</h3>
          </div>
          <p className={s.flowText}>{st.text}</p>
          <div className={s.flowState}>
            {states?.[st.key] ? <StatusTag state={states[st.key] as CapabilityState} /> : <span className="meta">Status unknown</span>}
          </div>
        </li>
      ))}
    </ol>
  );
}
