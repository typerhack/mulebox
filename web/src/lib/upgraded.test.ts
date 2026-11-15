import { afterEach, describe, expect, it, vi } from "vitest";

import { busy, isNewer, reloadWhenFree } from "./upgraded";

afterEach(() => { vi.useRealTimers(); document.body.innerHTML = ""; });

describe("a page left open across an upgrade", () => {
  it("counts only a different version, once both are known", () => {
    expect(isNewer("1.29.0", "1.30.0")).toBe(true);
    expect(isNewer("1.30.0", "1.30.0")).toBe(false);
    expect(isNewer(undefined, "1.30.0")).toBe(false);
  });

  it("reloads at once with no window open, and waits for an open one to close", () => {
    vi.useFakeTimers();
    const reload = vi.fn();
    reloadWhenFree(reload, () => false);
    expect(reload).toHaveBeenCalledTimes(1);
    document.body.innerHTML = '<div role="dialog"></div>';
    const later = vi.fn();
    reloadWhenFree(later);
    vi.advanceTimersByTime(5000);
    expect(busy()).toBe(true);
    expect(later).not.toHaveBeenCalled();
    document.body.innerHTML = "";
    vi.advanceTimersByTime(2000);
    expect(later).toHaveBeenCalledTimes(1);
  });
});
