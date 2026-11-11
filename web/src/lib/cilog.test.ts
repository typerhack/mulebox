import { describe, expect, it } from "vitest";

import { parseCiLog, stepSeconds } from "./cilog";

const T = (iso: string) => Date.parse(iso) / 1000;

describe("parseCiLog with step times and results", () => {
  const text = [
    "mulebox: step at 2026-11-11T07:25:03Z: Set up runner",
    "mulebox: step passed at 2026-11-11T07:26:33Z: Set up runner",
    "mulebox: step at 2026-11-11T07:26:33Z: Post Run x: y",
    "mulebox: step skipped at 2026-11-11T07:26:33Z: Post Run x: y",
    "mulebox: step at 2026-11-11T07:26:33Z: count",
    "--- output of count", "line 1",
  ].join("\n");

  it("gives each step its times and result, names with a colon kept whole", () => {
    const { steps, other } = parseCiLog(text);
    expect(steps.map((s) => [s.name, s.result])).toEqual([
      ["Set up runner", "passed"], ["Post Run x: y", "skipped"], ["count", null]]);
    expect(steps[0]).toMatchObject({ startedAt: T("2026-11-11T07:25:03Z"), endedAt: T("2026-11-11T07:26:33Z") });
    expect(steps[2].output).toBe("line 1\n");
    expect(other).toBe("");
  });

  it("measures an ended step to its end and a running one to now", () => {
    const { steps } = parseCiLog(text);
    expect(stepSeconds(steps[0], T("2026-11-11T08:00:00Z"))).toBe(90);
    expect(stepSeconds(steps[1], T("2026-11-11T08:00:00Z"))).toBe(0);
    expect(stepSeconds(steps[2], T("2026-11-11T07:27:03Z"))).toBe(30);
  });

  it("reads a log from before step times: no length, the old failed line still counts", () => {
    const { steps } = parseCiLog("mulebox: step: Tests\nmulebox: step failed: Tests\n");
    expect(steps).toMatchObject([{ name: "Tests", result: "failed", startedAt: null, endedAt: null }]);
    expect(stepSeconds(steps[0], 0)).toBeNull();
  });
});
