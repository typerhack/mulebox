# Project log

Every change to this repository is logged here, newest first, in the same commit as the
change, together with the version bump it causes. Rules: [AGENTS.md](AGENTS.md) (Versioning).

Entry format:

    ## <version> - <YYYY-MM-DD> - <patch|minor|major>
    - what changed and why (one line each)

## 0.25.0 - 2026-11-04 - minor
- Dashboard redesigned as a live monitor: boxes that fill the window, per-core meters, CPU
  and memory history, disk meters, machines with slot squares, and one jobs list. The page
  was a task list before; the user wanted to see the machine at a glance.
- One theme over the whole page, with a sun and moon switch remembered per browser. The
  sign-in page follows the system setting, because it may not load scripts.
- Drawing stops while the tab is hidden, and two graphs replace nine.

## 0.24.7 - 2026-11-04 - patch
- Test only: the dashboard snapshot test read an event stream once and sometimes saw two of
  its three events. It now reads until all three arrive.

## 0.24.6 - 2026-11-04 - patch
- Nothing under `/run` or `/var/run` may be bind-mounted from outside the checkout. A list of
  socket paths missed a rootless BuildKit socket in a user's run folder; sockets there have
  names no list can hold.

## 0.24.5 - 2026-11-04 - patch
- The loader names `LD_PRELOAD`, `LD_AUDIT` and `LD_LIBRARY_PATH` are refused only for a
  `compose:` project, the only place with a checked file to protect, and other `LD_*` names
  are not refused at all. 0.24.0 failed ordinary builds that set `LD_RUN_PATH`.

## 0.24.4 - 2026-11-04 - patch
- A service using a name from `build.tags` follows the job's private tag, as one using `image:`
  did. It kept the shared name, so it ran a stale image or pulled an unrelated one.

## 0.24.3 - 2026-11-04 - patch
- The coordinator adds `docker` and `compose-v1` to any job carrying compose files. Only the
  client did, so an older client's job could still reach an older worker.

## 0.24.2 - 2026-11-04 - patch
- A bind or file secret that is a Unix socket is refused by its file type, and a folder holding
  a known runtime's socket by a list: Docker, containerd, CRI-O, podman, k3s, BuildKit. Only
  Docker's was known, and a read-only mount does not stop anyone talking to a socket.

## 0.24.1 - 2026-11-04 - patch
- Devices asked for through `deploy.resources` are refused, as `devices:` and `gpus:` already were.

## 0.24.0 - 2026-11-04 - minor
- Environment names that change how a job starts are refused, on the client and on the worker
  (`common/env_rules.py`): `BASH_ENV` and its like for every job, `COMPOSE_*` and `DOCKER_*` for
  a compose project. `BASH_ENV` ran project code before `up`, which could replace the checked
  file. `up` is the first line of the script, so nothing of the project runs before it now.
- design.md and agents.md say the boundary plainly: this stops a CI file's assumptions from
  reaching past the job, and does not contain a hostile project.

## 0.23.1 - 2026-11-04 - patch
- `tools/drill_compose.py`: a drill against a real Docker daemon, since the tests use a fake one
  and cannot show that generated files make resources teardown can find.
- M4 done, with what passed on a real machine and what was not run, in docs/phases.md.

## 0.23.0 - 2026-11-04 - minor
- `[job_env]` in node.toml: environment for every job on a machine, for what the machine
  needs and no project should have to know. Below a project's `env:`. Node's 250 ms limit per
  address made npm fail near 3 s on a slow network; `docs/install.md` has the setting.
- Troubleshooting says how bridges were fixed in real use, as a NetworkManager setting.

## 0.22.1 - 2026-11-04 - patch
- Port allocation probes the protocol a port is published on. It always tried TCP, so a UDP
  service on the chosen port was missed and the job failed with "address already in use".

## 0.22.0 - 2026-11-04 - minor
- A `compose:` job needs `compose-v1`, which a worker reports by itself. A worker from before
  compose offering `docker` used to claim such a job, ignore the compose file list and run
  its commands against the machine. It is now refused, with "upgrade the build machine".
  Deploy workers before clients.

## 0.21.3 - 2026-11-04 - patch
- Cleanup runs beside the worker's loop. It ran inside it, so a stuck Docker daemon could stop
  heartbeats past another job's lease, and cancels and runner supervision with them. The
  cleaning job heartbeats too, and the worker waits for cleanups when it stops. `compose
  config`, which still runs in the loop, gets a timeout that stays inside a lease.

## 0.21.2 - 2026-11-04 - patch
- A built image gets a tag only its job has, whatever `image:` and `build.tags` say; services
  using that image follow. Cleanup removes that tag by name, without force, not the image
  by id, so a tag someone else put on the same image survives.

## 0.21.1 - 2026-11-04 - patch
- A read-only bind outside the checkout must already exist, and gets `create_host_path: false`.
  Compose would otherwise create the folder on the build machine, and nothing removes it.

## 0.21.0 - 2026-11-04 - minor
- `worker/compose_policy.py` holds what a compose model may not do, and refuses more: `volumes_from`
  outside the project, `container:` namespaces, `uts`, `userns_mode` and `cgroup` on the host,
  `devices`, `cap_add` beyond a short list, `security_opt`, the Docker API, `provider`, `runtime`,
  privileged hooks and builds, non-bridge networks, non-local volumes, and any bind of a
  folder holding the Docker socket. Review found these went straight through.

## 0.20.1 - 2026-11-04 - patch
- M4 status from the real drills: M4.2 done, M4.1 and M4.3 built with what is still open.
  Troubleshooting entry for NetworkManager detaching Docker's bridges, which blocks services
  reaching each other on an affected machine.

## 0.20.0 - 2026-11-04 - minor
- Jobs from `.mulebox.yml` run with `bash -e`. A multi-line job used to report only its last
  line, so failed migrations followed by a passing line counted as passed. A job relying
  on a line being allowed to fail now needs `|| true` on it.

## 0.19.0 - 2026-11-04 - minor
- `needs: [playwright]`: jobs share one browser folder in the cache root, so a browser is
  fetched once per machine. A worker offers the capability once a person has installed the
  system libraries, which takes root. `worker/runspec.py` keeps this out of the agent loop.

## 0.18.0 - 2026-11-04 - minor
- `compose:` works. mulebox merges the project's files with `docker compose config`, rewrites
  the result (`worker/compose_file.py`) and gives the job only that file, through
  `COMPOSE_FILE` and `COMPOSE_PROJECT_NAME`, so `docker compose exec -T` needs no flags.
  Containers start before `setup`, inside the job, so the timeout, cancel and redaction apply.
- Every published port moves to 127.0.0.1 on a port mulebox picks (`worker/ports.py`), named
  by `MULEBOX_PORT_<SERVICE>_<PORT>`, so jobs clash neither with each other nor with what
  else runs on the machine. `container_name` is dropped; networks and volumes are renamed.
- Refused, with the reason: host network, PID or IPC namespace, `privileged`, external
  networks and volumes, volumes on a host device, the Docker socket, writable binds outside
  the checkout.
- A failed job's log ends with the state and last lines of its containers.
- `mulebox contract` has a `compose` key. `config.py` split: `common/config_project.py`.

## 0.17.0 - 2026-11-04 - minor
- Docker cleanup: `worker/docker.py` is the one place that runs the docker CLI and refuses
  `prune` and `system` outright; `worker/docker_cleanup.py` removes only what a listing
  filtered on one job's exact labels returned, and repeats until that listing is empty.
- `worker/reclaim.py`: root-owned files in a job folder are given back to the worker's user
  by a locked-down throwaway container, then deleted through safepath. No sudo. It mounts
  only a folder `safepath.confirm_dir` proved to be inside the jobs root.
- `worker/cleaner.py`: Docker first, folder second, on every outcome, and recovery after a
  crash from both the job folders and the labels. A folder that cannot be removed no longer
  stops the worker from starting.

## 0.16.0 - 2026-11-04 - minor
- A job whose `needs` no worker offers no longer waits forever without a word: it is refused
  at submit with what to change, and a queued job that cannot start says why in
  `waiting_for`, shown by `mulebox check` and `mulebox queue`. Details: docs/interfaces-m4.md.
- `workers.OFFLINE_AFTER_S` and `is_online` moved out of the dashboard, which now shares them.

## 0.15.0 - 2026-11-04 - minor
- `services:` in `.mulebox.yml` is now a config error that says to use `compose:` or `env:`.
  It was parsed and printed by `mulebox contract`, but nothing ever started a service.
  Removed from the contract, whose `schema` goes to 2, and from the design doc's example.
- `compose:` files are checked on the laptop: safe relative names, no repeats, present in
  the project. A `compose:` project needs a worker with `docker`, and may not set
  `COMPOSE_FILE` or `COMPOSE_PROJECT_NAME` in `env:`. Running it comes in a later change.
- `common/compose.py`: the names and filters every Docker step is derived from.

## 0.14.1 - 2026-11-04 - patch
- Docs: README, docs/install.md and the node.toml template now say the LAN password is
  optional. No behaviour change.

## 0.14.0 - 2026-11-04 - minor
- `lan_password = false` turns off the dashboard's LAN sign-in, keeping the code and the
  range and Host rules. Requested by the user; the default stays true. `/healthz` also
  returns `sign_in`, which decides whether the page shows the sign-out button.

## 0.13.0 - 2026-11-04 - minor
- `mulebox projects` (M7.4): every project the coordinator has seen, worked out from its
  jobs. New `projects` message, additive, so the protocol version stays 1; an older
  coordinator refuses it with an error.
- No project registry: it would only be a second copy of `.mulebox.yml` and the job history.

## 0.12.0 - 2026-11-04 - minor
- `mulebox feedback draft` and `post` (M7.3): agents report what mulebox could not handle as
  GitHub issues. Drafting is local; `post` needs `feedback_repo` and refuses a file the
  scrub would still change. Rules: docs/design.md, Agent feedback.
- `common/anonymize.py`: removes names, home folders, email and IP addresses and URLs, on
  top of `redact.py`.
- Screenshots from the original idea are dropped: they cannot be scrubbed automatically.

## 0.11.1 - 2026-11-04 - patch
- `skills/mulebox/`: an installable skill for coding agents (M7.2), which sends them to
  `mulebox contract` rather than copying it. Built here; installing it is the user's step.

## 0.11.0 - 2026-11-04 - minor
- `mulebox contract` (M7.1): tells an agent how this project builds, tests and uses git
  through mulebox. Generated from `.mulebox.yml` and the code's own tables, so there is no
  second copy; needs no network; `--json` has stable keys and a `schema` number.
- `ProjectNotFound`: a missing `.mulebox.yml` and a broken one are now told apart.
- docs/phases.md: new M7 for agent work, starting from the parking lot.

## 0.10.0 - 2026-11-04 - minor
- Dashboard machines panel (M2.6): every worker, online or offline, free slots and what it
  is running. New `GET /api/machines` and `machines` event.
- Job heartbeats now refresh a worker's `last_seen`. Claims stop while a worker is full, so
  a busy machine would otherwise have shown as offline for its whole job.
- Free slots are counted from active jobs, because the stored value is stale during a job.
- `coordinator/workers.py`: worker storage moved out of store.py, which neared 300 lines.

## 0.9.0 - 2026-11-04 - minor
- `lan` mode is now plain HTTP by default; HTTPS is the new optional `lan_tls = true`. User's
  decision: on a trusted home network, a browser warning on every visit is worse than no
  encryption, and installing a certificate on each device is not worth it.
- The password and range rules now follow the listener a request arrived on, not TLS.
  Without this, dropping TLS would have left the LAN port with no sign-in.

## 0.8.0 - 2026-11-04 - minor
- `lan` dashboard mode (M2.4): HTTPS on a configured address with a password, for devices
  on the LAN. The SSH tunnel keeps working. Set up with the new `mulebox dashboard cert`,
  `password` and `firewall` commands. New node.toml keys: `lan_address`, `lan_port`.
- `lan_range` must now be a private network, and `lan` mode is IPv4 only.
- Self-signed certificate marked CA, because phones only fully trust those, with name
  constraints so it is valid for one address. No new Python dependency.
- Firewall: mulebox prints a script for the operator instead of running anything as root;
  one nftables table for one port, leaving ufw, Docker and VPN clients alone.
- `mulebox-dashboard` no longer restarts on exit 2 (configuration), and a failed bind exits
  1 so that it retries. `/healthz` also returns `lan`.
- docs/phases.md: new M2.6 machines panel (next after M2.4), new M5.3 per-machine metrics.

## 0.7.1 - 2026-11-04 - patch
- docs/phases.md: parking lot ideas from the user: agent contract, installable skill, agent
  feedback through GitHub issues, project registration. No behaviour change.

## 0.7.0 - 2026-11-04 - minor
- Web dashboard (M2.1-M2.3, `local` part of M2.4): `mulebox dashboard open` on the laptop,
  service `mulebox-dashboard` on the coordinator machine. Queue, live log, history, CPU per
  core, memory, disk, Docker. Read-only and bound to 127.0.0.1; plain HTML and JS, no CDN.
  Contract: docs/interfaces-m2.md. New dependency: aiohttp.
- `common/status.py`: one status model for the terminal view and the dashboard.
- Found in real use and fixed before release: `ssh -L` joined a shared `ControlMaster` and
  exited, leaving a forward nobody held (the tunnel is now its own connection); a browser
  filter list blocked a script named `logview.js`, which blanked the page (renamed, and the
  page now says what to check if its scripts never run).
- README no longer claims LAN access, which is not built yet.

## 0.6.5 - 2026-11-04 - patch
- M3.3 done. A runner recovers from a hard kill by itself (GitHub drops the old session
  after ~3 min). Reboot drill passed with an agent job running and a CI job waiting; sudden
  power loss was not tested. Recovery times are in docs/interfaces-m3.md.

## 0.6.4 - 2026-11-03 - patch
- docs/phases.md: M3.1 and M3.2 done; M3.3 drill results (overlap, cancelled run, runner
  crash passed; GitHub session conflict after a hard kill and the reboot drill still open).
  Repository CI is now 16 s warm (was 47 s). M2 started on branch m2-dashboard.

## 0.6.3 - 2026-11-03 - patch
- Faster repository CI: tests run in parallel (`pytest-xdist`, `-n auto`; 23 s -> 5 s on
  the laptop), the venv is kept in the runner tool cache and rebuilt only when
  `pyproject.toml` changes. A parametrized protocol test now collects in a fixed order
  (it iterated a set, which xdist rejects).

## 0.6.2 - 2026-11-03 - patch
- Fixes from the first CI run on a mulebox runner (Linux, Python 3.12.3, the minimum):
  - `test_stream_early_stop_reaps_process` expected stderr closed; since 0.5.1 reap leaves
    a pipe to its still-waiting reader (another process held it on Linux). Test corrected.
  - GitHub does not tell hooks the job's result, so a released runner slot showed as
    "passed". Queue entries now carry `kind`; `mulebox queue` shows runner slots as
    `released` (the real result is on GitHub).

## 0.6.1 - 2026-11-03 - patch
- Repository CI (`.github/workflows/ci.yml`): the test suite on a mulebox runner by default,
  switchable with the `CI_RUNS_ON` repository variable. First real use of M3.

## 0.6.0 - 2026-11-03 - minor
- M3 GitHub runners, built in parallel on two branches:
  - Slot reservations: runner job-started/completed hooks reserve a slot pinned to the
    worker in the same FIFO queue as agent jobs (`reserve`, `acquire`, `release`,
    `runner_jobs`); the worker supervises runners and releases a crashed runner's slot
    after 60 s. Store schema 2 with an in-place migration.
  - Runner management: `mulebox runner register|unregister --repo owner/name` on the
    laptop (token from `gh`, sent on stdin), `mulebox runner add|list|remove` on the build
    machine (latest actions/runner release, checksum verified, `mulebox-runner@` user
    unit). The token never appears in argv or logs.
- `.mulebox.yml` `env:` for throwaway CI values; `${MULEBOX_JOB_ID}` / `${MULEBOX_JOB_SLUG}`
  and earlier entries expand, no shell. Store schema 3.
- docs/agents.md: a guide for coding agents (everyday use, setting a project up, moving
  GitHub Actions to mulebox runners); linked from the README.
- Shared download/verify code in `mulebox/common/download.py`.

## 0.5.3 - 2026-11-03 - patch
- docs/interfaces-m3.md: contract for GitHub runners (slot reservations through runner
  hooks, supervision, runner install from the laptop), so M3 can be built in parallel.
- `mulebox/runners/` package stubs wired into the CLI.

## 0.5.2 - 2026-11-03 - patch
- Client lease 120 s -> 300 s, and the client keeps reconnecting the live view for up to
  4 min (24 tries, 10 s apart): a real build machine on Wi-Fi dropped off for ~3 min, which
  would have cancelled a healthy job.
- After giving up on the live view, the client says the job keeps running and how to
  read its result (`WatchLost`), instead of the wrong "the job was not run".
- docs/phases.md: M1.6 done (real project passes, broken commit fails like locally); M1
  complete.

## 0.5.1 - 2026-11-03 - patch
- Fixes found by running M1.5 / M1.8 / M1.9 on a real build machine:
  - Ctrl-C took up to 2 minutes: closing an ssh pipe waited on a reader thread still
    blocked on it. `ssh.reap` no longer closes a pipe a live thread is reading.
  - A crashed worker's jobs stayed "running" until the 120 s worker lease ran out. The
    first claim after a worker start now carries `restarted: true` and the coordinator
    interrupts the jobs that worker still held (`recovery.release_worker`).
  - An ssh process killed by a signal counts as a lost connection (`SSHUnavailable`), so
    the watch stream reconnects instead of failing.
- docs/phases.md: M1.5, M1.8 and M1.9 done.

## 0.5.0 - 2026-11-03 - minor
- M1.4 coordinator (`mulebox/coordinator/`): SQLite store (WAL, `BEGIN IMMEDIATE`),
  atomic claim with cluster slots, idempotent submit, client and worker leases, restart
  recovery, upload staging with hash check and size cap, logs, `rpc` / `rpc-upload` /
  `rpc-download`, the watch stream, `coordinator serve`.
- M1.5 worker (`mulebox/worker/`): claim loop, safe workspace extraction plus a local git
  commit, systemd and subprocess executors, log tailing through the redactor, heartbeats
  and cancel, recovery of orphan units and job folders, node/pnpm toolchain install.
- M1.6 / M1.7 client (`mulebox/client/`): snapshot with built-in secret excludes, upload,
  submit, live log, exit codes like a local run, Ctrl-C cancel, stale warning, `queue`
  (with a live view), `logs`, `cancel`.
- M1.8 install (`install/`, `tools/deploy.sh`, docs/install.md): build-machine install as
  two systemd user services; never deletes, never uses sudo.
- Integration: worker local link wired to the coordinator; one shared line cap
  (`protocol.MAX_LINE_BYTES`); ssh helpers made public instead of reached into; worker
  heartbeat 3 s so a cancel lands in seconds; finished status replies carry the duration;
  `.envrc` and `.netrc` added to the secret excludes.
- Verified end to end on one machine with a fake ssh: pass, fail (same exit code),
  `mulebox cancel`, Ctrl-C (exit 130 in 1 s, no processes or folders left).
- docs/interfaces-m1.md: decisions made during the build.

## 0.4.1 - 2026-11-03 - patch
- docs/interfaces-m1.md: contract for the coordinator, worker, client and install script
  (M1.4 - M1.8), so they can be built in parallel. M1 simplifications recorded there (full
  snapshot instead of a build-machine clone, `rpc` opens SQLite directly).
- Protocol: message types `queue`, `queue_ok`, `logs`, `watch`.
- Package stubs `client/`, `coordinator/`, `worker/` with `commands.register`; the CLI
  dispatches to each subcommand's handler.

## 0.4.0 - 2026-11-03 - minor
- M1.3 `mulebox/common/safepath.py` (+ `roots.py`, `mounts.py`): the only code that
  deletes. Roots validated once (no `/`, home, system folders or overlaps; device and inode
  recorded). Deletion and creation anchored on directory descriptors with `O_NOFOLLOW`;
  the walk never follows symlinks, never leaves the root's mount (Linux mount ids from
  `/proc/self/mountinfo` and fdinfo, macOS `st_dev` + `ismount`), refuses mount points.
  Permission failures raise `RemovalDenied`; no escalation in this module.
- Tests cover symlink swaps mid-check and mid-walk, simulated mounts, prefix lookalikes,
  fd leaks; also run on Linux in a container.
- Known gaps: a directory renamed out of the root by someone with write access mid-delete;
  same-device mounts undetectable on macOS; real mounts only simulated in tests.
- README: rerun the editable install after a VERSION bump.

## 0.3.0 - 2026-11-03 - minor
- M1.2 shared modules in `mulebox/common/`, built in parallel to docs/interfaces.md:
  - `ids.py`: prefixed ULIDs (`job-...`), validation, timestamps.
  - `log.py`: idempotent setup of the `mulebox` logger, text or JSON lines.
  - `config.py` + `config_reader.py`: `.mulebox.yml`, `client.toml`, `node.toml`, strict
    validation (unknown keys, ranges, CIDR, ssh targets); errors name file and field.
  - `protocol.py`: versioned JSON-line messages, required body fields per type, job state
    machine (no self-transitions; finished is terminal).
  - `ssh.py`: argv-only subprocess, `--` before the `shlex.join` remote command, exit 255
    as `SSHUnavailable`, `RemoteError` / `RemoteTimeout`, streaming without deadlocks.
  - `redact.py`: known secrets and token patterns blanked; `StreamRedactor` catches secrets
    split across chunks.
- PyYAML 6.0.3 pinned as the first runtime dependency.
- docs/interfaces.md: additions found while building (see "Decisions made in M1.2").
- Known gaps: duplicate YAML keys are not detected; `decode` has no line-size cap (the
  reader must cap it); `RemoteError.stderr` is raw and must be redacted by callers.

## 0.2.1 - 2026-11-03 - patch
- docs/interfaces.md: the API contract for the shared modules (ids, log, config, protocol,
  ssh, redact, safepath), so they can be built in parallel.
- `mulebox/common/` package with the base `MuleboxError`.

## 0.2.0 - 2026-11-03 - minor
- M1.1 package skeleton: `pyproject.toml` (Python 3.12+, setuptools 84.2.1, version read
  from VERSION), `mulebox` CLI entry point with `--version` / `version`, pytest 9.2.0 as the
  pinned dev dependency, tests for the CLI and version source.
- File-size rule enforced in code: `tools/check_line_counts.py` warns above 300 lines and
  fails at 500; the test suite runs it on the whole repository.
- README: development section (venv, install, tests).

## 0.1.0 - 2026-11-03 - minor
- Project created from the design work in a private setup repo: README, design, roadmap
  (docs/phases.md), versioning and project-log rules, agent rules.
- Design reviewed by an external model (core queue, dashboard, multiple machines); the
  adopted changes are part of docs/design.md.
- Groundwork measured on a real setup (M4 Pro laptop vs a 2014 4-core i7 on Wi-Fi): the old
  machine ran two real CI suites 1.8x and 3.5x slower than the laptop, but 2-3x faster than
  GitHub-hosted runners, with the laptop left idle. Basis for "offload, then queue".
