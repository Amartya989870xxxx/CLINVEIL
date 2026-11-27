// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Parses the two theme blocks of tokens.css and asserts WCAG 2.2 AA contrast for every text/surface pair
// the interface actually uses. Brand colours used only as non-text accents must reach 3:1 (1.4.11).
const css = readFileSync(new URL("../src/styles/tokens.css", import.meta.url), "utf8");

function block(selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)) out[m[1] as string] = m[2] as string;
  return out;
}

function lum(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = c.map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4)) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const ratio = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p) as [number, number];
  return (x + 0.05) / (y + 0.05);
};

const themes = { light: block(':root[data-theme="light"]'), dark: block(':root[data-theme="dark"]') };
const TEXT = ["ink", "ink-2", "accent-ink", "ok", "warn", "danger"];
const SURFACES = ["bg", "surface", "surface-2", "surface-sunken"];

describe.each(Object.entries(themes))("%s theme contrast", (_name, t) => {
  it.each(TEXT)("text token --%s reaches 4.5:1 on every surface", (fg) => {
    for (const bg of SURFACES) expect(ratio(t[fg]!, t[bg]!), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
  });
  it("tertiary text --ink-3 reaches 4.5:1 on the backgrounds it is used on", () => {
    for (const bg of ["bg", "surface", "surface-sunken"]) expect(ratio(t["ink-3"]!, t[bg]!), `ink-3 on ${bg}`).toBeGreaterThanOrEqual(4.5);
  });
  it("the focus/selection accent reaches 3:1 on the page background", () => {
    expect(ratio(t["accent"]!, t["bg"]!)).toBeGreaterThanOrEqual(3);
  });
  it("form-control borders reach 3:1 against surfaces", () => {
    expect(ratio(t["rule-strong"]!, t["surface"]!)).toBeGreaterThanOrEqual(3);
  });
  it("filled primary buttons keep 4.5:1 text", () => {
    const btnText = _name === "dark" ? "#111110" : t["ink-inverse"]!;
    expect(ratio(btnText, t["accent-ink"]!)).toBeGreaterThanOrEqual(4.5);
  });
  it("source-badge and legend text is readable on its wash", () => {
    expect(ratio(t["warn"]!, t["warn-wash"]!)).toBeGreaterThanOrEqual(4.5);
    expect(ratio(t["ok"]!, t["ok-wash"]!)).toBeGreaterThanOrEqual(4.5);
  });
});
