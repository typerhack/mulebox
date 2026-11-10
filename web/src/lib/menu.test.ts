import { afterEach, describe, expect, it, vi } from "vitest";

import { jobGroups, queueGroups, steerable } from "./menu";
import type { Job, Machine } from "./types";

const job = (more: Partial<Job>): Job => ({ job_id: "job-1", state: "queued", kind: "job", position: 2, ...more });
const labels = (groups: ReturnType<typeof jobGroups>) => groups.map((group) => group.map((item) => item.label));
const machine = (name: string, state: string): Machine => ({ name, state, slots: 2, free_slots: 1, capabilities: [], jobs: [] });

afterEach(() => vi.unstubAllGlobals());

describe("menus", () => {
  it("offers a waiting job pause, its moves, boost and cancel", () => {
    expect(labels(jobGroups(job({}), 3))).toEqual([
      ["Pause"], ["Move to the front", "Move up one", "Move down one", "Move to the end"],
      ["Boost", "Open its page"], ["Cancel job"]]);
    expect(labels(jobGroups(job({ position: 1 }), 1))[1]).toEqual([]);
  });

  it("offers a running job freeze or resume and no moves", () => {
    expect(labels(jobGroups(job({ state: "running", position: null }), 3))[0]).toEqual(["Freeze"]);
    const frozen = labels(jobGroups(job({ state: "running", position: null, paused: true, boost: true }), 3));
    expect(frozen).toEqual([["Resume"], [], ["End boost", "Open its page"], ["Cancel job"]]);
  });

  it("offers a GitHub run its moves while it waits, and asks GitHub to cancel", () => {
    const run = job({ kind: "runner", run_url: "https://github.com/example-org/x/actions/runs/1" });
    const waiting = jobGroups(run, 3);
    expect(labels(waiting)).toEqual([[], ["Move to the front", "Move up one", "Move down one", "Move to the end"],
                                     ["Open its page", "Open on GitHub"], ["Cancel on GitHub"]]);
    expect(waiting[3][0]).toMatchObject({ danger: true, sure: "Yes, cancel the run" });
    expect(labels(jobGroups({ ...run, state: "running", position: null }, 3))[0]).toEqual(["Freeze"]);
    expect(labels(jobGroups({ ...run, run_url: "javascript:1" }, 3))[3]).toEqual([]);
  });

  it("shows the three dots only where something can be steered", () => {
    expect(steerable(job({}))).toBe(true);
    expect(steerable(job({ state: "finished" }))).toBe(false);
    expect(steerable(job({ cancel_requested: true }))).toBe(false);
    expect(steerable(job({ kind: "upgrade" }))).toBe(true);
    expect(steerable(job({ kind: "upgrade", state: "running" }))).toBe(false);
    expect(steerable(job({ kind: "runner", position: null }))).toBe(false);
  });

  it("sends the same request as the command, with the page's token", async () => {
    const fetched = vi.fn(async (url: string) => new Response(
      JSON.stringify(url === "/api/session" ? { action_token: "tok" } : { ok: true })));
    vi.stubGlobal("fetch", fetched);
    await jobGroups(job({}), 3)[0][0].run();
    const [url, options] = fetched.mock.calls.at(-1) as unknown as [string, RequestInit];
    expect(url).toBe("/api/jobs/job-1/control");
    expect(options.body).toBe(JSON.stringify({ action: "pause" }));
    expect((options.headers as Record<string, string>)["X-Mulebox-Token"]).toBe("tok");
  });

  it("lists for the whole queue only what applies now", () => {
    const snapshot = { now: 0, recent: [], queued: [job({ paused: true })],
                       running: [job({ job_id: "r", state: "running" }), job({ job_id: "ci", kind: "runner", state: "running" })] };
    const panel = { machines: [machine("build-1", "busy"), machine("build-2", "draining"), machine("build-3", "offline")],
                    total: 3, online: 2, free_slots: 1 };
    expect(labels(queueGroups(snapshot, panel))).toEqual([
      ["Pause all machines", "Resume all machines"], ["Freeze 1 running job", "Resume 1 paused job"]]);
    expect(labels(queueGroups(null, null))).toEqual([[], []]);
  });
});
