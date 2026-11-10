// A load meter with its label and its number (design-system.md, Meter styles). The style,
// Gauge or Rainbow, is the stylesheet's; this only sets the share. A meter turns warning from
// 80% and danger from 92%, with the icon beside its number, so colour never says it alone.

import { OctagonAlert, TriangleAlert } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

import { cx } from "./cx";

export const WARN_FROM = 80, DANGER_FROM = 92;
export const levelOf = (value: number) => (value >= DANGER_FROM ? "danger" : value >= WARN_FROM ? "warn" : null);
const share = (value: number) => ({ "--v": `${Math.max(0, Math.min(100, value)).toFixed(1)}%` }) as CSSProperties;

interface BarProps { value: number | null; label: string; levels?: boolean; className?: string }

// The bar alone, for a table cell or a card.
export function MeterBar({ value, label, levels = true, className }: BarProps) {
  const shown = value ?? 0;
  return (
    <div className={cx("meter", className)} role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={Math.round(shown)} data-level={(levels && levelOf(shown)) || undefined} style={share(shown)}>
      <i />
    </div>
  );
}

interface Props extends BarProps {
  name: ReactNode;    // the label on the left
  text: ReactNode;    // the number on the right
}

export function Meter({ name, text, value, label, levels = true, className }: Props) {
  const level = levels && value !== null ? levelOf(value) : null;
  return (
    <div className={cx("meter-row", className)}>
      <span className="truncate text-sm text-ink-2">{name}</span>
      <MeterBar value={value} label={label} levels={levels} />
      <span className="num inline-flex items-center justify-end gap-1 text-sm font-medium">
        {level === "danger" && <OctagonAlert aria-hidden className="status-icon size-icon-s text-danger" />}
        {level === "warn" && <TriangleAlert aria-hidden className="status-icon size-icon-s text-warning" />}
        {text}
      </span>
    </div>
  );
}
