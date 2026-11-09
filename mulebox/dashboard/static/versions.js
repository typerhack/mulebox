// The strip above the panels: what is out of step between the build machine, its workers and
// the laptops that send jobs (dashboard/notices.py), each with the command that fixes it.
// Hidden while everything is in step, which is the usual case.

import { el, warningIcon } from "./format.js";

// `a `b` c` -> text and <code> parts, so a command reads as one.
function withCode(text) {
  return text.split("`").map((part, i) => (i % 2 ? el("code", { text: part }) : part));
}

function notice(item) {
  return el("li", {}, warningIcon(),
            el("span", {}, el("span", {}, ...withCode(item.text)), " ",
               el("span", { class: "fix" }, ...withCode(item.fix))));
}

export function renderVersions(strip, list) {
  const items = list ?? [];
  strip.hidden = !items.length;
  strip.replaceChildren(...(items.length ? [el("ul", {}, ...items.map(notice))] : []));
}
