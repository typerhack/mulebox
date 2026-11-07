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
      0.14.0, off on the author's machine. Open: a reboot and a Wi-Fi drop with `lan` on. Not a
      priority, the user's call on 2026-11-06. Phone-size view: see M2.7.
- [x] M2.5 Optional cancel button with its own protection. Built 2026-11-05 (0.53.0): off by default,
      only for a signed-in session on the lan address, through `mulebox rpc` like `mulebox cancel`,
      with Origin and a session token on top of SameSite. In real Edge on localhost with a stand-in
      worker: two-step cancel of a queued and a running job; pages on another port and site changed
      nothing. Done 2026-11-06 (0.64.1): at the
      real LAN address over plain HTTP at 390x844 in headless Edge, a throwaway dashboard with a password
      and two real jobs, one queued and one running, both cancelled in two steps. No cookie gave 401; a
      wrong origin and a missing token gave 403. The session was made in its process, as no password may
      be typed there by an agent; signing in itself was seen in M2.4.
- [x] M2.6 Machines panel: every worker, online or offline, free slots. Live CPU and memory
      per machine is M5.3. Done 2026-11-04 (0.10.0): in real Chrome on a real machine, a job
      showed busy with nothing free for its whole run; a frozen worker showed offline in 14 s
      and came back in 2 s, and its job still passed. Only one real worker so far; more
      than one is covered by tests.
- [x] M2.7 Monitor redesign: boxed live view with meters and graphs, one theme, icon switch.
      Built 2026-11-04 (0.25.0): in real Microsoft Edge the theme switch and its memory, the
      queue, job and history views work, with no sideways scroll in a 390 px frame; the page
      fits without scrolling at 1440x900 and 1280x800 in headless Chrome. Deployed on a real
      machine: a compose job at full load moved the graph and meters live in Edge, with no
      console errors. Done 2026-11-06 (0.55.2): at phone size (390x844, the user's choice over a real
      phone) in Edge on the deployed dashboard, a live job and its question, no sideways scroll.
- [x] M2.8 Jobs box redesign: tabs (Queue, Failed, Passed, Recent, with live counts,
      remembered per browser) and the queue by machine: a lane per machine with what it
      runs and what waits for it, waiting jobs in exactly one place (a lane only when that
      machine is the one place the job can run, else one shared list, else stuck with the
      coordinator's reason). The Machines box stays in the top row and gains a small CPU
      and memory meter per machine, real only for the dashboard's own machine until M5.3
      (the rest read "no live data"). Built 2026-11-04 (0.26.0): in headless Chrome with
      one, three (one offline) and no machines, stuck and pinned jobs, at 1440x900,
      1280x800 and 390 px in both themes, the page fits and nothing scrolls sideways.
      Reviewed 2026-11-05 (0.51.3) in real Edge on a real machine: lanes, tabs, a live job, and no
      sideways scroll at 544 px; 390 px on 2026-11-06 (0.55.2). The redesign itself is M14.1.

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
- [~] M6.2 User docs: install, configure a project, agent rules snippet, troubleshooting. Written
      2026-11-05 (0.52.1). Open: a stranger's first passing `mulebox check` from them alone.
- [x] M6.3 Repository CI for mulebox itself; release process (tag on MAJOR releases). Done 2026-11-05
      (0.52.1): passed on GitHub-hosted machines on Python 3.12 and 3.13; docs/releasing.md.
- [~] M6.4 Security review; scan history for personal data before going public. Reviewed
      2026-11-05 (0.52.0): 7 fixes, the worst being fork pull requests on self-hosted runners, with a
      security model in docs/install.md. All 143 commits and local branches scanned: no secrets or
      addresses. History rewritten and pushed the same day: project names, author line and time zone
      are gone. Open: a real fork pull request on GitHub.
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

## M8: Agents at work
From real use by agents on 2026-11-04: an agent sat blocked on `mulebox check` for the whole
job, a missing toolchain showed only after submission, and the error offered no alternative.
Marked `[~]` until checked on a real machine.
- [x] M8.1 A missing toolchain error lists the versions the machine has. Tested 2026-11-04 (0.25.4)
      by unit tests only. Done 2026-11-05 (0.53.1): a real job asked for a node version the machine
      lacks: exit 5, stage `environment`, and the log listed the versions it has.
- [x] M8.2 Short failure summary at the end of a failed job, and `mulebox logs <id> --summary`.
      Tested 2026-11-04 (0.26.0) with unit tests and the fake coordinator. The failed stage comes
      from the job's stage rows since 0.35.0, tested with the real coordinator code. 0.52.2 keeps the failure itself in the summary. Done 2026-11-06 (0.62.2): a real failed
      compose job with a noisy Mongo service, the summary came last and showed the line before the failure.
- [x] M8.3 `mulebox doctor`, read-only: validates `.mulebox.yml`, reports toolchains and
      capabilities per machine, warns on a version difference. Workers report toolchains and version
      with every claim (schema 4). Tested 2026-11-04 (0.27.0) with the fake coordinator and the real
      coordinator code. Done 2026-11-05 (0.53.1): against a real machine, toolchains, capabilities,
      compose refusals and a version difference reported correctly.
- [x] M8.4 `mulebox check --detach` and `mulebox wait <id>`. Detached jobs are skipped by the client
      lease sweep (schema 5). Tested 2026-11-04 (0.28.0) with the real client and coordinator code
      through a local stand-in for ssh: survives lease expiry queued and running, `wait` matches an
      attached run in output, summary and exit code. Run 2026-11-05: a running detached job outlived
      its killed clients and the lease, and a later `wait` gave its result. Done 2026-11-06 (0.62.2): a detached job queued behind another with no
      client left ran, and `wait` gave its failure, summary and exit 7. The 5 min lease expiry itself was
      not waited for while queued; M18.1 saw a queued job outlive its client.
- [x] M8.5 `mulebox events --job <id> --json` and `mulebox status <id>`, on the coordinator's
      `watch` stream and the shared status model, open for later `stage` and `check_in` events.
      Tested 2026-11-04 (0.29.0) with the real coordinator code: position changes, machine, outcome,
      exit code, no log text; with the fake: a dropped stream repeats nothing and keeps the final
      line. Done 2026-11-05 (0.53.1): the Monitor tool followed a real compose job through the queue
      to its end, and `events` on a failed job exited with its code.
- [x] M8.6 While queued, `check` prints its position and suggests `--detach` for a long wait. The
      estimate design.md promised did not exist: there is now a labelled one, how long the job
      usually runs, from its past passed runs, and none of the time in line; design.md says so.
      Tested 2026-11-04 (0.30.0) with the fake coordinator and the real store. Done 2026-11-05
      (0.53.1): in a real queue of over 20 jobs, `check` printed its position, the labelled estimate
      and the `--detach` hint. A job at position 1 behind a long job still gets no suggestion.
- [x] M8.10 `mulebox logs`, `logs --summary` and `wait` say when a job's log has expired, so
      an empty answer is not read as an empty log. Tested 2026-11-04 (0.34.0) with the real
      coordinator code; since 0.35.0 a test removes the log with the real retention code.
      Done 2026-11-06 (0.62.2): `logs`, `logs --summary` and `wait` through the
      real CLI against a copy of the machine's history after the real service cleaned it.
- [~] M8.9 `mulebox doctor` runs the worker's compose policy on the project's files before any
      upload, so an external volume fails at once rather than after the queue. Tested
      2026-11-04 (0.33.0) with unit tests and the fake coordinator, and the steps it copies
      from `docker compose config` (profiles, unused resources, relative paths) were read off
      a local Docker client. Open: a real project's compose files. It does not read `include`
      or `extends` files, or values with variables.
- [x] M8.8 A job that could not start exits 5, not 1, so it does not read as a failed check. Tested
      2026-11-04 (0.32.0) with unit tests and the real coordinator code. Done 2026-11-05 (0.53.1): a
      job with a missing toolchain and one with a refused compose file each exited 5, with the
      reason in the summary.
- [~] M8.7 Skill versioning: the skill ships in the package (`skills/mulebox/SKILL.md` links
      to it), `mulebox skill install|update|status` over every Claude config folder, the skill
      states its contract schema, `mulebox doctor` reports it, a test ties the two. Tested
      2026-11-04 (0.31.0) with temporary folders only; the wheel holds SKILL.md. Open: the
      user installs it, and an agent notices a behind skill in a real session (see M7.2).

## M9: Faster and clearer jobs  (done 2026-11-06, 0.62.2)
Worked out from the first real jobs on a slow connection (2026-11-04).
- [x] M9.1 Package caches: `needs: [cache-pnpm]`, `[cache-composer]`, one folder per project,
      mounted by the project's own compose file, external volumes still refused. Built 2026-11-04
      (0.35.0). Run 2026-11-05: pnpm showed `reused 73, downloaded 0` on a second job. Done 2026-11-06 (0.62.2): a job in `composer:2` filled the cache, and a
      second installed with vendor removed and `COMPOSER_DISABLE_NETWORK=1`.
- [x] M9.2 `job_env` reaches compose services. Before, it reached only the `docker compose` process;
      a real container showed no `NODE_OPTIONS`. Built 2026-11-04 (0.35.0). Done 2026-11-05
      (0.53.1): a real pnpm install in a container, over a slow connection, saw the machine's
      `NODE_OPTIONS` with none set in the service.
- [x] M9.3 Services get 65536 open files unless they set their own. Built 2026-11-04 (0.35.0). Done 2026-11-06 (0.62.2): a real
      Mongo 8.2 service reported 65536 and took a write.
- [x] M9.4 Job steps: `job_steps` table with a migration, reported by the worker, read through
      `status` and `common/status.py`, shown by `mulebox status`. The failed stage reaches the
      summary and `events`. The dashboard shows them since 0.50.0. Built 2026-11-04 (0.35.0): a
      compose job on a local Docker daemon. Done 2026-11-05 (0.53.1): under systemd, a compose job
      showed its stages live and all seven at the end, and a failed job's summary named the stage.
- [x] M9.5 Usual duration of a project's job and of each stage, in `status` replies. The one source
      now: the queue estimate of M8.6 reads it too. Built 2026-11-04 (0.35.0), with tests. Done
      2026-11-05 (0.53.1): on real history a slow first run left the median alone, and the queue
      estimate reads the same figure.
- [x] M9.6 Image pull progress collapsed in stored and streamed logs, after redaction, with bytes on
      the stage. Built 2026-11-04 (0.35.0): samples from a real Compose 5.6 pull, and a pull through
      the worker on a local Docker daemon. Done 2026-11-05 (0.53.1): a 10 min pull of a 1.49 GB
      image over the slow link left a 17-line log, with 396 MB on the stage.
- [x] M9.7 Log cleanup: logs go after `log_days` (30), stage rows after `step_days` (365), through
      safepath, from the logs folder only. Built 2026-11-04 (0.35.0), with tests in temporary
      roots. Done 2026-11-06 (0.62.2): the real coordinator service on a copy
      of the machine's store and logs, as rule 7 asks: of 274 jobs, 141 logs and 413 stage rows past short
      limits went, job rows and a stray file stayed, and the real logs did not change.

## M10: Reports from real projects
Fixes from the first real project reports (2026-11-04). Tested with unit tests and the real
coordinator code; none of this has run on a build machine yet.
- [x] M10.1 `env:` entries are read in file order: the order travels beside the sorted JSON
      (`env_order`, schema 7). Done 2026-11-05 (0.53.1): in a real job, an entry built on one that
      sorts after it got its value.
- [x] M10.2 A later `env:` reference fails on the client with exit 2, before upload, in `check`,
      `run`, `contract` and `doctor`; `doctor` warns about names only `job_env` could set. Done
      2026-11-05 (0.53.1): `check`, `run` and `contract` exit 2 with no ssh call, `doctor` exits 2,
      and a `job_env` name warns.
- [x] M10.4 The failure summary is the last thing printed, after container logs and the stale
      warning. Tested with the fake remote and a log holding container logs. Done 2026-11-05
      (0.53.1): in a real failed compose job the summary came last, after the container logs and the
      stale warning.
- [x] M10.5 `mulebox feedback draft` keeps a title's punctuation and cuts a long one at a word.
      A cut at `;` could not be reproduced: the old code cut only at 100 characters, wherever
      that fell. (2026-11-04, 0.36.6)
- [x] M10.6 Docs: hardcoded database addresses and `network_mode: service:...`, Playwright
      `--with-deps` in a project's scripts, `COMPOSE_PROJECT_NAME` in CI scripts, and git-based
      checks that stay local. The contract says the last one too. (2026-11-04, 0.36.7)
- [x] M10.3 The contract's database rule is about shared databases: a job's own compose service
      needs no `${MULEBOX_JOB_SLUG}`. (2026-11-04, 0.36.4)

## M11: Time limits, decided by the user
`timeout_min` as a hard limit is gone; rules in docs/design.md, Time limits, and docs/agents.md, 1a.
Tested with unit tests, the real coordinator code and a local stand-in for ssh. Open on all of
it: a real machine.
- [x] M11.1 Check-ins: `check_in` every `timeout_min` in `events`, a warning in `check` and `wait`,
      activity and watcher in `mulebox status`. Built 2026-11-04 (0.37.0). Done 2026-11-05 (0.53.1):
      with `timeout_min: 1`, a detached job gave a `check_in` each minute in `events` and the same
      warning in `wait`, an attached `check` printed them too, and `status` showed activity and the
      watcher.
- [x] M11.2 (the stop rule was replaced by M18.1; the activity readings stay) Activity: output, plus the job's own CPU and its services' traffic from control groups,
      reported with worker heartbeats. Built 2026-11-04 (0.37.0) on the machine's readings; a real
      drill on 2026-11-05 showed a sleeping job could never be idle that way, so 0.43.0 measures the
      job. 2026-11-05 on a real machine: a sleeping job beside idle Redis containers stopped at 20m
      06s and left nothing; a silent job at 100% of a core ran its 23 minutes. Run 2026-11-05: a
      real MySQL, Postgres and Redis stack read 3.2 to 3.6% of a core, under the 10% line, and its
      idle count kept rising; it was cancelled before its stop. Done 2026-11-06 (0.64.1): a job beside idle real MySQL, Postgres and
      Redis, `timeout_min: 1`, stopped at 2m 05s with exit 76, nothing left behind.
- [-] M11.3 Replaced by M18.1 on 2026-11-06. Unattended jobs: `wait` and `events` count as watching, 15 minutes idle and 24 hours
      total as `[limits]`, queued jobs included, `stopped: unattended`, exit 76, schema 8 with
      an upgrade test. Built 2026-11-04 (0.37.0). Open: a job really stopped on a machine,
      with its containers gone, and the 124 path with a worker still on an older version.
- [-] M11.5 Replaced by M18.1 on 2026-11-06. Warnings to the user: warning icon, `unattended` and time left on the job, its machine
      and the Queue tab in the dashboard. Built 2026-11-04 (0.38.0): seen in headless Chrome on
      a seeded local store. Open: a real job on a real machine, in a real browser, and a phone.
- [-] M11.4 Replaced by M18.1 on 2026-11-06. Warnings to the agent: `unattended` event, `status`, `wait`, stderr of any command from
      the project. Built 2026-11-04 (0.37.0). Run 2026-11-05: seen by an agent on a queued job
      through `status`, `events`, `wait` and stderr. Open: a take-back while running, and a real
      stop.
- [x] M11.6 Restarts on a real machine. Done 2026-11-06 (0.62.3): a restart of both services, then a
      real reboot, each with a job running and a detached job queued: the running job gave `interrupted`
      (exit 75, not replayed), the queued job ran to its own exit 7, and nothing was left behind. Back
      over ssh in 93 s with services up and nobody at the machine; the VPN returned by itself. An upgrade
      with a job running is refused (M17.2). Dropped: workers older than 0.37 and 0.40, as none exist
      and nothing is released. Not covered: sudden power loss.

## M12: Per-job settings
- [x] M12.1 A job in `.mulebox.yml` may be a mapping with `run`, `setup` and `compose: false`; plain
      commands keep the top-level defaults. Built 2026-11-04 (0.39.0), client only, no worker or
      store change. Run 2026-11-05: a job ran with no containers and its own `setup`. Done 2026-11-06 (0.62.2): a passing run with its own `setup`.
- [x] M12.2 `ports:` on a job: a free port for a process of the job, `MULEBOX_PORT_<NAME>`, from the
      pool compose ports use. Built 2026-11-04 (0.40.0). Done 2026-11-05 (0.53.1): a real Vite
      server on its `ports:` port, reached by real Chromium.

## M13: Second reports from real projects
Fixes from the second project tests (2026-11-04).
- [~] M13.1 `mulebox doctor` reads Compose's `!reset` and `!override` tags, so the refusal check
      runs for projects using them; before, it gave up with a warning. Built 2026-11-05 (0.40.7):
      the rules read off Compose 5.6, a test against `docker compose config`, and real `doctor`
      runs on such files, one refused, one clean. Open: a real project's compose files.
- [x] M13.2 Images out of reach on the network: the job counts as never started, exit 5, with the
      reason in the log and the summary. A build that fails or an image that does not exist stays
      a failed job. Built 2026-11-05 (0.40.8): error texts from real pulls on a local Docker daemon,
      and a test through the worker with a stand-in `docker`. Done 2026-11-05 (0.43.0): a real job on
      a build machine with an unreachable registry: exit 5, stage `images`, reason in the summary.
- [x] M13.11 A cache that starts empty says so in the job's log, as that job downloads everything.
      Seeding was left out: a cache is one project's, and the machine's default store is shared.
      Built 2026-11-05 (0.49.0), with tests. Done 2026-11-05 (0.53.1): first jobs with pnpm, npm,
      Composer and pip caches said so in the log, and a second pnpm job did not.
- [x] M13.15 mulebox runs its own tests through itself: `.mulebox.yml` in this repository, and
      `needs: [cache-pip]`. Done 2026-11-05 (0.51.1): the full suite ran on a build machine's Python
      3.12 in parallel, in 24 s, also closing the M1.1 note on running there.
- [x] M13.14 Dashboard: a job's stages as a waterfall, with what is usual as a tick, live while it
      runs. Times only, no percentage: a length from past runs is not progress. (2026-11-05, 0.50.0,
      fixed 0.51.2 and 0.51.3 after the review in real Edge)
- [x] M13.12 Browsers stay in the shared folder: Playwright's cleanup removed them after every job.
      Done 2026-11-05 (0.49.2): on a real machine two Playwright versions stayed side by side, and
      a repeat job took 2 s against 9 min with the download.
- [x] M13.13 A failure summary whose last lines read as a network failure says so, as a hint: the
      job still counts as failed, it ran. Pulls are M13.2. Built 2026-11-05 (0.49.1), with tests.
      Done 2026-11-05 (0.53.1): a real pip install lost its connection; the job counted as failed
      with exit 1 and the summary gave the hint. Other package managers not seen.
- [x] M13.10 Docs: a cold cache and slow connections. (2026-11-05, 0.48.2)
- [x] M13.9 `needs: [cache-npm]`, for npm projects. Built 2026-11-05 (0.48.0), with tests. Done 2026-11-06 (0.62.2): with the project folder
      removed, `npm ci --offline` installed from the cache in 203 ms.
- [~] M13.8 `mulebox doctor` says whether the machine can connect to the registries of a project's
      images. A warning, as images it has still work. Built 2026-11-05 (0.47.0): on a build machine
      one registry reached, one unknown host warned. Open: with the VPN really down.
- [x] M13.7 A queued job names the jobs on the machines (`running_ahead`) in `status` and `events`,
      as `waiting_for` is only for a job nothing can run. Done 2026-11-05 (0.46.0): seen in a real
      queue on a build machine.
- [x] M13.6 A check-in and `status` give the job's last output line, redacted, so `command` does
      not hide which step is on. Done 2026-11-05 (0.45.0): seen in a real check-in and `status`.
- [x] M13.5 `mulebox events` has a `stage` event as a job enters each stage. Done 2026-11-05 (0.44.0):
      followed a real compose job on a build machine. Stages shorter than a report can be skipped.
- [x] M13.4 `usual` counts only runs before the job, so `status` on an old job says what was usual
      then, and of two middle runs takes the lower, a length a run really had. (2026-11-05, 0.43.2)
- [x] M13.3 The notice for `env:` entries a job goes without reads for one entry and for more.
      (2026-11-05, 0.40.9)

## M14: Dashboard, from real use
Decided by the user on 2026-11-05: the Jobs box comes before more project adoption.
- [ ] M14.1 Jobs box redesign. Three mockups were rejected as flooded with data; the top row (CPU,
      memory, disk, machines) stays. Done when: the user picks a design and it runs on the real
      dashboard in Edge.
- [ ] M14.2 Network use per machine on the dashboard, as jobs download a lot, counting Wi-Fi and a
      VPN tunnel once.
- [ ] M14.3 Hold a waiting job, pause a machine or the queue. Built on M2.5: off by default, sign-in
      only. Freezing a running job was advised against.

- [x] M14.4 The live job page tells a quiet job from a dead page. Reported 2026-11-06 from a real project
      whose gate prints nothing until it ends. Done 2026-11-06 (0.65.0): in real Edge beside a real job, it
      showed quiet for 45 s with 6.8 cores busy, and a stream cut with no error reopened at its offset in 30 s.
- [x] M14.5 A job's page says how it went, with an icon and a word, goes back to the queue when a
      watched job ends, and tells runs of one job apart. Done 2026-11-06 (0.66.0): in real Edge a real job
      ended and the page went to the queue, which showed the next job; scrolled up in a log, it stayed;
      passed, failed and running each showed their icon and word.

## M15: Managed environments
- [x] M15.1 A job declares what it needs; mulebox builds the environment, reuses it until the
      project, lockfile, toolchain or image changes, and reports its failures apart from code
      failures. Built in the job's own image, with network retries, without holding a build slot.
      Open question: secrets for private registries. Done 2026-11-06 (0.64.1): `install:`,
      a stage of its own, run in the job's image. On a real compose project with a committed lock, the
      next job skipped it, a changed compose file ran it, a bad manifest exited 5 with the reason, and a
      lost connection was tried again and recovered. Holding no slot was dropped: it would run more than
      `slots` allows, with the job's containers up (design.md). Secrets for private registries stay
      what they are today: `env:` and the machine's `[job_env]`.
- [x] M15.2 Run pnpm's pre-run dependency check once in the environment stage and turn it off for the
      job's commands, in containers too, as it can trigger a long silent install. Done 2026-11-06 (0.64.1): with
      `verifyDepsBeforeRun: install` set in a project, a job removed `node_modules` and `pnpm run` installed
      nothing, while the same job with the check forced on did. Seen set inside a compose service too. It
      needs an `install` or `setup`, or nothing has settled the packages.

## M16: Smaller ideas from real use
- [x] M16.1 `mulebox warm`: prepare a project's caches and images ahead of a job. Done 2026-11-06 (0.64.1): `mulebox warm`
      ran a real compose project up to its command, and does not count as a run of the job.
- [~] M16.2 Disk warning on a machine, with a confirmed cleanup. Built 2026-11-06 (0.64.1): the worker reports
      its fullest disk (schema 10), and under 10 GB `doctor` and every command from a project warn and
      name `mulebox project clean`, which lists first and removes with `--yes`. Seen reported by the real
      worker; the warning itself only in tests, as filling a real disk is not a drill. Open: a machine
      really low on disk.
- [x] M16.3 Deploy when idle: an upgrade waits until no job is running. Done 2026-11-06 (0.64.1): `mulebox setup pc
      --when-idle` with a job running: the job finished and passed, a job queued meanwhile said why it
      waited and ran after, and the upgrade passed. CI runs wait too (tests).
- [-] M16.4 Reuse a passed result: moved to M18.3, the user wants it now.

## M18: Jobs that respect the agent's time
From the user on 2026-11-06. Comes first: mulebox must beat an agent running directly on the machine.
Measured by that comparison on real jobs.
- [x] M18.1 No unattended rule. A check-in is a question, `mulebox ok` answers it, a working job always
      finishes, and only a stuck job with no answer stops. Replaces M11.2 to M11.5. Done 2026-11-06
      (0.55.2): on a real machine, a job's client killed mid-queue and the job finished; `mulebox ok`
      cleared a question; a hung job with `timeout_min: 1` was asked at 1 min and stopped at 2m 04s,
      exit 76, nothing left behind.
- [x] M18.2 Results wait for an agent that went away, and its next command says so, once. Done
      2026-11-06 (0.55.2): a real job, told once by the next command.
- [x] M18.3 `mulebox check` does not repeat a job on the same files: it gives the result or joins the
      running job, and `--again` forces a run. Replaces M16.4. Done 2026-11-06
      (0.55.2): real jobs, a repeat in 0.7 s, a failure kept exit 7, `--again` and a changed file ran,
      and a second agent joined the running job.
- [~] M18.4 Agents choose how to wait: follow, be pinged, or check later. In the docs, the contract
      and the skill 2026-11-06 (0.55.0). Open: an agent using them in a real session.
- [x] M18.5 Project homes in git: one repository per project on the machine, one worktree per
      branch at `~/.mulebox/projects/<project>/`, set up once and kept. A job sends only what changed
      and installs only when the lockfile or setup changes. Measured: worktree add 0.2 s and a
      warm pnpm install 2.1 s on the build machine. Built 2026-11-06 (0.56.0), with tests: one job
      per branch, `setup` skipped when nothing it depends on changed; 0.57.0 sends only changes.
      Done 2026-11-06 (0.57.1): this repository's gate with one changed file took 27.3 s through
      mulebox from the laptop and 25.2 s run directly on the machine. A compose job's own time went
      from 20 s to 2 s, with `npm install` at 323 ms; one changed file of 2001 sent 0.2 KiB of
      7.7 MiB; an older machine got the whole snapshot, and the job passed.
- [x] M18.6 Different branches run at once, two jobs on one branch wait in line. Done 2026-11-06
      (0.59.0, built 0.58.0): a new install has 2 slots. On a real machine with 2, four 12 s jobs on
      three branches took 28 s, the second job of a branch waited and named the first, and two
      compose jobs asking for one host port got their own, served traffic and left nothing. Seen
      in real Edge: both jobs in the lane, 0 of 2 slots free, no console errors.
- [x] M18.7 `mulebox projects` shows each project's folder and size; `project clean` and `project
      reset`. Done 2026-11-06 (0.59.0): on a real machine, sizes and folders listed; `reset` of a
      branch left the others; `reset` while a job ran was refused; a full `reset` went, and the next
      job built it again. `clean --yes` ran in test roots only, as AGENTS.md rule 7 asks; on the real
      machine its dry run listed only what it should.

## M17: Easy for anyone
Decided by the user on 2026-11-06, after M18: heavy work leaves the laptop, and anyone can set
mulebox up easily. Today that takes a clone, a venv, ssh config, a hand-edited node.toml and
toolchains installed by hand. Done for all of it when: M6.2, a stranger, passes.
- [~] M17.1 `mulebox init` writes `.mulebox.yml` from a project's files, checked by the real config
      reader. Built 2026-11-06 (0.55.0): on copies of the manifests of 24 real repositories it
      wrote 18, also for parts in `api/` and `web/`; the 6 it refused have nothing it can run on
      Linux. Run 2026-11-06 (0.61.1): what it wrote for a small npm and a small Python project
      passed as real jobs on a real machine, with no edits. Open: a real project of a stranger's,
      which M6.2 covers.
- [x] M17.2 `mulebox setup <host>`: one command on the laptop installs the build machine, finds what
      it offers (such as Docker), writes the client config, and proves it with a first job.
      Built 2026-11-06 (0.60.0): on a real machine an upgrade and its first job passed, a bad host
      gave advice, running jobs stopped it. Done 2026-11-06 (0.62.1): on a machine with no mulebox
      on it, in M17.5.
- [x] M17.3 A job's pinned node and pnpm install themselves on the machine the first time. Done
      2026-11-06 (0.61.0): on a real machine a job installed node in 48 s while a job on the other
      slot ran in 14 s, the next job started in under 2 s, a cancel took 2 s, a version that does not
      exist exited 5 with the reason, and pnpm installed once it got the machine's `[job_env]`.
- [~] M17.4 The client installs in one line, with no clone: pipx, a binary, or by hand, the user's
      choice on 2026-11-06. Built 2026-11-06 (0.62.0): on macOS, a pip install and the unpacked binary
      each ran `mulebox setup` and a job on a real machine, the binary with no Python on its path.
      The Linux binary ran in M17.5. Not run: pipx itself and the release workflow, which needs a
      tag. Open: the repository going public, which is what makes the pipx line and the releases
      page work; not yet, the user's call on 2026-11-06.
- [x] M17.5 Clean-machine run: a fresh Linux machine and a fresh project, docs only, all failures
      fixed. Done 2026-11-06 (0.62.1), with no spare machine, the user's choice: two throwaway
      containers, a blank Ubuntu with systemd and sshd as the build machine, and a laptop with no
      Python running the Linux binary. Found and fixed: jobs need git there, which nothing said.
      Then, from blank, setup named what was missing, and a new project went from `init` to a
      passing check with node installed in 36 s; a repeat, a broken commit (exit 1) and a revert
      all answered correctly. Docker was not on it, so compose did not run from blank.

## M19: Agent trials
From `docs/agent-trial.md` on real projects, 2026-11-06. First trial: all steps ran and the agent would
use mulebox, adding about 15 s to a 3 min 14 s gate. The second project stopped at its first gate, on M19.13; its rerun on 0.66.3 passed all but a
browser download blocked for the machine's network location.
- [x] M19.1 The failure summary keeps every failed part of a gate. Done 2026-11-06 (0.66.1): the real
      failed log of the trial, replayed, showed the type error and both failed parts.
- [x] M19.13 A container's own user can read what a project mounts. Done 2026-11-06 (0.66.3): a real job with
      `mysql:8.4` mounting an init folder started, ran its seed file and read the row back, in 17 s.
- [x] M19.14 `check` does not give back a failure from an older mulebox. Done 2026-11-07 (0.67.1): after a real
      upgrade from 0.66.7, a failure on the same files ran again rather than being given back.
- [~] M19.2 `mulebox init` in a git worktree names the project after the repository. Built (0.66.5), with a
      real git worktree in a test. Open: an agent using it.
- [x] M19.3 A repeat answered from an earlier result does not print "submitted" and a dashboard link. Done
      2026-11-07 (0.66.8): real repeats of a passed and a failed job on the machine.
- [x] M19.4 `doctor` does not say a machine offers a toolchain it has yet to install. Done 2026-11-07
      (0.66.8): against the real machine with a node version it lacks.
- [x] M19.5 Installing a pinned toolchain retries a lost network, and its error says network, not
      "switch versions". `status` warns when an install's output reads as a lost connection. Done 2026-11-07 (0.67.1):
      on the machine an unknown host took 3 tries and said network, a 404 took one and exit 5, and `status` warned in a
      real job. Not seen: a real outage, which cannot be staged safely.
- [x] M19.6 A way to keep a run hurt by an outage out of `usual`, and `usual` less skewed by one bad run:
      a stage that printed a lost connection while fetching marks its run, which then does not count; one
      bad run left alone was already held off by the median. Done 2026-11-07 (0.67.1): a real job that printed
      a lost connection in `setup` was marked; tests show `usual` skips it.
- [x] M19.7 A short way to run one test in a compose project, instead of `mulebox run --` and a long
      `docker compose exec`: `mulebox run --in <service> -- <cmd>`. Done 2026-11-07 (0.66.10): a real compose job.
- [x] M19.8 `mulebox queue` says why a job waits, as `status` does. Plainer word for `wait`'s "take it back":
      the contract's second name for `its_result` went, and the dashboard names `mulebox ok`. Done 2026-11-07 (0.67.1): a real queue named the job holding the branch.
- [~] M19.10 A rerun of the second trial, past the step where it stopped: small upload, install skipped,
      two branches, `--detach`, and a second gate's time with the images built. All seen in its job history on
      0.66.3: images 16 s against 554 s, install skipped on repeats, two branches at once, 164 s a gate. Open: one
      full `check` with browsers, from the project's own session.
- [x] M19.11 No alarming `pull access denied` for an image the job then builds itself. mulebox's own tag
      made Compose try a pull; a built service now has `pull_policy: build`. Done 2026-11-07 (0.67.1): a real job built its image with no such line.
- [x] M19.12 `mulebox feedback draft` keeps a whole title (a cut one was seen again). The cut came at 100
      characters; only GitHub's own limit cuts now. Done 2026-11-07 (0.66.8), through the real CLI.
- [x] M19.9 Collapse `Downloading ...: x MB/y MB` in the log; show pnpm's own install apart in `prepare`: a
      stage `toolchain`, as installing pinned tools was hidden in `prepare` (167 s on one real job). Done
      2026-11-07 (0.67.1): a real job showed `toolchain` 40 s, and the real log of 2224 lines kept one of its 589 download lines.

## Parking lot
- `mulebox init` on a laptop with no node writes a file with no node pinned; on a machine with none
  of its own the job ends with `npm: command not found`. Found 2026-11-06.
- Resumable browser downloads: Playwright restarts from zero. Would need a mirror of its own
  (`PLAYWRIGHT_DOWNLOAD_HOST`); worth it only if a first download keeps failing after M13.12.
- Project registry, if real adoption finds something that belongs neither in `.mulebox.yml`
  nor in the job history (reasoning: docs/design.md, Projects)
- MCP wrapper over the client commands
- Job weights, once measurements justify them
- macOS or Windows workers
