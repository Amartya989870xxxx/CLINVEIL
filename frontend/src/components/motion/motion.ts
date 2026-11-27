// Shared helpers for the decorative motion layer. Every animated element degrades to its final, static state when
// the user prefers reduced motion or the browser lacks IntersectionObserver (tests, old browsers).

const GLYPHS = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#/[]*";

export function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function canAnimate(): boolean {
  return typeof IntersectionObserver !== "undefined" && !prefersReducedMotion();
}

/** Deterministic pseudo-random glyph so a frame never flickers between renders of the same time. */
function glyph(seed: number): string {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return GLYPHS[Math.floor((x - Math.floor(x)) * GLYPHS.length)] ?? "#";
}

/**
 * Text morphing from `from` to `to` as p goes 0 -> 1: characters resolve left to right, the rest scramble.
 * Length interpolates between the two strings.
 */
export function scramble(from: string, to: string, p: number, salt = 0): string {
  if (p <= 0) return from;
  if (p >= 1) return to;
  const len = Math.round(from.length + (to.length - from.length) * p);
  const settled = Math.floor(to.length * p * p);
  let out = "";
  const tick = Math.floor(p * 24);
  for (let i = 0; i < len; i++) {
    const c = i < settled ? to[i] : undefined;
    out += c ?? glyph(i * 31 + tick * 7 + salt);
  }
  return out;
}

/** easeOutCubic */
export const ease = (x: number) => 1 - Math.pow(1 - Math.min(1, Math.max(0, x)), 3);
