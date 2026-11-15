// The "looks stuck" mockups of 2026-11-15. Loaded before ../storage/storage.js and
// ../mockups-2026-11-13.js, which draw the other icons and switch the theme. This file holds
// the example jobs and their verdicts once, draws each option's cards and job page from them,
// and opens what a click would open. Nothing is saved or sent anywhere.
// Icons: Lucide (ISC), outline.
(function () {
  "use strict";
  var ICONS = {
    "snail": "<path d=\"M2 13a6 6 0 1 0 12 0 4 4 0 1 0-8 0 2 2 0 0 0 4 0\"/><circle cx=\"10\" cy=\"13\" r=\"8\"/><path d=\"M2 21h12c4.4 0 8-3.6 8-8V7a2 2 0 1 0-4 0v6\"/><path d=\"M18 3 19.1 5.2\"/><path d=\"M22 3 20.9 5.2\"/>",
    "text-cursor-input": "<path d=\"M12 20h-1a2 2 0 0 1-2-2 2 2 0 0 1-2 2H6\"/><path d=\"M13 8h7a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-7\"/><path d=\"M5 16H4a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h1\"/><path d=\"M6 4h1a2 2 0 0 1 2 2 2 2 0 0 1 2-2h1\"/><path d=\"M9 6v12\"/>",
    "scroll-text": "<path d=\"M15 12h-5\"/><path d=\"M15 8h-5\"/><path d=\"M19 17V5a2 2 0 0 0-2-2H4\"/><path d=\"M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3\"/>",
    "cpu": "<path d=\"M12 20v2\"/><path d=\"M12 2v2\"/><path d=\"M17 20v2\"/><path d=\"M17 2v2\"/><path d=\"M2 12h2\"/><path d=\"M2 17h2\"/><path d=\"M2 7h2\"/><path d=\"M20 12h2\"/><path d=\"M20 17h2\"/><path d=\"M20 7h2\"/><path d=\"M7 20v2\"/><path d=\"M7 2v2\"/><rect x=\"4\" y=\"4\" width=\"16\" height=\"16\" rx=\"2\"/><rect x=\"8\" y=\"8\" width=\"8\" height=\"8\" rx=\"1\"/>",
    "terminal": "<path d=\"M12 19h8\"/><path d=\"m4 17 6-6-6-6\"/>",
    "arrow-down-up": "<path d=\"m3 16 4 4 4-4\"/><path d=\"M7 20V4\"/><path d=\"m21 8-4-4-4 4\"/><path d=\"M17 4v16\"/>",
    "container": "<path d=\"M22 7.7c0-.6-.4-1.2-.8-1.5l-6.3-3.9a1.72 1.72 0 0 0-1.7 0l-10.3 6c-.5.2-.9.8-.9 1.4v6.6c0 .5.4 1.2.8 1.5l6.3 3.9a1.72 1.72 0 0 0 1.7 0l10.3-6c.5-.3.9-1 .9-1.5Z\"/><path d=\"M10 21.9V14L2.1 9.1\"/><path d=\"m10 14 11.9-6.9\"/><path d=\"M14 19.8v-8.1\"/><path d=\"M18 17.5V9.4\"/>"
  };
  var root = document.documentElement;
  // ?theme=light or ?theme=dark opens the page in that theme (for screenshots).
  var asked = /[?&]theme=(light|dark)/.exec(location.search);
  if (asked) root.setAttribute("data-theme", asked[1]);

  // The four verdicts that show. `says` is the server's own sentence; `rows` is its evidence
  // (name, icon, value, whether it moved).
  var V = {
    slow: { icon: "snail", level: "warn", label: "Slow download", fact: "12.0 KB/s",
      says: "Downloading slowly: 12 KB/s, 41 MB of 300 MB of node-v22.tar.xz. Nothing else has moved for 3m.",
      rows: [["Download", "download", "12.0 KB/s, 41.0 MB of 300.0 MB", 1], ["Output", "terminal", "none for 3m", 0],
             ["Its CPU", "cpu", "0.0 cores for 3m", 0], ["Stage", "timer", "toolchain", 0]] },
    waiting: { icon: "hourglass", level: "info", label: "Waiting on purpose", fact: "quiet 4m",
      says: "Quiet for 4m, but its last line says it is waiting: \"Retrying in 60 s (attempt 3 of 5)\".",
      rows: [["Output", "terminal", "none for 4m", 0], ["Its CPU", "cpu", "0.0 cores for 4m", 0], ["Its I/O", "arrow-down-up", "0 B for 4m", 0],
             ["Services", "container", "redis: idle, no traffic", 0], ["Last line", "scroll-text", "Retrying in 60 s (attempt 3 of 5)", 2]] },
    asking: { icon: "text-cursor-input", level: "danger", label: "Asks for input", fact: "2m 30s",
      says: "Waiting for an answer it will never get, for 2m 30s: \"Overwrite existing files? [y/N]\". Cancel it and make the command non-interactive.",
      rows: [["Output", "terminal", "none for 2m 30s", 0], ["Its CPU", "cpu", "0.0 cores for 2m 30s", 0], ["Its I/O", "arrow-down-up", "0 B for 2m 30s", 0],
             ["Last line", "scroll-text", "Overwrite existing files? [y/N]", 2]] },
    stuck: { icon: "octagon-alert", level: "danger", label: "Looks stuck", fact: "quiet 5m 10s",
      says: "Looks stuck: no output, no CPU, no I/O for 5m 10s in stage command. Last line: \"Running migrations...\". Look at its log or cancel it.",
      rows: [["Output", "terminal", "none for 5m 10s", 0], ["Its CPU", "cpu", "0.0 cores for 5m 10s", 0], ["Its I/O", "arrow-down-up", "0 B for 5m 10s", 0],
             ["Services", "container", "postgres: idle, no traffic", 0], ["Stage", "timer", "command", 0], ["Last line", "scroll-text", "Running migrations...", 2]] }
  };
  var JOBS = [
    { key: "working", says: "working: nothing is shown", project: "example-app", job: "check", branch: "feature/login-form", id: "01JCX4M7", os: "macOS", stage: "command", time: "2m 14s", usual: "4m", cores: "3.2", pct: 40 },
    { key: "slow", says: "slow: a warning", project: "example-shop", job: "check", branch: "fix/cart-total", id: "01JCX4Q9", os: "Linux", stage: "toolchain", time: "6m 02s", usual: "3m", cores: "0.0", pct: 0, down: 1 },
    { key: "waiting", says: "waiting: for information", project: "example-api", job: "integration", branch: "main", id: "01JCX4R2", os: "macOS", stage: "command", time: "9m 41s", usual: "12m", cores: "0.0", pct: 0 },
    { key: "asking", says: "asking: it cannot go on", project: "example-site", job: "build", branch: "chore/scaffold", id: "01JCX4T5", os: "Linux", stage: "setup", time: "2m 52s", usual: "1m", cores: "0.0", pct: 0 },
    { key: "stuck", says: "stuck: it will not go on", project: "example-app", job: "migrate", branch: "feature/orders-table", id: "01JCX4V8", os: "macOS", stage: "command", time: "5m 31s", usual: "40s", cores: "0.0", pct: 0 }
  ];
  var seq = 0;
  function i(name, cls) { return '<i data-i="' + name + '"' + (cls ? ' class="' + cls + '"' : "") + "></i>"; }
  function ways() {
    return '<a class="btn" href="#page">' + i("scroll-text", "s") + 'Open its log</a><button class="btn" type="button">' + i("ban", "s") + "Cancel job</button>";
  }
  function facts(v) {
    return '<dl class="v-facts">' + v.rows.map(function (r) {
      return "<div" + (r[3] === 1 ? ' class="moved"' : "") + "><dt>" + i(r[1], "s") + r[0] + "</dt><dd>" + (r[3] === 2 ? "<code>" + r[2] + "</code>" : r[2]) +
        (r[3] === 1 ? ' <span class="t2">the only thing moving</span>' : "") + "</dd></div>";
    }).join("") + "</dl>";
  }

  // What each option adds to a card: `lead` takes the state icon's place, `mark` sits beside
  // the three dots, `over` comes last in the card (a tooltip, a line across it, a popover).
  var ADD = {
    a: function (v, id, open) {
      return { open: open ? " tip-open" : "",
        lead: '<button class="v-lead" type="button" data-level="' + v.level + '" data-tip aria-describedby="' + id + '" aria-label="Running: ' + v.label.toLowerCase() + '">' + i(v.icon, "l") + "</button>",
        over: '<span class="v-tip" role="tooltip" id="' + id + '"><b>Still running.</b> ' + v.says + "</span>" };
    },
    b: function (v, id, open) {
      return { open: " has-box", over: '<div class="v-box" data-level="' + v.level + '"><button class="v-line" type="button" aria-expanded="' + open + '" aria-controls="' + id + '">' +
        i(v.icon, "s") + "<b>" + v.label + '</b><span class="num">' + v.fact + "</span>" + i("chevron-down", "s chev") + "</button>" +
        '<div class="v-more" id="' + id + '"' + (open ? "" : " hidden") + "><p>" + v.says + '</p><span class="acts">' + ways() + "</span></div></div>" };
    },
    c: function (v, id, open) {
      return { mark: '<button class="icon-btn bare v-mark" type="button" data-level="' + v.level + '" aria-haspopup="dialog" aria-expanded="' + open + '" aria-controls="' + id +
        '" aria-label="' + v.label + ': what it is based on">' + i(v.icon) + "</button>",
        over: '<section class="float pop v-pop" role="dialog" aria-label="' + v.label + '" id="' + id + '"' + (open ? "" : " hidden") + '><header class="float-head"><h3 data-level="' + v.level + '">' +
          i(v.icon) + v.label + '</h3><button class="icon-btn bare" type="button" data-close aria-label="Close">' + i("x", "s") + '</button></header><div class="float-body"><p>' + v.says +
          '</p><h4 class="v-h">What mulebox sees of this job</h4>' + facts(v) + '</div><footer class="float-foot">' + ways() + "</footer></section>" };
    }
  };

  function card(job, opt, open) {
    var v = V[job.key], add = v ? ADD[opt](v, "v" + (++seq), open) : {};
    return '<figure class="v-fig"><figcaption>' + job.says + '</figcaption><article class="job-card' + (add.open || "") + '">' +
      (add.lead || '<span class="st" data-state="running" role="img" aria-label="Running">' + i("loader-circle", "l") + "</span>") +
      '<div class="job-main"><a class="job-name" href="#page">' + job.project + " <span>/</span> " + job.job + "</a>" +
      '<span class="meta"><span class="branch">' + i("git-branch", "s") + "<span>" + job.branch + '</span></span><span class="job-id">' + job.id + "</span></span>" +
      '<span class="meta"><span>' + i("laptop", "s") + job.os + "</span><span>" + job.stage + '</span><span class="num">' + job.time + " of usually " + job.usual + "</span></span>" +
      '<div class="meter-row"><span>Cores</span><span class="meter" style="--v:' + job.pct + '%"><i></i></span><span class="num">' + job.cores + "</span></div>" +
      (job.down ? '<div class="meter-row"><span>Down</span><span class="meter" style="--v:13.7%"><i></i></span><span class="num">41.0 of 300.0 MB</span></div>' +
        '<p class="dl-note"><span>Downloading node-v22.tar.xz</span><span class="num">12.0 KB/s</span></p>' : "") +
      '</div><div class="job-side">' + (add.mark || "") +
      '<button class="icon-btn bare" type="button" aria-label="Job actions">' + i("ellipsis") + "</button></div>" + (add.over || "") + "</article></figure>";
  }
  // <div data-cards="a" data-open="stuck" data-only="stuck,slow">: an option's cards.
  document.querySelectorAll("[data-cards]").forEach(function (box) {
    var only = box.getAttribute("data-only"), open = box.getAttribute("data-open");
    box.innerHTML = JOBS.filter(function (job) { return !only || only.split(",").indexOf(job.key) >= 0; })
      .map(function (job) { return card(job, box.getAttribute("data-cards"), job.key === open); }).join("");
  });

  // <div data-page="a">: the page of the stuck job. What an option changes is its state, the
  // notice under the header (B) and the panel beside the log (C).
  document.querySelectorAll("[data-page]").forEach(function (box) {
    var opt = box.getAttribute("data-page"), v = V.stuck;
    var running = '<span class="st big" data-state="running">' + i("loader-circle", "l") + "<span>Running</span></span>";
    var state = opt === "a" ? '<span class="st big v-word" data-level="danger">' + i(v.icon, "l") + "<span>Looks stuck</span></span>"
      : opt === "c" ? running + '<span class="st v-word" data-level="danger">' + i(v.icon) + "<span>Looks stuck</span></span>" : running;
    var notice = opt !== "b" ? "" : '<div class="strip danger v-note" role="status">' + i(v.icon) + '<div class="strip-lines"><div class="strip-line"><p><b>Looks stuck.</b> ' +
      "No output, no CPU, no I/O for 5m 10s in stage command. Last line: <code>Running migrations...</code></p>" +
      '<span class="acts"><button class="btn" type="button">' + i("chevrons-down", "s") + 'Go to its last line</button><button class="btn" type="button">' + i("ban", "s") + "Cancel job</button></span></div></div></div>";
    var left = opt === "c"
      ? '<section class="panel"><header class="panel-head"><h3>' + i(v.icon, "s") + 'What mulebox sees</h3><span class="panel-note">nothing has moved for 5m 10s</span></header><div class="panel-body">' + facts(v) +
        '<p class="sm t2 v-foot">A verdict from these readings. It stops nothing: the job runs on until it ends, is cancelled, or goes unanswered at its check-in.</p></div></section>'
      : '<p class="as-today">Stages, as today.</p>';
    box.innerHTML = '<div class="jp"><a class="crumb" href="index.html">' + i("arrow-left") + 'Back to the queue</a><header class="jp-head"><div class="jp-title">' + state +
      "<h1>example-app <span>/</span> migrate</h1></div>" +
      '<div class="jp-ctl" role="group" aria-label="Job controls"><button class="btn" type="button">' + i("snowflake", "s") + 'Freeze</button><button class="btn" type="button">' + i("zap", "s") +
      'Boost</button><button class="btn" type="button">' + i("ban", "s") + "Cancel</button></div>" +
      (opt === "a" ? '<p class="jp-say" role="status">' + v.says + "</p>" : "") +
      '<p class="meta"><span class="branch">' + i("git-branch", "s") + '<span>feature/orders-table</span></span><span class="job-id">01JCX4V8</span><span>' + i("laptop", "s") + "macOS</span><span>" +
      i("server", "s") + 'build-1</span><span class="num">started 14:02:09</span></p></header>' + notice +
      '<div class="jp-split">' + left + '<section class="panel"><header class="panel-head"><h3>Log</h3><span class="panel-note">quiet for 5m 10s</span></header><div class="panel-body">' +
      '<pre class="log">$ pnpm run migrate\n\n&gt; example-app@1.4.0 migrate\n&gt; node scripts/migrate.js\n\nConnecting to postgres at db:5432\nConnected.\n' +
      (opt === "a" ? "Running migrations..." : '<mark>Running migrations...</mark>') + "</pre>" +
      (opt === "a" ? "" : '<p class="log-end">' + i("octagon-alert", "s") + "Nothing after this line for 5m 10s</p>") + "</div></section></div></div>";
  });

  // A click opens and closes what a button controls; a tooltip also opens on a tap.
  document.addEventListener("click", function (event) {
    var tip = event.target.closest("[data-tip]"), opener = event.target.closest("[aria-controls]"), close = event.target.closest("[data-close]");
    if (tip) tip.closest(".job-card").classList.toggle("tip-open");
    if (close) opener = document.querySelector('[aria-controls="' + close.closest("[id]").id + '"]');
    if (opener && opener.hasAttribute("aria-expanded")) {
      var show = opener.getAttribute("aria-expanded") !== "true";
      opener.setAttribute("aria-expanded", String(show));
      document.getElementById(opener.getAttribute("aria-controls")).hidden = !show;
      window.dispatchEvent(new Event("resize"));   // the shared script then makes room for it
    }
  });
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
