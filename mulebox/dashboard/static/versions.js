// The strip above the panels: what is out of step between the build machine, its workers and
// the laptops that send jobs (dashboard/notices.py), each with the command that fixes it.
// Two levels: `danger` (a worker, jobs can fail) in red with a crossed circle, `warning` (a
// laptop, its jobs still run) in amber with a triangle; the strip takes its worst line's colour.
// A small mark in the header, with the count, stays in sight when the page scrolls and brings
// the strip back into view. Both are hidden while everything is in step, the usual case.

import { drawIcon, el } from "./format.js";

// Outlines, drawn with a stroke in the level's colour (versions.css), no fill.
const SHAPES = {
  danger: "M8 1.75a6.25 6.25 0 1 0 0 12.5 6.25 6.25 0 0 0 0-12.5ZM5.75 5.75l4.5 4.5M10.25 5.75l-4.5 4.5",
  warning: "M6.9 2.6a1.27 1.27 0 0 1 2.2 0l5.4 9.6A1.25 1.25 0 0 1 13.4 14H2.6a1.25 1.25 0 0 1-1.1-1.8ZM8 6v3.4M8 11.6v.01",
};

// `a `b` c` -> text and <code> parts, so a command reads as one.
function withCode(text) {
  return text.split("`").map((part, i) => (i % 2 ? el("code", { text: part }) : part));
}

function notice(item) {
  return el("li", { "data-level": item.level }, drawIcon(SHAPES[item.level] ?? SHAPES.warning, "level"),
            el("span", {}, el("span", {}, ...withCode(item.text)), " ",
               el("span", { class: "fix" }, ...withCode(item.fix))));
}

const worst = (items) => (items.some((item) => item.level === "danger") ? "danger" : "warning");

function renderMark(mark, strip, items) {
  mark.hidden = !items.length;
  if (!items.length) return;
  const level = worst(items);
  const word = `${items.length} out of step`;
  mark.dataset.level = level;
  mark.setAttribute("aria-label", `${word}: show`);
  mark.title = word;
  mark.replaceChildren(drawIcon(SHAPES[level], "level"), el("span", { class: "num", text: String(items.length) }));
  mark.onclick = () => {
    // Below the sticky header, not under it.
    strip.style.scrollMarginTop = `${(mark.closest("header")?.offsetHeight ?? 0) + 8}px`;
    strip.scrollIntoView({ block: "start" });
    strip.focus({ preventScroll: true });
  };
}

export function renderVersions(strip, mark, list) {
  const items = list ?? [];
  strip.hidden = !items.length;
  strip.dataset.level = worst(items);
  strip.replaceChildren(...(items.length ? [el("ul", {}, ...items.map(notice))] : []));
  renderMark(mark, strip, items);
}
