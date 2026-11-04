// Job tables: the live queue and the paged history. Rows come from the server's status
// model (common/status.py), so sections, order and shown state match `mulebox queue`.

import { badge, clock, duration, el, getJson } from "./format.js";

const TITLES = { running: "Running", queued: "Queued", recent: "Recent" };
const EMPTY = { running: "Nothing is running.", queued: "Nothing is waiting.",
                recent: "No finished jobs yet." };

function row(job, last) {
  const name = `${job.project ?? "-"} / ${job.job ?? "-"}`;
  return el("tr", {},
    el("td", {}, el("a", { href: `#/job/${encodeURIComponent(job.job_id)}`, text: name })),
    el("td", { class: "wide", text: job.branch ?? "-" }),
    el("td", {}, badge(job.shown_state ?? job.outcome ?? job.state)),
    el("td", { class: "num", "data-elapsed": job.section === "recent" ? null : "",
               text: duration(job.elapsed_s ?? job.duration_s) }),
    el("td", { class: "wide", text: last(job) }));
}

function table(jobs, heading, last) {
  const head = el("tr", {}, ...["Job", "Branch", "State", "Elapsed", heading].map((text, i) =>
    el("th", { scope: "col", class: i === 1 || i === 4 ? "wide" : null, text })));
  return el("table", {}, el("thead", {}, head),
            el("tbody", {}, ...jobs.map((job) => row(job, last))));
}

export function queueView(snapshot) {
  const root = el("div", {});
  for (const section of ["running", "queued", "recent"]) {
    const jobs = snapshot?.[section] ?? [];
    root.append(el("section", {},
      el("h2", { text: `${TITLES[section]} (${jobs.length})` }),
      jobs.length
        ? table(jobs, section === "queued" ? "Position" : "Worker",
                (j) => String(j.position ?? j.worker ?? "-"))
        : el("p", { class: "muted", text: EMPTY[section] })));
  }
  return root;
}

// Waiting and running rows tick locally between queue events; the server sends the base.
export function tick(root, snapshot, sinceSnapshot) {
  const rows = [...(snapshot?.running ?? []), ...(snapshot?.queued ?? [])];
  const cells = root.querySelectorAll("[data-elapsed]");
  cells.forEach((cell, i) => {
    const base = rows[i]?.elapsed_s;
    if (typeof base === "number") cell.textContent = duration(base + sinceSnapshot);
  });
}

export function historyView() {
  const body = el("tbody", {});
  const note = el("p", { class: "muted", role: "status" });
  const more = el("button", { type: "button", text: "Load more", hidden: "" });
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
        body.append(row({ ...job, section: "recent", shown_state: job.shown_state }, (j) =>
          clock(j.finished_at)));
      }
      next = page.next_before;
      more.hidden = next === null;
      note.textContent = body.children.length ? "" : "No finished jobs match.";
    } catch (error) {
      note.textContent = `Could not load the history: ${error.message}`;
    }
  }

  form.addEventListener("submit", (event) => { event.preventDefault(); load(true); });
  more.addEventListener("click", () => load(false));
  const head = el("tr", {}, ...["Job", "Branch", "State", "Run time", "Finished"].map((text, i) =>
    el("th", { scope: "col", class: i === 1 || i === 4 ? "wide" : null, text })));
  load(true);
  return el("div", {}, el("h2", { text: "History" }), form,
            el("table", {}, el("thead", {}, head), body), note, more);
}
