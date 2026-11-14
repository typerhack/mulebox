// The disk of a node as one ruler: what mulebox holds by kind, everything else on the disk,
// the free space, and the reserve hatched at the far end, which the used part must not reach.
// The numbers are said in words above it and in the legend, so no colour says anything alone.

import { TriangleAlert } from "lucide-react";
import type { CSSProperties } from "react";

import { bytes } from "../../lib/format";
import { headroom, held, parts, type PartKey, type Report } from "../../lib/storage";
import { cx } from "../../ui/cx";

const COLOUR: Record<PartKey, string> = {
  folders: "bg-chart-1", caches: "bg-chart-2", tools: "bg-chart-3", runners: "bg-chart-4", other: "bg-chart-5",
};
const share = (size: number, total: number) => ({ "--v": `${((100 * Math.max(0, size)) / total).toFixed(2)}%` }) as CSSProperties;

interface Props {
  report: Report;
  would?: number;        // bytes a removal would free, drawn hatched in place of branch folders
  legend?: boolean;
}

export function DiskRuler({ report, would = 0, legend }: Props) {
  const { total, free, reserve } = report.disk;
  const mine = parts(report), all = held(report), rest = Math.max(0, total - free - all);
  const room = headroom(report), after = room + would;
  const reserveShare = { width: `${((100 * Math.min(reserve, total)) / total).toFixed(2)}%` };
  return (
    <div className="grid min-w-0 gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-sm">
        <span><strong className="num text-xl font-semibold tracking-tight">{bytes(free)}</strong> free of {bytes(total)}
          {would > 0 && <>, <strong className="num font-semibold">{bytes(free + would)}</strong> after</>}</span>
        <span className="num inline-flex items-center gap-1">
          {after < 0 && <TriangleAlert aria-hidden className="status-icon size-icon-s text-warning" />}
          <strong className="font-semibold">{bytes(Math.abs(after))}</strong> {after < 0 ? "under" : "above"} the reserve of{" "}
          <strong className="font-semibold">{bytes(reserve)}</strong> ({report.policy.keep_free}){would > 0 && " after"}
        </span>
      </div>
      <div className="ruler" data-short={room < 0 || undefined} role="img"
        aria-label={`Disk: mulebox holds ${bytes(all)}, everything else ${bytes(rest)}, ${bytes(free)} free, of which ${bytes(reserve)} is the reserve`}>
        {mine.filter((part) => part.size > 0).map((part) => (
          <i key={part.key} className={COLOUR[part.key]} style={share(part.key === "folders" ? part.size - would : part.size, total)} />
        ))}
        {would > 0 && <i className="would hatch" style={share(would, total)} />}
        <i className="bg-surface-3" style={share(rest, total)} />
        <i className="reserve hatch" style={reserveShare} />
      </div>
      {legend && (
        <ul className="legend text-sm">
          {mine.map((part) => (
            <li key={part.key}><i className={cx("swatch", COLOUR[part.key])} /><span className="text-ink-2">{part.label}</span>
              <strong className="num font-semibold">{bytes(part.size)}</strong></li>
          ))}
          <li><i className="swatch bg-surface-3" /><span className="text-ink-2">Everything else on the disk</span>
            <strong className="num font-semibold">{bytes(rest)}</strong></li>
          <li><i className="swatch" /><span className="text-ink-2">Free</span><strong className="num font-semibold">{bytes(free)}</strong></li>
          <li><i className="swatch hatch border-ink-1" /><span className="text-ink-2">Reserve</span>
            <strong className="num font-semibold">{bytes(reserve)}</strong></li>
        </ul>
      )}
    </div>
  );
}
