// Moving a waiting job in line from the Queue tab: to the front, one up, one down, to the end
// (`mulebox first|up|down|last`, coordinator/job_control.py). Positions are the real line's,
// across every lane, so "up" passes the job just ahead of it in the whole queue. The queue
// event that follows redraws the list; until then the row says it is moving.

import { actionToken, post } from "./access.js";
import { drawIcon, el } from "./format.js";

// Outlines in the button's own colour (style.css, .moves).
const MOVES = [
  ["first", "Move to the front of the line", "M3.5 2.75h9M8 13.25v-7.5M4.75 9 8 5.75 11.25 9"],
  ["up", "Move one place up", "M8 13V3.5M4.75 6.75 8 3.5l3.25 3.25"],
  ["down", "Move one place down", "M8 3v9.5M4.75 9.25 8 12.5l3.25-3.25"],
  ["last", "Move to the end of the line", "M3.5 13.25h9M8 2.75v7.5M4.75 7 8 10.25 11.25 7"],
];

let token = null;  // the buttons show from the first render after the page has it
actionToken().then((given) => { token = given; });
const pending = new Map();  // job -> "moving" or a refusal, until the next queue event shows it

async function move(job, action) {
  pending.set(job.job_id, { position: job.position, text: "moving" });
  try {
    await post(`/api/jobs/${encodeURIComponent(job.job_id)}/control`, { action });
  } catch (failure) {
    pending.set(job.job_id, { position: job.position, failed: true,
      text: `Not moved. ${failure.status ? failure.message : "The dashboard did not answer."}` });
  }
}

// The four buttons for a waiting job at `job.position` of `total`, or null when this page
// offers no controls or the job has no place in line yet.
export function moveButtons(job, total) {
  if (!token || !["job", "upgrade"].includes(job.kind) || !job.position || job.cancel_requested) {
    return null;
  }
  const note = pending.get(job.job_id);
  if (note && !note.failed && note.position !== job.position) pending.delete(job.job_id);
  const left = pending.get(job.job_id);
  const blocked = { first: job.position === 1, up: job.position === 1,
                    down: job.position >= total, last: job.position >= total };
  const group = el("span", { class: "moves", role: "group", "aria-label": `Move ${job.job_id} in line` },
    ...MOVES.map(([action, label, shape]) => {
      const made = el("button", { type: "button", title: label, "aria-label": label,
                                  disabled: blocked[action] || left?.text === "moving" ? "" : null },
                      drawIcon(shape, "move-icon"));
      made.addEventListener("click", () => move(job, action));
      return made;
    }));
  if (!left) return group;
  return el("span", { class: "moves-wrap" }, group,
            el("span", { class: left.failed ? "failed" : "muted", role: "status", text: left.text }));
}
