import { useEffect } from "react";

/** Sets the browser tab title, e.g. "Results · CLINVEIL". */
export function useDocumentTitle(title: string | null) {
  useEffect(() => {
    document.title = title ? `${title} · CLINVEIL` : "CLINVEIL";
  }, [title]);
}
