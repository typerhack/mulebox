// The "proof that tests ran" mockups of 2026-11-15 (M24.1). Loaded before ../storage/storage.js
// and ../mockups-2026-11-13.js, which draw the other icons and switch the theme. This file holds
// the seven example jobs once, draws each option's rows, job page and small figures from them,
// and opens what a click would open. Nothing is saved or sent anywhere.
// Icons: Lucide (ISC), outline, the paths of the lucide-react version the dashboard uses.
(function () {
  "use strict";
  var ICONS = {
    "list-checks": "<path d=\"M13 5h8\"/><path d=\"M13 12h8\"/><path d=\"M13 19h8\"/><path d=\"m3 17 2 2 4-4\"/><path d=\"m3 7 2 2 4-4\"/>",
    "list-x": "<path d=\"M16 5H3\"/><path d=\"M11 12H3\"/><path d=\"M16 19H3\"/><path d=\"m15.5 9.5 5 5\"/><path d=\"m20.5 9.5-5 5\"/>",
    "list-minus": "<path d=\"M16 5H3\"/><path d=\"M11 12H3\"/><path d=\"M16 19H3\"/><path d=\"M21 12h-6\"/>",
    "list-plus": "<path d=\"M16 5H3\"/><path d=\"M11 12H3\"/><path d=\"M16 19H3\"/><path d=\"M18 9v6\"/><path d=\"M21 12h-6\"/>",
    "message-square-quote": "<path d=\"M22 17a2 2 0 0 1-2 2H6.828a2 2 0 0 0-1.414.586l-2.202 2.202A.71.71 0 0 1 2 21.286V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2z\"/><path d=\"M14 14a2 2 0 0 0 2-2V8h-2\"/><path d=\"M8 14a2 2 0 0 0 2-2V8H8\"/>",
    "scroll-text": "<path d=\"M15 12h-5\"/><path d=\"M15 8h-5\"/><path d=\"M19 17V5a2 2 0 0 0-2-2H4\"/><path d=\"M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3\"/>",
    "search": "<path d=\"m21 21-4.34-4.34\"/><circle cx=\"11\" cy=\"11\" r=\"8\"/>"
  };
  var root = document.documentElement;
  // ?theme=light or ?theme=dark opens the page in that theme (for screenshots).
  var asked = /[?&]theme=(light|dark)/.exec(location.search);
  if (asked) root.setAttribute("data-theme", asked[1]);

  // What each verdict looks like: its icon, the colour of that icon, and the state C gives it.
  var LOOK = {
    ok: ["list-checks", "plain"], more: ["list-plus", "plain"], fewer: ["list-minus", "failed", "Fewer tests"],
    zero: ["list-x", "failed", "No tests ran"], allowed: ["list-minus", "warn"]
  };
  // The seven situations. runners: name, ran, skipped, ran on the pass it was compared with.
  // `line` is what a row says in words, `sentence` what the page says, `result` today's line.
  var JOBS = [
    { key: "fewer", cap: "fewer tests than the last pass: a failure, exit 8", project: "example-app", job: "check", branch: "fix/cart-total", id: "01JCX5A1", os: "macOS",
      state: "failed", at: "14:07:31", took: "3m 49s", exit: 8, delta: "−8", cmp: ["01JCX3B2", "fix/cart-total", "today 11:52"],
      runners: [["pytest", 3462, 5, 3470], ["vitest", 213, 0, 213]],
      line: "<b>8 fewer tests</b> than the last pass: pytest ran 3462, was 3470",
      sentence: "The command passed, but pytest ran 3462 tests and the last pass on fix/cart-total ran 3470.", result: "Finished, 8 fewer tests than the last pass, exit 8, ended 14:07:31" },
    { key: "zero", cap: "a runner ran no tests: a failure, exit 8", project: "example-site", job: "unit", branch: "chore/vitest-config", id: "01JCX59T", os: "Linux",
      state: "failed", at: "13:58:44", took: "41s", exit: 8, delta: "−213", cmp: ["01JCX2Z6", "main", "yesterday 17:20"],
      runners: [["vitest", 0, 213, 213]],
      line: "<b>vitest ran no tests</b>: all 213 were skipped",
      sentence: "The command passed, but vitest ran 0 tests and skipped 213. A pass with no tests counts as a failure.", result: "Finished, vitest ran no tests, exit 8, ended 13:58:44" },
    { key: "broke", verdict: "ok", cap: "an ordinary failure: the command failed, the count is still shown", project: "example-shop", job: "check", branch: "fix/checkout-rounding", id: "01JCX54B", os: "macOS",
      state: "failed", at: "13:12:26", took: "2m 05s", exit: 1, delta: "", cmp: ["01JCX2T4", "fix/checkout-rounding", "today 10:31"],
      runners: [["jest", 1204, 2, 1204]], line: "", sentence: "", result: "Finished, in command, exit 1, ended 13:12:26" },
    { key: "ok", cap: "a normal pass", project: "example-app", job: "check", branch: "feature/login-form", id: "01JCX5K3", os: "macOS",
      state: "passed", at: "14:21:09", took: "3m 52s", exit: 0, delta: "", cmp: ["01JCX4M7", "main", "today 12:40"],
      runners: [["pytest", 3462, 5, 3462], ["vitest", 213, 0, 213]], line: "", sentence: "", result: "Finished, exit 0, ended 14:21:09" },
    { key: "more", cap: "a pass with more tests than before", project: "example-api", job: "check", branch: "feature/orders-table", id: "01JCX5H8", os: "Linux",
      state: "passed", at: "14:15:50", took: "5m 18s", exit: 0, delta: "+12", cmp: ["01JCX4R2", "main", "today 12:05"],
      runners: [["pytest", 1904, 2, 1892]], line: "", sentence: "", result: "Finished, exit 0, ended 14:15:50" },
    { key: "allowed", cap: "a pass allowed with fewer tests, with the agent's reason", project: "example-api", job: "check", branch: "chore/drop-v1-api", id: "01JCX57Q", os: "macOS",
      state: "passed", at: "13:41:10", took: "5m 02s", exit: 0, delta: "−72", cmp: ["01JCX4R2", "main", "today 12:05"], reason: "removed the old v1 API tests",
      runners: [["pytest", 1820, 2, 1892]],
      line: "<b>72 fewer tests, allowed.</b> The agent's reason: “removed the old v1 API tests”",
      sentence: "pytest ran 1820 tests and the last pass on main ran 1892. The agent let this run pass with fewer.", result: "Finished, 72 fewer tests allowed, exit 0, ended 13:41:10" },
    { key: "lint", verdict: null, cap: "no test summary (a lint): nothing is shown", project: "example-app", job: "lint", branch: "feature/login-form", id: "01JCX56D", os: "macOS",
      state: "passed", at: "13:30:02", took: "24s", exit: 0, runners: [], result: "Finished, exit 0, ended 13:30:02" }
  ];
  JOBS.forEach(function (j) {
    if (j.verdict === undefined) j.verdict = j.key;
    j.ran = j.runners.reduce(function (n, r) { return n + r[1]; }, 0);
    j.skipped = j.runners.reduce(function (n, r) { return n + r[2]; }, 0);
    j.was = j.runners.reduce(function (n, r) { return n + r[3]; }, 0);
    // Earlier runs of the same job, oldest first: a suite that grew slowly to the compared pass.
    j.past = [];
    for (var k = 0; k < 15; k++) j.past.push(j.runners.map(function (r) { return r[3] - Math.floor((14 - k) / 2) * Math.ceil(r[3] / 400); }));
  });
  var seq = 0;
  function i(name, cls) { return '<i data-i="' + name + '"' + (cls ? ' class="' + cls + '"' : "") + "></i>"; }
  function by(key) { return JOBS.filter(function (j) { return j.key === key; })[0]; }
  function tests(n) { return n === 1 ? "1 test" : n + " tests"; }
  function long(j) {   // the count in one plain sentence, for a tooltip and a screen reader
    var per = j.runners.map(function (r) { return r[0] + " " + r[1]; }).join(", ");
    return tests(j.ran) + " ran, " + j.skipped + " skipped (" + per + "). " +
      (j.key === "fewer" || j.key === "zero" ? j.sentence : j.key === "allowed" ? j.sentence + " Its reason: “" + j.reason + "”."
        : j.key === "more" ? "12 more than the last pass on " + j.cmp[1] + "." : "The same count as the last pass on " + j.cmp[1] + ".");
  }
  function state(j, opt, big) {
    var own = opt === "c" && LOOK[j.verdict] && LOOK[j.verdict][2];
    return '<span class="st' + (big ? " big" : "") + '" data-state="' + j.state + '">' + i(own ? LOOK[j.verdict][0] : j.state === "passed" ? "circle-check" : "circle-x", big ? "l" : "") +
      "<span>" + (own || (j.state === "passed" ? "Passed" : "Failed")) + "</span></span>";
  }
  function spark(j) {
    var all = j.past.slice(-11).map(function (p) { return p.reduce(function (a, b) { return a + b; }, 0); }).concat([j.ran]);
    var max = Math.max.apply(null, all);
    return '<span class="spark" role="img" aria-label="The last 12 runs">' + all.map(function (n) { return '<i style="--n:' + (n / max).toFixed(3) + '"></i>'; }).join("") + "</span>";
  }

  // What each option puts on a row: `end` before the time, `why` on a line under the name.
  var ROW = {
    a: function (j, open) {
      var id = "t" + (++seq), look = LOOK[j.verdict];
      return { open: open, end: '<button class="t-count" type="button" data-tone="' + look[1] + '" data-tip aria-expanded="' + open + '" aria-describedby="' + id + '" aria-label="' + tests(j.ran) + '">' +
        i(look[0], "s") + '<span class="num">' + j.ran + '</span><span class="w touch">tests</span>' + (j.delta ? '<span class="d num">' + j.delta + "</span>" : "") + "</button>",
        over: '<span class="t-tip" role="tooltip" id="' + id + '">' + long(j) + "</span>" };
    },
    b: function (j) {
      var look = LOOK[j.verdict];
      return { end: '<span class="t-count" data-tone="plain" title="Tests that ran">' + i("list-checks", "s") + '<span class="num">' + j.ran + '</span><span class="w">tests</span>' +
        (j.key === "more" ? '<span class="d num">' + j.delta + "</span>" : "") + "</span>",
        why: j.line ? '<span class="d-why" data-tone="' + look[1] + '">' + i(look[0], "s") + "<span>" + j.line + "</span></span>" : "" };
    },
    c: function (j) {
      return { end: '<span class="t-count" data-tone="plain" title="' + long(j) + '">' + spark(j) + '<span class="num">' + j.ran + '</span><span class="w">tests</span>' +
        (j.delta ? '<span class="d num">' + j.delta + "</span>" : "") + "</span>",
        why: j.reason ? '<span class="d-why" data-tone="plain">' + i("message-square-quote", "s") + "<span>Fewer tests, allowed: “" + j.reason + "”</span></span>" : "" };
    }
  };
  function row(j, opt, last, open) {
    var add = j.verdict ? ROW[opt](j, open) : {};
    return '<li class="d-row' + (add.open ? " tip-open" : "") + '" data-in="' + j.state + '">' + state(j, opt) +
      '<div class="d-main"><a class="job-name" href="#page">' + j.project + " <span>/</span> " + j.job + '</a><span class="branch">' + i("git-branch", "s") + "<span>" + j.branch +
      '</span></span><span class="job-id">' + j.id + '</span><span class="src">' + i("laptop", "s") + j.os + "</span>" + (add.why || "") + "</div>" +
      '<span class="d-end">' + (add.end || "") + '<span class="num">' + (last === "machine" ? "build-1" : j.at) + '</span><span class="num">' + j.took + "</span></span>" + (add.over || "") + "</li>";
  }
  // <ol data-rows="a" data-last="machine" data-only="fewer,zero" data-open="fewer">: an option's rows.
  document.querySelectorAll("[data-rows]").forEach(function (box) {
    var only = box.getAttribute("data-only"), open = box.getAttribute("data-open");
    box.innerHTML = JOBS.filter(function (j) { return !only || only.split(",").indexOf(j.key) >= 0; })
      .map(function (j) { return row(j, box.getAttribute("data-rows"), box.getAttribute("data-last"), j.key === open); }).join("");
  });

  // The parts of a job's page an option adds.
  function facts(j) {   // A: rows in "Job details"
    var rows = [["Tests", tests(j.ran) + " ran, " + j.skipped + " skipped"]].concat(j.runners.map(function (r) {
      return [r[0], r[1] + " ran, " + r[2] + " skipped" + (r[1] === r[3] ? "" : ", was " + r[3])];
    }), [["Compared with", j.cmp[0] + " on " + j.cmp[1]]], j.reason ? [["Reason for fewer", "“" + j.reason + "”"]] : [], j.exit === 8 ? [["Command's exit code", "0"], ["Exit code", "8"]] : []);
    return '<details class="t-details" open><summary>Job details</summary><dl class="t-facts">' + rows.map(function (r) { return "<div><dt>" + r[0] + "</dt><dd>" + r[1] + "</dd></div>"; }).join("") +
      '<div><dt class="t2">Project, branch, times, command</dt><dd class="t2">as today</dd></div></dl></details>';
  }
  function strip(j) {   // B: what happened, under the header
    if (!j.line) return "";
    var look = LOOK[j.verdict], bad = look[1] === "failed";
    return '<div class="strip t-strip' + (bad ? " danger" : "") + '" data-tone="' + look[1] + '" role="status">' + i(look[0]) + '<div class="strip-lines"><div class="strip-line"><p><b>' +
      (j.key === "fewer" ? "Fewer tests than the last pass." : j.key === "zero" ? "No tests ran." : "Passed with 72 fewer tests, allowed.") + "</b> " + j.sentence +
      (j.key === "fewer" ? ' Removed on purpose? The agent runs it again with the reason: <span class="cmd"><code>mulebox check --fewer-tests "&lt;reason&gt;"</code>' +
        '<button class="icon-btn bare" type="button" aria-label="Copy the command" title="Copy">' + i("copy", "s") + "</button></span>" : "") +
      (j.reason ? " Its reason: “" + j.reason + "”." : "") + "</p>" +
      (bad ? '<span class="acts"><button class="btn" type="button">' + i("scroll-text", "s") + "Go to the runner's summary</button><a class=\"btn\" href=\"#page\">Open the last pass</a></span>" : "") +
      "</div></div></div>";
  }
  function panel(j) {   // B: every runner beside the pass it was compared with
    return '<section class="panel"><header class="panel-head"><h3>' + i("list-checks", "s") + 'Tests</h3><span class="panel-note num">' + j.ran + " ran, " + j.skipped +
      ' skipped</span></header><div class="panel-body"><dl class="t-runs">' + j.runners.map(function (r) {
        var diff = r[1] - r[3], tone = r[1] === 0 || (diff < 0 && j.key === "fewer") ? "failed" : diff < 0 ? "warn" : "plain";
        var icon = r[1] === 0 ? "list-x" : diff < 0 ? "list-minus" : diff > 0 ? "list-plus" : "";
        return '<div data-tone="' + tone + '"><dt>' + r[0] + '</dt><dd><b class="num">' + r[1] + '</b> ran <span class="t2 num">' + r[2] + ' skipped</span></dd><dd class="was">' + (icon ? i(icon, "s") : "") + "<span>" +
          (r[1] === 0 ? "No test ran. The last pass ran " + r[3] + "." : diff ? Math.abs(diff) + (diff < 0 ? " fewer" : " more") + " than the last pass, which ran " + r[3] + "." : "The same as the last pass.") + "</span></dd></div>";
      }).join("") + "</dl>" +
      (j.reason ? '<div class="t-reason">' + i("message-square-quote", "s") + "<p><b>The agent's reason for fewer tests</b>“" + j.reason + "”</p></div>" : "") +
      '<p class="t-foot">Compared with <a href="#page"><code>' + j.cmp[0] + "</code></a>, the last pass on " + j.cmp[1] + ", " + j.cmp[2] + ".</p></div></section>";
  }
  function chart(j) {   // C: this job's runs, one bar each, stacked by runner, from zero
    var runs = j.past.concat([j.runners.map(function (r) { return r[1]; })]), look = LOOK[j.verdict];
    var max = Math.max.apply(null, runs.map(function (p) { return p.reduce(function (a, b) { return a + b; }, 0); }));
    var say = function (p, k) {
      var what = k === 15 ? "This run, " + j.id : k === 14 ? "The last pass, " + j.cmp[0] + " on " + j.cmp[1] : "Run " + (k + 1) + " of 16, a pass";
      return "<b>" + what + ".</b> " + tests(p.reduce(function (a, b) { return a + b; }, 0)) + ": " + j.runners.map(function (r, n) { return r[0] + " " + p[n]; }).join(", ") + "." +
        (k === 15 && j.sentence ? " " + j.sentence : "") + (k === 15 && j.reason ? " Its reason: “" + j.reason + "”." : "");
    };
    return '<section class="panel"><header class="panel-head"><h3>' + i("list-checks", "s") + "Tests, run by run</h3><span class=\"panel-note\">" + j.project + " / " + j.job +
      ', the last 16 runs</span></header><div class="panel-body"><p class="legend">' + j.runners.map(function (r) { return "<span><i></i>" + r[0] + "</span>"; }).join("") +
      '<span data-tone="' + look[1] + '">' + i(look[0], "s") + 'this run</span><span data-tone="plain">' + i("circle-check", "s") + 'the pass it is compared with</span></p><div class="bars">' +
      runs.map(function (p, k) {
        return '<button class="bar" type="button" aria-pressed="' + (k === 15) + '" data-say="' + say(p, k).replace(/"/g, "&quot;") + '" aria-label="' + (k === 15 ? "This run" : "Run " + (k + 1)) + '"' +
          (k === 15 ? ' data-tone="' + look[1] + '"' : k === 14 ? ' data-tone="plain"' : "") + ">" + p.map(function (n) { return '<i style="--n:' + (n / max).toFixed(4) + '"></i>'; }).join("") +
          (k === 15 ? i(look[0], "s") : k === 14 ? i("circle-check", "s") : "") + "</button>";
      }).join("") + '</div><p class="readout" aria-live="polite">' + say(runs[15], 15) + '</p><details class="t-table"><summary>As a table</summary><table><thead><tr><th>Run</th>' +
      j.runners.map(function (r) { return "<th>" + r[0] + "</th>"; }).join("") + "<th>Skipped</th></tr></thead><tbody><tr><td>" + j.id + "</td>" +
      j.runners.map(function (r) { return '<td class="num">' + r[1] + "</td>"; }).join("") + '<td class="num">' + j.skipped + "</td></tr><tr><td>" + j.cmp[0] + "</td>" +
      j.runners.map(function (r) { return '<td class="num">' + r[3] + "</td>"; }).join("") + '<td class="num">' + j.skipped + "</td></tr></tbody></table></details></div></section>";
  }
  function count(j) {
    var look = LOOK[j.verdict];
    return '<span class="t-count" data-tone="' + look[1] + '">' + i(look[0], "s") + '<span class="num">' + j.ran + '</span><span class="w">tests, ' + j.skipped + " skipped</span></span>";
  }

  // <div data-page="b">: the page of the job that failed for fewer tests.
  document.querySelectorAll("[data-page]").forEach(function (box) {
    var opt = box.getAttribute("data-page"), j = by("fewer");
    var mark = function (text) { return opt === "a" ? text : "<mark>" + text + "</mark>"; };
    box.innerHTML = '<div class="jp"><a class="crumb" href="index.html">' + i("arrow-left") + 'Back to the queue</a><header class="jp-head"><div class="jp-title">' + state(j, opt, true) +
      "<h1>example-app <span>/</span> check</h1></div>" +
      '<p class="jp-say" role="status">' + (opt === "a" ? j.result : opt === "c" ? j.sentence + " Finished, exit 8, ended 14:07:31." : "Finished, exit 8, ended 14:07:31") + "</p>" +
      '<p class="meta"><span class="branch">' + i("git-branch", "s") + "<span>" + j.branch + '</span></span><span class="job-id">' + j.id + "</span><span>" + i("laptop", "s") + "macOS</span><span>" +
      i("server", "s") + 'build-1</span><span class="num">started 14:03:42</span>' + (opt === "a" ? count(j) : "") + "</p></header>" + (opt === "b" ? strip(j) : "") +
      '<div class="jp-split"><div class="jp-left"><p class="as-today">Stages, as today.</p>' + (opt === "b" ? panel(j) : opt === "c" ? chart(j) : "") + "</div>" +
      '<section class="panel"><header class="panel-head"><h3>Log</h3><span class="panel-note">ended 14:07:31</span></header><div class="panel-body">' +
      '<pre class="log">$ pytest -q &amp;&amp; pnpm vitest run\n........................................ [100%]\n' + mark("3462 passed, 5 skipped in 212.40s") +
      "\n\n RUN  v3.2.4 /job/example-app\n Test Files  24 passed (24)\n      " + mark("Tests  213 passed (213)") + "\n\nmulebox: the command passed (exit 0)\nmulebox: pytest ran 3462 tests, the last pass ran 3470\n" +
      "mulebox: 8 fewer tests than 01JCX3B2: failed, exit 8</pre></div></section></div>" + (opt === "a" ? facts(j) : '<p class="as-today">Job details, as today.</p>') + "</div>";
  });

  // <div data-bits="b">: the same part of the page in the other situations.
  document.querySelectorAll("[data-bits]").forEach(function (box) {
    var opt = box.getAttribute("data-bits");
    box.innerHTML = JOBS.filter(function (j) { return j.key !== "fewer"; }).map(function (j) {
      var body = !j.verdict ? '<p class="none">No runner summary in its log, or <code>tests: false</code>: the page is as today, with nothing about tests.</p>'
        : opt === "a" ? '<p class="jp-say">' + j.result + '</p><p class="meta">' + count(j) + "</p>" + facts(j)
        : opt === "b" ? strip(j) + panel(j) : state(j, opt, true) + (j.sentence ? '<p class="jp-say">' + j.sentence + "</p>" : "") + chart(j);
      return '<figure class="v-fig"><figcaption>' + j.cap + '</figcaption><div class="bit">' + body + "</div></figure>";
    }).join("");
  });

  // Tabs filter the rows under them; a count opens its sentence on a tap; a bar says its run.
  document.addEventListener("click", function (event) {
    var tab = event.target.closest("[data-tab]"), tip = event.target.closest("[data-tip]"), bar = event.target.closest(".bar");
    if (tab) {
      tab.parentNode.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-selected", String(b === tab)); });
      tab.closest(".panel-body").querySelectorAll(".d-row").forEach(function (r) { r.hidden = tab.getAttribute("data-tab") !== "all" && r.getAttribute("data-in") !== tab.getAttribute("data-tab"); });
    }
    if (tip) {
      var on = tip.closest(".d-row").classList.toggle("tip-open");
      tip.setAttribute("aria-expanded", String(on));
    }
    if (bar) show(bar, true);
  });
  function show(bar, keep) {
    var chartEl = bar.closest(".panel-body");
    if (keep) chartEl.querySelectorAll(".bar").forEach(function (b) { b.setAttribute("aria-pressed", String(b === bar)); });
    chartEl.querySelector(".readout").innerHTML = bar.getAttribute("data-say");
  }
  document.addEventListener("mouseover", function (event) { var bar = event.target.closest && event.target.closest(".bar"); if (bar) show(bar, false); });
  document.addEventListener("mouseout", function (event) {
    var bar = event.target.closest && event.target.closest(".bar");
    if (bar) show(bar.parentNode.querySelector('[aria-pressed="true"]'), false);
  });
  document.addEventListener("focusin", function (event) { var bar = event.target.closest && event.target.closest(".bar"); if (bar) show(bar, false); });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") document.querySelectorAll(".tip-open").forEach(function (el) { el.classList.remove("tip-open"); });
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
