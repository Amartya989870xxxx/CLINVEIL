// EXAMPLE DATA: aggregate results of the team's INTERNAL red-team suite (CLINVEIL-REDTEAM-v1.0, public tiers only,
// evaluator 1.1) against engine ac3750425d1ee8582f288d05624f3f06e1151fa1, 2026-11-27. Not an official score.
// Values copied from the suite's reports/{quick_20261127-000230, standard_20261127-000138, fhir_20261127-000220,
// security_20261127-000214}.json. Aggregates only: no inputs, labels, file names or identities from that suite
// are included. The private blind tier is deliberately not shown.

export interface RedTeamTier {
  tier: string;
  files: number;
  description: string;
  pii_total: number;
  pii_left_visible: number;
  recall_on_exported_pct: number;
  clinical_kept_pct: number;
  correct_handling_pct: number;
  security_flags: number;
}

export const redTeam = {
  source: "example_fixture" as const,
  suite: "CLINVEIL-REDTEAM-v1.0 (internal, public tiers, evaluator 1.1)",
  engine_commit: "ac3750425d1ee8582f288d05624f3f06e1151fa1",
  recorded_on: "2026-11-27",
  tiers: [
    { tier: "Quick", files: 65, description: "Representative cases", pii_total: 668, pii_left_visible: 25, recall_on_exported_pct: 96.11, clinical_kept_pct: 98.54, correct_handling_pct: 100, security_flags: 0 },
    { tier: "Standard", files: 384, description: "Eight fictional hospital systems", pii_total: 4404, pii_left_visible: 388, recall_on_exported_pct: 91.17, clinical_kept_pct: 99.25, correct_handling_pct: 100, security_flags: 0 },
    { tier: "FHIR", files: 52, description: "Adversarial FHIR R4 bundles", pii_total: 779, pii_left_visible: 259, recall_on_exported_pct: 62.46, clinical_kept_pct: 100, correct_handling_pct: 100, security_flags: 0 },
    { tier: "Security", files: 58, description: "Malformed and hostile files", pii_total: 73, pii_left_visible: 2, recall_on_exported_pct: 95.92, clinical_kept_pct: 100, correct_handling_pct: 100, security_flags: 0 },
  ] satisfies RedTeamTier[],
  // Weaknesses this suite found in ac37504, with their status after Phase 2.1 (engine 9205b5a) as reported in
  // docs/evaluation/PHASE2_REMEDIATION.md. "Reported fixed" is the team's own report; this suite has not re-run.
  known_gaps: [
    {
      gap: "Free text in FHIR resources other than Patient (for example observation notes) was not checked for names or record numbers.",
      status: "Reported fixed in Phase 2.1 (B1)",
      fixed: true,
    },
    {
      gap: "A complaint written as 'C/O Left knee pain' was misread as 'care of' a relative and partly redacted.",
      status: "Reported fixed in Phase 2.1 (D2)",
      fixed: true,
    },
    {
      gap: "Processing time grew with the square of the number of findings or rows in one file: one CSV of about 118,000 rows would exceed the official 15 minutes.",
      status: "Partly addressed in Phase 2.1 (E4): the resolver is now near-linear; large files not re-measured",
      fixed: false,
    },
    {
      gap: "Date formats not seen before, such as 21-Sep-2000, could survive even after a 'DOB:' label.",
      status: "Not listed in the Phase 2.1 report; treat as open",
      fixed: false,
    },
  ],
};
