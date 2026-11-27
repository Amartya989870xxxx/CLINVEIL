// Upload of user-selected SYNTHETIC files to the local demo API (POST /api/v1/jobs with "upload").
// Checks here mirror the server's (backend/scripts/demo_api.py); the server re-checks everything. File contents go
// only to the local backend; nothing is logged, stored in the browser, or kept after the request.

export const UPLOAD_LIMITS = { files: 200, totalBytes: 32 * 1024 * 1024 };
export const UPLOAD_EXTENSIONS = [".csv", ".tsv", ".tab", ".txt", ".json"] as const;

export type UploadProblem = "none_selected" | "too_many" | "too_large" | "unsupported" | "bad_name" | "duplicate";

export const UPLOAD_PROBLEM_TEXT: Record<UploadProblem, string> = {
  none_selected: "Select at least one synthetic file.",
  too_many: `Upload at most ${UPLOAD_LIMITS.files} files at a time.`,
  too_large: "The selected files are larger than the local upload limit (32 MB).",
  unsupported: "Only .csv, .tsv, .tab, .txt and .json files (including FHIR R4 JSON) can be uploaded.",
  bad_name: "A file name is not usable. Rename the file and try again.",
  duplicate: "Two selected files have the same name. Rename one of them.",
};

function extension(name: string): string {
  const i = name.lastIndexOf(".");
  return i > 0 ? name.slice(i).toLowerCase() : "";
}

/** First problem that would make the server reject this selection, or null. Names are checked, never shown. */
export function uploadProblem(files: File[]): UploadProblem | null {
  if (files.length === 0) return "none_selected";
  if (files.length > UPLOAD_LIMITS.files) return "too_many";
  let total = 0;
  const seen = new Set<string>();
  for (const f of files) {
    total += f.size;
    // eslint-disable-next-line no-control-regex
    if (!f.name || f.name.length > 128 || f.name.startsWith(".") || /[/\\\u0000-\u001f\u007f]/.test(f.name)) return "bad_name";
    if (!(UPLOAD_EXTENSIONS as readonly string[]).includes(extension(f.name))) return "unsupported";
    const key = f.name.toLowerCase();
    if (seen.has(key)) return "duplicate";
    seen.add(key);
  }
  if (total > UPLOAD_LIMITS.totalBytes) return "too_large";
  return null;
}

function toBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let bin = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) bin += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  return btoa(bin);
}

export async function uploadBody(files: File[]): Promise<{ upload: { files: { name: string; content_base64: string }[] }; policy_preset: string }> {
  const out: { name: string; content_base64: string }[] = [];
  for (const f of files) out.push({ name: f.name, content_base64: toBase64(await f.arrayBuffer()) });
  return { upload: { files: out }, policy_preset: "competition_default" };
}
