// A job's stages as a waterfall: each bar starts where the stage started and is as long as it
// took, on one scale, so where the time went shows at a glance. The tick is where earlier
// passed runs usually ended the stage. That is a length from the past, so nothing here says
// how far along a job is.

import { bytes, duration, roughly } from "./format";
import type { JobDetail } from "./types";

export interface StageRow {
  name: string;
  state: "passed" | "failed" | "running" | "cancelled" | "released";
  from: number;            // seconds after the first stage started
  length: number;
  usualAt: number | null;  // where the stage usually ends, on the same scale
  took: string;
  tip: string;
  extra: { text: string; code: boolean } | null;  // the failing line, or what was fetched
}

export interface Timeline {
  rows: StageRow[];
  scale: number;       // seconds the track spans
  elapsed: number;
  running: boolean;
  usual: number | null;
  axis: string[];      // five labels, 0 to the scale
}

export function timeline(job: JobDetail, now: number): Timeline | null {
  const steps = job.steps ?? [];
  if (!steps.length) return null;
  const last = steps[steps.length - 1];
  const running = job.state !== "finished" && last.finished_at === null;
  const base = steps[0].started_at;
  const end = running ? now : Math.max(...steps.map((s) => s.finished_at ?? s.started_at));
  const elapsed = Math.max(0, end - base);
  const usual = job.usual?.job_s ?? null;
  const scale = Math.max(elapsed, usual ?? 0, 1);
  const rows = steps.map((step): StageRow => {
    const open = running && step === last;
    const failed = step.stage === job.failed_stage;
    const length = Math.max(0, (step.finished_at ?? (open ? now : step.started_at)) - step.started_at);
    const typical = job.usual?.stages?.[step.stage] ?? null;
    const took = `${duration(length)}${open ? " so far" : ""}`;
    const from = step.started_at - base;
    const extra = failed && step.failing_line ? { text: step.failing_line, code: true }
      : step.bytes_downloaded ? { text: `${bytes(step.bytes_downloaded)} fetched`, code: false } : null;
    return {
      name: step.stage, state: open ? "running" : failed ? "failed" : "passed", from, length,
      usualAt: typical === null ? null : Math.min(from + typical, scale), took, extra,
      tip: `${step.stage}: ${took}${failed ? ", failed" : ""}${typical === null ? "" : `, usually ${duration(typical)}`}`,
    };
  });
  const axis = [0, 0.25, 0.5, 0.75, 1].map((share) => (share ? roughly(scale * share) : "0"));
  return { rows, scale, elapsed, running, usual, axis };
}
