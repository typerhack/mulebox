// What a viewer chose, kept per browser: the theme (system, light or dark) and the meter style
// (auto, gauge or rainbow; docs/design-system.md, Meter styles). public/theme.js applies both
// before the first paint; this module holds the switches and follows the system as it changes.
// `data-theme` and `data-paint` on <html> are what the stylesheet colours by.

import { createStore, useStore } from "./store";

export type ThemeMode = "system" | "light" | "dark";
export type MeterMode = "auto" | "gauge" | "rainbow";
export const THEME_MODES: ThemeMode[] = ["system", "light", "dark"];
export const METER_MODES: MeterMode[] = ["auto", "gauge", "rainbow"];
const THEME_KEY = "mulebox-theme", METER_KEY = "mulebox-meters";

function read<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  let value: string | null;
  try { value = localStorage.getItem(key); } catch { value = null; }
  return (allowed as readonly string[]).includes(value ?? "") ? (value as T) : fallback;
}

// The default is not stored, so a later change of the default reaches every browser.
function write(key: string, value: string, fallback: string) {
  try {
    if (value === fallback) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch { /* private mode: the choice lasts until the page closes */ }
}

export interface Look {
  mode: ThemeMode;
  theme: "light" | "dark";
  meters: MeterMode;
  paint: "gauge" | "rainbow";
}

const systemLight = () => window.matchMedia?.("(prefers-color-scheme: light)").matches ?? false;

export function resolve(mode: ThemeMode, meters: MeterMode, light: boolean): Look {
  const theme = mode === "system" ? (light ? "light" : "dark") : mode;
  const paint = meters === "auto" ? (theme === "light" ? "rainbow" : "gauge") : meters;
  return { mode, theme, meters, paint };
}

const current = () => resolve(read(THEME_KEY, THEME_MODES, "system"), read(METER_KEY, METER_MODES, "auto"),
                              systemLight());
export const lookStore = createStore<Look>(current());

function apply(look: Look) {
  const root = document.documentElement;
  root.dataset.mode = look.mode;
  root.dataset.theme = look.theme;
  root.dataset.paint = look.paint;
  lookStore.set(look);
}

export function setTheme(mode: ThemeMode) {
  write(THEME_KEY, mode, "system");
  apply(resolve(mode, lookStore.get().meters, systemLight()));
}

export function setMeters(meters: MeterMode) {
  write(METER_KEY, meters, "auto");
  apply(resolve(lookStore.get().mode, meters, systemLight()));
}

export function startLook() {
  apply(current());
  window.matchMedia?.("(prefers-color-scheme: light)").addEventListener("change", () => apply(current()));
}

export const useLook = () => useStore(lookStore);
export const next = <T,>(list: readonly T[], value: T): T => list[(list.indexOf(value) + 1) % list.length];

// A small remembered choice, such as the Jobs box's tab.
export function remembered<T extends string>(key: string, allowed: readonly T[], fallback: T) {
  return {
    read: () => read(key, allowed, fallback),
    write: (value: T) => { try { localStorage.setItem(key, value); } catch { /* private mode */ } },
  };
}
