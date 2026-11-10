// The live line graph: a canvas the chart draws on (lib/chart.ts), the note that says its
// scale, and the tip that follows the pointer. It draws again when a sample comes and when
// the theme or the meter style changes, as its colours are the stylesheet's.

import { useEffect, useRef } from "react";

import { LineChart, type Point } from "../lib/chart";
import { useLook } from "../lib/prefs";
import { cx } from "./cx";

interface Props {
  points: Point[];
  max: number;
  windowS: number;
  format: (value: number) => string;
  label: string;
  scale: string;
  small?: boolean;
  className?: string;
}

export function Graph({ points, max, windowS, format, label, scale, small, className }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null), tip = useRef<HTMLDivElement>(null);
  const chart = useRef<LineChart | null>(null);
  const look = useLook();
  const formatRef = useRef(format);
  formatRef.current = format;

  useEffect(() => {
    if (!canvas.current || !tip.current) return undefined;
    const made = new LineChart(canvas.current, tip.current, windowS, (value) => formatRef.current(value));
    chart.current = made;
    const onShow = () => { if (!document.hidden) made.draw(); };
    document.addEventListener("visibilitychange", onShow);
    return () => { made.destroy(); document.removeEventListener("visibilitychange", onShow); chart.current = null; };
  }, [windowS]);

  useEffect(() => { chart.current?.update(points, max, look.paint); }, [points, max, look.paint, look.theme]);

  return (
    <div className={cx("graph", small && "graph-small", className)}>
      <canvas ref={canvas} role="img" aria-label={label} />
      <span className="pointer-events-none absolute top-0 left-0 bg-surface-1 pr-1 text-xs leading-none text-ink-2">{scale}</span>
      <div ref={tip} hidden
        className="num pointer-events-none absolute top-0 z-10 rounded-s bg-ink-1 px-2 py-1 text-sm text-surface-0" />
    </div>
  );
}
