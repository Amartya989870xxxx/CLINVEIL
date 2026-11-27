import type { FixtureProvenance, Source } from "../../services/api/types";
import { fmtDate } from "../../utils/format";
import s from "./common.module.css";

/** Every surface that renders data says where the data came from. */
export function SourceBadge({ source, provenance }: { source: Source; provenance?: FixtureProvenance }) {
  if (source === "live_backend") {
    return (
      <span className={`${s.source} ${s.sourceLive}`}>
        <span className={s.sourceDot} aria-hidden="true" />
        Live backend
      </span>
    );
  }
  const title = provenance
    ? `${provenance.recorded_from}, recorded ${fmtDate(provenance.recorded_on)} (engine ${provenance.engine_commit.slice(0, 7)}). Not live.`
    : "Example data, not produced by a live backend.";
  return (
    <span className={`${s.source} ${s.sourceExample}`} title={title}>
      <span className={s.sourceDot} aria-hidden="true" />
      Example data
      <span className="visually-hidden">. {title}</span>
    </span>
  );
}
