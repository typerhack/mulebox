// Agents' requests for the stand-in API (docs/interfaces-m2.md, Requests for more space): what
// waits, the settings history and the Agents option, answered, undone and set as the real
// coordinator does, with a node that takes an approved value a few seconds later. Every name is
// made up. MULEBOX_MOCK_ASKS: `none`, `one`, `two` (the default, a line each) or `three` (one
// folded line).

const GB = 1e9;
const now = () => Date.now() / 1000;
const WHICH = process.env.MULEBOX_MOCK_ASKS ?? "two";

interface Ask { id: string; node: string; setting: string; value: string; reason: string; project: string; job_id: string; client: string;
                asked_at: number; state: string; answer: Record<string, unknown> | null; change_id: string | null }
interface Change { id: string; node: string | null; setting: string; old: string | null; new: string | null; how: string;
                   asked: { value: string | null; note: string | null; asks: Record<string, unknown>[] } | null;
                   by: string | null; at: number; in_force_at: number | null; undo_of: string | null }

let agents = "ask", serial = 0;
const limits: Record<string, string> = { "build-1": "75GB", "build-2": "8GB" };
export const limitOf = (node: string) => limits[node] ?? "20GB";
const id = (kind: string) => `${kind}-mock${String((serial += 1)).padStart(4, "0")}`;

function ask(node: string, value: string, minutes: number, project: string, client: string, reason: string): Ask {
  return { id: id("ask"), node, setting: "max_size", value, reason, project, client, job_id: `job-01JCX${serial}M7Q2`,
           asked_at: now() - minutes * 60, state: "waiting", answer: null, change_id: null };
}
const asks: Ask[] = WHICH === "none" ? [] : [
  ask("build-1", "90GB", 12, "example-app", "alice-laptop",
      "The release branch builds three images and four branches are open this week, about 9 GB more than fits. The cleanup has run; I would rather not drop the package caches."),
  ...(WHICH === "one" ? [] : [ask("build-2", "16GB", 61, "example-ios", "bob-desktop",
      "DerivedData for the two schemes takes about 14 GB per branch, and the simulator runtimes are counted too.")]),
  ...(WHICH === "three" ? [ask("build-1", "84GB", 3, "example-shop", "alice-laptop",
      "The import job unpacks a 3 GB fixture set per branch. 84 GB would cover two branches at once.")] : []),
];
const asked = (list: Ask[], note: string | null = null) => ({
  value: list.reduce((a, b) => (parseFloat(b.value) > parseFloat(a) ? b.value : a), list[0].value), note,
  asks: list.map(({ value, reason, project, job_id, client, asked_at }) => ({ value, reason, project, job_id, client, asked_at })) });
const changes: Change[] = [
  { id: id("chg"), node: null, setting: "agents", old: "allow", new: "ask", how: "agents", asked: null,
    by: "the dashboard, from 192.168.1.50", at: now() - 60, in_force_at: null, undo_of: null },
  { id: id("chg"), node: "build-2", setting: "max_size", old: "6GB", new: "8GB", how: "allowed",
    asked: asked([ask("build-2", "8GB", 2, "example-ios", "bob-desktop", "Two simulator runtimes no longer fit beside DerivedData.")]),
    by: null, at: now() - 110, in_force_at: now() - 104, undo_of: null },
  { id: id("chg"), node: null, setting: "agents", old: "ask", new: "allow", how: "agents", asked: null,
    by: "the dashboard, from 192.168.1.50", at: now() - 240, in_force_at: null, undo_of: null },
  { id: id("chg"), node: "build-2", setting: "max_size", old: "6GB", new: "6GB", how: "declined",
    asked: asked([ask("build-2", "12GB", 300, "example-ios", "bob-desktop", "DerivedData for the two schemes takes about 14 GB per branch.")], "Clean the old schemes first."),
    by: "the dashboard, from 192.168.1.50", at: now() - 5 * 3600, in_force_at: null, undo_of: null },
  { id: id("chg"), node: "build-1", setting: "max_size", old: "70GB", new: "75GB", how: "approved_other",
    asked: asked([ask("build-1", "80GB", 1500, "example-app", "alice-laptop", "The release branch builds three images and four branches are open this week.")]),
    by: "`mulebox storage approve` on alice-laptop", at: now() - 26 * 3600, in_force_at: now() - 26 * 3600 + 8, undo_of: null },
  { id: id("chg"), node: "build-1", setting: "max_size", old: "50GB", new: "70GB", how: "owner", asked: null,
    by: "mulebox machine config", at: now() - 9 * 86400, in_force_at: now() - 9 * 86400 + 12, undo_of: null },
];

function undoable(change: Change): boolean {
  if (["declined", "undo", "agents"].includes(change.how) || change.old === change.new) return false;
  if (changes.some((c) => c.undo_of === change.id)) return false;
  const latest = changes.filter((c) => c.node === change.node && c.setting === change.setting && c.how !== "declined").sort((a, b) => b.at - a.at)[0];
  return latest?.id === change.id;
}
const waiting = () => asks.filter((a) => a.state === "waiting");
// The node takes a new value with its next check-in, here a few seconds later.
function record(change: Omit<Change, "id" | "in_force_at" | "undo_of"> & { undo_of?: string }): Change {
  const made: Change = { id: id("chg"), in_force_at: null, undo_of: null, ...change };
  changes.unshift(made);
  if (made.node && made.how !== "declined") {
    limits[made.node] = String(made.new);
    setTimeout(() => { made.in_force_at = now(); }, 6000);
  }
  return made;
}

export const asksLive = () => ({
  asks: waiting(), allowed: changes.filter((c) => c.how === "allowed" && c.at > now() - 86400).map((c) => ({ ...c, undoable: undoable(c) })),
});
export const asksBody = (editable: boolean, history = 50) => ({
  asks: waiting(), changes: changes.slice(0, history).map((c) => ({ ...c, undoable: undoable(c) })), agents, editable,
});

// A POST: the new body, or [status, refusal].
export function asksPost(body: Record<string, unknown>, by: string): { change_id?: string } | [number, string] {
  if (body.action === "agents") {
    if (body.option !== "ask" && body.option !== "allow") return [400, "agents: one of ask, allow"];
    if (body.option !== agents) record({ node: null, setting: "agents", old: agents, new: String(body.option), how: "agents", asked: null, by, at: now() });
    agents = String(body.option);
    return {};
  }
  if (body.action === "undo") {
    const change = changes.find((c) => c.id === body.change);
    if (!change) return [404, `no change '${String(body.change)}' in the settings history`];
    if (!undoable(change)) return [409, "only a node's latest change of a setting can be undone, once"];
    return { change_id: record({ node: change.node, setting: change.setting, old: change.new, new: change.old, how: "undo",
                                 asked: null, by, at: now(), undo_of: change.id }).id };
  }
  if (body.action !== "answer") return [400, "action: one of answer, undo, agents"];
  const list = waiting().filter((a) => !body.node || a.node === body.node);
  if (!list.length) return [404, `no request waits${body.node ? ` for ${String(body.node)}` : ""}`];
  const node = list[0].node, mine = list.filter((a) => a.node === node), largest = asked(mine).value;
  const value = body.approve ? String(body.value ?? largest) : null;
  if (value !== null && !/^\d+(\.\d+)?GB$/.test(value)) return [400, `max_size: ${value} is not a size`];
  const how = !body.approve ? "declined" : parseFloat(value ?? "") * GB === parseFloat(largest) * GB ? "approved" : "approved_other";
  const made = record({ node, setting: "max_size", old: limitOf(node), new: value ?? limitOf(node), how,
                        asked: asked(mine, body.note ? String(body.note) : null), by, at: now() });
  for (const item of mine) Object.assign(item, { state: body.approve ? "approved" : "declined", change_id: made.id,
                                                 answer: { value, note: body.note ?? null, by, at: now() } });
  return { change_id: made.id };
}
