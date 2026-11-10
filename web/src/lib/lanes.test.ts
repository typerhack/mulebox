import { describe, expect, it } from "vitest";

import { groupLanes, isStuck, waitReason } from "./lanes";
import type { Job, Machine, MachinesPanel, QueueSnapshot } from "./types";

const job = (id: string, more: Partial<Job>): Job => ({ job_id: id, state: "queued", kind: "job", ...more });
const machine = (name: string, state = "available"): Machine =>
  ({ name, state, slots: 2, free_slots: 2, capabilities: [], jobs: [] });
const panel = (...machines: Machine[]): MachinesPanel =>
  ({ machines, total: machines.length, online: machines.length, free_slots: 0 });
const queue = (running: Job[], queued: Job[]): QueueSnapshot => ({ now: 0, running, queued, recent: [] });

describe("groupLanes", () => {
  it("puts a waiting job in exactly one place", () => {
    const snapshot = queue(
      [job("run", { state: "running", worker: "build-1" })],
      [job("only", { position: 1, can_run_on: ["build-2"] }),
       job("pinned", { position: 2, kind: "runner", pinned_worker: "build-2" }),
       job("any", { position: 3, can_run_on: ["build-1", "build-2"] }),
       job("none", { position: 4, can_run_on: [] }),
       job("old-server", { position: 5 })]);
    const made = groupLanes(snapshot, panel(machine("build-1"), machine("build-2", "offline"), machine("build-3")));
    expect(made.lanes.map((lane) => lane.name)).toEqual(["build-1", "build-2"]);
    expect(made.lanes[1].waiting.map((j) => j.job_id)).toEqual(["only", "pinned"]);
    expect(made.shared.map((j) => j.job_id)).toEqual(["any", "old-server"]);
    expect(made.stuck.map((j) => j.job_id)).toEqual(["none"]);
    expect(made.quiet.map((lane) => lane.name)).toEqual(["build-3"]);
    expect(made.total).toBe(5);
  });

  it("gives a worker the panel does not list yet its own lane", () => {
    const made = groupLanes(queue([job("run", { state: "running", worker: "new-one" })], []), panel());
    expect(made.lanes).toMatchObject([{ name: "new-one", machine: null }]);
  });

  it("says why a job waits", () => {
    expect(isStuck(job("a", { can_run_on: [] }))).toBe(true);
    expect(isStuck(job("a", { can_run_on: [], pinned_worker: "build-1" }))).toBe(false);
    expect(waitReason(job("a", { waiting_for: "paused" }), 3)).toBe("paused");
    expect(waitReason(job("a", { can_run_on: ["build-1"] }), 3)).toBe("Only build-1");
    expect(waitReason(job("a", { can_run_on: ["build-1", "build-2"] }), 2)).toBeNull();
  });
});
