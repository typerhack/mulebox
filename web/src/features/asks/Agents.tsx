// The Agents button in the header and its window: what agents may do on every node, saved on
// the coordinator. One choice today, whether an agent's request for a setting change waits for
// the owner ("Ask me first", as installed) or is made at once and recorded ("Allow, and record
// it"), with one sentence under it. Read only, controls off, when the dashboard's are.

import { Bot } from "lucide-react";
import { useId, useRef, useState } from "react";

import type { AgentsOption } from "../../lib/asks";
import { AGENTS_LABEL, AGENTS_SAYS } from "../../lib/asksText";
import { saveAgents, useAsksBody } from "../../state/asks";
import { Button, IconButton } from "../../ui/Button";
import { Segmented } from "../../ui/Segmented";
import { Window } from "../../ui/Window";

const CHOICES = (["ask", "allow"] as AgentsOption[]).map((value) => ({ value, label: AGENTS_LABEL[value] }));

function AgentsWindow({ opener, onClose }: { opener: React.RefObject<HTMLElement | null>; onClose: () => void }) {
  const { body, problem: unread } = useAsksBody();
  const [picked, setPicked] = useState<AgentsOption | null>(null);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const says = useId(), name = useId();
  const saved = body?.agents ?? null, value = picked ?? saved, changed = picked !== null && picked !== saved;
  const editable = body?.editable ?? false;
  const save = async () => {
    if (!picked) return;
    setBusy(true);
    const problem = await saveAgents(picked);
    setSaid(problem ? `Not saved. ${problem}` : "Saved.");
    if (!problem) setPicked(null);
    setBusy(false);
  };
  const state = said ?? (!body ? (unread ? `Not read. ${unread}` : "Reading") : changed ? "Unsaved" : value === "ask" ? "As installed." : "");
  return (
    <Window title="Agents" icon={<Bot aria-hidden className="size-icon" />} opener={opener} onClose={onClose}
      note="What agents may do on every node. Saved on the coordinator."
      foot={<>
        <p role="status" className="mr-auto text-sm text-ink-2">{state}</p>
        <Button tone="ghost" onClick={onClose}>Close</Button>
        <Button tone="primary" disabled={!editable || !changed || busy} onClick={() => void save()}>Save</Button>
      </>}>
      <div className="grid gap-2">
        <strong id={name} className="font-semibold">When an agent asks for more space, or another setting change</strong>
        <Segmented choices={CHOICES} value={value} labelledBy={name} describedBy={says} disabled={!editable || busy || !body}
          onChange={(next) => { setSaid(null); setPicked(next); }} />
        <small id={says} className="max-w-read text-sm text-ink-2">{value ? AGENTS_SAYS[value] : ""}</small>
        {body && !editable && <p className="text-sm text-ink-2">Read only: this dashboard's controls are off.</p>}
      </div>
    </Window>
  );
}

export function AgentsButton() {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  return (
    <>
      <IconButton ref={button} label="Agents: what agents may do" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}>
        <Bot aria-hidden className="size-icon" />
      </IconButton>
      {open && <AgentsWindow opener={button} onClose={() => setOpen(false)} />}
    </>
  );
}
