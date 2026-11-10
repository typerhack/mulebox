// Smaller parts of a job's page: the line that says how it went, the facts, the note for a
// waiting question, and the way back to the queue once a watched job ends.

import { useEffect, useState } from "react";

import { clock, duration } from "../../lib/format";
import { go } from "../../lib/router";
import type { JobDetail } from "../../lib/types";
import { Button } from "../../ui/Button";
import { QuestionMark } from "../jobs/JobBits";

const BACK_AFTER_S = 10;

// "Is it over, and how did it go?": where it failed, what GitHub said, its exit code.
export function resultText(job: JobDetail): string {
  if (job.state !== "finished") return "";
  const failedIn = job.failed_stage ? `in ${job.failed_stage}` : null;
  const github = job.ci_result?.message?.replace(/\.$/, "") ?? null;
  const code = job.exit_code === null || job.exit_code === undefined ? null : `exit ${job.exit_code}`;
  return ["Finished", failedIn, github, code, `ended ${clock(job.finished_at)}`].filter(Boolean).join(", ");
}

export function factsOf(job: JobDetail): [string, string, boolean][] {
  const rows: [string, unknown, boolean?][] = [
    ["Project", job.project], ["Job", job.job], ["Branch", job.branch], ["Client", job.client],
    ["Worker", job.worker], ["Exit code", job.exit_code], ["Created", clock(job.created_at)],
    ["Started", clock(job.started_at)], ["Finished", clock(job.finished_at)],
    ["Run time", job.duration_s === null || job.duration_s === undefined ? null : duration(job.duration_s)],
    ["Commit", job.base_commit?.slice(0, 12), true],
    ["Check-in every", job.timeout_min ? `${job.timeout_min} min` : null], ["Stopped", job.stop_text],
    ["Toolchain", typeof job.toolchain === "string" ? job.toolchain : null, true],
    ["Command", job.command, true], ["Job id", job.job_id, true],
  ];
  return rows.filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([name, value, code]) => [name, String(value), Boolean(code)]);
}

export const JobFacts = ({ job }: { job: JobDetail }) => (
  <details className="rounded-l border border-line bg-surface-1 p-3">
    <summary className="cursor-pointer text-sm font-semibold text-ink-2">Job details</summary>
    <dl className="auto-facts mt-3">
      {factsOf(job).map(([name, value, code]) => (
        <div key={name} className="min-w-0">
          <dt className="text-sm text-ink-2">{name}</dt>
          <dd className="break-words">{code ? <code>{value}</code> : value}</dd>
        </div>
      ))}
    </dl>
  </details>
);

// Nobody answered: what happens, and the two ways out, which work whatever this page offers.
export const AloneNote = ({ job }: { job: JobDetail }) => (job.question && job.state !== "finished" ? (
  <div className="grid gap-1 rounded-m border border-warning bg-warning-soft px-3 py-2">
    <QuestionMark job={job} />
    <p>The agent was asked if all is well. If the job stays stuck it stops: {job.question.reason}.</p>
    <p>It is fine, let it go on: <code className="font-semibold">mulebox ok {job.job_id}</code></p>
    <p>Or end it: <code className="font-semibold">mulebox cancel {job.job_id}</code></p>
  </div>
) : null);

// Someone who watched a job end wants to see what the queue does next, but not at the cost of
// reading the result: the way back can be refused.
export function GoingBack({ onStay }: { onStay: () => void }) {
  const [left, setLeft] = useState(BACK_AFTER_S);
  useEffect(() => {
    const timer = setInterval(() => setLeft((n) => n - 1), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => { if (left <= 0) go("#/"); }, [left]);
  return (
    <p role="status" className="flex flex-wrap items-center gap-3 text-sm text-ink-2">
      <span>Back to the queue in {Math.max(0, left)} s.</span><Button onClick={onStay}>Stay on this job</Button>
    </p>
  );
}
