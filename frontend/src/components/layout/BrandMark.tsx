/** Three ruled lines, one veiled segment: a record with a protected field. Drawn, not stock. */
export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="7" fill="var(--ink)" />
      <path d="M9 10.5h14M9 16h9M9 21.5h14" stroke="var(--bg)" strokeWidth="2.2" strokeLinecap="round" />
      <rect x="19.5" y="14.2" width="4" height="3.6" rx="1" fill="var(--accent)" />
    </svg>
  );
}
