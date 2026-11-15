// The approval mockups of 2026-11-15. Loaded before ../storage/storage.js and
// ../mockups-2026-11-13.js, which draw the other icons and switch the theme. This file draws
// the space bar of each request, lets its value be changed, and answers Approve and Decline so
// an option can be tried. Nothing is saved or sent anywhere. Icons: Lucide (ISC), outline.
(function () {
  "use strict";
  var ICONS = {
    "bot": "<path d=\"M12 8V4H8\"/><rect width=\"16\" height=\"12\" x=\"4\" y=\"8\" rx=\"2\"/><path d=\"M2 14h2\"/><path d=\"M20 14h2\"/><path d=\"M15 13v2\"/><path d=\"M9 13v2\"/>",
    "history": "<path d=\"M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8\"/><path d=\"M3 3v5h5\"/><path d=\"M12 7v5l4 2\"/>",
    "pencil": "<path d=\"M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z\"/><path d=\"m15 5 4 4\"/>"
  };
  var WARN = 0.8;
  function gb(n) { return n.toFixed(1) + " GB"; }
  function pct(part, whole) { return Math.round(part / whole * 100); }

  document.querySelectorAll("[data-req]").forEach(function (req) {
    var d = req.dataset, held = +d.held, limit = +d.limit, ask = +d.ask, free = +d.free, floor = +d.floor, clean = +d.clean;
    var node = d.node, value = +(d.value || ask), scale = Math.max(ask, limit) + 10, most = Math.floor(held + free - floor);
    var box = req.querySelector("[data-space]");
    if (box) {
      box.classList.add("space");
      box.innerHTML =
        '<div class="space-top"><span><span class="big num">' + gb(held) + '</span> held by mulebox on ' + node + ', of <b class="num">' + gb(limit) + '</b></span>' +
        '<span class="lvl"><i data-i="triangle-alert" class="s"></i><span class="num">' + pct(held, limit) + '%</span> of its limit</span></div>' +
        '<div class="space-bar" role="img" data-bar><i class="room"></i><i class="more"></i><i class="held"></i><i class="now"></i><i class="tell"></i></div>' +
        '<ul class="space-key"><li><span class="sw held"></span>held now</li><li><span class="sw line"></span>limit now, <b class="num">' + gb(limit) + '</b></li>' +
        '<li><span class="sw more"></span>added, to <b class="num" data-v></b></li><li><span class="sw dots"></span>agents told from <b class="num" data-tell></b></li></ul>' +
        '<p class="would" data-would><i data-i="info" class="s"></i><span></span></p>' +
        '<dl class="space-facts"><div><dt>The cleanup can still free</dt><dd class="num">' + gb(clean) + '</dd></div>' +
        '<div><dt>Disk free</dt><dd class="num">' + gb(free) + ' <span>of ' + d.disk + ' GB</span></dd></div>' +
        '<div><dt>Disk floor</dt><dd class="num">' + gb(floor) + ' <span>10% kept free</span></dd></div></dl>';
    }
    function paint() {
      var worst = free - (value - held), after = pct(held, value), text;
      req.querySelectorAll("[data-v]").forEach(function (el) { el.textContent = gb(value); });
      req.querySelectorAll("[data-v-num]").forEach(function (el) { el.textContent = value + " GB"; });
      req.querySelectorAll("[data-tell]").forEach(function (el) { el.textContent = gb(value * WARN); });
      req.querySelectorAll("[data-differs]").forEach(function (el) { el.hidden = value === ask; });
      if (!box) return;
      var bar = box.querySelector("[data-bar]");
      bar.style.setProperty("--p-held", held / scale * 100 + "%");
      bar.style.setProperty("--p-limit", limit / scale * 100 + "%");
      bar.style.setProperty("--p-to", value / scale * 100 + "%");
      bar.style.setProperty("--p-tell", value * WARN / scale * 100 + "%");
      bar.setAttribute("aria-label", "mulebox holds " + gb(held) + " of a limit of " + gb(limit) + "; the limit would be " + gb(value));
      text = "At " + gb(value) + " mulebox is at " + after + "% of its limit" +
        (after >= WARN * 100 ? ", so agents are still told to ask." : ", and agents are told again from " + gb(value * WARN) + ".");
      text += worst < floor
        ? " Filled to the limit, the disk is left with " + gb(worst) + " free, " + gb(floor - worst) + " under its floor: the floor's cleanup would then step in first. " +
          most + " GB is the most that stays clear of it."
        : " Even filled to the limit, the disk keeps " + gb(worst) + " free, above its floor of " + gb(floor) + ".";
      var would = box.querySelector("[data-would]");
      would.setAttribute("data-level", worst < floor ? "warn" : "ok");
      would.querySelector("span").textContent = text;
    }
    req.addEventListener("click", function (event) {
      var step = event.target.closest("[data-gb-step]"), act = event.target.closest("[data-do]");
      if (step) { value = Math.min(scale, Math.max(limit + 1, value + Number(step.getAttribute("data-gb-step")))); paint(); }
      if (!act) return;
      var what = act.getAttribute("data-do"), said = req.querySelector("[data-said]");
      if (what === "other") { req.setAttribute("data-edit", ""); return; }
      if (what === "undo") { req.removeAttribute("data-state"); return; }
      req.setAttribute("data-state", what === "approve" ? "approved" : "declined");
      if (!said) return;
      var both = d.asks ? " One answer for all " + d.asks + " requests." : "";
      said.innerHTML = what === "approve"
        ? "<b>Approved" + (value === ask ? ": " + gb(value) : " at " + gb(value) + ", not the " + gb(ask) + " asked") + ".</b> <span>" + node +
          " takes it with its next check-in; the agent reads the answer in its next command." + both + "</span>"
        : "<b>Declined: the limit stays " + gb(limit) + ".</b> <span>The agent reads the answer in its next command, and is not told to ask again for 7 days." + both + "</span>";
    });
    paint();
  });

  document.querySelectorAll("i[data-i]").forEach(function (el) {
    var paths = ICONS[el.getAttribute("data-i")];
    if (!paths) return;
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", ("i " + el.className).trim());
    svg.innerHTML = paths;
    el.replaceWith(svg);
  });
})();
