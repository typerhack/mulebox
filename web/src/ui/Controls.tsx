// Settings controls (design-system.md, Components): a switch, a segmented choice and a number
// stepper. Each is outlined like anything that can be pressed, and 44px on touch.

import { Minus, Plus } from "lucide-react";
import { useState, type KeyboardEvent } from "react";

import { cx } from "./cx";

interface SwitchProps { checked: boolean; onChange: (next: boolean) => void; labelledBy: string; disabled?: boolean }

// On in the accent, with the knob on the right: the state is never colour alone. The button is
// the target; the track inside it is the picture (styles/components.css, `.switch`).
export const Switch = ({ checked, onChange, labelledBy, disabled }: SwitchProps) => (
  <button type="button" role="switch" aria-checked={checked} aria-labelledby={labelledBy} disabled={disabled}
    onClick={() => onChange(!checked)}
    className="inline-grid min-h-6 flex-none place-items-center rounded-full touch:min-h-ctl-touch touch:min-w-ctl-touch">
    <i aria-hidden className="switch" />
  </button>
);

type Id = string | number;
interface SegmentedProps<T extends Id> {
  options: [T, string][];
  value: T;
  onChange: (id: T) => void;
  label?: string;
  labelledBy?: string;
  disabled?: boolean;
}

// One of a few, as joined buttons: the chosen part is marked by weight, tone and an accent
// line. Arrow keys, Home and End move the choice, as in a radio group.
export function Segmented<T extends Id>({ options, value, onChange, label, labelledBy, disabled }: SegmentedProps<T>) {
  const at = options.findIndex(([id]) => id === value);
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const from = Math.max(0, at);
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1, Home: -from, End: options.length - 1 - from }[event.key];
    if (step === undefined || disabled) return;
    event.preventDefault();
    const [chosen] = options[(from + step + options.length) % options.length];
    onChange(chosen);
    event.currentTarget.querySelector<HTMLElement>(`[data-choice="${String(chosen)}"]`)?.focus();
  };
  return (
    <div role="radiogroup" aria-label={label} aria-labelledby={labelledBy} onKeyDown={onKeyDown} className="inline-flex max-w-full">
      {options.map(([id, text], index) => (
        <button key={String(id)} type="button" role="radio" aria-checked={id === value} data-choice={String(id)}
          tabIndex={index === Math.max(0, at) ? 0 : -1} disabled={disabled} onClick={() => onChange(id)}
          className={cx("h-ctl-s touch:h-ctl-touch touch:min-w-ctl-touch border border-line-strong bg-surface-1 px-3 text-sm font-medium whitespace-nowrap text-ink-2 transition-colors",
                        "hover:bg-surface-2 hover:text-ink-1 on:relative on:border-ink-1 on:bg-surface-3 on:font-semibold on:text-ink-1 on:shadow-mark",
                        "off:border-line off:text-ink-3 off:hover:bg-surface-1 off:on:border-line-strong off:on:text-ink-2",
                        index > 0 && "-ml-px", index === 0 && "rounded-l-m", index === options.length - 1 && "rounded-r-m")}>
          {text}
        </button>
      ))}
    </div>
  );
}

interface StepperProps {
  value: number;
  onChange: (next: number) => void;
  min: number;
  max: number;
  step?: number;
  label: string;
  unit: string;        // said with the range when a typed value is refused
  disabled?: boolean;
}

const STEP_BUTTON = "inline-grid size-ctl touch:size-ctl-touch place-items-center border border-line-strong bg-surface-1 text-ink-1 " +
  "transition-colors hover:relative hover:border-ink-1 hover:bg-surface-3 off:border-line off:bg-surface-2 off:text-ink-3";

// Minus, the value in mono, plus. A value may be typed; one out of range is refused, with the
// range said, and the stored value stays.
export function Stepper({ value, onChange, min, max, step = 1, label, unit, disabled }: StepperProps) {
  const [typed, setTyped] = useState<string | null>(null);
  const [refused, setRefused] = useState(false);
  const take = (text: string) => {
    const next = Number(text.trim());
    const ok = /^\d+$/.test(text.trim()) && next >= min && next <= max;
    setRefused(!ok);
    setTyped(ok ? null : text);
    if (ok && next !== value) onChange(next);
  };
  const move = (by: number) => {
    setTyped(null);
    setRefused(false);
    onChange(Math.min(max, Math.max(min, value + by)));
  };
  return (
    <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1">
      <span className="inline-flex">
        <button type="button" aria-label={`Less: ${label}`} disabled={disabled || value <= min} onClick={() => move(-step)}
          className={cx(STEP_BUTTON, "rounded-l-m")}><Minus aria-hidden className="size-icon" /></button>
        <input type="text" inputMode="numeric" aria-label={label} aria-invalid={refused || undefined} disabled={disabled}
          value={typed ?? String(value)} onChange={(event) => { setTyped(event.target.value); setRefused(false); }}
          onBlur={(event) => { if (typed !== null) take(event.target.value); }}
          onKeyDown={(event) => { if (event.key === "Enter") take(event.currentTarget.value); }}
          className="num -mx-px h-ctl touch:h-ctl-touch w-ctl-touch min-w-0 border border-line-strong bg-surface-1 text-center font-mono text-base font-semibold text-ink-1 focus:relative off:border-line off:text-ink-3" />
        <button type="button" aria-label={`More: ${label}`} disabled={disabled || value >= max} onClick={() => move(step)}
          className={cx(STEP_BUTTON, "rounded-r-m")}><Plus aria-hidden className="size-icon" /></button>
      </span>
      {refused && <span role="alert" className="text-sm font-medium">From {min} to {max} {unit}.</span>}
    </span>
  );
}
