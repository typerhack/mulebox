// Canvas line chart with a crosshair tooltip: one series, one axis, a fixed 0..max scale.
// The area under the line is filled with the load ramp (cool at the bottom, hot at the
// top), so a high value reads by colour as well as by height. Colours come from the CSS
// tokens on the canvas itself, so the theme is defined in the stylesheet only.
// Cost: one draw per new sample (every 2 s) or resize; nothing animates.

const GAP_S = 8;  // a hole in the samples (a reconnect) stays a hole in the line
const FILL_ALPHA = 0.32;

export class LineChart {
  constructor(canvas, tip, { windowS, format }) {
    this.canvas = canvas;
    this.tip = tip;
    this.windowS = windowS;
    this.format = format;
    this.points = [];
    this.max = 100;
    this.hover = null;
    this.tokens = null;
    this.ramp = null;  // cached gradient, keyed by height and theme
    new ResizeObserver(() => this.draw()).observe(canvas);
    canvas.addEventListener("pointermove", (event) => {
      this.hover = event.offsetX;
      this.draw();
    });
    canvas.addEventListener("pointerleave", () => {
      this.hover = null;
      this.tip.hidden = true;
      this.draw();
    });
  }

  token(name) {
    this.tokens ??= getComputedStyle(this.canvas);
    return this.tokens.getPropertyValue(name).trim();
  }

  update(points, max) {
    this.points = points;
    this.max = max || 1;
    this.draw();
  }

  // After a theme switch: forget the cached colours and draw again with the new ones.
  redraw() {
    this.tokens = null;
    this.ramp = null;
    this.draw();
  }

  fillRamp(ctx, height) {
    const key = `${height}:${this.token("--lo")}${this.token("--hi")}`;
    if (this.ramp?.key !== key) {
      const ramp = ctx.createLinearGradient(0, height, 0, 0);
      ramp.addColorStop(0, this.token("--lo"));
      ramp.addColorStop(0.62, this.token("--mid"));
      ramp.addColorStop(1, this.token("--hi"));
      this.ramp = { key, ramp };
    }
    return this.ramp.ramp;
  }

  draw() {
    const { canvas } = this;
    if (document.hidden) return;
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth, height = canvas.clientHeight;
    if (!width || !height) return;
    if (canvas.width !== Math.round(width * ratio)) canvas.width = Math.round(width * ratio);
    if (canvas.height !== Math.round(height * ratio)) canvas.height = Math.round(height * ratio);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const end = this.points.at(-1)?.t ?? 0;
    const x = (t) => width - ((end - t) / this.windowS) * width;
    const y = (v) => 1 + (1 - Math.min(v / this.max, 1)) * (height - 2);

    ctx.strokeStyle = this.token("--line-soft");
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (const share of [0.25, 0.5, 0.75]) {
      const level = Math.round(y(this.max * share)) + 0.5;
      ctx.moveTo(0, level);
      ctx.lineTo(width, level);
    }
    ctx.stroke();

    const line = new Path2D(), area = new Path2D();
    let previous = null;
    for (const point of this.points) {
      if (point.v === null) { previous = null; continue; }
      const broken = previous === null || point.t - previous.t > GAP_S;
      if (broken && previous !== null) area.lineTo(x(previous.t), height);
      if (broken) { line.moveTo(x(point.t), y(point.v)); area.moveTo(x(point.t), height); }
      line.lineTo(x(point.t), y(point.v));
      area.lineTo(x(point.t), y(point.v));
      previous = point;
    }
    if (previous !== null) area.lineTo(x(previous.t), height);
    ctx.globalAlpha = FILL_ALPHA;
    ctx.fillStyle = this.fillRamp(ctx, height);
    ctx.fill(area);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = this.token("--accent");
    ctx.lineWidth = 1.5;
    ctx.lineJoin = "round";
    ctx.stroke(line);
    this.drawHover(ctx, x, y, height);
  }

  drawHover(ctx, x, y, height) {
    if (this.hover === null) return;
    const near = this.nearest(x);
    if (!near) { this.tip.hidden = true; return; }
    const at = x(near.t);
    ctx.strokeStyle = this.token("--ink-muted");
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(Math.round(at) + 0.5, 0);
    ctx.lineTo(Math.round(at) + 0.5, height);
    ctx.stroke();
    ctx.fillStyle = this.token("--accent");
    ctx.strokeStyle = this.token("--bg");
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(at, y(near.v), 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    const time = new Date(near.t * 1000).toLocaleTimeString();
    this.tip.textContent = `${time}  ${this.format(near.v)}`;
    this.tip.hidden = false;
    const room = this.canvas.clientWidth - this.tip.offsetWidth;
    this.tip.style.left = `${Math.max(0, Math.min(at + 8, room))}px`;
  }

  nearest(x) {
    let best = null, distance = Infinity;
    for (const point of this.points) {
      if (point.v === null) continue;
      const gap = Math.abs(x(point.t) - this.hover);
      if (gap < distance) { best = point; distance = gap; }
    }
    return best;
  }
}
