// "Queue actions" in the header: everything at once (lib/menu.ts, queueGroups). Absent where
// this page has no controls.

import { SlidersHorizontal } from "lucide-react";

import { tokenStore } from "../../lib/api";
import { queueGroups } from "../../lib/menu";
import { useStore } from "../../lib/store";
import { useMachines, useQueue } from "../../state/live";
import { Button } from "../../ui/Button";
import { ActionMenu } from "../../ui/Menu";

export function QueueActions() {
  const token = useStore(tokenStore);
  const snapshot = useQueue(), machines = useMachines();
  if (!token) return null;
  const label = "Actions for every machine and every job";
  return (
    <ActionMenu groups={queueGroups(snapshot, machines)} label={label}>
      <Button title={label} aria-label={label} className="max-md:w-ctl-touch max-md:px-0">
        <SlidersHorizontal aria-hidden className="size-icon-s" /><span className="max-md:hidden">Queue actions</span>
      </Button>
    </ActionMenu>
  );
}
