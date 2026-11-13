// Shared by the mockups of 2026-11-13: draws the icons, switches the theme, and makes the few
// controls answer a click so an option can be tried. Nothing is saved or sent anywhere.
// Icons: Lucide (ISC), outline, the paths of the lucide-react version the dashboard uses.
(function () {
  "use strict";
  var ICONS = {
    "loader-circle": "<path d=\"M21 12a9 9 0 1 1-6.219-8.56\"/>",
    "clock": "<circle cx=\"12\" cy=\"12\" r=\"10\"/><path d=\"M12 6v6l4 2\"/>",
    "circle-check": "<circle cx=\"12\" cy=\"12\" r=\"10\"/><path d=\"m16 9-5.5 5.5L8 12\"/>",
    "circle-x": "<circle cx=\"12\" cy=\"12\" r=\"10\"/><path d=\"m15 9-6 6\"/><path d=\"m9 9 6 6\"/>",
    "ban": "<circle cx=\"12\" cy=\"12\" r=\"10\"/><path d=\"M4.929 4.929 19.07 19.071\"/>",
    "snowflake": "<path d=\"m10 20-1.25-2.5L6 18\"/><path d=\"M10 4 8.75 6.5 6 6\"/><path d=\"m14 20 1.25-2.5L18 18\"/><path d=\"m14 4 1.25 2.5L18 6\"/><path d=\"m17 21-3-6h-4\"/><path d=\"m17 3-3 6 1.5 3\"/><path d=\"M2 12h6.5L10 9\"/><path d=\"m20 10-1.5 2 1.5 2\"/><path d=\"M22 12h-6.5L14 15\"/><path d=\"m4 10 1.5 2L4 14\"/><path d=\"m7 21 3-6-1.5-3\"/><path d=\"m7 3 3 6h4\"/>",
    "pause": "<rect x=\"14\" y=\"3\" width=\"5\" height=\"18\" rx=\"1\"/><rect x=\"5\" y=\"3\" width=\"5\" height=\"18\" rx=\"1\"/>",
    "play": "<path d=\"M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z\"/>",
    "zap": "<path d=\"M15.914 4a1.5 1.5 0 00-2.474-1.561l-9 9A1.5 1.5 0 005.5 14h4.002a.5.5 0 01.471.666L8.086 20a1.5 1.5 0 002.475 1.56l9-9A1.5 1.5 0 0018.5 10h-3.997a.5.5 0 01-.472-.667z\"/>",
    "ellipsis": "<circle cx=\"12\" cy=\"12\" r=\"1\"/><circle cx=\"19\" cy=\"12\" r=\"1\"/><circle cx=\"5\" cy=\"12\" r=\"1\"/>",
    "chevrons-up": "<path d=\"m17 11-5-5-5 5\"/><path d=\"m17 18-5-5-5 5\"/>",
    "chevron-up": "<path d=\"m18 15-6-6-6 6\"/>",
    "chevron-down": "<path d=\"m6 9 6 6 6-6\"/>",
    "chevrons-down": "<path d=\"m7 6 5 5 5-5\"/><path d=\"m7 13 5 5 5-5\"/>",
    "copy": "<rect width=\"14\" height=\"14\" x=\"8\" y=\"8\" rx=\"2\" ry=\"2\"/><path d=\"M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2\"/>",
    "check": "<path d=\"M20 6 9 17l-5-5\"/>",
    "git-branch": "<path d=\"M15 6a9 9 0 0 0-9 9V3\"/><circle cx=\"18\" cy=\"6\" r=\"3\"/><circle cx=\"6\" cy=\"18\" r=\"3\"/>",
    "laptop": "<path d=\"M18 5a2 2 0 0 1 2 2v8.526a2 2 0 0 0 .212.897l1.068 2.127a1 1 0 0 1-.9 1.45H3.62a1 1 0 0 1-.9-1.45l1.068-2.127A2 2 0 0 0 4 15.526V7a2 2 0 0 1 2-2z\"/><path d=\"M20.054 15.987H3.946\"/>",
    "workflow": "<rect width=\"8\" height=\"8\" x=\"3\" y=\"3\" rx=\"2\"/><path d=\"M7 11v4a2 2 0 0 0 2 2h4\"/><rect width=\"8\" height=\"8\" x=\"13\" y=\"13\" rx=\"2\"/>",
    "download": "<path d=\"M12 15V3\"/><path d=\"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4\"/><path d=\"m7 10 5 5 5-5\"/>",
    "server": "<rect width=\"20\" height=\"8\" x=\"2\" y=\"2\" rx=\"2\" ry=\"2\"/><rect width=\"20\" height=\"8\" x=\"2\" y=\"14\" rx=\"2\" ry=\"2\"/><line x1=\"6\" x2=\"6.01\" y1=\"6\" y2=\"6\"/><line x1=\"6\" x2=\"6.01\" y1=\"18\" y2=\"18\"/>",
    "house": "<path d=\"M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8\"/><path d=\"M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z\"/>",
    "settings-2": "<path d=\"M14 17H5\"/><path d=\"M19 7h-9\"/><circle cx=\"17\" cy=\"17\" r=\"3\"/><circle cx=\"7\" cy=\"7\" r=\"3\"/>",
    "sliders-horizontal": "<path d=\"M10 5H3\"/><path d=\"M12 19H3\"/><path d=\"M14 3v4\"/><path d=\"M16 17v4\"/><path d=\"M21 12h-9\"/><path d=\"M21 19h-5\"/><path d=\"M21 5h-7\"/><path d=\"M8 10v4\"/><path d=\"M8 12H3\"/>",
    "x": "<path d=\"M18 6 6 18\"/><path d=\"m6 6 12 12\"/>",
    "minus": "<path d=\"M5 12h14\"/>",
    "plus": "<path d=\"M5 12h14\"/><path d=\"M12 5v14\"/>",
    "star": "<path d=\"M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z\"/>",
    "life-buoy": "<circle cx=\"12\" cy=\"12\" r=\"10\"/><path d=\"m4.93 4.93 4.24 4.24\"/><path d=\"m14.83 9.17 4.24-4.24\"/><path d=\"m14.83 14.83 4.24 4.24\"/><path d=\"m9.17 14.83-4.24 4.24\"/><circle cx=\"12\" cy=\"12\" r=\"4\"/>",
    "equal": "<line x1=\"5\" x2=\"19\" y1=\"9\" y2=\"9\"/><line x1=\"5\" x2=\"19\" y1=\"15\" y2=\"15\"/>",
    "arrow-down": "<path d=\"M12 5v14\"/><path d=\"m19 12-7 7-7-7\"/>",
    "arrow-up": "<path d=\"m5 12 7-7 7 7\"/><path d=\"M12 19V5\"/>",
    "timer": "<line x1=\"10\" x2=\"14\" y1=\"2\" y2=\"2\"/><line x1=\"12\" x2=\"15\" y1=\"14\" y2=\"11\"/><circle cx=\"12\" cy=\"14\" r=\"8\"/>",
    "repeat": "<path d=\"m17 2 4 4-4 4\"/><path d=\"M3 11v-1a4 4 0 0 1 4-4h14\"/><path d=\"m7 22-4-4 4-4\"/><path d=\"M21 13v1a4 4 0 0 1-4 4H3\"/>",
    "hourglass": "<path d=\"M5 22h14\"/><path d=\"M5 2h14\"/><path d=\"M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22\"/><path d=\"M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2\"/>",
    "flag": "<path d=\"M4 22V4a1 1 0 0 1 .4-.8A6 6 0 0 1 8 2c3 0 5 2 7.333 2q2 0 3.067-.8A1 1 0 0 1 20 4v10a1 1 0 0 1-.4.8A6 6 0 0 1 16 16c-3 0-5-2-8-2a6 6 0 0 0-4 1.528\"/>",
    "hand": "<path d=\"M18 11V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2\"/><path d=\"M14 10V4a2 2 0 0 0-2-2a2 2 0 0 0-2 2v2\"/><path d=\"M10 10.5V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2v8\"/><path d=\"M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15\"/>",
    "sun": "<circle cx=\"12\" cy=\"12\" r=\"4\"/><path d=\"M12 2v2\"/><path d=\"M12 20v2\"/><path d=\"m4.93 4.93 1.41 1.41\"/><path d=\"m17.66 17.66 1.41 1.41\"/><path d=\"M2 12h2\"/><path d=\"M20 12h2\"/><path d=\"m6.34 17.66-1.41 1.41\"/><path d=\"m19.07 4.93-1.41 1.41\"/>",
    "moon": "<path d=\"M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401\"/>",
    "info": "<circle cx=\"12\" cy=\"12\" r=\"10\"/><path d=\"M12 16v-4\"/><path d=\"M12 8h.01\"/>",
    "rotate-ccw": "<path d=\"M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8\"/><path d=\"M3 3v5h5\"/>",
    "chevron-right": "<path d=\"m9 18 6-6-6-6\"/>",
    "lock": "<rect width=\"18\" height=\"11\" x=\"3\" y=\"11\" rx=\"2\" ry=\"2\"/><path d=\"M7 11V7a5 5 0 0 1 10 0v4\"/>",
    "undo-2": "<path d=\"M9 14 4 9l5-5\"/><path d=\"M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11\"/>",
    "arrow-left": "<path d=\"m12 19-7-7 7-7\"/><path d=\"M19 12H5\"/>",
    "list-ordered": "<path d=\"M11 5h10\"/><path d=\"M11 12h10\"/><path d=\"M11 19h10\"/><path d=\"M4 4h1v5\"/><path d=\"M4 9h2\"/><path d=\"M6.5 20H3.4c0-1 2.6-1.925 2.6-3.5a1.5 1.5 0 0 0-2.6-1.02\"/>",
    "grip-vertical": "<circle cx=\"9\" cy=\"12\" r=\"1\"/><circle cx=\"9\" cy=\"5\" r=\"1\"/><circle cx=\"9\" cy=\"19\" r=\"1\"/><circle cx=\"15\" cy=\"12\" r=\"1\"/><circle cx=\"15\" cy=\"5\" r=\"1\"/><circle cx=\"15\" cy=\"19\" r=\"1\"/>",
    "circle-question-mark": "<circle cx=\"12\" cy=\"12\" r=\"10\"/><path d=\"M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3\"/><path d=\"M12 17h.01\"/>",
    "triangle-alert": "<path d=\"m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3\"/><path d=\"M12 9v4\"/><path d=\"M12 17h.01\"/>"
  };
  var root = document.documentElement;

  function draw(scope) {
    scope.querySelectorAll("i[data-i]").forEach(function (el) {
      var paths = ICONS[el.getAttribute("data-i")];
      if (!paths) return;
      var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 24 24");
      svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("class", ("i " + el.className).trim());
      svg.innerHTML = paths;
      el.replaceWith(svg);
    });
  }

  function theme() {
    var button = document.querySelector("[data-theme-switch]");
    if (!button) return;
    function paint() {
      var dark = root.getAttribute("data-theme") === "dark";
      button.innerHTML = '<i data-i="' + (dark ? "sun" : "moon") + '" class="s"></i>' + (dark ? "Light theme" : "Dark theme");
      draw(button);
    }
    button.addEventListener("click", function () {
      root.setAttribute("data-theme", root.getAttribute("data-theme") === "dark" ? "light" : "dark");
      paint();
    });
    paint();
  }

  // One of a group: the pressed one is checked, and a note beside the group says what it means.
  function segments() {
    document.querySelectorAll("[role=radiogroup]").forEach(function (group) {
      group.addEventListener("click", function (event) {
        var hit = event.target.closest("[role=radio]");
        if (!hit) return;
        group.querySelectorAll("[role=radio]").forEach(function (b) { b.setAttribute("aria-checked", String(b === hit)); });
        var note = group.getAttribute("data-note") && document.getElementById(group.getAttribute("data-note"));
        if (note && hit.getAttribute("data-says")) note.textContent = hit.getAttribute("data-says");
      });
    });
  }

  function toggles() {
    document.addEventListener("click", function (event) {
      var sw = event.target.closest("[role=switch]");
      if (sw) sw.setAttribute("aria-checked", String(sw.getAttribute("aria-checked") !== "true"));
      var press = event.target.closest("[data-toggle]");
      if (press) press.setAttribute("aria-pressed", String(press.getAttribute("aria-pressed") !== "true"));
    });
  }

  // Slots of a node: a number from 1 to 16, drawn as boxes (the busy ones filled, the ones a
  // change adds dashed), with what each job gets when all are busy.
  function slots() {
    document.querySelectorAll("[data-slots]").forEach(function (box) {
      var value = Number(box.getAttribute("data-slots"));
      var now = Number(box.getAttribute("data-now")), busy = Number(box.getAttribute("data-busy"));
      var cores = Number(box.getAttribute("data-cores")), gb = Number(box.getAttribute("data-gb"));
      var pick = box.hasAttribute("data-pick");
      function paint() {
        box.querySelectorAll("[data-n]").forEach(function (el) { el.textContent = String(value); });
        box.querySelectorAll("[data-each]").forEach(function (el) {
          el.textContent = "about " + (cores / value).toFixed(1) + " cores and " + (gb / value).toFixed(1) + " GB each when all are busy";
        });
        box.querySelectorAll("[data-changed]").forEach(function (el) { el.hidden = value === now; });
        box.querySelectorAll("[data-boxes]").forEach(function (el) {
          var count = pick ? 16 : Math.max(value, now), html = "";
          for (var n = 1; n <= count; n++) {
            var cls = n <= busy ? "busy" : n > now && n <= value ? "soon" : n > value ? "off" : "";
            html += pick
              ? '<button type="button" class="' + cls + '" data-set="' + n + '" aria-label="' + n + (n === 1 ? " slot" : " slots") + '"></button>'
              : '<i class="' + cls + '"></i>';
          }
          el.innerHTML = html;
        });
      }
      box.addEventListener("click", function (event) {
        var step = event.target.closest("[data-step]"), set = event.target.closest("[data-set]");
        if (step) value = Math.min(16, Math.max(1, value + Number(step.getAttribute("data-step"))));
        if (set) value = Number(set.getAttribute("data-set"));
        if (step || set) paint();
      });
      paint();
    });
  }

  // A popover hangs below its button; the stage grows so nothing of it is cut off.
  function room() {
    document.querySelectorAll(".stage").forEach(function (stage) {
      stage.style.paddingBottom = "";
      var bottom = stage.getBoundingClientRect().bottom, need = 0;
      stage.querySelectorAll(".pop").forEach(function (pop) {
        need = Math.max(need, pop.getBoundingClientRect().bottom - bottom);
      });
      if (need > -12) stage.style.paddingBottom = (parseFloat(getComputedStyle(stage).paddingBottom) + need + 12) + "px";
    });
  }

  // The page under a sheet or a dialog: a copy of a part drawn elsewhere on this page.
  document.querySelectorAll("[data-clone]").forEach(function (el) {
    var copy = document.querySelector(el.getAttribute("data-clone")).cloneNode(true);
    copy.querySelectorAll(".pop").forEach(function (pop) { pop.remove(); });
    copy.querySelectorAll("[id]").forEach(function (node) { node.removeAttribute("id"); });
    copy.querySelectorAll("[aria-expanded]").forEach(function (node) { node.removeAttribute("aria-expanded"); });
    copy.removeAttribute("id");
    el.setAttribute("aria-hidden", "true");
    el.inert = true;
    el.append(copy);
  });

  draw(document);
  theme();
  segments();
  toggles();
  slots();
  room();
  window.addEventListener("resize", room);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(room);
})();
