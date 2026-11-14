// The Storage tab's settings of a node on 1.26 or later (common/storage_policy.py): whether it
// cleans up on its own and Docker too, the most mulebox may hold, and the size past which agents
// are warned. Each in the window's own rows: what mulebox suggests, what the viewer set, what
// the node runs with. A node older than 1.26 reports none of them, and they are not shown.

import { Boxes, BrushCleaning, Gauge, Megaphone } from "lucide-react";
import { useId } from "react";

import { bytes, plural } from "../../lib/format";
import { OFF, ON_OFF, rowOf, type Draft, type NodeSettings, type SettingKey } from "../../lib/nodeSettings";
import { held, parseKeepFree, sizeBytes, sizeLabel, type Report } from "../../lib/storage";
import { Panel } from "../../ui/Panel";
import { Segmented } from "../../ui/Segmented";
import { Stepper } from "../../ui/Stepper";
import { ROWS, Row, RunsWith, meaning } from "./SettingsRows";

interface Props {
  view: NodeSettings;
  draft: Draft;
  defaults: Required<Pick<Draft, "auto_clean" | "docker_clean" | "max_size" | "warn_size">>;
  days: number;                             // the unused days on screen, which Docker's cleanup follows too
  report: Report | null;
  off: boolean;                             // nothing can be edited now
  busy: boolean;
  onEdit: (change: Draft) => void;
  drop: (key: SettingKey) => (() => void) | undefined;
}

const MAX_GB = 99999;
const onOff = (value: boolean | null | undefined) => (value === null || value === undefined ? "-" : value ? "On" : "Off");
const gbOf = (size: string | null | undefined) => {
  const found = parseKeepFree(size);
  return found?.unit === "GB" ? found.amount : null;
};

// Whether the node reports the settings of 1.26.
export const hasLimits = (view: NodeSettings) => typeof view.current?.auto_clean === "boolean";

type FlagKey = "auto_clean" | "docker_clean";
type SizeKey = "max_size" | "warn_size";

// The four panels, apart, for the tab to place each beside its kin.
export function useLimitPanels({ view, draft, defaults, days, report, off, busy, onEdit, drop }: Props) {
  const ids = { auto_clean: useId(), docker_clean: useId() };
  const auto = rowOf(view, draft, "auto_clean");
  const autoOn = auto.yours ?? defaults.auto_clean;
  const now = report ? held(report) : null;

  const flag = (key: FlagKey, says: { on: string; off: string }) => {
    const row = rowOf(view, draft, key);
    const value = row.yours ?? defaults[key];
    return (
      <>
        <Row label="Suggested" note="the default for every node"><span className="font-medium">{onOff(defaults[key])}</span></Row>
        <Row label="Yours" noteId={ids[key]} note={value ? says.on : says.off}>
          <Segmented label={key === "auto_clean" ? "Clean up on its own" : "Clean Docker too"} describedBy={ids[key]}
            disabled={off} value={value ? "on" : "off"} choices={ON_OFF} onChange={(next) => onEdit({ [key]: next === "on" })} />
        </Row>
        <RunsWith now={row.now === null ? null : onOff(row.now)} yours={onOff(row.yours)} mark={row.mark} online={view.online}
          same={row.now === defaults[key]} drop={drop(key)} busy={busy} />
      </>
    );
  };

  const size = (key: SizeKey, label: string, start: number, none: string, note: (limit: number) => string) => {
    const row = rowOf(view, draft, key);
    const value = row.yours ?? defaults[key];
    const gb = gbOf(value);
    const limit = sizeBytes(value);
    const turnOn = () => onEdit({ [key]: `${gbOf(row.now) ?? gbOf(defaults[key]) ?? start}GB` });
    return (
      <>
        <Row label="Suggested" note={defaults[key] === OFF ? "no limit: the free space to keep guards the disk" : "the default for every node"}>
          <span className="num font-medium">{sizeLabel(defaults[key])}</span>
        </Row>
        <Row label="Yours" note={limit === null ? (now === null ? none : `${none}; mulebox holds ${bytes(now)} now`)
                                  : now === null ? undefined : note(limit)}>
          <span className="ml-auto inline-flex flex-wrap items-center justify-end gap-2">
            {gb !== null && (
              <>
                <Stepper value={gb} min={1} max={MAX_GB} label={label} unit="GB" units="GB" disabled={off}
                  onChange={(next) => onEdit({ [key]: `${next}GB` })} />
                <span className="text-ink-2">GB</span>
              </>
            )}
            <Segmented label={`${label}: on or off`} disabled={off} value={gb === null ? "off" : "on"} choices={ON_OFF}
              onChange={(next) => (next === "on" ? turnOn() : onEdit({ [key]: OFF }))} />
          </span>
        </Row>
        <RunsWith now={row.now === null ? null : sizeLabel(row.now)} yours={sizeLabel(row.yours)} mark={row.mark}
          online={view.online} same={row.now === defaults[key]} drop={drop(key)} busy={busy} />
      </>
    );
  };

  const holds = (limit: number) => `mulebox holds ${bytes(now)} now${now !== null && now > limit ? ", more than that" : ""}`;
  return {
    maxSize: (
      <Panel subgrid title="Most mulebox may use" label="Most mulebox may use" icon={<Gauge aria-hidden className="size-icon" />} bodyClassName={ROWS}>
        {meaning("Past this, its oldest folders go, never a running, kept or latest one")}
        {size("max_size", "Most mulebox may use", 100, "No limit", holds)}
      </Panel>
    ),
    auto: (
      <Panel subgrid title="Clean up on its own" label="Clean up on its own" icon={<BrushCleaning aria-hidden className="size-icon" />} bodyClassName={ROWS}>
        {meaning("Whether the node removes what the rules above allow")}
        {flag("auto_clean", {
          on: "Each cleanup removes what the rules allow.",
          off: "Removes nothing by itself: the Storage page says what would go, and you clean it.",
        })}
      </Panel>
    ),
    docker: (
      <Panel subgrid title="Clean Docker too" label="Clean Docker too" icon={<Boxes aria-hidden className="size-icon" />} bodyClassName={ROWS}>
        {meaning("Build cache and images, never volumes")}
        {flag("docker_clean", {
          on: `${autoOn ? "Each cleanup" : "A cleanup you start"} also removes Docker build cache, dangling images and images mulebox's jobs pulled, once unused for ${plural(days, "day")}. Never volumes, or images mulebox never used.`,
          off: "Leaves Docker as it is.",
        })}
      </Panel>
    ),
    warn: (
      <Panel subgrid title="Warn agents over" label="Warn agents over" icon={<Megaphone aria-hidden className="size-icon" />} bodyClassName={ROWS}>
        {meaning("Past this, every command an agent runs tells it to tell you")}
        {size("warn_size", "Warn agents over", 50, "No warning", (limit) => `${holds(limit)}${now !== null && now > limit ? ": agents are told" : ""}`)}
      </Panel>
    ),
  };
}
