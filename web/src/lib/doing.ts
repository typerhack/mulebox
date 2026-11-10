// What a job in a slot is doing now: a word for its stage (a CI job's GitHub step) and the
// cores the job alone uses, from the worker's last reading (dashboard/data.py, `doing`).
// A download is told by its stage: per-job network is not measured, so nothing claims bytes.

import type { Doing } from "./types";

const WORDS: Record<string, string> = {
  toolchain: "Installing tools", prepare: "Preparing", environment: "Preparing",
  images: "Fetching images", services: "Starting services", install: "Installing packages",
  setup: "Setting up", command: "Running", cleanup: "Cleaning up",
};

export function doingWord(doing: Doing | null | undefined): string {
  if (doing?.step) return doing.step;
  if (doing?.stage) return WORDS[doing.stage] ?? doing.stage;
  return "Starting";
}

export const coresText = (pct: number | null | undefined) =>
  (typeof pct === "number" ? (pct / 100).toFixed(1) : "measuring");
