// In-browser inspection of user-selected SYNTHETIC files. Nothing is uploaded or stored: files are read locally to
// report count, size, detected format and problems the engine would set aside. File NAMES are never displayed
// (a name can itself contain personal details); files are identified by a SHA-256 prefix.

export type DetectedFormat = "csv" | "tsv" | "json" | "fhir" | "text" | "xml" | "pdf" | "image" | "archive" | "binary" | "empty";

export interface InspectedFile {
  index: number;
  sha12: string;
  bytes: number;
  format: DetectedFormat;
  problem: string | null; // plain-language reason it would be set aside, or null
}

export interface Inspection {
  files: InspectedFile[];
  bytes: number;
  formats: Partial<Record<DetectedFormat, number>>;
  setAside: number;
  truncated: boolean; // more files were selected than the inspection limit
}

export const LIMITS = { files: 500, totalBytes: 200 * 1024 * 1024, parseJsonBytes: 5 * 1024 * 1024 };
const SUPPORTED: DetectedFormat[] = ["csv", "tsv", "json", "fhir", "text"];

async function sha12(buf: ArrayBuffer): Promise<string> {
  if (!globalThis.crypto?.subtle) return "unavailable";
  const d = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(d).slice(0, 6), (b) => b.toString(16).padStart(2, "0")).join("");
}

function startsWith(b: Uint8Array, sig: number[]): boolean {
  return sig.every((v, i) => b[i] === v);
}

export function sniff(head: Uint8Array): DetectedFormat {
  if (head.length === 0) return "empty";
  if (startsWith(head, [0x25, 0x50, 0x44, 0x46])) return "pdf";
  if (startsWith(head, [0xff, 0xd8, 0xff]) || startsWith(head, [0x89, 0x50, 0x4e, 0x47]) || startsWith(head, [0x47, 0x49, 0x46])) return "image";
  if (startsWith(head, [0x50, 0x4b, 0x03, 0x04]) || startsWith(head, [0x1f, 0x8b]) || startsWith(head, [0x37, 0x7a, 0xbc, 0xaf])) return "archive";
  const utf16 = startsWith(head, [0xff, 0xfe]) || startsWith(head, [0xfe, 0xff]);
  if (!utf16 && head.slice(0, 4096).includes(0)) return "binary";
  const text = new TextDecoder(utf16 ? (head[0] === 0xff ? "utf-16le" : "utf-16be") : "utf-8", { fatal: false })
    .decode(head)
    .replace(/^﻿/, "")
    .trimStart();
  if (text.startsWith("<")) return "xml";
  if (text.startsWith("{") || text.startsWith("[")) return /"resourceType"\s*:\s*"Bundle"/.test(text) ? "fhir" : "json";
  const first = text.split(/\r?\n/, 1)[0] ?? "";
  if ((first.match(/\t/g) ?? []).length >= 2) return "tsv";
  if ((first.match(/[,;|]/g) ?? []).length >= 2) return "csv";
  return "text";
}

const PROBLEM: Partial<Record<DetectedFormat, string>> = {
  empty: "Empty file",
  pdf: "PDF: not supported, will be set aside",
  image: "Image: not supported, will be set aside",
  archive: "Archive: not opened, will be set aside",
  binary: "Binary content: will be set aside",
  xml: "XML: not supported in this release, will be set aside",
};

export async function inspectFiles(list: File[]): Promise<Inspection> {
  const files = list.slice(0, LIMITS.files);
  const out: InspectedFile[] = [];
  let bytes = 0;
  for (const [i, f] of files.entries()) {
    if (bytes + f.size > LIMITS.totalBytes) break;
    bytes += f.size;
    const buf = await f.arrayBuffer();
    const head = new Uint8Array(buf.slice(0, 8192));
    let format = sniff(head);
    let problem = PROBLEM[format] ?? null;
    if ((format === "json" || format === "fhir") && f.size <= LIMITS.parseJsonBytes) {
      try {
        JSON.parse(new TextDecoder("utf-8").decode(buf).replace(/^﻿/, ""));
      } catch {
        problem = "Broken or truncated JSON: will be set aside";
      }
    }
    if (format === "text" && f.size > 0) {
      const sample = new TextDecoder("utf-8", { fatal: false }).decode(head);
      if ((sample.match(/�/g) ?? []).length > 8) {
        format = "binary";
        problem = "Unreadable text encoding: will be set aside";
      }
    }
    out.push({ index: i + 1, sha12: await sha12(buf), bytes: f.size, format, problem });
  }
  const formats: Partial<Record<DetectedFormat, number>> = {};
  for (const f of out) formats[f.format] = (formats[f.format] ?? 0) + 1;
  return {
    files: out,
    bytes,
    formats,
    setAside: out.filter((f) => f.problem || !SUPPORTED.includes(f.format)).length,
    truncated: list.length > out.length,
  };
}
