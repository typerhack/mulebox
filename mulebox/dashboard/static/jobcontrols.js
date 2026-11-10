// A job's controls on its page: pause or resume, its place in line, boost
// (coordinator/job_control.py).
//
// Each acts at once: none loses work, and each has its way back on the same spot. A short line
// says what is on now, in the words of what it does to this job. Cancelling, which does lose
// work, stays apart and asks twice (canceljob.js).

import { post } from "./access.js";
import { el } from "./format.js";

const WAITING = new Set(["uploading", "queued"]);
const RUNNING = new Set(["starting", "running"]);

function said(job) {
  const running = RUNNING.has(job.state);
  const parts = [];
  if (job.paused) {
    parts.push(running ? "Paused: frozen on its machine, containers too. Resume goes on where it stopped."
                       : "Paused: it keeps its place in line and does not start.");
  }
  if (job.boost) {
    parts.push(running ? "Boosted: it gets the machine's CPU and disk first, and the machine takes no new job until it ends."
                       : "Boosted: first in line, and it gets its machine to itself once it starts.");
  } else if (job.position && WAITING.has(job.state)) {
    parts.push(`#${job.position} in line.`);
  }
  return parts.join(" ");
}

function buttons(job) {
  const waiting = WAITING.has(job.state);
  const list = [job.paused ? ["resume", "Resume", true] : ["pause", "Pause", false]];
  if (waiting && job.position) {
    list.push(["first", "To front", false], ["up", "Up", false], ["down", "Down", false],
              ["last", "To end", false]);
  }
  list.push(job.boost ? ["normal", "End boost", true] : ["boost", "Boost", false]);
  return list;
}

// `{ node, update(job) }`, or null when this page offers no controls for this job.
export function jobControls(job, token) {
  if (!token || job.kind !== "job" || job.cancel_requested
      || !(WAITING.has(job.state) || RUNNING.has(job.state))) {
    return null;
  }
  const node = el("div", { class: "job-controls" });
  const row = el("div", { class: "row-buttons", role: "group", "aria-label": "Job controls" });
  const line = el("p", { class: "controls-said", role: "status" });
  node.append(row, line);
  let shown = job, busy = false;

  async function act(action) {
    busy = true;
    draw(shown);
    try {
      const done = await post(`/api/jobs/${encodeURIComponent(job.job_id)}/control`, { action });
      shown = { ...shown, ...done };
      draw(shown);
    } catch (failure) {
      draw(shown, failure.status ? failure.message : "The dashboard did not answer.");
    } finally {
      busy = false;
      draw(shown);
    }
  }

  function draw(latest, problem = null) {
    row.replaceChildren(...buttons(latest).map(([action, text, on]) => {
      const made = el("button", { type: "button", text, "aria-pressed": on ? "true" : null,
                                  disabled: busy ? "" : null });
      made.addEventListener("click", () => act(action));
      return made;
    }));
    line.textContent = problem ? `Not changed. ${problem}` : said(latest);
    line.classList.toggle("failed", Boolean(problem));
  }

  draw(job);
  return {
    node,
    update(latest) {
      if (!(WAITING.has(latest.state) || RUNNING.has(latest.state)) || latest.cancel_requested) {
        node.remove();
        return;
      }
      shown = latest;
      if (!busy) draw(latest);
    },
  };
}
