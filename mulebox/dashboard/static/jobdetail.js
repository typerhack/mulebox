// One job's detail, with its stages and live log (joblog.js).

import { cancelControl } from "./canceljob.js";
import { badge, clock, duration, el, fill, getJson, safeUrl, questionMark } from "./format.js";
import { followLog, latestButton, quietText } from "./joblog.js";
import { timeline } from "./timeline.js";

const ASK_EVERY_S = 5;  // the clocks tick each second from the last answer

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
  if (!job.question) return null;
  return el("div", { class: "alone-note", "data-alone": job.job_id }, questionMark(job),
    el("p", { text: `The agent was asked if all is well. If the job stays stuck it stops: ${job.question.reason}.` }),
    el("p", {}, "Take it back: ", el("code", { text: `mulebox wait ${job.job_id}` })),
    el("p", {}, "Or end it: ", el("code", { text: `mulebox cancel ${job.job_id}` })));
}

// Render into the work box; returns a function that closes the live log.
export function jobView(box, jobId) {
  let stopLog = null, closed = false, ticking = null, onShow = null;
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
    const info = el("div", {}, facts(job));
    const quiet = el("span", { class: "muted", role: "status", text: quietText(job.activity) });
    let latest = job, ended = false, seconds = 0;
    const draw = () => stages.replaceChildren(timeline(latest) ?? "");
    const ask = () => getJson(`/api/jobs/${encodeURIComponent(jobId)}`)
      .then((fresh) => {
        if (closed || ended) return;
        if (fresh.state !== latest.state) info.replaceChildren(facts(fresh));
        latest = fresh;
        draw();
        quiet.textContent = quietText(fresh.activity);
        control?.update(fresh);
      })
      .catch(() => {});  // the next tick tries again, and the log shows the connection
    ticking = setInterval(() => {
      if (document.hidden) return;
      seconds += 1;
      if (seconds % ASK_EVERY_S === 0) ask();
      else draw();
    }, 1000);
    onShow = () => { if (!document.hidden && !ended) ask(); };
    document.addEventListener("visibilitychange", onShow);
    const pre = el("pre", { class: "log", tabindex: "0", "aria-label": "Job log",
                            "data-job": jobId });
    const link = el("a", { href: `/api/jobs/${encodeURIComponent(jobId)}/log.txt`,
                           text: "Full log as text" });
    const run = safeUrl(job.run_url);
    const note = el("span", { class: "muted", role: "status" });
    const latestOut = latestButton(pre);
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
      el("div", { class: "log-head" }, el("span", { text: "log" }), note, quiet, latestOut, link),
      pre,
    ].filter(Boolean);
    fill(box, `Job ${job.project ?? "-"} / ${job.job ?? "-"}`, stateSlot, ...parts);
    stopLog = followLog(pre, stateSlot, note, latestOut, (final) => {
      ended = true;
      stateSlot.replaceChildren(badge(final.shown_state ?? final.outcome ?? final.state));
      info.replaceChildren(facts(final));
      clearInterval(ticking);
      stages.replaceChildren(timeline(final) ?? "");
      quiet.textContent = "";
      box.querySelector("[data-alone]")?.remove();
      control?.update(final);
    });
  }).catch((error) => {
    if (!closed) {
      fill(box, "Job", null, back(),
           el("p", { text: `Could not load this job: ${error.message}` }));
    }
  });
  return () => {
    closed = true;
    clearInterval(ticking);
    stopLog?.();
    if (onShow) document.removeEventListener("visibilitychange", onShow);
  };
}
