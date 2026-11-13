// "Order" on a waiting line's heading: opens the order rules in a panel anchored under it
// (design-system/queue-order-mockup.html, option A). Changes are a copy until Save, and say
// "Unsaved" until then; Reset asks twice, as it drops every rule. Where this page has no
// controls the panel still opens, to read. Its host element needs the class `pop-host`.

import { ListOrdered } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { tokenStore } from "../../lib/api";
import { isDefault, isDirty } from "../../lib/order";
import { useStore } from "../../lib/store";
import { discardRules, editRules, loadRules, orderStore, resetRules, saveRules } from "../../state/order";
import { Button } from "../../ui/Button";
import { WithCode } from "../../ui/Code";
import { FloatPanel } from "../../ui/Float";
import { OrderLevels } from "./OrderLevels";
import { OrderRules } from "./OrderRules";

const READ_ONLY = "This dashboard's controls are off, so the rules can only be read here. Change them with `mulebox queue rules`.";

function Foot({ readOnly, dirty, plain }: { readOnly: boolean; dirty: boolean; plain: boolean }) {
  const { busy, said, problem } = useStore(orderStore);
  const [armed, setArmed] = useState(false);
  const keep = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (armed) keep.current?.focus(); }, [armed]);
  if (readOnly) {
    return <p className="mr-auto text-sm text-ink-2">{problem && <b role="alert" className="font-medium text-ink-1">{problem} </b>}<WithCode text={READ_ONLY} /></p>;
  }
  if (armed) {
    return (
      <>
        <p className="mr-auto flex-1 basis-col-s text-sm text-ink-2">Every level and rule goes; the line is first come, first served again.</p>
        <Button tone="danger" onClick={() => { setArmed(false); void resetRules(); }}>Yes, reset</Button>
        <Button ref={keep} onClick={() => setArmed(false)}>Keep rules</Button>
      </>
    );
  }
  const saving = busy === "saving";
  return (
    <>
      <p className="mr-auto flex-1 basis-col-s text-sm text-ink-2">
        {problem ? <span role="alert" className="font-medium text-ink-1">{problem}</span>
          : saving ? <span role="status">Saving</span>
            : dirty ? <span role="status" className="font-semibold text-ink-1">Unsaved changes</span>
              : said ? <span role="status">{said}</span>
                : plain ? "These are the defaults: first come, first served." : "A change applies to the line once you save it."}
      </p>
      {dirty ? <Button tone="ghost" disabled={saving} onClick={discardRules}>Discard</Button>
        : <Button disabled={plain || saving} onClick={() => setArmed(true)}>Reset to defaults</Button>}
      <Button tone="primary" disabled={!dirty || saving} onClick={() => void saveRules()}>Save</Button>
    </>
  );
}

export function OrderButton({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  const token = useStore(tokenStore);
  const { body, draft, problem, closed } = useStore(orderStore);
  const readOnly = !token || closed;
  const dirty = Boolean(body && draft && isDirty(body.rules, draft));
  const toggle = () => {
    if (!open) void loadRules();
    setOpen(!open);
  };
  return (
    <>
      <Button ref={opener} aria-haspopup="dialog" aria-expanded={open} onClick={toggle} className={className}>
        <ListOrdered aria-hidden className="size-icon-s" />Order
        {dirty && !open && <span className="text-sm font-normal text-ink-2">, unsaved</span>}
      </Button>
      {open && (
        <FloatPanel title="Order of the line" opener={opener} onClose={() => setOpen(false)}
          note={!body ? null : isDefault(body) ? "Defaults: first come, first served, moved by hand with the arrows."
            : "Rules are on. Each waiting row says why it stands where it does."}
          foot={body && draft ? <Foot readOnly={readOnly} dirty={dirty} plain={isDefault(body)} /> : null}>
          {body && draft ? (
            <div className="grid">
              <OrderRules body={body} draft={draft} edit={editRules} readOnly={readOnly} />
              <OrderLevels body={body} draft={draft} edit={editRules} readOnly={readOnly} />
            </div>
          ) : problem ? <p role="alert" className="font-medium">{problem}</p>
            : <p role="status" className="text-ink-2">Loading the rules</p>}
        </FloatPanel>
      )}
    </>
  );
}
