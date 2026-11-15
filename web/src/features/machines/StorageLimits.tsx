// The Storage tab's settings of a node on 1.26 or later (common/storage_policy.py): whether it
// cleans up on its own and Docker too (the space mulebox may use is in SpaceSettings.tsx). Each in the window's own rows: what mulebox suggests, what the viewer set, what
// the node runs with. A node older than 1.26 reports none of them, and they are not shown.

import { Boxes, BrushCleaning } from "lucide-react";
import { useId } from "react";

import { plural } from "../../lib/format";
import { ON_OFF, rowOf, type Draft, type NodeSettings, type SettingKey } from "../../lib/nodeSettings";
import { Panel } from "../../ui/Panel";
import { Segmented } from "../../ui/Segmented";
import { ROWS, Row, RunsWith, meaning } from "./SettingsRows";

interface Props {
  view: NodeSettings;
  draft: Draft;
  defaults: Required<Pick<Draft, "auto_clean" | "docker_clean">>;
  days: number;                             // the unused days on screen, which Docker's cleanup follows too
  off: boolean;                             // nothing can be edited now
  busy: boolean;
  onEdit: (change: Draft) => void;
  drop: (key: SettingKey) => (() => void) | undefined;
}

const onOff = (value: boolean | null | undefined) => (value === null || value === undefined ? "-" : value ? "On" : "Off");

// Whether the node reports the settings of 1.26.
export const hasLimits = (view: NodeSettings) => typeof view.current?.auto_clean === "boolean";

type FlagKey = "auto_clean" | "docker_clean";

// The two panels, apart, for the tab to place each beside its kin.
export function useLimitPanels({ view, draft, defaults, days, off, busy, onEdit, drop }: Props) {
  const ids = { auto_clean: useId(), docker_clean: useId() };
  const auto = rowOf(view, draft, "auto_clean");
  const autoOn = auto.yours ?? defaults.auto_clean;

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

  return {
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
  };
}
