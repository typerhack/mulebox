// The tests a finished job ran, as its row and its page word them (design-system/tests/,
// option B, the user's pick; docs/design.md, Proof that tests ran). The count and the verdict
// are the coordinator's (coordinator/test_proof.py); this only puts them into words: the quiet
// number, the line under a job's name when the count failed it or was let through, the strip's
// sentence, and each runner beside the pass it was compared with.

import { plural } from "./format";
import type { Job, Tests } from "./types";

export type TestsTone = "failed" | "warn" | "plain";
export type TestsKind = "ok" | "more" | "fewer" | "zero" | "allowed" | "missing";
export type RunnerMark = "zero" | "fewer" | "more" | null;

export interface RunnerRow {
  name: string;
  ran: number;
  skipped: number;
  was: number | null;      // what the compared pass ran; null when it had no count from it
  mark: RunnerMark;
  tone: TestsTone;
  text: string;            // beside the last pass, "" when there is nothing to compare with
}

export interface TestsView {
  kind: TestsKind;
  tone: TestsTone;
  counted: boolean;        // a runner's summary was read: the row shows the number
  ran: number;
  skipped: number;
  delta: string | null;    // "+12", only when the suite grew
  line: { bold: string; rest: string } | null;      // under the job's name on a row
  strip: { title: string; text: string } | null;    // on the job's page
  reason: string | null;   // the agent's own words for an allowed drop
  rows: RunnerRow[];
  first: string[];         // the runners whose summary to go to first: those that fell short
  summaries: string[];     // their summary lines as the log has them, those of `first` first
  compared: NonNullable<Tests["compared"]> | null;
  passed: boolean;         // the command passed: only a pass is held to the last pass
}

export const FEWER_COMMAND = "mulebox check --fewer-tests \"<reason>\"";
const count = (n: number) => plural(n, "test");
const list = (names: string[]) => (names.length < 2 ? names.join("")
  : `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`);

// The lines the coordinator counted (common/test_counts.py), the named runners' first: the page
// finds them in the log by their text, so no second set of patterns is kept here.
function summaryLines(tests: Tests, first: string[]): string[] {
  const lines = tests.lines ?? {};
  const order = [...first, ...Object.keys(lines).filter((name) => !first.includes(name))];
  return [...new Set(order.flatMap((name) => lines[name] ?? []))];
}

function runnerRows(tests: Tests, kind: TestsKind): RunnerRow[] {
  const now = tests.runners ?? {}, before = tests.compared?.runners ?? null;
  const names = [...Object.keys(now), ...Object.keys(before ?? {}).filter((name) => !(name in now))];
  return names.map((name) => {
    const ran = now[name]?.ran ?? 0, skipped = now[name]?.skipped ?? 0;
    const was = before && name in before ? before[name]?.ran ?? 0 : null;
    const diff = was === null ? null : ran - was;
    const last = was === null ? "" : ` The last pass ran ${was}.`;
    const [mark, text]: [RunnerMark, string] = !(name in now) ? ["zero", `No summary from it in this run.${last}`]
      : ran === 0 ? ["zero", `No test ran.${last}`]
      : diff === null ? [null, before ? "The last pass had no count from it." : ""]
      : diff < 0 ? ["fewer", `${-diff} fewer than the last pass, which ran ${was}.`]
      : diff > 0 ? ["more", `${diff} more than the last pass, which ran ${was}.`]
      : [null, "The same as the last pass."];
    const tone: TestsTone = mark === "zero" || (mark === "fewer" && kind === "fewer") ? "failed"
      : mark === "fewer" ? "warn" : "plain";
    return { name, ran, skipped, was, mark, tone, text };
  });
}

// Null for a job that is not finished, was not counted, or printed no summary (a lint): nothing
// about tests is shown then.
export function testsView(job: Pick<Job, "tests" | "state">): TestsView | null {
  const tests = job.tests;
  if (job.state !== "finished" || !tests || !tests.runners) return null;
  const counted = Object.keys(tests.runners).length > 0;
  const verdict = tests.verdict;
  if (!counted && verdict !== "missing") return null;
  const ran = tests.ran ?? 0, skipped = tests.skipped ?? 0;
  const compared = tests.compared ?? null;
  const base: TestsKind = verdict === "zero" || verdict === "fewer" || verdict === "allowed" || verdict === "missing" ? verdict : "ok";
  const rows = runnerRows(tests, base);
  const grew = rows.reduce((sum, row) => sum + (row.was === null ? (compared ? row.ran : 0) : row.ran - row.was), 0);
  const kind: TestsKind = base === "ok" && verdict === "ok" && compared && grew > 0 ? "more" : base;
  const drops = rows.filter((row) => row.was !== null && row.ran < row.was);
  const less = drops.reduce((sum, row) => sum + (row.was as number) - row.ran, 0);
  const none = rows.filter((row) => row.mark === "zero");
  const reason = tests.fewer?.trim() || null;
  const where = compared?.branch ? ` on ${compared.branch}` : "";
  const fell = drops.map((row) => `${row.name} ran ${count(row.ran)} and the last pass${where} ran ${row.was}`).join("; ");
  const quoted = reason ? `“${reason}”` : "";

  let line: TestsView["line"] = null, strip: TestsView["strip"] = null;
  if (kind === "fewer") {
    line = { bold: `${less} fewer ${less === 1 ? "test" : "tests"}`,
             rest: ` than the last pass: ${drops.map((row) => `${row.name} ran ${row.ran}, was ${row.was}`).join("; ")}` };
    strip = { title: "Fewer tests than the last pass.", text: `The command passed, but ${fell}.` };
  } else if (kind === "zero") {
    const all = none.reduce((sum, row) => sum + row.skipped, 0);
    line = { bold: `${list(none.map((row) => row.name))} ran no tests`,
             rest: all ? `: ${all === 1 ? "the one test was" : `all ${all} were`} skipped` : "" };
    strip = { title: "No tests ran.", text: `The command passed, but ${none.map((row) =>
      `${row.name} ran 0 tests${row.skipped ? ` and skipped ${row.skipped}` : ""}`).join("; ")}. A pass with no tests counts as a failure.` };
  } else if (kind === "allowed") {
    const fewer = `${less} fewer ${less === 1 ? "test" : "tests"}`;
    line = { bold: `${fewer}, allowed.`, rest: quoted ? ` The agent's reason: ${quoted}` : "" };
    strip = { title: `Passed with ${fewer}, allowed.`,
              text: `${fell ? `${fell}. ` : ""}The agent let this run pass with fewer.${quoted ? ` Its reason: ${quoted}.` : ""}` };
  } else if (kind === "missing") {
    line = { bold: "No test summary", rest: " in its log, and this job requires one" };
    strip = { title: "No test summary.", text: "The command passed, but its log has no test runner's summary, and this job has `tests: required`. A pass that cannot show its tests counts as a failure." };
  }
  return {
    kind, counted, ran, skipped, line, strip, rows, compared,
    tone: kind === "allowed" ? "warn" : line ? "failed" : "plain",
    delta: kind === "more" ? `+${grew}` : null,
    reason: kind === "allowed" ? reason : null,
    first: (kind === "zero" ? none : drops).map((row) => row.name),
    summaries: summaryLines(tests, (kind === "zero" ? none : drops).map((row) => row.name)),
    passed: verdict !== null && verdict !== undefined,
  };
}
