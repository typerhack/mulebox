// A GitHub job's log as its steps. The runner's hooks write one line per step as it starts
// (`mulebox: step: <name>`) and a step's output under `--- output of <name>` once the runner
// hands it over, often only when the step ends (runners/diary.py). This reads that text back
// into a list: every step in order, with whatever output it has so far.

export interface CiStep {
  name: string;
  output: string;
}

export interface CiLog {
  steps: CiStep[];
  other: string;   // output the runner did not tie to a step it announced
}

const STEP = "mulebox: step: ";
const OUTPUT = "--- output of ";

export function parseCiLog(text: string): CiLog {
  const steps: CiStep[] = [];
  const byName = new Map<string, CiStep>();
  let other = "";
  let into: CiStep | null = null, loose = false;
  for (const line of text.split("\n")) {
    if (line.startsWith(STEP)) {
      const step = { name: line.slice(STEP.length).trim(), output: "" };
      steps.push(step);
      byName.set(step.name, step);
      into = null;
      loose = false;
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
