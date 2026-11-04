// One job's detail and live log. Log text is appended as text nodes, never parsed as HTML.
// Reconnects resume by byte offset (the event id); the stream ends with an `end` event.

import { badge, clock, duration, el, getJson, safeUrl } from "./format.js";

const TAIL = 256 * 1024;
const KEEP_CHARS = 1024 * 1024;  // cap the page, not the job: the full log has its own link
const ANSI = /\x1b\[[0-9;?]*[ -/]*[@-~]/g;

function facts(job) {
  const rows = [
    ["Project", job.project], ["Job", job.job], ["Branch", job.branch],
    ["Client", job.client], ["Worker", job.worker], ["Exit code", job.exit_code],
    ["Created", clock(job.created_at)], ["Started", clock(job.started_at)],
    ["Finished", clock(job.finished_at)],
    ["Run time", job.duration_s === null ? null : duration(job.duration_s)],
    ["Commit", job.base_commit?.slice(0, 12)], ["Timeout", job.timeout_min && `${job.timeout_min} min`],
    ["Toolchain", typeof job.toolchain === "string" ? job.toolchain : null],
    ["Command", job.command],
  ].filter(([, value]) => value !== null && value !== undefined && value !== "");
  return el("dl", { class: "facts" }, ...rows.flatMap(([name, value]) => [
    el("dt", { text: name }), el("dd", { text: String(value) }),
  ]));
}

function follow(pre, stateSlot, onEnd) {
  const url = new URL(`/api/jobs/${encodeURIComponent(pre.dataset.job)}/log`, location.origin);
  url.searchParams.set("tail", String(TAIL));
  const source = new EventSource(url);
  source.addEventListener("state", (event) => {
    stateSlot.replaceChildren(badge(JSON.parse(event.data).state));
  });
  source.addEventListener("log", (event) => {
    const { offset, data } = JSON.parse(event.data);
    if (pre.dataset.started === undefined) {
      pre.dataset.started = "1";
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
    onEnd(JSON.parse(event.data));
  });
  return source;
}

// Render into `root`; returns a function that closes the live log.
export function jobView(root, jobId) {
  let source = null, closed = false;
  root.replaceChildren(el("p", { class: "muted", role: "status", text: "Loading" }));
  getJson(`/api/jobs/${encodeURIComponent(jobId)}`).then((job) => {
    if (closed) return;
    const stateSlot = el("span", {}, badge(job.shown_state ?? job.outcome ?? job.state));
    const info = el("div", {}, facts(job));
    const pre = el("pre", { class: "log", tabindex: "0", "aria-label": "Job log",
                            "data-job": jobId });
    const link = el("a", { href: `/api/jobs/${encodeURIComponent(jobId)}/log.txt`,
                           text: "Full log as text" });
    const run = safeUrl(job.run_url);
    root.replaceChildren(
      el("p", {}, el("a", { href: "#/", text: "Back to the queue" })),
      el("h2", { text: `${job.project ?? "-"} / ${job.job ?? "-"}` }),
      el("p", {}, stateSlot),
      job.kind === "runner"
        ? el("p", { class: "muted", text: "This entry only held a build slot for a GitHub " +
                    "runner. The job's result and log are on GitHub." })
        : null,
      run ? el("p", {}, el("a", { href: run, rel: "noreferrer", text: "Open the GitHub run" })) : null,
      info, el("h3", { text: "Log" }), pre, el("p", {}, link));
    source = follow(pre, stateSlot, (final) => {
      stateSlot.replaceChildren(badge(final.shown_state ?? final.outcome ?? final.state));
      info.replaceChildren(facts(final));
    });
  }).catch((error) => {
    if (!closed) {
      root.replaceChildren(el("p", { text: `Could not load this job: ${error.message}` }),
                           el("p", {}, el("a", { href: "#/", text: "Back to the queue" })));
    }
  });
  return () => { closed = true; source?.close(); };
}
