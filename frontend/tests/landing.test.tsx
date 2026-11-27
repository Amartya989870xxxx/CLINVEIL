import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/app/App";
import { AFTER, BEFORE } from "../src/fixtures/exampleRecord";

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener() {}, removeEventListener() {} });
  window.history.pushState({}, "", "/");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("landing page at /", () => {
  it("is separate from the workspace: no sidebar, no data controls, no run data", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<App />);
    expect(screen.getByRole("heading", { level: 1, name: /Protecting patient identities/ })).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "Main" })).toBeNull();
    expect(screen.queryByText("Example data")).toBeNull();
    expect(screen.queryByText("Local backend")).toBeNull();
    expect(screen.queryByText(/Backend/)).toBeNull();
    const text = document.body.textContent ?? "";
    for (const v of ["822", "3,350", "4,855", "0.89", "Implemented", "Not available yet", "Latest processing run"]) {
      expect(text, v).not.toContain(v);
    }
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("leads into the workspace and the demo", () => {
    render(<App />);
    const hrefs = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(hrefs).toContain("/overview");
    expect(hrefs).toContain("/overview?path=judge");
  });

  it("its excerpt lines come verbatim from the recorded engine run", () => {
    render(<App />);
    const pres = Array.from(document.querySelectorAll("pre"), (p) => p.textContent ?? "");
    expect(pres).toHaveLength(2);
    for (const line of pres[0]!.split("\n")) expect(BEFORE.split("\n")).toContain(line);
    for (const line of pres[1]!.split("\n")) expect(AFTER.split("\n")).toContain(line);
    expect(pres[1]).toContain("Dr. Ramesh Iyengar");
    expect(pres[1]).not.toContain("Awasthi");
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = render(<App />);
    const res = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(res.violations.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
  });
});

describe("workspace", () => {
  it("lives at /overview inside the app shell", async () => {
    window.history.pushState({}, "", "/overview");
    render(<App />);
    expect(screen.getByRole("navigation", { name: "Main" })).toBeTruthy();
    expect(await screen.findByRole("heading", { level: 1, name: "Overview" })).toBeTruthy();
  });
});

describe("landing section navigation", () => {
  it("glides to the section, marks the link current and moves focus to the heading", () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    render(<App />);
    const link = screen.getByRole("link", { name: "An example" });
    fireEvent.click(link);
    expect(scroll).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    expect(link.getAttribute("aria-current")).toBe("location");
    expect(document.activeElement?.id).toBe("example-title");
    expect(window.location.hash).toBe("#example");
  });

  it("jumps instead of gliding when the user prefers reduced motion", () => {
    window.matchMedia = vi.fn().mockImplementation((q: string) => ({
      matches: q.includes("reduce"),
      addEventListener() {},
      removeEventListener() {},
    }));
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: "Limitations" }));
    expect(scroll).toHaveBeenCalledWith({ behavior: "auto", block: "start" });
  });
});

describe("professional details", () => {
  it("each workspace page sets its own tab title and breadcrumb", async () => {
    window.history.pushState({}, "", "/preview");
    render(<App />);
    await screen.findByRole("heading", { level: 1, name: "Data preview" });
    expect(document.title).toBe("Data Preview · CLINVEIL");
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(crumbs.textContent).toBe("WorkspaceEvidenceData Preview");
    expect(crumbs.querySelector('[aria-current="page"]')?.textContent).toBe("Data Preview");
  });

  it("copy buttons copy the full value, not the shortened one", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    window.history.pushState({}, "", "/overview");
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Copy engine commit" }));
    expect(writeText).toHaveBeenCalledWith("ac3750425d1ee8582f288d05624f3f06e1151fa1");
    expect(await screen.findByRole("button", { name: "engine commit copied" })).toBeTruthy();
  });

  it("results can be printed", async () => {
    const print = vi.spyOn(window, "print").mockImplementation(() => undefined);
    window.history.pushState({}, "", "/results");
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Print or save as PDF/ }));
    expect(print).toHaveBeenCalled();
  });

  it("loading placeholders still announce themselves", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise(() => undefined));
    localStorage.setItem("clinveil.mode", "backend");
    window.history.pushState({}, "", "/results");
    render(<App />);
    expect(screen.getAllByRole("status")[0]?.textContent).toContain("Loading");
    localStorage.removeItem("clinveil.mode");
  });
});

describe("redaction reel", () => {
  it("its finished state is the engine's real output, line for line", () => {
    window.history.pushState({}, "", "/");
    render(<App />);
    const reel = screen.getByRole("figure", { name: /Animation of CLINVEIL processing/ });
    const lines = Array.from(reel.querySelectorAll("[aria-hidden='true'] > div"), (d) => d.textContent ?? "");
    expect(lines.length).toBeGreaterThanOrEqual(8);
    const after = AFTER.split("\n");
    for (const l of lines) expect(after).toContain(l);
    const text = lines.join("\n");
    expect(text).toContain("Dr. Ramesh Iyengar");
    expect(text).not.toContain("Kalindi");
    expect(text).not.toContain("9876512034");
  });
});
