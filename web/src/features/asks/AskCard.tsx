// One node's requests in the review window: the question, each agent's reason in its own words,
// who asked, the space bar, and the answer: Decline (with a short note if wanted), Another value
// (the Approve button's number becomes a stepper) and Approve. Once answered it says what was
// decided, with Undo until the node has taken it.

import { Ban, Bot, CircleCheck, CircleQuestionMark, Laptop, Pencil, Undo2 } from "lucide-react";
import { useState } from "react";

import { gbValue, wholeGb, type AskGroup, type NodeRoom } from "../../lib/asks";
import { names, settingName, valueText, when } from "../../lib/asksText";
import { useStore } from "../../lib/store";
import { sizeBytes } from "../../lib/storage";
import { answer, decidedStore, undo } from "../../state/asks";
import { Button } from "../../ui/Button";
import { Stepper } from "../../ui/Stepper";
import { SpaceBar } from "./SpaceBar";

interface Props { group: AskGroup; room: NodeRoom | null; now: number; editable: boolean; withNode: boolean; primary: boolean }

function Question({ group, room, now, withNode }: Pick<Props, "group" | "room" | "now" | "withNode">) {
  const larger = group.asks.length === 2 ? ", the larger of the two" : group.asks.length > 2 ? `, the largest of the ${group.asks.length}` : "";
  const from = room?.limit ? ` from ${valueText(group.setting, room.limit)}` : "";
  return (
    <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
      <h3 className="flex min-w-0 items-start gap-2 text-lg leading-tight font-semibold">
        <CircleQuestionMark aria-hidden className="status-icon mt-px size-icon flex-none text-warning" />
        <span>Raise the {settingName(group.setting)}{withNode ? ` on ${group.node}` : ""}{from} to {valueText(group.setting, group.largest)}{larger}?</span>
      </h3>
      <span className="text-sm whitespace-nowrap text-ink-2">{names(group.asks.map((a) => when(a.asked_at, now)))}</span>
    </header>
  );
}

function Reasons({ group, now }: { group: AskGroup; now: number }) {
  if (group.asks.length === 1) {
    const ask = group.asks[0];
    return (
      <>
        <blockquote className="ask-why">{ask.reason || "No reason given."}<cite>Written by the agent that asked</cite></blockquote>
        <p className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-2">
          {ask.project && <span className="inline-flex items-center gap-1"><Bot aria-hidden className="size-icon-s" />An agent working on <code className="font-mono text-ink-1">{ask.project}</code></span>}
          {ask.client && <span className="inline-flex items-center gap-1"><Laptop aria-hidden className="size-icon-s" /><code className="font-mono text-ink-1">{ask.client}</code></span>}
          {ask.job_id && <code className="font-mono wrap-anywhere text-ink-1">{ask.job_id}</code>}
        </p>
      </>
    );
  }
  return group.asks.map((ask) => (
    <blockquote key={ask.id} className="ask-why">{ask.reason || "No reason given."}
      <cite>Asks {valueText(ask.setting, ask.value)}: the agent of <code className="font-mono">{ask.project ?? "a project"}</code>
        {ask.client && <> from <code className="font-mono">{ask.client}</code></>}{ask.job_id && <>, <code className="font-mono">{ask.job_id}</code></>}, {when(ask.asked_at, now)}</cite>
    </blockquote>
  ));
}

export function AskCard({ group, room, now, editable, withNode, primary }: Props) {
  const decided = useStore(decidedStore).find((d) => d.asks.some((id) => group.asks.some((a) => a.id === id)));
  const asked = wholeGb(group.largest), sizes = group.setting === "max_size";
  const [other, setOther] = useState(false);
  const [gb, setGb] = useState(asked);
  const [declining, setDeclining] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const value = other && sizes ? gb * 1e9 : sizeBytes(group.largest) ?? 0;
  const most = room ? Math.max(asked, Math.floor(room.total / 1e9)) : Math.max(asked * 10, 1000);
  const send = async (approve: boolean) => {
    setBusy(true);
    setProblem(null);
    const more = approve ? (other && gb !== asked ? { value: gbValue(gb) } : {}) : note.trim() ? { note: note.trim() } : {};
    setProblem(await answer(group, approve, room?.limit ?? null, more));
    setBusy(false);
  };
  const undoIt = async (change: string) => { setBusy(true); setProblem(await undo(change)); setBusy(false); };

  return (
    <article className="grid min-w-0 gap-3" aria-label={`Requests for ${group.node}`}>
      <Question group={group} room={room} now={now} withNode={withNode} />
      <Reasons group={group} now={now} />
      {sizes && room ? <SpaceBar node={group.node} room={room} value={value} />
        : <p className="text-sm text-ink-2">{sizes ? `${group.node} has sent no storage report yet, so the space it holds is not known here.` : ""}</p>}
      {decided ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-m border border-line bg-surface-2 px-3 py-2">
          {decided.approve ? <CircleCheck aria-hidden className="status-icon size-icon text-passed" /> : <Ban aria-hidden className="status-icon size-icon text-cancelled" />}
          <p role="status" className="min-w-0 flex-1 basis-col-l"><strong className="font-semibold">{decided.line.head}</strong>{" "}
            <span className="text-ink-2">{decided.line.rest}</span></p>
          {decided.approve && decided.change && (
            <Button tone="ghost" disabled={busy} onClick={() => void undoIt(decided.change)}><Undo2 aria-hidden className="size-icon-s" />Undo</Button>
          )}
        </div>
      ) : declining ? (
        <div className="flex flex-wrap items-center justify-end gap-2">
          <input type="text" aria-label="A note for the agent, optional" placeholder="A note for the agent, optional" maxLength={200}
            value={note} onChange={(event) => setNote(event.target.value)} disabled={busy}
            className="h-ctl min-w-0 flex-1 basis-col-l rounded-m border border-line-strong bg-surface-1 px-2 placeholder:text-ink-3 touch:h-ctl-touch" />
          <Button tone="ghost" disabled={busy} onClick={() => setDeclining(false)}>Back</Button>
          <Button disabled={busy} onClick={() => void send(false)}>{note.trim() ? "Decline with the note" : "Decline"}</Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-end gap-2">
          {other && sizes && (
            <span className="mr-auto inline-flex flex-wrap items-center gap-2 text-sm">
              <Stepper value={gb} min={1} max={most} label="Space for mulebox, in GB" unit="GB" units="GB" disabled={busy || !editable}
                onChange={setGb} />
              {gb !== asked && <span className="text-ink-2">asked: {valueText(group.setting, group.largest)}</span>}
            </span>
          )}
          <Button tone="ghost" disabled={busy || !editable} onClick={() => setDeclining(true)}>Decline</Button>
          {sizes && !other && (
            <Button disabled={busy || !editable} onClick={() => { setGb(asked); setOther(true); }}><Pencil aria-hidden className="size-icon-s" />Another value</Button>
          )}
          <Button tone={primary ? "primary" : "secondary"} disabled={busy || !editable} onClick={() => void send(true)}>
            Approve <span className="num">{valueText(group.setting, other ? gbValue(gb) : group.largest)}</span>
          </Button>
        </div>
      )}
      {problem && <p role="alert" className="text-sm font-semibold">Not done. {problem}</p>}
    </article>
  );
}
