import { useEffect, useMemo, useRef, useState } from "react";

import { AFTER, BEFORE, NOT_YET_GENERALISED, PRESERVED, REMOVED_BEFORE, spansOf } from "../../fixtures/exampleRecord";
import { Icon } from "../common/Icon";
import { canAnimate, scramble } from "./motion";
import s from "./RedactionReel.module.css";

type Seg =
  | { kind: "text"; text: string }
  | { kind: "removed"; from: string; to: string; n: number }
  | { kind: "preserved"; text: string; n: number }
  | { kind: "generalised"; text: string };

interface Line {
  segs: Seg[];
}

// Lines of the recorded record that show something happening, picked by their label.
const PICK = ["Patient Name:", "UHID:", "W/o ", "Address:", "Mobile:", "DOB:", "Consultant:", "Diagnosis:", " 1. Tab", "Attendant:"];

/** Pairs each before-line with its real after-line: removed spans map, in order, onto the placeholders. */
function buildLines(): Line[] {
  const before = BEFORE.split("\n");
  const after = AFTER.split("\n");
  const lines: Line[] = [];
  let removedN = 0;
  let keptN = 0;
  for (const label of PICK) {
    const i = before.findIndex((l) => l.startsWith(label));
    const b = before[i];
    const a = after[i];
    if (i < 0 || b === undefined || a === undefined) continue;
    const spans = [
      ...spansOf(b, REMOVED_BEFORE, "removed"),
      ...spansOf(b, PRESERVED, "preserved"),
      ...spansOf(b, NOT_YET_GENERALISED, "generalised"),
    ].sort((x, y) => x.start - y.start);
    const tokens = a.match(/\[[A-Z]+\]/g) ?? [];
    if (spans.filter((x) => x.kind === "removed").length !== tokens.length) continue; // never invent a mapping
    const segs: Seg[] = [];
    let at = 0;
    let t = 0;
    for (const sp of spans) {
      if (sp.start < at) continue;
      if (sp.start > at) segs.push({ kind: "text", text: b.slice(at, sp.start) });
      const text = b.slice(sp.start, sp.end);
      if (sp.kind === "removed") segs.push({ kind: "removed", from: text, to: tokens[t++]!, n: removedN++ });
      else if (sp.kind === "preserved") segs.push({ kind: "preserved", text, n: keptN++ });
      else segs.push({ kind: "generalised", text });
      at = sp.end;
    }
    if (at < b.length) segs.push({ kind: "text", text: b.slice(at) });
    lines.push({ segs });
  }
  return lines;
}

// timeline (ms)
const LINE_GAP = 720;
const SWEEP = 520;
const FLAG_AT = 260;
const SCRAMBLE_AT = 460;
const SCRAMBLE_FOR = 620;
const HOLD = 3200;

/**
 * Signature animation: CLINVEIL working through a synthetic discharge summary. Text is the real recorded engine
 * output. Auto-plays only when motion is allowed and it is on screen; has a pause control (WCAG 2.2.2).
 */
export function RedactionReel() {
  const lines = useMemo(buildLines, []);
  const total = lines.length * LINE_GAP + SWEEP + SCRAMBLE_FOR;
  const animated = useRef(canAnimate()).current;
  const [t, setT] = useState(animated ? 0 : total);
  const [paused, setPaused] = useState(false);
  const [visible, setVisible] = useState(true);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!animated || !root.current) return;
    const io = new IntersectionObserver(([e]) => setVisible(Boolean(e?.isIntersecting)), { threshold: 0.15 });
    io.observe(root.current);
    return () => io.disconnect();
  }, [animated]);

  useEffect(() => {
    if (!animated || paused || !visible) return;
    let raf = 0;
    let last = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(64, now - last);
      last = now;
      setT((x) => (x + dt > total + HOLD ? 0 : x + dt));
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [animated, paused, visible, total]);

  const removedTotal = lines.reduce((n, l) => n + l.segs.filter((x) => x.kind === "removed").length, 0);
  const keptTotal = lines.reduce((n, l) => n + l.segs.filter((x) => x.kind === "preserved").length, 0);
  const genTotal = lines.reduce((n, l) => n + l.segs.filter((x) => x.kind === "generalised").length, 0);
  let removedDone = 0;
  let keptDone = 0;
  let activeLine = -1;
  const fading = t > total + HOLD - 500;

  const rendered = lines.map((line, i) => {
    const lt = t - i * LINE_GAP;
    if (lt >= 0 && lt < SWEEP + SCRAMBLE_FOR) activeLine = i;
    const sweep = Math.min(1, Math.max(0, lt / SWEEP));
    return (
      <div
        key={i}
        className={s.line}
        data-active={lt >= 0 && lt < SWEEP + SCRAMBLE_FOR ? "" : undefined}
        style={{ ["--sweep" as string]: sweep }}
      >
        {line.segs.map((seg, j) => {
          if (seg.kind === "text") return <span key={j}>{seg.text}</span>;
          if (seg.kind === "generalised")
            return (
              <span key={j} className={s.gen} data-on={lt > FLAG_AT ? "" : undefined}>
                {seg.text}
              </span>
            );
          if (seg.kind === "preserved") {
            const on = lt > SCRAMBLE_AT;
            if (on) keptDone++;
            return (
              <span key={j} className={s.kept} data-on={on ? "" : undefined}>
                {seg.text}
              </span>
            );
          }
          const p = (lt - SCRAMBLE_AT - j * 40) / SCRAMBLE_FOR;
          if (p >= 1) removedDone++;
          const state = p >= 1 ? "done" : p > 0 ? "scramble" : lt > FLAG_AT ? "flag" : "idle";
          return (
            <span key={j} className={s.removed} data-state={state}>
              {scramble(seg.from, seg.to, p, seg.n * 13)}
            </span>
          );
        })}
      </div>
    );
  });

  const status =
    t >= total ? "Release ready" : activeLine >= 0 ? `Scanning line ${activeLine + 1} of ${lines.length}` : "Reading export";

  return (
    <figure className={s.reel} ref={root} aria-labelledby="reel-caption">
      <div className={s.head}>
        <span className={s.doc}>
          <Icon name="file" size={14} /> discharge_summary.txt
        </span>
        <span className={s.status} data-done={t >= total ? "" : undefined} aria-hidden="true">
          <span className={s.pulse} /> {status}
        </span>
      </div>
      <div className={s.body} aria-hidden="true" data-fading={fading ? "" : undefined}>
        {rendered}
      </div>
      <div className={s.foot}>
        <span className={s.count} aria-hidden="true">
          <b>{removedDone}</b>/{removedTotal} personal details replaced
        </span>
        <span className={s.count} aria-hidden="true">
          <b data-kept="">{keptDone}</b>/{keptTotal} clinical items kept
        </span>
        <span className={`${s.count} ${s.countGen}`} aria-hidden="true">
          <i /> {genTotal} indirect identifiers kept exactly (not generalised yet)
        </span>
        {animated && (
          <button type="button" className={s.pause} onClick={() => setPaused((x) => !x)} aria-pressed={paused}>
            <Icon name={paused ? "play" : "pause"} size={14} />
            {paused ? "Play" : "Pause"}
            <span className="visually-hidden"> the redaction animation</span>
          </button>
        )}
      </div>
      <figcaption id="reel-caption" className="visually-hidden">
        Animation of CLINVEIL processing an invented synthetic discharge summary: the patient's name, hospital numbers,
        relative's name, address, phone number and date of birth are replaced with placeholders such as [NAME] and
        [PHONE], while the doctor's name, diagnosis and medicines are kept. The age, tehsil and district are kept
        exactly because generalisation is not built yet. The text is the real engine output.
      </figcaption>
    </figure>
  );
}
