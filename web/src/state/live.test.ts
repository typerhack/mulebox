import { afterEach, describe, expect, it, vi } from "vitest";

const reloads = vi.fn();
vi.mock("../lib/upgraded", async (real) => ({
  ...(await real<typeof import("../lib/upgraded")>()),
  reloadWhenFree: () => { reloads(); return () => undefined; },
}));

class Quiet { onopen = null; onerror = null; readyState = 0; addEventListener() {} close() {} }

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); reloads.mockReset(); });

describe("a page left open across an upgrade", () => {
  it("reloads when it comes back into view on a new version, with no reconnect seen", async () => {
    vi.useFakeTimers();
    let version = "1.32.1";
    vi.stubGlobal("EventSource", Quiet);  // the stream never opens: a sleeping tab saw nothing
    vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(
      JSON.stringify(url === "/healthz" ? { version } : {}), { status: 200 })));
    const { startLive } = await import("./live");
    const stop = startLive();
    await vi.advanceTimersByTimeAsync(60_000);  // the minute's read: the version it loaded with
    expect(reloads).not.toHaveBeenCalled();
    version = "1.32.2";
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(0);
    expect(reloads).toHaveBeenCalledTimes(1);
    stop();
  });
});
