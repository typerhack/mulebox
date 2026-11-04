// Canvas line chart with a crosshair tooltip: one series, one axis, a fixed 0..max scale.
// Colours come from the CSS tokens, so light and dark are defined in one place.

const GAP_S = 8;  // a hole in the samples (a reconnect) stays a hole in the line

function token(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export class LineChart {
  constructor(canvas, tip, { windowS, format }) {
    this.canvas = canvas;
    this.tip = tip;
    this.windowS = windowS;
    this.format = format;
    this.points = [];
    this.max = 100;
    this.hover = null;
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

  update(points, max) {
    this.points = points;
    this.max = max || 1;
    this.draw();
  }

  draw() {
    const { canvas } = this;
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

    ctx.strokeStyle = token("--grid");
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (const share of [0, 0.5, 1]) {
      const level = Math.round(y(this.max * share)) + 0.5;
      ctx.moveTo(0, level);
      ctx.lineTo(width, level);
    }
    ctx.stroke();

    ctx.strokeStyle = token("--series");
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.beginPath();
    let previous = null;
    for (const point of this.points) {
      if (point.v === null) { previous = null; continue; }
      const broken = previous === null || point.t - previous.t > GAP_S;
      ctx[broken ? "moveTo" : "lineTo"](x(point.t), y(point.v));
      previous = point;
    }
    ctx.stroke();
    this.drawHover(ctx, x, y, height);
  }

  drawHover(ctx, x, y, height) {
    if (this.hover === null) return;
    const near = this.nearest(x);
    if (!near) { this.tip.hidden = true; return; }
    const at = x(near.t);
    ctx.strokeStyle = token("--ink-muted");
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(Math.round(at) + 0.5, 0);
    ctx.lineTo(Math.round(at) + 0.5, height);
    ctx.stroke();
    ctx.fillStyle = token("--series");
    ctx.strokeStyle = token("--surface");
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
