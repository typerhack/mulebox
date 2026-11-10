// Finished jobs as rows: the state with its mark and word, the job, where a GitHub job failed,
// then the machine or the time it finished, and how long it ran. Used by the Failed, Passed
// and Recent tabs and by the History page.

import { FAILED, clock, stateOf } from "../../lib/format";
import type { Job } from "../../lib/types";
import { Status } from "../../ui/Status";
import { Branch, Elapsed, JobId, JobName, Source } from "./JobBits";

// Where a GitHub job failed, as its completed hook read it from the runner (runners/diary.py).
function why(job: Job): string | null {
  const ci = job.ci_result, state = stateOf(job);
  if (!ci?.step || !(FAILED.has(state) || state === "cancelled")) return null;
  return `In ${ci.step}${ci.message ? `: ${ci.message.replace(/\.$/, "")}` : ""}`;
}

export function DoneRow({ job, last }: { job: Job; last: "machine" | "finished" }) {
  const reason = why(job);
  return (
    <li className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-line py-2">
      <Status state={stateOf(job)} className="min-w-col-s self-center max-touch:min-w-0" />
      <div className="flex min-w-0 flex-1 basis-col-l flex-wrap items-baseline gap-x-3">
        <JobName job={job} /><Branch name={job.branch} /><JobId job={job} />
        <Source job={job} className="text-sm text-ink-2" />
        {reason && <span className="basis-full text-sm break-words text-ink-2">{reason}</span>}
      </div>
      <span className="num inline-flex gap-4 text-sm text-ink-2">
        <span>{last === "machine" ? job.worker ?? "-" : clock(job.finished_at)}</span><Elapsed job={job} />
      </span>
    </li>
  );
}

export const DoneList = ({ jobs, last }: { jobs: Job[]; last: "machine" | "finished" }) => (
  <ol className="border-t border-line">{jobs.map((job) => <DoneRow key={job.job_id} job={job} last={last} />)}</ol>
);
