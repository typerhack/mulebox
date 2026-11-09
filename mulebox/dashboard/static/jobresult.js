// The line that answers "is it over, and how did it go?": an icon and a word at the top of a
// job's page. The icon has its own shape for each kind of end, so colour never carries the
// meaning alone, and the word beside it says it in full.

import { clock, drawIcon, el, ICONS, markOf, stateText, toneOf } from "./format.js";

function detail(job) {
  if (job.state !== "finished") return "";
  const failedIn = job.failed_stage ? `in ${job.failed_stage}` : null;
  const github = job.ci_result?.message?.replace(/\.$/, "") ?? null;  // what GitHub says on the failed step
  const code = job.exit_code === null || job.exit_code === undefined ? null : `exit ${job.exit_code}`;
  return ["Finished", failedIn, github, code, `ended ${clock(job.finished_at)}`]
    .filter(Boolean).join(", ");
}

export function resultLine(job) {
  const state = job.shown_state ?? job.outcome ?? job.state;
  const tone = toneOf(state);
  return el("p", { class: "job-result", "data-tone": tone, role: "status" },
    drawIcon(job.state === "finished" ? markOf(state) : ICONS[tone] ?? ICONS.plain, "result-icon"),
    el("strong", { text: stateText(state) }),
    el("span", { class: "muted", text: detail(job) }));
}
