// The Storage tab of a node's settings window (the user's pick): how the node keeps its disk
// in check, a panel per setting in the window's own rows: what mulebox suggests, what the
// viewer set, what the node runs with. Above them one line says what the values on screen
// would do at the node's next cleanup, worked out from its last storage report, before a save.

import { Flag, HardDrive, Lightbulb, Shrink, Timer, TriangleAlert } from "lucide-react";
import { useId } from "react";

import { bytes, plural } from "../../lib/format";
import { DAYS_RANGE, HOURS_RANGE, LATEST, STORAGE_DEFAULTS, rowOf, type Draft, type NodeSettings, type SettingKey } from "../../lib/nodeSettings";
import { formatKeepFree, parseKeepFree, preview, previewText, reserveOf, type Report } from "../../lib/storage";
import { Panel } from "../../ui/Panel";
import { Segmented } from "../../ui/Segmented";
import { Stepper } from "../../ui/Stepper";
import { ROWS, Row, RunsWith, meaning } from "./SettingsRows";
import { hasLimits, useLimitPanels } from "./StorageLimits";

interface Props {
  view: NodeSettings;
  draft: Draft;
  report: Report | null;                    // the node's last storage report, for the sizes
  locked: boolean;
  busy: boolean;
  onEdit: (change: Draft) => void;
  onDrop: (key: SettingKey) => void;
}

const days = (n: number | null | undefined) => (typeof n === "number" ? plural(n, "day") : "-");
const hours = (n: number | null | undefined) => (typeof n !== "number" ? "-" : n === 0 ? "Never" : plural(n, "hour"));
const latest = (keep: boolean | null | undefined) => (keep === null || keep === undefined ? "-" : keep ? "Keep" : "Remove");
const UNITS = [{ value: "%", label: "%" }, { value: "GB", label: "GB" }];
const MAX_GB = 9999;

export function StorageSettings({ view, draft, report, locked, busy, onEdit, onDrop }: Props) {
  const says = useId();
  const known = typeof view.current?.keep_free === "string";  // a node older than 1.24 has none
  const off = locked || busy || !known;
  const defaults = { ...STORAGE_DEFAULTS, ...view.defaults };
  const free = rowOf(view, draft, "keep_free"), unused = rowOf(view, draft, "unused_days");
  const keep = rowOf(view, draft, "keep_latest"), idle = rowOf(view, draft, "idle_days");
  const mine = { keep_free: free.yours ?? defaults.keep_free, unused_days: unused.yours ?? defaults.unused_days,
                 keep_latest: keep.yours ?? defaults.keep_latest, idle_days: idle.yours ?? defaults.idle_days };
  const share = parseKeepFree(mine.keep_free) ?? { amount: 10, unit: "%" as const };
  const total = report?.disk.total ?? null;
  const size = (value: string) => (total === null ? null : reserveOf(value, total));
  const maxShare = view.choices?.keep_free?.max_share ?? 90;
  const range = (key: "unused_days" | "idle_days") => view.choices?.[key] ?? DAYS_RANGE;
  const drop = (key: SettingKey) => (locked ? undefined : () => onDrop(key));
  const setUnit = (unit: string) => {
    if (unit === share.unit) return;
    const gb = total === null ? 50 : Math.max(1, Math.round((total * share.amount) / 100 / 1e9));
    const pct = total === null ? 10 : Math.min(maxShare, Math.max(1, Math.round((100 * share.amount * 1e9) / total)));
    onEdit({ keep_free: formatKeepFree(unit === "GB" ? { amount: gb, unit: "GB" } : { amount: pct, unit: "%" }) });
  };
  const limits = known && hasLimits(view);
  const more = { auto_clean: rowOf(view, draft, "auto_clean").yours ?? defaults.auto_clean,
                 max_size: rowOf(view, draft, "max_size").yours ?? defaults.max_size };
  const panels = useLimitPanels({ view, draft, defaults, days: mine.unused_days, report, off, busy, onEdit, drop });
  const would = known && report ? preview(report, limits ? { ...mine, ...more } : mine, Date.now() / 1000) : null;
  const reserve = size(mine.keep_free);
  const thin = rowOf(view, draft, "slim_hours");
  const slims = typeof view.current?.slim_hours === "number";  // a node older than 1.29 slims nothing
  const slimHours = thin.yours ?? defaults.slim_hours;

  return (
    <div className="grid gap-gap">
      {!known ? (
        <p className="rounded-m border border-line-strong bg-surface-2 px-3 py-2">
          <strong className="font-semibold">{view.worker} runs a mulebox older than 1.24, which keeps no check on its disk.</strong>{" "}
          <span className="text-ink-2">Upgrade it to set these.</span>
        </p>
      ) : would && report && (
        <p role="status" className="flex items-start gap-2 rounded-m border border-line bg-surface-1 px-3 py-2 text-sm">
          {would.shortBy > 0 && <TriangleAlert aria-hidden className="status-icon mt-px size-icon-s flex-none text-warning" />}
          <span>{previewText(would, report)}</span>
        </p>
      )}
      <div className="@container">
        <div className="setting-panels">
          <Panel subgrid title="Free space to keep" label="Free space to keep" icon={<HardDrive aria-hidden className="size-icon" />} bodyClassName={ROWS}>
            {meaning("mulebox cleans up before the disk has less free than this")}
            <Row label="Suggested" note={size(defaults.keep_free) === null ? "a share of the node's disk" : `${bytes(size(defaults.keep_free))} of this node's ${bytes(total)} disk`}>
              <span className="num font-medium">{defaults.keep_free}</span>
            </Row>
            <Row label="Yours" note={reserve === null || !report ? undefined
              : `${bytes(reserve)}; the disk has ${bytes(report.disk.free)} free${reserve > report.disk.free ? ", less than that" : ""}`}>
              <span className="inline-flex flex-wrap items-start justify-end gap-2">
                <Stepper value={share.amount} min={1} max={share.unit === "%" ? maxShare : MAX_GB} label="Free space to keep"
                  unit={share.unit === "%" ? "percent" : "GB"} units={share.unit === "%" ? "percent" : "GB"} disabled={off}
                  onChange={(amount) => onEdit({ keep_free: formatKeepFree({ amount, unit: share.unit }) })} />
                <Segmented label="Unit of the free space to keep" value={share.unit} choices={UNITS} disabled={off} onChange={setUnit} />
              </span>
            </Row>
            <RunsWith now={free.now ?? null} yours={free.yours} mark={free.mark} online={view.online}
              same={free.now === defaults.keep_free} drop={drop("keep_free")} busy={busy} />
          </Panel>
          {limits && panels.maxSize}
          <Panel subgrid title="Unused branch folders" label="Unused branch folders" icon={<Timer aria-hidden className="size-icon" />} bodyClassName={ROWS}>
            {meaning("A branch folder goes after this long with no job")}
            <Row label="Suggested" note="the default for every node"><span className="num font-medium">{days(defaults.unused_days)}</span></Row>
            <Row label="Yours">
              <span className="ml-auto inline-flex items-center gap-2">
              <Stepper value={mine.unused_days} min={range("unused_days").min} max={range("unused_days").max} label="Days a branch folder may go unused"
                unit="day" disabled={off} onChange={(next) => onEdit({ unused_days: next })} />
              <span className="text-ink-2">days</span>
              </span>
            </Row>
            <RunsWith now={unused.now === null ? null : days(unused.now)} yours={days(unused.yours)} mark={unused.mark} online={view.online}
              same={unused.now === defaults.unused_days} drop={drop("unused_days")} busy={busy} />
          </Panel>
          {slims && (
            <Panel subgrid title="Slim idle folders" label="Slim idle folders" icon={<Shrink aria-hidden className="size-icon" />} bodyClassName={ROWS}>
              {meaning("A branch folder with no job this long loses what git ignores in it (installed packages, build output); its files stay, and its next job installs again")}
              <Row label="Suggested" note="the default for every node"><span className="num font-medium">{hours(defaults.slim_hours)}</span></Row>
              <Row label="Yours" note="0 never slims">
                <span className="ml-auto inline-flex items-center gap-2">
                <Stepper value={slimHours} min={view.choices?.slim_hours?.min ?? HOURS_RANGE.min} max={view.choices?.slim_hours?.max ?? HOURS_RANGE.max}
                  label="Hours before an idle branch folder is slimmed" unit="hour" disabled={off} onChange={(next) => onEdit({ slim_hours: next })} />
                <span className="text-ink-2">hours</span>
                </span>
              </Row>
              <RunsWith now={thin.now === null ? null : hours(thin.now)} yours={hours(thin.yours)} mark={thin.mark} online={view.online}
                same={thin.now === defaults.slim_hours} drop={drop("slim_hours")} busy={busy} />
            </Panel>
          )}
          <Panel subgrid title="Latest folder" label="Latest folder" icon={<Flag aria-hidden className="size-icon" />} bodyClassName={ROWS}>
            {meaning("What happens to each project's most recent folder")}
            <Row label="Suggested" note="so a project's next job after a break is still quick"><span className="font-medium">Keep</span></Row>
            <Row label="Yours" noteId={says} note={LATEST.find((choice) => choice.value === (mine.keep_latest ? "keep" : "remove"))?.says}>
              <Segmented label="Latest folder" describedBy={says} disabled={off} value={mine.keep_latest ? "keep" : "remove"} choices={LATEST}
                onChange={(next) => onEdit({ keep_latest: next === "keep" })} />
            </Row>
            <RunsWith now={keep.now === null ? null : latest(keep.now)} yours={latest(keep.yours)} mark={keep.mark} online={view.online}
              same={keep.now === defaults.keep_latest} drop={drop("keep_latest")} busy={busy} />
          </Panel>
          {limits && panels.auto}
          {limits && panels.docker}
          <Panel subgrid title="Idle projects" label="Idle projects" icon={<Lightbulb aria-hidden className="size-icon" />} bodyClassName={ROWS}>
            {meaning("A project with no job this long gets a suggestion to clean it, never a removal")}
            <Row label="Suggested" note="the default for every node"><span className="num font-medium">{days(defaults.idle_days)}</span></Row>
            <Row label="Yours">
              <span className="ml-auto inline-flex items-center gap-2">
              <Stepper value={mine.idle_days} min={range("idle_days").min} max={range("idle_days").max} label="Days before an idle project gets a suggestion"
                unit="day" disabled={off} onChange={(next) => onEdit({ idle_days: next })} />
              <span className="text-ink-2">days</span>
              </span>
            </Row>
            <RunsWith now={idle.now === null ? null : days(idle.now)} yours={days(idle.yours)} mark={idle.mark} online={view.online}
              same={idle.now === defaults.idle_days} drop={drop("idle_days")} busy={busy} />
          </Panel>
          {limits && panels.warn}
        </div>
      </div>
    </div>
  );
}
