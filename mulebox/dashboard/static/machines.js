// The machines panel: every worker, whether it is online, and what it has free.

import { badge, clock, el } from "./format.js";

function jobLink(job) {
  const label = job.kind === "runner" ? `${job.project} (CI)` : `${job.project} / ${job.job}`;
  return el("li", {}, el("a", { href: `#/job/${encodeURIComponent(job.job_id)}`, text: label }));
}

function detail(row) {
  if (row.state === "offline") return `Last seen ${clock(row.last_seen)}`;
  return `${row.free_slots} of ${row.slots} ${row.slots === 1 ? "slot" : "slots"} free`;
}

function card(row) {
  const parts = [
    el("p", { class: "machine-head" }, el("strong", { text: row.name }), badge(row.state)),
    el("p", { class: "muted", text: detail(row) }),
  ];
  if (row.capabilities.length) {
    parts.push(el("p", { class: "muted", text: row.capabilities.join(", ") }));
  }
  if (row.jobs.length) parts.push(el("ul", { class: "machine-jobs" }, ...row.jobs.map(jobLink)));
  return el("div", { class: "machine-card" }, ...parts);
}

export function renderMachines(root, panel) {
  const free = `${panel.free_slots} ${panel.free_slots === 1 ? "slot" : "slots"} free`;
  root.replaceChildren(
    el("h2", {}, "Machines ", el("span", { class: "value",
      text: `${panel.online} of ${panel.total} online, ${free}` })),
    ...panel.machines.map(card));
  if (!panel.machines.length) {
    root.append(el("p", { class: "muted", text: "No machine has checked in yet." }));
  }
}
