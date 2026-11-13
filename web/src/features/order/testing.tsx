// What the tests of the order panel share: an Order button and the panel, as the lanes hold them.

import { useRef } from "react";

import { TipProvider } from "../../ui/Tip";
import { OrderButton, OrderPanel } from "./OrderButton";

export function OrderHarness() {
  const home = useRef<HTMLDivElement>(null);
  return (
    <TipProvider>
      <div ref={home} tabIndex={-1} className="pop-host"><OrderButton /><OrderPanel home={home} /></div>
    </TipProvider>
  );
}
