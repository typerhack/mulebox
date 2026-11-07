// The queue by machine: one lane per worker with what it is running and the jobs waiting
// that only it can take. Slots, capabilities and readings are the Machines box's job
// (machines.js), so a lane carries only the machine's name and state.
//
// The queue itself is one line: a waiting job is not assigned until a worker claims it, so
// nothing here invents an assignment. A job goes in a machine's lane only when that machine
// is the one place it can run (pinned runner reservation, or the only worker whose
// capabilities cover its `needs`). A job several machines could take waits in one shared
// list, and a job no machine fits is shown as stuck with the coordinator's reason.
// Positions are the real queue positions in every list.

import { doingLine } from "./doing.js";
import { badge, clock, duration, el, jobLink, soonest, questionMark, runText } from "./format.js";

const SHARED = { title: "next free machine", sub: "whichever of these is free first" };
const STUCK = { title: "no machine fits", sub: "nothing offers what they need" };

function lane(name, machine) {
  return { name, machine, running: [], waiting: [] };
}

// Group the rows. `machines` may lag the queue by an event, so a worker the panel does not
// list yet still gets a lane, with what is known about it.
export function groupLanes(snapshot, machines) {
  const lanes = new Map((machines?.machines ?? []).map((m) => [m.name, lane(m.name, m)]));
  const get = (name) => {
    if (!lanes.has(name)) lanes.set(name, lane(name, null));
    return lanes.get(name);
  };
  const shared = [], stuck = [];
  for (const job of snapshot?.running ?? []) get(job.worker ?? "?").running.push(job);
  for (const job of snapshot?.queued ?? []) {
    const places = job.pinned_worker ? [job.pinned_worker] : job.can_run_on;
    if (!Array.isArray(places)) shared.push(job);  // an older server: no placement given
    else if (places.length === 1) get(places[0]).waiting.push(job);
    else if (places.length) shared.push(job);
    else stuck.push(job);
  }
  return { lanes: [...lanes.values()], shared, stuck };
}

// The time so far, and what a job like it usually takes. Never a time left or a percentage:
// past runs do not say how far this one has come (coordinator/usual.py).
function elapsed(job) {
  return el("span", { class: "time" },
    el("span", { class: "num", "data-elapsed": job.job_id, text: duration(job.elapsed_s) }),
    job.usual_s ? el("span", { class: "usual", text: `of usually ${duration(job.usual_s)}` }) : null);
}

function block(job, cores) {
  return el("div", { class: "slot-block", "data-filled": "1" },
    el("div", { class: "slot-head" }, badge(job.shown_state ?? job.state), elapsed(job)),
    jobLink(job),
    el("span", { class: "branch", text: runText(job) }),
    doingLine(job, cores),
    questionMark(job));
}

function blocks(entry) {
  if (entry.running.length) return entry.running.map((job) => block(job, entry.machine?.cores));
  const idle = entry.machine?.state === "offline" ? "offline" : "idle";
  return [el("p", { class: "empty", text: idle })];
}

function machineCell(entry) {
  const m = entry.machine;
  const head = el("p", { class: "head" }, el("strong", { text: entry.name }),
                  badge(m ? m.state : "unknown"));
  const alone = soonest([...entry.running, ...entry.waiting]);
  const lines = [head, questionMark(alone.job, alone.count)];
  if (m?.state === "offline") lines.push(el("p", { class: "muted", text: `last seen ${clock(m.last_seen)}` }));
  return el("div", { class: "lane-machine" }, ...lines);
}

function groupCell(group, tone) {
  return el("div", { class: "lane-machine" },
    el("p", { class: "head" }, el("strong", { text: group.title }), tone ? badge(tone) : null),
    el("p", { class: "muted", text: group.sub }));
}

// A waiting entry: its real queue position, the job, how long it has waited, and below it
// the reason it cannot start (from the coordinator) or, in the shared list, which machines
// could take it when not all of them can.
function waitingEntry(job, allMachines) {
  const place = job.position ? el("span", { class: "pos", text: `#${job.position}` })
                             : badge(job.shown_state ?? job.state);
  const lines = [];
  if (job.waiting_for) {
    lines.push(el("p", { class: "reason" }, badge("stuck"), el("span", { text: job.waiting_for })));
  } else if (allMachines && Array.isArray(job.can_run_on) && job.can_run_on.length < allMachines) {
    lines.push(el("p", { class: "muted", text: `only ${job.can_run_on.join(", ")}` }));
  }
  lines.push(questionMark(job));
  return el("li", { class: "wait" }, place,
    el("span", {}, jobLink(job), el("span", { class: "branch", text: runText(job) })),
    elapsed(job), ...lines);
}

function waitingCell(jobs, allMachines) {
  if (!jobs.length) return el("div", { class: "lane-waiting" }, el("p", { class: "empty", text: "nothing waiting" }));
  return el("div", { class: "lane-waiting" }, el("ul", { class: "waits" },
    ...jobs.map((job) => waitingEntry(job, allMachines))));
}

function laneRow(entry, state) {
  return el("div", { class: "lane", "data-state": state ?? null }, machineCell(entry),
    el("div", { class: "lane-running" }, ...blocks(entry)), waitingCell(entry.waiting));
}

function groupRow(group, jobs, tone, allMachines) {
  return el("div", { class: "lane", "data-state": tone ?? "shared" }, groupCell(group, tone),
    el("div", { class: "lane-running muted", text: "" }), waitingCell(jobs, allMachines));
}

function header() {
  return el("div", { class: "lane lane-head", "aria-hidden": "true" },
    ...["machine", "running", "waiting"].map((text) => el("span", { text })));
}

export function lanesView(snapshot, machines) {
  const { lanes, shared, stuck } = groupLanes(snapshot, machines);
  const root = el("div", { class: "lanes" });
  if (!lanes.length && !shared.length && !stuck.length) {
    root.append(el("p", { class: "empty", text: "No machine has checked in yet." }));
    return root;
  }
  root.append(header());
  // Stuck jobs first: they are the one thing here that needs a person.
  if (stuck.length) root.append(groupRow(STUCK, stuck, "stuck", null));
  for (const entry of lanes) root.append(laneRow(entry, entry.machine?.state));
  if (shared.length) root.append(groupRow(SHARED, shared, null, lanes.length));
  return root;
}
