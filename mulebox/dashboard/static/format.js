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

const TONES = {
  passed: "good", failed: "bad", timed_out: "warn", interrupted: "warn",
  running: "active", starting: "active", cleaning: "active",
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
