// The cancel button on a job's page; on a GitHub run's page it asks GitHub to cancel the run. The server gives a token only where its controls are on
// (interfaces-m2.md, Controls), so without one nothing here exists.
//
// A cancel is asked twice, in the page rather than a browser dialog. The first click puts
// "Keep job" under the pointer, so a double click keeps the job.

import { post } from "./access.js";
import { el, safeUrl } from "./format.js";

const CANCELLABLE = new Set(["uploading", "queued", "starting", "running"]);

// `{ node, update(job) }`, or null when this page offers no cancel for this job.
export function cancelControl(job, token) {
  const upgradeWaits = job.kind === "upgrade" && (job.state === "queued" || job.state === "uploading");
  const run = job.kind === "runner" && safeUrl(job.run_url);  // GitHub is asked (runners/cancel_run.py)
  if (!token || !(job.kind === "job" || upgradeWaits || run) || !CANCELLABLE.has(job.state)
      || job.cancel_requested) {
    return null;
  }
  const words = run
    ? { start: "Cancel on GitHub", sure: "Yes, cancel the run", keep: "Keep run",
        note: "GitHub is asked to cancel the run; the slot frees when the runner stops.",
        sending: "Asking GitHub", done: "GitHub is cancelling the run." }
    : { start: "Cancel job", sure: "Yes, cancel job", keep: "Keep job",
        note: "This stops the job for whoever is waiting on it.", sending: "Cancelling",
        done: "Cancel requested. The job is stopping." };
  const node = el("div", { class: "job-cancel" });
  let view = "idle";

  const button = (text, tone, onClick) => {
    const made = el("button", { type: "button", class: tone, text });
    made.addEventListener("click", onClick);
    return made;
  };
  const show = (name, ...parts) => {
    view = name;
    node.replaceChildren(...parts);
  };
  const requested = () => show("requested", el("p", { role: "status",
    text: words.done }));
  const idle = (problem) => {
    const start = button(words.start, "danger", armed);
    show("idle", problem ?? "", start);
    return start;
  };

  function armed() {
    const keep = button(words.keep, "", () => idle().focus());
    const yes = button(words.sure, "danger sure", () => send());
    const note = el("p", { text: words.note });
    show("armed", note, yes, keep);
    node.onkeydown = (event) => {
      if (event.key === "Escape" && view === "armed") idle().focus();
    };
    keep.focus();
  }

  async function send() {
    show("sending", el("p", { role: "status", text: words.sending }));
    try {
      const done = await post(`/api/jobs/${encodeURIComponent(job.job_id)}/cancel`);
      if (done.state === "finished") node.remove();
      else requested();
    } catch (failure) {
      if (failure.status === 401) {
        show("idle", el("p", { class: "failed", role: "alert" }, "Your sign-in has ended. ",
                        el("a", { href: "/login", text: "Sign in again" })));
      } else if (failure.status === 409) {  // the server knows better than this page by now
        show("gone", el("p", { role: "status", text: failure.message }));
      } else {
        const reason = failure.status ? failure.message : "The dashboard did not answer.";
        idle(el("p", { class: "failed", role: "alert", text: `Not cancelled. ${reason}` }));
      }
    }
  }

  idle();
  return {
    node,
    update(latest) {
      if (latest.state === "finished" || latest.state === "cleaning") node.remove();
      else if (latest.cancel_requested && view !== "requested") requested();
    },
  };
}
