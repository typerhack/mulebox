// The machines box: every worker, whether it is online, and its slots as filled or empty
// squares, so what is free shows at a glance.

import { badge, clock, el, fill } from "./format.js";

function jobLink(job) {
  const label = job.kind === "runner" ? `${job.project} (CI)` : `${job.project} / ${job.job}`;
  return el("li", {}, el("a", { href: `#/job/${encodeURIComponent(job.job_id)}`, text: label }));
}

function slots(row) {
  const used = row.state === "offline" ? 0 : Math.max(0, row.slots - row.free_slots);
  const squares = Array.from({ length: row.slots }, (_, i) =>
    el("span", { class: "slot", "data-used": i < used ? "1" : null }));
  const text = row.state === "offline"
    ? `last seen ${clock(row.last_seen)}`
    : `${row.free_slots} of ${row.slots} ${row.slots === 1 ? "slot" : "slots"} free`;
  return el("p", { class: "slots" }, el("span", { class: "boxes", "aria-hidden": "true" }, ...squares),
            el("span", { text }));
}

function card(row) {
  const parts = [
    el("p", { class: "head" }, el("strong", { text: row.name }), badge(row.state)),
    slots(row),
  ];
  if (row.capabilities.length) {
    parts.push(el("p", { class: "muted", text: row.capabilities.join(", ") }));
  }
  if (row.jobs.length) parts.push(el("ul", { class: "jobs" }, ...row.jobs.map(jobLink)));
  return el("div", { class: "machine", "data-state": row.state }, ...parts);
}

export function renderMachines(box, panel) {
  const free = `${panel.free_slots} ${panel.free_slots === 1 ? "slot" : "slots"} free`;
  const body = fill(box, "Machines", `${panel.online} of ${panel.total} online, ${free}`,
                    ...panel.machines.map(card));
  if (!panel.machines.length) {
    body.append(el("p", { class: "empty", text: "No machine has checked in yet." }));
  }
}
