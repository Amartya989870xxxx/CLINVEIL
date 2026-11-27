import { act, cleanup, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/app/App";
import { useResource } from "../src/hooks/useResource";

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener() {}, removeEventListener() {} });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("mobile menu", () => {
  it("closes on Escape and returns focus to the menu button", () => {
    window.history.pushState({}, "", "/overview");
    render(<App />);
    const btn = screen.getByRole("button", { name: "Open menu" });
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(btn);
  });

  it("closes when tapping outside it", () => {
    window.history.pushState({}, "", "/overview");
    render(<App />);
    const btn = screen.getByRole("button", { name: "Open menu" });
    fireEvent.click(btn);
    fireEvent.pointerDown(screen.getByRole("main"));
    expect(btn.getAttribute("aria-expanded")).toBe("false");
  });
});

describe("navigation", () => {
  it("every page change starts at the top, including between the landing page and the workspace", async () => {
    const scrollTo = vi.fn();
    window.scrollTo = scrollTo as unknown as typeof window.scrollTo;
    window.history.pushState({}, "", "/about");
    render(<App />);
    fireEvent.click(screen.getAllByRole("link", { name: "CLINVEIL home" })[0]!);
    expect(await screen.findByRole("heading", { level: 1, name: /Protecting patient identities/ })).toBeTruthy();
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "instant" });
  });
});

describe("useResource", () => {
  it("a refresh keeps showing the current data instead of flashing back to loading", async () => {
    let n = 0;
    const load = () => Promise.resolve(++n);
    const { result, rerender } = renderHook(({ refresh }) => useResource(load, ["job-1"], refresh), { initialProps: { refresh: 0 } });
    await act(async () => {});
    expect(result.current).toEqual({ status: "ready", data: 1 });
    rerender({ refresh: 1 });
    expect(result.current.status).toBe("ready"); // no loading flash while the poll is in flight
    await act(async () => {});
    expect(result.current).toEqual({ status: "ready", data: 2 });
  });

  it("a different resource starts from loading", async () => {
    const { result, rerender } = renderHook(({ id }) => useResource(() => Promise.resolve(id), [id]), { initialProps: { id: "a" } });
    await act(async () => {});
    expect(result.current).toEqual({ status: "ready", data: "a" });
    rerender({ id: "b" });
    expect(result.current.status).toBe("loading");
    await act(async () => {});
    expect(result.current).toEqual({ status: "ready", data: "b" });
  });
});

describe("CLINVEIL logo", () => {
  it("on the landing page itself, returns to the top and focuses the headline", () => {
    const scrollTo = vi.fn();
    window.scrollTo = scrollTo as unknown as typeof window.scrollTo;
    Element.prototype.scrollIntoView = vi.fn(); // jsdom lacks it; the page scrolls to #example on load
    window.history.pushState({}, "", "/#example");
    render(<App />);
    scrollTo.mockClear();
    fireEvent.click(screen.getAllByRole("link", { name: "CLINVEIL home" })[0]!);
    expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" });
    expect(window.location.hash).toBe("");
    expect(document.activeElement?.id).toBe("landing-title");
  });

  it("from a workspace page, opens the landing page", async () => {
    window.history.pushState({}, "", "/results");
    render(<App />);
    fireEvent.click(screen.getAllByRole("link", { name: "CLINVEIL home" })[0]!);
    expect(await screen.findByRole("heading", { level: 1, name: /Protecting patient identities/ })).toBeTruthy();
    expect(window.location.pathname).toBe("/");
  });
});
