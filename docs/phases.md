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

## M1: Core queue, one machine, terminal only  (done 2026-11-03, 0.5.2)
Goal: `mulebox check` from a project worktree runs the job on a build machine through the
queue and returns the same result as running it locally.
- [x] M1.1 Package skeleton: `pyproject.toml`, `mulebox` CLI entry point, pinned deps,
      test runner, line-count check (fails on files over 500 lines, warns over 300).
      Done 2026-11-03 (0.2.0): 7 tests pass on Python 3.13. Not yet run on 3.12, the
      minimum; covered when M1.8 installs on a Linux build machine.
- [x] M1.2 `common/`: config, protocol (versioned JSON), ssh, ids, log, redact. (2026-11-03, 0.3.0)
- [x] M1.3 `common/safepath.py`: roots, symlink and mount checks, descriptor-anchored delete. (2026-11-03, 0.4.0)
      Done when: tests cover escapes, mounts, races and relative paths.
- [x] M1.4 Coordinator: SQLite store, states, atomic claim, leases, idempotent submit,
      restart reconciliation. Done when: concurrency, lease-expiry and restart tests pass.
      Done 2026-11-03 (0.5.0): threads and processes claim at once, no double claims.
- [x] M1.5 Worker: claim loop, workspace from snapshot + local clone, systemd-run executor
      with limits, cleanup. Done when: run, timeout and cancel leave no processes behind.
      Done 2026-11-03 (0.5.1): on a real Ubuntu machine with the systemd executor, run,
      timeout (exit 124), cancel and Ctrl-C leave no units, processes or job folders.
- [x] M1.6 Client: snapshot with secret excludes, upload, submit, wait, stream, exit code,
      Ctrl-C cancel. Done when: a real project passes, and a broken commit fails with the
      same error as locally. Done 2026-11-03 (0.5.2): a real Next.js project's full gate
      passed on a build machine (3 min 42 s); a type error failed with the same tsc
      message and exit code 2 as locally.
- [x] M1.7 `mulebox queue`, `logs`, `cancel`, and the live terminal view. (2026-11-03, 0.5.0)
- [x] M1.8 Install script for a build machine (coordinator + worker, systemd user service).
      Note: Ubuntu does not ship `python3-venv` by default; the script must check for it
      and say how to install it. Run the test suite on the machine's Python (3.12 minimum).
      Done 2026-11-03 (0.5.1): `tools/deploy.sh` installed and upgraded a real machine.
- [x] M1.9 Failure drills: machine unreachable, network drop mid-job, daemon restart
      mid-job, two clients at once. Done 2026-11-03 (0.5.1): unreachable -> exit 3 in the
      connect timeout; dropped connection -> reconnect, job passes; worker restart and hard
      kill -> interrupted (exit 75) in seconds, orphan unit stopped; client killed -> job
      cancelled by lease expiry; two clients -> run one after the other.

## M2: Web dashboard
- [x] M2.1 Shared status/event model (also used by the terminal view) (2026-11-04, 0.7.0)
- [x] M2.2 aiohttp server: queue, live log over SSE, history. Done 2026-11-04 (0.7.0):
      used in a real browser through the tunnel on a real machine; live log, job end,
      history filter and reconnect after a service restart work.
- [x] M2.3 Resource graphs (CPU per core, memory, disk, Docker); measure overhead.
      Done 2026-11-04 (0.7.0): 0.48% of one core (0.06% of a 4C/8T machine) and 44 MB over
      60 s with one viewer and a live log open.
- [~] M2.4 Access modes `local` (SSH tunnel) and `lan` (password, firewall range; HTTPS
      optional since 0.9.0, user's choice). `local` done 2026-11-04 (0.7.0). `lan` built
      2026-11-04 (0.8.0, plain HTTP 0.9.0): on a real machine, sign-in, live events, session
      end and sign-out work in real Chrome; outside addresses are stopped by the firewall
      and by the app's own check; the tunnel still works. Open: used from a real phone, and
      a reboot and a Wi-Fi drop with `lan` on.
- [ ] M2.5 Optional cancel button with its own protection
- [x] M2.6 Machines panel: every worker, online or offline, free slots. Live CPU and memory
      per machine is M5.3. Done 2026-11-04 (0.10.0): in real Chrome on a real machine, a job
      showed busy with nothing free for its whole run; a frozen worker showed offline in 14 s
      and came back in 2 s, and its job still passed. Only one real worker so far; more
      than one is covered by tests.

## M3: GitHub Actions runners
- [x] M3.1 Runner install per repository on a worker, as a service, with labels (2026-11-03)
- [x] M3.2 Start/complete hooks with pinned slot reservation, timeout, supervision (2026-11-03)
- [x] M3.3 Example workflow snippet; drills for cancelled runs, crashes and reboots
      Done 2026-11-04 (0.6.5). Passed 2026-11-03: overlap (CI waits behind an agent job),
      cancelled run (slot freed in ~20 s), runner killed mid-job (supervision freed the
      slot after 60 s, unit restarted). After that hard kill GitHub kept the old runner
      session for ~3 min; the runner retried and reconnected by itself. Reboot drill on a
      real machine, with an agent job running and a CI job waiting: back in 66 s, services
      up unattended, agent job `interrupted` (exit 75, not replayed), nothing left behind,
      the waiting reservation released after 60 s, the next CI run passed. Not covered:
      sudden power loss (a clean reboot lets the worker report the job as it stops).

## M4: Docker Compose projects
- [ ] M4.1 `compose:` services in `.mulebox.yml`; unique project names and labels per job
- [ ] M4.2 Teardown on every outcome; root-owned file cleanup through safepath
- [ ] M4.3 Browser test support (Playwright dependencies on workers)

## M5: More machines
- [ ] M5.1 Separate worker install; register, capabilities, warm-up
- [ ] M5.2 Draining and removing workers; moving the coordinator (documented)
- [ ] M5.3 Workers report CPU and memory; the dashboard shows them per machine

## M6: Open-source readiness
- [ ] M6.1 Choose a license (user decision)
- [ ] M6.2 User docs: install, configure a project, agent rules snippet, troubleshooting
- [ ] M6.3 Repository CI for mulebox itself; release process (tag on MAJOR releases)
- [ ] M6.4 Security review; scan history for personal data before going public
- [ ] M6.5 1.0.0 release (only when the user declares it)

## M7: Agents
Order agreed with the user on 2026-11-04.
- [x] M7.1 Agent contract: `mulebox contract`, generated from `.mulebox.yml` and the code's
      own tables, so there is one source. Done 2026-11-04 (0.11.0): run through the real CLI
      in a project, outside one and with the build machine unreachable. Drift tests tie it
      to the real commands and to docs/agents.md.

## Parking lot
- Installable mulebox skill: installed once system-wide, so any project can say "use the
  mulebox skill" instead of pointing at docs/agents.md. The skill is built here; installing
  it is the user's step, in another session
- Agent feedback: agents file GitHub issues about what mulebox could not handle, with
  enough logs and screenshots to reproduce (redacted first, no secrets or private data)
- Project registration: each project registers with mulebox and stays registered, to avoid
  copy-pasted setup and to manage projects later
- MCP wrapper over the client commands
- More than one slot per worker, or job weights, once measurements justify it
- macOS or Windows workers
