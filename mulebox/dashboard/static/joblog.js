// A job's live log. Log text is appended as text nodes, never parsed as HTML. A reopened
// stream resumes by byte offset; the stream ends with an `end` event.

import { badge, duration, el } from "./format.js";
import { liveStream } from "./live.js";

const TAIL = 256 * 1024;
const KEEP_CHARS = 1024 * 1024;  // cap the page, not the job: the full log has its own link
const ANSI = /\x1b\[[0-9;?]*[ -/]*[@-~]/g;
const QUIET_AFTER_S = 30;
const WORKING_CPU_PCT = 10;  // the line attendance.py draws for a job doing nothing

export const atBottom = (pre) => pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 24;

// A script may keep its output to itself until the end. Silence and a dead page look alike,
// so a quiet job says how long it has been quiet and whether it is working.
export function quietText(activity) {
  const idle = activity?.output_idle_s;
  if (idle === null || idle === undefined || idle < QUIET_AFTER_S) return "";
  const quiet = `no new output for ${duration(idle)}`;
  const cpu = activity.job_cpu_pct;
  if (cpu === null || cpu === undefined) return quiet;
  if (cpu < WORKING_CPU_PCT) return `${quiet}, and the job is using almost no CPU`;
  return `${quiet}, the job is working (${(cpu / 100).toFixed(1)} cores busy)`;
}

// The way back to the end of the log, for someone who scrolled up while output arrives.
export function latestButton(pre) {
  const button = el("button", { type: "button", class: "log-latest", text: "new output, jump to latest" });
  button.hidden = true;
  button.addEventListener("click", () => {
    pre.scrollTop = pre.scrollHeight;
    button.hidden = true;
  });
  pre.addEventListener("scroll", () => { if (atBottom(pre)) button.hidden = true; });
  return button;
}

// The note beside the log says what the stream is doing until output arrives: a blank box
// must never mean "connected and empty" and "could not connect" at once. A browser allows
// about six open connections per site over plain HTTP, so with several tabs open the
// stream can wait in line; the full log link is a plain request and still works.
export function followLog(pre, stateSlot, note, latest, onEnd) {
  let offset = null;
  const url = () => {
    const address = new URL(`/api/jobs/${encodeURIComponent(pre.dataset.job)}/log`, location.origin);
    if (offset === null) address.searchParams.set("tail", String(TAIL));
    else address.searchParams.set("offset", String(offset));
    return address;
  };
  const started = () => pre.dataset.started !== undefined;
  note.textContent = "connecting to the live log";
  const stop = liveStream(url, {
    state: (event) => stateSlot.replaceChildren(badge(JSON.parse(event.data).state)),
    log: (event) => {
      const { offset: from, next_offset: next, data } = JSON.parse(event.data);
      if (!started()) {
        pre.dataset.started = "1";
        note.textContent = "";
        if (from > 0) pre.append(`[earlier output not shown, see the full log]\n`);
      }
      const follow = atBottom(pre);
      pre.append(data.replace(ANSI, ""));
      pre.normalize();
      const text = pre.firstChild;
      if (text && text.length > KEEP_CHARS) text.deleteData(0, text.length - KEEP_CHARS);
      if (follow) pre.scrollTop = pre.scrollHeight;
      else latest.hidden = false;
      offset = next;
    },
    end: (event) => {
      stop();
      if (!started()) note.textContent = "the job wrote no output";
      onEnd(JSON.parse(event.data));
    },
  }, {
    opened: () => { note.textContent = started() ? "" : "connected, no output yet"; },
    lost: (closed) => {
      note.textContent = closed ? "live log closed, trying again; the full log link works meanwhile"
        : "live log not connected, retrying; the full log link works meanwhile";
    },
  });
  return stop;
}
