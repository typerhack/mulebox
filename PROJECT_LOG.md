# Project log

Every change to this repository is logged here, newest first, in the same commit as the
change, together with the version bump it causes. Rules: [AGENTS.md](AGENTS.md) (Versioning).

Entry format:

    ## <version> - <YYYY-MM-DD> - <patch|minor|major>
    - what changed and why (one line each)

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
