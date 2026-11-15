// The review window for agents' requests: one node's requests with the reason, who asked and
// the space bar; with several nodes, a list grouped by node, each answered with its own disk in
// view. The groups are the ones the owner opened, so an answered card stays to say what was
// decided while the strip drops its request.

import { HardDrive } from "lucide-react";
import { useMemo, type RefObject } from "react";

import { tokenStore } from "../../lib/api";
import { roomOf, type AskGroup } from "../../lib/asks";
import { when } from "../../lib/asksText";
import { plural } from "../../lib/format";
import { useStore } from "../../lib/store";
import { reviewStore } from "../../state/asks";
import { tickStore } from "../../state/live";
import { useStorage } from "../../state/storage";
import { Button } from "../../ui/Button";
import { WithCode } from "../../ui/Code";
import { Window } from "../../ui/Window";
import { AskCard } from "./AskCard";

interface Props { groups: AskGroup[]; opener?: RefObject<HTMLElement | null>; onClose: () => void }

export function AskWindow({ groups, opener, onClose }: Props) {
  const { body } = useStorage();
  const editable = useStore(tokenStore) !== null;
  useStore(tickStore);
  const now = Date.now() / 1000;
  const count = groups.reduce((n, g) => n + g.asks.length, 0), many = groups.length > 1;
  const topic = groups.every((g) => g.setting === "max_size") ? "more space" : "a setting change";
  const title = `${count === 1 ? "Request" : "Requests"} for ${topic}`;
  const note = many ? `${count} waiting on ${plural(groups.length, "node")}` : `${groups[0]?.node}, asked ${when(groups[0]?.oldest ?? now, now)}`;
  return (
    <Window title={title} note={note} icon={<HardDrive aria-hidden className="size-icon" />} opener={opener} onClose={onClose}
      foot={<>
        {!editable && <p className="mr-auto text-sm text-ink-2"><WithCode text="Read only: this dashboard's controls are off. Answer with `mulebox storage approve` on a dev machine." /></p>}
        <Button tone="ghost" onClick={onClose}>Close</Button>
      </>}>
      <div className="grid gap-5">
        {groups.map((group) => (
          <section key={`${group.node}/${group.setting}`} aria-label={group.node} className="grid min-w-0 gap-3">
            {many && (
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-line-strong pb-2">
                <strong className="text-lg font-semibold">{group.node}</strong>
                <span className="text-sm text-ink-2">{group.asks.length > 1 ? `${group.asks.length} requests for its space, one answer` : "1 request"}</span>
              </div>
            )}
            <AskCard group={group} room={roomOf(body, group.node)} now={now} editable={editable} withNode={!many} primary={!many} />
          </section>
        ))}
      </div>
    </Window>
  );
}

// Where the window lives: always on the page, open while `reviewStore` holds groups.
export function AskWindowHost() {
  const open = useStore(reviewStore);
  const opener = useMemo(() => ({ current: open?.opener ?? null }), [open]);
  return open ? <AskWindow groups={open.groups} opener={opener} onClose={() => reviewStore.set(null)} /> : null;
}
