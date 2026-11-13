// A window: centred, the page dimmed behind it (design-system.md, Floating surfaces). Dialog
// semantics, Escape and a close button; focus moves in on open, stays inside while it is
// open, and goes back to what opened it on close. The page under it cannot be reached.
//
// Made here and not with Radix's Dialog, whose modal layer locks scrolling through a <style>
// element the page's security policy refuses (web/README.md).

import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";

import { IconButton } from "./Button";

const CAN_FOCUS = "a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled)";

interface Props {
  title: ReactNode;
  icon?: ReactNode;
  note?: ReactNode;       // one line under the title
  foot?: ReactNode;
  opener?: RefObject<HTMLElement | null>;  // what gets the focus back; else what had it (a click does not focus a button in every browser)
  onClose: () => void;
  children: ReactNode;
}

export function Window({ title, icon, note, foot, opener, onClose, children }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const close = useRef(onClose);
  useEffect(() => { close.current = onClose; });

  useEffect(() => {
    const back = opener?.current ?? (document.activeElement as HTMLElement | null);
    const page = document.getElementById("root");
    const scroll = document.body.style.overflow;
    page?.setAttribute("inert", "");
    document.body.style.overflow = "hidden";
    box.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      const within = box.current;
      if (!within) return;
      if (event.key === "Escape") {
        event.preventDefault();
        close.current();
      } else if (event.key === "Tab") {
        const stops = [...within.querySelectorAll<HTMLElement>(CAN_FOCUS)].filter((stop) => stop.tabIndex >= 0);
        const first = stops[0], last = stops[stops.length - 1], at = document.activeElement;
        if (!first) event.preventDefault();
        else if (!within.contains(at) || at === within) { event.preventDefault(); (event.shiftKey ? last : first).focus(); }
        else if (event.shiftKey && at === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && at === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = scroll;
      page?.removeAttribute("inert");
      if (back?.isConnected) back.focus();
    };
  }, [opener]);

  return createPortal(
    <div className="fixed inset-0 z-20 flex items-center justify-center overflow-hidden bg-scrim p-2 md:p-6">
      <div ref={box} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}
        className="flex max-h-full w-full max-w-window min-w-0 flex-col rounded-l border border-line-strong bg-surface-1 shadow-window outline-none">
        <header className="flex items-start justify-between gap-3 border-b border-line px-4 pt-4 pb-3">
          <div className="grid min-w-0 gap-1">
            <h2 id={titleId} className="flex min-w-0 items-center gap-2 text-lg font-semibold">{icon}<span className="truncate">{title}</span></h2>
            {note && <p className="text-sm text-ink-2">{note}</p>}
          </div>
          <IconButton label="Close" onClick={onClose} className="border-transparent"><X aria-hidden className="size-icon" /></IconButton>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">{children}</div>
        {foot && <footer className="flex flex-wrap items-center justify-end gap-x-3 gap-y-2 border-t border-line px-4 py-3">{foot}</footer>}
      </div>
    </div>,
    document.body,
  );
}
