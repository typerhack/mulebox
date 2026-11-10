import { describe, expect, it } from "vitest";

import { nearest } from "./chart";
import { parseCiLog } from "./cilog";
import { resolve } from "./prefs";
import { quietText } from "./quiet";
import { parseRoute } from "./router";
import { dayScale, hourTick, label, midnights, share } from "./stats";
import { timeline } from "./timeline";
import type { JobDetail } from "./types";

describe("parseCiLog", () => {
  it("reads steps and the output the runner handed over", () => {
    const text = ["mulebox: step: Set up job", "mulebox: step: Build site", "--- output of Build site",
                  "$ pnpm run build", "done", "--- output of a step", "Cleaning up", ""].join("\n");
    const { steps, other } = parseCiLog(text);
    expect(steps).toEqual([{ name: "Set up job", output: "" }, { name: "Build site", output: "$ pnpm run build\ndone\n" }]);
    expect(other).toBe("--- output of a step\nCleaning up");
  });
});

describe("timeline", () => {
  const job: JobDetail = {
    job_id: "j", state: "running", kind: "job", failed_stage: null,
    steps: [{ stage: "prepare", started_at: 100, finished_at: 102 },
            { stage: "command", started_at: 102, finished_at: null }],
    usual: { job_s: 240, stages: { prepare: 3, command: 190 } },
  };

  it("puts every stage on one scale, the open one up to now", () => {
    const made = timeline(job, 150);
    expect(made).toMatchObject({ scale: 240, elapsed: 50, running: true, usual: 240 });
    expect(made?.rows[0]).toMatchObject({ name: "prepare", state: "passed", from: 0, length: 2, usualAt: 3, took: "2s" });
    expect(made?.rows[1]).toMatchObject({ state: "running", from: 2, length: 48, usualAt: 192, took: "48s so far" });
    expect(made?.axis).toEqual(["0", "1m", "2m", "3m", "4m"]);
  });

  it("marks the stage that failed and shows its line", () => {
    const failed = timeline({ ...job, state: "finished", failed_stage: "command",
      steps: [{ stage: "command", started_at: 0, finished_at: 10, failing_line: "FAIL x" }] }, 99);
    expect(failed?.rows[0]).toMatchObject({ state: "failed", extra: { text: "FAIL x", code: true } });
    expect(timeline({ ...job, steps: [] }, 1)).toBeNull();
  });
});

describe("small helpers", () => {
  it("reads the hash routes", () => {
    expect(parseRoute("")).toEqual({ page: "queue" });
    expect(parseRoute("#/stats")).toEqual({ page: "stats" });
    expect(parseRoute("#/machines")).toEqual({ page: "machines" });
    expect(parseRoute("#/job/job-1%2Fx")).toEqual({ page: "job", jobId: "job-1/x" });
    expect(parseRoute("#/nothing")).toEqual({ page: "queue" });
  });

  it("makes Auto Rainbow in light and Gauge in dark", () => {
    expect(resolve("system", "auto", true)).toMatchObject({ theme: "light", paint: "rainbow" });
    expect(resolve("system", "auto", false)).toMatchObject({ theme: "dark", paint: "gauge" });
    expect(resolve("dark", "rainbow", true)).toMatchObject({ theme: "dark", paint: "rainbow" });
    expect(resolve("light", "gauge", false)).toMatchObject({ theme: "light", paint: "gauge" });
  });

  it("says when a job is quiet and whether it works", () => {
    expect(quietText({ output_idle_s: 10 })).toBe("");
    expect(quietText({ output_idle_s: 45, job_cpu_pct: 320 })).toContain("3.2 cores");
    expect(quietText({ output_idle_s: 45, job_cpu_pct: 2 })).toContain("almost no CPU");
  });

  it("finds the sample nearest the pointer, skipping holes", () => {
    const points = [{ t: 0, v: 1 }, { t: 10, v: null }, { t: 20, v: 3 }];
    expect(nearest(points, (t) => t, 11)).toEqual({ t: 20, v: 3 });
    expect(nearest([], (t) => t, 1)).toBeNull();
  });

  it("scales the day chart and words its numbers", () => {
    const days = [{ from: 0, runs: 1, kinds: { job: 3600, runner: 1800 } }];
    expect(dayScale(days, ["job", "runner"])).toMatchObject({ step: 1, max: 7200 });
    expect(dayScale(days, ["runner"]).step).toBe(0.25);
    expect(hourTick(0.5)).toBe("30m");
    expect(share(1, 4)).toBe("25%");
    expect(share(1, 300)).toBe("0.3%");
    expect(label("client", "laptop.local")).toBe("laptop");
    expect(label("kind", "runner")).toBe("GitHub Actions");
    expect(midnights(3, new Date(2026, 10, 10, 15)).map((t) => new Date(t * 1000).getDate())).toEqual([8, 9, 10]);
  });
});
