// Before anything is removed: what goes, what stays, what that frees, and the one red button
// that does it. Clean on a project's row removes its branch folders that would go by themselves
// anyway, one request each; the latest, kept and running ones stay. Only an idle project's
// "Clean it" removes the whole project (`mulebox project reset --yes`): latest folder and
// repository too, on every node, package caches kept. A branch's row removes that folder.

import { Trash2 } from "lucide-react";

import { bytes, plural } from "../../lib/format";
import { branchOf, cleanable, foldersSize, type Project, type StorageBody } from "../../lib/storage";
import { Button } from "../../ui/Button";

const SHOWN = 5;
const WHY: Record<string, string> = { latest: "the latest", kept: "kept by you", running: "a job runs in it" };

interface Props {
  body: StorageBody;
  project: Project;
  folder: string | null;       // one branch folder, or null for the project
  reset?: boolean;             // the whole project, its latest folder and repository too
  busy: boolean;
  problem: string | null;
  onRemove: () => void;
  onCancel: () => void;
}

export function CleanConfirm({ body, project, folder, reset, busy, problem, onRemove, onCancel }: Props) {
  const one = folder === null ? null : project.folders.find((f) => f.folder === folder) ?? null;
  const name = (f: string) => branchOf(body, project.project, f) ?? f;
  const { goes, stays, unknown } = cleanable(body, project);
  const listed = [...(reset ? project.folders : goes)].sort((a, b) => b.size - a.size);
  const sum = (folders: { size: number }[]) => folders.reduce((a, f) => a + f.size, 0);
  const frees = one ? one.size : reset ? foldersSize(project) + project.home : sum(goes);
  const nothing = !one && !reset && !goes.length;
  return (
    <div role="group" aria-label={`Clean ${one ? name(one.folder) : project.project}`}
      className="my-2 grid gap-3 rounded-m border border-line-strong bg-surface-2 p-3">
      {one ? (
        <p><strong className="font-semibold">Remove the folder of <code className="font-mono">{name(one.folder)}</code>:</strong>{" "}
          on every node that has it. That frees <strong className="num font-semibold">{bytes(one.size)}</strong> here.
          The branch's next job sets its folder up again.</p>
      ) : reset ? (
        <p><strong className="font-semibold">Clean all of {project.project}:</strong> removes its{" "}
          {plural(project.folders.length, "branch folder")}, the latest and any kept one too, and its repository, on every node.
          That frees <strong className="num font-semibold">{bytes(frees)}</strong> here.
          {project.caches > 0 && ` Its package caches (${bytes(project.caches)}) stay.`} Its next job sets it up from nothing.</p>
      ) : nothing ? (
        <p><strong className="font-semibold">Nothing to clean in {project.project}.</strong>{" "}
          Its {plural(project.folders.length, "folder")} {project.folders.length === 1 ? "is" : "are"} the latest, kept, in use, or of a branch mulebox does not know.</p>
      ) : (
        <p><strong className="font-semibold">Clean {project.project}:</strong> removes {plural(goes.length, "branch folder")} on every
          node that has them and frees <strong className="num font-semibold">{bytes(frees)}</strong> here.
          A removed branch's next job sets its folder up again.</p>
      )}
      {!one && listed.length > 0 && (
        <ul className="grid gap-1 text-sm">
          {listed.slice(0, SHOWN).map((f) => (
            <li key={f.folder} className="flex items-baseline justify-between gap-3">
              <code className="min-w-0 font-mono wrap-anywhere">{name(f.folder)}</code>
              <span className="num text-ink-2">{bytes(f.size)}</span>
            </li>
          ))}
          {listed.length > SHOWN && (
            <li className="flex items-baseline justify-between gap-3">
              <span>and {listed.length - SHOWN} more</span><span className="num text-ink-2">{bytes(sum(listed.slice(SHOWN)))}</span>
            </li>
          )}
        </ul>
      )}
      {!one && !reset && (stays.length > 0 || unknown.length > 0) && (
        <ul className="grid gap-1 text-sm text-ink-2">
          {stays.map((f) => (
            <li key={f.folder} className="flex items-baseline justify-between gap-3">
              <span className="min-w-0">Stays: <code className="font-mono wrap-anywhere">{name(f.folder)}</code> ({WHY[f.fate]})</span>
              <span className="num">{bytes(f.size)}</span>
            </li>
          ))}
          {unknown.length > 0 && (
            <li className="flex items-baseline justify-between gap-3">
              <span className="min-w-0">Stays: {plural(unknown.length, "folder")} of a branch mulebox does not know, which cannot be removed from here</span>
              <span className="num">{bytes(sum(unknown))}</span>
            </li>
          )}
        </ul>
      )}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <p className="mr-auto min-w-0 flex-1 basis-col-s text-sm text-ink-2">
          {problem ? <strong role="alert" className="font-semibold text-ink-1">Not all removed. {problem}</strong>
            : reset ? "Refused while a job of the project runs." : "A folder is refused while a job runs in it."}
        </p>
        <Button tone="ghost" disabled={busy} onClick={onCancel}>Cancel</Button>
        <Button tone="danger" disabled={busy || nothing} onClick={onRemove}>
          <Trash2 aria-hidden className="size-icon-s" />
          {busy ? "Removing" : one ? "Remove the folder" : reset ? "Remove the whole project" : `Remove ${plural(goes.length, "folder")}`}
        </Button>
      </div>
    </div>
  );
}
