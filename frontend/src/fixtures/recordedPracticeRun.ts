// EXAMPLE DATA. Every value below was recorded from one real CLINVEIL run; nothing here is live and the UI must
// label it "Example data". Recorded 2026-11-27 with:
//   RAKSHA_SECRET=<random> python3 main.py --input organiser-toolkit/dev/input --output <out>
//   python3 organiser-toolkit/validate_output.py --input organiser-toolkit/dev/input --output <out>  -> CONTRACT OK
//   python3 organiser-toolkit/check_dev.py --output <out>
// Engine commit ac3750425d1ee8582f288d05624f3f06e1151fa1 (main). Input: the organiser's synthetic practice set.
// Contains aggregates only: no record content, no answer key, no attacker data, no file names from the input.

import type {
  DatasetList,
  Findings,
  FixtureProvenance,
  Health,
  JobStatus,
  Metrics,
  QuarantineSummary,
  Summary,
} from "../services/api/types";

export const ENGINE_COMMIT = "ac3750425d1ee8582f288d05624f3f06e1151fa1";
export const RECORDED_JOB_ID = "example-practice-2026-11-27";

const provenance: FixtureProvenance = {
  source: "example_fixture",
  recorded_from: "One recorded CLINVEIL run on the organiser's synthetic practice dataset",
  engine_commit: ENGINE_COMMIT,
  dataset: "Secret Wards practice dataset (synthetic, 200 files)",
  command: "python3 main.py --input organiser-toolkit/dev/input --output <out>",
  recorded_on: "2026-11-27",
};

const env = { contract: "clinveil-frontend/1" as const, source: "example_fixture" as const, provenance };

export const exampleHealth: Health = {
  ...env,
  status: "ok",
  engine_version: "0.1.0",
  engine_commit: ENGINE_COMMIT,
  capabilities: {
    ingestion: "implemented",
    detection: "implemented",
    linking: "not_available",
    privacy_transforms: "partial",
    export: "implemented",
    validation: "implemented",
  },
};

export const exampleDatasets: DatasetList = {
  ...env,
  datasets: [
    {
      id: "practice-synthetic",
      label: "Secret Wards practice dataset",
      synthetic: true,
      description:
        "The organiser's synthetic practice exports from four fictional hospital systems: registrations, OPD visits, " +
        "discharge summaries, Hindi prescriptions, Hinglish nursing notes, lab reports, FHIR R4 bundles and " +
        "deliberately broken files.",
      files: 200,
      bytes: 626836,
      formats: { text: 101, json: 60, fhir: 19, csv: 16, tsv: 1, xml: 1, pdf: 1, image: 1 },
      expected_unsupported: 7,
    },
  ],
};

export const exampleJob: JobStatus = {
  ...env,
  job_id: RECORDED_JOB_ID,
  dataset_id: "practice-synthetic",
  state: "complete_with_quarantine",
  started_at: null, // not recorded; only the date is known (provenance.recorded_on)
  finished_at: null,
  exit_code: 0,
  seconds: 0.89,
  stages: [
    { id: "ingestion", state: "complete", detail_code: "files_set_aside" },
    { id: "detection", state: "complete", detail_code: null },
    { id: "linking", state: "not_available", detail_code: "phase_3" },
    { id: "privacy_transforms", state: "needs_attention", detail_code: "partial_dob_and_birth_year_only" },
    { id: "export", state: "complete", detail_code: null },
    { id: "validation", state: "complete", detail_code: "contract_ok" },
  ],
};

export const exampleSummary: Summary = {
  ...env,
  job_id: RECORDED_JOB_ID,
  counts: {
    files_total: 200,
    files_sanitized: 193,
    files_quarantined: 7,
    records_processed: 822,
    identifiers_detected: 3350,
    records_linked: 0,
    records_generalized: 19,
    records_suppressed: 0,
    records_quarantined: 0,
  },
  timing: { seconds: 0.89 },
  resources: { peak_rss_mb: 32.1 },
  validation: { contract_ok: true, checker: "validate_output.py" },
};

export const exampleFindings: Findings = {
  ...env,
  job_id: RECORDED_JOB_ID,
  by_type: {
    PATIENT_NAME: 1022,
    RELATIVE_NAME: 247,
    MRN: 891,
    PHONE: 313,
    PIN: 136,
    VILLAGE: 150,
    HOUSE: 132,
    LOCALITY: 107,
    LANDMARK: 64,
    DOB: 111,
    AADHAAR: 70,
    AADHAAR_MASKED: 16,
    ABHA_NUMBER: 46,
    PAN: 22,
    INSURANCE_ID: 22,
    EMAIL: 1,
  },
  by_script: null, // the engine's report does not break findings down by script yet
  by_channel: null,
};

export const exampleQuarantine: QuarantineSummary = {
  ...env,
  job_id: RECORDED_JOB_ID,
  reasons: {
    unsupported_image: 1,
    unsupported_pdf: 1,
    unsupported_xml: 1,
    invalid_json: 1,
    json_too_deep: 1,
    empty_file: 1,
    implausible_text: 1,
  },
  files: [
    { input_sha256: "545d612719ef21751e821337a9a72f5d8afcd8f5929d140808c4e37fc76314e6", output: null, status: "quarantined", format: "image", reason: "unsupported_image" },
    { input_sha256: "03ba7a3e2ee45aef33e292a0e60a9ff8acd96ce37a12f226a6a1e4a5e5c873c0", output: null, status: "quarantined", format: "pdf", reason: "unsupported_pdf" },
    { input_sha256: "17f77cf14e5499ba2268a0fafaa14fbff1bffe27862da5c0db6ea7ad4daf8d97", output: null, status: "quarantined", format: "xml", reason: "unsupported_xml" },
    { input_sha256: "b4bebb0bd74872503fa6166007f412d6398a091dd603c869a43b62e186d20770", output: null, status: "quarantined", format: "json", reason: "invalid_json" },
    { input_sha256: "15f3447e4be3f05fc4c5b1fe86d72c6f436aba14e7329c2b7aff3bfb0787cb83", output: null, status: "quarantined", format: "json", reason: "json_too_deep" },
    { input_sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", output: null, status: "quarantined", format: "empty", reason: "empty_file" },
    { input_sha256: "5284a0c91899945c97cdc81ea953d22866d1e1accefed566af2d83dec1e33fe8", output: null, status: "quarantined", format: "text", reason: "implausible_text" },
  ],
};

const practice = "Secret Wards practice dataset (synthetic, 200 files)";
const checked = "2026-11-27";

export const exampleMetrics: Metrics = {
  ...env,
  job_id: RECORDED_JOB_ID,
  dimensions: [
    {
      id: "privacy_attacks",
      measurements: [
        { key: "attack_arena", label: "Resistance to the organiser's attack arena (A1-A7)", value: null, unit: "ratio", dataset: practice, method: "Official evaluator (not available to teams before the event)", measured_at: null, caveat: "Only the official evaluator runs the attacker. Internal red-team runs are reported separately." },
      ],
    },
    {
      id: "detection",
      measurements: [
        { key: "pii_visible", label: "Practice-set personal information still visible", value: 0, numerator: 0, denominator: 3230, unit: "count", dataset: practice, method: "organiser check_dev.py", measured_at: checked, caveat: "Measured on the practice set only. The hidden datasets contain unseen names, labels and formats." },
        { key: "canaries_found", label: "Planted canary identities found in the output", value: 0, numerator: 0, denominator: 4, unit: "count", dataset: practice, method: "organiser check_dev.py", measured_at: checked, caveat: null },
      ],
    },
    {
      id: "utility",
      measurements: [
        { key: "medical_values_kept", label: "Medical values kept", value: 1, numerator: 4855, denominator: 4855, unit: "ratio", dataset: practice, method: "organiser check_dev.py", measured_at: checked, caveat: "Checks that listed values survive verbatim; it is not a clinical certification." },
      ],
    },
    {
      id: "identity",
      measurements: [
        { key: "linking_f05", label: "Records confidently linked (pairwise F0.5)", value: null, unit: "ratio", dataset: practice, method: "organiser check_dev.py", measured_at: checked, caveat: "Linking is not implemented yet (Phase 3). The checker reports 0.00 because no record is linked." },
      ],
    },
    {
      id: "integrity",
      measurements: [
        { key: "contract_ok", label: "Output contract validation", value: 1, unit: "bool", dataset: practice, method: "organiser validate_output.py", measured_at: checked, caveat: null },
        { key: "raw_copies", label: "Broken files copied out unchanged", value: 0, unit: "count", dataset: practice, method: "organiser check_dev.py", measured_at: checked, caveat: null },
      ],
    },
    {
      id: "performance",
      measurements: [
        { key: "seconds", label: "Processing time", value: 0.89, unit: "seconds", dataset: practice, method: "report.json timing", measured_at: checked, caveat: "Laptop measurement without the official 2-CPU / 4 GB limits. Internal tests show quadratic slow-downs on very large files." },
        { key: "peak_rss_mb", label: "Peak memory", value: 32.1, unit: "mb", dataset: practice, method: "report.json resources", measured_at: checked, caveat: null },
      ],
    },
  ],
};
