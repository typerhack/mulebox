// Every change of a node's setting, newest first, on the Storage page under the cleanup
// history: what changed, old to new, how (by hand, approved, declined, allowed, undone), who
// asked and why, who confirmed, when it was in force, and Undo while the change is the node's
// latest of that setting.

import { Ban, Bot, CircleCheck, History, Pencil, Undo2, type LucideIcon } from "lucide-react";
import { useState } from "react";

import type { Change, How } from "../../lib/asks";
import { entry, stamp, valueText } from "../../lib/asksText";
import { undo, useAsksBody } from "../../state/asks";
import { Button } from "../../ui/Button";
import { WithCode } from "../../ui/Code";
import { cx } from "../../ui/cx";

const ICON: Record<How, [LucideIcon, string]> = {
  approved: [CircleCheck, "text-passed"], approved_other: [CircleCheck, "text-passed"], declined: [Ban, "text-cancelled"],
  allowed: [Bot, "text-ink-1"], owner: [Pencil, "text-ink-2"], agents: [Pencil, "text-ink-2"], undo: [Undo2, "text-ink-2"],
};

function Row({ change, now, editable }: { change: Change; now: number; editable: boolean }) {
  const said = entry(change);
  const [Icon, tone] = ICON[change.how] ?? [Pencil, "text-ink-2"];
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const undoIt = async () => { setBusy(true); setProblem(await undo(change.id)); setBusy(false); };
  return (
    <li className="change-row">
      <Icon aria-hidden className={cx("status-icon mt-px size-icon", tone)} />
      <div className="grid min-w-0 gap-1">
        <p><strong className="font-semibold">{said.title}</strong> {said.how}</p>
        {(change.asked?.asks ?? []).map((ask, index) => (
          <p key={index} className="text-sm text-ink-2">
            Asked by an agent working on <code className="font-mono text-ink-1">{ask.project ?? "a project"}</code>
            {ask.client && <> from <code className="font-mono text-ink-1">{ask.client}</code></>}
            {ask.job_id && <>, <code className="font-mono text-ink-1">{ask.job_id}</code></>}
            {ask.reason ? <>: <q>{ask.reason}</q></> : "."}
          </p>
        ))}
        <p className="text-sm text-ink-2">
          <WithCode text={said.confirm} codeClassName="font-mono text-ink-1" />
          {said.note ? <>, with the note <q>{said.note}</q></> : change.how === "declined" ? "." : ""}
          {said.inForce && ` ${said.inForce}`}
        </p>
        {change.undoable && editable && (
          <span className="flex flex-wrap items-center gap-3">
            <Button disabled={busy} onClick={() => void undoIt()}>
              <Undo2 aria-hidden className="size-icon-s" />Undo: back to {valueText(change.setting, change.old)}
            </Button>
            {problem && <span role="alert" className="text-sm font-semibold">Not undone. {problem}</span>}
          </span>
        )}
      </div>
      <time dateTime={new Date(change.at * 1000).toISOString()} className="text-right text-sm whitespace-nowrap text-ink-2">{stamp(change.at, now)}</time>
    </li>
  );
}

export function SettingsHistory({ now }: { now: number }) {
  const { body, problem } = useAsksBody();
  const changes = body?.changes ?? [];
  return (
    <section aria-label="Settings history" className="keep-list">
      <div className="keep-head flex flex-wrap items-center gap-x-3 text-sm">
        <h3 className="flex items-center gap-2 font-semibold"><History aria-hidden className="size-icon-s flex-none" />Settings history
          <span className="font-normal text-ink-2">every change of a node's setting, newest first</span></h3>
      </div>
      {!body ? <p className="py-2 text-sm text-ink-2">{problem ? `The settings history could not be read. ${problem}` : "Reading the settings history"}</p>
        : !changes.length ? <p className="py-2 text-sm text-ink-2">No setting has changed yet.</p>
          : <ul>{changes.map((change) => <Row key={change.id} change={change} now={now} editable={body.editable} />)}</ul>}
    </section>
  );
}
