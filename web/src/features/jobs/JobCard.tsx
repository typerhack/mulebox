// A running job's card: its state as an icon, name, branch and id, where it came from, what
// it is doing, the time so far beside the usual, and the cores the job alone uses.

import { stateOf, stateText } from "../../lib/format";
import { coresText, doingWord } from "../../lib/doing";
import { waitReason } from "../../lib/lanes";
import type { Job } from "../../lib/types";
import { WithCode } from "../../ui/Code";
import { CopyText } from "../../ui/Copy";
import { Meter } from "../../ui/Meter";
import { Status } from "../../ui/Status";
import { Branch, Elapsed, JobId, JobName, Marks, OfUsual, QuestionMark, Source } from "./JobBits";
import { JobMenu, MoveButtons } from "./JobMenu";

export function JobCard({ job, cores, total }: { job: Job; cores: number | null | undefined; total: number }) {
  const state = stateOf(job);
  const frozen = Boolean(job.paused);
  const pct = job.doing?.cpu_pct;
  const word = doingWord(job.doing);
  return (
    <article className="on-card flex min-w-0 items-start gap-3 rounded-m border border-line bg-surface-2 p-3">
      <Status state={state} word={frozen ? `${stateText(state)}, frozen` : undefined} iconOnly still={frozen}
        size="l" className="mt-px" />
      <div className="grid min-w-0 flex-1 gap-1">
        <JobName job={job} />
        <span className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1"><Branch name={job.branch} /><JobId job={job} /></span>
        <span className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-2">
          <Source job={job} />
          {job.doing && <CopyText text={word} title={job.kind === "runner" ? "GitHub step" : "Stage"} />}
          <OfUsual job={job} />
        </span>
        {job.doing && (typeof pct === "number" && cores ? (
          <Meter name="Cores" value={(pct / cores)} text={coresText(pct)}
            label={`Cores this job uses: ${coresText(pct)} of ${cores}`} />
        ) : <p className="num text-sm text-ink-2">Cores: {coresText(pct)}</p>)}
        <QuestionMark job={job} />
      </div>
      <div className="flex flex-none items-center gap-2"><Marks job={job} /><JobMenu job={job} total={total} /></div>
    </article>
  );
}

const Reason = ({ text }: { text: string }) => (
  <span className="basis-full text-sm text-ink-2"><WithCode text={text} codeClassName="text-xs text-ink-1" /></span>
);

// A waiting row: its real queue position, the job, why it waits, how long it has waited, the
// four move arrows as one group, and the three dots.
export function WaitRow({ job, total, machineCount }: { job: Job; total: number; machineCount: number | null }) {
  const reason = waitReason(job, machineCount);
  return (
    <li className="wait-row min-w-0 border-b border-line py-2">
      {job.position
        ? <span aria-label={`Position ${job.position}`} className="num min-w-4 text-right font-mono text-sm text-ink-2">{job.position}</span>
        : <Status state={stateOf(job)} iconOnly />}
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-3">
        <JobName job={job} /><Branch name={job.branch} /><Source job={job} className="text-sm text-ink-2" />
        {reason && <Reason text={reason} />}
        <QuestionMark job={job} />
      </div>
      <div className="wait-side flex items-center gap-2">
        <Marks job={job} />
        <span className="wait-time text-sm whitespace-nowrap text-ink-2">waiting <Elapsed job={job} /></span>
        <MoveButtons job={job} total={total} /><JobMenu job={job} total={total} />
      </div>
    </li>
  );
}
