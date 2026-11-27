import { useEffect, useRef, useState } from "react";

import { canAnimate, ease } from "./motion";

const nf = new Intl.NumberFormat("en-IN");

/**
 * Counts the first number in `value` up from zero when it scrolls into view, keeping the rest of the text and the
 * number's formatting ("1,022", "0.89 s", "4,855 of 4,855 (100%)" animates 4,855 only). Screen readers get the final
 * text immediately; the animated copy is hidden from them.
 */
export function CountUp({ value, duration = 1100 }: { value: string; duration?: number }) {
  const m = /^(\D*?)(\d[\d,]*(?:\.\d+)?)(.*)$/s.exec(value);
  const ref = useRef<HTMLSpanElement>(null);
  const animate = useRef(Boolean(m) && canAnimate()).current;
  const [p, setP] = useState(animate ? 0 : 1);

  useEffect(() => {
    const el = ref.current;
    if (!animate || !el) return;
    let raf = 0;
    const io = new IntersectionObserver(
      ([e]) => {
        if (!e?.isIntersecting) return;
        io.disconnect();
        const t0 = performance.now();
        const tick = (now: number) => {
          const x = Math.min(1, (now - t0) / duration);
          setP(ease(x));
          if (x < 1) raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [animate, duration]);

  if (!m || !animate) return <>{value}</>;
  const [, pre, num, post] = m as unknown as [string, string, string, string];
  const decimals = num.includes(".") ? num.split(".")[1]!.length : 0;
  const target = Number(num.replace(/,/g, ""));
  const cur = target * p;
  const shown = decimals ? cur.toFixed(decimals) : nf.format(Math.round(cur));
  return (
    <span ref={ref}>
      <span className="visually-hidden">{value}</span>
      <span aria-hidden="true">
        {pre}
        {p >= 1 ? num : shown}
        {post}
      </span>
    </span>
  );
}
