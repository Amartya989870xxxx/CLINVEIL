import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DataModeProvider } from "../src/app/providers/DataModeProvider";
import { ThemeProvider } from "../src/app/providers/ThemeProvider";
import { AFTER, BEFORE, exampleRecord, NOT_YET_GENERALISED, PRESERVED, REMOVED_AFTER, REMOVED_BEFORE } from "../src/fixtures/exampleRecord";
import { About } from "../src/pages/About/About";
import { Architecture } from "../src/pages/Architecture/Architecture";
import { DataPreview } from "../src/pages/DataPreview/DataPreview";
import { PrivacyQuality } from "../src/pages/PrivacyQuality/PrivacyQuality";
import { ProcessDataset } from "../src/pages/ProcessDataset/ProcessDataset";
import { ProcessingRun } from "../src/pages/ProcessingRun/ProcessingRun";
import { Results } from "../src/pages/Results/Results";
import { sniff } from "../src/utils/inspect";

const PAGES: [string, string, () => ReactElement][] = [
  ["/process", "Process a dataset", () => <ProcessDataset />],
  ["/run", "Processing run", () => <ProcessingRun />],
  ["/results", "Results", () => <Results />],
  ["/privacy", "Privacy and quality", () => <PrivacyQuality />],
  ["/preview", "Data preview", () => <DataPreview />],
  ["/architecture", "Architecture", () => <Architecture />],
  ["/about", "About and limitations", () => <About />],
];

function renderAt(path: string, el: ReactElement, mode: "demo" | "backend" = "demo") {
  return render(
    <ThemeProvider>
      <DataModeProvider initial={mode}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path={path.split("?")[0]} element={el} />
            <Route path="/run" element={<h1>Run page</h1>} />
          </Routes>
        </MemoryRouter>
      </DataModeProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener() {}, removeEventListener() {} });
  sessionStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe.each(PAGES)("%s", (path, title, el) => {
  it("renders its heading and passes automated accessibility checks in example mode", async () => {
    const { container } = renderAt(path, el());
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeTruthy();
    await new Promise((r) => setTimeout(r, 0));
    const res = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  });

  it("never shows recorded example values when the backend is unreachable", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("network"));
    renderAt(path, el(), "backend");
    await new Promise((r) => setTimeout(r, 20));
    const text = document.body.textContent ?? "";
    for (const leaked of ["822", "3,350", "Kalindi", "4,855", "0.89 s", "Secret Wards practice dataset"]) {
      expect(text, leaked).not.toContain(leaked);
    }
  });
});

describe("Process Dataset wizard", () => {
  it("requires a choice, then walks to the recorded run in example mode", async () => {
    renderAt("/process", <ProcessDataset />);
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
    expect(screen.getByRole("alert").textContent).toContain("Choose a dataset");
    fireEvent.click(await screen.findByRole("radio", { name: /Secret Wards practice dataset/ }));
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
    expect(screen.getByRole("heading", { name: "Review the processing policy" })).toBeTruthy();
    expect(screen.getAllByText(/not available yet/).length).toBeGreaterThanOrEqual(3);
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
    expect(screen.getByText("Example mode: nothing will be processed")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Open the recorded run/ }));
    expect(await screen.findByRole("heading", { name: "Run page" })).toBeTruthy();
  });

  it("will not accept uploads without the synthetic-data confirmation", async () => {
    renderAt("/process", <ProcessDataset />);
    fireEvent.click(screen.getByRole("radio", { name: /Your own synthetic files/ }));
    expect((screen.getByLabelText("Synthetic files") as HTMLInputElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
    expect(screen.getByRole("alert").textContent).toContain("Confirm that the files are synthetic");
  });
});

describe("Processing Run", () => {
  it("shows linking as not available and never as complete", async () => {
    renderAt("/run", <ProcessingRun />);
    const row = (await screen.findByText("Connecting records of the same patient")).closest("li")!;
    expect(row.textContent).toContain("Not available yet");
    expect(row.textContent).not.toContain("Completed");
  });
});

describe("Data Preview fixture is the engine's real output", () => {
  it("every removed value is absent from the output and every kept value is present in both", () => {
    for (const v of REMOVED_BEFORE) {
      expect(BEFORE, v).toContain(v);
      expect(AFTER, v).not.toContain(v);
    }
    for (const v of [...PRESERVED, ...NOT_YET_GENERALISED]) {
      expect(BEFORE, v).toContain(v);
      expect(AFTER, v).toContain(v);
    }
    for (const v of REMOVED_AFTER) expect(AFTER, v).toContain(v);
  });
  it("spans point at the intended text", () => {
    const ex = exampleRecord.examples[0]!;
    for (const sp of ex.spans_before) expect(sp.end).toBeLessThanOrEqual(ex.before.length);
    expect(ex.spans_before.filter((s) => s.kind === "removed").length).toBeGreaterThanOrEqual(REMOVED_BEFORE.length);
  });
  it("highlights carry a text label, not only colour", async () => {
    renderAt("/preview", <DataPreview />);
    expect((await screen.findAllByText("(removed)")).length).toBeGreaterThan(5);
    expect(screen.getAllByText("(kept)").length).toBeGreaterThan(5);
  });
});

describe("file sniffing", () => {
  const b = (s: string) => new TextEncoder().encode(s);
  it.each([
    [new Uint8Array([]), "empty"],
    [new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d]), "pdf"],
    [new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d]), "image"],
    [new Uint8Array([0x50, 0x4b, 0x03, 0x04]), "archive"],
    [new Uint8Array([0x41, 0x00, 0x42, 0x43]), "binary"],
    [b('<?xml version="1.0"?><a/>'), "xml"],
    [b('{"resourceType": "Bundle", "entry": []}'), "fhir"],
    [b('[{"a": 1}]'), "json"],
    [b("uhid\tname\tage\n1\t2\t3"), "tsv"],
    [b("uhid,name,age\n1,2,3"), "csv"],
    [b("DISCHARGE SUMMARY\nPatient: x"), "text"],
  ] as const)("%#: detects %s", (bytes, want) => {
    expect(sniff(bytes)).toBe(want);
  });
});

describe("leak test positive control", () => {
  it("the same values do appear in example mode, so the backend-mode check is meaningful", async () => {
    renderAt("/results", <Results />);
    await screen.findByText("822");
    const text = document.body.textContent ?? "";
    for (const v of ["822", "3,350", "4,855", "0.89 s"]) expect(text, v).toContain(v);
    cleanup();
    renderAt("/preview", <DataPreview />);
    expect((await screen.findAllByText(/Kalindi/)).length).toBeGreaterThan(0);
  });
});

describe("Architecture", () => {
  it("stage details start collapsed and open on demand", () => {
    renderAt("/architecture", <Architecture />);
    const btn = screen.getByRole("button", { name: /Linking/ });
    const body = document.getElementById(btn.getAttribute("aria-controls")!)!;
    // closed: collapsed and inert (out of the tab order and hidden from assistive technology)
    expect(body.hasAttribute("inert")).toBe(true);
    expect(body.hasAttribute("data-open")).toBe(false);
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    expect(body.hasAttribute("inert")).toBe(false);
    expect(body.hasAttribute("data-open")).toBe(true);
  });
});
