import type { ReactNode } from "react";

import s from "./common.module.css";
import { Icon } from "./Icon";

export function Notice({ tone = "info", title, children }: { tone?: "info" | "warn"; title: string; children: ReactNode }) {
  return (
    <div className={`${s.notice} ${tone === "warn" ? s.noticeWarn : ""}`} role="note">
      <Icon name={tone === "warn" ? "alert" : "info"} size={16} />
      <div className={s.noticeTitle}>{title}</div>
      <div className={s.noticeBody}>{children}</div>
    </div>
  );
}
