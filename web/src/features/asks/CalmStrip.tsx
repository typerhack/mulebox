// The grey strip: nothing is wrong and nothing waits. It holds what the owner just answered,
// with Undo until the node has taken it, and each change applied without asking in the last
// day, "as you allowed", with Undo and Got it, which hides it in this browser. The header's
// mark counts none of it.

import { Ban, Bot, CircleCheck, Undo2 } from "lucide-react";
import { useState } from "react";

import { tokenStore } from "../../lib/api";
import { allowedLine, valueText, type Line } from "../../lib/asksText";
import { useStore } from "../../lib/store";
import { decidedStore, dropDecided, gotIt, undo, undoneStore, useAllowed } from "../../state/asks";
import { tickStore } from "../../state/live";
import { Button } from "../../ui/Button";

function Said({ line }: { line: Line }) {
  return (
    <p className="min-w-0 flex-1 basis-col-l">
      <strong className="font-semibold">{line.head}</strong> <span className="text-ink-2">{line.rest}</span>
    </p>
  );
}
const ROW = "flex flex-wrap items-center gap-x-3 gap-y-1";
const ICON = "status-icon mt-px size-icon flex-none self-start";

export function CalmStrip() {
  const decided = useStore(decidedStore), allowed = useAllowed(), undone = useStore(undoneStore);
  const editable = useStore(tokenStore) !== null;
  useStore(tickStore);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  if (!decided.length && !allowed.length) return null;
  const now = Date.now() / 1000;
  const undoIt = async (change: string) => { setBusy(true); setProblem(await undo(change)); setBusy(false); };
  const undoButton = (change: string, tone: "ghost" | "secondary" = "ghost") => (
    <Button tone={tone} disabled={busy || !editable} onClick={() => void undoIt(change)}><Undo2 aria-hidden className="size-icon-s" />Undo</Button>
  );
  return (
    <section role="status" aria-label="Answered and allowed" className="rounded-m border border-line bg-surface-2 px-3 py-2">
      <ul className="grid gap-1">
        {decided.map((d) => (
          <li key={d.change || d.asks.join()} className={ROW}>
            {d.approve ? <CircleCheck aria-hidden className={`${ICON} text-passed`} /> : <Ban aria-hidden className={`${ICON} text-cancelled`} />}
            <Said line={d.line} />
            {d.approve ? d.change && undoButton(d.change)
              : <Button tone="ghost" onClick={() => dropDecided(d.change)}>Got it</Button>}
          </li>
        ))}
        {allowed.map((change) => {
          const back = undone.has(change.id);
          return (
            <li key={change.id} className={ROW}>
              <Bot aria-hidden className={`${ICON} text-ink-1`} />
              <Said line={back ? { head: `Undone: ${change.node} is back to ${valueText(change.setting, change.old)}.`, rest: "The node takes it with its next check-in." }
                : allowedLine(change, now)} />
              <span className="inline-flex flex-wrap gap-2">
                {!back && change.undoable && undoButton(change.id, "secondary")}
                <Button tone="ghost" onClick={() => gotIt(change.id)}>Got it</Button>
              </span>
            </li>
          );
        })}
        {problem && <li role="alert" className="pl-6 text-sm font-semibold">Not undone. {problem}</li>}
      </ul>
    </section>
  );
}
