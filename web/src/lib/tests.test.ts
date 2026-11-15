import { describe, expect, it } from "vitest";

import { dayTime } from "./format";
import { testsView } from "./tests";
import type { Tests } from "./types";

const view = (tests: Tests | null | undefined, state = "finished") => testsView({ state, tests });
const last = (runners: NonNullable<Tests["runners"]>, branch = "main") =>
  ({ job_id: "job-01EXAMPLEX4R2D4", branch, ran: 0, runners, finished_at: 1_800_000_000 });

describe("the tests a job ran, in words", () => {
  it("is nothing for a running job, a job not counted, and a job with no summary", () => {
    expect(view(undefined)).toBeNull();
    expect(view({ mode: "auto", base: "main", fewer: null })).toBeNull();                 // only what it was sent with
    expect(view({ runners: {}, ran: 0, skipped: 0, verdict: null, compared: null })).toBeNull();  // a lint
    expect(view({ runners: { pytest: { ran: 4, skipped: 0 } }, ran: 4, verdict: "ok" }, "running")).toBeNull();
  });

  it("is a plain count for a pass with as many tests, and for an ordinary failure", () => {
    const same = view({ runners: { pytest: { ran: 40, skipped: 2 } }, ran: 40, skipped: 2, verdict: "ok", compared: last({ pytest: { ran: 40 } }) });
    expect(same).toMatchObject({ kind: "ok", tone: "plain", ran: 40, skipped: 2, delta: null, line: null, strip: null, passed: true });
    expect(same?.rows[0].text).toBe("The same as the last pass.");
    const broke = view({ runners: { jest: { ran: 1204, skipped: 2 } }, ran: 1204, skipped: 2, verdict: null, compared: null });
    expect(broke).toMatchObject({ kind: "ok", line: null, strip: null, delta: null, passed: false });
    expect(broke?.rows[0]).toMatchObject({ text: "", mark: null });
  });

  it("says by how much a suite grew, a new runner included", () => {
    const more = view({ runners: { pytest: { ran: 1904, skipped: 2 } }, ran: 1904, verdict: "ok", compared: last({ pytest: { ran: 1892 } }) });
    expect(more).toMatchObject({ kind: "more", delta: "+12", line: null, strip: null });
    expect(more?.rows[0]).toMatchObject({ mark: "more", tone: "plain", text: "12 more than the last pass, which ran 1892." });
    const added = view({ runners: { pytest: { ran: 10 }, vitest: { ran: 5 } }, ran: 15, verdict: "ok", compared: last({ pytest: { ran: 10 } }) });
    expect(added?.delta).toBe("+5");
    expect(added?.rows[1].text).toBe("The last pass had no count from it.");
  });

  it("words a failure for fewer tests with the runner and both numbers", () => {
    const fewer = view({ runners: { pytest: { ran: 3462, skipped: 5 }, vitest: { ran: 213, skipped: 0 } }, ran: 3675, skipped: 5, verdict: "fewer",
      compared: last({ pytest: { ran: 3470 }, vitest: { ran: 213 } }, "fix/cart-total"), command_exit: 0 });
    expect(fewer).toMatchObject({ kind: "fewer", tone: "failed", first: ["pytest"], delta: null });
    expect(fewer?.line).toEqual({ bold: "8 fewer tests", rest: " than the last pass: pytest ran 3462, was 3470" });
    expect(fewer?.strip).toEqual({ title: "Fewer tests than the last pass.",
      text: "The command passed, but pytest ran 3462 tests and the last pass on fix/cart-total ran 3470." });
    expect(fewer?.rows.map((row) => [row.mark, row.tone])).toEqual([["fewer", "failed"], [null, "plain"]]);
    expect(fewer?.rows[0].text).toBe("8 fewer than the last pass, which ran 3470.");
  });

  it("counts a runner the last pass had and this run does not as none", () => {
    const gone = view({ runners: { pytest: { ran: 10 } }, ran: 10, verdict: "fewer", compared: last({ pytest: { ran: 10 }, vitest: { ran: 1 } }) });
    expect(gone?.line).toEqual({ bold: "1 fewer test", rest: " than the last pass: vitest ran 0, was 1" });
    expect(gone?.rows[1]).toMatchObject({ name: "vitest", ran: 0, mark: "zero", text: "No summary from it in this run. The last pass ran 1." });
  });

  it("words a pass with no tests", () => {
    const zero = view({ runners: { vitest: { ran: 0, skipped: 213 } }, ran: 0, skipped: 213, verdict: "zero", compared: last({ vitest: { ran: 213 } }) });
    expect(zero?.line).toEqual({ bold: "vitest ran no tests", rest: ": all 213 were skipped" });
    expect(zero?.strip?.text).toBe("The command passed, but vitest ran 0 tests and skipped 213. A pass with no tests counts as a failure.");
    expect(zero?.rows[0]).toMatchObject({ mark: "zero", tone: "failed", text: "No test ran. The last pass ran 213." });
    expect(view({ runners: { pytest: { ran: 0, skipped: 0 } }, verdict: "zero" })?.line).toEqual({ bold: "pytest ran no tests", rest: "" });
  });

  it("words a drop the agent allowed, with its reason in its own words", () => {
    const allowed = view({ runners: { pytest: { ran: 1820, skipped: 2 } }, ran: 1820, verdict: "allowed", fewer: "removed the old v1 API tests",
      compared: last({ pytest: { ran: 1892 } }) });
    expect(allowed).toMatchObject({ kind: "allowed", tone: "warn", reason: "removed the old v1 API tests" });
    expect(allowed?.line).toEqual({ bold: "72 fewer tests, allowed.", rest: " The agent's reason: “removed the old v1 API tests”" });
    expect(allowed?.strip).toEqual({ title: "Passed with 72 fewer tests, allowed.",
      text: "pytest ran 1820 tests and the last pass on main ran 1892. The agent let this run pass with fewer. Its reason: “removed the old v1 API tests”." });
    expect(allowed?.rows[0].tone).toBe("warn");
  });

  it("words a required summary that is missing, with no count", () => {
    const missing = view({ mode: "required", runners: {}, ran: 0, skipped: 0, verdict: "missing", compared: null, command_exit: 0 });
    expect(missing).toMatchObject({ kind: "missing", tone: "failed", counted: false, rows: [] });
    expect(missing?.line?.bold).toBe("No test summary");
  });

  it("writes a moment as today, yesterday or its day", () => {
    const at = (d: number, h: number) => new Date(2026, 10, d, h, 5).getTime() / 1000;
    expect(dayTime(at(15, 12), at(15, 14))).toMatch(/^today \d\d:05/);
    expect(dayTime(at(14, 23), at(15, 0))).toMatch(/^yesterday \d\d:05/);
    expect(dayTime(at(3, 9), at(15, 14))).toMatch(/3.*Nov|Nov.*3/);
  });
});
