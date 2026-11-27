// Plain-language wording for codes the engine reports. Codes are fixed vocabularies; nothing here is derived
// from record content.

import type { DimensionId, EntityType, QuarantineReason, StageId } from "../services/api/types";

export const ENTITY_GROUPS: { group: string; types: { type: EntityType; label: string }[] }[] = [
  {
    group: "Names",
    types: [
      { type: "PATIENT_NAME", label: "Patient names" },
      { type: "RELATIVE_NAME", label: "Relatives' names" },
    ],
  },
  {
    group: "Identity numbers",
    types: [
      { type: "MRN", label: "Hospital record numbers (UHID, IPD, MRN)" },
      { type: "AADHAAR", label: "Aadhaar numbers" },
      { type: "AADHAAR_MASKED", label: "Masked Aadhaar numbers" },
      { type: "ABHA_NUMBER", label: "ABHA health IDs" },
      { type: "ABHA_ADDRESS", label: "ABHA addresses" },
      { type: "PAN", label: "PAN numbers" },
      { type: "INSURANCE_ID", label: "Insurance and scheme IDs" },
    ],
  },
  {
    group: "Contact details",
    types: [
      { type: "PHONE", label: "Phone numbers" },
      { type: "EMAIL", label: "E-mail addresses" },
    ],
  },
  {
    group: "Address details",
    types: [
      { type: "HOUSE", label: "House numbers" },
      { type: "LOCALITY", label: "Localities and wards" },
      { type: "LANDMARK", label: "Landmarks" },
      { type: "VILLAGE", label: "Villages" },
      { type: "PIN", label: "PIN codes" },
    ],
  },
  { group: "Dates", types: [{ type: "DOB", label: "Dates of birth" }] },
];

export const REASONS: Record<QuarantineReason, { text: string; next: string }> = {
  empty_file: { text: "Empty file", next: "Nothing to process; check the export." },
  file_too_large: { text: "Larger than the configured size limit", next: "Split the export or raise the limit." },
  implausible_text: { text: "Does not look like readable text", next: "Check the file's encoding or content." },
  invalid_json: { text: "Broken or truncated JSON", next: "Re-export the file." },
  json_too_deep: { text: "JSON nested beyond the safe depth", next: "Flatten the export structure." },
  json_too_large: { text: "JSON larger than the safe size", next: "Split the export." },
  undecodable_text: { text: "Text in an unreadable encoding", next: "Re-export as UTF-8." },
  unsupported_archive: { text: "Archive (zip, tar, gzip): not opened", next: "Extract and provide the files individually." },
  unsupported_attachment: { text: "Contains an attachment type that cannot be checked", next: "Remove the attachment or export it separately." },
  unsupported_binary: { text: "Binary file", next: "Provide a text export." },
  unsupported_format: { text: "Unsupported format", next: "Provide CSV, TSV, JSON, FHIR R4 or text." },
  unsupported_image: { text: "Image (cannot be checked for text)", next: "Images are out of scope for this release." },
  unsupported_pdf: { text: "PDF (cannot be checked reliably)", next: "Provide a text export of the document." },
  unsupported_xml: { text: "XML (not supported in this release)", next: "Provide a JSON or FHIR JSON export." },
  invalid_attachment: { text: "Attachment that cannot be decoded", next: "Re-export the file." },
  attachment_too_large: { text: "Attachment larger than the safe size", next: "Export the attachment separately." },
  symlink_outside_input: { text: "Link pointing outside the input folder", next: "Copy the real file into the input." },
  not_a_regular_file: { text: "Not a regular file", next: "Provide ordinary files only." },
};

export const STAGES: Record<StageId, { order: number; title: string; plain: string }> = {
  ingestion: { order: 1, title: "Reading and checking files", plain: "Every export is read and checked; files that cannot be read safely are set aside, never copied." },
  detection: { order: 2, title: "Finding personal information", plain: "Names, identity numbers, contact and address details are found in text, tables, keys, file names and attachments, in Latin, Devanagari and Hinglish." },
  linking: { order: 3, title: "Connecting records of the same patient", plain: "Records are linked only when strong evidence connects them; uncertain records stay unlinked." },
  privacy_transforms: { order: 4, title: "Protecting indirect identifiers", plain: "Ages, places and dates that could identify someone indirectly are generalised or shifted." },
  export: { order: 5, title: "Preserving clinical information and exporting", plain: "Personal details are replaced in place; medicines, doses, vitals, labs and diagnoses are kept, in the original formats." },
  validation: { order: 6, title: "Checking privacy, format and consistency", plain: "The release, its report and its record list are validated before the run reports success." },
};

export const DETAIL_TEXT: Record<string, string> = {
  files_set_aside: "Some files were set aside safely.",
  phase_3: "Not built yet: planned for Phase 3.",
  partial_dob_and_birth_year_only: "Only dates of birth are protected today (removed, or reduced to the year in FHIR). Age bands, place generalisation and date shifting are not built yet.",
  partial_phase4:
    "Applied: per-patient keyed date shift (ambiguous dates suppressed), 5-year age bands for structured ages, 3-digit PIN prefixes where at least 5 records share them. Not built: village to tehsil/district (villages are removed instead), banding of JSON numeric and free-text ages, formal k-anonymity.",
  contract_ok: "Release validated against the organiser's output contract.",
  no_stage_progress: "Running. The engine reports stage results when the run finishes.",
};

export const DIMENSION_LABEL: Record<DimensionId, string> = {
  privacy_attacks: "Privacy against attacks",
  detection: "Personal-data detection",
  utility: "Medical-data preservation",
  identity: "Patient identity consistency",
  integrity: "Output quality and validity",
  performance: "Speed and reliability",
};

/** The question each organiser scoring dimension asks, in plain words. */
export const DIMENSION_QUESTION: Record<DimensionId, string> = {
  privacy_attacks: "Can an attacker re-identify a patient from the release?",
  detection: "Are names, numbers, contact and address details removed everywhere they appear?",
  utility: "Do diagnoses, medicines, doses, vitals and lab values survive unchanged?",
  identity: "Are records of the same patient connected, and only when the evidence is strong?",
  integrity: "Is the release in the required format, complete, and free of unsafe copies?",
  performance: "Does it finish within the official limits (2 CPUs, 4 GB, 15 minutes)?",
};
