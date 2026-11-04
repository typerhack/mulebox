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
      and by the app's own check; the tunnel still works. The password is optional since
      0.14.0, off on the author's machine. Open: used from a real phone, and a reboot and a
      Wi-Fi drop with `lan` on.
- [ ] M2.5 Optional cancel button with its own protection
- [x] M2.6 Machines panel: every worker, online or offline, free slots. Live CPU and memory
      per machine is M5.3. Done 2026-11-04 (0.10.0): in real Chrome on a real machine, a job
      showed busy with nothing free for its whole run; a frozen worker showed offline in 14 s
      and came back in 2 s, and its job still passed. Only one real worker so far; more
      than one is covered by tests.
- [~] M2.7 Monitor redesign: boxed live view with meters and graphs, one theme, icon switch.
      Built 2026-11-04 (0.25.0): in real Microsoft Edge the theme switch and its memory, the
      queue, job and history views work, with no sideways scroll in a 390 px frame; the page
      fits without scrolling at 1440x900 and 1280x800 in headless Chrome. Deployed on a real
      machine: a compose job at full load moved the graph and meters live in Edge, with no
      console errors. Open: a real phone.

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
- [x] M4.1 `compose:` services in `.mulebox.yml`; unique project names and labels per job.
      Done 2026-11-04 (0.23.0): on a real machine, two compose files merged, `env:` reached
      compose, `docker compose exec -T` and `setup` worked, ports asked for 6379 and 27017
      (one held by a running database) moved to 127.0.0.1, `depends_on` on a one-shot passed,
      a job needing docker with no capable worker was refused at once. Over the job's own
      network, a real MySQL and Redis stack: a client reached both by name, wrote and read a
      table, and the network was gone afterwards. `tools/drill_compose.py` shows on a real
      daemon that generated files make labelled resources teardown finds. Not run: a real
      Laravel project.
- [x] M4.2 Teardown on every outcome; root-owned file cleanup through safepath.
      Done 2026-11-04 (0.20.0, cleanup beside the loop 0.21.3): on a real machine, passed,
      failed, cancelled (also during `up --wait`), timed out (exit 124 in 1m01s), failed setup,
      a worker hard kill (also during `up --wait`) followed by a restart, and a clean worker
      restart each left no labelled container, network or volume, no job folder and no unit.
      Containers of a killed worker were removed by label on restart. Root-owned files, a 700
      folder, a 000 file and a symlink to /etc/passwd were cleaned with no sudo. Built images
      removed, base images and build cache kept. A database, a GitHub runner and a foreign
      volume stayed untouched. Not covered: sudden power loss; a Docker daemon that really
      hangs (a stand-in in the tests only).
- [x] M4.3 Browser test support (Playwright dependencies on workers). Done 2026-11-04
      (0.23.0): on a real machine offering `playwright`, a job with `needs: [playwright]` got
      the shared browser folder, ran `playwright install --only-shell chromium`, drove real
      Chromium against a container through `MULEBOX_PORT_...`, and left nothing behind. The
      browser was copied into that folder beforehand to spare a large download, so a job
      fetching one itself has not run.

## M5: More machines
- [ ] M5.1 Separate worker install; register, capabilities, warm-up
- [ ] M5.2 Draining and removing workers; moving the coordinator (documented)
- [ ] M5.3 Workers report CPU and memory; the dashboard shows them per machine

## M6: Open-source readiness
- [x] M6.1 License: MIT, chosen by the user. (2026-11-04, 0.25.2)
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
- [~] M7.2 Installable skill: `skills/mulebox/`, installed once system-wide, so any project
      can say "use the mulebox skill". Built 2026-11-04 (0.11.1). Open: the user installs it
      in another session, and an agent uses it in a real project.
- [~] M7.3 Agent feedback: `mulebox feedback draft` and `post`, redacted first. Built
      2026-11-04 (0.12.0): a real failed job with fake private output left no project,
      branch, identity, address, password or machine name in its draft; `post` sent the
      reviewed file to a stand-in `gh` and refused a tampered one. Screenshots dropped: they
      cannot be scrubbed. Open: the user sets `feedback_repo`, and one real issue is posted.
- [x] M7.4 Projects: `mulebox projects`, worked out from the job history. A registry was
      dropped: it would hold nothing beyond `.mulebox.yml` and that history, so it would
      only be a second copy. Done 2026-11-04 (0.13.0): run against a real coordinator.

## M9: Faster and clearer jobs
Worked out from the first real jobs on a slow connection (2026-11-04). Everything here is
tested with fakes and a local Docker daemon. Open on all of it: a real job on a build machine.
- [~] M9.1 Package caches: `needs: [cache-pnpm]`, `[cache-composer]`, one folder per project,
      mounted by the project's own compose file, external volumes still refused. Built
      2026-11-04 (0.26.0). Open: a real pnpm and a real Composer project on a build machine,
      with a second job showing the packages as reused.
- [~] M9.2 `job_env` reaches compose services. Before, it reached only the `docker compose`
      process; a real container showed no `NODE_OPTIONS`. Built 2026-11-04 (0.27.0). Open: a
      real install in a container over the slow connection.
- [~] M9.3 Services get 65536 open files unless they set their own. Built 2026-11-04 (0.28.0).
      Open: the real `mongo` test run that died with WiredTiger error 24.
- [~] M9.4 Job steps: `job_steps` table with a migration, reported by the worker, read through
      `status` and `common/status.py`. No view yet. Built 2026-11-04 (0.29.0): a compose job
      on a local Docker daemon. Open: a job on a build machine under systemd.
- [~] M9.5 Usual duration of a project's job and of each stage, in `status` replies. Built
      2026-11-04 (0.30.0), with tests. Open: seeing it on real history.

## Parking lot
- Project registry, if real adoption finds something that belongs neither in `.mulebox.yml`
  nor in the job history (reasoning: docs/design.md, Projects)
- MCP wrapper over the client commands
- More than one slot per worker, or job weights, once measurements justify it
- macOS or Windows workers
