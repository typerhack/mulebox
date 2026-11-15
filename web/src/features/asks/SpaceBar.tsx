// The space for mulebox on a node as one bar, around a request for more: what mulebox holds,
// the limit now, the part a yes adds (hatched), and the dotted mark from which agents are told
// again. One sentence under it says what the value does, the disk's floor included; it follows
// the value as the owner changes it. Every number is also in words, so no colour says it alone.

import { Info, TriangleAlert } from "lucide-react";
import type { CSSProperties } from "react";

import type { NodeRoom } from "../../lib/asks";
import { spaceSentence, WARN_SHARE } from "../../lib/asksText";
import { bytes } from "../../lib/format";
import { sizeBytes } from "../../lib/storage";
import { cx } from "../../ui/cx";

const GB = 1e9;
const at = (part: number, scale: number) => `${((100 * Math.max(0, Math.min(part, scale))) / scale).toFixed(2)}%`;

export function SpaceBar({ node, room, value }: { node: string; room: NodeRoom; value: number }) {
  const limit = sizeBytes(room.limit) ?? room.held;
  const scale = Math.max(value, limit, room.held) + 10 * GB;
  const share = limit > 0 ? Math.round((room.held / limit) * 100) : 0, warn = share >= WARN_SHARE * 100;
  const said = spaceSentence({ held: room.held, value, free: room.free, floor: room.floor });
  const marks = { "--p-held": at(room.held, scale), "--p-limit": at(limit, scale), "--p-to": at(value, scale),
                  "--p-tell": at(value * WARN_SHARE, scale) } as CSSProperties;
  return (
    <div className="grid min-w-0 gap-2 rounded-m border border-line bg-surface-2 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-sm">
        <span><strong className="num text-xl font-semibold tracking-tight">{bytes(room.held)}</strong> held by mulebox on {node}, of{" "}
          <strong className="num font-semibold">{bytes(limit)}</strong></span>
        <span className="inline-flex items-center gap-1 font-semibold">
          {warn && <TriangleAlert aria-hidden className="status-icon size-icon-s text-warning" />}
          <span className="num">{share}%</span> of its limit
        </span>
      </div>
      <div className="space-bar" role="img" style={marks} data-level={warn ? "warn" : undefined}
        aria-label={`mulebox holds ${bytes(room.held)} of a limit of ${bytes(limit)}; the limit would be ${bytes(value)}`}>
        <i className="room" /><i className="more hatch" /><i className="held" /><i className="now" /><i className="tell" />
      </div>
      <ul className="space-key text-sm text-ink-2">
        <li><i className="swatch held" data-level={warn ? "warn" : undefined} />held now</li>
        <li><i className="swatch line" />limit now, <strong className="num font-semibold text-ink-1">{bytes(limit)}</strong></li>
        <li><i className="swatch more hatch" />added, to <strong className="num font-semibold text-ink-1">{bytes(value)}</strong></li>
        <li><i className="swatch dots" />agents told from <strong className="num font-semibold text-ink-1">{bytes(value * WARN_SHARE)}</strong></li>
      </ul>
      <p className="flex max-w-read items-start gap-2 text-sm">
        {said.warn ? <TriangleAlert aria-hidden className="status-icon mt-px size-icon-s flex-none text-warning" />
          : <Info aria-hidden className="mt-px size-icon-s flex-none text-ink-2" />}
        <span className={cx(said.warn && "font-medium")}>{said.text}</span>
      </p>
      <dl className="space-facts text-sm">
        <div><dt className="text-ink-2">The cleanup can still free</dt><dd className="num font-semibold">{bytes(room.clean)}</dd></div>
        <div><dt className="text-ink-2">Disk free</dt><dd className="num font-semibold">{bytes(room.free)}{" "}
          <span className="font-normal text-ink-2">of {bytes(room.total)}</span></dd></div>
        <div><dt className="text-ink-2">Disk floor</dt><dd className="num font-semibold">{bytes(room.floor)}{" "}
          <span className="font-normal text-ink-2">{room.keepFree} kept free</span></dd></div>
      </dl>
    </div>
  );
}
