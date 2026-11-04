# Interfaces: web dashboard (M2)

The contract for `mulebox/dashboard/`, `mulebox/common/status.py` and
`mulebox/client/tunnel.py`. Design goals: [design.md](design.md) (Dashboard).

## Status model (`common/status.py`)

One place decides how a job is shown; the terminal view and the dashboard both use it.
Input is a public job dict; every function tolerates missing or malformed fields.

- Sections: `running` (starting, running, cleaning), `queued` (uploading, queued, by
  position) and `recent` (finished, newest first).
- Shown state: the outcome of a finished job, else its state. A finished runner
  reservation that passed or failed shows `released`: it only held a slot, the real result
  is on GitHub. `interrupted` and `cancelled` reservations keep their outcome.
- Elapsed: waiting time when queued, running time when active, run time when finished.
- `fingerprint(jobs)`: what changes when a view must redraw. Elapsed time is left out, so a
  ticking clock never causes an event.

## Processes and access

- `mulebox dashboard serve` runs on the coordinator machine as the user service
  `mulebox-dashboard`. It binds `127.0.0.1`, plus `lan_address` in `lan` mode, and has no
  option to bind anything else.
- `[dashboard] mode` in `node.toml`: `local` (default) serves; `off` exits 0 at once, and
  the unit does not restart; `lan` adds the TLS listener (below). Exit 2 is a configuration
  problem, which the unit does not retry; exit 1 is a failed bind, which it does, because
  Wi-Fi can come up after the service.
- `mulebox dashboard open [--port N] [--remote-port N] [--no-browser]` on the laptop runs
  `ssh -N -L 127.0.0.1:<local>:127.0.0.1:<remote> <coordinator>`, waits for `/healthz`,
  opens the browser and holds the tunnel until Ctrl-C (exit 0). A tunnel that closes or a
  dashboard that does not answer exits 3, the "unreachable" code. The tunnel is always its
  own ssh connection, never a shared `ControlMaster` one: ssh would otherwise hand the
  forward to the master and exit, and Ctrl-C could not close it.

## `lan` mode

Setup steps: [install.md](install.md). Modules: `lan_commands.py` (CLI, checks before
serving), `login.py` (rules and pages), `session.py`, `password.py`, `cert.py`,
`firewall.py`, `lanfiles.py`, `listeners.py`.

- **Two listeners, one app.** Plain HTTP on `127.0.0.1:<port>` for the tunnel, with no
  password, and HTTPS on `<lan_address>:<lan_port>`. The rules follow `request.secure`,
  which comes from the connection, never from a header. Forwarded-for headers are ignored.
- **Order on the TLS listener.** Host must be `lan_address` (421), the peer must be in
  `lan_range` (403), then a session is needed. Only `/login` and `/static/style.css` are
  open without one. Pages redirect to `/login`; `/healthz` and `/api/` get 401.
- **Password.** scrypt hash in `dashboard/password` beside `node.toml`, mode 600. Read at
  start, so a new one needs a restart. Never an argument: `mulebox dashboard password`
  prompts, or reads one line from stdin when that is not a terminal.
- **Sessions.** In memory, as hashes, 24 h, at most 64 (oldest dropped). A restart signs
  everyone out; open pages then return to `/login` on their own. Cookie: `Secure`,
  `HttpOnly`, `SameSite=Strict`.
- **Failed logins.** Per address: 5 free, then a wait of 30 s doubling to 15 min (429),
  even for the right password. One scrypt at a time, so logins cannot starve jobs.
- **Cross-site posts** are refused with `Sec-Fetch-Site`. `Origin` cannot do this: with the
  `no-referrer` policy, browsers send `Origin: null` on a same-site form post.
- **Certificate.** Self-signed, marked CA because phones only fully trust those, with
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

## Guarantees

- **Read-only.** The store is opened with SQLite `mode=ro`, so a write fails in SQLite
  itself. All routes are GET, apart from `POST /login` and `POST /logout` on the TLS
  listener, which only touch sessions; any other method gets 405. There is no cancel
  button (M2.5).
- **Host check.** Only `127.0.0.1`, `localhost` and `[::1]`, on any port, or `lan_address`
  on the TLS listener; anything else gets 421. This stops DNS rebinding from a web page.
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
| `GET /healthz` | `{ok, version, lan}`; `lan` is true on the TLS listener |
| `GET`, `POST /login` | sign-in page and form; TLS listener only, else 404 |
| `POST /logout` | ends the session, 204; TLS listener only, else 404 |
| `GET /api/queue` | status-model snapshot: `now`, `running`, `queued`, `recent` |
| `GET /api/history?limit=&before=&project=` | `{jobs, next_before}`, newest first; `limit` 1..200, default 50; page with `before = next_before` |
| `GET /api/jobs/{id}` | job detail with redacted `command` and `log_size`; 404 if unknown |
| `GET /api/jobs/{id}/log.txt` | the stored log as plain text |
| `GET /api/jobs/{id}/log` | live log, SSE (below) |
| `GET /api/events` | queue and metrics, SSE (below) |
| `GET /api/metrics` | `{history, drops}`: the kept samples and viewers dropped so far |

Bad numbers in `limit` or `before` give 400. An unusable offset or event id is ignored.

## Server-Sent Events

`/api/events`: one stream for the whole page.

- Events: `queue` (a snapshot, sent only when the fingerprint changes), `metrics` (every
  2 s) and `metrics_history` (`{history}`, only in a snapshot).
- Ids are `<epoch>-<seq>`; the epoch is random per server process. A reconnect with
  `Last-Event-ID` gets what it missed from the last 256 events. If the id is from another
  process or too old, the viewer gets a fresh snapshot instead.
- A viewer more than 64 events behind is dropped, so it can never slow anyone else; its
  browser reconnects and resumes.

`/api/jobs/{id}/log`: starts at `Last-Event-ID`, else `?offset=`, else `?tail=` bytes before
the end, else 0.

- `log` (`offset`, `next_offset`, `data`): the event id is the byte offset after the chunk,
  so a reconnect resumes exactly there.
- `state` (`state`): when the job's state changes.
- `end` (job detail): once, after the whole log of a finished job. The page closes the
  stream on it; otherwise the browser would reconnect.

## Metrics

Sampled once however many viewers there are (`hub.py`). Blocking reads run in a thread.

| Value | Every | Source |
| --- | --- | --- |
| `cpu` (percent per core), `memory`, `self` (own CPU and RSS) | 2 s | `/proc` |
| `docker` (running containers, or null) | 5 s | Engine API socket |
| `disk` (one entry per file system holding a root) | 30 s | `statvfs`, never `du` |

The last 150 samples (5 minutes) are kept. Missing values are null, not errors: without
`/proc` (macOS) or Docker the dashboard still runs.
