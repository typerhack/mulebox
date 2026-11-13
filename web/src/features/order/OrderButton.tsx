// "Order" on a waiting line's heading opens the order rules in a panel
// (design-system/queue-order-mockup.html, option A). Changes are a copy until Save, and say
// "Unsaved" until then; Reset asks twice, as it drops every rule. Where this page has no
// controls the panel still opens, to read.
//
// One panel (`OrderPanel`), mounted once where the lanes are, not in a lane: a lane goes when
// its last waiting job starts, and the open panel, its focus and what is typed in it must not go
// with it. It hangs under the button it was opened from (CSS anchor positioning, `.pop-opener`),
// and at the top of the lanes when that button is gone or the browser cannot anchor. Closing
// gives the focus back to that button, else to another Order button, else to `home`. While open,
// it reads the rules again every few seconds, keeping what the viewer has not saved.

import { ListOrdered } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type RefObject } from "react";

import { tokenStore } from "../../lib/api";
import { isDefault, isDirty } from "../../lib/order";
import { useStore } from "../../lib/store";
import { REREAD_MS } from "../../lib/turns";
import { closeRules, discardRules, editRules, isReading, loadRules, openRules, orderStore, resetRules,
         saveRules } from "../../state/order";
import { Button } from "../../ui/Button";
import { WithCode } from "../../ui/Code";
import { cx } from "../../ui/cx";
import { FloatPanel } from "../../ui/Float";
import { OrderLevels } from "./OrderLevels";
import { OrderRules } from "./OrderRules";

const READ_ONLY = "This dashboard's controls are off, so the rules can only be read here. Change them with `mulebox queue rules`.";
const BUTTON = "data-order-button";

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

// The Order button the panel was opened from, while it is on the page; else another; else `home`.
function openerOf(from: string | null, home: RefObject<HTMLElement | null>): RefObject<HTMLElement | null> {
  return {
    get current() {
      const buttons = [...document.querySelectorAll<HTMLElement>(`[${BUTTON}]`)];
      return buttons.find((button) => button.getAttribute(BUTTON) === from) ?? buttons[0] ?? home.current;
    },
  };
}

export function OrderButton({ className }: { className?: string }) {
  const id = useId();
  const { body, draft, openedBy } = useStore(orderStore);
  const open = openedBy === id;
  const dirty = Boolean(body && draft && isDirty(body.rules, draft));
  return (
    <Button aria-haspopup="dialog" aria-expanded={open} {...{ [BUTTON]: id }}
      onClick={() => (open ? closeRules() : openRules(id))} className={cx(className, open && "pop-opener")}>
      <ListOrdered aria-hidden className="size-icon-s" />Order
      {dirty && !openedBy && <span className="text-sm font-normal text-ink-2">, unsaved</span>}
    </Button>
  );
}

// The panel itself. Its host element needs the class `pop-host` and holds every Order button.
export function OrderPanel({ home }: { home: RefObject<HTMLElement | null> }) {
  const token = useStore(tokenStore);
  const { body, draft, problem, closed, busy, openedBy } = useStore(orderStore);
  const opener = useMemo(() => openerOf(openedBy, home), [openedBy, home]);
  const shown = openedBy !== null;
  useEffect(() => closeRules, []);  // the lanes went (another tab): the panel does not wait for them
  useEffect(() => {
    if (!shown) return;
    const timer = setInterval(() => { if (!document.hidden && !isReading()) void loadRules(); }, REREAD_MS);
    return () => clearInterval(timer);
  }, [shown]);
  if (!shown) return null;
  const readOnly = !token || closed;
  const saving = busy === "saving";
  const dirty = Boolean(body && draft && isDirty(body.rules, draft));
  return (
    <FloatPanel title="Order of the line" opener={opener} onClose={closeRules}
      note={!body ? null : isDefault(body) ? "Defaults: first come, first served, moved by hand with the arrows."
        : "Rules are on. Each waiting row says why it stands where it does."}
      foot={body && draft ? <Foot readOnly={readOnly} dirty={dirty} plain={isDefault(body)} /> : null}>
      {body && draft ? (
        <div className="grid">
          <OrderRules body={body} draft={draft} edit={editRules} readOnly={readOnly || saving} />
          <OrderLevels body={body} draft={draft} edit={editRules} readOnly={readOnly} busy={saving} />
        </div>
      ) : problem ? <p role="alert" className="font-medium">{problem}</p>
        : <p role="status" className="text-ink-2">Loading the rules</p>}
    </FloatPanel>
  );
}
