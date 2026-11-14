// A node's cleanups, newest first, for the owner to read back what mulebox removed and why:
// when each ran, what set it off, the folders it removed (each with its reason), what it freed
// in Docker, the free space before and after, and every error, word for word. The last 20, more
// on demand. Nothing is rounded away: a run that removed nothing is listed too.

import { ChevronRight, History, OctagonAlert } from "lucide-react";
import { useState } from "react";

import { ago, bytes, clock, plural } from "../../lib/format";
import { TRIGGERS, branchOf, whyText, type StorageBody, type Sweep } from "../../lib/storage";
import { cx } from "../../ui/cx";

const FIRST = 20;
const keyOf = (sweep: Sweep) => String(sweep.started);

function Detail({ sweep, body, days }: { sweep: Sweep; body: StorageBody; days: number }) {
  const docker = sweep.docker;
  return (
    <div className="grid gap-2 border-b border-line py-2 pl-5 text-sm">
      <p className="text-ink-2">
        Ran for {sweep.seconds} s with the automatic cleanup {sweep.auto ? "on" : "off"}.
        {sweep.would_remove > 0 && ` It removed nothing by itself: ${plural(sweep.would_remove, "folder")} would have gone.`}
      </p>
      {sweep.removed.length > 0 && (
        <ul className="grid gap-1">
          {sweep.removed.map((gone) => (
            <li key={`${gone.project}/${gone.folder}`} className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span className="min-w-0">
                <code className="font-mono wrap-anywhere">{branchOf(body, gone.project, gone.folder) ?? gone.folder}</code>{" "}
                <span className="text-ink-2">of {gone.project}: {whyText(gone.why, days)}</span>
              </span>
              <span className="num font-medium">{bytes(gone.size)}</span>
            </li>
          ))}
          {sweep.count > sweep.removed.length && <li className="text-ink-2">and {sweep.count - sweep.removed.length} more, not listed in the record</li>}
        </ul>
      )}
      {docker ? (
        <p>Docker: build cache <strong className="num font-medium">{bytes(docker.build_cache)}</strong>, images{" "}
          <strong className="num font-medium">{bytes(docker.images)}</strong> freed.
          {docker.removed.length > 0 && <> Images removed: <code className="font-mono wrap-anywhere">{docker.removed.join(", ")}</code>.</>}</p>
      ) : <p className="text-ink-2">Docker was not cleaned in this run.</p>}
      {sweep.errors.length > 0 && (
        <ul className="grid gap-1">
          {sweep.errors.map((error, index) => (
            <li key={index} className="flex items-start gap-2 font-medium">
              <OctagonAlert aria-hidden className="status-icon mt-px size-icon-s flex-none text-danger" />
              <span className="min-w-0 wrap-anywhere">{error}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

interface Props { sweeps: Sweep[]; body: StorageBody; days: number; now: number }

export function CleanupHistory({ sweeps, body, days, now }: Props) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [all, setAll] = useState(false);
  const shown = all ? sweeps : sweeps.slice(0, FIRST);
  const flip = (key: string) => setOpen((had) => { const next = new Set(had); if (!next.delete(key)) next.add(key); return next; });
  return (
    <section aria-label="Cleanup history" className="keep-list">
      <div className="sweep-head keep-head text-sm">
        <h3 className="flex items-center gap-2 font-semibold"><History aria-hidden className="size-icon-s flex-none" />Cleanup history
          <span className="font-normal text-ink-2">{sweeps.length ? `${sweeps.length} recorded, newest first` : ""}</span></h3>
        <div className="sweep-meta font-semibold text-ink-2"><span>Why it ran</span><span>Folders</span><span>Docker</span><span>Free space</span><span /></div>
      </div>
      {!sweeps.length && <p className="py-2 text-sm text-ink-2">No cleanup recorded yet. A node on mulebox 1.26 or later records each one.</p>}
      {shown.map((sweep) => {
        const key = keyOf(sweep), isOpen = open.has(key);
        const docker = sweep.docker ? sweep.docker.build_cache + sweep.docker.images : null;
        return (
          <div key={key}>
            <button type="button" aria-expanded={isOpen} onClick={() => flip(key)}
              className={cx("sweep-row w-full text-left hover:bg-surface-2", isOpen && "bg-surface-2")}>
              <span className="flex min-w-0 items-center gap-2">
                <ChevronRight aria-hidden className={cx("size-icon-s flex-none text-ink-2 transition-transform", isOpen && "rotate-90")} />
                <span className="num font-medium">{clock(sweep.started)}</span>
                <span className="text-sm whitespace-nowrap text-ink-2">{ago(sweep.started, now)}</span>
              </span>
              <span className="sweep-meta text-sm">
                <span>{TRIGGERS[sweep.trigger] ?? sweep.trigger}</span>
                <span className={sweep.count ? "num font-medium" : "num text-ink-2"}>
                  {sweep.count ? `${plural(sweep.count, "folder")} removed, ${bytes(sweep.bytes)}`
                    : sweep.would_remove ? `none removed; ${sweep.would_remove} would go` : "no folder removed"}</span>
                <span className={docker ? "num font-medium" : "num text-ink-2"}>{docker === null ? "Docker not cleaned" : `Docker ${bytes(docker)} freed`}</span>
                <span className="num">free {bytes(sweep.free_before)} to {bytes(sweep.free_after)}</span>
                <span className="inline-flex items-center gap-1 font-medium whitespace-nowrap">
                  {sweep.errors.length > 0 && <><OctagonAlert aria-hidden className="status-icon size-icon-s text-danger" />{plural(sweep.errors.length, "error")}</>}
                </span>
              </span>
            </button>
            {isOpen && <Detail sweep={sweep} body={body} days={days} />}
          </div>
        );
      })}
      {sweeps.length > FIRST && (
        <p className="py-2 text-sm">
          <button type="button" onClick={() => setAll(!all)} className="font-medium underline touch:min-h-ctl-touch">
            {all ? "Show the last 20" : `${sweeps.length - FIRST} earlier cleanups`}
          </button>
        </p>
      )}
    </section>
  );
}
