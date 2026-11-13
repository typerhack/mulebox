// A node's settings window (the user's pick, "Suggested and yours"): opened from the settings
// button on a machine's row. It reads the node's settings (docs/interfaces-m2.md, Node
// settings), holds the viewer's edits until Save, and reads again when the machines event says
// the node took a change. With the dashboard's controls off, or a node on an older mulebox,
// it only shows.

import { Clock, Lock, OctagonAlert, RotateCcw, Server, Settings2, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";

import { problemText } from "../../lib/api";
import { asSuggested, changes, dropPending, readSettings, saveSettings,
         type Draft, type NodeSettings, type SettingKey } from "../../lib/nodeSettings";
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
      className={cx("mb-4 flex flex-wrap items-start gap-x-3 gap-y-2 rounded-m border px-3 py-2", TONES[tone][0])}>
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
  const [problem, setProblem] = useState<string | null>(null);

  // Again whenever the row changes: that is how the page hears the node took a change.
  useEffect(() => {
    let stale = false;
    readSettings(name).then((next) => { if (!stale) setView(next); })
      .catch((failure) => { if (!stale) setProblem(`Not read. ${problemText(failure)}`); });
    return () => { stale = true; };
  }, [name, machine.settings_pending, machine.slots, machine.priority]);

  const send = async (ask: () => Promise<NodeSettings>, failed: string, done?: () => void) => {
    setBusy(true);
    setProblem(null);
    try {
      setView(await ask());
      done?.();
    } catch (failure) {
      setProblem(`${failed} ${problemText(failure)}`);
    } finally {
      setBusy(false);
    }
  };
  const body = view ? changes(view, draft) : {};
  const dirty = Object.keys(body).length > 0;
  const locked = !view || !view.editable || !view.applies;
  const save = () => send(() => saveSettings(name, body), "Not saved.", () => setDraft({}));
  // One setting's pending change goes when the node is asked for what it already has.
  const dropOne = (key: SettingKey) => {
    const now = view?.current?.[key];
    if (now !== undefined) void send(() => saveSettings(name, { [key]: now }), "Not dropped.");
  };
  const waits = view?.pending && Object.keys(view.pending).length > 0;

  return (
    <Window title={name} icon={<Server aria-hidden className="size-icon" />}
      note={`Node settings${machine.host ? ", dashboard host" : ""}`} opener={opener} onClose={onClose}
      foot={(
        <>
          <p className="mr-auto min-w-0 flex-1 basis-col-m text-sm text-ink-2">
            {problem ? <strong role="alert" className="font-semibold text-ink-1">{problem}</strong>
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
