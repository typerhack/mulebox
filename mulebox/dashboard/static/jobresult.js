// The line that answers "is it over, and how did it go?": an icon and a word at the top of a
// job's page. The icon has its own shape for each kind of end, so colour never carries the
// meaning alone, and the word beside it says it in full.

import { clock, drawIcon, el, stateText, toneOf } from "./format.js";

const ICONS = {
  good: "M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1ZM11.6 4.6 6.9 9.3 4.4 6.8 3 8.2l3.9 3.9 6.1-6.1Z",
  bad: "M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1ZM5.6 4.2 8 6.6l2.4-2.4 1.4 1.4L9.4 8l2.4 2.4-1.4 1.4L8 9.4l-2.4 2.4-1.4-1.4L6.6 8 4.2 5.6Z",
  warn: "M8 1 15.5 15H.5ZM7 6v5h2V6Zm0 6v2h2v-2Z",
  active: "M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1Zm0 2a5 5 0 1 1 0 10A5 5 0 0 1 8 3Zm0 2a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z",
  plain: "M2 2h12v12H2Zm2 2v8h8V4Z",
};

function detail(job) {
  if (job.state !== "finished") return "";
  const failedIn = job.failed_stage ? `in ${job.failed_stage}` : null;
  const code = job.exit_code === null || job.exit_code === undefined ? null : `exit ${job.exit_code}`;
  return ["Finished", failedIn, code, `ended ${clock(job.finished_at)}`]
    .filter(Boolean).join(", ");
}

export function resultLine(job) {
  const state = job.shown_state ?? job.outcome ?? job.state;
  const tone = toneOf(state);
  return el("p", { class: "job-result", "data-tone": tone, role: "status" },
    drawIcon(ICONS[tone] ?? ICONS.plain, "result-icon"),
    el("strong", { text: stateText(state) }),
    el("span", { class: "muted", text: detail(job) }));
}
