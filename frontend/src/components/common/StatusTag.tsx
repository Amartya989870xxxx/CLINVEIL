import type { CapabilityState, StageState } from "../../services/api/types";
import s from "./common.module.css";
import { Icon, type IconName } from "./Icon";

type Any = CapabilityState | StageState;

const MAP: Record<Any, { label: string; tone: "ok" | "warn" | "danger" | "neutral" | "active"; icon: IconName }> = {
  implemented: { label: "Implemented", tone: "ok", icon: "check" },
  partial: { label: "Partly implemented", tone: "warn", icon: "partial" },
  not_available: { label: "Not available yet", tone: "neutral", icon: "dash" },
  waiting: { label: "Waiting", tone: "neutral", icon: "dash" },
  in_progress: { label: "In progress", tone: "active", icon: "run" },
  complete: { label: "Completed", tone: "ok", icon: "check" },
  needs_attention: { label: "Needs attention", tone: "warn", icon: "alert" },
  failed: { label: "Failed", tone: "danger", icon: "cross" },
};

/** Status is always text + icon, never colour alone. */
export function StatusTag({ state, label }: { state: Any; label?: string }) {
  const m = MAP[state];
  return (
    <span className={`${s.tag} ${s[m.tone]}`}>
      <Icon name={m.icon} size={15} />
      {label ?? m.label}
    </span>
  );
}
