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
  `mulebox-dashboard`. It binds `127.0.0.1` and has no option to bind anything else.
- `[dashboard] mode` in `node.toml`: `local` (default) serves; `off` exits 0 at once, and
  the unit does not restart; `lan` is refused with exit 2 until it is built (M2.4).
- `mulebox dashboard open [--port N] [--remote-port N] [--no-browser]` on the laptop runs
  `ssh -N -L 127.0.0.1:<local>:127.0.0.1:<remote> <coordinator>`, waits for `/healthz`,
  opens the browser and holds the tunnel until Ctrl-C (exit 0). A tunnel that closes or a
  dashboard that does not answer exits 3, the "unreachable" code. The tunnel is always its
  own ssh connection, never a shared `ControlMaster` one: ssh would otherwise hand the
  forward to the master and exit, and Ctrl-C could not close it.

## Guarantees

- **Read-only.** The store is opened with SQLite `mode=ro`, so a write fails in SQLite
  itself. All routes are GET; any other method gets 405. There is no cancel button (M2.5).
- **Host check.** Only `127.0.0.1`, `localhost` and `[::1]`, on any port; anything else
  gets 421. This stops DNS rebinding from a web page in the laptop's browser.
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
| `GET /healthz` | `{ok, version}` |
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
