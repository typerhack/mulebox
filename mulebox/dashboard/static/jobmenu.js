// Actions menus on the Jobs box: three dots on every job card and waiting row, and "Queue actions"
// beside the tabs for everything at once. Each item sends the same request as its command
// (`mulebox pause|resume|first|up|down|last|boost|normal|cancel`, `mulebox machine pause|resume`).
//
// Every item has an icon, a name and one line on what it does, and only the items that apply
// to the job as it is now are listed. The queue view is redrawn on every queue event, so the
// open menu lives on the page itself and follows its button (found again by `data-menu`).

import { actionToken, post } from "./access.js";
import { drawIcon, el } from "./format.js";
import { MOVE_SHAPES } from "./queuemoves.js";

const WAITING = new Set(["uploading", "queued"]);
const RUNNING = new Set(["starting", "running"]);

// Outlines, stroked in the item's colour (canceljob.css, .action-menu).
const ICON = {
  pause: "M5.75 3.5v9M10.25 3.5v9",
  resume: "M5 3.25v9.5L12.25 8Z",
  freeze: "M8 1.75v12.5M2.6 4.9l10.8 6.2M2.6 11.1l10.8-6.2M6.25 2.75 8 4.25l1.75-1.5M6.25 13.25 8 11.75l1.75 1.5",
  boost: "M9.25 1.75 3.75 9h4.5l-1.5 5.25L12.25 7h-4.5Z",
  calm: "M3 8h10",
  open: "M9.5 2.5h4v4M13.5 2.5 7.75 8.25M11.5 9.5v4h-9v-9h4",
  cancel: "M8 1.75a6.25 6.25 0 1 0 0 12.5 6.25 6.25 0 0 0 0-12.5ZM5.75 5.75l4.5 4.5M10.25 5.75l-4.5 4.5",
  chevron: "M4.5 6.25 8 9.75l3.5-3.5",
  dots: "M2.25 8a1.75 1.75 0 1 0 3.5 0 1.75 1.75 0 1 0-3.5 0ZM6.25 8a1.75 1.75 0 1 0 3.5 0 1.75 1.75 0 1 0-3.5 0ZM10.25 8a1.75 1.75 0 1 0 3.5 0 1.75 1.75 0 1 0-3.5 0Z",
  ...MOVE_SHAPES,
};

// A job's state set by its owner, as small icons beside its state on its card and row, with the
// words as the tooltip and for screen readers; null when nothing is set.
export function steeredIcons(job) {
  const running = RUNNING.has(job.state);
  const marks = [job.paused && (running ? ["freeze", "frozen"] : ["pause", "paused"]),
                 job.boost && ["boost", "boosted"]].filter(Boolean);
  if (!marks.length) return null;
  const words = marks.map(([, word]) => word).join(", ");
  return el("span", { class: "steered", role: "img", "aria-label": words, title: words },
            ...marks.map(([icon]) => drawIcon(ICON[icon], "steer-icon")));
}

let token = null;  // menus show from the first draw after the page has it (app.js draws again)
actionToken().then((given) => { token = given; });
const latest = new Map();  // menu key -> what its items are made from
let open = null;  // { key, node, problem, armed }

const jobUrl = (id, what) => `/api/jobs/${encodeURIComponent(id)}/${what}`;
const control = (id, action) => () => post(jobUrl(id, "control"), { action });
const item = (icon, label, hint, send, tone = null) => ({ icon, label, hint, send, tone });

function moves(job) {
  const at = job.position, last = latest.get("queue")?.total ?? Infinity;
  return [
    at > 1 && item("first", "Move to the front", "Starts before every other waiting job", control(job.job_id, "first")),
    at > 1 && item("up", "Move up one", `To #${at - 1} in line`, control(job.job_id, "up")),
    at < last && item("down", "Move down one", `To #${at + 1} in line`, control(job.job_id, "down")),
    at < last && item("last", "Move to the end", "Every other waiting job goes first", control(job.job_id, "last")),
  ].filter(Boolean);
}

function jobGroups(job) {
  const open_ = item("open", "Open its page", "Its log, stages and all its details",
                     () => { location.hash = `#/job/${encodeURIComponent(job.job_id)}`; });
  if (job.kind === "upgrade") {
    return [moves(job), [open_],
            [item("cancel", "Cancel upgrade", "Takes it out of line; the machine stays as it is",
                  () => post(jobUrl(job.job_id, "cancel")), "danger")]];
  }
  const running = RUNNING.has(job.state);
  const hold = job.paused
    ? item("resume", "Resume", running ? "Goes on where it stopped" : "Can start again, in its place",
           control(job.job_id, "resume"))
    : running
      ? item("freeze", "Freeze", "Stops it where it is, containers too; nothing is lost", control(job.job_id, "pause"))
      : item("pause", "Pause", "Keeps its place in line but does not start", control(job.job_id, "pause"));
  const boost = job.boost
    ? item("calm", "End boost", "Shares the machine again", control(job.job_id, "normal"))
    : item("boost", "Boost", running ? "Gets the CPU and disk first; nothing new starts beside it"
                                     : "Goes first, then gets its machine to itself",
           control(job.job_id, "boost"));
  return [[hold], WAITING.has(job.state) && job.position ? moves(job) : [], [boost, open_],
          [item("cancel", "Cancel job", "Stops it for whoever waits on it",
                () => post(jobUrl(job.job_id, "cancel")), "danger")]];
}

async function each(list, send) {
  const results = await Promise.allSettled(list.map(send));
  const failed = results.filter((r) => r.status === "rejected");
  if (failed.length) throw new Error(`${failed.length} of ${list.length} not changed: ${failed[0].reason.message}`);
}

function queueGroups({ snapshot, machines }) {
  const jobs = [...(snapshot?.running ?? []), ...(snapshot?.queued ?? [])]
    .filter((job) => job.kind === "job" && !job.cancel_requested);
  const toFreeze = jobs.filter((job) => RUNNING.has(job.state) && !job.paused);
  const paused = jobs.filter((job) => job.paused);
  const rows = (machines?.machines ?? []).filter((m) => m.state !== "offline");
  const taking = rows.filter((m) => m.state !== "draining"), held = rows.filter((m) => m.state === "draining");
  const machine = (action) => (m) => post(`/api/machines/${encodeURIComponent(m.name)}/control`, { action });
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  return [
    [taking.length && item("pause", "Pause all machines", "No new job starts; what runs finishes",
                           () => each(taking, machine("pause"))),
     held.length && item("resume", "Resume all machines", held.length === 1 ? "The machine takes jobs again"
                                           : `${held.length} machines take jobs again`,
                         () => each(held, machine("resume")))],
    [toFreeze.length && item("freeze", `Freeze ${plural(toFreeze.length, "running job")}`,
                             "Each stops where it is; nothing is lost",
                             () => each(toFreeze, (j) => control(j.job_id, "pause")())),
     paused.length && item("resume", `Resume ${plural(paused.length, "paused job")}`,
                           "Frozen ones go on, paused ones can start",
                           () => each(paused, (j) => control(j.job_id, "resume")()))],
  ].map((group) => group.filter(Boolean));
}

function close() {
  open?.node.remove();
  document.querySelector(`[data-menu="${open?.key}"]`)?.setAttribute("aria-expanded", "false");
  open = null;
}

function place(node, button) {
  const box = button.getBoundingClientRect();
  node.style.top = `${box.bottom + window.scrollY + 4}px`;
  const left = Math.min(box.right - node.offsetWidth, window.innerWidth - node.offsetWidth - 8);
  node.style.left = `${Math.max(8, left) + window.scrollX}px`;
}

function entry(made) {
  const armed = made.tone === "danger" && open.armed;
  const button = el("button", { type: "button", role: "menuitem", class: made.tone ?? null },
    drawIcon(ICON[made.icon], "item-icon"),
    el("span", { class: "item-text" },
       el("span", { class: "item-label", text: armed ? `Yes, ${made.label.toLowerCase()}` : made.label }),
       el("span", { class: "item-hint", text: armed ? "Click again to confirm" : made.hint })));
  button.addEventListener("click", async () => {
    if (made.tone === "danger" && !open.armed) {
      open.armed = true;
      draw();
      open.node.querySelector(".danger")?.focus();
      return;
    }
    try {
      await made.send();
      close();
    } catch (failure) {
      open.problem = failure.message || "The dashboard did not answer.";
      draw();
    }
  });
  return button;
}

function draw() {
  const source = latest.get(open.key);
  const groups = (source.kind === "queue" ? queueGroups(source) : jobGroups(source.job))
    .filter((group) => group.length);
  const parts = [];
  groups.forEach((group, index) => {
    if (index) parts.push(el("hr", { role: "separator" }));
    parts.push(...group.map(entry));
  });
  if (!groups.length) parts.push(el("p", { class: "empty", text: "Nothing to change right now." }));
  if (open.problem) parts.push(el("p", { class: "failed", role: "alert", text: `Not changed. ${open.problem}` }));
  open.node.replaceChildren(...parts);
}

function show(key, button) {
  if (open?.key === key) { close(); return; }
  close();
  const node = el("div", { class: "action-menu", role: "menu", "aria-label": button.getAttribute("aria-label") });
  open = { key, node, problem: null, armed: false };
  node.addEventListener("keydown", (event) => {
    const items = [...node.querySelectorAll("button")];
    const at = items.indexOf(document.activeElement);
    const step = { ArrowDown: 1, ArrowUp: -1 }[event.key];
    if (event.key === "Escape") { close(); button.focus(); }
    else if (step) { event.preventDefault(); items[(at + step + items.length) % items.length]?.focus(); }
  });
  document.body.append(node);
  draw();
  place(node, button);
  button.setAttribute("aria-expanded", "true");
  node.querySelector("button")?.focus();
}

document.addEventListener("click", (event) => {
  if (open && !open.node.contains(event.target) && !event.target.closest?.("[data-menu]")) close();
});
window.addEventListener("resize", () => close());

// A job's button is the three dots, small enough to sit beside its time; the queue's has words.
function menuButton(key, text, label) {
  const parts = text ? [el("span", { text }), drawIcon(ICON.chevron, "chevron")]
                     : [drawIcon(ICON.dots, "dots")];
  const made = el("button", { type: "button", class: text ? "menu-button" : "menu-button dots-button",
                              "data-menu": key, title: label, "aria-label": label,
                              "aria-haspopup": "menu", "aria-expanded": open?.key === key ? "true" : "false" },
                  ...parts);
  made.addEventListener("click", () => show(key, made));
  return made;
}

// After a redraw: the open menu follows its new button, or closes when its job has gone.
export function followMenu() {
  if (!open) return;
  const button = document.querySelector(`[data-menu="${open.key}"]`);
  if (!button) { close(); return; }
  button.setAttribute("aria-expanded", "true");
  if (!open.node.contains(document.activeElement)) draw();
  place(open.node, button);
}

// The "Actions" button for one job, or null where this page has no controls or nothing to steer.
export function jobMenu(job) {
  const upgradeWaits = job.kind === "upgrade" && WAITING.has(job.state);
  if (!token || !(job.kind === "job" || upgradeWaits) || job.cancel_requested
      || !(WAITING.has(job.state) || RUNNING.has(job.state))) return null;
  latest.set(job.job_id, { kind: "job", job });
  return menuButton(job.job_id, null, `Actions for ${job.project ?? "job"} ${job.job_id}`);
}

// "Queue actions": every machine and every job at once.
export function queueMenu(snapshot, machines) {
  if (!token) return null;
  const total = (snapshot?.queued ?? []).filter((job) => job.position).length;
  latest.set("queue", { kind: "queue", snapshot, machines, total });
  return menuButton("queue", "Queue actions", "Actions for every machine and every job");
}
