// A tooltip: the word for an icon that stands alone (design-system.md, Icons).

import * as Tooltip from "@radix-ui/react-tooltip";
import type { ReactElement, ReactNode } from "react";

export const TipProvider = ({ children }: { children: ReactNode }) => (
  <Tooltip.Provider delayDuration={300} skipDelayDuration={200}>{children}</Tooltip.Provider>
);

export function Tip({ text, children }: { text: ReactNode; children: ReactElement }) {
  if (!text) return children;
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content sideOffset={4} collisionPadding={8}
          className="z-30 max-w-menu rounded-s bg-ink-1 px-2 py-1 text-sm text-surface-0">
          {text}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
