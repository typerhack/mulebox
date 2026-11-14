// The owner's decision when a node is under its reserve and the rules have nothing left to
// remove (design.md, Disk use and cleanup on its own): what the node says could go next,
// oldest first, with just enough ticked to be back above the reserve. The ruler answers each
// tick. Nothing goes without the red button; each ticked folder is then removed on every node.

import { HardDrive, Trash2 } from "lucide-react";
import { useMemo, useState, type RefObject } from "react";

import { ago, bytes, plural } from "../../lib/format";
import { branchOf, type CouldGo, type Report, type StorageBody } from "../../lib/storage";
import { markGone, refreshStorage } from "../../state/storage";
import { sendRemove } from "../../lib/storage";
import { problemText } from "../../lib/api";
import { Button } from "../../ui/Button";
import { Window } from "../../ui/Window";
import { DiskRuler } from "./DiskRuler";

const keyOf = (folder: CouldGo) => `${folder.project}/${folder.folder}`;
const WHY: Record<string, string> = {
  stays: "Would go by itself once it is unused long enough.",
  latest: "The project's latest folder: its next job would set it up again, slower once.",
  kept: "Kept by you. Drop its keep mark on the Storage page to offer it here.",
};

// Just enough of what would go by itself anyway, oldest first, to cover what is missing.
export function proposed(folders: CouldGo[], need: number, can: (folder: CouldGo) => boolean): Set<string> {
  const ticked = new Set<string>();
  let total = 0;
  for (const folder of folders) {
    if (total >= need) break;
    if (folder.fate !== "stays" || !can(folder)) continue;
    ticked.add(keyOf(folder));
    total += folder.size;
  }
  return ticked;
}

interface Props { node: string; body: StorageBody; report: Report; now: number; opener?: RefObject<HTMLElement | null>; onClose: () => void }

export function ReviewWindow({ node, body, report, now, opener, onClose }: Props) {
  const short = report.short;
  const folders = useMemo(() => short?.folders ?? [], [short]);
  const can = (folder: CouldGo) => folder.fate !== "kept" && branchOf(body, folder.project, folder.folder) !== null;
  const [ticked, setTicked] = useState(() => proposed(folders, short?.need ?? 0, can));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const chosen = folders.filter((folder) => ticked.has(keyOf(folder)));
  const frees = chosen.reduce((a, f) => a + f.size, 0);
  const flip = (folder: CouldGo) => setTicked((had) => {
    const next = new Set(had);
    if (!next.delete(keyOf(folder))) next.add(keyOf(folder));
    return next;
  });
  const remove = async () => {
    setBusy(true);
    setProblem(null);
    const failed: string[] = [];
    for (const folder of chosen) {
      try {
        const said = await sendRemove(folder.project, branchOf(body, folder.project, folder.folder));
        if (said.length) failed.push(...said); else markGone(folder.project, folder.folder);
      } catch (failure) {
        failed.push(problemText(failure));
      }
    }
    await refreshStorage();
    setBusy(false);
    if (failed.length) setProblem(failed.join(" ")); else onClose();
  };
  return (
    <Window title={node} icon={<HardDrive aria-hidden className="size-icon" />} opener={opener} onClose={onClose}
      note={short ? `${bytes(short.need)} under its reserve of ${bytes(report.disk.reserve)}` : "Above its reserve again"}
      foot={(
        <>
          <p className="mr-auto min-w-0 flex-1 basis-col-m text-sm text-ink-2">
            {problem ? <strong role="alert" className="font-semibold text-ink-1">Not all removed. {problem}</strong>
              : `${chosen.length} of ${folders.length} ticked: frees ${bytes(frees)} here. Or lower the reserve in this node's settings.`}
          </p>
          <Button tone="ghost" disabled={busy} onClick={onClose}>Not now</Button>
          <Button tone="danger" disabled={busy || !chosen.length} onClick={() => void remove()}>
            <Trash2 aria-hidden className="size-icon-s" />{busy ? "Removing" : `Remove ${bytes(frees)}`}
          </Button>
        </>
      )}>
      <div className="grid gap-3">
        <DiskRuler report={report} would={frees} />
        <p className="text-sm text-ink-2">
          The rules ran: no branch folder here is unused for {plural(report.policy.unused_days, "day")}.
          These could go next, oldest first. Hatched in green: what the ticked lines free.
        </p>
        <div>
          {folders.map((folder) => {
            const branch = branchOf(body, folder.project, folder.folder), id = `review-${keyOf(folder)}`;
            return (
              <label key={keyOf(folder)} htmlFor={id} className="tick-row">
                <input id={id} type="checkbox" checked={ticked.has(keyOf(folder))} disabled={busy || !can(folder)}
                  onChange={() => flip(folder)} />
                <span className="grid min-w-0">
                  <span className="min-w-0"><code className="font-mono font-medium wrap-anywhere">{branch ?? folder.folder}</code>{" "}
                    <span className="text-ink-2">of {folder.project}, last job {ago(folder.last_used, now)}</span></span>
                  <span className="text-sm text-ink-2">
                    {branch === null ? "mulebox does not know this folder's branch: clean its project on the Storage page." : WHY[folder.fate]}
                  </span>
                </span>
                <strong className="num font-semibold">{bytes(folder.size)}</strong>
              </label>
            );
          })}
          {!folders.length && <p className="text-ink-2">Nothing more could go: free space some other way, or lower the reserve.</p>}
        </div>
      </div>
    </Window>
  );
}
