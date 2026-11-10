// The Statistics page (`#/stats`): how long jobs ran, today and since the first job, with
// filters and one breakdown table. The numbers are `/api/stats`, the same module as
// `mulebox stats` (coordinator/stats.py); this page only asks and draws. "Today" is this
// browser's own day: it sends its local midnight, and the last 14 midnights for the chart.

import { duration, el, fill, getJson } from "./format.js";
import { SERIES, dayChart, dayName, hideTip, icon, legend, withTip } from "./statschart.js";

const DIMS = [["project", "Project"], ["kind", "Type"], ["client", "Source"], ["worker", "Machine"], ["job", "Job name"]];
const FILTERS = [["kind", "Type", "all types"], ["project", "Project", "all projects"],
                 ["client", "Source", "all sources"], ["worker", "Machine", "all machines"]];
const DAYS = 14, LIMIT = 8, REFRESH_MS = 60_000;
const state = { filters: {}, by: "project", range: "all", open: false };  // kept between visits

const isGithub = (key) => key === "runner" || key === "github";
const int = (n) => Math.round(n).toLocaleString("en-US");
const runsText = (n) => `${int(n)} ${n === 1 ? "run" : "runs"}`;
const pct = (part, whole) => (whole > 0 ? `${part / whole >= 0.1 ? Math.round((100 * part) / whole)
  : Math.round((1000 * part) / whole) / 10}%` : "0%");
const finished = (r) => r.runs - r.running;
const average = (r) => (finished(r) > 0 ? duration((r.seconds - r.running_seconds) / finished(r)) : "-");

function label(dim, key) {
  if (dim === "kind") return SERIES.find(([kind]) => kind === key)?.[2] ?? key;
  if (dim === "client") return key === "github" ? "GitHub" : key.replace(/\.local$/, "");
  return String(key ?? "-").replace("__", "/");
}
const iconFor = { kind: (k) => (k === "runner" ? "github" : "own"), client: (k) => (k === "github" ? "github" : "laptop"),
                  worker: () => "machine" };
const seriesClass = (dim, key) => (dim === "kind" || dim === "client" ? (isGithub(key) ? "gh" : "own") : "");

function nameCell(dim, key) {
  const which = iconFor[dim]?.(key);
  return el("span", { class: "name" }, which ? icon(which) : null, el("span", { class: "txt", text: label(dim, key) }));
}

function midnights(count) {
  const now = new Date();
  return Array.from({ length: count }, (_, i) =>
    new Date(now.getFullYear(), now.getMonth(), now.getDate() - (count - 1 - i)).getTime() / 1000);
}

async function ask() {
  const days = midnights(DAYS);
  const query = (extra) => new URLSearchParams({ ...Object.fromEntries(
    Object.entries(state.filters).filter(([, v]) => v)), ...extra });
  const [today, all] = await Promise.all([getJson(`/api/stats?${query({ from: days.at(-1) })}`),
                                          getJson(`/api/stats?${query({ day_starts: days.join(",") })}`)]);
  return { today, all };
}

function apart(total) {
  const run = total.running, unknown = total.unknown;
  return el("p", { class: "apart" },
    withTip(el("span", { "data-some": run ? "1" : null, tabindex: "0" }, icon("running"),
      run ? `${int(run)} still running, ${duration(total.running_seconds)} so far` : "none running now"),
      "Runs still going", "They count up to now, and grow until they end."),
    withTip(el("span", { "data-some": unknown ? "1" : null, tabindex: "0" }, icon("unknown"),
      unknown ? `${runsText(unknown)} with no recorded length` : "every length recorded"),
      "No recorded length", "Most often a run cut off by a restart. Counted apart, never as zero."));
}

function head(range, found) {
  const t = found.total;
  const when = range === "today"
    ? el("p", { class: "when" }, el("b", { text: "Today" }), `, ${dayName(found.from, { weekday: "long", day: "numeric", month: "short" })}`)
    : el("p", { class: "when" }, el("b", { text: "All time" }),
         found.first_started_at ? `, since the first job on ${dayName(found.first_started_at, { day: "numeric", month: "short", year: "numeric" })}` : "");
  const box = el("div", { class: "head" }, when, el("p", { class: "big", text: duration(t.seconds) }),
    el("p", { class: "sub", text: `${int(t.seconds / 60)} minutes in ${runsText(t.runs)}` }));
  const rows = SERIES.map(([kind]) => found.by.kind?.find((r) => r.key === kind)).filter(Boolean);
  if (rows.length && t.seconds > 0) {
    const bar = el("div", { class: "split", role: "img",
      "aria-label": rows.map((r) => `${label("kind", r.key)} ${pct(r.seconds, t.seconds)}`).join(", ") },
      ...rows.filter((r) => r.seconds > 0).map((r) => {
        const part = el("i", { class: `seg ${seriesClass("kind", r.key)}` });
        part.style.flex = `${r.seconds} 0 0`;
        return part;
      }));
    box.append(bar, el("div", { class: "split-rows" }, ...rows.flatMap((r) => [
      el("span", { class: "name" }, el("i", { class: `sw ${seriesClass("kind", r.key)}` }), icon(iconFor.kind(r.key)),
         el("span", { class: "txt", text: label("kind", r.key) })),
      el("span", { class: "num", text: duration(r.seconds) }),
      el("span", { class: "num muted", text: pct(r.seconds, t.seconds) })])));
  }
  box.append(apart(t));
  return box;
}

function table(found, redraw) {
  const rows = found.by[state.by] ?? [];
  if (!rows.length) return el("p", { class: "empty", text: "Nothing ran in this period." });
  const max = Math.max(...rows.map((r) => r.seconds), 1), sum = found.total.seconds;
  const shown = state.open ? rows : rows.slice(0, LIMIT);
  const body = shown.map((r) => {
    const fillBar = el("i", { class: seriesClass(state.by, r.key), "data-zero": r.seconds ? null : "1" });
    fillBar.style.width = `${(100 * r.seconds) / max}%`;
    const marks = [r.unknown && withTip(el("span", { class: "odd", tabindex: "0" }, icon("unknown"), String(r.unknown)),
                                        `${runsText(r.unknown)} with no recorded length`),
                   r.running && withTip(el("span", { class: "odd", tabindex: "0" }, icon("running"), String(r.running)),
                                        `${r.running} still running`, `${duration(r.running_seconds)} so far`)];
    return el("tr", {},
      el("td", {}, el("span", { class: "name" }, nameCell(state.by, r.key), ...marks.filter(Boolean))),
      el("td", { class: "barcell wide" }, withTip(el("div", { class: "bar", tabindex: "0" }, fillBar),
         label(state.by, r.key), `${duration(r.seconds)}, ${pct(r.seconds, sum)} of the time`)),
      el("td", { class: "num", text: duration(r.seconds) }),
      el("td", { class: "num soft", text: int(r.runs) }),
      el("td", { class: "num soft wide", text: average(r) }));
  });
  const title = Object.fromEntries(DIMS)[state.by];
  const grid = el("table", {},
    el("thead", {}, el("tr", {}, el("th", { text: title }), el("th", { class: "wide" }), el("th", { class: "num", text: "run time" }),
      el("th", { class: "num", text: "runs" }), el("th", { class: "num wide", text: "average" }))),
    el("tbody", {}, ...body));
  if (rows.length <= LIMIT) return grid;
  const more = el("button", { class: "link", type: "button", text: state.open ? `Show the top ${LIMIT}` : `Show all ${rows.length}` });
  more.addEventListener("click", () => { state.open = !state.open; redraw(); });
  return el("div", {}, grid, el("p", { class: "more" }, more));
}

function filterField(choices, [dim, title, all], onchange) {
  const select = el("select", { "aria-label": title, "data-on": state.filters[dim] ? "1" : null },
    el("option", { value: "", text: all }), ...(choices[dim] ?? []).map((key) => el("option", { value: key, text: label(dim, key) })));
  select.value = state.filters[dim] ?? "";
  select.addEventListener("change", () => { state.filters[dim] = select.value; onchange(); });
  return el("label", { class: "field" }, el("span", { text: title }), el("span", { class: "sel" }, select));
}

function switcher(options, value, pick, aria) {
  return el("div", { class: "seg-ctl", role: "group", "aria-label": aria }, ...options.map(([key, text]) => {
    const button = el("button", { type: "button", "aria-pressed": String(key === value), text });
    button.addEventListener("click", () => pick(key));
    return button;
  }));
}

function page(box, data, reload, redraw) {
  const { today, all } = data;
  // The series that ran under these filters (a GitHub source leaves only GitHub runs).
  const ran = new Set((all.by.kind ?? []).filter((r) => r.runs || r.unknown).map((r) => r.key));
  const shown = SERIES.map(([kind]) => kind).filter((kind) => ran.has(kind));
  const tabs = el("div", { class: "tabs", role: "tablist" }, ...DIMS.map(([dim, title]) => {
    const tab = el("button", { type: "button", role: "tab", "aria-selected": String(dim === state.by), text: title });
    tab.addEventListener("click", () => { state.by = dim; state.open = false; redraw(); });
    return tab;
  }));
  const range = switcher([["today", "Today"], ["all", "All time"]], state.range,
                         (key) => { state.range = key; redraw(); }, "Period for the table");
  fill(box, "Statistics", null, el("div", { class: "stats" },
    el("div", { class: "filters-row" }, ...FILTERS.map((f) => filterField(all.choices, f, reload))),
    el("div", { class: "heads" }, head("today", today), head("all", all)),
    el("p", { class: "measure" }, icon("info"),
       el("span", { text: "Run time is added up: two jobs side by side for ten minutes count as twenty." })),
    el("div", { class: "lower" },
      el("div", {}, el("div", { class: "panel-head" }, el("h3", { text: `Last ${DAYS} days` }), legend(shown)),
         dayChart(all.days, shown)),
      el("div", { class: "breakdown" }, el("div", { class: "panel-head" }, el("h3", { text: "Where the time went" }), range),
         tabs, table(state.range === "today" ? today : all, redraw)))));
}

export function statsView(box) {
  let data = null, timer = null, gone = false;
  const redraw = () => { hideTip(); if (data && !gone) page(box, data, load, redraw); };
  async function load() {
    try {
      data = await ask();
      redraw();
    } catch (failure) {
      if (!gone) fill(box, "Statistics", null, el("p", { class: "failed", role: "alert",
        text: `The numbers did not load: ${failure.message}. \`mulebox stats\` gives the same in a terminal.` }));
    }
  }
  fill(box, "Statistics", null, el("p", { class: "muted", text: "Adding up job minutes" }));
  load();
  timer = setInterval(() => { if (!document.hidden && !document.querySelector("select:focus")) load(); }, REFRESH_MS);
  return () => { gone = true; clearInterval(timer); hideTip(); };
}
