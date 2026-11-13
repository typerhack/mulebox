// What the tests of a node's settings window share: a machine's row, the server's answer, and
// the window opened from its button.

import { fireEvent, render, screen } from "@testing-library/react";

import type { NodeSettings } from "../../lib/nodeSettings";
import type { Machine } from "../../lib/types";
import { TipProvider } from "../../ui/Tip";
import { NodeSettingsButton } from "./NodeSettings";

export const machine = (more: Partial<Machine> = {}): Machine =>
  ({ name: "build-2", state: "available", slots: 2, free_slots: 2, capabilities: ["docker"], jobs: [], cores: 16,
     version: "1.16.2", priority: "normal", settings_pending: false, ...more });
export const view = (more: Partial<NodeSettings> = {}): NodeSettings => ({
  worker: "build-2", online: true, draining: false, version: "1.16.2", running: 0, applies: true,
  current: { slots: 2, priority: "normal" }, pending: null, pending_since: null, error: null,
  suggested: { slots: 4, reason: "16 cores and 34.4 GB of memory, at about 4 cores and 6 GB a job" },
  choices: { slots: { min: 1, max: 64 }, priority: ["preferred", "normal", "fallback"] }, editable: true, ...more,
});
export { reply } from "../../lib/heldServer.testing";

export const row = (shown: Machine) => <TipProvider><NodeSettingsButton machine={shown} /></TipProvider>;

export async function open(shown = machine()) {
  const made = render(row(shown));
  fireEvent.click(screen.getByRole("button", { name: "Settings of build-2" }));
  await screen.findByRole("region", { name: "Slots" });
  return made;
}
export const cell = (name: string, label: string) =>
  screen.getByRole("region", { name }).querySelector(`[data-label="${label}"]`)?.textContent;
