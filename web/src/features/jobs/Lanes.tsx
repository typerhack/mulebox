// The Queue tab: the queue by machine (lib/lanes.ts). A lane only for a machine that runs or
// waits for something; the rest are one line of names. A lane with both shows its running
// cards on the left and its line on the right, each under a heading; with only one of the
// two it takes the whole width. Stuck jobs come first: they are the
// one thing here that needs a person. Slots, offers and readings are the Machines box's job.

import type { ReactNode } from "react";

import { ago, plural } from "../../lib/format";
import { groupLanes, type Lane } from "../../lib/lanes";
import type { MachinesPanel, QueueSnapshot } from "../../lib/types";
import { Empty } from "../../ui/Panel";
import { Status } from "../../ui/Status";
import { MachineState } from "../machines/parts";
import { JobCard } from "./JobCard";
import { WaitList } from "./WaitList";

interface LaneBoxProps {
  title: string;
  state?: ReactNode;
  note: ReactNode;
  sub?: string | null;
  children?: ReactNode;
}

const LaneBox = ({ title, state, note, sub, children }: LaneBoxProps) => (
  <section aria-label={title} className="grid min-w-0 gap-2 border-t border-line pt-4 first:border-t-0 first:pt-0">
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <strong className="text-lg font-semibold">{title}</strong>{state}
      <span className="num ml-auto text-sm text-ink-2 max-md:ml-0 max-md:basis-full">{note}</span>
    </div>
    {sub && <p className="text-sm text-ink-2">{sub}</p>}
    {children}
  </section>
);

const COLUMN = "text-sm font-semibold text-ink-2";

function laneNote(lane: Lane): string {
  return [lane.running.length && `${lane.running.length} running`,
          lane.waiting.length && `${lane.waiting.length} waiting for it`].filter(Boolean).join(", ");
}

function MachineLane({ lane, total, now }: { lane: Lane; total: number; now: number }) {
  const m = lane.machine;
  const offline = m?.state === "offline";
  const both = lane.running.length > 0 && lane.waiting.length > 0;
  const cards = lane.running.map((job) => <JobCard key={job.job_id} job={job} cores={m?.cores} total={total} />);
  const line = <WaitList jobs={lane.waiting} total={total} machineCount={null} label={`Waiting for ${lane.name}`} />;
  return (
    <LaneBox title={lane.name} note={laneNote(lane)}
      state={m ? <MachineState machine={m} /> : <Status state="unknown" word="Not listed yet" />}
      sub={offline ? `Offline, last seen ${ago(m.last_seen, now)}. What waits for it starts when it is back.` : null}>
      {both ? (
        <div className="lane-split">
          <div><h3 className={COLUMN}>Running</h3><div className="run-cards">{cards}</div></div>
          <div className="lane-wait"><h3 className={COLUMN}>Waiting in line</h3>{line}</div>
        </div>
      ) : (
        <>{cards.length > 0 && <div className="auto-cards">{cards}</div>}{line}</>
      )}
    </LaneBox>
  );
}

interface Props { snapshot: QueueSnapshot; machines: MachinesPanel | null }

export function Lanes({ snapshot, machines }: Props) {
  const { lanes, quiet, shared, stuck, total } = groupLanes(snapshot, machines);
  const now = Date.now() / 1000;
  const count = (machines?.machines ?? []).length;
  if (!lanes.length && !quiet.length && !shared.length && !stuck.length) {
    return <Empty title="No machine has checked in yet." hint="Jobs show here once a worker is online." />;
  }
  const nothing = !lanes.length && !shared.length && !stuck.length;
  return (
    <div className="@container grid gap-5">
      {stuck.length > 0 && (
        <LaneBox title="No machine fits" note={`${stuck.length} waiting`}
          state={<Status state="stuck" word="Stuck" />} sub="Nothing offers what these need.">
          <WaitList jobs={stuck} total={total} machineCount={null} label="Waiting, no machine fits" />
        </LaneBox>
      )}
      {lanes.map((lane) => <MachineLane key={lane.name} lane={lane} total={total} now={now} />)}
      {shared.length > 0 && (
        <LaneBox title="Next free machine" note={`${shared.length} waiting`}
          sub="Whichever machine is free first takes these, in this order.">
          <WaitList jobs={shared} total={total} machineCount={count} label="Waiting for the next free machine" />
        </LaneBox>
      )}
      {nothing && <Empty title="Nothing is running or waiting." hint="Send a job with `mulebox check` from a project." />}
      {quiet.length > 0 && !nothing && (
        <LaneBox title={`Nothing running on ${quiet.length === 1 ? quiet[0].name : plural(quiet.length, "machine")}`}
          note={quiet.length > 1 ? <a href="#/machines">All machines</a> : ""} state={quiet.length === 1 && quiet[0].machine ? <MachineState machine={quiet[0].machine} /> : undefined}>
          {quiet.length > 1 && (
            <p className="flex flex-wrap gap-x-4 gap-y-2 text-ink-2">
              {quiet.map((lane) => (
                <span key={lane.name} className="inline-flex items-center gap-2 whitespace-nowrap">
                  {lane.machine && <MachineState machine={lane.machine} iconOnly />}{lane.name}
                </span>
              ))}
            </p>
          )}
        </LaneBox>
      )}
    </div>
  );
}
