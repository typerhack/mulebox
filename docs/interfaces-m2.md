# Interfaces: web dashboard (M2)

The contract for `mulebox/dashboard/`, `mulebox/common/status.py` and
`mulebox/client/tunnel.py`. Design goals: [design.md](design.md) (Dashboard).

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
and `waiting_for` (needs.py, when a queued job cannot start now). None of it is an
assignment: the queue is one line, and the first capable worker with a free slot takes the
job. A running job has its `worker`; a runner reservation its `pinned_worker`.

## Jobs box (`static/jobs.js`, `static/lanes.js`)

Tabs, each with a live count, remembered per browser, each showing one thing: `Queue`
(default, what is happening now), `Failed` (failed, timed out or interrupted) and `Passed`
among the finished jobs the queue keeps, GitHub jobs included, and `Recent` (all of those, so
also cancelled jobs and runner slots released before 0.76.0, which are neither a pass nor a
failure). Ticking times are
keyed by job id, whatever order a tab puts them in. A viewer's first `queue` snapshot is
built when it connects, never taken from the last published event, whose elapsed times
would be stale.

`Queue` is the queue by machine: one lane per worker with its name and state, a block per
running job, and the jobs waiting for it. Slots, capabilities and readings are shown once,
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

## Processes and access

- `mulebox dashboard serve` runs on the coordinator machine as the user service
  `mulebox-dashboard`. It binds `127.0.0.1`, plus `lan_address` in `lan` mode, and has no
  option to bind anything else.
- `[dashboard] mode` in `node.toml`: `local` (default) serves; `off` exits 0 at once, and
  the unit does not restart; `lan` adds the LAN listener (below). Exit 2 is a configuration
  problem, which the unit does not retry; exit 1 is a failed bind, which it does, because
  Wi-Fi can come up after the service.
- `mulebox dashboard open [--port N] [--remote-port N] [--no-browser]` on the laptop runs
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

## Machines box (`dashboard/machines.py`, `static/machines.js`)

The panel feeds the Machines box, the lanes above and `/api/machines`.

- A row per worker in the coordinator's `workers` table: `name`, `state`, `slots`,
  `free_slots`, `capabilities`, `last_seen`, `jobs`, `cpu_pct`, `mem_pct`. Plus `total`,
  `online` and `free_slots` for the cluster.
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
- **Out of step** (`dashboard/notices.py`, `static/versions.js`): `notices`, a list of `kind`
  (`worker`, `client`, `skill`), `level` (`danger` for a worker, as jobs can fail; `warning` for
  a laptop), `name`, `text` and `fix`, dangers first. Shown as a strip above the panels in its
  worst level's colour, and as a mark with the count in the header that brings the strip into
  view; both hidden while empty. A notice is an online worker on another mulebox than the coordinator,
  a laptop seen in the last 14 days on another mulebox than the build machine, or a laptop
  whose skill differs from its mulebox's. Laptops say their `client_version` and `skill`
  (`current`, `out_of_date`, `none`) with every `submit`; the newest word per laptop is kept in
  the `clients` table (schema 19, coordinator/clients.py). Laptops older than 0.83.0 say neither
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
  `lan_range` (403), then a session is needed. Only `/login` and `/static/style.css` are
  open without one. Pages redirect to `/login`; `/healthz` and `/api/` get 401.
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

## Controls (`dashboard/cancel.py`, `dashboard/controls.py`, `dashboard/canceller.py`, `static/access.js`, `static/canceljob.js`, `static/jobcontrols.js`)

On by default (`controls = false` under `[dashboard]` takes them away), on the tunnel and on the
LAN address, with or without a password: mulebox is for its owner's own network, and whoever
reaches the queue may steer it, as `mulebox cancel` and `mulebox pause` already let them. A job's
page has Pause or Resume, Run first or Back in line (waiting jobs), Boost or End boost
(coordinator/job_control.py), and Cancel; each online machine in the Machines box has Pause or
Resume (`machine drain` and `resume`). `cancel_button`, from before 0.87.0, is read and ignored.
What the protection below keeps out is other web pages in the same browser.

- **The way to the coordinator.** The same `cancel`, `job_control` and `machine` requests the
  CLI sends, to the same `mulebox rpc`, started as a child process instead of over ssh
  (`Canceller`, 30 s limit). So every rule stays in the coordinator, and the dashboard process itself keeps its read-only
  store. `read_reply` in `client/remote.py` reads the answer for both.
- **What it cancels.** Agent jobs before they finish, from a job's page only, so a click in a
  moving queue cannot land on the wrong job. A runner reservation is refused (409): GitHub owns
  those, and cancelling the slot would not stop the run. A finished job is 409. Unknown is 404.
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
    dev server on the build machine.
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
- **No external resources.** No CDN, no build step; `static/` ships in the wheel.
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
| `POST /api/jobs/{id}/control` | body `{action}`: pause, resume, first, boost, normal; `{job_id, action, state, paused, boost, priority}` |
| `POST /api/machines/{name}/control` | body `{action}`: pause or resume; `{machine, action, running}` |
| `GET /api/queue` | status-model snapshot: `now`, `running`, `queued`, `recent`; waiting agent jobs carry `needs`, `can_run_on`, `waiting_for` |
| `GET /api/machines` | machines panel snapshot (above) |
| `GET /api/history?limit=&before=&project=` | `{jobs, next_before}`, newest first; `limit` 1..200, default 50; page with `before = next_before` |
| `GET /api/jobs/{id}` | job detail with redacted `command`, `cancel_requested`, `log_size` and, while it runs, `activity` as in a `status` reply; 404 if unknown |
| `GET /api/jobs/{id}/log.txt` | the stored log as plain text |
| `GET /api/jobs/{id}/log` | live log, SSE (below) |
| `GET /api/events` | queue, machines and metrics, SSE (below) |
| `GET /api/metrics` | `{history, drops}`: the kept samples and viewers dropped so far |

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
| `cpu` (percent per core), `memory`, `self` (own CPU and RSS) | 2 s | `/proc` |
| `docker` (running containers, or null) | 5 s | Engine API socket |
| `disk` (one entry per file system holding a root) | 30 s | `statvfs`, never `du` |

The last 150 samples (5 minutes) are kept. Missing values are null, not errors: without
`/proc` (macOS) or Docker the dashboard still runs.
