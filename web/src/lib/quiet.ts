// A script may keep its output to itself until the end. Silence and a dead page look alike,
// so a quiet job says how long it has been quiet and whether it is working.

import { duration } from "./format";
import type { Activity } from "./types";

const QUIET_AFTER_S = 30;
const WORKING_CPU_PCT = 10;  // the line attendance.py draws for a job doing nothing

export function quietText(activity: Activity | null | undefined): string {
  const idle = activity?.output_idle_s;
  if (idle === null || idle === undefined || idle < QUIET_AFTER_S) return "";
  const quiet = `Quiet for ${duration(idle)}.`;
  const cpu = activity?.job_cpu_pct;
  if (cpu === null || cpu === undefined) return quiet;
  if (cpu < WORKING_CPU_PCT) return `${quiet} The job is using almost no CPU.`;
  return `${quiet} The job is using ${(cpu / 100).toFixed(1)} cores, so it is still working.`;
}
