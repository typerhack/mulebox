// The machines box: every worker, whether it is online, its slots as filled or empty
// squares, its capabilities, what it is running, and a small live reading of its CPU and
// memory on the same load ramp as the big graphs, and its network in and out as text.
//
// A reading is only shown when the server measured it (`cpu_pct`, `mem_pct` on the row).
// Every worker reports its machine's load (M5.3); one that is offline or has not reported yet
// says "no live data". Each online machine has Pause (no new jobs there; what runs finishes) or
// Resume, the dashboard's `mulebox machine pause|resume`. Network (M14.2) counts the machine's physical interfaces only, so a VPN
// tunnel's traffic is not added to Wi-Fi's.

import { actionToken, post } from "./access.js";
import { badge, bytes, clock, el, fill, jobLink, meter, soonest, questionMark } from "./format.js";

const READINGS = [["cpu", "cpu_pct"], ["mem", "mem_pct"]];

let token = null;  // the controls show from the first render after the page has it
actionToken().then((given) => { token = given; });
const asked = new Map();  // machine -> what this page asked and has not seen yet, or a refusal

async function steer(name, action) {
  asked.set(name, action === "pause" ? "Pausing" : "Resuming");
  try {
    await post(`/api/machines/${encodeURIComponent(name)}/control`, { action });
  } catch (failure) {
    asked.set(name, `Not changed. ${failure.status ? failure.message : "The dashboard did not answer."}`);
  }
}

function control(row) {
  if (!token || row.state === "offline") return null;
  const paused = row.state === "draining";
  const note = asked.get(row.name);
  if (note && (note === "Pausing") === paused) asked.delete(row.name);  // it took
  const left = asked.get(row.name);
  if (left && !left.startsWith("Not")) return el("span", { class: "muted", role: "status", text: left });
  const made = el("button", { type: "button", class: "machine-control",
                              text: paused ? "Resume" : "Pause",
                              title: paused ? "Let this machine take jobs again"
                                            : "Take no new jobs here; what runs finishes" });
  made.addEventListener("click", () => steer(row.name, paused ? "resume" : "pause"));
  return el("span", { class: "machine-controls" }, made,
            left ? el("span", { class: "failed", role: "alert", text: left }) : null);
}

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

const rate = (kibS) => `${bytes(kibS * 1024)}/s`;

// Text only: a rate has no fixed top, so a bar would mean nothing.
function network(row) {
  const { net_in_kib_s: inbound, net_out_kib_s: outbound } = row;
  if (typeof inbound !== "number" || typeof outbound !== "number") return null;
  return el("div", { class: "row net" }, el("span", { class: "label", text: "net" }),
            el("span", { class: "value num", text: `in ${rate(inbound)}, out ${rate(outbound)}` }));
}

function readings(row) {
  const live = READINGS.filter(([, key]) => typeof row[key] === "number");
  if (!live.length) {
    return el("p", { class: "muted reading-none", text: "no live data" });
  }
  return el("div", { class: "readings" }, ...live.map(([label, key]) => reading(row, label, key)),
            ...[network(row)].filter(Boolean));
}

function card(row) {
  const alone = soonest(row.jobs);
  const parts = [
    el("p", { class: "head" }, el("strong", { text: row.name }), badge(row.state)),
    control(row),
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
