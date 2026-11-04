// Job views: the live queue as one process-list style table (running, queued, recent) and
// the paged history. Rows come from the server's status model (common/status.py), so
// sections, order and shown state match `mulebox queue`.

import { badge, clock, duration, el, fill, getJson } from "./format.js";

const TITLES = { running: "running", queued: "queued", recent: "recent" };
const EMPTY = { running: "nothing is running", queued: "nothing is waiting",
                recent: "no finished jobs yet" };

const name = (job) => `${job.project ?? "-"} / ${job.job ?? "-"}`;
const link = (job) => el("a", { href: `#/job/${encodeURIComponent(job.job_id)}`, text: name(job) });
const state = (job) => badge(job.shown_state ?? job.outcome ?? job.state);

function where(job) {
  if (job.section === "queued") return job.position ? `queue #${job.position}` : "queue";
  return job.worker ?? "-";
}

// Columns: state, job (with branch), machine, time. Running rows are the brightest.
function row(job, last) {
  const ticking = job.section === "recent" ? null : "";
  return el("tr", { class: job.section === "running" ? "running" : null },
    el("td", { class: "state" }, state(job)),
    el("td", {}, link(job), el("span", { class: "branch", text: job.branch ?? "-" })),
    el("td", { class: "wide", text: last(job) }),
    el("td", { class: "num", "data-elapsed": ticking,
               text: duration(job.elapsed_s ?? job.duration_s) }));
}

function head(last) {
  return el("thead", {}, el("tr", {}, ...[["state", "state"], ["job", null], [last, "wide"],
                                           ["time", null]].map(([text, cls]) =>
    el("th", { scope: "col", class: cls, text }))));
}

function group(section, count) {
  return el("tr", { class: "group" }, el("th", { colspan: "4" }, TITLES[section],
    el("span", { class: "count", text: String(count) })));
}

export function queueView(box, snapshot) {
  const body = el("tbody", {});
  const counts = {};
  for (const section of ["running", "queued", "recent"]) {
    const jobs = snapshot?.[section] ?? [];
    counts[section] = jobs.length;
    body.append(group(section, jobs.length));
    if (!jobs.length) {
      body.append(el("tr", {}, el("td", { colspan: "4", class: "empty", text: EMPTY[section] })));
    }
    for (const job of jobs) body.append(row(job, where));
  }
  const note = snapshot ? `${counts.running} running, ${counts.queued} queued` : "waiting for data";
  fill(box, "Jobs", note, el("table", {}, head("machine"), body));
}

// Waiting and running rows tick locally between queue events; the server sends the base.
// Document order is running rows first, then queued rows, matching the snapshot's order.
export function tick(root, snapshot, sinceSnapshot) {
  const rows = [...(snapshot?.running ?? []), ...(snapshot?.queued ?? [])];
  const cells = root.querySelectorAll("[data-elapsed]");
  cells.forEach((cell, i) => {
    const base = rows[i]?.elapsed_s;
    if (typeof base === "number") cell.textContent = duration(base + sinceSnapshot);
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
