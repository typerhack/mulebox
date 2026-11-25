// A running job's card: its state as an icon, name, branch and id, where it came from, what
// it is doing, the time so far beside the usual, the cores the job alone uses, what it
// downloads while it does, and, across its foot, what it looks like when it is not working.

import { Bed, Repeat } from "lucide-react";

import { stateOf, stateText } from "../../lib/format";
import { heldWords } from "../../lib/health";
import { coresText, doingWord } from "../../lib/doing";
import { waitReason } from "../../lib/lanes";
import { placeOf } from "../../lib/order";
import type { Job } from "../../lib/types";
import { useMachines } from "../../state/live";
import { WithCode } from "../../ui/Code";
import { CopyText } from "../../ui/Copy";
import { Meter } from "../../ui/Meter";
import { Status } from "../../ui/Status";
import { Branch, Elapsed, JobId, JobName, Marks, OfUsual, QuestionMark, Source } from "./JobBits";
import { DownloadMeter } from "./DownloadMeter";
import { JobMenu, MoveButtons } from "./JobMenu";
import { LooksLine } from "./LooksLine";

export function JobCard({ job, cores, total }: { job: Job; cores: number | null | undefined; total: number }) {
  const state = stateOf(job);
  const frozen = Boolean(job.paused);
  const pct = job.doing?.cpu_pct;
  const word = doingWord(job.doing);
  return (
    <article className="on-card flex min-w-0 flex-wrap items-start gap-3 rounded-m border border-line bg-surface-2 p-3">
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
        <DownloadMeter download={job.doing?.download} trails={job.kind === "runner"} />
        <QuestionMark job={job} />
      </div>
      <div className="flex flex-none items-center gap-2"><Marks job={job} /><JobMenu job={job} total={total} /></div>
      <LooksLine job={job} />
    </article>
  );
}

const Reason = ({ text }: { text: string }) => (
  <span className="basis-full text-sm text-ink-2"><WithCode text={text} codeClassName="text-xs text-ink-1" /></span>
);

// Why a row stands where it does under the order rules, with the rule's icon; the server's own
// full sentence is its tooltip and is on the job's page. It wraps inside the job's column, so
// the arrows keep their place.
function Place({ job }: { job: Job }) {
  const place = placeOf(job);
  if (!place) return null;
  return (
    <span title={job.place_reason ?? undefined} className="place flex basis-full items-start gap-1 text-sm text-ink-2">
      <place.Icon aria-hidden className="mt-hair size-icon-s" /><span className="min-w-0 break-words">{place.text}</span>
    </span>
  );
}

// A waiting row: its real queue position, the job, why it waits, why it stands there, how long
// it has waited, the four move arrows as one group, and the three dots.
// A job a node's checks hold back says so in four words, leading to the strip that has the
// node's sentence and fix (the user's pick, option B of design-system/resting/).
function Held({ job }: { job: Job }) {
  const words = heldWords(job, useMachines()?.machines ?? []);
  if (!words) return null;
  const show = (event: React.MouseEvent) => {
    event.preventDefault();
    const strip = document.getElementById("out-of-step");
    strip?.scrollIntoView({ block: "start" });
    strip?.focus({ preventScroll: true });
  };
  return (
    <a href="#out-of-step" onClick={show} className="inline-flex basis-full items-center gap-1 text-sm font-medium">
      <Bed aria-hidden className="status-icon size-icon-s text-danger" /><span>{words}</span>
    </a>
  );
}

// Put back in line once, as its node could not set it up (coordinator/health.py).
const BackInLine = ({ job }: { job: Job }) => (job.retries ? (
  <span title="Its node could not set it up, so it went back in line. This happens once."
    className="inline-flex items-center gap-1 text-sm text-ink-2"><Repeat aria-hidden className="size-icon-s" />back in line once</span>
) : null);

export function WaitRow({ job, total, machineCount }: { job: Job; total: number; machineCount: number | null }) {
  const held = Boolean(job.held_by?.length);
  const reason = held ? null : waitReason(job, machineCount);
  return (
    <li className="wait-row min-w-0 border-b border-line py-2">
      {job.position
        ? <span aria-label={`Position ${job.position}`} className="num min-w-4 text-right font-mono text-sm text-ink-2">{job.position}</span>
        : <Status state={stateOf(job)} iconOnly />}
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-3">
        <JobName job={job} /><Branch name={job.branch} /><Source job={job} className="text-sm text-ink-2" />
        <BackInLine job={job} />
        {held && <Held job={job} />}
        {reason && <Reason text={reason} />}
        <Place job={job} />
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
