import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SEARCH_MS, debounce, historyHash, historyUrl, parseHistoryHash, setHistoryHash } from "./history";
import { parseRoute } from "./router";

describe("history filters in the hash", () => {
  it("round-trip through the hash, odd characters included", () => {
    const filters = { kind: "runner", project: "example-app", job: "e2e", result: "failed", q: "fix/50% & co" };
    const hash = historyHash(filters);
    expect(hash.startsWith("#/history?")).toBe(true);
    expect(parseHistoryHash(hash)).toEqual(filters);
    expect(parseRoute(hash)).toEqual({ page: "history" });
  });

  it("leave out empty and unknown names", () => {
    expect(historyHash({ project: "", q: "" })).toBe("#/history");
    expect(parseHistoryHash("#/history?project=&other=x&worker=build-1")).toEqual({ worker: "build-1" });
    expect(parseHistoryHash("#/history")).toEqual({});
  });

  it("keep the filters when paging", () => {
    const url = new URL(historyUrl({ project: "example-app", q: "main" }, 1700000000.5), "http://x");
    expect(url.pathname).toBe("/api/history");
    expect(Object.fromEntries(url.searchParams)).toEqual(
      { project: "example-app", q: "main", limit: "50", before: "1700000000.5" });
  });

  it("swap the hash in place and tell the router", () => {
    const heard = vi.fn();
    window.addEventListener("hashchange", heard);
    const steps = window.history.length;
    setHistoryHash({ result: "passed" });
    expect(window.location.hash).toBe("#/history?result=passed");
    expect(window.history.length).toBe(steps);
    expect(heard).toHaveBeenCalledTimes(1);
    setHistoryHash({ result: "passed" });  // no change, no event
    expect(heard).toHaveBeenCalledTimes(1);
    window.removeEventListener("hashchange", heard);
  });
});

describe("debounce", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("runs once typing has stopped, with the last text", () => {
    const run = vi.fn();
    const later = debounce(run, SEARCH_MS);
    later("m"); vi.advanceTimersByTime(SEARCH_MS - 1);
    later("ma"); vi.advanceTimersByTime(SEARCH_MS - 1);
    later("mai");
    expect(run).not.toHaveBeenCalled();
    vi.advanceTimersByTime(SEARCH_MS);
    expect(run).toHaveBeenCalledTimes(1);
    expect(run).toHaveBeenCalledWith("mai");
  });

  it("drops a waiting call on cancel", () => {
    const run = vi.fn();
    const later = debounce(run, SEARCH_MS);
    later("x");
    later.cancel();
    vi.advanceTimersByTime(SEARCH_MS * 2);
    expect(run).not.toHaveBeenCalled();
  });
});
