// "Space for mulebox" in a node's Storage tab (common/storage_policy.py, 1.30): one panel for
// the two settings about how much of the disk mulebox takes. The space it may use (`max_size`):
// past it the oldest folders are slimmed, then removed, and agents are told from 80% of it. The
// disk floor (`keep_free`): what the disk itself keeps free, which counts only when the disk is
// nearly full for another reason. Side by side when the window is wide, one under the other on
// a phone; each with what mulebox suggests, what the viewer set and what the node runs with.

import { HardDrive } from "lucide-react";
import type { ReactNode } from "react";

import { bytes } from "../../lib/format";
import { OFF, ON_OFF, rowOf, type Draft, type NodeSettings, type SettingKey } from "../../lib/nodeSettings";
import { formatKeepFree, held, parseKeepFree, reserveOf, sizeBytes, sizeLabel, type Report } from "../../lib/storage";
import { Panel } from "../../ui/Panel";
import { Segmented } from "../../ui/Segmented";
import { Stepper } from "../../ui/Stepper";
import { ROWS, Row, RunsWith, meaning } from "./SettingsRows";

interface Props {
  view: NodeSettings;
  draft: Draft;
  defaults: { keep_free: string; max_size: string };
  report: Report | null;
  limits: boolean;                          // the node reports `max_size` (1.26 and later)
  off: boolean;
  busy: boolean;
  onEdit: (change: Draft) => void;
  drop: (key: SettingKey) => (() => void) | undefined;
}

const WARN_SHARE = 0.8;  // common/storage_policy.py
const MAX_GB = 99999;
const UNITS = [{ value: "%", label: "%" }, { value: "GB", label: "GB" }];
const gbOf = (size: string | null | undefined) => {
  const found = parseKeepFree(size);
  return found?.unit === "GB" ? found.amount : null;
};

// Each part sets its title and rows on the rows of the grid around it (`.setting-panel`, as the
// panels side by side do), so the two parts' meaning, Suggested, Yours and Runs with line up.
export function Part({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="setting-panel min-w-0">
      <h3 className="pb-2 text-sm font-semibold">{title}</h3>
      <div className={`setting-panel-body ${ROWS}`}>{children}</div>
    </section>
  );
}

export function SpaceSettings({ view, draft, defaults, report, limits, off, busy, onEdit, drop }: Props) {
  const now = report ? held(report) : null;
  const total = report?.disk.total ?? null;
  const most = rowOf(view, draft, "max_size");
  const mostValue = most.yours ?? defaults.max_size;
  const gb = gbOf(mostValue), limit = sizeBytes(mostValue);
  const free = rowOf(view, draft, "keep_free");
  const share = parseKeepFree(free.yours ?? defaults.keep_free) ?? { amount: 10, unit: "%" as const };
  const reserve = total === null ? null : reserveOf(formatKeepFree(share), total);
  const suggestedReserve = total === null ? null : reserveOf(defaults.keep_free, total);
  const maxShare = view.choices?.keep_free?.max_share ?? 90;
  const setUnit = (unit: string) => {
    if (unit === share.unit) return;
    const inGb = total === null ? 50 : Math.max(1, Math.round((total * share.amount) / 100 / 1e9));
    const pct = total === null ? 10 : Math.min(maxShare, Math.max(1, Math.round((100 * share.amount * 1e9) / total)));
    onEdit({ keep_free: formatKeepFree(unit === "GB" ? { amount: inGb, unit: "GB" } : { amount: pct, unit: "%" }) });
  };
  const mostNote = limit === null
    ? `No limit and no warning${now === null ? "" : `; mulebox holds ${bytes(now)} now`}`
    : `Agents are told from ${bytes(limit * WARN_SHARE)}${now === null ? "" : `; mulebox holds ${bytes(now)} now${now > limit ? ", more than that" : ""}`}`;

  return (
    <Panel title="Space for mulebox" label="Space for mulebox" icon={<HardDrive aria-hidden className="size-icon" />} className="col-span-full">
      <div className="setting-parts">
        {limits && (
          <Part title="Space it may use">
            {meaning("Everything mulebox keeps on this node. Past it the oldest folders are slimmed, then removed, never a running, kept or latest one; agents are told from 80% of it and ask you for more")}
            <Row label="Suggested" note="the default for every node"><span className="num font-medium">{sizeLabel(defaults.max_size)}</span></Row>
            <Row label="Yours" note={mostNote}>
              <span className="ml-auto inline-flex flex-wrap items-center justify-end gap-2">
                {gb !== null && (
                  <>
                    <Stepper value={gb} min={1} max={MAX_GB} label="Space mulebox may use" unit="GB" units="GB" disabled={off}
                      onChange={(next) => onEdit({ max_size: `${next}GB` })} />
                    <span className="text-ink-2">GB</span>
                  </>
                )}
                <Segmented label="Space mulebox may use: on or off" disabled={off} value={gb === null ? "off" : "on"} choices={ON_OFF}
                  onChange={(next) => onEdit({ max_size: next === "on" ? `${gbOf(most.now) ?? gbOf(defaults.max_size) ?? 20}GB` : OFF })} />
              </span>
            </Row>
            <RunsWith now={most.now === null ? null : sizeLabel(most.now)} yours={sizeLabel(most.yours)} mark={most.mark}
              online={view.online} same={most.now === defaults.max_size} drop={drop("max_size")} busy={busy} />
          </Part>
        )}
        <Part title="Disk floor">
          {meaning("Free space the disk itself keeps. It counts only when the disk is nearly full for another reason: then mulebox cleans up early")}
          <Row label="Suggested" note={suggestedReserve === null ? "a share of the node's disk" : `${bytes(suggestedReserve)} of this node's ${bytes(total)} disk`}>
            <span className="num font-medium">{defaults.keep_free}</span>
          </Row>
          <Row label="Yours" note={reserve === null || !report ? undefined
            : `${bytes(reserve)}; the disk has ${bytes(report.disk.free)} free${reserve > report.disk.free ? ", less than that" : ""}`}>
            <span className="inline-flex flex-wrap items-start justify-end gap-2">
              <Stepper value={share.amount} min={1} max={share.unit === "%" ? maxShare : MAX_GB} label="Disk floor"
                unit={share.unit === "%" ? "percent" : "GB"} units={share.unit === "%" ? "percent" : "GB"} disabled={off}
                onChange={(amount) => onEdit({ keep_free: formatKeepFree({ amount, unit: share.unit }) })} />
              <Segmented label="Unit of the disk floor" value={share.unit} choices={UNITS} disabled={off} onChange={setUnit} />
            </span>
          </Row>
          <RunsWith now={free.now ?? null} yours={free.yours} mark={free.mark} online={view.online}
            same={free.now === defaults.keep_free} drop={drop("keep_free")} busy={busy} />
        </Part>
      </div>
    </Panel>
  );
}
