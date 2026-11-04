# Project log

Every change to this repository is logged here, newest first, in the same commit as the
change, together with the version bump it causes. Rules: [AGENTS.md](AGENTS.md) (Versioning).

Entry format:

    ## <version> - <YYYY-MM-DD> - <patch|minor|major>
    - what changed and why (one line each)

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
