// The strip above the panels: what is out of step between the build machine, its workers and
// the laptops that send jobs (dashboard/notices.py), each with the command that fixes it.
// Two levels: `danger` (a worker, jobs can fail) in red with a crossed circle, `warning` (a
// laptop, its jobs still run) in amber with a triangle; the strip takes its worst line's colour.
// A small mark in the header, with the count, stays in sight when the page scrolls and brings
// the strip back into view. Both are hidden while everything is in step, the usual case.

import { ICONS, drawIcon, el } from "./format.js";

const SHAPES = { danger: ICONS.bad, warning: ICONS.warn };

// `a `b` c` -> text and <code> parts, so a command reads as one.
function withCode(text) {
  return text.split("`").map((part, i) => (i % 2 ? el("code", { text: part }) : part));
}

function notice(item) {
  return el("li", { "data-level": item.level }, drawIcon(SHAPES[item.level] ?? ICONS.warn, "level"),
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
    strip.scrollIntoView({ block: "nearest" });
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
