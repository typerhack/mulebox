# Roadmap (phases)

Single source of truth for what is done and open. Design: [design.md](design.md).

How to use it:
- "What is open?" -> the first unfinished phase and its open tasks.
- Mark `[~]` when started, `[x]` only when the "done when" check passed (add the date).
- Every finished task is a change: bump [../VERSION](../VERSION) and log it in
  [../PROJECT_LOG.md](../PROJECT_LOG.md) (rules in [../AGENTS.md](../AGENTS.md)).
- New ideas go to "Parking lot", not into the current phase.
- Status: `[ ]` open, `[~]` in progress, `[x]` done, `[-]` dropped (say why).

## M0: Project setup  (0.1.0, 2026-11-03)
- [x] M0.1 Repo, README, design, roadmap, versioning and project-log rules
- [x] M0.2 Design reviewed (core, dashboard, multiple machines)

## M1: Core queue, one machine, terminal only
Goal: `mulebox check` from a project worktree runs the job on a build machine through the
queue and returns the same result as running it locally.
- [x] M1.1 Package skeleton: `pyproject.toml`, `mulebox` CLI entry point, pinned deps,
      test runner, line-count check (fails on files over 500 lines, warns over 300).
      Done 2026-11-03 (0.2.0): 7 tests pass on Python 3.13. Not yet run on 3.12, the
      minimum; covered when M1.8 installs on a Linux build machine.
- [x] M1.2 `common/`: config, protocol (versioned JSON), ssh, ids, log, redact. (2026-11-03, 0.3.0)
- [ ] M1.3 `common/safepath.py`: roots, symlink and mount checks, descriptor-anchored delete.
      Done when: tests cover escapes, mounts, races and relative paths.
- [ ] M1.4 Coordinator: SQLite store, states, atomic claim, leases, idempotent submit,
      restart reconciliation. Done when: concurrency, lease-expiry and restart tests pass.
- [ ] M1.5 Worker: claim loop, workspace from snapshot + local clone, systemd-run executor
      with limits, cleanup. Done when: run, timeout and cancel leave no processes behind.
- [ ] M1.6 Client: snapshot with secret excludes, upload, submit, wait, stream, exit code,
      Ctrl-C cancel. Done when: a real project passes, and a broken commit fails with the
      same error as locally.
- [ ] M1.7 `mulebox queue`, `logs`, `cancel`, and the live terminal view.
- [ ] M1.8 Install script for a build machine (coordinator + worker, systemd user service).
      Note: Ubuntu does not ship `python3-venv` by default; the script must check for it
      and say how to install it. Run the test suite on the machine's Python (3.12 minimum).
- [ ] M1.9 Failure drills: machine unreachable, network drop mid-job, daemon restart
      mid-job, two clients at once.

## M2: Web dashboard
- [ ] M2.1 Shared status/event model (also used by the terminal view)
- [ ] M2.2 aiohttp server: queue, live log over SSE, history
- [ ] M2.3 Resource graphs (CPU per core, memory, disk, Docker); measure overhead
- [ ] M2.4 Access modes `local` (SSH tunnel) and `lan` (password, HTTPS, firewall range)
- [ ] M2.5 Optional cancel button with its own protection

## M3: GitHub Actions runners
- [ ] M3.1 Runner install per repository on a worker, as a service, with labels
- [ ] M3.2 Start/complete hooks with pinned slot reservation, timeout, supervision
- [ ] M3.3 Example workflow snippet; drills for cancelled runs, crashes and reboots

## M4: Docker Compose projects
- [ ] M4.1 `compose:` services in `.mulebox.yml`; unique project names and labels per job
- [ ] M4.2 Teardown on every outcome; root-owned file cleanup through safepath
- [ ] M4.3 Browser test support (Playwright dependencies on workers)

## M5: More machines
- [ ] M5.1 Separate worker install; register, capabilities, warm-up
- [ ] M5.2 Draining and removing workers; moving the coordinator (documented)

## M6: Open-source readiness
- [ ] M6.1 Choose a license (user decision)
- [ ] M6.2 User docs: install, configure a project, agent rules snippet, troubleshooting
- [ ] M6.3 Repository CI for mulebox itself; release process (tag on MAJOR releases)
- [ ] M6.4 Security review; scan history for personal data before going public
- [ ] M6.5 1.0.0 release (only when the user declares it)

## Parking lot
- MCP wrapper over the client commands
- More than one slot per worker, or job weights, once measurements justify it
- macOS or Windows workers
