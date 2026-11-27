// A small, restrained icon set drawn for CLINVEIL: 20 px grid, 1.5 px strokes, current colour.
// Icons are decorative (aria-hidden) unless a label is given; meaning is always also carried by text.

import type { ReactElement } from "react";

const paths: Record<string, ReactElement> = {
  overview: (
    <>
      <path d="M3.5 4.5h13M3.5 10h8M3.5 15.5h13" />
      <path d="M14 8.2h2.5v3.6H14z" />
    </>
  ),
  process: (
    <>
      <path d="M10 3v8.5M6.8 8.3 10 11.5l3.2-3.2" />
      <path d="M3.5 12.5v3a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1v-3" />
    </>
  ),
  run: (
    <>
      <circle cx="4.5" cy="10" r="1.6" />
      <circle cx="10" cy="10" r="1.6" />
      <circle cx="15.5" cy="10" r="1.6" />
      <path d="M6.1 10h2.3M11.6 10h2.3" />
    </>
  ),
  results: (
    <>
      <rect x="3.5" y="3.5" width="13" height="13" rx="1.5" />
      <path d="M3.5 8h13M8 8v8.5" />
    </>
  ),
  shield: <path d="M10 3 4.5 5v4.6c0 3.3 2.3 6 5.5 7.4 3.2-1.4 5.5-4.1 5.5-7.4V5L10 3Z" />,
  preview: (
    <>
      <rect x="3" y="4" width="6" height="12" rx="1" />
      <rect x="11" y="4" width="6" height="12" rx="1" />
      <path d="M5 7.5h2M5 10h2M13 7.5h2M13 10h1" />
    </>
  ),
  architecture: (
    <>
      <rect x="3" y="3.5" width="5" height="4" rx="1" />
      <rect x="12" y="3.5" width="5" height="4" rx="1" />
      <rect x="7.5" y="12.5" width="5" height="4" rx="1" />
      <path d="M5.5 7.5v2.5h9V7.5M10 10v2.5" />
    </>
  ),
  info: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 9v4.5M10 6.4v.1" />
    </>
  ),
  check: <path d="m4.5 10.5 3.5 3.5 7.5-8" />,
  dash: <path d="M5 10h10" />,
  partial: (
    <>
      <circle cx="10" cy="10" r="6.5" />
      <path d="M10 3.5a6.5 6.5 0 0 1 0 13Z" fill="currentColor" stroke="none" />
    </>
  ),
  alert: (
    <>
      <path d="M10 3.5 2.8 16h14.4L10 3.5Z" />
      <path d="M10 8.5v3.5M10 14v.1" />
    </>
  ),
  cross: <path d="m5.5 5.5 9 9M14.5 5.5l-9 9" />,
  sun: (
    <>
      <circle cx="10" cy="10" r="3.2" />
      <path d="M10 2.5v1.8M10 15.7v1.8M2.5 10h1.8M15.7 10h1.8M4.7 4.7 6 6M14 14l1.3 1.3M4.7 15.3 6 14M14 6l1.3-1.3" />
    </>
  ),
  moon: <path d="M15.5 12.3A6.2 6.2 0 0 1 7.7 4.5a6.2 6.2 0 1 0 7.8 7.8Z" />,
  monitor: (
    <>
      <rect x="3" y="4" width="14" height="9.5" rx="1.2" />
      <path d="M7.5 16.5h5M10 13.5v3" />
    </>
  ),
  arrowRight: <path d="M4 10h12M11.5 5.5 16 10l-4.5 4.5" />,
  chevronDown: <path d="m5.5 8 4.5 4.5L14.5 8" />,
  lock: (
    <>
      <rect x="4.5" y="9" width="11" height="8" rx="1.3" />
      <path d="M7 9V6.5a3 3 0 0 1 6 0V9" />
    </>
  ),
  file: (
    <>
      <path d="M5.5 2.8h6l3.5 3.5v10.9H5.5Z" />
      <path d="M11.5 2.8v3.5H15" />
    </>
  ),
  copy: (
    <>
      <rect x="7" y="7" width="9.5" height="9.5" rx="1.3" />
      <path d="M13 7V4.8a1.3 1.3 0 0 0-1.3-1.3H4.8a1.3 1.3 0 0 0-1.3 1.3v6.9A1.3 1.3 0 0 0 4.8 13H7" />
    </>
  ),
  printer: (
    <>
      <path d="M6 7.5V3.5h8v4" />
      <rect x="3" y="7.5" width="14" height="6.5" rx="1.3" />
      <path d="M6 12h8v4.5H6z" />
    </>
  ),
  slash: <path d="M12.5 4 7.5 16" />,
  pause: <path d="M7.5 5v10M12.5 5v10" />,
  play: <path d="M6.5 4.5v11l9-5.5Z" />,
  replay: (
    <>
      <path d="M4.5 10a5.5 5.5 0 1 0 1.8-4.1" />
      <path d="M4 3.5v3.2h3.2" />
    </>
  ),
  book: (
    <>
      <path d="M3.5 4.5h4.5a2 2 0 0 1 2 2v9.5a1.5 1.5 0 0 0-1.5-1.5h-5Z" />
      <path d="M16.5 4.5H12a2 2 0 0 0-2 2v9.5a1.5 1.5 0 0 1 1.5-1.5h5Z" />
    </>
  ),
};

export type IconName = keyof typeof paths;

export function Icon({ name, size = 18, label }: { name: IconName; size?: number; label?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
      data-icon={name}
    >
      {paths[name]}
    </svg>
  );
}
