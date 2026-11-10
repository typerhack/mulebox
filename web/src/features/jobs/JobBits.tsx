// The small pieces a job is shown with, wherever it appears: its name and link, branch, where
// it came from, the marks its owner set, the waiting question and its ticking times.

import { Download, GitBranch, Laptop, Pause, Snowflake, TriangleAlert, Workflow, Zap, type LucideIcon } from "lucide-react";

import { RUNNING, duration, isCI, jobHref, nameParts, roughly, shortId, timeLeft } from "../../lib/format";
import type { Job } from "../../lib/types";
import { useAge } from "../../state/live";
import { cx } from "../../ui/cx";
import { Tip } from "../../ui/Tip";

export function JobName({ job, className }: { job: Job; className?: string }) {
  const [project, name] = nameParts(job);
  return (
    <a href={jobHref(job)} className={cx("font-semibold no-underline hover:underline", className)}>
      {project}{name && <> <span className="font-normal text-ink-3">/</span> {name}</>}
    </a>
  );
}

export const Branch = ({ name }: { name: string | null | undefined }) => (name ? (
  <span className="inline-flex min-w-0 items-center gap-1 font-mono text-xs text-ink-2">
    <GitBranch aria-hidden className="size-icon-s" /><span className="truncate">{name}</span>
  </span>
) : null);

export const JobId = ({ job }: { job: Job }) => (
  <span title={`Job id ${job.job_id}`} className="font-mono text-xs whitespace-nowrap text-ink-3">{shortId(job)}</span>
);

// Where a job came from: a GitHub CI run, an upgrade, or the system of the laptop that sent
// it. Older clients do not say, and then it is only a laptop.
export function Source({ job, className }: { job: Job; className?: string }) {
  const [Icon, word, tip]: [LucideIcon, string, string] = job.kind === "upgrade"
    ? [Download, "Upgrade", "A mulebox upgrade: nothing new starts here before it"]
    : isCI(job) ? [Workflow, "CI", "A GitHub CI run"]
      : [Laptop, job.client_os ?? "Laptop", `Sent from a laptop${job.client_os ? `, ${job.client_os}` : ""}`];
  return (
    <span title={tip} className={cx("inline-flex items-center gap-1 whitespace-nowrap", className)}>
      <Icon aria-hidden className="size-icon-s" />{word}
    </span>
  );
}

// Frozen, paused and boosted are marks on a job, not results: drawn in ink, never in a status
// colour. A running job that is paused is frozen on its machine.
export function marksOf(job: Job): { word: string; Icon: LucideIcon }[] {
  const running = RUNNING.has(job.state);
  return [
    job.paused && (running ? { word: "Frozen", Icon: Snowflake } : { word: "Paused", Icon: Pause }),
    job.boost && { word: "Boosted", Icon: Zap },
  ].filter(Boolean) as { word: string; Icon: LucideIcon }[];
}

export function Marks({ job, words }: { job: Job; words?: boolean }) {
  return (
    <>
      {marksOf(job).map(({ word, Icon }) => (words ? (
        <span key={word} className="inline-flex items-center gap-1 font-medium whitespace-nowrap">
          <Icon aria-hidden className="size-icon" />{word}
        </span>
      ) : (
        <Tip key={word} text={word}>
          <span role="img" aria-label={word} className="inline-grid place-items-center text-ink-1">
            <Icon aria-hidden className="size-icon" />
          </span>
        </Tip>
      )))}
    </>
  );
}

// A time that ticks between queue events: the server sends the base, the page adds the age.
export function Elapsed({ job }: { job: Job }) {
  const age = useAge();
  const base = job.elapsed_s ?? job.duration_s;
  const live = job.section !== "recent" && typeof job.elapsed_s === "number";
  return <span className="num">{duration(live ? (base ?? 0) + age : base)}</span>;
}

// The time so far and what a job like it usually takes. Never a time left or a percentage:
// past runs do not say how far this one has come (coordinator/usual.py).
export const OfUsual = ({ job }: { job: Job }) => (
  <span className="whitespace-nowrap">
    <Elapsed job={job} />
    {job.usual_s ? <span title={`Usually ${duration(job.usual_s)}`}> of usually {roughly(job.usual_s)}</span> : null}
  </span>
);

function Left({ job }: { job: Job }) {
  const age = useAge();
  return <span className="num">{timeLeft(Math.max(0, (job.question?.left_s ?? 0) - age))}</span>;
}

// A waiting question: the agent was asked if all is well and has not answered. A working job
// goes on; a stuck one stops when the time is up.
export function QuestionMark({ job, count = 1 }: { job: Job | null; count?: number }) {
  if (!job?.question) return null;
  return (
    <span title={`The agent has not answered. A working job goes on; a stuck one stops: ${job.question.reason}.`}
      className="inline-flex flex-wrap items-center gap-x-2 text-sm font-medium">
      <TriangleAlert aria-hidden className="status-icon size-icon-s text-warning" />
      <span>{count > 1 ? `${count} need an answer` : "Needs an answer"}</span><Left job={job} />
    </span>
  );
}
