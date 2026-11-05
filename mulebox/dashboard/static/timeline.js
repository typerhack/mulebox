// A job's stages as a waterfall: each bar starts where the stage started and is as long as it
// took, on one scale, so where the time went shows at a glance. The tick is what earlier passed
// runs usually took. That is a length from the past, so nothing here says how far along a job is.

import { bytes, duration, el } from "./format.js";

const percent = (part, whole) => `${(part / whole * 100).toFixed(2)}%`;

function bar(from, length, scale, tone) {
  return el("span", { class: "span", "data-tone": tone,
                      style: `left:${percent(from, scale)};width:${percent(length, scale)}` });
}

function track(label, spanNode, usualAt, scale) {
  const tick = usualAt ? el("span", { class: "tick", title: `usual ${duration(usualAt)}`,
                                      style: `left:${percent(usualAt, scale)}` }) : null;
  return el("span", { class: "lane", role: "img", "aria-label": label }, spanNode, tick);
}

function row(name, took, track_, usual, extra) {
  return el("div", { class: "stage-row" },
    el("span", { class: "stage-name", text: name }), track_,
    el("span", { class: "value", text: took }),
    el("span", { class: "stage-usual", text: usual === null ? "" : `usual ${duration(usual)}` }),
    extra ?? null);
}

function stageRow(step, base, scale, now, usual, isOpen) {
  const end = step.finished_at ?? (isOpen ? now : step.started_at);
  const seconds = Math.max(0, end - step.started_at);
  const failed = step.finished_at !== null && (step.exit_code ?? 0) !== 0;
  const tone = isOpen ? "open" : failed ? "failed" : "done";
  const took = `${duration(seconds)}${isOpen ? " so far" : ""}${failed ? " failed" : ""}`;
  const typical = usual?.stages?.[step.stage] ?? null;
  const from = step.started_at - base;
  const line = failed && step.failing_line
    ? el("code", { class: "failing-line", text: step.failing_line }) : null;
  const fetched = step.bytes_downloaded
    ? el("span", { class: "stage-fetched", text: `${bytes(step.bytes_downloaded)} fetched` }) : null;
  return row(step.stage, took, track(`${step.stage}: ${took}`, bar(from, seconds, scale, tone),
                                     typical === null ? null : from + typical, scale),
             typical, line ?? fetched);
}

export function timeline(job, now = Date.now() / 1000) {
  const steps = job.steps ?? [];
  if (!steps.length) return null;
  const last = steps[steps.length - 1];
  const running = job.state !== "finished" && last.finished_at === null;
  const base = steps[0].started_at;
  const end = running ? now : Math.max(...steps.map((s) => s.finished_at ?? s.started_at));
  const elapsed = Math.max(0, end - base);
  const usual = job.usual ?? null;
  const scale = Math.max(elapsed, usual?.job_s ?? 0, 1);
  const took = `${duration(elapsed)}${running ? " so far" : ""}`;
  const whole = row("whole job", took,
    track(`whole job: ${took}`, bar(0, elapsed, scale, running ? "open" : "done"),
          usual?.job_s ?? null, scale), usual?.job_s ?? null);
  return el("div", { class: "timeline" }, whole,
    ...steps.map((step) => stageRow(step, base, scale, now, usual,
                                    running && step === last)));
}
