// What a job in a slot is doing now, on its card: a word for its stage (a CI job's GitHub
// step) and a meter of the cores the job alone uses, from the worker's last reading
// (dashboard/data.py, `doing`). The meter pulses only while the job really uses CPU, so the
// busy card stands out and a quiet one stays still. A download is told by its stage: per-job
// network is not measured, so nothing here claims bytes.

import { el, meter } from "./format.js";

export const BUSY_PCT = 50;  // of one core

const WORDS = {
  toolchain: "installing tools", prepare: "preparing", environment: "preparing",
  images: "fetching images", services: "starting services", install: "installing packages",
  setup: "setting up", command: "running its command", cleanup: "cleaning up",
};

export function doingWord(doing) {
  if (doing?.step) return doing.step;
  if (doing?.stage) return WORDS[doing.stage] ?? doing.stage;
  return "working";
}

export const coresText = (pct) => (typeof pct === "number" ? `${(pct / 100).toFixed(1)} cores` : "measuring");

export function doingLine(job, cores) {
  const doing = job.doing;
  if (!doing) return null;
  const pct = doing.cpu_pct;
  const busy = typeof pct === "number" && pct >= BUSY_PCT;
  const word = doingWord(doing);
  const value = coresText(pct);
  const parts = [el("span", { class: "doing-word", title: word, text: word })];
  if (typeof pct === "number" && cores) {
    const bar = meter({ "aria-label": `${word}: ${value} of ${cores}` });
    bar.set(pct / 100 / cores);
    parts.push(bar.node);
  }
  parts.push(el("span", { class: "doing-cores num", text: value }));
  return el("p", { class: "doing", "data-busy": busy ? "1" : null, role: "status" }, ...parts);
}
