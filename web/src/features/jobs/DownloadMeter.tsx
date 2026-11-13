// A running card's Down meter, under Cores (design-system/download-progress-mockup.html,
// option A): it fills when the total is known and is an open, dashed track when not, with
// what downloads and how fast on a line below. Once no byte has moved for a while the fill
// and a warning icon take the warning colour, and the line says for how long. Not load, so
// it keeps one solid fill in both meter styles. A GitHub run's figures are a floor, so its
// amount reads "at least". Where the card is narrow the amount takes its own row, right-aligned
// under the track, rather than squeezing the track away.

import { TriangleAlert } from "lucide-react";

import { downloadView } from "../../lib/download";
import type { Download } from "../../lib/types";
import { MeterBar } from "../../ui/Meter";

interface Props {
  download: Download | null | undefined;
  trails?: boolean;   // a GitHub run: its runner writes output in blocks, so the figures trail
}

export function DownloadMeter({ download, trails = false }: Props) {
  const view = downloadView(download, trails);
  if (!view) return null;
  const floor = trails ? "A GitHub runner writes its output in blocks, so this trails" : null;
  const aged = view.age !== null && view.age >= 5 ? `figures from ${Math.round(view.age)} s ago` : null;
  const open = view.sized ? "How much has arrived is not known" : "Downloaded so far; the total is not known";
  const note = [floor, aged].filter(Boolean).join(", ") || undefined;
  return (
    <>
      <div className="meter-row meter-wrap">
        <span className="truncate text-sm text-ink-2">Down</span>
        {view.share === null
          ? <span role="img" aria-label={open} title={open} className="track-open" />
          : <MeterBar value={view.share} level={view.quiet ? "warn" : null} className="meter-flat"
              label={`Downloaded ${view.amount}`} />}
        <span title={note} className="num text-right text-sm font-medium">{view.amount}</span>
      </div>
      {view.quiet ? (
        <p className="flex min-w-0 flex-wrap items-center gap-x-2 text-sm text-ink-2">
          <TriangleAlert aria-hidden className="status-icon size-icon-s text-warning" />
          <b className="font-medium whitespace-nowrap text-ink-1">{view.quiet}</b>
          {view.subject && <span className="min-w-0 wrap-anywhere">{view.subject}</span>}
        </p>
      ) : (
        <p className="flex min-w-0 flex-wrap items-center gap-x-2 text-sm text-ink-2">
          <span className="min-w-0 wrap-anywhere">{view.subject ? `Downloading ${view.subject}` : "Downloading"}</span>
          {view.speed && (
            <span className="num" title={view.wholeNode ? "All traffic into the node, not this job's alone" : undefined}>
              {view.speed}{view.wholeNode ? ", whole node" : ""}
            </span>
          )}
        </p>
      )}
    </>
  );
}
