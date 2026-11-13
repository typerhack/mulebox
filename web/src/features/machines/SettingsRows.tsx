// The body of a node's settings window, in the panels of the top row: a panel per setting with
// what mulebox suggests and why, what the viewer set, and what the node runs with now, where an
// edit reads "unsaved" until Save and a saved change "pending" until the node took it. Beside
// them, what the node itself reports, locked.

import { Clock, ListOrdered, Lock, PenLine, RotateCcw, SquareStack } from "lucide-react";
import { useId, type ReactNode } from "react";

import { ago, plural } from "../../lib/format";
import { PRIORITIES, SLOTS_RANGE, SUGGESTED_PRIORITY, priorityLabel, rowOf,
         type Draft, type Mark, type NodeSettings, type SettingKey } from "../../lib/nodeSettings";
import type { Machine } from "../../lib/types";
import { IconButton } from "../../ui/Button";
import { Fact, Panel } from "../../ui/Panel";
import { Segmented } from "../../ui/Segmented";
import { Stepper } from "../../ui/Stepper";
import { Offers } from "./parts";

interface Props {
  machine: Machine;
  view: NodeSettings;
  draft: Draft;
  locked: boolean;                          // nothing here can be changed
  busy: boolean;                            // a save is on its way: no edit until it is back
  onEdit: (change: Draft) => void;
  onDrop: (key: SettingKey) => void;        // take a pending change back
}

// One fact of a setting, as the top panels write theirs: its name on the left, its value on the
// right, and under both a line that says why or what happens next.
function Row({ label, note, noteId, children }: { label: string; note?: ReactNode; noteId?: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-3 text-sm last:pb-0">
      <span className="text-ink-2">{label}</span>
      <div data-label={label} className="contents">
        {children}
        {note && <small id={noteId} className="basis-full text-sm text-ink-2">{note}</small>}
      </div>
    </div>
  );
}

interface RunsProps { now: ReactNode | null; yours: ReactNode; mark: Mark; online: boolean; same: boolean; drop?: () => void; busy: boolean }

function RunsWith({ now, yours, mark, online, same, drop, busy }: RunsProps) {
  const Icon = mark === "unsaved" ? PenLine : Clock;
  return (
    <Row label="Runs with"
      note={mark === "unsaved" ? "sent to the node when you save"
        : mark === "pending" ? (online ? "the node takes it on its next check-in" : "the node takes it when it is back online")
        : same ? "as suggested" : ""}>
      <span className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-1">
        <span className="num font-medium">{now === null ? "Not reported" : <>{now} now</>}</span>
        {mark && (
          <span className="num inline-flex items-center gap-1 font-medium">
            <Icon aria-hidden className="status-icon size-icon-s text-queued" />{yours} {mark}
          </span>
        )}
        {mark === "pending" && drop && (
          <button type="button" disabled={busy} onClick={drop}
            className="inline-flex min-h-ctl-s items-center justify-center font-medium underline touch:min-h-ctl-touch touch:min-w-ctl-touch off:text-ink-3">
            Drop it
          </button>
        )}
      </span>
    </Row>
  );
}

const ROWS = "divide-y divide-line";
const meaning = (text: string) => <p className="pb-3 text-sm text-ink-2">{text}</p>;

export function SettingsRows({ machine, view, draft, locked, busy, onEdit, onDrop }: Props) {
  const says = useId();
  const range = view.choices?.slots ?? SLOTS_RANGE;
  const known = view.choices?.priority ?? PRIORITIES.map((choice) => choice.value);
  const slots = rowOf(view, draft, "slots"), priority = rowOf(view, draft, "priority");
  const mine = slots.yours ?? machine.slots;
  const suggested = view.suggested?.slots;
  const drop = (key: SettingKey) => (locked ? undefined : () => onDrop(key));
  return (
    <div className="@container">
      <div className="settings-grid">
        <div className="grid content-start gap-gap">
          <Panel title="Slots" label="Slots" icon={<SquareStack aria-hidden className="size-icon" />} bodyClassName={ROWS}>
            {meaning(`Jobs at once, ${range.min} to ${range.max}`)}
            <Row label="Suggested" note={suggested ? `from ${view.suggested?.reason}` : "the node has not reported its cores and memory"}>
              {suggested ? <span className="num font-medium">{suggested}</span> : <span>None yet</span>}
            </Row>
            <Row label="Yours">
              <span className="inline-flex items-start gap-2">
                {!locked && !busy && suggested !== undefined && suggested !== mine && (
                  <IconButton label={`Use the suggested ${suggested}`} className="size-ctl"
                    tip={`Sets ${suggested} as your value: a fixed number, kept until you change it`}
                    onClick={() => onEdit({ slots: suggested })}>
                    <RotateCcw aria-hidden className="size-icon" />
                  </IconButton>
                )}
                <Stepper value={mine} min={range.min} max={range.max} label="Slots" unit="slot" disabled={locked || busy}
                  onChange={(next) => onEdit({ slots: next })} />
              </span>
            </Row>
            <RunsWith now={slots.now ?? machine.slots} yours={slots.yours} mark={slots.mark} online={view.online}
              same={slots.now !== null && slots.now === suggested} drop={drop("slots")} busy={busy} />
          </Panel>
          <Panel title="Priority" label="Priority" icon={<ListOrdered aria-hidden className="size-icon" />} bodyClassName={ROWS}>
            {meaning("Which node a job goes to first")}
            <Row label="Suggested" note="the default for every node">
              <span className="font-medium">{priorityLabel(SUGGESTED_PRIORITY)}</span>
            </Row>
            <Row label="Yours" noteId={says}
              note={PRIORITIES.find((choice) => choice.value === priority.yours)?.says ?? "Not reported by the node."}>
              <Segmented label="Priority" describedBy={says} disabled={locked || busy} value={priority.yours}
                choices={PRIORITIES.filter((choice) => known.includes(choice.value))}
                onChange={(next) => onEdit({ priority: next })} />
            </Row>
            <RunsWith now={priority.now ? priorityLabel(priority.now) : null} yours={priorityLabel(priority.yours)}
              mark={priority.mark} online={view.online} same={priority.now === SUGGESTED_PRIORITY}
              drop={drop("priority")} busy={busy} />
          </Panel>
        </div>
        <Panel title="Reported by the node" label="Reported by the node" icon={<Lock aria-hidden className="size-icon" />}
          bodyClassName="flex flex-col gap-2">
          <p className="pb-1 text-sm text-ink-2">Set in its node.toml</p>
          <Fact name="Version">{view.version ?? machine.version ?? "not reported"}</Fact>
          <Fact name="State">
            {view.online ? `Online, ${plural(view.running ?? machine.jobs.length, "job")} running${view.draining ? ", paused" : ""}`
                         : `Offline, last seen ${ago(machine.last_seen, Date.now() / 1000)}`}
          </Fact>
          {typeof machine.cores === "number" && <Fact name="System">{plural(machine.cores, "core")}</Fact>}
          {machine.capabilities.length ? <Offers machine={machine} word /> : <Fact name="Offers">nothing named</Fact>}
        </Panel>
      </div>
    </div>
  );
}
