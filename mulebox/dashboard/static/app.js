// Dashboard start-up: the one event stream, the hash routes, the theme switch and the
// once-a-second tick.

import { getJson } from "./format.js";
import { jobView } from "./jobdetail.js";
import { historyView, queueView, tick, tickLeft } from "./jobs.js";
import { Machine } from "./machine.js";
import { renderMachines } from "./machines.js";

const work = document.getElementById("work");
const conn = document.getElementById("conn");
const machine = new Machine({ cpu: document.getElementById("cpu"),
                              mem: document.getElementById("mem"),
                              disk: document.getElementById("disk") });

let snapshot = null;
let snapshotAt = 0;
let machines = null;
let route = "";
let closeView = null;

function setConn(state, text) {
  conn.dataset.state = state;
  conn.textContent = text;
}

const age = () => (performance.now() - snapshotAt) / 1000;

function showQueue() {
  queueView(work, snapshot, machines);
  if (snapshot) {  // never show the snapshot's older times
    tick(work, snapshot, age());
    tickLeft(document, snapshot, age());
  }
}

function navigate() {
  closeView?.();
  closeView = null;
  route = location.hash.replace(/^#\/?/, "");
  const name = route.startsWith("history") ? "history" : "queue";
  document.querySelectorAll("[data-nav]").forEach((link) => {
    if (link.dataset.nav === name) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  if (route.startsWith("job/")) closeView = jobView(work, decodeURIComponent(route.slice(4)));
  else if (route === "history") historyView(work);
  else showQueue();
}

async function sessionEnded() {
  const reply = await fetch("/healthz").catch(() => null);
  if (reply?.status === 401) location.assign("/login");
  else setConn("lost", "closed; reload the page");
}

async function signOut() {
  await fetch("/logout", { method: "POST" }).catch(() => {});
  location.assign("/login");
}

// Theme: theme.js chose one before the first paint. The button steps through the modes and
// shows the current one; in system mode the page follows the system as it changes.
const themeButton = document.getElementById("theme");
const systemLight = window.matchMedia("(prefers-color-scheme: light)");
const MODES = ["system", "light", "dark"];
const nextMode = (mode) => MODES[(MODES.indexOf(mode) + 1) % MODES.length];
function applyMode(mode) {
  const root = document.documentElement;
  root.dataset.mode = mode;
  root.dataset.theme = mode === "system" ? (systemLight.matches ? "light" : "dark") : mode;
  const label = `Theme: ${mode}. Switch to ${nextMode(mode)}`;
  themeButton.setAttribute("aria-label", label);
  themeButton.title = label;
  machine.redraw();  // the graphs read their colours from the stylesheet
}
function saveMode(mode) {
  try {
    if (mode === "system") localStorage.removeItem("mulebox-theme");
    else localStorage.setItem("mulebox-theme", mode);
  } catch { /* private mode: the choice lasts until the page closes */ }
}
applyMode(document.documentElement.dataset.mode ?? "system");
themeButton.addEventListener("click", () => {
  const mode = nextMode(document.documentElement.dataset.mode);
  saveMode(mode);
  applyMode(mode);
});
systemLight.addEventListener("change", () => {
  if (document.documentElement.dataset.mode === "system") applyMode("system");
});

const stream = new EventSource("/api/events");
stream.onopen = () => setConn("live", "live");
stream.onerror = () => {
  setConn("lost", "reconnecting");
  // The browser retries a dropped connection by itself, but gives up on a refused one.
  if (stream.readyState === EventSource.CLOSED) sessionEnded();
};
stream.addEventListener("queue", (event) => {
  snapshot = JSON.parse(event.data);
  snapshotAt = performance.now();
  if (route === "") showQueue();
});
// Readings move every couple of seconds; the lanes only care who is there and whether
// it is online, so they are not redrawn for a reading alone.
let laneKey = "";
stream.addEventListener("machines", (event) => {
  machines = JSON.parse(event.data);
  renderMachines(document.getElementById("machines"), machines);
  const key = JSON.stringify(machines.machines.map((m) => [m.name, m.state]));
  if (key !== laneKey) {
    laneKey = key;
    if (route === "") showQueue();
  }
});
stream.addEventListener("metrics", (event) => machine.add(JSON.parse(event.data)));
stream.addEventListener("metrics_history", (event) => {
  machine.reset(JSON.parse(event.data).history);
});

window.addEventListener("hashchange", navigate);
setInterval(() => {
  if (!snapshot || document.hidden) return;
  if (route === "") tick(work, snapshot, age());
  tickLeft(document, snapshot, age());
}, 1000);
navigate();
getJson("/healthz").then((health) => {
  document.getElementById("version").textContent = health.version;
  const signout = document.getElementById("signout");
  signout.hidden = !health.sign_in;
  signout.addEventListener("click", signOut);
}).catch(() => {});
