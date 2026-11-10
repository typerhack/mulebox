// The top row, the same on every page: CPU with its graph and cores, Memory over Disk, and the
// Machines box.

import { useStore } from "../../lib/store";
import { tickStore, useMachines } from "../../state/live";
import { useShown } from "../../state/picked";
import { CpuPanel, DiskPanel, MemoryPanel } from "./LoadPanels";
import { MachinesBox } from "./MachinesBox";

export function TopRow() {
  const shown = useShown();
  const panel = useMachines();
  useStore(tickStore);  // "last seen" moves on
  const now = Date.now() / 1000;
  return (
    <div className="top-row">
      <CpuPanel shown={shown} now={now} />
      <div className="top-side">
        <MemoryPanel shown={shown} now={now} />
        <DiskPanel shown={shown} now={now} />
      </div>
      <MachinesBox panel={panel} shown={shown} now={now} />
    </div>
  );
}
