# Project log

Every change to this repository is logged here, newest first, in the same commit as the
change, together with the version bump it causes. Rules: [AGENTS.md](AGENTS.md) (Versioning).

Entry format:

    ## <version> - <YYYY-MM-DD> - <patch|minor|major>
    - what changed and why (one line each)

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
