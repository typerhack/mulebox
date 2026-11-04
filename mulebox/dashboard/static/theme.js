// Applies the chosen theme before the first paint. A classic script on purpose: a module
// would run after the page is shown and the theme would flash. The choice is kept in
// localStorage; without one, the system setting decides (app.js follows later changes).
(function () {
  var theme = null;
  try { theme = localStorage.getItem("mulebox-theme"); } catch (error) { theme = null; }
  if (theme !== "light" && theme !== "dark") {
    theme = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  document.documentElement.dataset.theme = theme;
})();
