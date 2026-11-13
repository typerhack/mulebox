// A segmented choice: one of a few (design-system.md, Settings controls), drawn as radio marks:
// no box, a ring before each word, the chosen ring filled in the accent with a heavier word,
// never colour alone. A radio group: Tab reaches the chosen part, arrow keys move the choice,
// Home and End take the ends. Each word holds a hidden heavier copy of itself (`.seg-word`), so
// a part keeps its width when chosen. `small` is the 28px kind for dense rows (the order rules,
// a period choice). Its look is `.seg` in styles/components.css.

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
      className={cx("seg", small && "seg-small")}>
      {choices.map((choice, index) => (
        <button key={String(choice.value)} type="button" role="radio" aria-checked={index === chosen} disabled={disabled}
          tabIndex={index === chosen || (chosen < 0 && index === 0) ? 0 : -1}
          onClick={() => onChange(choice.value)} onKeyDown={(event) => move(event, index)}>
          <span aria-hidden className="seg-ring" data-on={index === chosen || undefined} />
          <span className="seg-word" data-word={choice.label}>{choice.label}</span>
        </button>
      ))}
    </div>
  );
}
