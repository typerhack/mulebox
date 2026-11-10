// What the actions menus offer: three dots on every job card and waiting row, and "Queue
// actions" for everything at once. Each item sends the same request as its command
// (`mulebox pause|resume|first|up|down|last|boost|normal|cancel`, `mulebox machine pause|resume`),
// and only the items that apply to the job as it is now are listed.

import { ChevronDown, ChevronUp, ChevronsDown, ChevronsUp, ExternalLink, Minus, Pause, Play, ScrollText,
         Snowflake, X, Zap, type LucideIcon } from "lucide-react";

import { cancelJob, controlJob, controlMachine, type JobAction } from "./api";
import { RUNNING, WAITING, jobHref, plural, safeUrl } from "./format";
import { go } from "./router";
import type { Job, MachinesPanel, QueueSnapshot } from "./types";
import type { MenuGroups, MenuItem } from "../ui/Menu";

const item = (id: string, Icon: LucideIcon, label: string, hint: string, run: MenuItem["run"],
              danger: { sure?: string } | null = null): MenuItem =>
  ({ id, Icon, label, hint, run, danger: Boolean(danger), sure: danger?.sure });
const control = (job: Job, action: JobAction) => () => controlJob(job.job_id, action);

function moves(job: Job, total: number): MenuItem[] {
  const at = job.position ?? 0;
  return [
    at > 1 && item("first", ChevronsUp, "Move to the front", "Starts before every other waiting job", control(job, "first")),
    at > 1 && item("up", ChevronUp, "Move up one", `To #${at - 1} in line`, control(job, "up")),
    at < total && item("down", ChevronDown, "Move down one", `To #${at + 1} in line`, control(job, "down")),
    at < total && item("last", ChevronsDown, "Move to the end", "Every other waiting job goes first", control(job, "last")),
  ].filter(Boolean) as MenuItem[];
}
const inLine = (job: Job, total: number) => (WAITING.has(job.state) && job.position ? moves(job, total) : []);

// A GitHub run's slot: it moves while it waits; once it runs, its runner is frozen or boosted
// (runners/runner_controls.py). Cancel asks GitHub, which owns the run (runners/cancel_run.py).
function runnerGroups(job: Job, total: number, open: MenuItem): MenuGroups {
  const running = RUNNING.has(job.state);
  const run = safeUrl(job.run_url);
  const hold = !running ? null : job.paused
    ? item("resume", Play, "Resume", "The runner goes on where it stopped", control(job, "resume"))
    : item("freeze", Snowflake, "Freeze", "Stops the runner and its containers; a long freeze can fail the run",
           control(job, "pause"));
  const boost = !running ? null : job.boost
    ? item("calm", Minus, "End boost", "Shares the machine again", control(job, "normal"))
    : item("boost", Zap, "Boost", "Gets the CPU and disk first; nothing new starts beside it", control(job, "boost"));
  const github = run && item("github", ExternalLink, "Open on GitHub", "The run, its steps and its output there",
                             () => { window.open(run, "_blank", "noopener"); });
  const cancel = run && item("cancel", X, "Cancel on GitHub", "Asks GitHub to cancel the run; the slot frees",
                             () => cancelJob(job.job_id), { sure: "Yes, cancel the run" });
  return [[hold], inLine(job, total), [boost, open, github], [cancel]]
    .map((group) => group.filter(Boolean) as MenuItem[]);
}

export function jobGroups(job: Job, total: number): MenuGroups {
  const open = item("open", ScrollText, "Open its page", "Its log, stages and all its details",
                    () => go(jobHref(job)));
  if (job.kind === "runner") return runnerGroups(job, total, open);
  if (job.kind === "upgrade") {
    return [moves(job, total), [open],
            [item("cancel", X, "Cancel upgrade", "Takes it out of line; the machine stays as it is",
                  () => cancelJob(job.job_id), {})]];
  }
  const running = RUNNING.has(job.state);
  const hold = job.paused
    ? item("resume", Play, "Resume", running ? "Goes on where it stopped" : "Can start again, in its place",
           control(job, "resume"))
    : running
      ? item("freeze", Snowflake, "Freeze", "Stops it where it is, containers too; nothing is lost", control(job, "pause"))
      : item("pause", Pause, "Pause", "Keeps its place in line but does not start", control(job, "pause"));
  const boost = job.boost
    ? item("calm", Minus, "End boost", "Shares the machine again", control(job, "normal"))
    : item("boost", Zap, "Boost", running ? "Gets the CPU and disk first; nothing new starts beside it"
                                          : "Goes first, then gets its machine to itself", control(job, "boost"));
  return [[hold], inLine(job, total), [boost, open],
          [item("cancel", X, "Cancel job", "Stops it for whoever waits on it", () => cancelJob(job.job_id), {})]];
}

// Whether a job has anything to steer: the three dots show only then.
export function steerable(job: Job): boolean {
  const live = WAITING.has(job.state) || RUNNING.has(job.state);
  const onlyMoves = job.kind === "upgrade" && WAITING.has(job.state) && Boolean(job.position);
  const run = job.kind === "runner" && (RUNNING.has(job.state) || Boolean(job.position));
  return live && !job.cancel_requested && (job.kind === "job" || onlyMoves || run);
}

async function each<T>(list: T[], send: (one: T) => Promise<unknown>) {
  const results = await Promise.allSettled(list.map(send));
  const failed = results.filter((r): r is PromiseRejectedResult => r.status === "rejected");
  if (failed.length) {
    const why = failed[0].reason instanceof Error ? failed[0].reason.message : "no answer";
    throw new Error(`${failed.length} of ${list.length} not changed: ${why}`);
  }
}

// "Queue actions": every machine and every job at once.
export function queueGroups(snapshot: QueueSnapshot | null, machines: MachinesPanel | null): MenuGroups {
  const jobs = [...(snapshot?.running ?? []), ...(snapshot?.queued ?? [])]
    .filter((job) => job.kind === "job" && !job.cancel_requested);
  const toFreeze = jobs.filter((job) => RUNNING.has(job.state) && !job.paused);
  const paused = jobs.filter((job) => job.paused);
  const rows = (machines?.machines ?? []).filter((m) => m.state !== "offline");
  const taking = rows.filter((m) => m.state !== "draining"), held = rows.filter((m) => m.state === "draining");
  return [
    [taking.length && item("pause-machines", Pause, "Pause all machines", "No new job starts; what runs finishes",
                           () => each(taking, (m) => controlMachine(m.name, "pause"))),
     held.length && item("resume-machines", Play, "Resume all machines",
                         held.length === 1 ? "The machine takes jobs again" : `${held.length} machines take jobs again`,
                         () => each(held, (m) => controlMachine(m.name, "resume")))],
    [toFreeze.length && item("freeze-jobs", Snowflake, `Freeze ${plural(toFreeze.length, "running job")}`,
                             "Each stops where it is; nothing is lost",
                             () => each(toFreeze, (j) => controlJob(j.job_id, "pause"))),
     paused.length && item("resume-jobs", Play, `Resume ${plural(paused.length, "paused job")}`,
                           "Frozen ones go on, paused ones can start",
                           () => each(paused, (j) => controlJob(j.job_id, "resume")))],
  ].map((group) => group.filter(Boolean) as MenuItem[]);
}
