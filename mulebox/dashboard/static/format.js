// Small display helpers shared by the views. Same duration format as the terminal view.

export function duration(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  const pad = (n) => String(n).padStart(2, "0");
  if (h) return `${h}h ${pad(m)}m`;
  if (m) return `${m}m ${pad(s)}s`;
  return `${s}s`;
}

export function bytes(n) {
  if (n === null || n === undefined) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = n, unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function clock(seconds) {
  if (!seconds) return "-";
  return new Date(seconds * 1000).toLocaleString([], {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

// A link target only when it is really http(s): stored values never become script URLs.
export function safeUrl(text) {
  try {
    const url = new URL(text);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

// A job's display name and its link to the detail view. A runner reservation only holds a
// slot for GitHub Actions, so it is named by its repository, without the owner: the project of
// one is `owner__repo` (coordinator/reservations.py). `repository` gives the full name back.
const isCI = (job) => job.kind === "runner";
export const repository = (job) => (job.project ?? "-").replace("__", "/");

export function jobName(job) {
  if (isCI(job)) return (job.project ?? "-").split("__").pop();
  return `${job.project ?? "-"} / ${job.job ?? "-"}`;
}

// The end of a job's id: ids made close in time start alike, their ends never do.
export const shortId = (job) => job.job_id.slice(-6);

// Where a job came from, as a word: CI, or the system of the laptop that sent it. Older
// clients do not say, and then the line goes without it.
const origin = (job) => (isCI(job) ? "CI" : job.client_os ?? null);

export const runText = (job) =>
  [origin(job), job.branch ?? "-", shortId(job)].filter(Boolean).join(", ");

// GitHub's mark for a CI slot, a laptop for a job an agent sent. The word in `runText` says
// the same, so the icon is decoration for a quicker eye.
const GITHUB = "M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 " +
  "0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82" +
  "-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27" +
  "-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 " +
  "3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67" +
  ".01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15" +
  ".45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z";
const LAPTOP = "M2.5 3h11v7.5h-11ZM3.75 4.25v5h8.5v-5ZM.5 11.5h15v.75c0 .7-.55 1.25-1.25 " +
  "1.25H1.75C1.05 13.5.5 12.95.5 12.25Z";

export function jobLink(job) {
  return el("a", { href: `#/job/${encodeURIComponent(job.job_id)}`, class: "job-link" },
    drawIcon(isCI(job) ? GITHUB : LAPTOP, "origin"), el("span", { text: jobName(job) }));
}

// Build a DOM element. Text always goes through textContent, so nothing is parsed as HTML.
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === null || value === undefined) continue;
    if (name === "class") node.className = value;
    else if (name === "text") node.textContent = value;
    else node.setAttribute(name, value);
  }
  node.append(...children.filter((c) => c !== null && c !== undefined));
  return node;
}

// A box: its title on the border, a note on the right of the border, a scrolling body.
export function fill(box, title, note, ...children) {
  const parts = [el("h2", { text: title })];
  if (note !== null && note !== undefined) parts.push(el("span", { class: "note" }, note));
  parts.push(el("div", { class: "body" }, ...children));
  box.replaceChildren(...parts);
  return parts.at(-1);
}

// A meter on the load ramp; `set(share)` moves the cover that hides the unused part.
export function meter(attrs = {}) {
  const rest = el("div", { class: "rest" });
  const node = el("div", { class: "meter", role: "img", ...attrs }, el("div", { class: "ramp" }), rest);
  return { node, set(share) { rest.style.width = `${(100 - Math.max(0, Math.min(1, share)) * 100).toFixed(1)}%`; } };
}

const TONES = {
  passed: "good", failed: "bad", timed_out: "warn", interrupted: "warn",
  "stopped: stuck": "warn",
  running: "active", starting: "active", cleaning: "active",
  available: "good", busy: "active", offline: "bad", stuck: "bad",
};

// State as words plus a shape: colour never carries the meaning alone.
export const toneOf = (state) => TONES[String(state ?? "unknown")] ?? "plain";
const words = (state) => String(state ?? "unknown").replaceAll("_", " ");
export const stateText = (state) => words(state).replace(/^./, (first) => first.toUpperCase());

export function badge(state) {
  return el("span", { class: "badge", "data-tone": toneOf(state), text: words(state) });
}

// An icon, drawn here because `el` cannot make SVG. Decoration: the word beside it carries
// the meaning.
export function drawIcon(path, name) {
  const ns = "http://www.w3.org/2000/svg";
  const icon = document.createElementNS(ns, "svg");
  icon.setAttribute("viewBox", "0 0 16 16");
  icon.setAttribute("aria-hidden", "true");
  icon.classList.add(name);
  const shape = document.createElementNS(ns, "path");
  shape.setAttribute("fill-rule", "evenodd");
  shape.setAttribute("d", path);
  icon.append(shape);
  return icon;
}

export const warningIcon = () => drawIcon("M8 1 15.5 15H.5ZM7 6v5h2V6Zm0 6v2h2v-2Z", "warning");

export const timeLeft = (seconds) => `${duration(seconds)} left`;

// The job among `jobs` that stops first, and how many nobody is watching.
export function soonest(jobs) {
  const alone = jobs.filter((job) => job.question);
  alone.sort((a, b) => a.question.left_s - b.question.left_s);
  return { job: alone[0] ?? null, count: alone.length };
}

// Warning icon, the word and the time left. `data-left` is the job id, so tick.js can count it
// down, and drop the whole mark once somebody watches the job again.
export function questionMark(job, count = 1) {
  if (!job?.question) return null;
  const word = count > 1 ? `${count} need an answer` : "needs an answer";
  return el("span", { class: "alone", "data-alone": job.job_id,
                      title: `The agent has not answered. A working job goes on; a stuck one stops: ${job.question.reason}.` },
    warningIcon(), el("span", { text: word }),
    el("span", { class: "num", "data-left": job.job_id, text: timeLeft(job.question.left_s) }));
}

export async function getJson(url) {
  const reply = await fetch(url, { headers: { Accept: "application/json" } });
  if (!reply.ok) throw new Error(`${reply.status} ${(await reply.text()).trim()}`);
  return reply.json();
}
