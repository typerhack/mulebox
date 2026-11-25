// The "job usage" mockups of 2026-11-25 (M23.8). Loaded before ../storage/storage.js and
// ../mockups-2026-11-13.js, which draw the other icons and switch the theme. This file holds the
// example nodes, jobs and runs once, draws each option's summary and job page from them, and
// answers the few clicks. Nothing is saved or sent anywhere.
// Icons: Lucide (ISC), outline, the paths of the lucide-react version the dashboard uses.
(function () {
  "use strict";
  var ICONS = {
    "cpu": "<path d=\"M12 20v2\"/><path d=\"M12 2v2\"/><path d=\"M17 20v2\"/><path d=\"M17 2v2\"/><path d=\"M2 12h2\"/><path d=\"M2 17h2\"/><path d=\"M2 7h2\"/><path d=\"M20 12h2\"/><path d=\"M20 17h2\"/><path d=\"M20 7h2\"/><path d=\"M7 20v2\"/><path d=\"M7 2v2\"/><rect x=\"4\" y=\"4\" width=\"16\" height=\"16\" rx=\"2\"/><rect x=\"8\" y=\"8\" width=\"8\" height=\"8\" rx=\"1\"/>",
    "memory-stick": "<path d=\"M12 12v-2\"/><path d=\"M12 18v-2\"/><path d=\"M16 12v-2\"/><path d=\"M16 18v-2\"/><path d=\"M2 11h1.5\"/><path d=\"M20 18v-2\"/><path d=\"M20.5 11H22\"/><path d=\"M4 18v-2\"/><path d=\"M8 12v-2\"/><path d=\"M8 18v-2\"/><rect x=\"2\" y=\"6\" width=\"20\" height=\"10\" rx=\"2\"/>",
    "chart-column": "<path d=\"M3 3v16a2 2 0 0 0 2 2h16\"/><path d=\"M18 17V9\"/><path d=\"M13 17V5\"/><path d=\"M8 17v-3\"/>",
    "external-link": "<path d=\"M15 3h6v6\"/><path d=\"M10 14 21 3\"/><path d=\"M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6\"/>",
    "arrow-down-wide-narrow": "<path d=\"m3 16 4 4 4-4\"/><path d=\"M7 20V4\"/><path d=\"M11 4h10\"/><path d=\"M11 8h7\"/><path d=\"M11 12h4\"/>",
    "circle-dashed": "<path d=\"M10.1 2.182a10 10 0 0 1 3.8 0\"/><path d=\"M13.9 21.818a10 10 0 0 1-3.8 0\"/><path d=\"M17.609 3.721a10 10 0 0 1 2.69 2.7\"/><path d=\"M2.182 13.9a10 10 0 0 1 0-3.8\"/><path d=\"M20.279 17.609a10 10 0 0 1-2.7 2.69\"/><path d=\"M21.818 10.1a10 10 0 0 1 0 3.8\"/><path d=\"M3.721 6.391a10 10 0 0 1 2.7-2.69\"/><path d=\"M6.391 20.279a10 10 0 0 1-2.69-2.7\"/>"
  };
  var root = document.documentElement;
  // ?theme=light or ?theme=dark opens the page in that theme (for screenshots).
  var asked = /[?&]theme=(light|dark)/.exec(location.search);
  if (asked) root.setAttribute("data-theme", asked[1]);

  // The nodes: cores, memory in GB, the GB one ruled unit of memory stands for.
  var NODES = {
    "build-1": { os: "Linux", cores: 8, mem: 16, unit: 2, slots: 2 },
    "mac-1": { os: "macOS", cores: 10, mem: 32, unit: 4, slots: 2 },
    "build-2": { os: "Linux", cores: 4, mem: 8, unit: 2, slots: 1, old: "1.35.5" }
  };
  // The jobs, heaviest first on each node. c and m: the median and the highest peak over the
  // last passed runs (cores; GB). lp: where its number sits on option B's map.
  var JOBS = [
    { n: 1, project: "example-app", job: "test", kind: "github", node: "build-1", runs: 20, c: [7.2, 7.8], m: [5.6, 6.3], lp: "t" },
    { n: 2, project: "example-shop", job: "build", kind: "github", node: "build-1", runs: 20, c: [3.6, 7.4], m: [2.4, 4.8], lp: "b" },
    { n: 3, project: "example-app", job: "check", kind: "agent", node: "build-1", runs: 20, c: [5.4, 6.1], m: [3.1, 3.5], lp: "b" },
    { n: 4, project: "example-api", job: "e2e", kind: "github", node: "build-1", runs: 12, c: [4.8, 6.6], m: [7.9, 9.4], lp: "r" },
    { n: 5, project: "example-api", job: "check", kind: "agent", node: "build-1", runs: 18, c: [3.2, 4.4], m: [2.2, 2.9], lp: "t" },
    { n: 6, project: "example-shop", job: "check", kind: "agent", node: "build-1", runs: 20, c: [2.1, 2.6], m: [1.6, 1.9], lp: "t" },
    { n: 7, project: "example-site", job: "unit", kind: "agent", node: "build-1", runs: 20, c: [1.4, 1.8], m: [0.7, 0.9], lp: "r" },
    { n: 8, project: "example-app", job: "lint", kind: "agent", node: "build-1", runs: 20, c: [0.9, 1.2], m: [0.412, 0.538], lp: "t" },
    { n: 9, project: "example-site", job: "format", kind: "agent", node: "build-1", runs: 20, c: null, m: [0.148, 0.212], gap: "short" },
    { n: 10, project: "example-ios", job: "build", kind: "github", node: "mac-1", runs: 9, c: [7.1, 9.3], m: [6.0, 7.7], lp: "l" },
    { n: 11, project: "example-ios", job: "test", kind: "agent", node: "mac-1", runs: 14, c: [6.3, 8.2], m: [5.2, 6.8], lp: "l" },
    { n: 12, project: "example-legacy", job: "check", kind: "agent", node: "build-2", runs: 6, c: null, m: null, gap: "none" }
  ];
  // One run each, for the job's page. stages: name and seconds; the last one of a running job
  // is the one it is in. pc and pm: its peaks and their stages; avg: cpu_s over its run time.
  var RUNS = {
    fin: { cap: "a finished job (the page above)", project: "example-app", job: "check", kind: "agent", node: "build-1", id: "01JD2K7Q", branch: "feature/login-form",
      state: "passed", secs: 232, usual: 240, pc: 6.1, pcIn: "command", pm: 3.5, pmIn: "install", avg: 3.5, cpu: 812, samples: 23, uc: 5.4, um: 3.1, fit: [7, 3.5], of: 20,
      stages: [["prepare", 4], ["toolchain", 2], ["environment", 9], ["images", 14], ["install", 38], ["setup", 12], ["command", 153]] },
    run: { cap: "a running job, in its command", project: "example-api", job: "check", kind: "agent", node: "build-1", id: "01JD2M4C", branch: "feature/orders-table",
      state: "running", secs: 100, usual: 318, pc: 4.1, pcIn: "command", pm: 2.6, pmIn: "setup", avg: 2.2, cpu: 220, samples: 10, uc: 3.2, um: 2.2, fit: [5, 3.0], of: 18,
      now: [3.9, 2.4], stages: [["prepare", 3], ["toolchain", 2], ["environment", 8], ["images", 11], ["install", 21], ["setup", 9], ["command", 46]] },
    ci: { cap: "a running GitHub run", project: "example-api", job: "e2e", kind: "github", node: "build-1", id: "01JD2M9X", branch: "main",
      state: "running", secs: 130, usual: 340, pc: 5.9, pm: 7.4, avg: 3.1, cpu: 403, samples: 13, uc: 4.8, um: 7.9, fit: [7, 9.5], of: 12, now: [4.2, 6.8], stages: [["CI run", 130]] },
    short: { cap: "too short to measure cores", project: "example-site", job: "format", kind: "agent", node: "build-1", id: "01JD2L1B", branch: "main",
      state: "passed", secs: 14, usual: 15, pc: null, pm: 0.212, pmIn: "command", samples: 1, um: 0.148, fit: [null, 0.5], of: 20, stages: [["prepare", 3], ["command", 11]] },
    none: { cap: "not measured: its node runs an older mulebox", project: "example-legacy", job: "check", kind: "agent", node: "build-2", id: "01JD2H6T", branch: "main",
      state: "passed", secs: 140, usual: 150, pc: null, pm: null, samples: 0, stages: [["prepare", 5], ["install", 40], ["command", 95]] }
  };

  function i(name, cls) { return '<i data-i="' + name + '"' + (cls ? ' class="' + cls + '"' : "") + "></i>"; }
  function co(n) { return n.toFixed(1); }
  function gb(n) { return n < 1 ? (n * 1000).toFixed(1) + " MB" : n.toFixed(1) + " GB"; }
  function fitC(j) { return Math.ceil(j.c[1]); }
  function fitM(j) { return Math.ceil(j.m[1] * 2) / 2; }
  function dur(s) { return s < 60 ? s + "s" : Math.floor(s / 60) + "m" + (s % 60 ? " " + ("0" + (s % 60)).slice(-2) + "s" : ""); }
  function size(n) { return n.toFixed(1) + " GB"; }   // a size is in steps of 0.5 GB, so always in GB
  function clamp(n) { return Math.max(0, Math.min(1, n)).toFixed(3); }
  function cores(n) { return n === 1 ? "1 core" : n + " cores"; }
  function src(kind) { return kind === "github" ? i("workflow", "s") : i("laptop", "s"); }
  function kindWord(kind) { return kind === "github" ? "GitHub run" : "agent job"; }
  function name(j) { return '<a class="job-name" href="#page">' + j.project + " <span>/</span> " + j.job + "</a>"; }
  function nameCell(j) {
    return '<div class="u-name" title="' + (j.kind === "github" ? "A GitHub run's job" : "An agent's job") + '">' + src(j.kind) + name(j) +
      '<small class="num">' + j.runs + " passed runs, " + kindWord(j.kind) + "</small></div>";
  }
  function gapText(j) {
    return j.gap === "none"
      ? "Not measured. " + j.node + " runs mulebox " + NODES[j.node].old + ", which sends no usage: <code>mulebox setup " + j.node + "</code> upgrades it."
      : "Cores: too short to measure. Its runs end before two readings, 20 s.";
  }
  function nodeHead(key, count) {
    var nd = NODES[key];
    return '<div class="u-node"><strong>' + i("server") + key + '</strong><span class="num">' + nd.os + ", " + nd.cores + " cores, " + gb(nd.mem) + ' memory</span><span class="right num">' +
      i("arrow-down-wide-narrow", "s") + count + (count === 1 ? " job" : " jobs, heaviest first") + "</span></div>";
  }
  function groups(only) {
    var out = [];
    Object.keys(NODES).forEach(function (key) {
      var jobs = JOBS.filter(function (j) { return j.node === key && (!only || only.indexOf(j.n) >= 0); });
      if (jobs.length) out.push([key, jobs]);
    });
    return out;
  }

  // Option A: a row per job, each measure as a range on a track that is the whole node.
  function range(of, units, med, hi, fit, label) {
    return '<div class="u-range" role="img" aria-label="' + label + '" title="' + label + '" style="--of:' + of + ";--units:" + units + ";--med:" + med + ";--hi:" + hi + ";--fit:" + fit +
      '"><i class="hi"></i><i class="med"></i><i class="fit"></i></div>';
  }
  function rowA(j) {
    var nd = NODES[j.node];
    if (j.gap === "none") return '<div class="u-row">' + nameCell(j) + '<p class="u-gap wide">' + i("circle-dashed", "s") + "<span>" + gapText(j) + "</span></p></div>";
    var c = j.c ? '<div class="u-cell"><span class="lab">Cores, of ' + nd.cores + "</span>" +
      range(nd.cores, nd.cores, j.c[0], j.c[1], fitC(j), "Cores: usually " + co(j.c[0]) + ", at most " + co(j.c[1]) + ", of " + nd.cores) +
      '<p class="u-say num"><b>' + co(j.c[1]) + "</b> at most, " + co(j.c[0]) + " usually</p></div>"
      : '<p class="u-gap">' + i("circle-dashed", "s") + "<span>" + gapText(j) + "</span></p>";
    var m = '<div class="u-cell"><span class="lab">Memory, of ' + gb(nd.mem) + "</span>" +
      range(nd.mem, nd.mem / nd.unit, j.m[0], j.m[1], fitM(j), "Memory: usually " + gb(j.m[0]) + ", at most " + gb(j.m[1]) + ", of " + gb(nd.mem)) +
      '<p class="u-say num"><b>' + gb(j.m[1]) + "</b> at most, " + gb(j.m[0]) + " usually</p></div>";
    return '<div class="u-row">' + nameCell(j) + c + m + '<p class="u-fit num"><span class="lab">Fits every run</span>' +
      (j.c ? "<span>" + fitC(j) + " of " + nd.cores + " cores</span>" : '<span class="of">cores not known</span>') + "<span>" + size(fitM(j)) + "</span></p></div>";
  }
  function listA(only) {
    return '<div class="u-list">' + groups(only).map(function (g) {
      var nd = NODES[g[0]];
      return nodeHead(g[0], g[1].length) + '<div class="u-head"><span>Job</span><span>Cores, of ' + nd.cores + "</span><span>Memory, of " + gb(nd.mem) +
        "</span><span>Fits every run</span></div>" + g[1].map(rowA).join("");
    }).join("") + "</div>";
  }

  // Option B: a node's jobs as points, cores across and memory up; the list beside it is the
  // same figures as a table, numbered like the points.
  function say(j) {
    var nd = NODES[j.node];
    return "<b>" + j.n + ". " + j.project + " / " + j.job + "</b>, " + (j.kind === "github" ? "a GitHub run's job" : "an agent's job") + ", " + j.runs + " passed runs. At most <b>" + co(j.c[1]) +
      " cores and " + gb(j.m[1]) + "</b>; usually " + co(j.c[0]) + " and " + gb(j.m[0]) + ". Fits every run: " + fitC(j) + " of " + nd.cores + " cores, " + size(fitM(j)) + " of " + gb(nd.mem) + ".";
  }
  function map(key, jobs) {
    var nd = NODES[key], on = jobs.filter(function (j) { return j.c && j.m; });
    var ticks = function (max, unit) { return [0, 1, 2, 3, 4].map(function (k) { return "<span>" + (max * k / 4) + (k === 4 ? unit : "") + "</span>"; }).join(""); };
    if (!on.length) return '<p class="none">Nothing to draw for ' + key + ": none of its runs were measured.</p>";
    return '<div><div class="u-map"><p class="u-ax-t top">Memory, the most held in a run</p><div class="u-ax-y num">' + ticks(nd.mem, " GB") + '</div><div class="u-plot">' +
      '<span class="u-half x">half of ' + key + '</span><span class="u-half y">half of ' + key + '</span><svg class="u-tails" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">' +
      on.map(function (j) {
        return '<line class="' + (j.kind === "github" ? "gh" : "") + '" x1="' + (j.c[0] / nd.cores * 100).toFixed(2) + '" y1="' + (100 - j.m[0] / nd.mem * 100).toFixed(2) + '" x2="' +
          (j.c[1] / nd.cores * 100).toFixed(2) + '" y2="' + (100 - j.m[1] / nd.mem * 100).toFixed(2) + '"/>';
      }).join("") + "</svg>" +
      on.map(function (j, k) {
        return '<button class="u-pt' + (j.kind === "github" ? " gh" : "") + '" type="button" aria-pressed="' + (k === 0) + '" data-lp="' + j.lp + '" style="--x:' + (j.c[1] / nd.cores).toFixed(4) +
          ";--y:" + (j.m[1] / nd.mem).toFixed(4) + '" data-say="' + say(j).replace(/"/g, "&quot;") + '" aria-label="' + j.project + " / " + j.job + '"><i></i><span>' + j.n + "</span></button>";
      }).join("") + '</div><div class="u-ax-x num">' + ticks(nd.cores, "") + '</div><p class="u-ax-t">Cores, the busiest 10 s of a run</p></div>' +
      '<p class="u-read" aria-live="polite">' + say(on[0]) + "</p></div>";
  }
  function rowB(j) {
    var nd = NODES[j.node], num = '<span class="pos num">' + j.n + "</span>";
    if (j.gap === "none") return '<div class="u-row">' + num + nameCell(j) + '<p class="u-gap wide">' + i("circle-dashed", "s") + "<span>" + gapText(j) + "</span></p></div>";
    return '<div class="u-row">' + num + nameCell(j) +
      (j.c ? '<span class="r num"><span class="lab">Cores, usual and highest: </span>' + co(j.c[0]) + " / <b>" + co(j.c[1]) + "</b></span>"
        : '<span class="r t2" title="Its runs end before two readings, 20 s">too short</span>') +
      '<span class="r num"><span class="lab">Memory, usual and highest: </span>' + gb(j.m[0]).replace(/ [MG]B/, "") + " / <b>" + gb(j.m[1]) + "</b></span>" +
      '<span class="r num"><span class="lab">Fits every run: </span><b>' + (j.c ? fitC(j) + " of " + nd.cores + ", " : "") + size(fitM(j)) + "</b></span></div>";
  }
  function viewB(key) {
    var jobs = JOBS.filter(function (j) { return j.node === key; }), nd = NODES[key];
    return '<div class="u-mapwrap" data-node="' + key + '"' + (key === "build-1" ? "" : " hidden") + ">" + map(key, jobs) +
      '<div class="u-tbl"><div class="u-head"><span></span><span>Job</span><span class="r">Cores, of ' + nd.cores + '</span><span class="r">Memory, of ' + gb(nd.mem) +
      '</span><span class="r">Fits every run</span></div>' + jobs.map(rowB).join("") + "</div></div>";
  }

  // Option C: on the Machines page, a node's cores as boxes and how many of a job fit at once.
  function cells(count, unit, pair) {
    var html = "";
    for (var k = 0; k < count; k++) html += '<i style="--f:' + clamp(pair[0] / unit - k) + ";--h:" + clamp(pair[1] / unit - k) + '"></i>';
    return '<span class="u-cells" role="img">' + html + "</span>";
  }
  function rowC(j) {
    var nd = NODES[j.node];
    if (j.gap === "none") return '<div class="u-row">' + nameCell(j) + '<p class="u-gap wide">' + i("circle-dashed", "s") + "<span>" + gapText(j) + "</span></p></div>";
    var byC = j.c ? Math.floor(nd.cores / fitC(j)) : Infinity, byM = Math.floor(nd.mem / fitM(j)), at = Math.min(byC, byM);
    var c = j.c ? '<div class="u-cell"><span class="lab">Cores, a box each</span>' + cells(nd.cores, 1, j.c) + '<p class="u-say num"><b>' + fitC(j) + " of " + nd.cores +
      "</b>, at most " + co(j.c[1]) + "</p></div>" : '<p class="u-gap">' + i("circle-dashed", "s") + "<span>" + gapText(j) + "</span></p>";
    return '<div class="u-row">' + nameCell(j) + c + '<div class="u-cell"><span class="lab">Memory, a box per ' + nd.unit + " GB</span>" + cells(nd.mem / nd.unit, nd.unit, j.m) +
      '<p class="u-say num"><b>' + size(fitM(j)) + "</b>, at most " + gb(j.m[1]) + '</p></div><p class="u-side num"><span class="lab">Side by side</span>' +
      (j.c ? "<b>" + at + " at a time</b><span>" + (byC < byM ? i("cpu", "s") + "cores decide" : byM < byC ? i("memory-stick", "s") + "memory decides" : "cores and memory") + "</span>"
        : "<span>not known without cores</span>") + "</p></div>";
  }
  function listC(only) {
    return groups(only).map(function (g) {
      var key = g[0], nd = NODES[key];
      return '<section class="panel"><header class="panel-head strong"><h3>' + i("server") + "What " + key + "'s jobs need</h3><span class=\"panel-note num\">" + nd.cores + " cores, " + gb(nd.mem) +
        ", " + nd.slots + (nd.slots === 1 ? " slot" : " slots") + ' today</span></header><div class="panel-body gap"><div class="u-list cells"><div class="u-head"><span>Job, heaviest first</span><span>Cores, a box each</span>' +
        "<span>Memory, a box per " + nd.unit + " GB</span><span>Side by side</span></div>" + g[1].map(rowC).join("") + "</div>" +
        (key === "build-1" && !only ? '<p class="u-today">' + i("info", "s") + "<span><b>Today build-1 runs any 2 jobs at once.</b> By these figures two runs of example-app / test would ask for 16 of its 8 cores, " +
          "and four lints would fit. Nothing acts on this yet.</span></p>" : "") + "</div></section>";
    }).join("");
  }

  // The job's page. Stages as today; B writes the peaks under the stage they happened in.
  function stagesPanel(r, peaks) {
    var nd = NODES[r.node], live = r.state === "running", gh = r.kind === "github", scale = Math.max(r.secs, r.usual), at = 0;
    var pct = function (n) { return (100 * n / scale).toFixed(2) + "%"; };
    var peakC = '<p class="wf-peak">' + i("cpu", "s") + "<span><b>" + (r.pc === null ? "" : co(r.pc) + " of " + nd.cores + " cores") + "</b>, its busiest 10 s" + (live ? " so far" : "") + "</span></p>";
    var peakM = '<p class="wf-peak">' + i("memory-stick", "s") + "<span><b>" + (r.pm === null ? "" : gb(r.pm) + " of " + gb(nd.mem)) + "</b>, the most it held" + (live ? " so far" : "") + "</span></p>";
    var rows = r.stages.map(function (s, k) {
      var last = k === r.stages.length - 1, state = live && last ? "running" : "passed";
      var row = '<li><div class="wf-row"><span class="st" data-state="' + state + '">' + i(state === "running" ? "loader-circle" : "circle-check", "s") + "<span>" + s[0] + '</span></span><div class="wf-track">' +
        '<i class="wf-bar" style="--from:' + pct(at) + ";--len:" + pct(s[1]) + '"></i>' + (last ? '<i class="wf-usual" style="--at:' + pct(r.usual) + '"></i>' : "") + '</div><span class="num">' + dur(s[1]) + "</span></div>" +
        (peaks && r.pc !== null && (gh || s[0] === r.pcIn) ? peakC : "") + (peaks && r.pm !== null && (gh || s[0] === r.pmIn) ? peakM : "") + "</li>";
      at += s[1];
      return row;
    }).join("");
    var marks = scale % 240 === 0 ? [0, 1, 2, 3, 4] : [0, 2, 4];   // five labels when they are whole minutes
    var axis = marks.map(function (k) { return "<span>" + (k ? dur(Math.round(scale * k / 4)) : "0") + "</span>"; }).join("");
    var meter = !live ? "" : peaks
      ? '<div class="meter-row"><span>Cores</span><div class="u-range thin" role="img" aria-label="Cores now and the peak so far" style="--of:' + nd.cores + ";--units:1;--med:" + r.now[0] + ";--fit:" + r.pc +
        '"><i class="med"></i><i class="fit"></i></div><span class="num">' + co(r.now[0]) + " of " + nd.cores + "</span></div>"
      : '<div class="meter-row"><span>Cores</span><div class="meter"><i style="--v:' + (100 * r.now[0] / nd.cores).toFixed(0) + '%"></i></div><span class="num">' + co(r.now[0]) + " of " + nd.cores + "</span></div>";
    var key = '<p class="u-key"><span><i class="k"></i>This run</span><span><i class="k fit"></i>Where it usually ends</span>' + (peaks && live ? '<span><i class="k fit"></i>On Cores: its peak so far</span>' : "") + "</p>";
    var foot = !peaks ? "" : r.samples === 0 ? '<p class="wf-foot u-gap">' + i("circle-dashed", "s") + "<span>Cores and memory were not measured: " + r.node + " runs mulebox " + NODES[r.node].old + ".</span></p>"
      : r.pc === null ? '<p class="wf-foot u-gap">' + i("circle-dashed", "s") + "<span>Too short to measure cores: it ended before two readings. Memory from 1 reading.</span></p>"
      : '<p class="wf-foot num"><b>' + co(r.avg) + " cores on average</b> over " + dur(r.secs) + (live ? " so far" : "") + ", from " + r.samples + " readings." +
        (live ? " Memory now " + gb(r.now[1]) + "." : "") + (gh ? " The cores count the run's Compose containers." : "") + "</p>";
    return '<section class="panel"><header class="panel-head strong"><h3>' + (gh ? "Time" : "Stages") + '</h3><span class="panel-note num">' + dur(r.secs) + (live ? " so far" : "") + " of usually " + dur(r.usual) +
      '</span></header><div class="panel-body wf"><ol>' + rows + '</ol><div class="wf-row wf-axis" aria-hidden="true"><span></span><div class="num">' + axis + "</div><span></span></div>" + key + meter + foot + "</div></section>";
  }
  function measure(r, what) {   // A: one measure of a run against its node
    var nd = NODES[r.node], isC = what === "c", live = r.state === "running", peak = isC ? r.pc : r.pm, of = isC ? nd.cores : nd.mem, usual = isC ? r.uc : r.um;
    var head = '<div class="u-m-top"><span class="nm">' + i(isC ? "cpu" : "memory-stick") + (isC ? "Cores" : "Memory") + "</span>";
    if (peak === null) return '<div class="u-m">' + head + '</div><p class="u-gap">' + i("circle-dashed", "s") + "<span>Too short to measure: the run ended before two readings, 20 s.</span></p></div>";
    var where = isC ? r.pcIn : r.pmIn;
    return '<div class="u-m">' + head + '<span class="num"><b>' + (isC ? co(peak) : gb(peak)) + "</b> of " + (isC ? of + " cores" : gb(of)) + (live ? ", so far" : "") + "</span></div>" +
      '<div class="u-range" role="img" aria-label="' + (isC ? "Cores" : "Memory") + ' at the peak, against the node" style="--of:' + of + ";--units:" + (isC ? of : of / nd.unit) + ";--med:" + peak + ";--fit:" + usual +
      '"><i class="med"></i><i class="fit"></i></div><p class="u-say num">' +
      (isC ? "Its busiest 10 s" + (where ? ", in <b>" + where + "</b>" : "") + ". " + (r.avg ? "<b>" + co(r.avg) + "</b> on average over " + dur(r.secs) + (live ? ", " + co(r.now[0]) + " now" : "") + "." : "")
        : "The most it held" + (where ? ", in <b>" + where + "</b>" : "") + "." + (live ? " " + gb(r.now[1]) + " now." : "")) + "</p></div>";
  }
  function panelA(r) {
    var body = r.samples === 0 ? '<p class="u-gap">' + i("circle-dashed", "s") + "<span>Not measured. " + r.node + " runs mulebox " + NODES[r.node].old + ", which sends no usage: <code>mulebox setup " + r.node + "</code> upgrades it.</span></p>"
      : measure(r, "c") + measure(r, "m") + '<p class="u-key"><span><i class="k"></i>This run\'s peak</span><span><i class="k fit"></i>This job\'s usual peak</span></p>' +
        '<p class="t-foot">The last ' + r.of + " passes of " + r.project + " / " + r.job + " fit in <b>" + (r.fit[0] ? cores(r.fit[0]) + " and " : "") + size(r.fit[1]) + '</b>. <a href="#summary">Usage of this job</a></p>';
    return '<section class="panel"><header class="panel-head strong"><h3>Usage</h3><span class="panel-note num">' +
      (r.samples ? r.samples + (r.samples === 1 ? " reading" : " readings, one every 10 s") : "no readings") + '</span></header><div class="panel-body u-use">' + body + "</div></section>";
  }
  function lineC(r) {   // C: one sentence under the header
    var nd = NODES[r.node], live = r.state === "running";
    var text = r.samples === 0 ? "Cores and memory were not measured: " + r.node + " runs mulebox " + NODES[r.node].old + "."
      : r.pc === null ? "Too short to measure cores. It held <b>" + gb(r.pm) + "</b> of " + gb(nd.mem) + " at most."
      : (live ? "So far it used" : "Used") + " at most <b>" + co(r.pc) + " of " + nd.cores + " cores</b>" + (r.pcIn ? " (in " + r.pcIn + ")" : "") + " and <b>" + gb(r.pm) + " of " + gb(nd.mem) + "</b>" +
        (r.pmIn ? " (in " + r.pmIn + ")" : "") + "; " + co(r.avg) + " cores on average" + (live ? ", " + co(r.now[0]) + " now" : "") + ".";
    return '<p class="u-line">' + i(r.samples === 0 || r.pc === null ? "circle-dashed" : "cpu", "s") + "<span>" + text + "</span></p>";
  }
  function factsC(r) {
    var nd = NODES[r.node], live = r.state === "running", so = live ? " so far" : "";
    var rows = r.samples === 0 ? [["Usage", "not measured"]] : [
      ["Peak cores" + so, r.pc === null ? "too short to measure" : co(r.pc) + " of " + nd.cores + (r.pcIn ? ", in " + r.pcIn : "")],
      ["Peak memory" + so, gb(r.pm) + " of " + gb(nd.mem) + (r.pmIn ? ", in " + r.pmIn : "")]].concat(r.pc === null ? [] : [
      ["Average cores", co(r.avg) + " over " + dur(r.secs)], ["CPU time", dur(r.cpu)]], [["Readings", r.samples + ", one every 10 s"]],
      r.fit ? [["Fits its last " + r.of + " passes", (r.fit[0] ? cores(r.fit[0]) + ", " : "") + size(r.fit[1])]] : []);
    return '<details class="t-details" open><summary>Job details</summary><dl class="t-facts">' + rows.map(function (p) { return '<div><dt>' + p[0] + '</dt><dd class="num">' + p[1] + "</dd></div>"; }).join("") +
      '<div><dt class="t2">Project, branch, times, command</dt><dd class="t2">as today</dd></div></dl></details>';
  }
  function state(r, big) {
    var live = r.state === "running";
    return '<span class="st' + (big ? " big" : "") + '" data-state="' + r.state + '">' + i(live ? "loader-circle" : "circle-check", big ? "l" : "") + "<span>" + (live ? "Running" : "Passed") + "</span></span>";
  }

  document.querySelectorAll("[data-summary]").forEach(function (box) {
    var opt = box.getAttribute("data-summary"), only = box.getAttribute("data-only");
    only = only ? only.split(",").map(Number) : null;
    box.innerHTML = opt === "a" ? listA(only) : opt === "c" ? listC(only) : Object.keys(NODES).map(viewB).join("");
    if (only && opt === "b") box.querySelectorAll(".u-row").forEach(function (row, k) { row.hidden = k > 3; });
  });
  // <div data-page="a">: the page of the finished job.
  document.querySelectorAll("[data-page]").forEach(function (box) {
    var opt = box.getAttribute("data-page"), r = RUNS.fin;
    box.innerHTML = '<div class="jp"><a class="crumb" href="index.html">' + i("arrow-left") + 'Back to the queue</a><header class="jp-head"><div class="jp-title">' + state(r, true) +
      "<h1>" + r.project + " <span>/</span> " + r.job + '</h1></div><p class="jp-say" role="status">Finished, exit 0, ended 14:21:09</p>' + (opt === "c" ? lineC(r) : "") +
      '<p class="meta"><span class="branch">' + i("git-branch", "s") + "<span>" + r.branch + '</span></span><span class="job-id">' + r.id + "</span><span>" + i("laptop", "s") + "macOS</span><span>" +
      i("server", "s") + r.node + '</span><span class="num">started 14:17:17</span></p></header><div class="jp-split"><div class="jp-left">' + stagesPanel(r, opt === "b") + (opt === "a" ? panelA(r) : "") +
      '<p class="as-today">Tests, as today.</p></div><p class="as-today log-ph">Log, as today.</p></div>' + (opt === "c" ? factsC(r) : '<p class="as-today">Job details, as today.</p>') + "</div>";
  });
  // <div data-bits="a">: the same part of the page for the other runs.
  document.querySelectorAll("[data-bits]").forEach(function (box) {
    var opt = box.getAttribute("data-bits");
    box.innerHTML = ["run", "ci", "short", "none"].map(function (key) {
      var r = RUNS[key];
      return '<figure class="v-fig"><figcaption>' + r.cap + '</figcaption><div class="bit">' + (opt === "a" ? panelA(r) : opt === "b" ? stagesPanel(r, true) : lineC(r) + factsC(r)) + "</div></figure>";
    }).join("");
  });

  // Option B: a point says its job in the line under the map; the node choice swaps the map.
  function show(pt, keep) {
    var wrap = pt.closest(".u-mapwrap");
    if (keep) wrap.querySelectorAll(".u-pt").forEach(function (b) { b.setAttribute("aria-pressed", String(b === pt)); });
    wrap.querySelector(".u-read").innerHTML = pt.getAttribute("data-say");
  }
  document.addEventListener("click", function (event) {
    var pt = event.target.closest(".u-pt"), pick = event.target.closest("[data-show-node]");
    if (pt) show(pt, true);
    if (pick) pick.closest(".panel-body").querySelectorAll(".u-mapwrap").forEach(function (w) { w.hidden = w.getAttribute("data-node") !== pick.getAttribute("data-show-node"); });
  });
  document.addEventListener("mouseover", function (event) { var pt = event.target.closest && event.target.closest(".u-pt"); if (pt) show(pt, false); });
  document.addEventListener("mouseout", function (event) {
    var pt = event.target.closest && event.target.closest(".u-pt");
    if (pt) show(pt.parentNode.querySelector('[aria-pressed="true"]') || pt, false);
  });
  document.addEventListener("focusin", function (event) { var pt = event.target.closest && event.target.closest(".u-pt"); if (pt) show(pt, false); });

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
