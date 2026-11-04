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
// slot for GitHub Actions, so it is named by its project.
export function jobName(job) {
  if (job.kind === "runner") return `${job.project ?? "-"} (CI)`;
  return `${job.project ?? "-"} / ${job.job ?? "-"}`;
}

export function jobLink(job) {
  return el("a", { href: `#/job/${encodeURIComponent(job.job_id)}`, text: jobName(job) });
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
  running: "active", starting: "active", cleaning: "active",
  available: "good", busy: "active", offline: "bad", stuck: "bad",
};

// State as words plus a shape: colour never carries the meaning alone.
export function badge(state) {
  const text = String(state ?? "unknown");
  return el("span", { class: "badge", "data-tone": TONES[text] ?? "plain",
                      text: text.replaceAll("_", " ") });
}

export async function getJson(url) {
  const reply = await fetch(url, { headers: { Accept: "application/json" } });
  if (!reply.ok) throw new Error(`${reply.status} ${(await reply.text()).trim()}`);
  return reply.json();
}
