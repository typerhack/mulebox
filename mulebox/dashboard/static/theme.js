// Applies the chosen theme before the first paint. A classic script on purpose: a module
// would run after the page is shown and the theme would flash. `data-mode` is the choice
// (system, light or dark, kept in localStorage); `data-theme` is what that gives now, and
// is the one the stylesheet colours by. app.js holds the switch and follows the system.
(function () {
  var mode = null;
  try { mode = localStorage.getItem("mulebox-theme"); } catch (error) { mode = null; }
  if (mode !== "light" && mode !== "dark") mode = "system";
  var light = mode === "light" ||
    (mode === "system" && window.matchMedia("(prefers-color-scheme: light)").matches);
  document.documentElement.dataset.mode = mode;
  document.documentElement.dataset.theme = light ? "light" : "dark";
})();
