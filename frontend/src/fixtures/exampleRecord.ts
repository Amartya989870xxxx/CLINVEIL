// EXAMPLE DATA: one invented synthetic discharge summary and the REAL output of CLINVEIL for it.
// Re-recorded 2026-11-27: python3 main.py --input <dir with this file> --output <out>, engine
// 442dfbdbbaed77e0ccc283911bed825a890a5e20, RAKSHA_SECRET set to a fixture-only value (so the pseudonym below is
// stable for this example and unrelated to any real release). The "after" text is copied verbatim from
// sanitized/; nothing was edited by hand. Highlight spans are computed from the listed substrings (tests assert they all exist).

import type { Example, Examples, Span } from "../services/api/types";
import { RECORDED_JOB_ID } from "./recordedPracticeRun";

export const EXAMPLE_ENGINE_COMMIT = "442dfbdbbaed77e0ccc283911bed825a890a5e20";

export const BEFORE = "ARAVALIKA MULTISPECIALITY HOSPITAL (SYNTHETIC EXAMPLE)\nDISCHARGE SUMMARY\n\nPatient Name: Kalindi Awasthi        Age/Sex: 58 Yrs/F\nUHID: AMH/26/041273        IPD No: AMH-IP-26-30417\nW/o Ramesh Awasthi\nAddress: H.No. 214, Mohalla Neem Chowk, Vill. Fatehganj, Tehsil Amarkot Sadar, Distt. Amarkot - 271304\nMobile: +91 98765 12034\nDOB: 14/03/1968\nConsultant: Dr. Ramesh Iyengar (MD Medicine)\nWard/Bed: Ward 4 (Medicine) / Bed 12\n\nDiagnosis: Type 2 diabetes mellitus without complications (E11.9)\nPresenting complaints: C/O fever x 4 days, giddiness since morning.\nVitals: BP 138/86, Pulse 92/min, SpO2 97%\nHaemoglobin 10.8 g/dL; Random Blood Sugar 246 mg/dL\n\nMedications on discharge:\n 1. Tab Dolo 650 BD x 5 days\n 2. Tab Metformin 500 mg 1-0-1 x 30 days\n\nAdvice: Review in OPD after 2 weeks with Dr. Ramesh Iyengar.\nAttendant: Ramesh Awasthi, Mob. 9876512034\n";

export const AFTER = "ARAVALIKA MULTISPECIALITY HOSPITAL (SYNTHETIC EXAMPLE)\nDISCHARGE SUMMARY\n\nPatient Name: [NAME]        Age/Sex: 58 Yrs/F\nUHID: PSN-B05B4R        IPD No: [MRN]\nW/o [RELATIVE]\nAddress: [HOUSE], [LOCALITY], Vill. [VILLAGE], Tehsil Amarkot Sadar, Distt. Amarkot - [PIN]\nMobile: [PHONE]\nDOB: [DOB]\nConsultant: Dr. Ramesh Iyengar (MD Medicine)\nWard/Bed: Ward 4 (Medicine) / Bed 12\n\nDiagnosis: Type 2 diabetes mellitus without complications (E11.9)\nPresenting complaints: C/O fever x 4 days, giddiness since morning.\nVitals: BP 138/86, Pulse 92/min, SpO2 97%\nHaemoglobin 10.8 g/dL; Random Blood Sugar 246 mg/dL\n\nMedications on discharge:\n 1. Tab Dolo 650 BD x 5 days\n 2. Tab Metformin 500 mg 1-0-1 x 30 days\n\nAdvice: Review in OPD after 2 weeks with Dr. Ramesh Iyengar.\nAttendant: [RELATIVE], Mob. [PHONE]\n";

/** What the engine removed (before), and the placeholders it wrote (after). */
export const REMOVED_BEFORE = [
  "Kalindi Awasthi", "AMH/26/041273", "AMH-IP-26-30417", "Ramesh Awasthi", "H.No. 214", "Mohalla Neem Chowk",
  "Fatehganj", "271304", "+91 98765 12034", "14/03/1968", "9876512034",
];
export const REMOVED_AFTER = ["[NAME]", "PSN-B05B4R", "[MRN]", "[RELATIVE]", "[HOUSE]", "[LOCALITY]", "[VILLAGE]", "[PIN]", "[PHONE]", "[DOB]"];

/** Clinical content that must survive, present in both texts. */
export const PRESERVED = [
  "Dr. Ramesh Iyengar", "Type 2 diabetes mellitus without complications (E11.9)", "C/O fever x 4 days",
  "BP 138/86", "Pulse 92/min", "SpO2 97%", "Haemoglobin 10.8 g/dL", "Random Blood Sugar 246 mg/dL",
  "Tab Dolo 650 BD x 5 days", "Tab Metformin 500 mg 1-0-1 x 30 days", "Ward 4 (Medicine)",
];

/** Kept as written by the current engine: an age inside free text is not banded (only structured ages are), and
 * tehsil and district are kept by design. Shown as "not generalised". */
export const NOT_YET_GENERALISED = ["58 Yrs/F", "Tehsil Amarkot Sadar", "Distt. Amarkot"];

export function spansOf(text: string, needles: string[], kind: Span["kind"]): Span[] {
  const out: Span[] = [];
  for (const n of needles) {
    let i = text.indexOf(n);
    while (i >= 0) {
      out.push({ start: i, end: i + n.length, kind });
      i = text.indexOf(n, i + n.length);
    }
  }
  return out.sort((a, b) => a.start - b.start);
}

const example: Example = {
  id: "discharge-synthetic-1",
  title: "Discharge summary (invented synthetic patient)",
  before: BEFORE,
  after: AFTER,
  synthetic: true,
  spans_before: [...spansOf(BEFORE, REMOVED_BEFORE, "removed"), ...spansOf(BEFORE, PRESERVED, "preserved"),
    ...spansOf(BEFORE, NOT_YET_GENERALISED, "generalised")].sort((a, b) => a.start - b.start),
  spans_after: [...spansOf(AFTER, REMOVED_AFTER, "removed"), ...spansOf(AFTER, PRESERVED, "preserved"),
    ...spansOf(AFTER, NOT_YET_GENERALISED, "generalised")].sort((a, b) => a.start - b.start),
};

export const exampleRecord: Examples = {
  contract: "clinveil-frontend/1",
  source: "example_fixture",
  provenance: {
    source: "example_fixture",
    recorded_from: "CLINVEIL run on one invented synthetic discharge summary",
    engine_commit: EXAMPLE_ENGINE_COMMIT,
    dataset: "One synthetic discharge summary written for this preview",
    command: "python3 main.py --input <folder with the record> --output <out>",
    recorded_on: "2026-11-27",
  },
  job_id: RECORDED_JOB_ID,
  examples: [example],
};
