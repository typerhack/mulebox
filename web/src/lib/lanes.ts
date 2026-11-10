// The queue by machine: one lane per worker with what it is running and the jobs waiting
// that only it can take.
//
// The queue itself is one line: a waiting job is not assigned until a worker claims it, so
// nothing here invents an assignment. A job goes in a machine's lane only when that machine
// is the one place it can run (pinned runner reservation, or the only worker whose
// capabilities cover its `needs`). A job several machines could take waits in one shared
// list, and a job no machine fits is shown as stuck with the coordinator's reason.

import { shortId } from "./format";
import type { Job, Machine, MachinesPanel, QueueSnapshot } from "./types";

export interface Lane {
  name: string;
  machine: Machine | null;
  running: Job[];
  waiting: Job[];
}

export interface Lanes {
  lanes: Lane[];   // machines that run or wait for something
  quiet: Lane[];   // the rest: one line of names
  shared: Job[];
  stuck: Job[];
  total: number;   // jobs with a place in line, across every lane
}

// `machines` may lag the queue by an event, so a worker the panel does not list yet still
// gets a lane, with what is known about it.
export function groupLanes(snapshot: QueueSnapshot | null, machines: MachinesPanel | null): Lanes {
  const all = new Map<string, Lane>((machines?.machines ?? []).map((m) =>
    [m.name, { name: m.name, machine: m, running: [], waiting: [] }]));
  const get = (name: string) => {
    let lane = all.get(name);
    if (!lane) { lane = { name, machine: null, running: [], waiting: [] }; all.set(name, lane); }
    return lane;
  };
  const shared: Job[] = [], stuck: Job[] = [];
  for (const job of snapshot?.running ?? []) get(job.worker ?? "?").running.push(job);
  for (const job of snapshot?.queued ?? []) {
    const places = job.pinned_worker ? [job.pinned_worker] : job.can_run_on;
    if (!Array.isArray(places)) shared.push(job);  // an older server: no placement given
    else if (places.length === 1) get(places[0]).waiting.push(job);
    else if (places.length) shared.push(job);
    else stuck.push(job);
  }
  const rows = [...all.values()];
  const busy = (lane: Lane) => lane.running.length > 0 || lane.waiting.length > 0;
  return { lanes: rows.filter(busy), quiet: rows.filter((lane) => !busy(lane)), shared, stuck,
           total: (snapshot?.queued ?? []).filter((job) => job.position).length };
}

export const isStuck = (job: Job) =>
  Array.isArray(job.can_run_on) && !job.can_run_on.length && !job.pinned_worker;

// Why a waiting job is where it is: the coordinator's reason, the job holding its branch (as
// `mulebox queue` says it, client/report.py), or which machines could take it when not all can.
export function waitReason(job: Job, machineCount: number | null): string | null {
  if (job.waiting_for) return job.waiting_for;
  if (job.branch_busy) return `${shortId({ job_id: job.branch_busy })} is running on this branch`;
  if (machineCount && Array.isArray(job.can_run_on) && job.can_run_on.length < machineCount) {
    return `Only ${job.can_run_on.join(", ")}`;
  }
  return null;
}

// A long line shows its first few jobs until asked for all of them. One row more than that
// is shown as it is: a control that hides a single row saves nothing.
export const WAIT_SHOWN = 5;

export function shownWaiting(jobs: Job[], all: boolean): { rows: Job[]; long: boolean } {
  const long = jobs.length > WAIT_SHOWN + 1;
  return { rows: long && !all ? jobs.slice(0, WAIT_SHOWN) : jobs, long };
}
