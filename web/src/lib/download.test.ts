import { describe, expect, it } from "vitest";

import { downloadView } from "./download";

const MB = 1024 ** 2;

describe("a download in words", () => {
  it("is nothing when nothing downloads", () => {
    expect(downloadView(null)).toBeNull();
    expect(downloadView(undefined)).toBeNull();
  });

  it("gives a share and one unit when the total is known", () => {
    const view = downloadView({ what: "cache", name: "npm cache", done_bytes: 12 * MB, total_bytes: 41 * MB,
                                rate_bytes_s: 0.6 * MB, as_of_s: 2, stalled: false });
    expect(view).toMatchObject({ amount: "12.0 of 41.0 MB", subject: "npm cache", speed: "614 KB/s", quiet: null });
    expect(view?.share).toBeCloseTo(29.27, 1);
    expect(downloadView({ done_bytes: 512 * 1024, total_bytes: 41 * MB })?.amount).toBe("512 KB of 41.0 MB");
    expect(downloadView({ done_bytes: 50 * MB, total_bytes: 41 * MB })?.share).toBe(100);
  });

  it("has no share without a total, and says what it knows", () => {
    expect(downloadView({ what: "package", done_bytes: 18 * MB, total_bytes: null }))
      .toMatchObject({ share: null, amount: "18.0 MB so far", subject: "packages", speed: null });
    expect(downloadView({ what: "tool", name: "node-v22.12.0-linux-x64.tar.gz" })?.amount).toBe("size not known");
    expect(downloadView({ what: "network", total_bytes: 0 })).toMatchObject({ share: null, subject: "" });
    // a size with nothing yet arrived: no definite 0%, and worded as what is to come
    expect(downloadView({ what: "package", total_bytes: 906 * MB }))
      .toMatchObject({ share: null, sized: true, amount: "906 MB to download" });
  });

  it("says at least, in the words, for a floor", () => {
    expect(downloadView({ done_bytes: 12 * MB, total_bytes: 41 * MB }, true)?.amount).toBe("at least 12.0 of 41.0 MB");
    expect(downloadView({ done_bytes: 18 * MB }, true)?.amount).toBe("at least 18.0 MB so far");
    expect(downloadView({ total_bytes: 906 * MB }, true)?.amount).toBe("906 MB to download");
    expect(downloadView({ done_bytes: 12 * MB, total_bytes: 41 * MB })?.amount).toBe("12.0 of 41.0 MB");
  });

  it("prefers the job's own measured traffic, and never passes the node's off as the job's", () => {
    const printed = { done_bytes: MB, rate_bytes_s: 100 * 1024 };
    expect(downloadView({ ...printed, net_bytes_s: 600 * 1024, net_scope: "job" }))
      .toMatchObject({ speed: "600 KB/s", wholeNode: false });
    expect(downloadView({ ...printed, net_bytes_s: 600 * 1024, net_scope: "machine" }))
      .toMatchObject({ speed: "100 KB/s", wholeNode: false });
    expect(downloadView({ done_bytes: MB, net_bytes_s: 600 * 1024, net_scope: "machine" }))
      .toMatchObject({ speed: "600 KB/s", wholeNode: true });
  });

  it("says for how long no byte has moved, only once the worker counts it stopped", () => {
    expect(downloadView({ done_bytes: MB, quiet_s: 45, stalled: false, rate_bytes_s: 0 })?.quiet).toBeNull();
    expect(downloadView({ done_bytes: MB, quiet_s: 61.4, stalled: true, rate_bytes_s: 9 }))
      .toMatchObject({ quiet: "No bytes for 61 s", speed: null });
    expect(downloadView({ quiet_s: 200, stalled: true })?.quiet).toBe("No bytes for 3m 20s");
    expect(downloadView({ quiet_s: null, stalled: true })?.quiet).toBe("No bytes moving");
  });
});
