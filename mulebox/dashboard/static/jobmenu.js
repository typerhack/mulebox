// "More actions" menus on the Jobs box: one on every job card and waiting row, and one for the
// whole queue in the box's header. Each item sends the same request as its command
// (`mulebox pause|resume|first|up|down|last|boost|normal|cancel`, `mulebox machine pause|resume`).
//
// The queue view is redrawn on every queue event, so the open menu lives outside it, on the
// page itself, and follows its button (found again by `data-menu`) after each redraw. The
// latest copy of each job comes with that redraw, so the items always match its state.

import { actionToken, post } from "./access.js";
import { drawIcon, el } from "./format.js";

const DOTS = "M3 8a1.25 1.25 0 1 0 2.5 0A1.25 1.25 0 0 0 3 8Zm3.75 0a1.25 1.25 0 1 0 2.5 0 1.25 1.25 0 0 0-2.5 0Zm3.75 0a1.25 1.25 0 1 0 2.5 0 1.25 1.25 0 0 0-2.5 0Z";
const WAITING = new Set(["uploading", "queued"]);
const RUNNING = new Set(["starting", "running"]);

let token = null;  // menus show from the first render after the page has it
actionToken().then((given) => { token = given; });
const latest = new Map();  // menu key -> what its items are made from
let open = null;  // { key, node, problem, armed }

const jobUrl = (id, what) => `/api/jobs/${encodeURIComponent(id)}/${what}`;
const control = (id, action) => post(jobUrl(id, "control"), { action });

function upgradeItems(job) {
  return [["Move to the front", () => control(job.job_id, "first")],
          ["Move up one", () => control(job.job_id, "up")],
          ["Move down one", () => control(job.job_id, "down")],
          ["Move to the end", () => control(job.job_id, "last")],
          ["Open its page", () => { location.hash = `#/job/${encodeURIComponent(job.job_id)}`; }],
          ["Cancel upgrade", () => post(jobUrl(job.job_id, "cancel")), "danger"]];
}

function jobItems(job) {
  if (job.kind === "upgrade") return upgradeItems(job);
  const running = RUNNING.has(job.state);
  const items = [job.paused
    ? ["Resume", () => control(job.job_id, "resume")]
    : [running ? "Freeze (pause where it is)" : "Pause (keep its place)", () => control(job.job_id, "pause")]];
  if (WAITING.has(job.state) && job.position) {
    items.push(["Move to the front", () => control(job.job_id, "first")],
               ["Move up one", () => control(job.job_id, "up")],
               ["Move down one", () => control(job.job_id, "down")],
               ["Move to the end", () => control(job.job_id, "last")]);
  }
  items.push(job.boost ? ["End boost", () => control(job.job_id, "normal")]
                       : ["Boost (whole machine, first in line)", () => control(job.job_id, "boost")]);
  items.push(["Open its page", () => { location.hash = `#/job/${encodeURIComponent(job.job_id)}`; }]);
  items.push(["Cancel job", () => post(jobUrl(job.job_id, "cancel")), "danger"]);
  return items;
}

async function each(list, send) {
  const results = await Promise.allSettled(list.map(send));
  const failed = results.filter((r) => r.status === "rejected");
  if (failed.length) throw new Error(`${failed.length} of ${list.length} not changed: ${failed[0].reason.message}`);
}

function queueItems({ snapshot, machines }) {
  const jobs = [...(snapshot?.running ?? []), ...(snapshot?.queued ?? [])]
    .filter((job) => job.kind === "job" && !job.cancel_requested);
  const running = jobs.filter((job) => RUNNING.has(job.state));
  const rows = (machines?.machines ?? []).filter((m) => m.state !== "offline");
  const machine = (m, action) => post(`/api/machines/${encodeURIComponent(m.name)}/control`, { action });
  return [
    [`Pause all machines (no new jobs start)`, () => each(rows.filter((m) => m.state !== "draining"), (m) => machine(m, "pause")),
     null, !rows.some((m) => m.state !== "draining")],
    ["Resume all machines", () => each(rows.filter((m) => m.state === "draining"), (m) => machine(m, "resume")),
     null, !rows.some((m) => m.state === "draining")],
    [`Freeze all running jobs (${running.filter((j) => !j.paused).length})`,
     () => each(running.filter((j) => !j.paused), (j) => control(j.job_id, "pause")), null,
     !running.some((j) => !j.paused)],
    [`Resume all paused jobs (${jobs.filter((j) => j.paused).length})`,
     () => each(jobs.filter((j) => j.paused), (j) => control(j.job_id, "resume")), null,
     !jobs.some((j) => j.paused)],
  ];
}

function close() {
  open?.node.remove();
  document.querySelector(`[data-menu="${open?.key}"]`)?.setAttribute("aria-expanded", "false");
  open = null;
}

function place(node, button) {
  const box = button.getBoundingClientRect();
  node.style.top = `${box.bottom + window.scrollY + 4}px`;
  node.style.left = `${Math.max(8, Math.min(box.right - node.offsetWidth, window.innerWidth - node.offsetWidth - 8)) + window.scrollX}px`;
}

function draw() {
  const { key, node } = open;
  const source = latest.get(key);
  const items = source.kind === "queue" ? queueItems(source) : jobItems(source.job);
  node.replaceChildren(...items.map(([text, send, tone, disabled]) => {
    const sure = tone === "danger" && open.armed;
    const yes = source.job?.kind === "upgrade" ? "Yes, cancel the upgrade"
                                                : "Yes, cancel: it stops for whoever waits on it";
    const made = el("button", { type: "button", role: "menuitem", class: tone ?? null,
                                disabled: disabled ? "" : null, text: sure ? yes : text });
    made.addEventListener("click", async () => {
      if (tone === "danger" && !open.armed) { open.armed = true; draw(); node.querySelector(".danger")?.focus(); return; }
      try {
        await send();
        close();
      } catch (failure) {
        open.problem = failure.message || "The dashboard did not answer.";
        draw();
      }
    });
    return made;
  }), ...(open.problem ? [el("p", { class: "failed", role: "alert", text: `Not changed. ${open.problem}` })] : []));
}

function show(key, button) {
  if (open?.key === key) { close(); return; }
  close();
  const node = el("div", { class: "action-menu", role: "menu", "aria-label": button.getAttribute("aria-label") });
  open = { key, node, problem: null, armed: false };
  node.addEventListener("keydown", (event) => {
    const items = [...node.querySelectorAll("button:not([disabled])")];
    const at = items.indexOf(document.activeElement);
    const step = { ArrowDown: 1, ArrowUp: -1 }[event.key];
    if (event.key === "Escape") { const back = button; close(); back.focus(); }
    else if (step) { event.preventDefault(); items[(at + step + items.length) % items.length]?.focus(); }
  });
  document.body.append(node);
  draw();
  place(node, button);
  button.setAttribute("aria-expanded", "true");
  node.querySelector("button:not([disabled])")?.focus();
}

document.addEventListener("click", (event) => {
  if (open && !open.node.contains(event.target) && !event.target.closest?.("[data-menu]")) close();
});
window.addEventListener("resize", () => close());

function menuButton(key, label) {
  const made = el("button", { type: "button", class: "menu-button", "data-menu": key, title: label,
                              "aria-label": label, "aria-haspopup": "menu",
                              "aria-expanded": open?.key === key ? "true" : "false" },
                  drawIcon(DOTS, "dots"));
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

// The menu button for one job, or null where this page has no controls or nothing to steer.
export function jobMenu(job) {
  const upgradeWaits = job.kind === "upgrade" && WAITING.has(job.state);
  if (!token || !(job.kind === "job" || upgradeWaits) || job.cancel_requested
      || !(WAITING.has(job.state) || RUNNING.has(job.state))) return null;
  latest.set(job.job_id, { kind: "job", job });
  return menuButton(job.job_id, `Actions for ${job.project ?? "job"} ${job.job_id}`);
}

// The menu button for the whole queue: every machine and every job at once.
export function queueMenu(snapshot, machines) {
  if (!token) return null;
  latest.set("queue", { kind: "queue", snapshot, machines });
  return menuButton("queue", "Actions for the whole queue");
}
