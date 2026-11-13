// A segmented choice: one of a few (design-system.md, Settings controls). A radio group: Tab
// reaches the chosen part, arrow keys move the choice, Home and End take the ends. The chosen
// part carries the accent line and a heavier word, never colour alone.

import { useRef } from "react";

import { cx } from "./cx";

interface Choice { value: string; label: string }
interface Props {
  choices: Choice[];
  value: string | null;
  label: string;
  describedBy?: string;
  disabled?: boolean;
  onChange: (next: string) => void;
}

const MOVES: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };

export function Segmented({ choices, value, label, describedBy, disabled, onChange }: Props) {
  const group = useRef<HTMLDivElement>(null);
  const chosen = choices.findIndex((choice) => choice.value === value);
  const move = (event: React.KeyboardEvent, from: number) => {
    const to = event.key === "Home" ? 0 : event.key === "End" ? choices.length - 1
      : event.key in MOVES ? (from + MOVES[event.key] + choices.length) % choices.length : -1;
    if (to < 0) return;
    event.preventDefault();
    onChange(choices[to].value);
    group.current?.querySelectorAll<HTMLElement>("[role=radio]")[to]?.focus();
  };
  return (
    <div ref={group} role="radiogroup" aria-label={label} aria-describedby={describedBy} className="flex max-w-full">
      {choices.map((choice, index) => (
        <button key={choice.value} type="button" role="radio" aria-checked={index === chosen} disabled={disabled}
          tabIndex={index === chosen || (chosen < 0 && index === 0) ? 0 : -1}
          onClick={() => onChange(choice.value)} onKeyDown={(event) => move(event, index)}
          className={cx("-ml-px inline-flex h-ctl min-w-0 flex-1 items-center justify-center border px-3 text-sm whitespace-nowrap",
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
