# Interfaces: web dashboard (M2)

The contract for `mulebox/dashboard/`, `mulebox/common/status.py` and
`mulebox/client/tunnel.py`. Design goals: [design.md](design.md) (Dashboard).

## The front end (`dashboard/pages.py`, `web/`)

- **React** (M14.10): source in `web/` at the repository root ([web/README.md](../web/README.md)),
  built by `npm run build` into `mulebox/dashboard/app/` (not in git; in the wheel on
  PyPI). `/` serves `app/index.html` and its files are under `/app/`; it is the only
  front end.
- **Without a build** (a checkout nobody built), `/` and `/login` answer 503 with a short page
  that says how to get one: a release, or `npm ci` and `npm run build` in `web/`. The API and
  the event streams keep working. `mulebox setup` builds before it makes a wheel and stops,
  naming Node.js and npm, when the build is missing or stale and npm is not there
  (`client/webbuild.py`).
- **Sign-in page**: `web/login.html` with `web/src/login/login.css`, built to `app/login.html`
  and `app/login.css`, the fonts to `app/fonts/` by fixed names (`web/vite.config.ts`), so
  the LAN guard can let exactly those through. No script; the server fills in its message.
  Its theme follows the system setting.
- The code: `web/src/lib/` (lanes, menus, formats, the log's steps, the chart),
  `web/src/state/` (the stream into stores, the picked machine) and `web/src/features/` (one
  folder per view). Pages: the queue (`#/`), a job (`#/job/<id>`), history (`#/history`), statistics
  (`#/stats`) and machines (`#/machines`); the machine picked for CPU, Memory and Disk
  (`/api/metrics?machine=`, asked every 2 s while another machine than the host is picked),
  the meter style switch (Auto, Gauge, Rainbow, kept per browser as `mulebox-meters`), and a
  GitHub job's log drawn as its steps, each with its length (live while it runs) and result
  (`web/src/lib/cilog.ts` reads the lines `runners/live_log.py` writes from the runner's own
  files: `mulebox: step at <time>: <name>` as a step starts, `mulebox: step <passed|failed|
  cancelled|skipped> at <time>: <name>` as it ends, and `--- output of <name>`; logs from
  before 0.101 have `mulebox: step: <name>` with no time and a result for failed steps only).
- Every guard below covers it: these are GET routes of one app. The policy has
  `font-src 'self'` for the bundled Geist files. The build has no inline script or style,
  loads nothing from another origin, and sets styles only through the DOM, which the policy
  allows.

## Status model (`common/status.py`)

One place decides how a job is shown; the terminal view and the dashboard both use it.
Input is a public job dict; every function tolerates missing or malformed fields.

- Sections: `running` (starting, running, cleaning), `queued` (uploading, queued, by
  position) and `recent` (finished, newest first).
- Shown state: the outcome of a finished job, else its state. A finished runner
  reservation shows the GitHub job's own result (`passed`, `failed`, `cancelled`) when its
  completed hook read it from the runner (`ci_result`, docs/interfaces-m3.md). One released by
  a mulebox before 0.76.0 has no `ci_result` and, if it passed or failed, shows `released`: it
  only says the slot was given back. `interrupted` reservations keep their outcome.
- A finished job's state carries its mark in every view: a check for passed, a cross for
  failed, a warning for timed out, interrupted or stopped, a stop sign for cancelled. A failed
  GitHub job's row also says the step that failed and GitHub's message on it.
- Elapsed: waiting time when queued, running time when active, run time when finished.
- `fingerprint(jobs)`: what changes when a view must redraw. Elapsed time is left out, so a
  ticking clock never causes an event. Where a waiting job may go (below) is in, so a
  capable machine going offline redraws the queue. So is a card's activity (`doing`: stage,
  step, CPU in steps of 10% of a core): before 0.75.2 it was not, and a long job's card kept
  what it showed at its start until something else in the queue changed or the page reloaded.

## Where a waiting job may go (`coordinator/views.py` `placement`)

The dashboard's queue rows add, on waiting agent jobs only: `needs`, `can_run_on` (the
workers whose capabilities cover them, online or not: the same test `queue.claim` makes)
and `waiting_for` (needs.py, when a queued job cannot start now), and on every queued job
`branch_busy`, the job holding its branch (views.py `running_ahead`), which the row names as
`mulebox queue` does ("XFZPMD is running on this branch"). None of it is an
assignment: the queue is one line, and the first capable worker with a free slot takes the
job. A running job has its `worker`; a runner reservation its `pinned_worker`.

## Jobs box (`web/src/features/jobs/`, `web/src/lib/lanes.ts`)

Tabs, each with a live count, remembered per browser, each showing one thing: `Queue`
(default, what is happening now), `Failed` (failed, timed out or interrupted) and `Passed`
among the finished jobs the queue keeps, GitHub jobs included, and `Recent` (all of those, so
also cancelled jobs and runner slots released before 0.76.0, which are neither a pass nor a
failure). Ticking times are
keyed by job id, whatever order a tab puts them in. A viewer's first `queue` snapshot is
built when it connects, never taken from the last published event, whose elapsed times
would be stale.

`Queue` is the queue by machine: one lane per worker with its name and state, a block per
running job, and the jobs waiting for it. In the React dashboard a lane with both shows the
running blocks on the left and the line on the right, each under a heading (one column when
narrow), and a line of more than 6 shows its first 5 until "Show all waiting (N)" is pressed
(docs/design-system.md, Several machines). Slots, capabilities and readings are shown once,
in the Machines box, not here. Waiting jobs keep their real positions and appear in
exactly one place:

- a machine's lane, when it is the one place the job can run (a pinned runner
  reservation, or the only capable worker, even if that worker is offline);
- the `next free machine` list, when several machines could take it (named when not all
  of them can);
- the `no machine fits` lane, first and in the alarm colour, when no worker covers its
  needs. A job with a `waiting_for` reason shows it, wherever it sits, marked `stuck`.

With no placement fields (an older server) every waiting job goes to the shared list.

`status_ok` of a `status` request has `steps`, one row per stage, and `common/status.py` reads
them: `current_stage`, `step_duration_s`, `failed_step` ([interfaces-m4.md](interfaces-m4.md),
Job steps). `mulebox status` shows them, and the job view as a waterfall with `steps`, `usual` and `failed_stage` in its reply. A `status` reply, a
watch stream's last `status_ok` and its `result` have `stage` when a job ended badly in a known
stage (`steps.failed_stage`), and `job_event` puts it in the `finished` event.

## Statistics page (`web/src/features/stats/`, `web/src/lib/stats.ts`)

`#/stats`, under the top row like every page. Filters (type, project, source, machine) on top;
today and all time side by side, each with its split between mulebox jobs and GitHub Actions
and what is apart (runs still going, runs with no recorded length); a note that run time is
added up; the last 14 days as stacked columns; one table, by project, type, source, machine or
job name, for today or all time, the top 8 with a way to show all. Two `/api/stats` requests
per change, with this browser's own midnights; again each minute while the page is open. The
design is option A of three the user was shown on 2026-11-10.

## History page (`web/src/features/history/`, `web/src/lib/history.ts`, `dashboard/history_query.py`)

`#/history`: every finished job, newest first, 50 at a time with "Load more". A search box
("Search project, job or branch") searches about 300 ms after typing stops, or at once on
Enter; its cross or Escape clears it. Below it the dropdowns Type, Project, Source and Machine,
the Statistics page's own with its wording and labels, then Job name and Result (passed,
failed, cancelled). The values come from the `choices` of the first page, the Statistics page's
list (`coordinator/stats.py` `choices`). The filters live in the hash, such as
`#/history?project=example-app&q=main`, swapped in place (no browser history step), so a reload
or a shared link keeps them. A request a newer one replaced is ignored when it answers. With
nothing found the page says so and offers "Clear filters"; with filters set the same control
sits beside the search.

## Processes and access

- `mulebox dashboard serve` runs on the coordinator machine as the user service
  `mulebox-dashboard`. It binds `127.0.0.1`, plus `lan_address` in `lan` mode, and has no
  option to bind anything else.
- `[dashboard] mode` in `node.toml`: `local` (default) serves; `off` exits 0 at once, and
  the unit does not restart; `lan` adds the LAN listener (below). Exit 2 is a configuration
  problem, which the unit does not retry; exit 1 is a failed bind, which it does, because
  Wi-Fi can come up after the service.
- `mulebox dashboard open [--port N] [--remote-port N] [--no-browser]` on the dev machine runs
  `ssh -N -L 127.0.0.1:<local>:127.0.0.1:<remote> <coordinator>`, waits for `/healthz`,
  opens the browser and holds the tunnel until Ctrl-C (exit 0). A tunnel that closes or a
  dashboard that does not answer exits 3, the "unreachable" code. The tunnel is always its
  own ssh connection, never a shared `ControlMaster` one: ssh would otherwise hand the
  forward to the master and exit, and Ctrl-C could not close it.

## Waiting questions

Queue rows, machine rows' `jobs` and a job's detail carry `question` (`attendance.fields`:
`number`, `since`, `stop_reason`, `reason`, `stop_at`, `left_s`) only while a question is unanswered.
Every view marks it the same way (`questionMark`): a warning triangle, `needs an answer` and the
time left if the job stays stuck, which keeps moving while it works. The Queue tab adds a count,
and a job's page says what happens. The server sends `left_s` when the whole minutes change (both
fingerprints); browsers count down between (`tickLeft`). A stopped job reads `stopped: stuck`
(`shown_state`, also in history), with its reason as `stop_text` on the job's page, and stays out
of the Failed tab: it did not fail.

## Machines box (`dashboard/machines.py`, `web/src/features/top/MachinesBox.tsx`)

The panel feeds the Machines box, the lanes above and `/api/machines`.

- A row per worker in the coordinator's `workers` table: `name`, `state`, `slots`,
  `free_slots`, `capabilities`, `last_seen`, `jobs`, `cpu_pct`, `mem_pct`, `cores`,
  `net_in_kib_s`, `net_out_kib_s`, `host` (true on the row of the worker on the dashboard's own
  machine, `node.toml`'s `name`; none is when no worker runs there) and `version` (the mulebox
  the worker last reported, null before it did; a change publishes a `machines` event). Plus
  `total`, `online` and `free_slots` for the cluster.
- **Readings.** `cpu_pct` (average over the cores), `mem_pct` and `cores` are what each worker
  last reported with a claim or heartbeat (`workers.load`, M5.3), at most every 2 s; null while
  it is offline or has not reported, and then the box reads `no live data`, never a guess. The
  machine the dashboard runs on gets the hub's own finer sample on top (the row named after
  `node.toml`'s `name`). A `machines` event is published when a reading moves a whole percent.
- `state`: `offline` when not seen for 15 s, else `busy` with nothing free, else `available`.
- **Seen.** Claims stop while a worker has no free slot, so a job's heartbeats, every 3 s,
  also refresh `last_seen`. The worker lease cannot do this job: at 120 s it would keep a
  dead machine online for two minutes.
- **Free slots** are counted from the jobs holding a slot. The stored `free_slots` is what
  the worker last said in a claim, which is stale while it is busy. An offline machine
  offers none. They are job slots, not spare CPU; per-machine load is M5.3.
- A worker that is gone for good stays listed as offline until removing workers exists
  (M5.2).
- **Out of step** (`dashboard/notices.py`, `web/src/features/header/OutOfStep.tsx`): `notices`, a list of `kind`
  (`worker`, `client`, `skill`), `level` (`danger` for a worker, as jobs can fail; `warning` for
  a dev machine), `name`, `text` and `fix`, dangers first. Shown as a strip above the panels in its
  worst level's colour, and as a mark with the count in the header that brings the strip into
  view; both hidden while empty. A notice is an online worker on another mulebox than the coordinator,
  a dev machine seen in the last 14 days on another mulebox than the node, or a dev machine
  whose skill differs from its mulebox's. Dev machines say their `client_version` and `skill`
  (`current`, `out_of_date`, `none`) with every `submit`; the newest word per dev machine is kept in
  the `clients` table (schema 19, coordinator/clients.py). Dev machines older than 0.83.0 say neither
  and are not listed. Nothing is compared with a release: only installs that disagree.

## `lan` mode

Setup steps: [install.md](install.md). Modules: `lan_commands.py` (CLI, checks before
serving), `login.py` (rules and pages), `session.py`, `password.py`, `cert.py`,
`firewall.py`, `lanfiles.py`, `listeners.py`.

- **Two listeners, one app.** `127.0.0.1:<port>` for the tunnel, with no password, and
  `<lan_address>:<lan_port>`, plain HTTP unless `lan_tls` is on. `lan_port` is `port` unless set,
  so one number works on both addresses; they stay two sockets. The rules follow which
  listener the socket belongs to, never a header, and do not depend on TLS. If the socket
  address is unknown, the request counts as LAN. Forwarded-for headers are ignored.
- **Plain HTTP is a choice, not a default to fix** (user, 2026-11-04): the password and
  pages are readable by anyone who can capture the network's traffic. It suits a network
  where everyone is trusted; `lan_tls` covers the rest. A warning on every visit was
  judged worse than no encryption at home.
- **Order on the LAN listener.** Host must be `lan_address` (421), the peer must be in
  `lan_range` (403), then a session is needed. Only `/login`, its stylesheet `/app/login.css` and the
  bundled fonts under `/app/fonts/` are open without one (`login.is_public`). Pages redirect to `/login`; `/healthz` and `/api/` get 401.
- **`lan_password = false`** turns sign-in off: `/login` redirects to `/`, posts to it get
  404, and no password file is needed. The Host and range rules still apply. It defaults
  to true, and the service logs a warning when it is off.
- **Password.** scrypt hash in `dashboard/password` beside `node.toml`, mode 600. Read at
  start, so a new one needs a restart. Never an argument: `mulebox dashboard password`
  prompts, or reads one line from stdin when that is not a terminal.
- **Sessions.** In memory, as hashes, 24 h, at most 64 (oldest dropped). A restart signs
  everyone out; open pages then return to `/login` on their own. Cookie: `HttpOnly`,
  `SameSite=Strict`, and `Secure` with `lan_tls`.
- **Failed logins.** Per address: 5 free, then a wait of 30 s doubling to 15 min (429),
  even for the right password. One scrypt at a time, so logins cannot starve jobs.
- **Cross-site posts.** `SameSite=Strict` keeps the cookie off them, and `Sec-Fetch-Site`,
  sent by browsers only over HTTPS, refuses them. `Origin` cannot do this: with the
  `no-referrer` policy, browsers send `Origin: null` on a same-site form post.
- **Certificate (`lan_tls` only).** Self-signed, marked CA because phones only fully trust those, with
  `pathlen:0` and name constraints for this one address. Created with the `openssl`
  command, so there is no new Python dependency. Checked at start: exists, matches
  `lan_address`, not expired.
- **Firewall.** mulebox never runs anything as root. `mulebox dashboard firewall` prints a
  script for the operator. Its rules sit in their own table, not in `/etc/nftables.conf`,
  whose usual `flush ruleset` would remove every other tool's rules. The range check in
  the app stands on its own if the rule is missing.
- **IPv4 only.** `lan_address` is IPv4, and the rule drops IPv6 to the LAN port.
- **Files outside the roots.** `dashboard/` holds operator configuration, written only by
  the explicit `cert` and `password` commands, never by a job.

## Controls (`dashboard/cancel.py`, `dashboard/controls.py`, `dashboard/canceller.py`, `web/src/features/job/JobControls.tsx`, `web/src/features/jobs/JobMenu.tsx`)

On by default (`controls = false` under `[dashboard]` takes them away), on the tunnel and on the
LAN address, with or without a password: mulebox is for its owner's own network, and whoever
reaches the queue may steer it, as `mulebox cancel` and `mulebox pause` already let them. A job's
page has Pause or Resume, To front, Up, Down and To end (waiting jobs), Boost or End boost
(coordinator/job_control.py), and Cancel; each online machine in the Machines box has Pause or
Resume (`machine drain` and `resume`). In the Queue tab each waiting job has four arrows for the
same moves; positions are the whole line's, across lanes.
Every running card and waiting row also has a three-dots button opening a menu of that job's
actions, each with an icon and a line on what it does, listing only what applies now (`web/src/lib/menu.ts`).
"Queue actions", beside the tabs, does everything at once: pause or resume all machines, freeze
all running jobs, resume all paused jobs. Each item sends the same request as one button would.
A frozen, paused or boosted job shows a snowflake, pause or bolt icon beside its state, and a
waiting row gives the coordinator's own reason (paused, a paused project, behind an upgrade). `cancel_button`, from before 0.87.0, is read and ignored.
What the protection below keeps out is other web pages in the same browser.

- **The way to the coordinator.** The same `cancel`, `job_control` and `machine` requests the
  CLI sends, to the same `mulebox rpc`, started as a child process instead of over ssh
  (`Canceller`, 30 s limit). So every rule stays in the coordinator, and the dashboard process itself keeps its read-only
  store. `read_reply` in `client/remote.py` reads the answer for both.
- **What it cancels.** Agent jobs before they finish, from a job's page or its three dots, which
  ask twice. For a GitHub run's slot GitHub is asked to cancel the run (interfaces-m3.md), as
  cancelling only the slot would not stop it; a slot with no run address, or a `gh` that is not
  logged in, is 502 with the reason. A finished job is 409. Unknown is 404.
  A coordinator that fails or does not answer is 502, with the reason, and the job is untouched.
  Cancelling twice is harmless. Each cancel is logged with the job and the address it came from.
- **The other controls act at once.** None loses work and each has its way back on the same
  spot; a line under them says what is on. A coordinator's refusal is 409 with its own words.
- **Cancel is asked twice.** In the page, not a browser dialog. The first click puts `Keep job` under the
  pointer and takes the focus, so a double click or Enter keeps the job; Escape does too.
- **Cross-site requests.** All of these must hold, and none is a guess at who is asking. With a
  password a session is not enough, as a browser adds the cookie by itself; without one there is
  no cookie, and the token alone is what a page of this dashboard has and another page has not:
  - `SameSite=Strict` keeps the cookie off a request from another site. It does not cover a page
    on another port of this address, which browsers count as the same site, such as a project's
    dev server on the node.
  - `Sec-Fetch-Site` must be `same-origin` when sent, which browsers do only in a secure context.
  - `Origin` must be exactly this page's origin. A form post has `null` under the page's
    `no-referrer` policy, which is why `/login` cannot use this rule; `fetch` sends the real one.
  - `X-Mulebox-Token` must hold `action_token`. With a password it is derived from the session
    by a one-way hash, so it ends with the session and does not reveal the `HttpOnly` cookie;
    without one it is a secret the service makes when it starts, and a page refused with an old
    one asks for the new one once. Only a page of this origin
    can read it from `/api/session`, and a cross-site page cannot set the header, because no
    route answers a preflight and no reply carries CORS headers.

## Guarantees

- **Read-only.** The store is opened with SQLite `mode=ro`, so a write fails in SQLite
  itself. All routes are GET, apart from `POST /login` and `POST /logout` on the LAN
  listener, which only touch sessions, and the controls (above), whose writes happen in a
  `mulebox rpc` process; any other method gets 405.
- **Host check.** Only `127.0.0.1`, `localhost` and `[::1]`, on any port, or `lan_address`
  on the LAN listener; anything else gets 421. This stops DNS rebinding from a web page.
- **Headers on every reply**, errors and streams included: a strict
  Content-Security-Policy (same origin, no inline script or style), `nosniff`,
  `no-referrer`, `X-Frame-Options: DENY`. API replies are `no-store`.
- **Data.** Never returned: job `env`, leases, attempt ids, upload hashes. Docker gives a
  container count only, never names, images or inspect output. Commands are redacted.
- **Logs are text.** They are redacted by the worker before storage. The page appends them
  as text nodes; no code path parses server data as HTML.
- **No external resources.** No CDN, and nothing is built on a node: the React
  build in `app/` ships in the wheel. Fonts are files of the package.
- **File names.** Browser filter lists block some script names outright (`logview.js` was
  one), and one blocked ES module stops the whole page. Check new names in a real browser.

## HTTP API

| Route | Reply |
| --- | --- |
| `GET /healthz` | `{ok, version, lan, sign_in}`; `lan` is true on the LAN listener, `sign_in` when it needs a password |
| `GET`, `POST /login` | sign-in page and form; LAN listener only, else 404 |
| `POST /logout` | ends the session, 204; LAN listener only, else 404 |
| `GET /api/session` | `{action_token, cancel_token}` (the same value): what this page sends with a change, null with the controls off |
| `POST /api/jobs/{id}/cancel` | `{job_id, state, outcome, cancel_requested}`; rules in Controls |
| `POST /api/jobs/{id}/control` | body `{action}`: pause, resume, first, up, down, last, boost, normal; `{job_id, action, state, position, paused, boost, priority}` |
| `POST /api/machines/{name}/control` | body `{action}`: pause or resume; `{machine, action, running}` |
| `GET /api/queue` | status-model snapshot: `now`, `running`, `queued`, `recent`; waiting agent jobs carry `needs`, `can_run_on`, `waiting_for` |
| `GET /api/machines` | machines panel snapshot (above) |
| `GET /api/history?limit=&before=&project=&job=&client=&worker=&kind=&result=&q=` | `{jobs, next_before}`, finished jobs newest first, and on the first page (no `before`) `choices`, every value of each filter as `/api/stats` gives it; `limit` 1..200, default 50; page with `before = next_before`, which keeps the filters. `project`, `job`, `client`, `worker` and `kind` (job or runner) are exact values; `result` is passed, failed (timed out and interrupted too) or cancelled (stopped as stuck too), as `shown_state` shows them, a GitHub run with no result of its own matching none; `q` is part of the project, job name or branch in any case, `%` and `_` taken as typed. Values up to 200 characters; 400 on a bad value |
| `GET /api/jobs/{id}` | job detail with redacted `command`, `cancel_requested`, `log_size` and, while it runs, `activity` as in a `status` reply; 404 if unknown |
| `GET /api/jobs/{id}/log.txt` | the stored log as plain text |
| `GET /api/jobs/{id}/log` | live log, SSE (below) |
| `GET /api/events` | queue, machines and metrics, SSE (below) |
| `GET /api/metrics?machine=` | no `machine`, or the host's own name: `{history, drops, machine, host: true}`, the kept samples, viewers dropped so far and the host's worker name (null when none runs there). Another worker: `{machine, host: false, last_seen, history}` (Metrics, below); 404 for a name the store does not know |
| `GET /api/stats?from=&to=&day_starts=&by=&project=&job=&client=&worker=&kind=` | job minutes, the `stats_ok` body of interfaces-m1.md (`day_starts` and `by` comma-separated); 400 on a bad value |

Bad numbers in `limit` or `before` give 400. An unusable offset or event id is ignored.

## Server-Sent Events

`/api/events`: one stream for the whole page.

- Events: `queue` and `machines` (snapshots, sent only when they change), `metrics` (every
  2 s) and `metrics_history` (`{history}`, only in a snapshot).
- Ids are `<epoch>-<seq>`; the epoch is random per server process. A reconnect with
  `Last-Event-ID` gets what it missed from the last 256 events. If the id is from another
  process or too old, the viewer gets a fresh snapshot instead.
- A viewer more than 64 events behind is dropped, so it can never slow anyone else; its
  browser reconnects and resumes.
- `beat` (empty, every 5 s with nothing else to send, on both streams): a connection can die
  with no error, so a page that hears nothing for 20 s opens the stream again.

`/api/jobs/{id}/log`: starts at `Last-Event-ID`, else `?offset=`, else `?tail=` bytes before
the end, else 0.

- `log` (`offset`, `next_offset`, `data`): the event id is the byte offset after the chunk,
  so a reconnect resumes exactly there.
- `state` (`state`): when the job's state changes.
- `end` (job detail): once, after the whole log of a finished job. The page closes the
  stream on it; otherwise the browser would reconnect.

A page reopened after a dead connection asks with `?offset=`, the last `next_offset` it got.

## Metrics

Sampled once however many viewers there are (`hub.py`). Blocking reads run in a thread.

| Value | Every | Source |
| --- | --- | --- |
| `cpu` (percent per core), `memory`, `swap` (`total`, `used`), `self` (own CPU and RSS) | 2 s | `/proc` |
| `docker` (running containers, or null) | 5 s | Engine API socket |
| `jobs_memory` (bytes, or null without cgroup v2) | 5 s | The working set (`memory.current` less the `inactive_file` page cache) of the agent job units, of the services of GitHub runners running a job (an idle listener is not counted), and of the containers of both: labelled `mulebox.job`, or started by Compose from a runner's `_work` folder |
| `disk` (one entry per file system holding a root) | 30 s | `statvfs`, never `du` |
| `docker_disk` (bytes, or null) | 5 min | Engine API `GET /system/df`: image layers, containers, volumes and build cache, the total `docker system df` gives; Docker sizes every layer for it (0.7 s on a machine with 59 images) |

`jobs_memory` leaves out page cache the kernel can drop at once, as `used` does. The Memory box
shows it as Jobs and swap as Swap, the Disk box `docker_disk` as Docker, on the dashboard's own
machine only. The last 150 samples (5 minutes) are kept. Missing values are null, not errors: without
`/proc` (macOS) or Docker the dashboard still runs.

**Other machines** (`dashboard/machine_history.py`, `dashboard/metrics_api.py`). Each worker
sends with its claims and heartbeats, in `load` (interfaces-m1.md), `cpu` (percent per core),
`memory` (`total`, `available`, `used` bytes) and `disk`, the fullest file system under its
roots (`roots`, `total`, `used`, `free`; common/disk.py `fullest`), read in the same sampling as
`cpu_pct`, at most every 2 s, by no extra process. The coordinator keeps the latest in
`workers.load`. The hub's machines loop, which reads the workers every 2 s anyway, keeps an
entry per worker each time its `last_seen` moved on by 1.5 s or more: `{t, cpu, memory, disk}`,
`t` being `last_seen` and `disk` a list of one, so the host's shape without `self`, `docker`,
`viewers`, `swap`, `jobs_memory` and `docker_disk`. Up to 5 minutes and 200 entries per worker, in the dashboard process only; a worker
removed from the store is forgotten, and a restart starts empty. An offline worker answers
`history: []` with its `last_seen`. A worker before these readings gives `cpu: []`,
`memory: null` and `disk: []`. The page polls this every 2 s while such a machine is picked; the
host's samples keep coming on the event stream.
