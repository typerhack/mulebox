// What the strip, the review window and the settings history say about agents' requests, in
// the words of the approved mockups (docs/design-system/approvals/, option A). Sizes print
// with the page's one formatter, `bytes`, so "30GB" reads "30.0 GB".

import type { AskGroup, Change } from "./asks";
import { ago, bytes, day } from "./format";
import { sizeBytes } from "./storage";

export const AGENTS_LABEL: Record<string, string> = { ask: "Ask me first", allow: "Allow, and record it" };
export const AGENTS_SAYS: Record<string, string> = {
  ask: "Nothing changes until you answer. The agent keeps working with what there is.",
  allow: "The change is made at once and recorded with who asked and why. You are told, and can undo it.",
};
export const WARN_SHARE = 0.8;   // agents are told to ask again from 80% of the space (design.md)

export const settingName = (setting: string) => (setting === "max_size" ? "space for mulebox" : setting.replaceAll("_", " "));
export function valueText(setting: string, value: string | null | undefined): string {
  if (setting === "agents") return AGENTS_LABEL[value ?? ""] ?? String(value ?? "-");
  if (setting === "max_size") {
    const found = sizeBytes(value);
    return found === null ? "no limit" : bytes(found);
  }
  return value === null || value === undefined ? "-" : String(value);
}
const space = (value: string | null | undefined) => valueText("max_size", value);

export const when = (at: number, now: number) => { const said = ago(at, now); return said === "now" ? "just now" : said; };
export function names(list: string[]): string {
  const once = [...new Set(list)];
  return once.length < 2 ? once.join("") : `${once.slice(0, -1).join(", ")} and ${once.at(-1)}`;
}
const known = (values: (string | null)[]) => values.filter((v): v is string => !!v);

// "Asked for example-app from alice-laptop, 12 min ago."
function askedFor(group: AskGroup, now: number): string {
  const projects = names(known(group.asks.map((a) => a.project))), clients = names(known(group.asks.map((a) => a.client)));
  const times = names(group.asks.map((a) => when(a.asked_at, now)));
  return `Asked${projects ? ` for ${projects}` : ""}${clients ? ` from ${clients}` : ""}, ${times}.`;
}

export interface Line { head: string; rest: string }
export interface Room { limit: string | null; held: number | null }   // from the node's storage report

// One strip line for the requests of one node.
export function askLine(group: AskGroup, room: Room | null, now: number): Line {
  const up = room?.limit ? `, up from ${space(room.limit)}` : "";
  const who = group.asks.length === 1 ? "An agent asks" : `${group.asks.length} agents ask`;
  const what = group.setting === "max_size"
    ? `${who} for ${group.asks.length > 1 ? "up to " : ""}${space(group.largest)} of space on ${group.node}${up}.`
    : `${who} to set ${settingName(group.setting)} on ${group.node} to ${valueText(group.setting, group.largest)}.`;
  const held = room?.held !== null && room?.held !== undefined ? `mulebox holds ${bytes(room.held)} there. ` : "";
  return { head: what, rest: `${held}${askedFor(group, now)}` };
}

// From three requests: one line with the count, per node, and the oldest age.
export function foldLine(groups: AskGroup[], now: number): Line {
  const count = groups.reduce((n, g) => n + g.asks.length, 0);
  const topic = groups.every((g) => g.setting === "max_size") ? "more space" : "a setting change";
  const per = groups.map((g) => {
    const projects = [...new Set(known(g.asks.map((a) => a.project)))];
    return `${g.asks.length} for ${g.node}${projects.length ? ` (${projects.join(", ")})` : ""}`;
  });
  const oldest = Math.min(...groups.map((g) => g.oldest));
  return { head: `${count} requests for ${topic} wait for your answer.`, rest: `${per.join(", ")}. The oldest was asked ${when(oldest, now)}.` };
}

// What the strip says once answered, until the node has taken it.
export function decidedLine(group: AskGroup, approve: boolean, chosen: string | null, limit: string | null): Line {
  const both = group.asks.length > 1 ? ` One answer for all ${group.asks.length} requests.` : "";
  if (!approve) {
    return { head: `Declined: ${limit ? `the limit stays ${space(limit)}` : "nothing changes"}.`,
             rest: `The agent reads the answer in its next command, and is not told to ask again for 7 days.${both}` };
  }
  const same = sizeBytes(chosen) === sizeBytes(group.largest);
  return { head: same ? `Approved: ${space(chosen)}.` : `Approved at ${space(chosen)}, not the ${space(group.largest)} asked.`,
           rest: `${group.node} takes it with its next check-in; the agent reads the answer in its next command.${both}` };
}

// The grey line for a change applied without asking.
export function allowedLine(change: Change, now: number): Line {
  const first = change.asked?.asks[0];
  const from = first ? ` Asked${first.project ? ` for ${first.project}` : ""}${first.client ? ` from ${first.client}` : ""}, ${when(first.asked_at, now)}.` : "";
  const head = change.setting === "max_size"
    ? `${change.node} now has ${space(change.new)} of space for mulebox, up from ${space(change.old)}.`
    : `${change.node} now has ${settingName(change.setting)} ${valueText(change.setting, change.new)}, from ${valueText(change.setting, change.old)}.`;
  return { head, rest: `Applied without asking, as you allowed.${from}` };
}

// Under the space bar: what a value does, and whether the disk stays above its floor.
export interface Bar { held: number; value: number; free: number; floor: number }
export function spaceSentence({ held, value, free, floor }: Bar): { text: string; warn: boolean } {
  const worst = free - (value - held), after = Math.round((held / value) * 100);
  let text = `At ${bytes(value)} mulebox is at ${after}% of its limit` +
    (after >= WARN_SHARE * 100 ? ", so agents are still told to ask." : `, and agents are told again from ${bytes(value * WARN_SHARE)}.`);
  const most = Math.floor((held + free - floor) / 1e9);
  text += worst < floor
    ? ` Filled to the limit, the disk is left with ${bytes(Math.max(0, worst))} free, ${bytes(floor - worst)} under its floor: the floor's cleanup would then step in first. ${most} GB is the most that stays clear of it.`
    : ` Even filled to the limit, the disk keeps ${bytes(worst)} free, above its floor of ${bytes(floor)}.`;
  return { text, warn: worst < floor };
}

// "Today 10:42", "9 Nov 17:03".
export function stamp(at: number, now: number): string {
  const date = new Date(at * 1000), today = new Date(now * 1000).toDateString() === date.toDateString();
  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${today ? "Today" : day(at, now)} ${time}`;
}

// A settings history entry: what changed, how, and who confirmed, with when it took effect.
const later = (s: number) => (s < 90 ? `${Math.max(0, Math.round(s))} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${Math.round(s / 3600)} h`);
const via = (by: string) => (by.startsWith("the dashboard") ? `on ${by}` : `with ${by}`);
export interface Entry { title: string; how: string; confirm: string; note: string | null; inForce: string | null }
export function entry(change: Change): Entry {
  const asked = change.asked?.value ? `Asked ${valueText(change.setting, change.asked.value)}; ` : "";
  const what = change.setting === "agents" ? "Agents, when an agent asks for a setting change" : `${change.node}, ${settingName(change.setting)}`;
  const title = change.how === "declined" ? `${what}: stays ${valueText(change.setting, change.old)}.`
    : `${what}: ${valueText(change.setting, change.old)} to ${valueText(change.setting, change.new)}.`;
  const by = change.by ?? "";
  const how = {
    owner: "Nobody asked.", agents: "Nobody asked.", undo: "An earlier change undone.",
    approved: `${asked}approved as asked.`, approved_other: `${asked}approved at another value.`,
    declined: `${asked}declined.`, allowed: `${asked}applied without asking, as you allowed.`,
  }[change.how] ?? "";
  const confirm = change.how === "allowed" || !by ? "Nobody confirmed."
    : change.how === "owner" || change.how === "agents" ? `Changed ${via(by)}.`
    : change.how === "declined" ? `Declined ${via(by)}`
    : change.how === "undo" ? `Undone ${via(by)}.` : `Confirmed ${via(by)}.`;
  const takes = change.how !== "declined" && change.how !== "agents" && change.node !== null;
  const inForce = !takes ? null : change.in_force_at !== null
    ? `In force ${later(change.in_force_at - change.at)} later.` : "Not in force yet: the node takes it with its next check-in.";
  return { title, how: how.charAt(0).toUpperCase() + how.slice(1), confirm,
           note: change.how === "declined" ? change.asked?.note ?? null : null, inForce };
}
