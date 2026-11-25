// "Room for you" in a node's Jobs tab (the user's pick, option A of design-system/owner-room/):
// the cores and memory a node keeps for its owner (`keep_cores`, `keep_memory`; docs/design.md,
// Job sizes). Jobs that declare a size share only what is left; a job with no size takes one slot
// as before. Each part has what mulebox suggests (nothing kept), what the viewer set, and what the
// node runs with, as every setting here does.

import { Monitor } from "lucide-react";

import { plural } from "../../lib/format";
import { ROOM_DEFAULTS, memoryGb, rowOf, type Draft, type NodeSettings, type SettingKey } from "../../lib/nodeSettings";
import { Panel } from "../../ui/Panel";
import { Stepper } from "../../ui/Stepper";
import { Row, RunsWith, meaning } from "./SettingsRows";
import { Part } from "./SpaceSettings";

interface Props {
  view: NodeSettings;
  draft: Draft;
  cores: number | null;                      // the node's own, as it reports them
  off: boolean;
  busy: boolean;
  onEdit: (change: Draft) => void;
  drop: (key: SettingKey) => (() => void) | undefined;
}

const gb = (value: number) => `${value} GB`;
const share = (kept: number, total: number | null, words: (n: number) => string) =>
  total === null ? (kept ? `${words(kept)} kept for you` : "Jobs with a size share all of it")
    : kept ? `Jobs with a size share ${Math.max(0, total - kept)} of ${words(total)}`
    : `Jobs with a size share all ${words(total)}`;

export function OwnerRoom({ view, draft, cores, off, busy, onEdit, drop }: Props) {
  const keptCores = rowOf(view, draft, "keep_cores"), keptMemory = rowOf(view, draft, "keep_memory");
  const maxCores = view.choices?.keep_cores?.max ?? cores ?? 1024;
  const totalGb = view.choices?.keep_memory?.max_gb ?? null;
  const coresYours = keptCores.yours ?? 0;
  const memoryYours = memoryGb(keptMemory.yours) ?? 0;
  const coreWords = (n: number) => plural(n, "core");
  return (
    <Panel title="Room for you" label="Room for you" icon={<Monitor aria-hidden className="size-icon" />} className="col-span-full">
      {meaning("For a node that is also your PC. Jobs that say their size share what is left; a job with no size takes one slot, as today. It decides how many jobs start, it does not hold back a job that is running")}
      <div className="setting-parts">
        <Part title="Cores kept">
          {meaning(`Whole cores, 0 to ${maxCores}`)}
          <Row label="Suggested" note="the default for every node: nothing kept">
            <span className="num font-medium">{coreWords(ROOM_DEFAULTS.keep_cores)}</span>
          </Row>
          <Row label="Yours" note={share(coresYours, cores, coreWords)}>
            <Stepper value={coresYours} min={0} max={maxCores} label="Cores kept for you" unit="core" disabled={off}
              onChange={(next) => onEdit({ keep_cores: next })} />
          </Row>
          <RunsWith now={keptCores.now == null ? null : coreWords(keptCores.now)} yours={coreWords(coresYours)}
            mark={keptCores.mark} online={view.online} same={keptCores.now === ROOM_DEFAULTS.keep_cores}
            drop={drop("keep_cores")} busy={busy} />
        </Part>
        <Part title="Memory kept">
          {meaning(`Whole GB, 0 to ${totalGb ?? "the node's memory"}`)}
          <Row label="Suggested" note="the default for every node: nothing kept">
            <span className="num font-medium">{gb(0)}</span>
          </Row>
          <Row label="Yours" note={share(memoryYours, totalGb, gb)}>
            <span className="ml-auto inline-flex items-center gap-2">
              <Stepper value={memoryYours} min={0} max={totalGb ?? 4096} label="Memory kept for you" unit="GB" units="GB"
                disabled={off} onChange={(next) => onEdit({ keep_memory: `${next}GB` })} />
              <span className="text-ink-2">GB</span>
            </span>
          </Row>
          <RunsWith now={keptMemory.now == null ? null : gb(memoryGb(keptMemory.now) ?? 0)} yours={gb(memoryYours)}
            mark={keptMemory.mark} online={view.online} same={memoryGb(keptMemory.now) === 0}
            drop={drop("keep_memory")} busy={busy} />
        </Part>
      </div>
    </Panel>
  );
}
