// Job views: the Jobs box with its tabs (Queue by machine, Failed, Passed, Recent) and the
// paged history. Rows come from the server's status model (common/status.py), so sections,
// order and shown state match `mulebox queue`; the machines come from the machines panel.
//
// Each tab shows one thing. Queue is what is happening now; Failed and Passed are the
// results that are one or the other (a released runner slot and a cancelled job are
// neither, and only Recent and History list them); Recent is the last few finished jobs.

import { badge, clock, duration, el, fill, getJson, jobLink, timeLeft, warningIcon } from "./format.js";
import { lanesView } from "./lanes.js";

const FAILED = new Set(["failed", "timed_out", "interrupted"]);
const TAB_KEY = "mulebox-jobs-tab";
const TABS = [
  { id: "queue", label: "Queue", pick: (s) => [...s.running, ...s.queued] },
  { id: "failed", label: "Failed", pick: (s) => s.recent.filter((j) => FAILED.has(j.shown_state)) },
  { id: "passed", label: "Passed", pick: (s) => s.recent.filter((j) => j.shown_state === "passed") },
  { id: "recent", label: "Recent", pick: (s) => s.recent },
];

let current = remembered();

function remembered() {
  let tab = null;
  try { tab = localStorage.getItem(TAB_KEY); } catch { tab = null; }
  return TABS.some((t) => t.id === tab) ? tab : "queue";
}

function choose(id) {
  current = id;
  try { localStorage.setItem(TAB_KEY, id); } catch { /* private mode */ }
}

const state = (job) => badge(job.shown_state ?? job.outcome ?? job.state);

function where(job) {
  if (job.section === "queued") return job.position ? `queue #${job.position}` : "queue";
  return job.worker ?? "-";
}

// Columns: state, job (with branch), machine, time. Running rows are the brightest. A
// ticking cell is keyed by job id, so a tick can never land on another row.
function row(job, last) {
  const ticking = job.section === "recent" ? null : job.job_id;
  return el("tr", { class: job.section === "running" ? "running" : null },
    el("td", { class: "state" }, state(job)),
    el("td", {}, jobLink(job), el("span", { class: "branch", text: job.branch ?? "-" })),
    el("td", { class: "wide", text: last(job) }),
    el("td", { class: "num", "data-elapsed": ticking,
               text: duration(job.elapsed_s ?? job.duration_s) }));
}

function head(last) {
  return el("thead", {}, el("tr", {}, ...[["state", "state"], ["job", null], [last, "wide"],
                                           ["time", null]].map(([text, cls]) =>
    el("th", { scope: "col", class: cls, text }))));
}

// Finished rows only, of the last few the server keeps for the queue; History has the rest.
function table(tab, snapshot) {
  const body = el("tbody", {});
  const jobs = tab.pick(snapshot);
  for (const job of jobs) body.append(row(job, where));
  const kept = snapshot.recent.length;
  const scope = tab.id === "recent" ? `the last ${kept} finished jobs; `
    : jobs.length ? `${jobs.length} of the last ${kept} finished jobs; ` : `none of the last ${kept} finished jobs; `;
  const note = el("p", { class: "status" }, scope, el("a", { href: "#/history", text: "History" }),
                  " has them all.");
  return [jobs.length ? el("table", {}, head("machine"), body) : null, note];
}

function tabs(snapshot, box, machines) {
  const buttons = TABS.map((tab) => {
    const count = snapshot ? tab.pick(snapshot).length : null;
    const button = el("button", { type: "button", role: "tab", id: `tab-${tab.id}`, "data-tab": tab.id,
                                  "aria-selected": String(tab.id === current),
                                  "aria-controls": "jobs-panel",
                                  tabindex: tab.id === current ? "0" : "-1" }, tab.label);
    if (count !== null) button.append(el("span", { class: "count", text: String(count) }));
    const alone = tab.id === "queue" && snapshot ? tab.pick(snapshot).filter((j) => j.unattended).length : 0;
    if (alone) {
      button.append(el("span", { class: "count warned", title: `${alone} unattended` }, warningIcon(),
                       el("span", { text: `${alone} unattended` })));
    }
    button.addEventListener("click", () => { choose(tab.id); queueView(box, snapshot, machines); });
    return button;
  });
  const list = el("div", { class: "tabs", role: "tablist", "aria-label": "Job views" }, ...buttons);
  list.addEventListener("keydown", (event) => {
    const index = TABS.findIndex((t) => t.id === current);
    const step = { ArrowRight: 1, ArrowLeft: -1, Home: -index, End: TABS.length - 1 - index }[event.key];
    if (step === undefined) return;
    event.preventDefault();
    choose(TABS[(index + step + TABS.length) % TABS.length].id);
    queueView(box, snapshot, machines);
    box.querySelector(`[data-tab="${current}"]`)?.focus();
  });
  return list;
}

function fleetNote(machines) {
  if (!machines) return "waiting for data";
  const free = `${machines.free_slots} ${machines.free_slots === 1 ? "slot" : "slots"} free`;
  return `${machines.online} of ${machines.total} online, ${free}`;
}

export function queueView(box, snapshot, machines) {
  const focused = document.activeElement?.dataset?.tab;
  const tab = TABS.find((t) => t.id === current);
  const panel = el("div", { class: "panel", role: "tabpanel", id: "jobs-panel",
                            "aria-labelledby": `tab-${tab.id}` });
  if (!snapshot) panel.append(el("p", { class: "empty", text: "waiting for data" }));
  else if (tab.id === "queue") panel.append(lanesView(snapshot, machines));
  else panel.append(...table(tab, snapshot));
  fill(box, "Jobs", fleetNote(machines), tabs(snapshot, box, machines), panel);
  if (focused) box.querySelector(`[data-tab="${current}"]`)?.focus();
}

// Waiting and running times tick locally between queue events; the server sends the base.
// Cells carry their job id, whatever order tabs or lanes put them in.
export function tick(root, snapshot, sinceSnapshot) {
  const base = new Map();
  for (const job of [...(snapshot?.running ?? []), ...(snapshot?.queued ?? [])]) {
    base.set(job.job_id, job.elapsed_s);
  }
  root.querySelectorAll("[data-elapsed]").forEach((cell) => {
    const value = base.get(cell.dataset.elapsed);
    if (typeof value === "number") cell.textContent = duration(value + sinceSnapshot);
  });
}

// Time left on unattended jobs, wherever one is shown. Somebody watching again ends the mark
// (the machines box and a job's page redraw less often than the queue).
export function tickLeft(root, snapshot, sinceSnapshot) {
  const base = new Map();
  for (const job of [...(snapshot?.running ?? []), ...(snapshot?.queued ?? [])]) {
    base.set(job.job_id, job.unattended?.left_s ?? null);
  }
  root.querySelectorAll("[data-left]").forEach((cell) => {
    const value = base.get(cell.dataset.left);
    if (value === null) cell.closest("[data-alone]")?.remove();
    else if (typeof value === "number") cell.textContent = timeLeft(Math.max(0, value - sinceSnapshot));
  });
}

export function historyView(box) {
  const body = el("tbody", {});
  const note = el("p", { class: "status", role: "status" });
  const count = el("span", { text: "" });
  const more = el("button", { type: "button", class: "more", text: "Load more", hidden: "" });
  const filter = el("input", { type: "search", placeholder: "Project name",
                               "aria-label": "Filter by project" });
  const form = el("form", { class: "filters" }, filter,
                  el("button", { type: "submit", text: "Filter" }));
  let next = null;

  async function load(reset) {
    if (reset) { body.replaceChildren(); next = null; }
    const query = new URLSearchParams({ limit: "50" });
    if (next !== null) query.set("before", String(next));
    if (filter.value.trim()) query.set("project", filter.value.trim());
    note.textContent = "Loading";
    try {
      const page = await getJson(`/api/history?${query}`);
      for (const job of page.jobs) {
        body.append(row({ ...job, section: "recent" }, (j) => clock(j.finished_at)));
      }
      next = page.next_before;
      more.hidden = next === null;
      note.textContent = body.children.length ? "" : "No finished jobs match.";
      count.textContent = `${body.children.length} shown${next === null ? "" : ", more below"}`;
    } catch (error) {
      note.textContent = `Could not load the history: ${error.message}`;
    }
  }

  form.addEventListener("submit", (event) => { event.preventDefault(); load(true); });
  more.addEventListener("click", () => load(false));
  load(true);
  fill(box, "History", count, form, el("table", {}, head("finished"), body), note, more);
}
