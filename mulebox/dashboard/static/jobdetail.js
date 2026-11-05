// One job's detail and live log. Log text is appended as text nodes, never parsed as HTML.
// Reconnects resume by byte offset (the event id); the stream ends with an `end` event.

import { cancelControl } from "./canceljob.js";
import { badge, clock, duration, el, fill, getJson, safeUrl, unattendedMark } from "./format.js";
import { timeline } from "./timeline.js";

const TAIL = 256 * 1024;
const KEEP_CHARS = 1024 * 1024;  // cap the page, not the job: the full log has its own link
const ANSI = /\x1b\[[0-9;?]*[ -/]*[@-~]/g;
const STAGES_EVERY_MS = 5000;

function facts(job) {
  const rows = [
    ["Project", job.project], ["Job", job.job], ["Branch", job.branch],
    ["Client", job.client], ["Worker", job.worker], ["Exit code", job.exit_code],
    ["Created", clock(job.created_at)], ["Started", clock(job.started_at)],
    ["Finished", clock(job.finished_at)],
    ["Run time", job.duration_s === null ? null : duration(job.duration_s)],
    ["Commit", job.base_commit?.slice(0, 12)], ["Check-in every", job.timeout_min && `${job.timeout_min} min`],
    ["Stopped", job.stop_text],
    ["Toolchain", typeof job.toolchain === "string" ? job.toolchain : null],
    ["Command", job.command], ["Job id", job.job_id],
  ].filter(([, value]) => value !== null && value !== undefined && value !== "");
  return el("dl", { class: "facts" }, ...rows.flatMap(([name, value]) => [
    el("dt", { text: name }), el("dd", { text: String(value) }),
  ]));
}

// Nobody is watching: what happens, and the two ways out, which work whatever this page offers.
function aloneNote(job) {
  if (!job.unattended) return null;
  return el("div", { class: "alone-note", "data-alone": job.job_id }, unattendedMark(job),
    el("p", { text: `It stops by itself: ${job.unattended.reason}.` }),
    el("p", {}, "Take it back: ", el("code", { text: `mulebox wait ${job.job_id}` })),
    el("p", {}, "Or end it: ", el("code", { text: `mulebox cancel ${job.job_id}` })));
}

// The note beside the log says what the stream is doing until output arrives: a blank box
// must never mean "connected and empty" and "could not connect" at once. A browser allows
// about six open connections per site over plain HTTP, so with several tabs open the
// stream can wait in line; the full log link is a plain request and still works.
function follow(pre, stateSlot, note, onEnd) {
  const url = new URL(`/api/jobs/${encodeURIComponent(pre.dataset.job)}/log`, location.origin);
  url.searchParams.set("tail", String(TAIL));
  const source = new EventSource(url);
  note.textContent = "connecting to the live log";
  source.onopen = () => {
    if (pre.dataset.started === undefined) note.textContent = "connected, no output yet";
  };
  source.onerror = () => {
    note.textContent = source.readyState === EventSource.CLOSED
      ? "live log closed; reload the page, or open the full log"
      : "live log not connected, retrying; the full log link works meanwhile";
  };
  source.addEventListener("state", (event) => {
    stateSlot.replaceChildren(badge(JSON.parse(event.data).state));
  });
  source.addEventListener("log", (event) => {
    const { offset, data } = JSON.parse(event.data);
    if (pre.dataset.started === undefined) {
      pre.dataset.started = "1";
      note.textContent = "";
      if (offset > 0) pre.append(`[earlier output not shown, see the full log]\n`);
    }
    const stuck = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 24;
    pre.append(data.replace(ANSI, ""));
    pre.normalize();
    const text = pre.firstChild;
    if (text && text.length > KEEP_CHARS) text.deleteData(0, text.length - KEEP_CHARS);
    if (stuck) pre.scrollTop = pre.scrollHeight;
  });
  source.addEventListener("end", (event) => {
    source.close();
    if (pre.dataset.started === undefined) note.textContent = "the job wrote no output";
    onEnd(JSON.parse(event.data));
  });
  return source;
}

// Render into the work box; returns a function that closes the live log.
export function jobView(box, jobId) {
  let source = null, closed = false, ticking = null;
  const back = () => el("p", { class: "crumb" }, el("a", { href: "#/", text: "Back to the queue" }));
  fill(box, "Job", null, back(), el("p", { class: "muted", role: "status", text: "Loading" }));
  Promise.all([
    getJson(`/api/jobs/${encodeURIComponent(jobId)}`),
    getJson("/api/session").catch(() => null),  // no answer: no button, the rest still works
  ]).then(([job, access]) => {
    if (closed) return;
    const control = cancelControl(job, access?.cancel_token);
    const stateSlot = el("span", {}, badge(job.shown_state ?? job.outcome ?? job.state));
    const stages = el("div", {}, timeline(job));
    ticking = setInterval(() => {
      if (document.hidden) return;
      getJson(`/api/jobs/${encodeURIComponent(jobId)}`)
        .then((latest) => {
          if (closed) return;
          stages.replaceChildren(timeline(latest) ?? "");
          control?.update(latest);
        })
        .catch(() => {});  // the next tick tries again, and the log shows the connection
    }, STAGES_EVERY_MS);
    const info = el("div", {}, facts(job));
    const pre = el("pre", { class: "log", tabindex: "0", "aria-label": "Job log",
                            "data-job": jobId });
    const link = el("a", { href: `/api/jobs/${encodeURIComponent(jobId)}/log.txt`,
                           text: "Full log as text" });
    const run = safeUrl(job.run_url);
    const note = el("span", { class: "muted", role: "status" });
    const parts = [
      control ? el("div", { class: "job-bar" }, back(), control.node) : back(),
      job.kind === "runner"
        ? el("p", { class: "muted note-text", text: "This entry only held a build slot for a " +
                    "GitHub runner. The job's result and log are on GitHub." })
        : null,
      run ? el("p", {}, el("a", { href: run, rel: "noreferrer", text: "Open the GitHub run" })) : null,
      aloneNote(job),
      stages,
      info,
      el("div", { class: "log-head" }, el("span", { text: "log" }), note, link),
      pre,
    ].filter(Boolean);
    fill(box, `Job ${job.project ?? "-"} / ${job.job ?? "-"}`, stateSlot, ...parts);
    source = follow(pre, stateSlot, note, (final) => {
      stateSlot.replaceChildren(badge(final.shown_state ?? final.outcome ?? final.state));
      info.replaceChildren(facts(final));
      clearInterval(ticking);
      stages.replaceChildren(timeline(final) ?? "");
      box.querySelector("[data-alone]")?.remove();
      control?.update(final);
    });
  }).catch((error) => {
    if (!closed) {
      fill(box, "Job", null, back(),
           el("p", { text: `Could not load this job: ${error.message}` }));
    }
  });
  return () => { closed = true; clearInterval(ticking); source?.close(); };
}
