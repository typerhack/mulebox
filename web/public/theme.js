// Applies the chosen theme and meter style before the first paint. A classic script on
// purpose: a module would run after the page is shown and the theme would flash, and the
// page's security policy allows no inline script. `data-mode` is the theme choice (system,
// light or dark), `data-theme` what that gives now, `data-paint` the meter style it gives
// (auto is Rainbow in light and Gauge in dark). src/lib/prefs.ts holds the switches.
(function () {
  var mode = null, meters = null;
  try {
    mode = localStorage.getItem("mulebox-theme");
    meters = localStorage.getItem("mulebox-meters");
  } catch (error) { mode = null; }
  if (mode !== "light" && mode !== "dark") mode = "system";
  var light = mode === "light" ||
    (mode === "system" && window.matchMedia("(prefers-color-scheme: light)").matches);
  var root = document.documentElement;
  root.dataset.mode = mode;
  root.dataset.theme = light ? "light" : "dark";
  root.dataset.paint = meters === "gauge" || meters === "rainbow" ? meters : light ? "rainbow" : "gauge";
})();
