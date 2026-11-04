// Dashboard start-up: the one event stream, the hash routes and the once-a-second tick.

import { getJson } from "./format.js";
import { jobView } from "./jobdetail.js";
import { historyView, queueView, tick } from "./jobs.js";
import { Machine } from "./machine.js";

const work = document.getElementById("work");
const conn = document.getElementById("conn");
const machine = new Machine(document.getElementById("machine"));

let snapshot = null;
let snapshotAt = 0;
let route = "";
let closeView = null;

function setConn(state, text) {
  conn.dataset.state = state;
  conn.textContent = text;
}

function showQueue() {
  work.replaceChildren(queueView(snapshot));
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
  else if (route === "history") work.replaceChildren(historyView());
  else showQueue();
}

const stream = new EventSource("/api/events");
stream.onopen = () => setConn("live", "live");
stream.onerror = () => setConn("lost", "reconnecting");
stream.addEventListener("queue", (event) => {
  snapshot = JSON.parse(event.data);
  snapshotAt = performance.now();
  if (route === "") showQueue();
});
stream.addEventListener("metrics", (event) => machine.add(JSON.parse(event.data)));
stream.addEventListener("metrics_history", (event) => {
  machine.reset(JSON.parse(event.data).history);
});

window.addEventListener("hashchange", navigate);
setInterval(() => {
  if (route === "" && snapshot) tick(work, snapshot, (performance.now() - snapshotAt) / 1000);
}, 1000);
navigate();
getJson("/healthz").then((health) => {
  document.getElementById("version").textContent = health.version;
}).catch(() => {});
