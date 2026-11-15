// Agents' requests in the amber strip, on every page until answered (the user's pick, option A
// of docs/design-system/approvals/): up to two requests are a line each, answered where they
// are or opened in the review window; from three, one line with the count per node and the
// oldest age, and Review all. Requests for one setting of one node get one answer.

import { CircleQuestionMark } from "lucide-react";
import { useState } from "react";

import { tokenStore } from "../../lib/api";
import { roomOf, type AskGroup } from "../../lib/asks";
import { askLine, foldLine, valueText, type Line } from "../../lib/asksText";
import { useStore } from "../../lib/store";
import { answer, reviewStore, useWaiting } from "../../state/asks";
import { tickStore } from "../../state/live";
import { useStorage } from "../../state/storage";
import { Button } from "../../ui/Button";

export const FOLD_FROM = 3;

function Said({ line }: { line: Line }) {
  return (
    <p className="min-w-0 flex-1 basis-col-l">
      <strong className="font-semibold">{line.head}</strong> <span className="text-ink-2">{line.rest}</span>
    </p>
  );
}

export function AskLines() {
  const groups = useWaiting();
  const { body } = useStorage();
  const editable = useStore(tokenStore) !== null;
  useStore(tickStore);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const now = Date.now() / 1000;
  const count = groups.reduce((n, g) => n + g.asks.length, 0);
  const review = (event: React.MouseEvent<HTMLButtonElement>, which: AskGroup[]) => reviewStore.set({ groups: which, opener: event.currentTarget });
  const quick = async (group: AskGroup, approve: boolean) => {
    setBusy(true);
    setProblem(await answer(group, approve, roomOf(body, group.node)?.limit ?? null));
    setBusy(false);
  };
  const icon = <CircleQuestionMark aria-hidden className="status-icon mt-px size-icon flex-none self-start text-warning" />;
  const row = "flex flex-wrap items-center gap-x-3 gap-y-1";
  return (
    <>
      {count >= FOLD_FROM ? (
        <li className={row}>
          {icon}<Said line={foldLine(groups, now)} />
          <Button aria-haspopup="dialog" onClick={(event) => review(event, groups)}>Review all {count}</Button>
        </li>
      ) : groups.map((group) => (
        <li key={`${group.node}/${group.setting}`} className={row}>
          {icon}<Said line={askLine(group, roomOf(body, group.node), now)} />
          <span className="inline-flex flex-wrap gap-2">
            <Button disabled={busy || !editable} onClick={() => void quick(group, true)}>Approve {valueText(group.setting, group.largest)}</Button>
            <Button aria-haspopup="dialog" onClick={(event) => review(event, [group])}>Review</Button>
            <Button tone="ghost" disabled={busy || !editable} onClick={() => void quick(group, false)}>Decline</Button>
          </span>
        </li>
      ))}
      {problem && <li role="alert" className="pl-6 text-sm font-semibold">Not answered. {problem}</li>}
    </>
  );
}
