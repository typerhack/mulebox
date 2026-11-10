// A filter's dropdown, as the Statistics and History pages show it: its name above, "All ..."
// for no filter, and an accent border while a value is chosen.

import type { FocusEventHandler } from "react";

import { cx } from "./cx";

interface Props {
  title: string;
  everything: string;            // the empty choice, such as "All projects"
  value: string;
  options: [string, string][];   // [value, what it reads]
  onChange: (value: string) => void;
  onFocus?: FocusEventHandler<HTMLSelectElement>;
  onBlur?: FocusEventHandler<HTMLSelectElement>;
}

export function FilterSelect({ title, everything, value, options, onChange, onFocus, onBlur }: Props) {
  return (
    <label className="grid min-w-0 gap-1 text-sm text-ink-2">
      {title}
      <select value={value} onChange={(event) => onChange(event.target.value)} onFocus={onFocus} onBlur={onBlur}
        className={cx("h-ctl touch:h-ctl-touch w-full max-w-col-m min-w-0 rounded-m border bg-surface-1 px-2 text-base text-ink-1",
                      value ? "border-accent" : "border-line-strong")}>
        <option value="">{everything}</option>
        {options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}
      </select>
    </label>
  );
}
