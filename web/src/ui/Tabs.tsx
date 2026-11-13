// Tabs with counts: a 2px accent line under the selected one. Arrow keys, Home and End move
// between them, as a tab list should.

import type { KeyboardEvent, ReactNode } from "react";

import { cx } from "./cx";

export interface TabItem<T extends string> { id: T; label: string; count?: number | null; extra?: ReactNode }

interface Props<T extends string> {
  items: TabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  label: string;
  panelId?: string;
  className?: string;
}

export function Tabs<T extends string>({ items, value, onChange, label, panelId, className }: Props<T>) {
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = items.findIndex((item) => item.id === value);
    const step = { ArrowRight: 1, ArrowLeft: -1, Home: -index, End: items.length - 1 - index }[event.key];
    if (step === undefined) return;
    event.preventDefault();
    const chosen = items[(index + step + items.length) % items.length];
    onChange(chosen.id);
    event.currentTarget.querySelector<HTMLElement>(`[data-tab="${chosen.id}"]`)?.focus();
  };
  return (
    <div role="tablist" aria-label={label} onKeyDown={onKeyDown}
      className={cx("flex min-w-0 flex-wrap gap-x-5 border-b border-line touch:gap-x-4", className)}>
      {items.map((item) => {
        const selected = item.id === value;
        return (
          <button key={item.id} type="button" role="tab" data-tab={item.id} id={`tab-${item.id}`}
            aria-selected={selected} aria-controls={panelId} tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.id)}
            className={cx("-mb-px inline-flex h-tab touch:h-ctl-touch items-center gap-2 border-b-2 whitespace-nowrap transition-colors",
                          selected ? "border-accent font-semibold text-ink-1"
                                   : "border-transparent font-medium text-ink-2 hover:text-ink-1")}>
            {item.label}
            {item.count !== null && item.count !== undefined && (
              <span className={cx("num rounded-s border bg-surface-2 px-1 text-xs font-medium",
                                  selected ? "border-line-strong text-ink-1" : "border-line text-ink-2")}>
                {item.count}
              </span>
            )}
            {item.extra}
          </button>
        );
      })}
    </div>
  );
}
