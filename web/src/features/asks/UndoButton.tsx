// Undo for an answer just given. It appears where Approve was, so it takes no click for its first
// moment: a double-click on Approve would otherwise take the yes back at once (seen on the real
// dashboard).

import { Undo2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "../../ui/Button";

export const ARM_MS = 1500;

interface Props { disabled: boolean; onUndo: () => void; tone?: "ghost" | "secondary" }

export function UndoButton({ disabled, onUndo, tone = "ghost" }: Props) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setArmed(true), ARM_MS);
    return () => clearTimeout(timer);
  }, []);
  return (
    <Button tone={tone} disabled={disabled || !armed} onClick={onUndo}>
      <Undo2 aria-hidden className="size-icon-s" />Undo
    </Button>
  );
}
