import { useEffect, useState } from "react";

import s from "./common.module.css";
import { Icon } from "./Icon";

/** Copies a short technical value (a commit or hash). Hidden where the clipboard API is unavailable. */
export function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(t);
  }, [copied]);
  if (typeof navigator === "undefined" || !navigator.clipboard) return null;
  return (
    <button
      type="button"
      className={s.copy}
      onClick={() => navigator.clipboard.writeText(value).then(() => setCopied(true), () => undefined)}
      aria-label={copied ? `${label} copied` : `Copy ${label}`}
      title={copied ? "Copied" : `Copy ${label}`}
    >
      <Icon name={copied ? "check" : "copy"} size={14} />
      <span className="visually-hidden" aria-live="polite">
        {copied ? "Copied" : ""}
      </span>
    </button>
  );
}
