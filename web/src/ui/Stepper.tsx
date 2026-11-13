// A number stepper: minus, the value in mono, plus (design-system.md, Settings controls). A
// value may be typed; one out of range is refused and the range said, the last good value kept.

import { Minus, Plus } from "lucide-react";
import { useId, useState } from "react";

import { cx } from "./cx";

interface Props {
  value: number;
  min: number;
  max: number;
  label: string;                 // what is counted, as the field's accessible name: "Slots"
  unit: string;                  // one of them, for the buttons: "slot"
  units?: string;                // more than one, when `step` is: "minutes" (default unit + "s")
  step?: number;                 // how far a button moves the value (1)
  disabled?: boolean;
  onChange: (next: number) => void;
}

const SIDE = "inline-grid size-ctl touch:size-ctl-touch place-items-center border border-line-strong bg-surface-1 " +
  "hover:relative hover:border-ink-1 hover:bg-surface-3 focus-visible:relative off:border-line off:bg-surface-2 off:text-ink-3";

export function Stepper({ value, min, max, label, unit, units = `${unit}s`, step: by = 1, disabled, onChange }: Props) {
  const [typed, setTyped] = useState<string | null>(null);  // while it differs from a good value
  const refusal = useId();
  const range = `From ${min} to ${max}.`;
  const type = (text: string) => {
    const n = Number(text);
    const good = /^\d+$/.test(text.trim()) && n >= min && n <= max;
    setTyped(good ? null : text);
    if (good) onChange(n);
  };
  const step = (sign: number) => { setTyped(null); onChange(Math.min(max, Math.max(min, value + sign * by))); };
  const many = by === 1 ? `One ${unit}` : `${by} ${units}`;
  return (
    <span className="inline-grid gap-1">
      <span className="inline-flex items-stretch">
        <button type="button" aria-label={`${many} fewer`} disabled={disabled || value <= min}
          onClick={() => step(-1)} className={cx(SIDE, "rounded-l-m")}>
          <Minus aria-hidden className="size-icon" />
        </button>
        <input type="text" inputMode="numeric" aria-label={label} disabled={disabled}
          aria-invalid={typed !== null || undefined} aria-describedby={typed !== null ? refusal : undefined}
          value={typed ?? String(value)} onChange={(event) => type(event.target.value)} onBlur={() => setTyped(null)}
          className="num -mx-px h-ctl w-ctl-touch min-w-0 border border-line-strong bg-surface-1 text-center font-mono text-lg font-semibold focus-visible:relative off:border-line off:bg-surface-2 off:text-ink-3 touch:h-ctl-touch" />
        <button type="button" aria-label={`${many} more`} disabled={disabled || value >= max}
          onClick={() => step(1)} className={cx(SIDE, "rounded-r-m")}>
          <Plus aria-hidden className="size-icon" />
        </button>
      </span>
      {typed !== null && <span id={refusal} role="alert" className="text-sm font-medium">Not taken. {range}</span>}
    </span>
  );
}
