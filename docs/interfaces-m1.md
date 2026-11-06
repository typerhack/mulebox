# Interfaces for M1.4 - M1.8 (coordinator, worker, client, install)

Contract for the parallel build of the rest of M1. Shared modules: [interfaces.md](interfaces.md).
Design: [design.md](design.md). Changes to this file go through the integrator.

## Decisions for M1 (simplifications, revisit later)

- **Full snapshot, no worker-side clone.** The client sends a tar.gz of the worktree (tracked +
  untracked, not ignored, minus excludes). The worker extracts it; no git remote access is
  needed on build machines. Delta uploads against a cached base are a parking-lot item.
- **No coordinator socket daemon for requests.** `mulebox rpc` opens the SQLite store
  directly (WAL mode, `busy_timeout`, `BEGIN IMMEDIATE` for writes). The coordinator
  service (`mulebox coordinator serve`) only runs periodic sweeps (lease expiry, recovery).
- **One node in M1.** Worker and coordinator run on the same machine as two systemd user
  services. The worker talks to the coordinator through `CoordinatorLink`; M1 ships the
  local link (direct calls) and the ssh link (for M5).
- **Leases.** Client lease 300 s (was 120 s until 0.5.2), renewed by heartbeats every 20 s on the `watch` stream.
  Worker lease 120 s per job, renewed every 20 s. Clock: coordinator `time.time()`.

## Filesystem layout on a build machine (inside NodeConfig roots)

| Path | Owner | Content |
| --- | --- | --- |
| `<staging>/state/mulebox.db` | coordinator | SQLite store |
| `<staging>/uploads/<job_id>.tar.gz` | coordinator | snapshot; removed when the job finishes |
| `<staging>/bases/<project hash>.tar.gz` | coordinator | a project's last snapshot, what the next upload is compared with |
| `<staging>/logs/<job_id>.log` | coordinator | redacted job log, removed after `log_days` (interfaces-m4.md) |
| `<projects>/<project>/repo.git` | worker | the project's repository on this machine |
| `<projects>/<project>/trees/<branch>-<hash>/` | worker | one worktree per branch, kept between jobs: where jobs run |
| `<projects>/<project>/state/<branch>-<hash>.setup` | worker | what the last finished `setup` depended on |
| `<jobs>/<project>/<job_id>/` | worker | the job's scratch files, removed after it |
| `<jobs>/<project>/<job_id>/out.log` | worker | raw unit output (worker redacts before sending) |
| `<cache>/toolchains/<name>/<version>/bin` | worker | pinned toolchains, prepended to PATH |
| `<cache>/packages/<project>/<tool>` | jobs that ask | package caches (interfaces-m4.md) |

All creation through `safepath.ensure_dir`, all deletion through `safepath.remove_tree`.

## CLI (registered by each package; `mulebox/cli.py` only dispatches)

Each package has `<pkg>/commands.py` with `register(sub: argparse._SubParsersAction) -> None`.
Every subcommand sets `func=handler`, where `handler(args) -> int` returns the exit code.

| Command | Package | Notes |
| --- | --- | --- |
| `mulebox check [job] [--detach]` | client | default job `check`; exit code = job exit code; `--detach` prints the job id once queued and exits 0 |
| `mulebox run [--detach] -- <cmd...>` | client | ad-hoc argv |
| `mulebox wait <job_id>` | client | what an attached `check` gives (log, summary, exit code), via watch; takes a detached job back |
| `mulebox events --job <job_id> [--json]` | client | state changes from watch with `log: false`, through `status.job_event`; exit code = job exit code. Format: client/events.py |
| `mulebox status <job_id> [--json]` | client | one `status` request; exit 0 whatever the job did |
| `mulebox queue [--watch]` | client | table; `--watch` = live view (M1.7) |
| `mulebox logs <job_id> [-f] [--summary]` | client | `-f` follows via watch without lease; `--summary` reads the log's tail only (client/summary.py). A log that gives nothing for a job whose `log_size` is above 0 has expired: stderr says so, also in `wait`, and the exit code stays what it was |
| `mulebox cancel <job_id>` | client | |
| `mulebox skill install\|update\|status [--config-dir <dir>...]` | client | copies of the packaged skill in Claude config folders (client/skill_install.py); `status --json` for tools |
| `mulebox doctor [--json]` | client | read-only; `machines` request, or `mulebox version` over ssh from a coordinator too old for it. Compose files go through the worker's policy on what they show themselves. Exit 0 ok or warnings, 1 a job would not run, 2 config, 3 unreachable |
| `mulebox rpc` | coordinator | one request line on stdin; replies on stdout |
| `mulebox rpc-upload <job_id> <sha256>` | coordinator | tar.gz bytes on stdin |
| `mulebox rpc-download <job_id>` | coordinator | tar.gz bytes on stdout (ssh link) |
| `mulebox coordinator serve` | coordinator | sweep loop; recovery first |
| `mulebox worker serve` | worker | claim loop; recovery first |
| `mulebox toolchain install <name> <version>` | worker | node, pnpm |
| `mulebox toolchain list` | worker | |

Exit codes for client failures (not job failures): 2 usage/config error, 3 build machine
unreachable (`SSHUnavailable`), 4 protocol/remote error, 130 cancelled by Ctrl-C.
A finished job maps: passed -> its exit code (0), failed -> its exit code, or 5 if it could not start (no command ran),
timed_out -> 124 (a worker older than 0.37 only), cancelled -> 130, interrupted -> 75, a
stop (`cancelled` with a `stop_reason`, docs/design.md, Time limits) -> 76.

## Wire usage (protocol.py; replies reuse `request_id`)

`submit_ok`, `status`, `queue_ok` and `machines_ok` also carry `dashboard`: `{"url": str | null}`,
null when the dashboard is only reachable through a tunnel, or `null` when it is off. Older
coordinators leave it out, and the client then prints nothing.

`status_ok` is the generic reply carrying `job_id, state` (+ `outcome`, `exit_code`,
`position` when queued, `worker` when active, `estimate_s` and `estimate_runs` when queued
with enough history (coordinator/usual.py), `stage` when a job ended badly in a known stage, `cancel: bool` for worker heartbeats). Errors reply `error` with
codes `not_found`, `bad_request`, `conflict`, `too_large`, `internal`.

| Request | Body (required + used extras) | Reply |
| --- | --- | --- |
| submit | project, job, argv, idempotency_key, fingerprint, base_commit, client, + `setup`, `toolchain`, `needs`, `timeout_min`, `branch`, `detached` | submit_ok (job_id, state, `detached`); repeat key returns the same job. A client that asked for `detached` and does not see it echoed cancels the job |
| rpc-upload (argv) | job_id, sha256 of the tar.gz | status_ok (state `queued`) or error |
| status | job_id | status_ok (+ `project`, `job`, `branch`, `kind`, `detached`, `created_at`, `started_at`, `finished_at`, `log_size`, `attended`, `unattended`, `activity`; `stop_reason` on a stopped job) |
| cancel | job_id | status_ok |
| heartbeat | job_id, lease (`client`/`worker`), + `attempt_id` and `activity` for worker | status_ok (+ `cancel`) |
| queue | + `limit` (default 20 recent finished) | queue_ok (jobs: list of job dicts; `dashboard`, see below) |
| projects | - | projects_ok (projects: `project`, `jobs`, `last_run`, `kind`, `state`, `outcome` of the newest job, newest first) |
| logs | job_id, offset | log_chunk (data from offset, `eof: bool`) |
| watch | job_id, offset, + `lease: bool`, `log: bool` (default true) | stream: log_chunk (none with `log: false`) / status_ok lines, final `result` |
| claim | worker, capabilities, free_slots, + `toolchains` (name to versions), `version` | claim_ok or claim_none |
| machines | - | machines_ok (`version` of the coordinator; `workers`: worker, online, capabilities, toolchains or null, version or null, slots) |
| job_update | job_id, state, + attempt_id | status_ok |
| log_chunk (worker) | job_id, offset, data, + attempt_id | status_ok |
| result (worker) | job_id, outcome, exit_code, duration_s, + attempt_id | status_ok |

`claim_ok` body: `limits: "coordinator"` (no runtime limit on the worker; an older
coordinator sends none and `timeout_min` stays hard), job_id, attempt_id, project, argv,
fingerprint, base_commit, timeout_min,
setup, toolchain, needs, job. Job dicts in queue_ok: job_id, project, job, branch, client,
state, outcome, exit_code, worker, position, created_at, started_at, finished_at (epoch s),
kind, detached. A `result` adds duration_s and fingerprint.

Watch stream: after the `watch` request line the client keeps stdin open and writes a
`heartbeat` line (lease `client`) every 20 s; each renews the client lease if `lease: true`,
or whatever `lease` says for a detached job, which is how `wait` and `events` count as watching.
`reach` (`hosts`, at most 8) answers `reach_ok` with `hosts` as host to true or false: whether a TCP
connection to each opened, for `mulebox doctor`.
A `status_ok` may carry `stage` (`log: false` only, as a job enters a stage), or `check_in` (every `timeout_min`, a question: `job_ok` with `job_id` answers it). `submit` with
`reuse: true` may answer with `already`, the earlier job's result, and that job's id, and
`submit_ok` and `queue` with `news_for` carry `questions` and `finished_away`. The server polls every 0.5 s and writes `log_chunk` for new log bytes and
`status_ok` on state changes; it ends with `result` (job dict fields) and exits 0.
Line cap for any request: 1 MiB (`MAX_LINE_BYTES`). Upload cap: 1 GiB.

Remote command: client and ssh link run `[remote_bin, "rpc"]` via `common.ssh`. A
`remote_bin` starting with `~/` is sent without the `~/` (ssh starts in the home folder;
`shlex.join` would quote `~`).

## Coordinator (`mulebox/coordinator/`)

- `store.py`: `Store(path: Path)`; `open()` creates schema (tables `jobs`, `workers`,
  `meta(schema_version)`); WAL; all writes in `BEGIN IMMEDIATE`. Job rows hold every field
  above plus `idempotency_key UNIQUE`, `attempt_id`, `client_lease_until`,
  `worker_lease_until`, `cancel_requested`, `log_size`, `queued_at`.
  `check_transition` guards every state change.
- `queue.py`: `claim(store, worker, capabilities, free_slots, cluster_slots=1) -> dict | None`
  atomic: oldest `queued` job whose `needs` are a subset of capabilities, only if fewer than
  `cluster_slots` jobs are `starting|running|cleaning`. Sets `starting`, worker, attempt_id,
  worker lease. `position(job_id)`.
- `leases.py`: `renew_client`, `renew_worker`, `expire(store, now)`: an expired client lease
  stops nothing; a stuck job with no answer gets a stop (`attendance.py`); expired worker lease
  -> `finished/interrupted`. Uploading jobs older than 10 min -> `finished/interrupted`.
- `recovery.py`: on coordinator start, jobs in `starting|running|cleaning` whose worker
  lease expired -> `interrupted`. Never replays a job.
- `staging.py`: upload write (temp name in uploads dir, stream, hash, size cap, verify,
  atomic rename), download, remove; log append at offset (idempotent: a chunk whose offset
  is below `log_size` is skipped for the overlap), read from offset.
- `api.py`: `handle(store, staging, msg: Message, now: float) -> Message` for every
  non-streaming request; pure dispatch, no stdin/stdout.
- `rpc.py`: the `rpc`, `rpc-upload`, `rpc-download` entry points (stdin/stdout, line cap,
  the watch stream loop with a stdin heartbeat reader thread).
- `daemon.py`: `serve(node)`: recovery, then every 5 s `leases.expire`; SIGTERM exits.
- Node config: `load_node_config()`; roots via `Roots.from_config(node.roots)`.

## Worker (`mulebox/worker/`)

- `link.py`: `CoordinatorLink` protocol with `call(msg) -> Message` and
  `fetch_snapshot(job_id, dest: Path) -> None`. `LocalLink(store, staging)` calls
  `coordinator.api.handle` (the only worker -> coordinator import); `SSHLink(target,
  remote_bin)` uses `common.ssh`.
- `workspace.py`: `job_dir(...)`, `cleanup(...)` (the job's scratch folder, through safepath)
  and `git(cwd, *args)`, with fixed settings so no hook of a project runs.
- `project_home.py`: `prepare(paths, project, branch, job_id, snapshot) -> Synced(tree, changed,
  lost)` extracts with `tarfile` `filter="data"`, then syncs the branch's worktree and commits it
  (author `mulebox`), so git-based tools work. `setup_key`, `setup_is_current`, `remember_setup`
  and `forget_setup` decide whether `setup` runs.
- `executor.py`: `Executor` protocol: `start(spec) -> handle`, `poll(handle) -> int | None`
  (exit code when done), `stop(handle)`, `list_orphans() -> list[str]`, `kill(name)`.
  `RunSpec(name, argv, cwd, env, log_path, timeout_s)`.
  - `SystemdExecutor`: `systemd-run --user --unit=mulebox-job-<job_id> --collect
    --property=RuntimeMaxSec=<s> --property=KillMode=control-group
    --property=TimeoutStopSec=10s --property=CPUWeight=50 --property=IOWeight=50
    --property=StandardOutput=append:<log> --property=StandardError=append:<log>
    --working-directory=<cwd> --setenv=K=V ... -- <argv>`, each `$` of the argv doubled so
    that systemd leaves `${...}` to bash; state via `systemctl --user show`; timeout recognised by `Result=timeout`.
  - `SubprocessExecutor`: same contract with a process group (tests and macOS dev).
- `toolchains.py`: `path_for(roots, toolchain: dict) -> list[Path]` (missing -> clear error
  naming `mulebox toolchain install`), `install(roots, name, version)`: node from
  nodejs.org tarball verified against `SHASUMS256.txt`; pnpm via that node's npm into
  `<cache>/toolchains/pnpm/<version>`.
- `agent.py`: `serve(node, link, executor)`: recovery (stop orphan `mulebox-job-*` units,
  remove leftover job folders), then loop: claim when a slot is free (poll 1 s), fetch
  snapshot, prepare, `job_update starting->running`, run `bash -c "set -e; <setup>"` then the
  job argv as one script, tail `out.log` through `StreamRedactor` into `log_chunk`s (max
  64 KiB each), heartbeat every 20 s (stop the job on `cancel: true`; stop it if the
  coordinator is unreachable for 120 s), then `cleaning`, cleanup, `result`.
  Env: `MULEBOX=1`, `MULEBOX_JOB_ID`, PATH with toolchains first, HOME unchanged.

Stage rows: `steps`, see [interfaces-m4.md](interfaces-m4.md), Job steps.

## Client (`mulebox/client/`)

- `snapshot.py`: `make_snapshot(root: Path, extra_excludes) -> Snapshot(path, sha256,
  fingerprint, base_commit, branch, files)`: `git ls-files -co --exclude-standard -z`;
  built-in excludes `.secret/`, `.env`, `.env.*`, `secrets/`, `.npmrc`, `.envrc`, `.netrc`, `*.pem`, `*.key`,
  `*.p12`, `*.pfx`, `id_rsa*`, `id_ed25519*`, `id_ecdsa*`, `id_dsa*`, `.git-credentials`, `.pypirc`, `.ssh/`,
  `.aws/`, `.mulebox/`; symlinks stored as links (never followed); tar.gz
  to a temp file. `fingerprint`: sha256 over sorted (path, mode, sha256 of content or link
  target). `current_fingerprint(root, excludes)` for the stale check.
- `remote.py`: `Remote(client_config)`: `call(msg)`, `upload(job_id, path, sha256)`,
  `watch(job_id, offset, lease) -> Iterator[Message]` (writes heartbeats from a thread).
- `submit.py`: `run_job(project_cfg, job_name | argv, root) -> int`: snapshot, submit
  (idempotency key `sub-...`), upload, watch, print log to stdout, status lines to stderr
  (queue position, elapsed), Ctrl-C sends cancel and returns 130, stale warning at the end.
- `tui.py`: `mulebox queue --watch` live view: ANSI full-screen refresh every 2 s, `q` or
  Ctrl-C quits; plain table when stdout is not a TTY.
- `commands.py`: check, run, queue, logs, cancel.

## Install (`install/`, M1.8)

- `install/install.sh` (run on the build machine): checks Linux, systemd, Python >= 3.12
  and `python3 -m venv` (prints `sudo apt-get install python3-venv` if missing); creates
  `~/.mulebox/venv`, installs the given wheel, links `~/.mulebox/bin/mulebox`; writes
  `~/.config/mulebox/node.toml` from a template if missing (roots under `~/.mulebox/`);
  creates the roots; installs `mulebox-coordinator.service` and `mulebox-worker.service`
  user units; checks `loginctl show-user` Linger and prints how to enable it; never deletes.
- `tools/deploy.sh <ssh-target>` (run on the laptop): builds a wheel, copies it and
  `install.sh` with `scp`, runs the install, prints `mulebox --version` from the machine.
- `docs/install.md`: user steps.

## Decisions made during the build (0.5.0)

Coordinator:
- Extra modules: `errors`, `validate`, `views`, `worker_api`, `uploads`, `watch`, `lineio`,
  `context`, `node` (`open_local(node) -> (Store, Staging)`, used by the worker's local link).
- `api.handle(store, staging, msg, now, *, cluster_slots=1)` never raises. `rpc` passes
  `node.slots` as `cluster_slots` (one node in M1). `rpc`/`rpc-upload` exit 4 on an `error`
  reply (the reply line is still on stdout); bad node config exits 2.
- Uploading jobs ignore the client lease (only the 10 min upload timeout applies); a
  finished upload starts a fresh client lease.
- `job_update finished` is a bad_request: a job ends only through `result`. Log chunks are
  accepted in starting/running/cleaning only; an offset past the end is a conflict.
- Worker replies carry `cancel`; a heartbeat with the current attempt on a finished job
  gets `cancel: true`. `status_ok` for finished jobs carries `duration_s`.
- `watch` also re-sends `status_ok` when the queue position changes.

Worker:
- `systemd-run` without `--collect` (it would unload failed units and lose the exit code
  and `Result=timeout`); failed units are read, then `reset-failed`.
- `Executor.timed_out(handle)`; `NodePaths.from_config(node.roots)` names the roots.
- Heartbeat every 3 s (not 20 s): it is also how fast a cancel is noticed. Lease stays 120 s.
- Job script: `bash -c "set -e\n<setup>\n<shlex.join(argv)>"`.
- Coordinator unreachable for 120 s: stop, clean, report `interrupted` once it answers.
- `SSHLink.fetch_snapshot` holds the archive in memory (streaming is a later item).

Client:
- Symlinks that are absolute or leave the project are skipped (extraction would reject
  them) and reported. Excludes ignore case. Archive members carry no owner names.
- `mulebox run` also sends setup/toolchain/needs/timeout_min; its job name is `run`.
- A named job is sent as `["bash", "-e", "-c", "<cmd>"]` since 0.20.0: before, only the last
  line of a multi-line job decided its exit code.
- The watch stream reconnects up to 3 times, 5 s apart, then exits 3.
- `RemoteTimeout` exits 3. The ssh processes run in their own session so Ctrl-C reaches
  only mulebox, which then sends `cancel`.

Shared: `protocol.MAX_LINE_BYTES` (1 MiB) is the one line cap; `common.ssh` exposes
`ssh_command`, `raise_for_exit`, `cannot_start`, `drain_stream`, `reap` for the client's
streaming upload and watch; `config_reader.NAME_RE` is the one name pattern.

Install: deploy copies the wheel, `install.sh`, `node.toml.example` and `systemd/` to
`~/.mulebox/tmp/`; services follow the roles in node.toml; a replaced venv is moved to
`~/.mulebox/tmp/venv-old-*` (never deleted by the script).

## Changes in 0.5.1
- `claim` body may carry `restarted: true` (first claim after a worker start): the
  coordinator interrupts every active job held by that worker name before claiming.
- `ssh.raise_for_exit`: a negative exit code (local ssh killed by a signal) raises
  `SSHUnavailable`. `ssh.reap` leaves a pipe open while a reader thread is still on it.
