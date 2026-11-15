// A running job's verdict, as its card and page word it (docs/design.md, A job that looks
// stuck). The judgement and its sentence are the coordinator's; this only names the verdict,
// gives it a level and picks the one figure for the card: how fast for a slow job, how long
// it has been quiet for the others. Working, an unknown verdict or none shows nothing.

import { downloadView } from "./download";
import { duration } from "./format";
import type { Job } from "./types";

export type LooksLevel = "warning" | "info" | "danger";
export interface LooksView {
  verdict: "slow" | "waiting" | "asking" | "stuck";
  label: string;
  level: LooksLevel;
  figure: string | null;   // "12.0 KB/s", "quiet 5m 10s"
  text: string;            // the server's sentence; "" from a server that sent none
}

const SHOWN: Record<string, [string, LooksLevel]> = {
  slow: ["Slow", "warning"], waiting: ["Waiting on purpose", "info"],
  asking: ["Asks for input", "danger"], stuck: ["Looks stuck", "danger"],
};

// `now` in epoch seconds: the quiet time counts on from `since` between the server's updates,
// and never reads less than the server last said.
export function looksView(job: Pick<Job, "looks" | "doing" | "kind">, now: number): LooksView | null {
  const looks = job.looks, shown = looks && SHOWN[looks.verdict];
  if (!looks || !shown) return null;
  const verdict = looks.verdict as LooksView["verdict"];
  let figure: string | null;
  if (verdict === "slow") {
    figure = downloadView(job.doing?.download, job.kind === "runner")?.speed ?? null;
  } else {
    const told = typeof looks.quiet_s === "number" ? looks.quiet_s : null;
    const counted = typeof looks.since === "number" ? now - looks.since : null;
    const quiet = told === null ? counted : counted === null ? told : Math.max(told, counted);
    figure = quiet === null ? null : `quiet ${duration(quiet)}`;
  }
  const slowLabel = job.doing?.download ? "Slow download" : "Slow";
  return { verdict, label: verdict === "slow" ? slowLabel : shown[0], level: shown[1], figure, text: looks.text?.trim() ?? "" };
}

// The sentence after the bold label, without saying the label twice ("Looks stuck: no output").
export function afterLabel(view: LooksView): string {
  const { label, text } = view;
  if (!text.toLowerCase().startsWith(label.toLowerCase())) return text;
  const rest = text.slice(label.length).replace(/^[:.,]?\s*/, "");
  return rest ? rest[0].toUpperCase() + rest.slice(1) : "";
}
