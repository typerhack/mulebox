// A node's settings window (the user's pick, "Suggested and yours"): opened from the settings
// button on a machine's row. It reads the node's settings (docs/interfaces-m2.md, Node
// settings), holds the viewer's edits until Save, and reads again when the machine's row changes and every
// few seconds while it is open. With the dashboard's controls off, or a node on an older mulebox,
// it only shows.

import { Clock, Lock, OctagonAlert, RotateCcw, Server, Settings2, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";

import { problemText } from "../../lib/api";
import { POLL_MS, asSuggested, changes, dropPending, readSettings, saveSettings, unsent,
         type Draft, type NodeSettings, type SettingKey } from "../../lib/nodeSettings";
import { createTurns } from "../../lib/turns";
import type { Machine } from "../../lib/types";
import { Button, IconButton } from "../../ui/Button";
import { WithCode } from "../../ui/Code";
import { cx } from "../../ui/cx";
import { Tip } from "../../ui/Tip";
import { Window } from "../../ui/Window";
import { SettingsRows } from "./SettingsRows";

type Tone = "calm" | "warning" | "danger";
const TONES: Record<Tone, [string, string]> = {
  calm: ["border-line-strong bg-surface-2", "text-queued"],
  warning: ["border-warning bg-warning-soft", "text-warning"],
  danger: ["border-danger bg-failed-soft", "text-danger"],
};

function Strip({ tone, icon: Icon, alert, action, children }:
               { tone: Tone; icon: typeof Lock; alert?: boolean; action?: ReactNode; children: ReactNode }) {
  return (
    <div role={alert ? "alert" : "status"}
      className={cx("mb-3 flex flex-wrap items-start gap-x-3 gap-y-2 rounded-m border px-3 py-2", TONES[tone][0])}>
      <Icon aria-hidden className={cx("status-icon mt-px size-icon", TONES[tone][1])} />
      <p className="min-w-0 flex-1 basis-col-s">{children}</p>
      {action}
    </div>
  );
}

interface WindowProps { machine: Machine; opener?: RefObject<HTMLElement | null>; onClose: () => void }

export function NodeSettingsWindow({ machine, opener, onClose }: WindowProps) {
  const name = machine.name;
  const [view, setView] = useState<NodeSettings | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<{ text: string; read?: boolean } | null>(null);
  // Answers can come back in any order: one is shown only while its turn is the newest
  // (lib/turns.ts), so a read asked before a save never undoes it.
  const [turns] = useState(createTurns);
  const reading = useRef(0);    // the turn of a read still on its way, to not pile a second on it
  const saving = useRef(false);

  const read = useCallback(() => {
    if (saving.current) return;  // the save reads again when it is done
    const mine = turns.take();
    reading.current = mine;
    readSettings(name).then((next) => {
      if (!turns.newest(mine)) return;
      setView(next);
      setProblem((had) => (had?.read ? null : had));
    }).catch((failure) => {
      if (turns.newest(mine)) setProblem({ text: `Not read. ${problemText(failure)}`, read: true });
    }).finally(() => { if (reading.current === mine) reading.current = 0; });
  }, [name, turns]);

  // Again whenever the row changes: that is how the page hears the node took a change, went
  // away, was paused or upgraded, or started a job.
  useEffect(read, [read, machine.settings_pending, machine.slots, machine.priority, machine.state,
                   machine.version, machine.jobs.length]);
  // And every few seconds, as the row cannot say that the node failed to write a change: it
  // reads "pending" before and after. Edits are kept, they live apart from what was read.
  useEffect(() => {
    const timer = setInterval(() => { if (!reading.current && !document.hidden) read(); }, POLL_MS);
    return () => clearInterval(timer);
  }, [read]);

  // A save, or a pending change dropped. Nothing can be edited meanwhile (`busy`); of the
  // edits, only what was sent is forgotten. Its answer is shown, then the node is read again,
  // as that answer may be older than what the row has said since.
  const send = async (ask: () => Promise<NodeSettings>, failed: string, sent?: Draft) => {
    if (saving.current) return;
    saving.current = true;
    turns.take();
    setBusy(true);
    setProblem(null);
    try {
      const next = await ask();
      turns.take();
      setView(next);
      if (sent) setDraft((had) => unsent(had, sent));
    } catch (failure) {
      setProblem({ text: `${failed} ${problemText(failure)}` });
    } finally {
      saving.current = false;
      setBusy(false);
      read();
    }
  };
  const body = view ? changes(view, draft) : {};
  const dirty = Object.keys(body).length > 0;
  const locked = !view || !view.editable || !view.applies;
  const save = () => send(() => saveSettings(name, body), "Not saved.", body);
  // One setting's pending change goes when the node is asked for what it already has.
  const dropOne = (key: SettingKey) => {
    const now = view?.current?.[key];
    if (now !== undefined) void send(() => saveSettings(name, { [key]: now }), "Not dropped.");
  };
  const waits = view?.pending && Object.keys(view.pending).length > 0;

  return (
    <Window title={name} icon={<Server aria-hidden className="size-icon" />}
      note={`Node settings${machine.host ? ", dashboard host" : ""}`} opener={opener} onClose={onClose} ground
      foot={(
        <>
          <p className="mr-auto min-w-0 flex-1 basis-col-m text-sm text-ink-2">
            {problem ? <strong role="alert" className="font-semibold text-ink-1">{problem.text}</strong>
              : locked ? "Nothing here can be changed from this page."
              : "Applies to the next job; running jobs keep their slot. A suggestion you take is saved as a fixed value of yours."}
          </p>
          {!locked && view && (
            <Button tone="ghost" disabled={busy} onClick={() => setDraft(asSuggested(view))}>
              <RotateCcw aria-hidden className="size-icon-s" />All as suggested
            </Button>
          )}
          <Button tone="ghost" onClick={onClose}>{dirty ? "Cancel" : "Close"}</Button>
          {!locked && <Button tone="primary" disabled={!dirty || busy} onClick={() => void save()}>{busy ? "Saving" : "Save changes"}</Button>}
        </>
      )}>
      {!view ? <p className="text-ink-2">{problem ? "The settings could not be read." : "Reading the node's settings"}</p> : (
        <>
          {!view.editable && (
            <Strip tone="calm" icon={Lock}>
              <strong className="font-semibold">Read only: this dashboard's controls are off.</strong>{" "}
              <WithCode text={`Change it from a dev machine: \`mulebox machine config ${name} --slots 3\`.`} />
            </Strip>
          )}
          {!view.applies && (
            <Strip tone="warning" icon={TriangleAlert}>
              <strong className="font-semibold">
                {name} runs an older mulebox{view.version ? ` (${view.version})` : ""} that takes no settings from afar.
              </strong>{" "}
              <WithCode text={`Upgrade it first: \`mulebox setup ${name}\`.`} />
            </Strip>
          )}
          {view.error && (
            <Strip tone="danger" icon={OctagonAlert} alert
              action={view.editable && <Button disabled={busy} onClick={() => void send(() => dropPending(name), "Not dropped.")}>Drop the change</Button>}>
              <strong className="font-semibold">{name} could not take the change.</strong>{" "}
              {view.error.replace(/\.$/, "")}. It stays pending until you save another value or drop it.
            </Strip>
          )}
          {waits && !view.error && !view.online && (
            <Strip tone="calm" icon={Clock}>
              <strong className="font-semibold">{name} is offline.</strong> It takes the pending change when it is back.
            </Strip>
          )}
          <SettingsRows machine={machine} view={view} draft={draft} locked={locked} busy={busy}
            onEdit={(change) => setDraft((had) => ({ ...had, ...change }))} onDrop={dropOne} />
        </>
      )}
    </Window>
  );
}

// The settings button of a machine's row, with a small mark while a saved change waits for
// the node. Focus comes back to the button when the window closes (ui/Window.tsx).
export function NodeSettingsButton({ machine }: { machine: Machine }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  return (
    <>
      {machine.settings_pending && (
        <Tip text="A settings change waits for this node">
          <span role="img" aria-label="Settings change pending" className="inline-grid place-items-center">
            <Clock aria-hidden className="status-icon size-icon-s text-queued" />
          </span>
        </Tip>
      )}
      <IconButton small ref={button} label={`Settings of ${machine.name}`} tip="Node settings" aria-haspopup="dialog" onClick={() => setOpen(true)}>
        <Settings2 aria-hidden className="size-icon-s" />
      </IconButton>
      {open && <NodeSettingsWindow machine={machine} opener={button} onClose={() => setOpen(false)} />}
    </>
  );
}
