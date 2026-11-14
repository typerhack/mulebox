// What goes next on a node by itself, soonest first, across its projects: the list behind
// "Show what goes next". A folder can be kept from here, which takes it off the list with the
// node's next cleanup.

import { HardDrive } from "lucide-react";
import type { RefObject } from "react";

import { ago, bytes, plural } from "../../lib/format";
import { branchOf, fateText, goingNext, keptBranch, type Report, type StorageBody } from "../../lib/storage";
import { Button } from "../../ui/Button";
import { Window } from "../../ui/Window";
import { RowActs } from "./ProjectRows";

interface Props {
  node: string;
  body: StorageBody;
  report: Report;
  now: number;
  opener?: RefObject<HTMLElement | null>;
  onKeep?: (project: string, branch: string | null, on: boolean) => void;
  onClose: () => void;
}

export function GoingNextWindow({ node, body, report, now, opener, onKeep, onClose }: Props) {
  const next = goingNext(report);
  const total = next.reduce((a, f) => a + f.size, 0);
  return (
    <Window title={node} icon={<HardDrive aria-hidden className="size-icon" />} opener={opener} onClose={onClose}
      note={`What goes next on its own: ${plural(next.length, "branch folder")}, ${bytes(total)}`}
      foot={(
        <>
          <p className="mr-auto min-w-0 flex-1 basis-col-m text-sm text-ink-2">
            A folder goes once no job used it for {plural(report.policy.unused_days, "day")}; the node cleans up every hour.
            {report.policy.keep_latest && " Each project's latest folder stays."}
          </p>
          <Button tone="ghost" onClick={onClose}>Close</Button>
        </>
      )}>
      {next.length ? (
        <div className="keep-list">
          {next.map((folder) => {
            const branch = branchOf(body, folder.project, folder.folder), kept = keptBranch(body, folder.project, branch);
            return (
              <div key={`${folder.project}/${folder.folder}`} className="keep-row">
                <span className="grid min-w-0">
                  <code className="min-w-0 font-mono text-sm wrap-anywhere">{branch ?? folder.folder}</code>
                  <span className="text-sm text-ink-2">{folder.project}</span>
                </span>
                <span className="keep-meta text-sm">
                  <strong className="num font-semibold">{bytes(folder.size)}</strong>
                  <span className="text-ink-2">{ago(folder.last_used, now)}</span>
                  <span className={folder.fate === "remove" || (folder.removed_in ?? 9) < 1 ? "font-medium" : "text-ink-2"}>
                    {kept ? "Kept by you from the next cleanup" : fateText(folder, report.policy)}</span>
                </span>
                <RowActs path={report.paths ? `${report.paths.projects}/${folder.project}/trees/${folder.folder}` : null}
                  what={branch ?? folder.folder} kept={kept}
                  locked={branch === null ? "mulebox does not know this folder's branch" : undefined}
                  onKeep={onKeep ? () => onKeep(folder.project, branch, !kept) : undefined} />
              </div>
            );
          })}
        </div>
      ) : <p className="text-ink-2">Nothing is due to go on its own on this node.</p>}
    </Window>
  );
}
