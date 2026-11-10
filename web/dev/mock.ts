// A stand-in for the dashboard's API, for `npm run dev` with no dashboard: the routes and
// events of docs/interfaces-m2.md over the made-up data of fixtures.ts. Controls change that
// data and publish it, so menus, arrows, Pause and Cancel can be tried without touching a
// real queue.

import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";

import { makeScene } from "./scenes.ts";
import { answerHistory, historyRows } from "./history.ts";
import { AGENT_LOG, CI_LOG, detail, makeMachines, makeQueue, sample, stats, type MockJob } from "./fixtures.ts";

const TOKEN = "mock-token";
const now = () => Date.now() / 1000;
const scene = makeScene(process.env.MULEBOX_MOCK_SCENE);
const queue = scene?.queue ?? makeQueue();
let machines = makeMachines(queue, scene?.machines);
const viewers = new Set<ServerResponse>();
const history = historyRows(queue.recent, now());

const send = (res: ServerResponse, event: string, data: unknown, id?: number) =>
  res.write(`${id === undefined ? "" : `id: ${id}\n`}event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
const json = (res: ServerResponse, body: unknown, status = 200) => {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
};
const text = (res: ServerResponse, body: string, status = 200) => {
  res.writeHead(status, { "Content-Type": "text/plain" });
  res.end(`${body}\n`);
};
const sse = (res: ServerResponse) => res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-store" });

const snapshot = () => ({ now: now(), ...queue });
function panel() {
  const live = machines.filter((m) => m.state !== "offline");
  return { machines, total: machines.length, online: live.length, free_slots: live.reduce((sum, m) => sum + m.free_slots, 0),
           notices: [{ kind: "client", level: "warning", name: "laptop.local",
                       text: "Laptop laptop.local runs mulebox 0.95.2, the build machine 0.95.5.", fix: "Upgrade mulebox on it with `pipx upgrade mulebox`." },
                     ...machines.filter((m) => m.version !== "0.95.5").map((m) => ({ kind: "worker", level: "danger", name: m.name,
                       text: `Worker ${m.name} runs mulebox ${m.version}, the coordinator 0.95.5.`, fix: `Run \`mulebox setup ${m.name}\`.` }))] };
}
const publish = () => viewers.forEach((res) => { send(res, "queue", snapshot()); send(res, "machines", panel()); });
const find = (id: string) => [...queue.running, ...queue.queued, ...queue.recent].find((row) => row.job_id === id);

function renumber() {
  queue.queued.forEach((row, index) => { row.position = index + 1; });
}

function controlJob(row: MockJob, action: string): string | null {
  const at = queue.queued.indexOf(row);
  const to = { first: 0, up: at - 1, down: at + 1, last: queue.queued.length - 1 }[action];
  if (action === "pause") row.paused = true;
  else if (action === "resume") row.paused = false;
  else if (action === "boost") row.boost = true;
  else if (action === "normal") row.boost = false;
  else if (to !== undefined && at >= 0 && to >= 0 && to < queue.queued.length) {
    queue.queued.splice(at, 1);
    queue.queued.splice(to, 0, row);
    renumber();
  } else return "the job cannot move there";
  return null;
}

function cancel(row: MockJob) {
  for (const list of [queue.running, queue.queued]) {
    const at = list.indexOf(row);
    if (at >= 0) list.splice(at, 1);
  }
  Object.assign(row, { state: "finished", outcome: "cancelled", shown_state: "cancelled", section: "recent",
                       finished_at: now(), position: null, duration_s: row.elapsed_s ?? 0 });
  queue.recent.unshift(row);
  renumber();
  machines = makeMachines(queue, scene?.machines).map((m, index) => ({ ...m, state: machines[index].state === "draining" ? "draining" : m.state }));
}

function body(req: IncomingMessage): Promise<Record<string, string>> {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (chunk) => { raw += chunk; });
    req.on("end", () => { try { resolve(JSON.parse(raw || "{}")); } catch { resolve({}); } });
  });
}

function logStream(res: ServerResponse, row: MockJob) {
  const lines = row.kind === "runner" ? CI_LOG : AGENT_LOG;
  sse(res);
  let offset = 0, sent = 0;
  const push = () => {
    if (sent < lines.length) {
      const data = `${lines[sent]}\n`;
      send(res, "log", { offset, next_offset: offset + data.length, data }, offset + data.length);
      offset += data.length;
      sent += 1;
    } else if (row.state === "finished") {
      send(res, "end", detail(row));
      clearInterval(timer);
      res.end();
    } else res.write("event: beat\ndata: {}\n\n");
  };
  const timer = setInterval(push, row.state === "finished" ? 20 : 700);
  res.on("close", () => clearInterval(timer));
}

async function handle(req: IncomingMessage, res: ServerResponse, next: () => void) {
  const url = new URL(req.url ?? "/", "http://mock");
  const path = url.pathname;
  const post = req.method === "POST";
  if (post && req.headers["x-mulebox-token"] !== TOKEN) return text(res, "the page's token is missing or old", 403);
  const jobMatch = /^\/api\/jobs\/([^/]+)(?:\/(.*))?$/.exec(path);
  const machineMatch = /^\/api\/machines\/([^/]+)\/control$/.exec(path);
  if (path === "/healthz") return json(res, { ok: true, version: "0.95.5", lan: false, sign_in: false });
  if (path === "/api/session") return json(res, { action_token: TOKEN, cancel_token: TOKEN });
  if (path === "/api/queue") return json(res, snapshot());
  if (path === "/api/machines") return json(res, panel());
  if (path === "/api/history") {
    const { status, body } = answerHistory(history, url.searchParams);
    await new Promise((done) => setTimeout(done, 100 + Math.random() * 400));
    return status === 200 ? json(res, body) : text(res, String(body), status);
  }
  if (path === "/api/stats") return json(res, stats((url.searchParams.get("day_starts") ?? "").split(",").filter(Boolean).map(Number)));
  if (path === "/api/metrics") {
    const name = url.searchParams.get("machine"), row = machines.find((m) => m.name === name);
    if (name && !row) return text(res, "no such machine", 404);
    const live = !row || row.state !== "offline";
    const history = live ? Array.from({ length: 150 }, (_, i) => sample(now() - 2 * (149 - i), machines.indexOf(row ?? machines[0]))) : [];
    return json(res, { machine: row?.name ?? machines[0].name, host: !row || row.host, last_seen: row?.last_seen ?? now(), history });
  }
  if (path === "/api/events") {
    sse(res);
    viewers.add(res);
    send(res, "queue", snapshot());
    send(res, "machines", panel());
    send(res, "metrics_history", { history: Array.from({ length: 150 }, (_, i) => sample(now() - 2 * (149 - i))) });
    const timer = setInterval(() => send(res, "metrics", sample(now())), 2000);
    res.on("close", () => { clearInterval(timer); viewers.delete(res); });
    return undefined;
  }
  if (machineMatch && post) {
    const row = machines.find((m) => m.name === decodeURIComponent(machineMatch[1]));
    const { action } = await body(req);
    if (!row) return text(res, "no such machine", 404);
    row.state = action === "pause" ? "draining" : row.free_slots ? "available" : "busy";
    publish();
    return json(res, { machine: row.name, action, running: row.jobs.length });
  }
  if (jobMatch) {
    const row = find(decodeURIComponent(jobMatch[1]));
    if (!row) return text(res, "no such job", 404);
    if (!jobMatch[2]) return json(res, detail(row));
    if (jobMatch[2] === "log.txt") return text(res, (row.kind === "runner" ? CI_LOG : AGENT_LOG).join("\n"));
    if (jobMatch[2] === "log") return logStream(res, row);
    if (post && row.state === "finished") return text(res, "the job has finished", 409);
    if (post && jobMatch[2] === "cancel") {
      cancel(row);
      publish();
      return json(res, { job_id: row.job_id, state: "finished", outcome: "cancelled", cancel_requested: true });
    }
    if (post && jobMatch[2] === "control") {
      const { action } = await body(req);
      const refusal = controlJob(row, action);
      if (refusal) return text(res, refusal, 409);
      publish();
      return json(res, { job_id: row.job_id, action, state: row.state, position: row.position, paused: row.paused, boost: row.boost });
    }
  }
  return next();
}

export function mockApi(): Plugin {
  return {
    name: "mulebox-mock-api",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url?.startsWith("/api/") || req.url?.startsWith("/healthz")) void handle(req, res, next);
        else next();
      });
    },
  };
}
