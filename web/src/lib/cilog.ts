// A GitHub job's log as its steps. The worker writes one line as each step starts
// (`mulebox: step at <time>: <name>`) and one as it ends (`mulebox: step passed at <time>: <name>`,
// or failed, cancelled, skipped), with the times of the runner's own diary, and a step's output
// under `--- output of <name>` once the runner hands it over, often only when the step ends
// (runners/live_log.py). Logs written before the times read `mulebox: step: <name>` and, for a
// failed step only, `mulebox: step failed: <name>`. This reads that text back into a list: every
// step in order, with its times, its result once it ended, and whatever output it has so far.

export type StepResult = "passed" | "failed" | "cancelled" | "skipped";

export interface CiStep {
  name: string;
  output: string;
  startedAt: number | null;   // epoch seconds, from the runner's diary
  endedAt: number | null;
  result: StepResult | null;  // null while it runs, or when an older log does not say
}

export interface CiLog {
  steps: CiStep[];
  other: string;   // output the runner did not tie to a step it announced
}

const STARTED = /^mulebox: step(?: at (\S+))?: (.*)$/;
const ENDED = /^mulebox: step (passed|failed|cancelled|skipped)(?: at (\S+))?: (.*)$/;
const OUTPUT = "--- output of ";

function seconds(at: string | undefined): number | null {
  if (!at) return null;
  const ms = Date.parse(at);
  return Number.isNaN(ms) ? null : ms / 1000;
}

export function parseCiLog(text: string): CiLog {
  const steps: CiStep[] = [];
  const byName = new Map<string, CiStep>();
  let other = "";
  let into: CiStep | null = null, loose = false;
  for (const line of text.split("\n")) {
    const started = STARTED.exec(line);
    const ended = started ? null : ENDED.exec(line);
    if (started) {
      const step: CiStep = { name: started[2].trim(), output: "", startedAt: seconds(started[1]),
                             endedAt: null, result: null };
      steps.push(step);
      byName.set(step.name, step);
      into = null;
      loose = false;
    } else if (ended) {
      const step = byName.get(ended[3].trim());
      if (step) {
        step.result = ended[1] as StepResult;
        step.endedAt = seconds(ended[2]);
      }
    } else if (line.startsWith(OUTPUT)) {
      into = byName.get(line.slice(OUTPUT.length).trim()) ?? null;
      loose = into === null;
      if (loose) other += `${line}\n`;
    } else if (into) {
      into.output += `${line}\n`;
    } else if (loose || line.trim()) {
      other += `${line}\n`;
    }
  }
  return { steps, other: other.trimEnd() };
}

// How long a step took, or has run so far; null when its start is not known.
export function stepSeconds(step: CiStep, now: number): number | null {
  if (step.startedAt === null) return null;
  const end = step.endedAt ?? (step.result ? null : now);
  return end === null ? null : Math.max(0, end - step.startedAt);
}
