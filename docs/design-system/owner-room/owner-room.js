// The "room for the owner" mockups of 2026-11-25. Loaded before ../mockups-2026-11-13.js, which
// draws the shared icons and switches the theme. This file holds the example node once and
// writes each option's window and parts from it, in each state, so the same markup is shown
// wide, in the states beside it and in the 390 px frames. Nothing is saved or sent anywhere.
// Icons: Lucide (ISC), outline.
(function () {
  "use strict";
  var ICONS = {
    "monitor": "<rect width=\"20\" height=\"14\" x=\"2\" y=\"3\" rx=\"2\"/><line x1=\"8\" x2=\"16\" y1=\"21\" y2=\"21\"/><line x1=\"12\" x2=\"12\" y1=\"17\" y2=\"21\"/>",
    "square-stack": "<path d=\"M4 10c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h4c1.1 0 2 .9 2 2\"/><path d=\"M10 16c-1.1 0-2-.9-2-2v-4c0-1.1.9-2 2-2h4c1.1 0 2 .9 2 2\"/><rect width=\"8\" height=\"8\" x=\"14\" y=\"14\" rx=\"2\"/>",
    "cpu": "<path d=\"M12 20v2\"/><path d=\"M12 2v2\"/><path d=\"M17 20v2\"/><path d=\"M17 2v2\"/><path d=\"M2 12h2\"/><path d=\"M2 17h2\"/><path d=\"M2 7h2\"/><path d=\"M20 12h2\"/><path d=\"M20 17h2\"/><path d=\"M20 7h2\"/><path d=\"M7 20v2\"/><path d=\"M7 2v2\"/><rect x=\"4\" y=\"4\" width=\"16\" height=\"16\" rx=\"2\"/><rect x=\"8\" y=\"8\" width=\"8\" height=\"8\" rx=\"1\"/>",
    "memory-stick": "<path d=\"M12 12v-2\"/><path d=\"M12 18v-2\"/><path d=\"M16 12v-2\"/><path d=\"M16 18v-2\"/><path d=\"M2 11h1.5\"/><path d=\"M20 18v-2\"/><path d=\"M20.5 11H22\"/><path d=\"M4 18v-2\"/><path d=\"M8 12v-2\"/><path d=\"M8 18v-2\"/><rect x=\"2\" y=\"6\" width=\"20\" height=\"10\" rx=\"2\"/>",
    "pen-line": "<path d=\"M12 20h9\"/><path d=\"M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.854z\"/>"
  };
  var root = document.documentElement;
  var asked = /[?&]theme=(light|dark)/.exec(location.search);
  if (asked) root.setAttribute("data-theme", asked[1]);

  // The example node, and the three states every option is shown in.
  var NODE = { name: "build-1", cores: 8, gb: 16.6, slots: 2 };
  var KEEP = { cores: 2, gb: 4 };
  var STATES = {
    none: { now: [0, 0], yours: [0, 0] },                     // the default: nothing kept
    kept: { now: [2, 4], yours: [2, 4] },                     // 2 cores and 4 GB kept, applied
    pending: { now: [0, 0], yours: [2, 4], mark: "pending" }, // saved, the node has yet to take it
    open: { now: [0, 0], yours: [2, 4], mark: "unsaved" }     // option C, while it is being changed
  };
  var cores = function (n) { return n + (n === 1 ? " core" : " cores"); };
  var gb = function (n) { return (Math.round(n * 10) / 10) + " GB"; };
  var left = function (keep) { return [NODE.cores - keep[0], Math.round((NODE.gb - keep[1]) * 10) / 10]; };

  function stepper(value, one, unit) {
    return '<span class="row tight"><span class="stepper"><button type="button" aria-label="One ' + one + ' fewer"><i data-i="minus"></i></button>' +
      '<output>' + value + '</output><button type="button" aria-label="One ' + one + ' more"><i data-i="plus"></i></button></span>' +
      (unit ? '<span class="unit">' + unit + '</span>' : "") + '</span>';
  }
  var DROP = '<button type="button" class="link-btn">Drop it</button>';
  function mark(text, kind) {
    return '<span class="wait-mark num"><i data-i="' + (kind === "unsaved" ? "pen-line" : "clock") + '" class="s"></i>' + text + " " + kind + '</span>';
  }
  // The window's own "Runs with" row: what the node has now, then a change on its way.
  function runsWith(now, yours, state, same) {
    var note = state.mark === "unsaved" ? "sent to the node when you save"
      : state.mark === "pending" ? "the node takes it on its next check-in" : same ? "as suggested" : "";
    return '<div class="set-row"><span>Runs with</span><span class="row tight"><b class="num">' + now + ' now</b>' +
      (state.mark ? mark(yours, state.mark) + (state.mark === "pending" ? DROP : "") : "") + '</span>' +
      (note ? '<small>' + note + '</small>' : "") + '</div>';
  }

  // The Slots panel as it is today; option B adds its rows through `more`.
  function slotsPanel(more) {
    return '<section class="panel" aria-label="Slots"><header class="panel-head"><h3><i data-i="square-stack"></i>Slots</h3></header>' +
      '<div class="panel-body set-rows"><p class="set-mean">Jobs at once, 1 to 16</p>' +
      '<div class="set-row"><span>Suggested</span><b class="num">2</b><small>from 8 cores and 16.6 GB</small></div>' +
      '<div class="set-row"><span>Yours</span>' + stepper(NODE.slots, "slot") + '</div>' +
      '<div class="set-row"><span>Runs with</span><b class="num">2 now</b><small>as suggested</small></div>' +
      (more || "") + '</div></section>';
  }
  var today = function (what, tall) { return '<p class="as-today' + (tall ? " tall" : "") + '">' + what + ', as today</p>'; };

  // Option A: one panel, two parts, each in the window's three rows (as "Space for mulebox").
  function partA(key) {
    var s = STATES[key], rest = left(s.yours);
    function part(title, mean, zero, value, control, share, now, yours) {
      return '<section class="part" aria-label="' + title + '"><h4>' + title + '</h4><div class="set-rows">' +
        '<p class="set-mean">' + mean + '</p>' +
        '<div class="set-row"><span>Suggested</span><b class="num">' + zero + '</b><small>the default for every node: nothing kept</small></div>' +
        '<div class="set-row"><span>Yours</span>' + control + '<small>' + share + '</small></div>' +
        runsWith(now, yours, s, value === 0) + '</div></section>';
    }
    return '<section class="panel full" aria-label="Room for you"><header class="panel-head"><h3><i data-i="monitor"></i>Room for you</h3></header>' +
      '<div class="panel-body"><p class="lead-line">For a node that is also your PC. Jobs that say their size share what is left; a job with no size takes one slot, as today. It decides how many jobs start, it does not hold back a job that is running.</p>' +
      '<div class="parts">' +
      part("Cores kept", "Whole cores, 0 to " + NODE.cores, cores(0), s.now[0], stepper(s.yours[0], "core"),
        s.yours[0] ? "Jobs with a size share " + rest[0] + " of " + cores(NODE.cores) : "Jobs with a size share all " + cores(NODE.cores),
        cores(s.now[0]), cores(s.yours[0])) +
      part("Memory kept", "Whole GB, 0 to 16", gb(0), s.now[1], stepper(s.yours[1], "GB", "GB"),
        s.yours[1] ? "Jobs with a size share " + rest[1] + " of " + gb(NODE.gb) : "Jobs with a size share all " + gb(NODE.gb),
        gb(s.now[1]), gb(s.yours[1])) +
      '</div></div></section>';
  }

  // Option B: two more rows in the Slots panel, under its own three.
  function partB(key) {
    var s = STATES[key], rest = left(s.yours);
    var says = s.yours[0] || s.yours[1] ? "Jobs with a size share " + cores(rest[0]) + " and " + gb(rest[1])
                                        : "Nothing kept: jobs with a size share all " + cores(NODE.cores) + " and " + gb(NODE.gb);
    return slotsPanel(
      '<p class="kept-h"><b>Kept for you</b><small>' + says + '</small></p>' +
      '<div class="set-row kept-row"><span>Cores</span>' + stepper(s.yours[0], "core") + '</div>' +
      '<div class="set-row kept-row"><span>Memory</span>' + stepper(s.yours[1], "GB", "GB") + '</div>' +
      (s.mark ? '<p class="kept-wait"><span>' + cores(s.now[0]) + " and " + gb(s.now[1]) + ' now</span>' +
        mark(cores(s.yours[0]) + " and " + gb(s.yours[1]), s.mark) + DROP + '</p>' : ""));
  }

  // Option C: what jobs get, drawn, with one sentence and a button that opens the two values.
  function partC(key) {
    var s = STATES[key], rest = left(s.yours), nowRest = left(s.now), soon = Boolean(s.mark);
    var boxes = "";
    for (var n = 0; n < NODE.cores; n++) boxes += '<i' + (n >= rest[0] ? ' class="' + (soon ? "soon" : "kept") + '"' : "") + '></i>';
    var mem = '<i style="--gb: ' + rest[1] + '"></i>' + (s.yours[1] ? '<i class="' + (soon ? "soon" : "kept") + '" style="--gb: ' + s.yours[1] + '"></i>' : "");
    var kept = cores(s.yours[0]) + " and " + gb(s.yours[1]);
    var say = key === "none" ? '<p><b>Nothing is kept for you.</b><small>Jobs that say their size share the whole node. On a node that is also your PC, keep some.</small></p>' +
        '<button type="button" class="btn">Keep some for you</button>'
      : key === "kept" ? '<p><b>' + kept + ' are kept for you.</b><small>Jobs that say their size share the rest. A job with no size takes one slot, as today.</small></p>' +
        '<button type="button" class="btn">Change</button>'
      : key === "pending" ? '<p><b>' + kept + ' will be kept for you.</b><small>Nothing is kept now: ' + NODE.name + ' takes the change on its next check-in.</small></p>' +
        '<span class="row tight">' + mark(kept, "pending") + DROP + '</span>'
      : '<p class="share-edit"><label>Cores kept ' + stepper(s.yours[0], "core") + '</label><label>Memory kept ' + stepper(s.yours[1], "GB", "GB") + '</label></p>' +
        '<span class="row tight">' + mark(kept, "unsaved") + '</span>';
    return '<section class="panel full" aria-label="What jobs get"><header class="panel-head"><h3><i data-i="monitor"></i>What jobs get</h3>' +
      '<span class="panel-note num">' + NODE.name + ": " + cores(NODE.cores) + ", " + gb(NODE.gb) + '</span></header>' +
      '<div class="panel-body"><div class="share">' +
      '<div class="share-row"><span><i data-i="cpu" class="s"></i>Cores</span><span class="cores" role="img" aria-label="' + rest[0] + " of " + NODE.cores + ' cores for jobs">' + boxes + '</span>' +
      '<b class="num">' + (soon ? nowRest[0] + " now, " + rest[0] + " next" : rest[0] + " of " + NODE.cores) + '</b></div>' +
      '<div class="share-row"><span><i data-i="memory-stick" class="s"></i>Memory</span><span class="mem" role="img" aria-label="' + rest[1] + " of " + NODE.gb + ' GB for jobs">' + mem + '</span>' +
      '<b class="num">' + (soon ? gb(nowRest[1]) + " now, " + gb(rest[1]) + " next" : rest[1] + " of " + gb(NODE.gb)) + '</b></div></div>' +
      '<p class="share-key"><span><i></i>for jobs</span>' + (key === "none" ? "" : soon ? '<span><i class="soon"></i>kept for you once the change is taken</span>' : '<span><i class="kept"></i>kept for you</span>') + '</p>' +
      '<div class="share-say">' + say + '</div></div></section>';
  }

  var PARTS = { a: partA, b: partB, c: partC };
  // The Jobs tab around each option's part, with the panels that do not change drawn as boxes.
  function jobsTab(option, key) {
    var part = PARTS[option](key);
    if (option === "b") return part + today("Priority", true) + today("Dev mode") + today("Reported by the node");
    return slotsPanel() + today("Priority", true) + part + today("Dev mode") + today("Reported by the node");
  }
  function windowOf(option, key) {
    var dirty = STATES[key].mark === "unsaved";
    return '<section class="float win" aria-label="Settings of ' + NODE.name + '">' +
      '<header class="float-head"><div><h3><i data-i="server"></i>' + NODE.name + '</h3><p class="sm t2">Node settings, dashboard host</p></div>' +
      '<button class="icon-btn bare" type="button" aria-label="Close" title="Close"><i data-i="x"></i></button></header>' +
      '<div class="float-body ground gap"><div class="tabs" role="tablist"><button type="button" role="tab" aria-selected="true">Jobs</button><button type="button" role="tab" aria-selected="false">Storage</button></div>' +
      '<div class="jobs">' + jobsTab(option, key) + '</div></div>' +
      '<footer class="float-foot"><p>Applies to the next job; running jobs keep their slot. A suggestion you take is saved as a fixed value of yours.</p>' +
      '<button class="btn ghost" type="button"><i data-i="rotate-ccw" class="s"></i>All as suggested</button><button class="btn ghost" type="button">' + (dirty ? "Cancel" : "Close") + '</button>' +
      '<button class="btn primary" type="button"' + (dirty ? "" : " disabled") + '>Save changes</button></footer></section>';
  }

  // ?only=a&state=pending: that option's window alone, for the 390 px frames. It tells the page
  // around it how tall it is.
  var only = /[?&]only=([abc])/.exec(location.search), state = /[?&]state=([a-z]+)/.exec(location.search);
  if (only) {
    document.body.className = "frame";
    document.body.innerHTML = windowOf(only[1], state ? state[1] : "pending");
    var tell = function () { parent.postMessage({ ownerRoom: location.search, height: Math.ceil(document.body.getBoundingClientRect().height) }, "*"); };
    window.addEventListener("load", tell);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(tell);
    setTimeout(tell, 1200);
  } else {
    document.querySelectorAll("[data-window]").forEach(function (el) { var at = el.getAttribute("data-window").split(":"); el.innerHTML = windowOf(at[0], at[1]); });
    document.querySelectorAll("[data-part]").forEach(function (el) { var at = el.getAttribute("data-part").split(":"); el.innerHTML = PARTS[at[0]](at[1]); });
    window.addEventListener("message", function (event) {
      if (!event.data || !event.data.ownerRoom) return;
      document.querySelectorAll("iframe").forEach(function (frame) {
        if (frame.contentWindow === event.source) frame.style.height = event.data.height + "px";
      });
    });
  }

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
