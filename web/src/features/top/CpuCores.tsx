// The meters under the CPU graph, in the view the viewer chose (remembered per browser):
// details, one meter per core as always, or compact, the busiest cores by name and one line for
// the rest, so a machine with many cores keeps the box its size (the user's idea, 2026-11-11).

import { ChartNoAxesColumnDecreasing, LayoutGrid } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { busiest, rest } from "../../lib/cores";
import { percent } from "../../lib/format";
import { remembered } from "../../lib/prefs";
import { IconButton } from "../../ui/Button";
import { Meter } from "../../ui/Meter";

export type CpuView = "details" | "compact";
const VIEW = remembered<CpuView>("mulebox-cpu-view", ["details", "compact"], "details");
const WIDE = "(min-width: 1101px)"; // the lg breakpoint, where cores sit four to a row

const SAYS = { details: "details, every core", compact: "compact, the busiest cores" };
const ICON = { details: LayoutGrid, compact: ChartNoAxesColumnDecreasing };

export function useWide(): boolean {
  return useSyncExternalStore(
    (changed) => {
      const list = window.matchMedia?.(WIDE);
      list?.addEventListener("change", changed);
      return () => list?.removeEventListener("change", changed);
    },
    () => window.matchMedia?.(WIDE).matches ?? true,
  );
}

// How many cores the compact view names: two rows of the grid, beside the line for the rest.
export const shownCount = (wide: boolean) => (wide ? 6 : 4);

export function useCpuView(): [CpuView, (view: CpuView) => void] {
  const [view, setView] = useState<CpuView>(VIEW.read);
  return [view, (next) => { VIEW.write(next); setView(next); }];
}

export function ViewSwitch({ view, set }: { view: CpuView; set: (view: CpuView) => void }) {
  const to: CpuView = view === "details" ? "compact" : "details";
  const Icon = ICON[view];
  return (
    <IconButton small label={`CPU view: ${SAYS[view]}. Switch to ${to}`} onClick={() => set(to)}
      className="-my-1">
      <Icon aria-hidden className="size-icon-s" />
    </IconButton>
  );
}

// Whether the compact view would show anything less than the details view.
export const compactable = (cores: number, wide: boolean) => cores > shownCount(wide);

export function CpuCores({ cores, view, machine }: { cores: number[]; view: CpuView; machine: string }) {
  const wide = useWide();
  const held = useRef<{ machine: string; set: number[] }>({ machine, set: [] });
  if (held.current.machine !== machine) held.current = { machine, set: [] };
  const compact = view === "compact" && compactable(cores.length, wide);
  const shown = compact ? busiest(cores, shownCount(wide), held.current.set) : [];
  useEffect(() => { if (compact) held.current.set = shown; });

  if (!compact) {
    return (
      <div className="cores">
        {cores.map((value, index) => (
          <Meter key={index} name={String(index)} value={value} text={percent(value)}
            label={`Core ${index}: ${percent(value)}`} />
        ))}
      </div>
    );
  }
  const all = cores.reduce((a, b) => a + b, 0) / cores.length;
  const others = rest(cores, shown);
  return (
    <div className="grid gap-1">
      <Meter name="All" value={all} text={percent(all)} label={`CPU, all ${cores.length} cores: ${percent(all)}`} />
      <div className="cores">
        {shown.map((index) => (
          <Meter key={index} name={String(index)} value={cores[index]} text={percent(cores[index])}
            label={`Core ${index}: ${percent(cores[index])}`} />
        ))}
        {others && (
          <Meter className="cores-rest" levels={false} name={`${others.count} others`} value={others.average}
            label={`The other ${others.count} cores: ${percent(others.average)} on average, ${percent(others.highest)} at most`}
            text={<span className="font-normal text-ink-2">average <b className="font-medium text-ink-1">{percent(others.average)}</b>, highest <b className="font-medium text-ink-1">{percent(others.highest)}</b></span>} />
        )}
      </div>
    </div>
  );
}
