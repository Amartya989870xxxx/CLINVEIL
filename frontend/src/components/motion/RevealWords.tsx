import { Fragment } from "react";

import s from "./motion.module.css";

/** Words rise out of a mask one after another. Plain text for assistive technology; static under reduced motion. */
export function RevealWords({ text, start = 0, step = 55, className }: { text: string; start?: number; step?: number; className?: string }) {
  const words = text.split(" ");
  return (
    <span className={className}>
      {words.map((w, i) => (
        <Fragment key={i}>
          <span className={s.mask}>
            <span className={s.word} style={{ animationDelay: `${start + i * step}ms` }}>
              {w}
            </span>
          </span>
          {i < words.length - 1 ? " " : ""}
        </Fragment>
      ))}
    </span>
  );
}
