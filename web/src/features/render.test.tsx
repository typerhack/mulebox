import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../lib/api";
import type { Job, JobDetail, Machine } from "../lib/types";
import { machinesStore, queueStore } from "../state/live";
import { Meter } from "../ui/Meter";
import { TipProvider } from "../ui/Tip";
import { CancelControl, buttonsFor, said } from "./job/JobControls";
import { JobsBox } from "./jobs/JobsBox";

const job = (id: string, more: Partial<Job>): Job =>
  ({ job_id: `job-${id}`, project: "example-app", job: "check", state: "queued", kind: "job", ...more });
const machine = (name: string, more: Partial<Machine> = {}): Machine =>
  ({ name, state: "busy", slots: 2, free_slots: 0, capabilities: [], jobs: [], cores: 8, ...more });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  tokenStore.set(undefined);
  queueStore.set({ snapshot: null, at: 0 });
  machinesStore.set(null);
});

function showQueue() {
  queueStore.set({ at: performance.now(), snapshot: {
    now: 0,
    running: [job("run", { state: "running", worker: "build-1", section: "running", elapsed_s: 61, usual_s: 240,
                           paused: true, doing: { stage: "command", cpu_pct: 320 } })],
    queued: [job("wait", { position: 1, section: "queued", elapsed_s: 5, can_run_on: ["build-1", "build-2"] }),
             job("stuck", { position: 2, section: "queued", can_run_on: [], waiting_for: "Needs gpu" })],
    recent: [job("ok", { state: "finished", outcome: "passed", shown_state: "passed", section: "recent", duration_s: 9 }),
             job("bad", { state: "finished", shown_state: "failed", section: "recent", kind: "runner",
                          ci_result: { step: "Build site", message: "Process completed with exit code 1." } })],
  } });
  machinesStore.set({ machines: [machine("build-1"), machine("build-2", { state: "available" })], total: 2, online: 2, free_slots: 2 });
}

describe("the Jobs box", () => {
  it("shows the queue by machine, with counts on the tabs", () => {
    showQueue();
    render(<TipProvider><JobsBox /></TipProvider>);
    expect(screen.getByRole("tab", { name: /Queue/ }).textContent).toContain("3");
    expect(screen.getByRole("region", { name: "build-1" }).textContent).toContain("1m 01s of usually 4m");
    expect(screen.getByRole("img", { name: "Running, frozen" })).toBeTruthy();
    expect(screen.getByRole("meter", { name: /3.2 of 8/ }).getAttribute("aria-valuenow")).toBe("40");
    expect(screen.getByRole("region", { name: "No machine fits" }).textContent).toContain("Needs gpu");
    expect(screen.getByRole("region", { name: "Next free machine" }).textContent).toContain("waiting 5s");
    expect(screen.getByRole("region", { name: /Nothing running on build-2/ })).toBeTruthy();
  });

  it("says which job holds a waiting job's branch, as `mulebox queue` does", () => {
    queueStore.set({ at: performance.now(), snapshot: {
      now: 0, recent: [],
      running: [job("run", { state: "running", worker: "build-1", section: "running" })],
      queued: [job("next", { position: 1, section: "queued", can_run_on: ["build-1", "build-2"], branch_busy: "job-xfzpmd" })],
    } });
    machinesStore.set({ machines: [machine("build-1"), machine("build-2", { state: "available" })], total: 2, online: 2, free_slots: 2 });
    render(<TipProvider><JobsBox /></TipProvider>);
    expect(screen.getByRole("region", { name: "Next free machine" }).textContent).toContain("xfzpmd is running on this branch");
  });

  it("has no controls without the page's token, and arrows and menus with it", () => {
    showQueue();
    const { unmount } = render(<TipProvider><JobsBox /></TipProvider>);
    expect(screen.queryByRole("group", { name: /Move/ })).toBeNull();
    unmount();
    tokenStore.set("tok");
    render(<TipProvider><JobsBox /></TipProvider>);
    expect(screen.getAllByRole("group", { name: /Move example-app/ })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Move to the front of the line" }).map((b) => b.hasAttribute("disabled"))).toEqual([false, true]);
    expect(screen.getAllByRole("button", { name: /^Actions for/ })).toHaveLength(3);
  });

  it("splits a lane with running and waiting jobs, and only that lane", () => {
    showQueue();
    queueStore.set({ at: performance.now(), snapshot: {
      now: 0, recent: [],
      running: [job("a", { state: "running", worker: "build-1" }), job("b", { state: "running", worker: "build-2" })],
      queued: [job("w", { position: 1, can_run_on: ["build-1"] }), job("any", { position: 2, can_run_on: ["build-1", "build-2"] })],
    } });
    render(<TipProvider><JobsBox /></TipProvider>);
    const split = screen.getByRole("region", { name: "build-1" });
    expect([...split.querySelectorAll("h3")].map((h) => h.textContent)).toEqual(["Running", "Waiting in line"]);
    expect(screen.getByRole("list", { name: "Waiting for build-1" }).children).toHaveLength(1);
    expect(screen.getByRole("region", { name: "build-2" }).querySelector("h3")).toBeNull();
    expect(screen.getByRole("region", { name: "Next free machine" }).querySelector("h3")).toBeNull();
  });

  it("folds a long line to its first rows and opens it in place, positions kept", () => {
    showQueue();
    queueStore.set({ at: performance.now(), snapshot: {
      now: 0, recent: [], running: [job("a", { state: "running", worker: "build-1" })],
      queued: Array.from({ length: 8 }, (_, i) => job(`w${i}`, { position: i + 1, can_run_on: ["build-1"] })),
    } });
    render(<TipProvider><JobsBox /></TipProvider>);
    const list = screen.getByRole("list", { name: "Waiting for build-1" });
    expect(list.children).toHaveLength(5);
    expect(screen.getByRole("region", { name: "build-1" }).textContent).toContain("8 waiting for it");
    const more = screen.getByRole("button", { name: "Show all waiting (8)" });
    expect(more.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(more);
    expect(list.children).toHaveLength(8);
    expect(list.querySelector("li:last-child [aria-label='Position 8']")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show the first 5" }));
    expect(list.children).toHaveLength(5);
  });

  it("remembers the tab, and says where a GitHub job failed", () => {
    showQueue();
    render(<TipProvider><JobsBox /></TipProvider>);
    fireEvent.click(screen.getByRole("tab", { name: /Failed/ }));
    expect(localStorage.getItem("mulebox-jobs-tab")).toBe("failed");
    expect(screen.getByRole("tabpanel").textContent).toContain("In Build site: Process completed with exit code 1");
    expect(screen.getByRole("tabpanel").textContent).toContain("1 of the last 2 finished jobs.");
  });
});

describe("a job's controls", () => {
  const running: JobDetail = { job_id: "job-x", state: "running", kind: "job" };

  it("asks twice before cancelling, and keeps the job on the first answer", async () => {
    const fetched = vi.fn(async (url: string) => new Response(
      JSON.stringify(url === "/api/session" ? { action_token: "tok" } : { state: "running" })));
    vi.stubGlobal("fetch", fetched);
    render(<CancelControl job={running} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel job" }));
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Keep job"));
    expect(fetched).not.toHaveBeenCalledWith("/api/jobs/job-x/cancel", expect.anything());
    fireEvent.click(screen.getByRole("button", { name: "Keep job" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel job" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, cancel job" }));
    await screen.findByText("Cancel requested. The job is stopping.");
    expect(fetched.mock.calls.at(-1)?.[0]).toBe("/api/jobs/job-x/cancel");
  });

  it("lists what applies to the job as it is", () => {
    const names = (j: JobDetail) => buttonsFor(j).map(([, text]) => text);
    expect(names(running)).toEqual(["Freeze", "Boost"]);
    expect(names({ ...running, state: "queued", position: 2, paused: true })).toEqual(
      ["Resume", "To front", "Up", "Down", "To end", "Boost"]);
    expect(names({ ...running, kind: "runner", state: "queued", position: 1 })).toEqual(["To front", "Up", "Down", "To end"]);
    expect(said({ ...running, state: "queued", position: 2 })).toBe("#2 in line.");
    expect(said({ ...running, paused: true })).toContain("frozen on its machine");
  });
});

describe("a meter", () => {
  it("turns warning from 80% and danger from 92%, with an icon beside the number", () => {
    render(<><Meter name="a" value={50} text="50%" label="a" /><Meter name="b" value={84} text="84%" label="b" />
             <Meter name="c" value={95} text="95%" label="c" /></>);
    expect(screen.getByRole("meter", { name: "a" }).dataset.level).toBeUndefined();
    expect(screen.getByRole("meter", { name: "b" }).dataset.level).toBe("warn");
    expect(screen.getByRole("meter", { name: "c" }).dataset.level).toBe("danger");
    expect(document.querySelectorAll("svg").length).toBe(2);
  });
});
