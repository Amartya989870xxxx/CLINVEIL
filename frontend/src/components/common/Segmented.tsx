import { useId, useLayoutEffect, useRef, useState } from "react";

import s from "./common.module.css";
import { Icon, type IconName } from "./Icon";

export interface SegOption<T extends string> {
  value: T;
  label: string;
  icon?: IconName;
  hideLabel?: boolean;
}

/**
 * A native radio group styled as a segmented control (keyboard: arrows, like any radio group).
 * A thumb slides to the selected option; with reduced motion it moves instantly.
 */
export function Segmented<T extends string>({
  legend,
  options,
  value,
  onChange,
}: {
  legend: string;
  options: SegOption<T>[];
  value: T;
  onChange: (v: T) => void;
}) {
  const name = useId();
  const root = useRef<HTMLFieldSetElement>(null);
  const [thumb, setThumb] = useState<{ x: number; w: number } | null>(null);

  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    const measure = () => {
      // measure the <label> wrapper: it is positioned, so its offsetLeft is relative to this fieldset
      const label = el.querySelector<HTMLInputElement>("input:checked")?.parentElement;
      if (!label || !label.offsetWidth) return setThumb(null);
      setThumb({ x: label.offsetLeft, w: label.offsetWidth });
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [value, options.length]);

  return (
    <fieldset ref={root} className={s.segmented} data-ready={thumb ? "" : undefined}>
      <legend className="visually-hidden">{legend}</legend>
      {thumb && (
        <span
          className={s.segThumb}
          aria-hidden="true"
          style={{ width: thumb.w, transform: `translateX(${thumb.x}px)` }}
        />
      )}
      {options.map((o) => (
        <label key={o.value} className={s.segItem} title={o.hideLabel ? o.label : undefined}>
          <input type="radio" name={name} value={o.value} checked={value === o.value} onChange={() => onChange(o.value)} />
          <span className={s.segLabel}>
            {o.icon && <Icon name={o.icon} size={15} />}
            {o.hideLabel ? <span className="visually-hidden">{o.label}</span> : o.label}
          </span>
        </label>
      ))}
    </fieldset>
  );
}
