import { afterEach, describe, expect, it, vi } from "vitest";

import { reply } from "./heldServer.testing";
import { askRun, askUsage, coreUnit, coresOf, memoryOf, memoryUnit, part, sendsNoUsage, weight, whyNot, type UsageJob } from "./usage";

const GB = 1e9;
const job = (name: string, more: Partial<UsageJob> = {}): UsageJob => ({
  project: "example-app", job: name, kind: "job", runs: 20, measured: 20, not_measured: 0, no_cores: 0,
  cores: { median: 1, max: 2 }, memory: { median: GB, max: 2 * GB }, fits: { cores: 2, memory: 2 * GB }, machines: ["build-1"], ...more,
});
const refuse = (status: number) => Promise.resolve(new Response("no such route", { status }));

afterEach(() => vi.unstubAllGlobals());

describe("the ruling of a usage bar", () => {
  it("rules cores one by one up to 16, then in larger steps", () => {
    expect([4, 8, 16, 32, 64].map(coreUnit)).toEqual([1, 1, 1, 2, 4]);
  });
  it("rules memory so a node is 8 units or fewer", () => {
    expect([2, 8, 16, 32, 64].map((gb) => memoryUnit(gb * GB) / GB)).toEqual([0.5, 2, 2, 4, 8]);
    expect(memoryUnit(16.6 * GB) / GB).toBe(2);
  });
  it("never draws a share past the node's end", () => {
    expect(part(4, 8)).toBe("50.00%");
    expect(part(12, 8)).toBe("100.00%");
  });
});

describe("what a job weighs on a node", () => {
  const size = { cores: 8, memory: 16 * GB };
  it("is the larger share of its highest peaks, with the unmeasured last", () => {
    const cpu = job("cpu", { cores: { median: 5, max: 6 } }), ram = job("ram", { memory: { median: GB, max: 14 * GB } });
    const none = job("none", { measured: 0, cores: null, memory: null });
    expect([none, cpu, ram].sort((a, b) => weight(b, size) - weight(a, size)).map((j) => j.job)).toEqual(["ram", "cpu", "none"]);
  });
});

describe("the words for a gap and a peak", () => {
  it("knows a mulebox from before usage was sent", () => {
    expect(["1.35.5", "0.99.0", "1.36.0", "2.0.0", null, "dev"].map(sendsNoUsage)).toEqual([true, true, false, false, false, false]);
    expect(whyNot("build-2", "1.35.5", "these runs")).toBe("build-2 runs mulebox 1.35.5, which sends no usage");
    expect(whyNot("build-2", "1.36.0", "this run")).toBe("build-2 sent no usage for this run");
  });
  it("sets a peak beside its node, or alone when the node's size is not known", () => {
    expect(coresOf(6.12, { cores: 8 })).toBe("6.1 of 8 cores");
    expect(coresOf(6.12, {})).toBe("6.1 cores");
    expect(memoryOf(3.5 * GB, { memory: 16 * GB })).toBe("3.5 GB of 16.0 GB");
  });
});

describe("asking for the summary", () => {
  it("asks once per node when jobs ran on several, and sorts each node heaviest first", async () => {
    const asked: string[] = [];
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      asked.push(url);
      const worker = new URL(url, "http://x").searchParams.get("worker");
      const jobs = worker === "build-2" ? [job("check", { machines: ["build-2"] })]
        : worker === "build-1" ? [job("lint"), job("check", { cores: { median: 5, max: 6 } })]
          : [job("check", { machines: ["build-1", "build-2"] }), job("lint"), job("queued", { machines: [] })];
      return reply({ machines: { "build-1": { cores: 8, memory: 16 * GB }, "build-2": { cores: 4, memory: 8 * GB } }, jobs, runs: 20, all: true });
    }));
    const view = await askUsage({ project: "", kind: "job" }, true);
    expect(asked).toEqual(["/api/usage?kind=job&all=1", "/api/usage?kind=job&all=1&worker=build-1", "/api/usage?kind=job&all=1&worker=build-2"]);
    expect(view?.nodes.map((node) => [node.name, node.size.cores, node.jobs.map((j) => j.job)])).toEqual(
      [["build-1", 8, ["check", "lint"]], ["build-2", 4, ["check"]]]);
    expect(view?.projects).toEqual(["example-app"]);
    expect(view?.machines).toEqual(["build-1", "build-2"]);
  });

  it("asks once when everything ran on one node, and keeps the project choices of a filtered answer out", async () => {
    const fetched = vi.fn(() => reply({ machines: { "build-1": { cores: 8 } }, jobs: [job("check")], runs: 20, all: false }));
    vi.stubGlobal("fetch", fetched);
    const view = await askUsage({ project: "example-app" }, false);
    expect(fetched).toHaveBeenCalledTimes(1);
    expect(view?.projects).toBeNull();
    expect(view?.nodes[0].jobs).toHaveLength(1);
  });

  it("reads an older coordinator's 404 as nothing to show, and any other refusal as a failure", async () => {
    vi.stubGlobal("fetch", vi.fn(() => refuse(404)));
    expect(await askUsage({}, false)).toBeNull();
    expect(await askRun("job-1")).toBeNull();
    vi.stubGlobal("fetch", vi.fn(() => refuse(500)));
    await expect(askUsage({}, false)).rejects.toThrow("500");
  });
});
