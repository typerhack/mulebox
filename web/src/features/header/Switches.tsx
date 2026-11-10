// The theme switch (system, light, dark) and the meter style switch (auto, gauge, rainbow).
// Each steps through its choices and shows the current one; both are remembered per browser.

import { Contrast, Gauge, Monitor, Moon, Rainbow, Sun } from "lucide-react";

import { METER_MODES, THEME_MODES, next, setMeters, setTheme, useLook } from "../../lib/prefs";
import { IconButton } from "../../ui/Button";

const THEME_ICON = { system: Monitor, light: Sun, dark: Moon };
const METER_ICON = { auto: Contrast, gauge: Gauge, rainbow: Rainbow };
const METER_SAYS = {
  auto: "auto (Rainbow in light, Gauge in dark)", gauge: "Gauge, one solid fill",
  rainbow: "Rainbow, coloured by load",
};

export function ThemeSwitch() {
  const { mode } = useLook();
  const Icon = THEME_ICON[mode], to = next(THEME_MODES, mode);
  return (
    <IconButton label={`Theme: ${mode}. Switch to ${to}`} onClick={() => setTheme(to)}>
      <Icon aria-hidden className="size-icon" />
    </IconButton>
  );
}

export function MeterSwitch() {
  const { meters } = useLook();
  const Icon = METER_ICON[meters], to = next(METER_MODES, meters);
  return (
    <IconButton label={`Meters: ${METER_SAYS[meters]}. Switch to ${to}`} onClick={() => setMeters(to)}>
      <Icon aria-hidden className="size-icon" />
    </IconButton>
  );
}
