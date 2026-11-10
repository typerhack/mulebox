// The Statistics page's pictures: the day chart (one column per day, mulebox jobs and GitHub
// runs stacked), its legend, outline icons and the tooltip that follows the pointer or focus.
// No inline style attributes (the page's CSP forbids them): sizes go through element.style.

import { drawOutline, duration, el } from "./format.js";

export const PATHS = {
  github: ["M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.4 5.4 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4",
           "M9 18c-4.51 2-5-2-7-2"],
  own: ["M3 8l9-5 9 5v8l-9 5-9-5z", "M3 8l9 5 9-5M12 13v8"],
  laptop: ["M5 5h14a1 1 0 0 1 1 1v10H4V6a1 1 0 0 1 1-1z", "M2 20h20"],
  machine: ["M4 4h16a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z",
            "M4 13h16a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-5a1 1 0 0 1 1-1z", "M7 7.5h.01M7 16.5h.01"],
  running: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M12 7v5l3 2"],
  unknown: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M9.5 9.2a2.6 2.6 0 1 1 3.6 2.4c-.7.4-1.1.9-1.1 1.7M12 17h.01"],
  info: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M12 11v5M12 8h.01"],
};
export const icon = (name) => drawOutline(PATHS[name], `i-${name}`);

// Series: mulebox's own jobs and GitHub runs keep one colour each everywhere on the page.
export const SERIES = [["job", "own", "mulebox jobs"], ["runner", "gh", "GitHub Actions"]];

const day = (from, opts) => new Date(from * 1000).toLocaleDateString("en-GB", opts);
export const dayName = day;
const runs = (n) => `${n.toLocaleString("en-US")} ${n === 1 ? "run" : "runs"}`;

const tip = el("div", { class: "stat-tip", role: "tooltip", hidden: "" });
function place(x, y) {
  const width = tip.offsetWidth, height = tip.offsetHeight;
  tip.style.left = `${Math.max(6, Math.min(innerWidth - width - 6, x - width / 2))}px`;
  tip.style.top = `${y - height - 12 < 6 ? y + 16 : y - height - 12}px`;
}
// `lines`: the tooltip's title, then its lines.
export function withTip(node, title, ...lines) {
  const show = (x, y) => {
    if (!tip.isConnected) document.body.append(tip);
    tip.replaceChildren(el("b", { text: title }), ...lines.map((text) => el("span", { text })));
    tip.hidden = false;
    place(x, y);
  };
  node.addEventListener("pointermove", (event) => show(event.clientX, event.clientY));
  node.addEventListener("pointerleave", () => { tip.hidden = true; });
  node.addEventListener("focus", () => {
    const box = node.getBoundingClientRect();
    show(box.left + box.width / 2, box.top + box.height / 3);
  });
  node.addEventListener("blur", () => { tip.hidden = true; });
  return node;
}
export const hideTip = () => { tip.hidden = true; };

export function legend(shown) {
  return el("p", { class: "legend" }, ...SERIES.filter(([kind]) => shown.includes(kind)).map(([kind, cls, name]) =>
    el("span", {}, el("i", { class: `sw ${cls}` }), icon(kind === "runner" ? "github" : "own"), name)));
}

// Columns on one scale with two grid lines, the hours on the left and the day numbers below.
export function dayChart(days, shown) {
  const value = (d) => shown.reduce((sum, kind) => sum + (d.kinds?.[kind] ?? 0), 0);
  const top = Math.max(...days.map(value), 1) / 3600;
  const step = [0.25, 0.5, 1, 2, 3, 4, 6, 8, 12, 24, 48].find((s) => s * 2 >= top) ?? Math.ceil(top / 2);
  const max = step * 2 * 3600;
  const tick = (hours) => (hours > 0 && hours < 1 ? `${hours * 60}m` : `${hours}h`);
  const last = days.length - 1;
  const cols = days.map((d, index) => {
    const total = value(d);
    const segs = [...SERIES].reverse().filter(([kind]) => shown.includes(kind) && d.kinds?.[kind] > 0)
      .map(([kind, cls]) => {
        const seg = el("i", { class: `seg ${cls}` });
        seg.style.flex = `${d.kinds[kind]} 0 0`;
        return seg;
      });
    let stack = null;
    if (total > 0) {
      stack = el("span", { class: "stack" }, ...segs);
      stack.style.height = `${Math.max(1.5, (100 * total) / max)}%`;
    }
    const col = el("button", { class: "col", type: "button",
      "aria-label": `${day(d.from, { weekday: "long", day: "numeric", month: "long" })}: ${duration(total)}` }, stack);
    const parts = shown.length > 1 ? SERIES.map(([kind, , name]) => `${name} ${duration(d.kinds?.[kind] ?? 0)}`) : [];
    return withTip(col, `${day(d.from, { weekday: "short", day: "numeric", month: "short" })}${index === last ? ", today" : ""}`,
      ...(total > 0 ? [`${duration(total)} in ${runs(d.runs)}`, ...parts] : ["nothing ran"]));
  });
  let month = null;
  const months = days.map((d) => {
    const name = day(d.from, { month: "short" });
    const text = name === month ? "" : name;
    month = name;
    return el("span", { text });
  });
  const ticks = [0, 1, 2].map((n) => {
    const label = el("span", { text: tick(step * n) });
    label.style.bottom = `${n * 50}%`;
    return label;
  });
  const chart = el("div", { class: "chart", role: "group", "aria-label": `Run time per day, last ${days.length} days` },
    el("div", { class: "yaxis" }, ...ticks),
    el("div", { class: "plot" }, el("div", { class: "grid top" }), el("div", { class: "grid mid" }),
       el("div", { class: "cols" }, ...cols)),
    el("div", { class: "xaxis" }, ...days.map((d, index) =>
      el("span", { "data-now": index === last ? "1" : null, text: String(new Date(d.from * 1000).getDate()) }))),
    el("div", { class: "months" }, ...months));
  return chart;
}
