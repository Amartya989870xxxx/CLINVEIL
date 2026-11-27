import { cleanup, render, screen, within } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DataModeProvider } from "../src/app/providers/DataModeProvider";
import { ThemeProvider } from "../src/app/providers/ThemeProvider";
import * as F from "../src/fixtures/recordedPracticeRun";
import { Overview } from "../src/pages/Overview/Overview";

function renderOverview(mode: "demo" | "backend") {
  return render(
    <ThemeProvider>
      <DataModeProvider initial={mode}>
        <MemoryRouter>
          <Overview />
        </MemoryRouter>
      </DataModeProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener() {}, removeEventListener() {} });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("fixtures are labelled", () => {
  it("every exported fixture is example_fixture with full provenance", () => {
    for (const [name, v] of Object.entries(F)) {
      if (typeof v !== "object" || v === null || !("contract" in v)) continue;
      const f = v as { source: string; provenance?: { engine_commit: string; recorded_on: string } };
      expect(f.source, name).toBe("example_fixture");
      expect(f.provenance?.engine_commit, name).toMatch(/^[0-9a-f]{40}$/);
      expect(f.provenance?.recorded_on, name).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });
  it("unimplemented capabilities are never reported as implemented", () => {
    expect(F.exampleHealth.capabilities.linking).toBe("not_available");
    expect(F.exampleJob.stages.find((s) => s.id === "linking")?.state).toBe("not_available");
    expect(F.exampleSummary.counts.records_linked).toBe(0);
  });
});

describe("Overview", () => {
  it("demo mode shows recorded values with an Example data badge", async () => {
    renderOverview("demo");
    const run = await screen.findByRole("region", { name: "Latest processing run" });
    expect(within(run).getByText("Example data")).toBeTruthy();
    expect(await within(run).findByText("822 processed")).toBeTruthy();
    expect(screen.getAllByText("Not measured yet").length).toBeGreaterThanOrEqual(2);
  });

  it("backend mode never shows fixture numbers when the backend is unreachable", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("network"));
    renderOverview("backend");
    // the latest run is asked for, and an unreachable backend is reported as such (never replaced by fixtures)
    expect((await screen.findAllByText("The local CLINVEIL backend is not reachable.")).length).toBeGreaterThan(0);
    expect(screen.queryByText("822 processed")).toBeNull();
    expect(screen.queryByText("Example data")).toBeNull();
    expect((await screen.findAllByText("The local CLINVEIL backend is not reachable.")).length).toBeGreaterThan(0);
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = renderOverview("demo");
    await screen.findByText("822 processed");
    const res = await axe.run(container, { rules: { "color-contrast": { enabled: false } } }); // jsdom cannot compute colour; see contrast.test.ts
    expect(res.violations.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
  });
});
