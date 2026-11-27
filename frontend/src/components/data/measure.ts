import type { Measurement } from "../../services/api/types";
import { fmtInt, fmtSeconds } from "../../utils/format";

/** Render a measured value exactly; never compute a score in the browser. */
export function formatMeasurement(m: Measurement): { text: string; measured: boolean } {
  if (m.value === null) return { text: "Not measured yet", measured: false };
  switch (m.unit) {
    case "bool":
      return { text: m.value ? "Passed" : "Failed", measured: true };
    case "seconds":
      return { text: fmtSeconds(m.value), measured: true };
    case "mb":
      return { text: `${m.value.toFixed(1)} MB`, measured: true };
    case "ratio":
      if (m.numerator !== undefined && m.denominator !== undefined) {
        const pct = m.denominator ? (100 * m.numerator) / m.denominator : 0;
        return { text: `${fmtInt(m.numerator)} of ${fmtInt(m.denominator)} (${pct.toFixed(pct % 1 ? 1 : 0)}%)`, measured: true };
      }
      return { text: `${(m.value * 100).toFixed(1)}%`, measured: true };
    case "count":
      if (m.numerator !== undefined && m.denominator !== undefined) {
        return { text: `${fmtInt(m.numerator)} of ${fmtInt(m.denominator)}`, measured: true };
      }
      return { text: fmtInt(m.value), measured: true };
  }
}
