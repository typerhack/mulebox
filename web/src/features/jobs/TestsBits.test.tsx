import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Job, JobDetail, Tests } from "../../lib/types";
import { TipProvider } from "../../ui/Tip";
import { LOG_ID } from "../job/LogPanel";
import { summaryRanges } from "../job/logMarks";
import { TestsNote } from "../job/TestsNote";
import { TestsPanel } from "../job/TestsPanel";
import { DoneList } from "./DoneList";

const NOW = new Date(2026, 10, 15, 14, 30).getTime() / 1000;
const last = (runners: NonNullable<Tests["runners"]>, branch = "main") =>
  ({ job_id: "job-01EXAMPLEX4R2D4", branch, ran: 0, runners, finished_at: NOW - 3600 });
const job = (id: string, tests: Tests | undefined, more: Partial<JobDetail> = {}): JobDetail => ({
  job_id: `job-01EXAMPLE${id}`, project: "example-app", job: "check", state: "finished", outcome: "passed", shown_state: "passed",
  kind: "job", worker: "build-1", duration_s: 229, section: "recent", tests, ...more,
});
const FAILED = { outcome: "failed", shown_state: "failed", exit_code: 8 };
const FEWER = job("FEWER1", { runners: { pytest: { ran: 3462, skipped: 5 }, vitest: { ran: 213, skipped: 0 } }, ran: 3675, skipped: 5,
  verdict: "fewer", compared: last({ pytest: { ran: 3470 }, vitest: { ran: 213 } }, "fix/cart-total"), command_exit: 0 }, FAILED);
const ZERO = job("ZERO01", { runners: { vitest: { ran: 0, skipped: 213 } }, ran: 0, skipped: 213, verdict: "zero",
  compared: last({ vitest: { ran: 213 } }), command_exit: 0 }, FAILED);
const BROKE = job("BROKE1", { runners: { jest: { ran: 1204, skipped: 2 } }, ran: 1204, skipped: 2, verdict: null, compared: null },
  { outcome: "failed", shown_state: "failed", exit_code: 1 });
const OK = job("OK0001", { runners: { pytest: { ran: 3462, skipped: 5 } }, ran: 3462, skipped: 5, verdict: "ok", compared: last({ pytest: { ran: 3462 } }) });
const MORE = job("MORE01", { runners: { pytest: { ran: 1904, skipped: 2 } }, ran: 1904, skipped: 2, verdict: "ok", compared: last({ pytest: { ran: 1892 } }) });
const ALLOWED = job("ALLOW1", { runners: { pytest: { ran: 1820, skipped: 2 } }, ran: 1820, skipped: 2, verdict: "allowed",
  fewer: "removed the old v1 API tests", compared: last({ pytest: { ran: 1892 } }) });
const LINT = job("LINT01", { runners: {}, ran: 0, skipped: 0, verdict: null, compared: null }, { job: "lint" });
const MISSING = job("MISS01", { mode: "required", runners: {}, ran: 0, skipped: 0, verdict: "missing", compared: null, command_exit: 0 }, FAILED);

afterEach(cleanup);
const rows = (jobs: Job[]) => { render(<DoneList jobs={jobs} last="machine" />); return screen.getAllByRole("listitem"); };
const page = (row: JobDetail) => render(<TipProvider><TestsNote job={row} /><TestsPanel job={row} now={NOW} /></TipProvider>);

describe("a finished row's tests", () => {
  it("shows the count as a quiet number, with how much the suite grew", () => {
    const [ok, more, broke] = rows([OK, MORE, BROKE]);
    expect(ok.textContent).toContain("3462tests");
    expect(ok.textContent).not.toMatch(/\+|fewer|ran no/);
    expect(within(ok).getByTitle("3462 tests ran, 5 skipped")).toBeTruthy();
    expect(more.textContent).toContain("1904tests+12");
    expect(broke.textContent).toContain("1204tests");          // an ordinary failure keeps its count
    expect(broke.textContent).not.toMatch(/fewer|last pass/);    // and adds nothing
  });

  it("adds a line in words for fewer, none and an allowed drop, coloured on its icon only", () => {
    const [fewer, zero, allowed] = rows([FEWER, ZERO, ALLOWED]);
    expect(fewer.textContent).toContain("8 fewer tests than the last pass: pytest ran 3462, was 3470");
    expect(fewer.querySelector("svg.lucide-list-minus")?.getAttribute("class")).toContain("text-failed");
    expect(zero.textContent).toContain("vitest ran no tests: all 213 were skipped");
    expect(zero.textContent).toContain("0tests");
    expect(zero.querySelector("svg.lucide-list-x")?.getAttribute("class")).toContain("text-failed");
    expect(allowed.textContent).toContain("72 fewer tests, allowed. The agent's reason: “removed the old v1 API tests”");
    expect(allowed.querySelector("svg.lucide-list-minus")?.getAttribute("class")).toContain("text-warning");
  });

  it("shows nothing for a job with no summary or none counted, and no number for a missing one", () => {
    const [lint, plain, missing] = rows([LINT, job("PLAIN1", undefined), MISSING]);
    for (const row of [lint, plain]) expect(row.textContent).not.toMatch(/tests|summary/);
    expect(missing.textContent).toContain("No test summary in its log, and this job requires one");
    expect(missing.textContent).not.toMatch(/\dtests/);
  });
});

describe("a job page's tests", () => {
  it("says a failure for fewer tests in a danger strip, with the command and two ways on", () => {
    page(FEWER);
    const strip = screen.getByRole("status");
    expect(strip.className).toContain("border-danger");
    expect(strip.textContent).toContain("Fewer tests than the last pass. The command passed, but pytest ran 3462 tests and the last pass on fix/cart-total ran 3470.");
    expect(strip.textContent).toContain("Removed on purpose? The agent runs it again with the reason: mulebox check --fewer-tests \"<reason>\"");
    expect(screen.getByRole("button", { name: "Copy the command" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Go to the runner's summary" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open the last pass" }).getAttribute("href")).toBe("#/job/job-01EXAMPLEX4R2D4");
  });

  it("lists each runner beside the pass it was compared with, which is a link", () => {
    page(FEWER);
    const panel = screen.getByRole("region", { name: "Tests" });
    expect(panel.textContent).toContain("3675 ran, 5 skipped");
    expect(panel.textContent).toContain("pytest3462 ran 5 skipped8 fewer than the last pass, which ran 3470.");
    expect(panel.textContent).toContain("vitest213 ran 0 skippedThe same as the last pass.");
    expect(panel.textContent).toMatch(/Compared with X4R2D4, the last pass on fix\/cart-total, today \d\d:30[^.]*\./);
    expect(within(panel).getByRole("link", { name: "X4R2D4" }).getAttribute("href")).toBe("#/job/job-01EXAMPLEX4R2D4");
  });

  it("has a warning strip and the reason in the panel for an allowed drop, and no buttons", () => {
    page(ALLOWED);
    const strip = screen.getByRole("status");
    expect(strip.className).toContain("border-warning");
    expect(strip.textContent).toContain("Passed with 72 fewer tests, allowed. pytest ran 1820 tests and the last pass on main ran 1892.");
    expect(strip.textContent).not.toContain("mulebox check");
    expect(screen.queryByRole("button", { name: "Go to the runner's summary" })).toBeNull();
    expect(screen.getByRole("region", { name: "Tests" }).textContent).toContain("The agent's reason for fewer tests“removed the old v1 API tests”");
  });

  it("says no tests ran in a danger strip", () => {
    page(ZERO);
    expect(screen.getByRole("status").textContent).toContain("No tests ran. The command passed, but vitest ran 0 tests and skipped 213.");
    expect(screen.getByRole("region", { name: "Tests" }).textContent).toContain("No test ran. The last pass ran 213.");
  });

  it("has the panel and no strip for a normal pass and an ordinary failure", () => {
    page(MORE);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("region", { name: "Tests" }).textContent).toContain("12 more than the last pass, which ran 1892.");
    cleanup();
    page(BROKE);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("region", { name: "Tests" }).textContent).toContain("Not compared: only a pass is held to the last pass.");
  });

  it("shows nothing for a job with no summary, and only the strip's words for a missing one", () => {
    expect(page(LINT).container.innerHTML).toBe("");
    cleanup();
    page(MISSING);
    expect(screen.getByRole("status").textContent).toContain("No test summary. The command passed, but its log has no test runner's summary");
    expect(screen.queryByRole("button", { name: "Go to the runner's summary" })).toBeNull();
    expect(screen.getByRole("region", { name: "Tests" }).textContent).toContain("No test runner's summary in its log.");
  });

  it("finds the runners' summary lines in the log and goes to them", () => {
    render(<pre id={LOG_ID} tabIndex={0}>{"$ pytest -q && pnpm vitest run\n....... [100%]\n3462 passed, 5 skipped in 212.40s\n\n Test Files  24 passed (24)\n      Tests  213 passed (213)\n3 passed the review\n"}</pre>);
    const log = document.getElementById(LOG_ID) as HTMLElement;
    const lines = ["      Tests  213 passed (213)", "3462 passed, 5 skipped in 212.40s"];
    expect(summaryRanges(log, lines).map(String)).toEqual(lines);
    expect(summaryRanges(log, ["3 passed"])).toEqual([]);
    log.scrollIntoView = () => undefined;   // jsdom has none
    page(FEWER);
    fireEvent.click(screen.getByRole("button", { name: "Go to the runner's summary" }));
    expect(document.activeElement).toBe(log);
  });
});
