// The projects of a node's report: a row each, opening to its branch folders. Every row says
// its size, its last job and what happens to it, and has its three actions: copy its path,
// keep it (no automatic rule removes it, on any node), clean it (CleanConfirm first; on a
// project, only the folders that would go by themselves). An idle project's row asks whether
// to clean all of it. With the controls off only the copy stays.

import { ChevronRight, Clock, Flag, GitBranch, Lightbulb, LoaderCircle, Pin, Timer, Trash2, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";

import { ago, bytes, plural } from "../../lib/format";
import { branchOf, fateText, goingNext, keptBranch, keptProject, projectSize, suggestions,
         type Fate, type Folder, type Project, type Report, type StorageBody } from "../../lib/storage";
import { IconButton } from "../../ui/Button";
import { CopyButton } from "../../ui/Copy";
import { cx } from "../../ui/cx";
import { CleanConfirm } from "./CleanConfirm";

export interface Asking { project: string; folder: string | null; reset?: boolean }  // `reset`: the whole project
export interface Controls {
  editable: boolean;
  open: Set<string>;
  asking: Asking | null;
  busy: boolean;
  problem: string | null;
  toggle: (project: string) => void;
  keep: (project: string, branch: string | null, on: boolean) => void;
  ask: (asking: Asking | null) => void;
  remove: () => void;
}

const FATE_ICON: Record<Fate, LucideIcon> = { running: LoaderCircle, kept: Pin, latest: Flag, remove: Timer, stays: Clock };

export function FateLine({ icon: Icon, strong, tone, children }: { icon: LucideIcon; strong?: boolean; tone?: string; children: ReactNode }) {
  return (
    <span className={cx("inline-flex min-w-0 items-center gap-1", strong ? "font-medium text-ink-1" : "text-ink-2")}>
      <Icon aria-hidden className={cx("status-icon size-icon-s flex-none", tone ?? "text-ink-2")} />{children}
    </span>
  );
}

interface ActsProps { path: string | null; what: string; kept?: boolean; locked?: string; onKeep?: () => void; onClean?: () => void }
// Copy, keep, clean; a missing one leaves its place empty so the columns stay in line. `locked`
// says why this row can be neither kept nor cleaned.
export function RowActs({ path, what, kept, locked, onKeep, onClean }: ActsProps) {
  return (
    <span className="keep-acts">
      {path ? <CopyButton text={path} label={`Copy the path of ${what}`} /> : <span className="size-ctl-s" />}
      {onKeep ? (
        <IconButton small label={kept ? `Stop keeping ${what}` : `Keep ${what}`} aria-pressed={Boolean(kept)} disabled={Boolean(locked)}
          tip={locked ?? (kept ? "Kept by you: no automatic rule removes it. Press to drop the mark" : "Keep: no automatic rule removes it, on any node")}
          onClick={onKeep} className={kept ? "text-accent" : undefined}>
          <Pin aria-hidden className="size-icon-s" />
        </IconButton>
      ) : <span className="size-ctl-s max-touch:hidden" />}
      {onClean ? (
        <IconButton small label={`Clean ${what}`} disabled={Boolean(locked)} tip={locked ?? "Clean: lists what it removes first"} onClick={onClean}>
          <Trash2 aria-hidden className="size-icon-s" />
        </IconButton>
      ) : <span className="size-ctl-s max-touch:hidden" />}
    </span>
  );
}

function projectFate(project: Project, report: Report, body: StorageBody, ctl: Controls) {
  const idle = suggestions(report).find((found) => found.project === project.project);
  if (idle) {
    return (
      <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        <FateLine icon={Lightbulb} strong tone="text-warning">
          {idle.days === null ? "No job seen here" : `No job for ${plural(idle.days, "day")}`}. Clean it?</FateLine>
        {ctl.editable && (
          <button type="button" onClick={() => ctl.ask({ project: project.project, folder: null, reset: true })}
            className="font-medium underline touch:min-h-ctl-touch">Clean it</button>
        )}
      </span>
    );
  }
  if (keptProject(body, project.project)) return <FateLine icon={Pin} tone="text-accent">Kept by you</FateLine>;
  const next = goingNext(report).filter((f) => f.project === project.project);
  const soon = next.filter((f) => f.fate === "remove" || (f.removed_in ?? Infinity) < 1);
  if (soon.length) return <FateLine icon={Timer} strong>{plural(soon.length, "folder")} {soon.length === 1 ? "goes" : "go"} within a day</FateLine>;
  if (next.length) return <FateLine icon={Clock}>{fateText(next[0]).replace("Removed", "Next goes")}</FateLine>;
  return <FateLine icon={Flag}>Nothing goes on its own</FateLine>;
}

const lastJob = (folders: Folder[]) => Math.max(0, ...folders.map((f) => f.last_used ?? 0)) || null;
const NO_BRANCH = "mulebox does not know this folder's branch: clean the project instead";

const FIRST = 8;  // a project's folders before "more": the ones used last

interface FoldersProps { body: StorageBody; project: Project; home: string | null; now: number; ctl: Controls; asked: Asking | null }
function Folders({ body, project, home, now, ctl, asked }: FoldersProps) {
  const [all, setAll] = useState(false);
  const name = project.project;
  const sorted = [...project.folders].sort((a, b) => (b.last_used ?? 0) - (a.last_used ?? 0));
  const shown = all ? sorted : sorted.slice(0, FIRST);
  return (
    <div className="keep-sub">
      {shown.map((folder) => {
        const branch = branchOf(body, name, folder.folder), mine = keptBranch(body, name, branch);
        const busy = folder.fate === "running";
        return (
          <div key={folder.folder}>
            <div className="keep-row">
              <span className="flex min-w-0 items-center gap-2">
                <GitBranch aria-hidden className="size-icon-s flex-none text-ink-2" />
                <code className="min-w-0 font-mono text-sm wrap-anywhere">{branch ?? folder.folder}</code>
              </span>
              <span className="keep-meta text-sm">
                <strong className="num font-semibold">{bytes(folder.size)}</strong>
                <span className="text-ink-2">{ago(folder.last_used, now)}</span>
                <FateLine icon={FATE_ICON[folder.fate]} strong={folder.fate === "remove"}
                  tone={folder.fate === "kept" ? "text-accent" : folder.fate === "running" ? "text-running" : undefined}>{fateText(folder)}</FateLine>
              </span>
              <RowActs path={home && `${home}/trees/${folder.folder}`} what={branch ?? folder.folder}
                kept={mine} locked={branch === null ? NO_BRANCH : undefined}
                onKeep={ctl.editable ? () => ctl.keep(name, branch, !mine) : undefined}
                onClean={ctl.editable && !busy ? () => ctl.ask({ project: name, folder: folder.folder }) : undefined} />
            </div>
            {asked?.folder === folder.folder && (
              <CleanConfirm body={body} project={project} folder={folder.folder} busy={ctl.busy} problem={ctl.problem}
                onRemove={ctl.remove} onCancel={() => ctl.ask(null)} />
            )}
          </div>
        );
      })}
      {sorted.length > FIRST && (
        <p className="border-b border-line-strong py-2 pl-5 text-sm">
          <button type="button" onClick={() => setAll(!all)} className="font-medium underline touch:min-h-ctl-touch">
            {all ? "Show fewer" : `${sorted.length - FIRST} more branch folders`}
          </button>
        </p>
      )}
    </div>
  );
}

interface Props { body: StorageBody; report: Report; now: number; ctl: Controls }

export function ProjectRows({ body, report, now, ctl }: Props) {
  const home = (project: string) => (report.paths ? `${report.paths.projects}/${project}` : null);
  return (
    <>
      {[...report.projects].sort((a, b) => projectSize(b) - projectSize(a)).filter((p) => p.folders.length || p.home).map((project) => {
        const name = project.project, open = ctl.open.has(name), kept = keptProject(body, name);
        const asked = ctl.asking?.project === name ? ctl.asking : null;
        return (
          <div key={name}>
            <div className="keep-row">
              <button type="button" aria-expanded={open} onClick={() => ctl.toggle(name)}
                className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-left touch:min-h-ctl-touch">
                <ChevronRight aria-hidden className={cx("size-icon-s flex-none text-ink-2 transition-transform", open && "rotate-90")} />
                <strong className="font-semibold wrap-anywhere">{name}</strong>
                <span className="text-sm whitespace-nowrap text-ink-2">{plural(project.folders.length, "folder")}</span>
              </button>
              <span className="keep-meta text-sm">
                <strong className="num font-semibold">{bytes(projectSize(project) - project.caches)}</strong>
                <span className="text-ink-2">{ago(lastJob(project.folders), now)}</span>
                {projectFate(project, report, body, ctl)}
              </span>
              <RowActs path={home(name)} what={name} kept={kept}
                onKeep={ctl.editable ? () => ctl.keep(name, null, !kept) : undefined}
                onClean={ctl.editable ? () => ctl.ask({ project: name, folder: null }) : undefined} />
            </div>
            {asked && asked.folder === null && (
              <CleanConfirm body={body} project={project} folder={null} reset={asked.reset} busy={ctl.busy} problem={ctl.problem}
                onRemove={ctl.remove} onCancel={() => ctl.ask(null)} />
            )}
            {open && <Folders body={body} project={project} home={home(name)} now={now} ctl={ctl} asked={asked} />}
          </div>
        );
      })}
    </>
  );
}
