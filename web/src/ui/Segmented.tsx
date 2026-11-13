// A segmented choice: one of a few (design-system.md, Settings controls). A radio group: Tab
// reaches the chosen part, arrow keys move the choice, Home and End take the ends. The chosen
// part carries the accent line and a heavier word, never colour alone. `small` is the 28px
// inline kind for dense rows (the order rules, a period choice); the default fills its row.

import { useRef } from "react";

import { cx } from "./cx";

type Id = string | number;
export interface Choice<T extends Id = string> { value: T; label: string }
interface Props<T extends Id> {
  choices: Choice<T>[];
  value: T | null;
  label?: string;
  labelledBy?: string;
  describedBy?: string;
  disabled?: boolean;
  small?: boolean;
  onChange: (next: T) => void;
}

const MOVES: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };

export function Segmented<T extends Id>({ choices, value, label, labelledBy, describedBy, disabled, small, onChange }: Props<T>) {
  const group = useRef<HTMLDivElement>(null);
  const chosen = choices.findIndex((choice) => choice.value === value);
  const move = (event: React.KeyboardEvent, from: number) => {
    const to = event.key === "Home" ? 0 : event.key === "End" ? choices.length - 1
      : event.key in MOVES ? (from + MOVES[event.key] + choices.length) % choices.length : -1;
    if (to < 0 || disabled) return;
    event.preventDefault();
    onChange(choices[to].value);
    group.current?.querySelectorAll<HTMLElement>("[role=radio]")[to]?.focus();
  };
  return (
    <div ref={group} role="radiogroup" aria-label={label} aria-labelledby={labelledBy} aria-describedby={describedBy}
      className={cx("max-w-full", small ? "inline-flex" : "flex")}>
      {choices.map((choice, index) => (
        <button key={String(choice.value)} type="button" role="radio" aria-checked={index === chosen} disabled={disabled}
          tabIndex={index === chosen || (chosen < 0 && index === 0) ? 0 : -1}
          onClick={() => onChange(choice.value)} onKeyDown={(event) => move(event, index)}
          className={cx("-ml-px inline-flex items-center justify-center border px-3 text-sm whitespace-nowrap",
                        small ? "h-ctl-s touch:min-w-ctl-touch" : "h-ctl min-w-0 flex-1",
                        "first:ml-0 first:rounded-l-m last:rounded-r-m focus-visible:relative touch:h-ctl-touch off:border-line off:text-ink-3",
                        index === chosen
                          ? "relative border-ink-1 bg-surface-3 font-semibold text-ink-1 shadow-chosen off:bg-surface-2 off:shadow-none"
                          : "border-line-strong bg-surface-1 font-medium text-ink-2 hover:bg-surface-2 hover:text-ink-1 off:bg-surface-2")}>
          {choice.label}
        </button>
      ))}
    </div>
  );
}
