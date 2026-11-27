import type { ReactNode } from "react";

import { RevealWords } from "../motion/RevealWords";
import s from "./layout.module.css";

export function PageHeader({
  eyebrow,
  title,
  lead,
  actions,
  badge,
}: {
  eyebrow?: string;
  title: string;
  lead?: ReactNode;
  actions?: ReactNode;
  badge?: ReactNode;
}) {
  return (
    <header className={s.pageHeader}>
      {(eyebrow || badge) && (
        <div style={{ display: "flex", alignItems: "center", gap: "var(--s-3)" }}>
          {eyebrow && <span className="eyebrow">{eyebrow}</span>}
          {badge}
        </div>
      )}
      <h1 className={s.pageTitle} tabIndex={-1}>
        <RevealWords text={title} step={45} />
      </h1>
      {lead && <p className={s.pageLead}>{lead}</p>}
      {actions && <div className={s.pageActions}>{actions}</div>}
    </header>
  );
}
