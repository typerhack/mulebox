// A panel opened from a button and anchored to it (design-system.md, Floating surfaces): a
// hairline, `--shadow-2`, dialog semantics. Focus moves in on open; Escape or the close button
// closes it and gives the focus back to the opener; a press outside closes it too. Its place
// comes from the stylesheet (`.pop` inside a `.pop-host`), so nothing is measured in script.
// When the focused control goes away or turns disabled (Save, once saved), the focus would drop to
// the page and Escape would no longer reach the panel; the panel then takes the focus itself.

import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";

import { IconButton } from "./Button";

interface Props {
  title: string;
  note?: ReactNode;                              // one line under the title
  opener: RefObject<HTMLElement | null>;
  onClose: () => void;
  foot?: ReactNode;
  children: ReactNode;
}

export function FloatPanel({ title, note, opener, onClose, foot, children }: Props) {
  const id = useId();
  const panel = useRef<HTMLDivElement>(null), first = useRef<HTMLButtonElement>(null);
  const close = (back: boolean) => {
    onClose();
    if (back) opener.current?.focus();
  };
  const latest = useRef(close);
  useEffect(() => { latest.current = close; });
  useEffect(() => {
    if (document.activeElement === document.body) panel.current?.focus({ preventScroll: true });
  });

  useEffect(() => {
    first.current?.focus({ preventScroll: true });
    panel.current?.scrollIntoView?.({ block: "nearest" });
    const outside = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (target && !panel.current?.contains(target) && !opener.current?.contains(target)) latest.current(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [opener]);

  return (
    <div ref={panel} role="dialog" aria-labelledby={id} tabIndex={-1}
      onKeyDown={(event) => { if (event.key === "Escape") { event.stopPropagation(); close(true); } }}
      className="pop rounded-l outline-none border border-line-strong bg-surface-1 shadow-menu dark:bg-surface-2">
      <header className="flex items-start justify-between gap-3 border-b border-line py-3 pr-3 pl-4">
        <div className="grid min-w-0 gap-1">
          <h3 id={id} className="text-lg font-semibold">{title}</h3>
          {note && <p className="text-sm text-ink-2">{note}</p>}
        </div>
        <IconButton ref={first} small label="Close" onClick={() => close(true)}><X aria-hidden className="size-icon" /></IconButton>
      </header>
      <div className="pop-body p-4">{children}</div>
      {foot && <footer className="flex flex-wrap items-center justify-end gap-x-3 gap-y-2 border-t border-line px-4 py-3">{foot}</footer>}
    </div>
  );
}
