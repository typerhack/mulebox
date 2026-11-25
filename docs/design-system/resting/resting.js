// The "a node that rests" mockups of 2026-11-25 (M23.5). Loaded before ../storage/storage.js
// and ../mockups-2026-11-13.js, which draw the other icons and switch the theme. This file
// holds the three example nodes and their problems once, draws each option's Machines box,
// Machines page, waiting lane, strip and Health window from them, and answers the few clicks.
// Nothing is saved or sent anywhere.
// Icons: Lucide (ISC), outline.
(function () {
  "use strict";
  var ICONS = {
    "bed": "<path d=\"M2 4v16\"/><path d=\"M2 8h18a2 2 0 0 1 2 2v10\"/><path d=\"M2 17h20\"/><path d=\"M6 8v9\"/>",
    "stethoscope": "<path d=\"M11 2v2\"/><path d=\"M5 2v2\"/><path d=\"M5 3H4a2 2 0 0 0-2 2v4a6 6 0 0 0 12 0V5a2 2 0 0 0-2-2h-1\"/><path d=\"M8 15a6 6 0 0 0 12 0v-3\"/><circle cx=\"20\" cy=\"10\" r=\"2\"/>",
    "circle": "<circle cx=\"12\" cy=\"12\" r=\"10\"/>",
    "eye": "<path d=\"M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0\"/><circle cx=\"12\" cy=\"12\" r=\"3\"/>",
    "terminal": "<path d=\"M12 19h8\"/><path d=\"m4 17 6-6-6-6\"/>",
    "container": "<path d=\"M22 7.7c0-.6-.4-1.2-.8-1.5l-6.3-3.9a1.72 1.72 0 0 0-1.7 0l-10.3 6c-.5.2-.9.8-.9 1.4v6.6c0 .5.4 1.2.8 1.5l6.3 3.9a1.72 1.72 0 0 0 1.7 0l10.3-6c.5-.3.9-1 .9-1.5Z\"/><path d=\"M10 21.9V14L2.1 9.1\"/><path d=\"m10 14 11.9-6.9\"/><path d=\"M14 19.8v-8.1\"/><path d=\"M18 17.5V9.4\"/>"
  };

  // The API's `health` of each node, as docs/design.md gives it, with the few words the page
  // adds: a short name per check (`short`), and the times as a clock and a length.
  var DISK = { check: "disk", icon: "hard-drive", name: "Disk space", short: "Low disk", fact: "1.2 GB free", since: "10:42", length: "18m",
    message: "1.2 GB free on the disk of its cache folder, under its min_free of 5.0 GB",
    fix: "Free space on build-1: `mulebox storage clean` removes what its rules allow, `mulebox project clean` lists more; `docker system df` shows Docker's." };
  var DOCKER = { check: "docker", icon: "container", name: "Docker", short: "No Docker", fact: "does not answer", since: "10:58", length: "2m",
    message: "Docker does not answer (Cannot connect to the Docker daemon at unix:///var/run/docker.sock)",
    fix: "Start Docker: `sudo systemctl start docker` on build-2. Jobs without Docker still run there." };
  var NODES = {
    "build-1": { name: "build-1", host: true, state: "resting", cpu: 4, mem: 31, slots: 2, used: 0, seen: "3 s ago", version: "1.41.1",
      offers: ["linux", "docker", "compose-v1", "isolated"], withheld: [], problem: DISK, level: "danger",
      head: "build-1 is resting", lead: "It takes no job since 10:42. 2 jobs wait for it; GitHub runs it already holds go on." },
    "build-2": { name: "build-2", state: "idle", word: "Working", cpu: 38, mem: 44, slots: 2, used: 1, seen: "1 s ago", version: "1.41.1",
      offers: ["linux", "docker", "compose-v1", "isolated"], withheld: ["docker", "compose-v1", "isolated"], problem: DOCKER, level: "warn",
      head: "build-2 takes no Docker jobs", lead: "Since 10:58. Jobs that need no Docker still run here." },
    "mac-1": { name: "mac-1", state: "idle", word: "Idle", cpu: 6, mem: 52, slots: 2, used: 0, seen: "2 s ago", version: "1.41.1",
      offers: ["macos", "xcode", "simulator"], withheld: [] }
  };
  var ALL = ["build-1", "build-2", "mac-1"];
  var seq = 0;
  // ?show=machines shows one section alone, without the page's head (for screenshots).
  var show = /[?&]show=([a-z]+)/.exec(location.search);
  if (show) document.querySelectorAll(".doc > header, .case:not(#" + show[1] + "), .notes, .foot").forEach(function (el) { el.hidden = true; });

  function i(name, cls) { return '<i data-i="' + name + '"' + (cls ? ' class="' + cls + '"' : "") + "></i>"; }
  function code(text) { return text.replace(/`([^`]+)`/g, "<code>$1</code>"); }
  function tone(n) { return n.state === "resting" ? "bed" : "triangle-alert"; }

  // A node's state, as web/src/ui/Status.tsx draws one: the colour on the icon only.
  function state(n, words) {
    var resting = n.state === "resting", word = resting ? "Resting" : n.word;
    return '<span class="st" data-state="' + (resting ? "resting" : "queued") + '"' + (words ? "" : ' role="img" aria-label="' + word + '" title="' +
      (resting ? "Resting: takes no job until its check passes" : word) + '"') + ">" + i(resting ? "bed" : "circle") + (words ? "<span>" + word + "</span>" : "") + "</span>";
  }
  function slots(n, words) {
    var boxes = "";
    for (var k = 0; k < n.slots; k++) boxes += '<i' + (k < n.used ? ' class="busy"' : "") + "></i>";
    var text = n.state === "resting" ? "takes no job" : (n.slots - n.used) + " of " + n.slots + " slots free";
    return '<span class="slots"><span class="slot-boxes" role="img" aria-label="' + text + '">' + boxes + "</span>" + (words ? '<span class="num">' + text + "</span>" : "") + "</span>";
  }
  function controls(n) {
    return '<button class="icon-btn" type="button" aria-label="Pause ' + n.name + '" title="Take no new jobs here; what runs finishes">' + i("pause", "s") + "</button>" +
      '<button class="icon-btn" type="button" aria-label="Settings of ' + n.name + '" title="Node settings">' + i("settings-2", "s") + "</button>";
  }
  function offers(n, word) {
    return '<p class="tags offers">' + (word ? '<span class="sm t2">Offers</span>' : "") + n.offers.map(function (name) {
      var off = n.withheld.indexOf(name) >= 0;
      return '<code class="tag' + (off ? " off" : "") + '"' + (off ? ' title="Withheld: ' + n.problem.short + '"' : "") + ">" + name + "</code>";
    }).join("") + "</p>";
  }
  function name(n) {
    return "<strong>" + n.name + "</strong>" + (n.host ? '<span class="mark" role="img" aria-label="Dashboard host" title="Dashboard host">' + i("house", "s") + "</span>" : "");
  }
  // What is wrong and what to do: the node's own two sentences.
  function prob(n) {
    return '<div class="h-prob"><p><b>' + n.problem.message + '.</b></p><p class="h-fix">' + code(n.problem.fix) + "</p></div>";
  }
  function check(n, extra, quiet) {
    return '<span class="h-acts"><button class="btn" type="button" data-check>' + i("stethoscope", "s") + "Check now</button>" + (extra || "") +
      '<span class="h-when num" role="status">' + (quiet ? "" : "checked 20 s ago, again in 40 s") + "</span></span>";
  }
  function pop(n, id, open) {
    return '<section class="float pop h-pop" role="dialog" aria-label="' + n.head + '" id="' + id + '"' + (open ? "" : " hidden") + '><header class="float-head"><h3 data-level="' + n.level + '">' +
      i(tone(n)) + n.head + '</h3><button class="icon-btn bare" type="button" data-close aria-label="Close">' + i("x", "s") + '</button></header><div class="float-body"><p class="sm t2">' + n.lead + "</p>" +
      prob(n) + '</div><footer class="float-foot">' + check(n, '<a class="btn ghost" href="#window">All checks</a>') + "</footer></section>";
  }
  function line(n, id, open, href) {   // option A: icon, two words, one figure
    var p = n.problem, inner = i(p.icon, "s") + "<b>" + p.short + '</b><span class="num">' + p.fact + '</span><span class="when num">' + p.length + "</span>";
    return href ? '<a class="h-line" data-level="' + n.level + '" href="' + href + '">' + inner + i("chevron-right", "s chev") + "</a>"
      : '<button class="h-line" type="button" data-level="' + n.level + '" aria-expanded="' + open + '" aria-controls="' + id + '">' + inner + i("chevron-down", "s chev") + "</button>";
  }
  function markButton(n, id, open) {   // option C: the mark that opens the popover
    return '<button class="icon-btn bare h-mark" type="button" data-level="' + n.level + '" aria-haspopup="dialog" aria-expanded="' + open + '" aria-controls="' + id +
      '" aria-label="' + n.head + ': why, and the fix">' + i(tone(n)) + "</button>";
  }
  function warnMark(n) {   // option B: a mark beside the name, like the out-of-step one
    return n.problem && n.state !== "resting" ? '<span class="mark h-warn" role="img" aria-label="' + n.problem.short + '" title="' + n.head + ': see the strip">' + i("triangle-alert", "s") + "</span>" : "";
  }

  // The Machines box with three nodes or more: one line a node (MachinesBox.tsx, SlimRow).
  function slim(n, o, open) {
    var id = "h" + (++seq), sick = !!n.problem, lead = state(n), after = "", under = "";
    if (sick && o === "a") under = line(n, id, false, "#machines");
    if (sick && o === "b") after = warnMark(n);
    if (sick && o === "c") {
      if (n.state === "resting") lead = markButton(n, id, open); else after = markButton(n, id, open);
      under = pop(n, id, open);
    }
    return '<div class="m-slim">' + '<span class="m-id">' + lead + name(n) + after + '</span><span class="m-ctl">' + slots(n, false) + controls(n) + "</span>" + under + "</div>";
  }
  // With one or two nodes: a full row each (FullRow).
  function full(n, o, open) {
    var id = "h" + (++seq), sick = !!n.problem, st = state(n, true), under = "";
    if (sick && o === "a") under = '<div class="h-box">' + line(n, id, open) + '<div class="h-more" id="' + id + '"' + (open ? "" : " hidden") + ">" + prob(n) + check(n) + "</div></div>";
    if (sick && o === "c") {
      st = (n.state === "resting" ? "" : state(n)) + '<button class="h-state" type="button" aria-haspopup="dialog" aria-expanded="' + open + '" aria-controls="' + id + '">' +
        (n.state === "resting" ? state(n, true) : '<span class="st" data-state="warning">' + i("triangle-alert") + "<span>" + n.problem.short + "</span></span>") + i("chevron-down", "s chev") + "</button>";
      under = pop(n, id, open);
    }
    if (sick && o === "b" && n.state !== "resting") st = state(n) + '<span class="st" data-state="warning" title="See the strip">' + i("triangle-alert") + "<span>" + n.problem.short + "</span></span>";
    return '<div class="machine"><div class="row apart"><span class="row tight m-id">' + name(n) + '</span><span class="row tight">' + st + controls(n) + "</span></div>" +
      (o === "a" ? under : "") +
      '<div class="labels-4 stack"><div class="meter-row"><span>CPU</span><span class="meter" style="--v:' + n.cpu + '%"><i></i></span><span class="num">' + n.cpu + "%</span></div>" +
      '<div class="meter-row"><span>Mem</span><span class="meter" style="--v:' + n.mem + '%"><i></i></span><span class="num">' + n.mem + "%</span></div></div>" +
      '<div class="row apart sm t2">' + slots(n, true) + "</div>" + offers(n, true) + (o === "c" ? under : "") + "</div>";
  }
  document.querySelectorAll("[data-box]").forEach(function (box) {
    var o = box.getAttribute("data-box"), rows = (box.getAttribute("data-nodes") || ALL.join()).split(","), open = box.getAttribute("data-open");
    var isFull = box.getAttribute("data-rows") === "full";
    var body = rows.map(function (key) { return (isFull ? full : slim)(NODES[key], o, key === open); }).join("");
    box.innerHTML = '<section class="panel m-box"><header class="panel-head"><h3>' + i("server", "s") + 'Machines</h3><span class="panel-note num">' +
      (isFull ? "2 of 2 online, 1 slot free" : "3 of 3 online, 3 slots free") + '</span></header><div class="panel-body">' +
      (isFull ? body : '<div class="m-list">' + body + '</div><a class="m-all" href="#machines"><span>All 3 machines</span>' + i("chevron-right", "s") + "</a>") + "</div></section>";
  });

  // The Machines page (MachinesPage.tsx), without its Network and Version columns.
  document.querySelectorAll("[data-mpage]").forEach(function (box) {
    var o = box.getAttribute("data-mpage"), open = box.getAttribute("data-open");
    var heads = ["Name", "State", "CPU", "Memory", "Slots", "Offers"].concat(o === "c" ? ["Health"] : [], ["Last seen"]);
    var rows = ALL.map(function (key) {
      var n = NODES[key], sick = !!n.problem, id = "h" + (++seq), st = state(n, true), health = "";
      if (sick && o === "b" && n.state !== "resting") st += warnMark(n);
      if (o === "c") {
        health = '<td data-label="Health" class="pop-cell">' + (sick
          ? '<button class="h-state" type="button" aria-haspopup="dialog" aria-expanded="' + (key === open) + '" aria-controls="' + id + '"><span class="st" data-state="' +
            (n.level === "danger" ? "resting" : "warning") + '">' + i(n.level === "danger" ? "octagon-alert" : "triangle-alert") + "<span>" + n.problem.short + "</span></span>" + i("chevron-down", "s chev") + "</button>" + pop(n, id, key === open)
          : '<span class="st" data-state="passed">' + i("circle-check") + "<span>All pass</span></span>") + "</td>";
      }
      var reading = function (label, v) { return '<td data-label="' + label + '"><span class="reading"><span class="meter" style="--v:' + v + '%"><i></i></span><span class="num">' + v + "%</span></span></td>"; };
      return '<tr class="' + (sick && o === "a" ? "has-sub" : "") + '"><td class="wide"><span class="row tight m-id">' + name(n) + (n.host ? '<span class="sm t2">Dashboard host</span>' : "") + "</span></td>" +
        '<td data-label="State"><span class="m-state">' + st + "</span></td>" + reading("CPU", n.cpu) + reading("Memory", n.mem) +
        '<td data-label="Slots">' + slots(n, true) + '</td><td data-label="Offers" class="wide">' + offers(n) + "</td>" + health +
        '<td data-label="Last seen" class="num">' + n.seen + '</td><td class="wide end"><span class="m-ctl"><button class="icon-btn" type="button" aria-label="Show ' + n.name +
        ' in CPU, Memory and Disk">' + i("eye", "s") + "</button>" + controls(n) + "</span></td></tr>" +
        (sick && o === "a" ? '<tr class="h-sub"><td class="wide" colspan="8"><div class="h-under" data-level="' + n.level + '">' + i(tone(n)) + '<div class="stack">' + prob(n) +
          check(n, '<span class="h-when num">since ' + n.problem.since + "</span>") + "</div></div></td></tr>" : "");
    }).join("");
    box.innerHTML = '<section class="panel m-page"><header class="panel-head strong"><h3>All machines</h3></header><div class="panel-body"><table class="m-table"><thead><tr>' +
      heads.map(function (h) { return '<th scope="col">' + h + "</th>"; }).join("") + '<th scope="col" class="end"><span class="sr">Actions</span></th></tr></thead><tbody>' + rows + "</tbody></table></div></section>";
  });

  // The Jobs box: the lane of the resting node, with the two jobs that wait for it.
  var JOBS = [
    { pos: 1, project: "example-app", job: "check", branch: "feature/login-form", os: "macOS", wait: "6m 12s" },
    { pos: 2, project: "example-shop", job: "integration", branch: "fix/cart-total", os: "Linux", wait: "19m 40s", again: true }
  ];
  document.querySelectorAll("[data-lane]").forEach(function (box) {
    var o = box.getAttribute("data-lane"), open = box.getAttribute("data-open"), n = NODES["build-1"];
    var rows = JOBS.map(function (job) {
      var id = "h" + (++seq), isOpen = String(job.pos) === open, why = "", side = "", under = "";
      var again = job.again ? '<span class="src" title="build-1 could not set this job up at 10:41, so it went back in line. This happens once.">' + i("repeat", "s") + "back in line once</span>" : "";
      if (o === "a") {
        why = '<div class="why" data-level="danger"><button class="h-line" type="button" data-level="danger" aria-expanded="' + isOpen + '" aria-controls="' + id + '">' + i("bed", "s") +
          '<span class="why-text"><b>build-1 is resting:</b> ' + n.problem.message + " (since " + n.problem.since + ")</span>" + i("chevron-down", "s chev") + "</button>" +
          '<div class="h-more" id="' + id + '"' + (isOpen ? "" : " hidden") + '><p class="h-fix">' + code(n.problem.fix) + "</p>" + check(n, "", true) + "</div></div>";
      } else if (o === "b") {
        why = '<a class="why-short" data-level="danger" href="#strip">' + i("bed", "s") + "<span>build-1 is resting: low disk</span></a>";
      } else {
        why = '<span class="src">waits for build-1</span>';
        side = markButton(n, id, isOpen);
        under = pop(n, id, isOpen);
      }
      return '<li class="wait-row"><span class="pos" aria-label="Position ' + job.pos + '">' + job.pos + '</span><div class="wait-main"><a class="job-name" href="#">' + job.project + " <span>/</span> " + job.job +
        '</a><span class="branch">' + i("git-branch", "s") + "<span>" + job.branch + '</span></span><span class="src">' + i("laptop", "s") + job.os + "</span>" + again + why + "</div>" +
        '<div class="wait-side">' + side + '<span class="wait-time num">waiting ' + job.wait + '</span><span class="moves"><button class="icon-btn" type="button" aria-label="Move up"' + (job.pos === 1 ? " disabled" : "") + ">" +
        i("chevron-up", "s") + '</button><button class="icon-btn" type="button" aria-label="Move down"' + (job.pos === 2 ? " disabled" : "") + ">" + i("chevron-down", "s") +
        '</button></span><button class="icon-btn bare" type="button" aria-label="Job actions">' + i("ellipsis") + "</button></div>" + under + "</li>";
    }).join("");
    box.innerHTML = '<section class="panel"><header class="panel-head strong"><h3>Jobs</h3><span class="panel-note num">1 running, 2 waiting</span></header><div class="panel-body gap">' +
      '<div class="lane-head"><strong>build-1</strong>' + state(n, true) + '<span class="lane-note">takes no job, 2 waiting</span></div><ol class="waits" aria-label="Waiting for build-1">' + rows + "</ol></div></section>";
  });

  // Option B: the strip above the panels, a line a node, the worst level's colour.
  function stripLine(n, says, extra) {
    return '<li data-level="' + n.level + '">' + i(n.level === "danger" ? "octagon-alert" : "triangle-alert") + '<p><b>' + says + " " + n.problem.message + ".</b> <span>" + code(n.problem.fix) +
      " Since " + n.problem.since + ".</span></p>" + check(n, extra, true) + "</li>";
  }
  document.querySelectorAll("[data-hstrip]").forEach(function (box) {
    box.innerHTML = '<section class="strip danger h-strip" id="strip" role="status" aria-label="Nodes that need you" tabindex="-1"><ul>' +
      stripLine(NODES["build-1"], "build-1 is resting and takes no job:", '<a class="btn" href="#">' + i("hard-drive", "s") + "Open Storage</a>") +
      (box.getAttribute("data-hstrip") === "one" ? "" : stripLine(NODES["build-2"], "build-2 takes no Docker jobs:")) + "</ul></section>";
  });
  // The warning that comes long before a rest; the same in every option.
  document.querySelectorAll("[data-warnstrip]").forEach(function (box) {
    box.innerHTML = '<section class="strip h-strip" role="status" aria-label="Low disk space"><ul><li data-level="warn">' + i("triangle-alert") +
      "<p><b>mac-1 has 21 GB free of 250 GB, under 10%.</b> <span>Its cleanup ran at 10:31 and freed 3.2 GB. Under 5.0 GB it rests and takes no job.</span></p>" +
      '<span class="h-acts"><a class="btn" href="#">' + i("hard-drive", "s") + "Open Storage</a></span></li></ul></section>";
  });

  // Option C: the Health tab of the node's settings window: every check, and min_free.
  var CHECKS = [
    { p: DISK }, { icon: "folder", name: "Folders", says: "its four folders can be written" }, { icon: "git-branch", name: "git", says: "runs" },
    { icon: "terminal", name: "Job runner", says: "systemd's user manager answers" }, { icon: "container", name: "Docker", says: "answers" },
    { icon: "repeat", name: "Starts", says: "no jobs in a row that could not start" }
  ];
  document.querySelectorAll("[data-hwin]").forEach(function (box) {
    var n = NODES["build-1"];
    box.innerHTML = '<section class="float win h-win" role="dialog" aria-label="Settings of build-1"><header class="float-head"><div><h3>' + i("server") + 'build-1</h3><p class="sm t2">Node settings, dashboard host</p></div>' +
      '<button class="icon-btn bare" type="button" aria-label="Close" title="Close">' + i("x") + '</button></header><div class="float-body gap">' +
      '<div class="tabs" role="tablist"><button type="button" role="tab" aria-selected="false">Jobs</button><button type="button" role="tab" aria-selected="false">Storage</button>' +
      '<button type="button" role="tab" aria-selected="true">Health<span class="st" data-state="resting">' + i("octagon-alert", "s") + "</span></button></div>" +
      '<div class="h-sum"><p class="st big" data-state="resting">' + i("bed", "l") + "<span>Resting since 10:42</span></p><p class=\"t2\">One check of six fails, so build-1 takes no job. It checks again every minute and takes jobs as soon as all pass.</p>" + check(n) + "</div>" +
      '<ul class="h-checks" aria-label="The checks of build-1">' + CHECKS.map(function (c) {
        return c.p ? '<li class="fails">' + i("octagon-alert") + "<b>" + c.p.name + '</b><span class="num">fails since ' + c.p.since + "</span>" + prob(n) + "</li>"
          : "<li>" + i("circle-check") + "<b>" + c.name + '</b><span class="t2">' + c.says + "</span></li>";
      }).join("") + "</ul>" +
      '<div class="field"><span class="field-name">Least free space</span><span class="row"><span class="stepper" role="group" aria-label="Least free space in GB"><button type="button" aria-label="Less">' + i("minus", "s") +
      '</button><output>5</output><button type="button" aria-label="More">' + i("plus", "s") + '</button></span><span class="num">GB</span><span class="sm t2">the default</span></span>' +
      '<p class="field-hint">Under this, build-1 rests: a job needs room to check out and install. You are warned long before, under 10% free (49 GB of this node\'s 490 GB), and its cleanup runs then.</p></div>' +
      '</div><footer class="float-foot"><p>Checks are read from the node; only the free space is a setting.</p><button class="btn" type="button">Close</button><button class="btn primary" type="button" disabled>Save</button></footer></section>';
  });

  // A click opens and closes what a button controls; "Check now" answers after a moment.
  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[aria-controls]"), close = event.target.closest("[data-close]"), ask = event.target.closest("[data-check]");
    if (close) opener = document.querySelector('[aria-controls="' + close.closest("[id]").id + '"]');
    if (opener && opener.hasAttribute("aria-expanded")) {
      var show = opener.getAttribute("aria-expanded") !== "true";
      opener.setAttribute("aria-expanded", String(show));
      document.getElementById(opener.getAttribute("aria-controls")).hidden = !show;
      window.dispatchEvent(new Event("resize"));   // the shared script then makes room for it
    }
    if (ask && !ask.disabled) {
      var when = ask.parentNode.querySelector(".h-when[role=status]"), label = ask.lastChild;
      ask.disabled = true;
      label.textContent = "Checking";
      setTimeout(function () {
        ask.disabled = false;
        label.textContent = "Check now";
        if (when) when.textContent = "checked just now: still failing";
      }, 1400);
    }
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
