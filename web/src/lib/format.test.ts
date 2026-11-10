import { describe, expect, it } from "vitest";

import { ago, bytes, codeParts, duration, jobName, nameParts, roughly, safeUrl, soonest } from "./format";
import type { Job } from "./types";

const job = (more: Partial<Job>): Job => ({ job_id: "job-01ABCDEF123456", state: "queued", kind: "job", ...more });

describe("format", () => {
  it("writes durations as the terminal view does", () => {
    expect(duration(null)).toBe("-");
    expect(duration(9)).toBe("9s");
    expect(duration(134)).toBe("2m 14s");
    expect(duration(3725)).toBe("1h 02m");
    expect(roughly(90)).toBe("2m");
    expect(roughly(45)).toBe("45s");
  });

  it("writes sizes and ages", () => {
    expect(bytes(0)).toBe("0 B");
    expect(bytes(1536)).toBe("1.5 KB");
    expect(bytes(215 * 1024 ** 3)).toBe("215 GB");
    expect(ago(1000, 1005)).toBe("now");
    expect(ago(1000, 1000 + 14 * 60)).toBe("14 min ago");
    expect(ago(null, 5)).toBe("never");
  });

  it("names a GitHub slot by its repository without the owner", () => {
    expect(nameParts(job({ kind: "runner", project: "example-org__docs-site", job: "build" }))).toEqual(["docs-site", "build"]);
    expect(jobName(job({ project: "example-app", job: "check" }))).toBe("example-app / check");
    expect(jobName(job({ kind: "upgrade", branch: "0.96.0" }))).toBe("mulebox upgrade to 0.96.0");
  });

  it("only lets http links through", () => {
    expect(safeUrl("https://github.com/example-org/x/actions/runs/1")).toContain("https://github.com/");
    expect(safeUrl("javascript:alert(1)")).toBeNull();
    expect(safeUrl("")).toBeNull();
  });

  it("finds the question that runs out first", () => {
    const jobs = [job({ question: { reason: "a", left_s: 90 } }), job({}), job({ job_id: "b", question: { reason: "b", left_s: 20 } })];
    expect(soonest(jobs)).toMatchObject({ count: 2, job: { job_id: "b" } });
  });

  it("splits a line into text and commands", () => {
    expect(codeParts("Run `mulebox ok` now")).toEqual([
      { text: "Run ", code: false }, { text: "mulebox ok", code: true }, { text: " now", code: false }]);
  });
});
