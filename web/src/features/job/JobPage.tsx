// One job's page: how it went, its controls, its stages beside its live log, and its details.
// A GitHub job's page says GitHub has its output and shows its steps (CiSteps.tsx).

import { ArrowLeft, ExternalLink, Server } from "lucide-react";
import { useCallback, useState } from "react";

import { tokenStore } from "../../lib/api";
import { clock, isCI, nameParts, repository, safeUrl, stateOf } from "../../lib/format";
import { quietText } from "../../lib/quiet";
import { useStore } from "../../lib/store";
import type { JobDetail } from "../../lib/types";
import { tickStore, useMachines, useQueue } from "../../state/live";
import { LinkButton } from "../../ui/Button";
import { Panel } from "../../ui/Panel";
import { Status } from "../../ui/Status";
import { Branch, JobId, Marks, Source } from "../jobs/JobBits";
import { CiSteps } from "./CiSteps";
import { CancelControl, SteerButtons, cancellable, said, steers } from "./JobControls";
import { AloneNote, GoingBack, JobFacts, resultText } from "./JobParts";
import { LogPanel } from "./LogPanel";
import { useJob } from "./useJob";
import { RunTimePanel, StagesPanel } from "./Waterfall";

const Crumb = () => (
  <a href="#/" className="inline-flex min-h-ctl-s touch:min-h-ctl-touch items-center gap-2 justify-self-start font-medium text-ink-2 no-underline hover:text-ink-1">
    <ArrowLeft aria-hidden className="size-icon" />Back to the queue
  </a>
);

function Loaded({ job, first, finish, merge }: { job: JobDetail; first: JobDetail; finish: (j: JobDetail) => void; merge: (p: Partial<JobDetail>) => void }) {
  const token = useStore(tokenStore);
  const snapshot = useQueue(), machines = useMachines();
  useStore(tickStore);
  const [state, setState] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [goBack, setGoBack] = useState(false);
  const now = Date.now() / 1000;
  const ci = isCI(job);
  const live = [...(snapshot?.running ?? []), ...(snapshot?.queued ?? [])].find((row) => row.job_id === job.job_id) ?? null;
  const shownJob: JobDetail = { ...job, question: job.state === "finished" ? null : live?.question ?? job.question };
  const cores = machines?.machines.find((m) => m.name === job.worker)?.cores;
  const shown = job.state === "finished" ? stateOf(job) : state ?? stateOf(job);
  const [project, name] = nameParts(job);
  const run = safeUrl(job.run_url);
  const result = resultText(job), line = problem ?? said(job);
  const onEnd = useCallback((final: JobDetail, atEnd: boolean) => {
    finish(final);
    // Only for a job watched to its end, and never while its log is being read further up.
    if (first.state !== "finished" && atEnd) setGoBack(true);
  }, [finish, first.state]);

  return (
    <div className="@container grid min-w-0 gap-gap">
      <Crumb />
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex max-w-full flex-auto flex-wrap items-center gap-x-3 gap-y-1">
          <Status state={shown} size="xl" still={Boolean(job.paused)} className="text-lg font-semibold" />
          <h1 className="text-xl leading-tight font-semibold tracking-tight">
            {ci && "CI "}{project}{name && <> <span className="font-normal text-ink-3">/</span> {name}</>}
          </h1>
          {job.state !== "finished" && <Marks job={job} words />}
        </div>
        {token && (
          <div role="group" aria-label="Job controls" className="flex min-w-0 flex-wrap gap-2">
            {steers(job) && <SteerButtons job={job} onChange={merge} onProblem={setProblem} />}
            {run && (
              <LinkButton href={run} target="_blank" rel="noopener noreferrer">
                <ExternalLink aria-hidden className="size-icon-s" />{job.state === "finished" ? "Open the GitHub run" : "Follow it live on GitHub"}
              </LinkButton>
            )}
            {cancellable(job) && <CancelControl job={job} />}
          </div>
        )}
        {!token && run && <LinkButton href={run} target="_blank" rel="noopener noreferrer"><ExternalLink aria-hidden className="size-icon-s" />Open the GitHub run</LinkButton>}
        {line && steers(job) && <p role="status" className="basis-full text-sm text-ink-2">{line}</p>}
        {result && <p role="status" className="basis-full text-sm text-ink-2">{result}</p>}
        <p className="flex basis-full flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-2">
          <Branch name={job.branch} /><JobId job={job} /><Source job={job} />
          {job.worker && <span className="inline-flex items-center gap-1 whitespace-nowrap"><Server aria-hidden className="size-icon-s" />{job.worker}</span>}
          <span className="num">{job.started_at ? `started ${clock(job.started_at)}` : `created ${clock(job.created_at)}`}</span>
        </p>
      </header>
      {goBack && <GoingBack onStay={() => setGoBack(false)} />}
      <AloneNote job={shownJob} />
      {ci && (
        <p className="max-w-read text-sm text-ink-2">
          GitHub Actions runs this job of {repository(job)} on this machine and holds one of its build slots while it
          does. The steps below show each step as it starts, and a step's output once the runner writes it, often only
          when the step ends. GitHub has it second by second, and the result.
        </p>
      )}
      <div className="job-split">
        {ci ? <RunTimePanel job={job} live={live} cores={cores} now={now} />
            : <StagesPanel job={job} live={live} cores={cores} now={now} />}
        {ci ? <CiSteps job={job} onState={setState} onEnd={onEnd} />
            : <LogPanel jobId={job.job_id} quiet={job.state === "finished" ? "" : quietText(job.activity)} onState={setState} onEnd={onEnd} />}
      </div>
      <JobFacts job={job} />
    </div>
  );
}

export function JobPage({ jobId }: { jobId: string }) {
  const { job, first, error, finish, merge } = useJob(jobId);
  if (error) {
    return <div className="grid gap-gap"><Crumb /><Panel title="Job" label="Job" strong><p>Could not load this job: {error}</p></Panel></div>;
  }
  if (!job || !first) {
    return <div className="grid gap-gap"><Crumb /><p role="status" className="text-ink-2">Loading</p></div>;
  }
  return <Loaded key={jobId} job={job} first={first} finish={finish} merge={merge} />;
}
