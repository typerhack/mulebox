// The machines box: every worker, whether it is online, its slots as filled or empty
// squares, its capabilities, what it is running, and a small live reading of its CPU and
// memory on the same load ramp as the big graphs.
//
// A reading is only shown when the server measured it (`cpu_pct`, `mem_pct` on the row).
// Every worker reports its machine's load (M5.3); one that is offline or has not reported yet
// says "no live data".

import { badge, clock, el, fill, jobLink, meter, soonest, questionMark } from "./format.js";

const READINGS = [["cpu", "cpu_pct"], ["mem", "mem_pct"]];

function slots(row) {
  const used = row.state === "offline" ? 0
    : row.state === "draining" ? row.jobs.length : Math.max(0, row.slots - row.free_slots);
  const squares = Array.from({ length: row.slots }, (_, i) =>
    el("span", { class: "slot", "data-used": i < used ? "1" : null }));
  const text = row.state === "offline"
    ? `last seen ${clock(row.last_seen)}`
    : row.state === "draining"
    ? `takes no new jobs, ${row.jobs.length} running`
    : `${row.free_slots} of ${row.slots} ${row.slots === 1 ? "slot" : "slots"} free`;
  return el("p", { class: "slots" }, el("span", { class: "boxes", "aria-hidden": "true" }, ...squares),
            el("span", { text }));
}

// One meter per reading. The value is always text too, so colour never carries it alone.
function reading(row, label, key) {
  const value = row[key];
  const bar = meter({ "aria-label": `${row.name} ${label}: ${value.toFixed(0)}%` });
  bar.set(value / 100);
  return el("div", { class: "row" }, el("span", { class: "label", text: label }), bar.node,
            el("span", { class: "value num", text: `${value.toFixed(0)}%` }));
}

function readings(row) {
  const live = READINGS.filter(([, key]) => typeof row[key] === "number");
  if (!live.length) {
    return el("p", { class: "muted reading-none", text: "no live data" });
  }
  return el("div", { class: "readings" }, ...live.map(([label, key]) => reading(row, label, key)));
}

function card(row) {
  const alone = soonest(row.jobs);
  const parts = [
    el("p", { class: "head" }, el("strong", { text: row.name }), badge(row.state)),
    questionMark(alone.job, alone.count),
    readings(row),
    slots(row),
  ];
  if (row.capabilities.length) {
    parts.push(el("p", { class: "muted", text: row.capabilities.join(", ") }));
  }
  if (row.jobs.length) {
    parts.push(el("ul", { class: "jobs" }, ...row.jobs.map((job) => el("li", {}, jobLink(job),
                                                                       questionMark(job)))));
  }
  return el("div", { class: "machine", "data-state": row.state }, ...parts.filter(Boolean));
}

export function renderMachines(box, panel) {
  const free = `${panel.free_slots} ${panel.free_slots === 1 ? "slot" : "slots"} free`;
  const body = fill(box, "Machines", `${panel.online} of ${panel.total} online, ${free}`,
                    ...panel.machines.map(card));
  if (!panel.machines.length) {
    body.append(el("p", { class: "empty", text: "No machine has checked in yet." }));
  }
}
