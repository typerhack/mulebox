// The table of a node's settings window: a row per setting with what mulebox suggests and
// why, what the viewer set, and what the node runs with now, where an edit reads "unsaved"
// until Save and a saved change "pending" until the node took it. Then what the node itself
// reports, locked.

import { Clock, Lock, PenLine, RotateCcw } from "lucide-react";
import { useId, type ReactNode } from "react";

import { ago, plural } from "../../lib/format";
import { PRIORITIES, SLOTS_RANGE, SUGGESTED_PRIORITY, priorityLabel, rowOf,
         type Draft, type Mark, type NodeSettings, type SettingKey } from "../../lib/nodeSettings";
import type { Machine } from "../../lib/types";
import { IconButton } from "../../ui/Button";
import { Segmented } from "../../ui/Segmented";
import { Stepper } from "../../ui/Stepper";

interface Props {
  machine: Machine;
  view: NodeSettings;
  draft: Draft;
  locked: boolean;                          // nothing here can be changed
  busy: boolean;
  onEdit: (change: Draft) => void;
  onDrop: (key: SettingKey) => void;        // take a pending change back
}

interface RunsProps { now: ReactNode | null; yours: ReactNode; mark: Mark; online: boolean; same: boolean; drop?: () => void; busy: boolean }

function RunsWith({ now, yours, mark, online, same, drop, busy }: RunsProps) {
  const Icon = mark === "unsaved" ? PenLine : Clock;
  return (
    <span role="cell" data-label="Runs with">
      <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="num font-medium">{now === null ? "Not reported" : <>{now} now</>}</span>
        {mark && (
          <span className="num inline-flex items-center gap-1 text-sm font-medium">
            <Icon aria-hidden className="status-icon size-icon-s text-queued" />{yours} {mark}
          </span>
        )}
        {mark === "pending" && drop && (
          <button type="button" disabled={busy} onClick={drop}
            className="inline-flex min-h-ctl-s items-center text-sm font-medium underline touch:min-h-ctl-touch off:text-ink-3">
            Drop it
          </button>
        )}
      </span>
      <small>
        {mark === "unsaved" ? "sent to the node when you save"
          : mark === "pending" ? (online ? "the node takes it on its next check-in" : "the node takes it when it is back online")
          : same ? "as suggested" : ""}
      </small>
    </span>
  );
}

const tags = (items: string[]) => (
  <span className="flex flex-wrap gap-1">
    {items.map((name) => (
      <code key={name} className="rounded-s border border-line bg-surface-2 px-1 text-xs whitespace-nowrap">{name}</code>
    ))}
  </span>
);

export function SettingsRows({ machine, view, draft, locked, busy, onEdit, onDrop }: Props) {
  const says = useId();
  const range = view.choices?.slots ?? SLOTS_RANGE;
  const known = view.choices?.priority ?? PRIORITIES.map((choice) => choice.value);
  const slots = rowOf(view, draft, "slots"), priority = rowOf(view, draft, "priority");
  const mine = slots.yours ?? machine.slots;
  const suggested = view.suggested?.slots;
  const drop = (key: SettingKey) => (locked ? undefined : () => onDrop(key));
  const facts: [string, ReactNode][] = [
    ["Version", <span className="num">{view.version ?? machine.version ?? "not reported"}</span>],
    ["State", view.online ? `Online, ${plural(view.running ?? machine.jobs.length, "job")} running${view.draining ? ", paused" : ""}`
                          : `Offline, last seen ${ago(machine.last_seen, Date.now() / 1000)}`],
    ...(typeof machine.cores === "number" ? [["System", plural(machine.cores, "core")] as [string, ReactNode]] : []),
    ["Offers", machine.capabilities.length ? tags(machine.capabilities) : "nothing named"],
  ];
  return (
    <div className="ledger">
      <div role="table" aria-label="Settings">
        <div role="row" className="ledger-row head">
          <span role="columnheader">Setting</span><span role="columnheader">Suggested</span>
          <span role="columnheader">Yours</span><span role="columnheader">Runs with</span>
        </div>
        <div role="row" className="ledger-row">
          <span role="rowheader" className="font-semibold">Slots<small>jobs at once, {range.min} to {range.max}</small></span>
          <span role="cell" data-label="Suggested">
            {suggested ? <><span className="num font-medium">{suggested}</span><small>from {view.suggested?.reason}</small></>
                       : <>None yet<small>the node has not reported its cores and memory</small></>}
          </span>
          <span role="cell" data-label="Yours" className="flex flex-wrap items-start gap-2">
            <Stepper value={mine} min={range.min} max={range.max} label="Slots" unit="slot" disabled={locked}
              onChange={(next) => onEdit({ slots: next })} />
            {!locked && suggested !== undefined && suggested !== mine && (
              <IconButton label={`Use the suggested ${suggested}`} className="size-ctl"
                tip={`Sets ${suggested} as your value: a fixed number, kept until you change it`}
                onClick={() => onEdit({ slots: suggested })}>
                <RotateCcw aria-hidden className="size-icon" />
              </IconButton>
            )}
          </span>
          <RunsWith now={slots.now ?? machine.slots} yours={slots.yours} mark={slots.mark} online={view.online}
            same={slots.now !== null && slots.now === suggested} drop={drop("slots")} busy={busy} />
        </div>
        <div role="row" className="ledger-row">
          <span role="rowheader" className="font-semibold">Priority<small>which node a job goes to first</small></span>
          <span role="cell" data-label="Suggested">
            <span className="font-medium">{priorityLabel(SUGGESTED_PRIORITY)}</span><small>the default for every node</small>
          </span>
          <span role="cell" data-label="Yours" className="grid gap-1">
            <Segmented label="Priority" describedBy={says} disabled={locked} value={priority.yours}
              choices={PRIORITIES.filter((choice) => known.includes(choice.value))}
              onChange={(next) => onEdit({ priority: next })} />
            <small id={says}>{PRIORITIES.find((choice) => choice.value === priority.yours)?.says ?? "Not reported by the node."}</small>
          </span>
          <RunsWith now={priority.now ? priorityLabel(priority.now) : null} yours={priorityLabel(priority.yours)}
            mark={priority.mark} online={view.online} same={priority.now === SUGGESTED_PRIORITY}
            drop={drop("priority")} busy={busy} />
        </div>
      </div>
      <h3 className="flex items-center gap-2 border-b border-line-strong pt-5 pb-2 text-sm font-semibold text-ink-2">
        <Lock aria-hidden className="size-icon-s" />Reported by the node, set in its node.toml
      </h3>
      <dl>
        {facts.map(([name, value]) => (
          <div key={name} className="ledger-row fact"><dt className="text-ink-2">{name}</dt><dd>{value}</dd></div>
        ))}
      </dl>
    </div>
  );
}
