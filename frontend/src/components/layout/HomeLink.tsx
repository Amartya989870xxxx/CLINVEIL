import type { MouseEvent, ReactNode } from "react";
import { Link, useLocation } from "react-router";

import { prefersReducedMotion } from "../motion/motion";

/**
 * The CLINVEIL logo link. Always leads to the first page: from anywhere else it navigates to "/", and on the
 * landing page itself (where navigating to "/" would change nothing) it returns to the top and focuses the headline.
 */
export function HomeLink({ className, children }: { className?: string; children: ReactNode }) {
  const { pathname } = useLocation();
  function onClick(e: MouseEvent<HTMLAnchorElement>) {
    if (pathname !== "/" || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? "auto" : "smooth" });
    if (window.location.hash) history.replaceState(null, "", "/");
    document.getElementById("landing-title")?.focus({ preventScroll: true });
  }
  return (
    <Link to="/" className={className} aria-label="CLINVEIL home" onClick={onClick}>
      {children}
    </Link>
  );
}
