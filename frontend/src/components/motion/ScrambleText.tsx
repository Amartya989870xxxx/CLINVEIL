import { useEffect, useRef, useState } from "react";

import { canAnimate, scramble } from "./motion";

/** Short label that "decrypts" itself on hover or focus of its parent row. */
export function ScrambleText({ text, trigger }: { text: string; trigger: number }) {
  const [shown, setShown] = useState(text);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (!canAnimate()) return;
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / 420);
      setShown(scramble(text, text, p < 1 ? Math.max(0.01, p) : 1, trigger));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [trigger, text]);
  return <>{shown}</>;
}
