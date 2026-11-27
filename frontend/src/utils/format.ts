const nf = new Intl.NumberFormat("en-IN");

export const fmtInt = (n: number): string => nf.format(n);

export function fmtBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KiB`;
  return `${(b / 1024 / 1024).toFixed(1)} MiB`;
}

export function fmtSeconds(s: number): string {
  return s < 10 ? `${s.toFixed(2)} s` : `${s.toFixed(1)} s`;
}

export function fmtDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export const shortSha = (sha: string): string => sha.slice(0, 12);

/** "27 Nov 2026, 04:35" in the viewer's local time, from an ISO timestamp. */
export function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
