// Canvas line chart with a crosshair tooltip: one series, one axis, a fixed 0..max scale.
// Two styles (docs/design-system.md, Meter styles): Gauge draws the line in the graph colour
// over a faint fill; Rainbow takes the load ramp from bottom to top, on the line and the area.
// Colours are read from the tokens on the canvas itself, so the theme lives in the stylesheet.
// Cost: one draw per new sample (every 2 s), resize or pointer move; nothing animates.

const GAP_S = 8;  // a hole in the samples (a reconnect) stays a hole in the line
const ALPHA = { gauge: 0.14, rainbow: 0.4 };
const LINE = 1.5, DOT = 4;

export interface Point { t: number; v: number | null }
export type Paint = "gauge" | "rainbow";

export function nearest(points: Point[], at: (t: number) => number, x: number): Point | null {
  let best: Point | null = null, distance = Infinity;
  for (const point of points) {
    if (point.v === null) continue;
    const gap = Math.abs(at(point.t) - x);
    if (gap < distance) { best = point; distance = gap; }
  }
  return best;
}

export class LineChart {
  private points: Point[] = [];
  private max = 100;
  private hover: number | null = null;
  private paint: Paint = "gauge";
  private readonly watcher: ResizeObserver;

  constructor(private readonly canvas: HTMLCanvasElement, private readonly tip: HTMLElement,
              private readonly windowS: number, private readonly format: (value: number) => string) {
    this.watcher = new ResizeObserver(() => this.draw());
    this.watcher.observe(canvas);
    canvas.addEventListener("pointermove", this.onMove);
    canvas.addEventListener("pointerleave", this.onLeave);
  }

  private onMove = (event: PointerEvent) => { this.hover = event.offsetX; this.draw(); };
  private onLeave = () => { this.hover = null; this.tip.hidden = true; this.draw(); };

  destroy() {
    this.watcher.disconnect();
    this.canvas.removeEventListener("pointermove", this.onMove);
    this.canvas.removeEventListener("pointerleave", this.onLeave);
  }

  update(points: Point[], max: number, paint: Paint) {
    this.points = points;
    this.max = max || 1;
    this.paint = paint;
    this.draw();
  }

  draw() {
    const { canvas } = this;
    if (document.hidden) return;
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth, height = canvas.clientHeight;
    const ctx = canvas.getContext("2d");
    if (!width || !height || !ctx) return;
    if (canvas.width !== Math.round(width * ratio)) canvas.width = Math.round(width * ratio);
    if (canvas.height !== Math.round(height * ratio)) canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const styles = getComputedStyle(canvas);
    const token = (name: string) => styles.getPropertyValue(name).trim();

    const end = this.points.at(-1)?.t ?? 0;
    const x = (t: number) => width - ((end - t) / this.windowS) * width;
    const y = (v: number) => 1 + (1 - Math.min(v / this.max, 1)) * (height - 2);

    ctx.strokeStyle = token("--border");
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (const share of [0.25, 0.5, 0.75]) {
      const level = Math.round(y(this.max * share)) + 0.5;
      ctx.moveTo(0, level);
      ctx.lineTo(width, level);
    }
    ctx.stroke();

    const line = new Path2D(), area = new Path2D();
    let previous: Point | null = null;
    for (const point of this.points) {
      if (point.v === null) { previous = null; continue; }
      const broken: boolean = previous === null || point.t - previous.t > GAP_S;
      if (broken && previous !== null) area.lineTo(x(previous.t), height);
      if (broken) { line.moveTo(x(point.t), y(point.v)); area.moveTo(x(point.t), height); }
      line.lineTo(x(point.t), y(point.v));
      area.lineTo(x(point.t), y(point.v));
      previous = point;
    }
    if (previous !== null) area.lineTo(x(previous.t), height);

    let ink: string | CanvasGradient = token("--graph-line");
    if (this.paint === "rainbow") {
      const ramp = ctx.createLinearGradient(0, height, 0, 0);
      ramp.addColorStop(0, token("--ramp-lo"));
      ramp.addColorStop(0.62, token("--ramp-mid"));
      ramp.addColorStop(1, token("--ramp-hi"));
      ink = ramp;
    }
    ctx.globalAlpha = ALPHA[this.paint];
    ctx.fillStyle = ink;
    ctx.fill(area);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = ink;
    ctx.lineWidth = LINE;
    ctx.lineJoin = "round";
    ctx.stroke(line);
    this.drawHover(ctx, x, y, height, token);
  }

  private drawHover(ctx: CanvasRenderingContext2D, x: (t: number) => number, y: (v: number) => number,
                    height: number, token: (name: string) => string) {
    if (this.hover === null) return;
    const near = nearest(this.points, x, this.hover);
    if (!near || near.v === null) { this.tip.hidden = true; return; }
    const at = x(near.t);
    ctx.strokeStyle = token("--text-2");
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(Math.round(at) + 0.5, 0);
    ctx.lineTo(Math.round(at) + 0.5, height);
    ctx.stroke();
    ctx.fillStyle = token("--graph-line");
    ctx.strokeStyle = token("--surface-1");
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(at, y(near.v), DOT, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    this.tip.textContent = `${new Date(near.t * 1000).toLocaleTimeString()}  ${this.format(near.v)}`;
    this.tip.hidden = false;
    const room = this.canvas.clientWidth - this.tip.offsetWidth;
    this.tip.style.left = `${Math.max(0, Math.min(at + 8, room))}px`;
  }
}
