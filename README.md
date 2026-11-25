# mulebox

Send your AI coding agents' builds and tests to the Linux and Mac machines on your network.

Agents (Claude Code, Codex, and others) edit code on your dev machine. Builds, type checks, linting
and test suites are slow, hot and noisy, and several agents running them at once can freeze the
dev machine. With mulebox, an agent types `mulebox check` instead. The job waits its turn in **one
line** shared by every project and agent, runs on a node, and the agent gets the
output and the exit code as if the command had run locally.

![The mulebox dashboard: CPU, memory, disk and machines on top, the jobs running and waiting below](docs/images/queue-dark.png)

Status: **1.x, in daily use on a real node** (version in [VERSION](VERSION)). The
commands, `.mulebox.yml` and the config files are stable: a change that breaks them needs 2.0.
What is open is in the [roadmap](docs/phases.md).

## Why mulebox

Most tools that put your own machines to work run CI. mulebox is built for the agent at your dev
machine, here and now, and it takes your CI along in the same line.

- **Made for agents.** `check` gives the output and exit code a local run would. An agent can send
  a job with `--detach`, come back with `wait`, and answer a long job's check-in with `mulebox ok`.
  The same files never run twice: a repeat gets the earlier result, and a second agent joins the job
  already running. ([For agents](#for-agents))
- **Your working copy, not a push.** Committed or not, the files as they are now go to the node.
  Secrets stay behind, each branch has its own git worktree there, and only changed files are sent.
  ([Fast](#fast))
- **Real projects, not just a command.** Every job gets its own Docker Compose services and ports,
  removed on every outcome (files root wrote included). Package caches, Playwright browsers and the
  environment are built once and reused. ([Real projects](#real-projects))
- **Tools an agent can use alone.** `mulebox contract` tells an agent how this project runs. The skill
  keeps itself current. `doctor` checks everything before a job is sent, `init` writes the config,
  `warm` gets a project ready ahead of time, and `feedback` files a scrubbed issue.
  ([For agents](#for-agents))
- **One line for agents and CI.** GitHub Actions runners wait for a slot in the same line as your
  agents' jobs, so a node never runs more than it has room for.
  ([GitHub Actions](#github-actions-on-the-same-machines))
- **You see and steer everything.** A live dashboard has logs, resource graphs, stages as a
  waterfall, a CI run's steps as they happen, download progress, and job minutes. From it or the
  CLI you can freeze, boost, move or cancel a job, pause a machine, set a node's slots, and set
  rules for the order of the line. ([The dashboard](#the-dashboard-1), [You steer](#you-steer))
- **A pass you can require on GitHub.** `check` can post its result as a commit status on the
  pushed commit, so a pull request shows it. ([For agents](#for-agents))
- **Upgrades that wait their turn.** An upgrade queues like a job or waits until the node is idle, so
  no running job is cut short. ([You steer](#you-steer))

## Install

You need a Linux machine with systemd, git and Python 3.12 or newer, which your dev machine reaches
over ssh with a key, at an address that does not change (below). A Mac can be a node too, beside Linux
nodes or alone ([A Mac as a node](docs/install.md#a-mac-as-a-node)).

### Give every machine a fixed address

mulebox remembers where each node is: the dev machine keeps the address you set it up with,
a second machine keeps its coordinator's address in its own config, and the dashboard on the LAN
is opened at it. Most routers hand out addresses by DHCP, and a machine can get a new one after a
reboot, a lost Wi-Fi connection or a router restart. Then the dev machine cannot reach it (exit 3),
other machines show offline, and nothing runs until the address is fixed. mulebox does not work
with an address that changes.

Before `mulebox setup`, make each machine's address permanent, in one of these ways:

- **Reserve it on your router** (called a DHCP reservation, static lease or fixed IP): pick the
  machine by its MAC address and give it an address. Nothing changes on the machine itself.
- **Set a static address on the machine**, outside the range the router hands out.
- **Use a name that always finds the machine**, if every machine and the dev machine can resolve it,
  such as a VPN that keeps each device's address.

Check after a reboot of the machine that `ssh <node> true` still works. If an address did change,
put the new one in `~/.ssh/config` (or in `coordinator` in the dev machine's `client.toml`), and on every
other machine in `coordinator` in `node.toml`, then `mulebox service restart worker` there.

### Let your coding agent install it

Give your agent (Claude Code, Codex, or another) this prompt, with your node's ssh name:

```text
Install mulebox for me and set up this project to use it. Read
https://raw.githubusercontent.com/typerhack/mulebox/main/docs/getting-started.md and follow it
in order. My node is <node> (I reach it with `ssh <node>`). Ask me, in one message, only
for the steps that need a password or sudo, then finish the rest yourself and show me a passing
`mulebox check`.
```

The page is written for this: it says which steps need you (copying an ssh key, installing
`python3-venv` with sudo) and which the agent can do alone.

### Or by hand

On the dev machine:

```sh
uv tool install mulebox        # or, with Python 3.12 or newer: pipx install mulebox
mulebox setup <node>           # installs mulebox on your node, then runs a first job
```

mulebox is on [PyPI](https://pypi.org/project/mulebox/). uv brings its own Python, so the dev machine
needs none; to get uv: `brew install uv`, or `curl -LsSf https://astral.sh/uv/install.sh | sh`.

`<node>` is your node as you reach it with ssh, named as you like: a name from your
`~/.ssh/config`, such as `mulebox setup homelab`, or `user@address`, such as
`mulebox setup alice@192.168.1.50`. The dashboard shows the machine under its own hostname.

Then, in any project:

```sh
mulebox init                   # writes .mulebox.yml from the project's own files
mulebox check                  # runs the project's checks on the node
mulebox dashboard open         # the dashboard in your browser, through an ssh tunnel
```

To upgrade later: `uv tool upgrade mulebox` (or `pipx upgrade mulebox`), then
`mulebox setup <node>`. From a clone, and the details: [install.md](docs/install.md#2-install-on-the-dev-machine). The whole
path from nothing to a passing project, in order: [getting-started.md](docs/getting-started.md).

## How it works

Two kinds of machine:

- the **dev machine**: where you and your agents edit code: a laptop, a desktop or another Linux PC. It runs only the
  `mulebox` command, which talks to the nodes over ssh.
- **nodes**: the Linux machines and Macs that run the jobs. Each runs a
  **worker**, which runs jobs. One node is also the **coordinator**: it holds the line of jobs
  and their history, and serves the dashboard.

<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/architecture-dark.svg">
  <img src="docs/images/architecture-light.svg" width="760" alt="The dev machine sends a job over ssh to node 1, the coordinator, which holds the line of jobs and the dashboard; nodes 2 and 3 are workers that get a job when they ask for one over ssh">
</picture>
</p>

- The dev machine only ever talks to the coordinator. It does not know how many nodes there are,
  so adding one changes nothing for agents or projects.
- Workers ask the coordinator for work. A job goes to a node with a free slot that has what the
  job needs (Docker, Playwright, a toolchain, Xcode). Of the free ones, a `preferred` node goes
  before a `fallback` one, then the node that ran the branch's last job, as it holds the branch's
  folder and installed dependencies, then the node with more free slots; none waits longer than
  30 s for a better one. `--on <node>` sends a job to one node alone. A job runs only on a node
  of its project's system, Linux or macOS (`os:` in `.mulebox.yml`). A node in dev mode, being
  set up or tried out, takes only jobs sent to it with `--on`. A job may declare its size
  (`size: {cores: 4, memory: 6GB}`); a node then fits as many jobs as its cores and memory hold,
  less what it keeps for its owner, and keeps room for a big job so small ones cannot starve it.
  A job with no size counts as one slot. A worker reaches the coordinator
  with a key that can do nothing but worker requests.
- The dashboard runs only on the coordinator. Workers send their CPU, memory and network readings
  with every heartbeat, so one page shows every node.
- One node is enough to start: it is both coordinator and worker. A second joins with
  `mulebox setup <second-node> --worker-of <first-node>`. A node can be drained, resumed and removed
  (`mulebox machine`). Run so far with a Linux node and a Mac node side by side.

## The dashboard

Live, in the browser: the line of jobs with each machine's lane, every job's stages and log as
they happen, and controls to pause, freeze, boost, reorder or cancel. It has a dark and a light
theme and follows the system's by default.

| | |
| --- | --- |
| ![The queue in the light theme](docs/images/queue-light.png) | ![A running job: its stages as a waterfall beside its live log](docs/images/job-dark.png) |
| The queue, light theme | A running job: stages and live log |
| ![A GitHub Actions run on a mulebox runner, with its steps](docs/images/ci-run-light.png) | ![Every machine with its state, load, slots and what it offers](docs/images/machines-dark.png) |
| A GitHub Actions run, step by step | Every machine at a glance |
| ![History with search and filters](docs/images/history-light.png) | ![How long jobs ran, today and since the first job](docs/images/statistics-dark.png) |
| History, searchable | Job minutes, by kind, project and machine |
| ![A node's settings, Jobs tab: slots, priority, dev mode and what the node reports, each setting with mulebox's suggestion beside yours](docs/images/node-settings-dark.png) | ![The Order panel: the rules for the order of the line, each waiting row saying why it stands where it does](docs/images/order-light.png) |
| A node's slots, priority and dev mode, with the suggestion | Rules for the order of the line |
| ![The Storage page: a node's disk as one ruler with its reserve, the automatic cleanup and what it last did, then every project and its branch folders with what happens to each](docs/images/storage-dark.png) | ![The Storage tab of a node's settings: the space mulebox may use beside the disk floor, when unused folders go and idle ones are slimmed, the latest folder, cleaning up on its own, cleaning Docker too, and idle projects](docs/images/storage-settings-light.png) |
| What mulebox holds on a node, and what goes when | A node's disk settings, with what they would do |

The Storage page shows, per node, what mulebox holds on its disk and what happens to each part: the
disk as one ruler with the free-space reserve at its end, every project and its branch folders
with size, last job and when each goes on its own, package caches, toolchains, runners, and
Docker's totals with what the last cleanup freed there. Each folder's path can be copied, a project or
branch marked to keep, and a clean lists what it removes before anything goes. A project with no
job for two weeks gets a suggestion on its row. At the top, one line says whether the automatic
cleanup is on and what it does, what the last one removed, and what mulebox holds against the space
it may use; Run now runs a cleanup at once, and says first how much it removes and slims. At the bottom, the cleanup history lists every
cleanup with why it ran, each folder it removed and why, what it freed in Docker, the free space
before and after, and any error. The rules are a node's settings, in the Storage
tab of its settings window: first the space mulebox may use (20 GB by default, agents told from 80%
of it) beside the disk floor, which counts only when the disk is nearly full for another reason;
then after how many hours an idle branch folder is slimmed and after how many days an unused one
goes, whether each project's latest folder stays, whether the node cleans up on its own and cleans
Docker too, and when an idle project is suggested for cleaning. One line says what the values on
screen would do before they are saved.

![The cleanup history: each cleanup with why it ran, the folders it removed and why, what Docker freed, the free space before and after, and an error](docs/images/storage-history-light.png)

### When an agent needs more space

From 80% of the space mulebox may use on a node, every command an agent runs tells it to ask you
for more. With your yes it sends `mulebox storage ask --size 30GB --reason "..."`, and the request
shows in the strip under the header, on every page, within seconds: Approve, Review or Decline.
Review shows the agent's reason, who asked, and a bar of what mulebox holds, the limit now and what
the yes would add, with a sentence that follows another value as you change it, including whether
the disk would stay above its floor. Several requests for one node get one answer. The agent hears
the answer in its next command, and while a request waits it is told not to ask again.

| | |
| --- | --- |
| ![Two agents' requests for more space in the strip under the header, each with Approve, Review and Decline, and a grey line for a change applied without asking](docs/images/ask-strip-light.png) | ![The review window: the agent's reason, who asked, the space bar with what the yes adds and the 80% mark, and Approve, Another value and Decline](docs/images/ask-review-dark.png) |
| Requests in the strip, on every page | One request, with the space bar |

Whether a request needs your yes is your choice, in the Agents window in the header (or `mulebox
agents ask|allow`): Ask me first, as installed, or Allow, and record it, which applies a request
at once and tells you in a grey line with Undo. Every change of a node's setting, asked by an agent
or made by you in the settings window or with `mulebox machine config`, goes into the settings
history on the Storage page and `mulebox storage changes`: the old and new value, who asked and
why, who confirmed, when the node took it, and Undo for a node's latest change.

| | |
| --- | --- |
| ![The Agents window: Ask me first or Allow, and record it, with what each does](docs/images/agents-light.png) | ![The settings history: changes applied without asking, approved at another value, declined with a note, the Agents option and a change by hand, each with who asked and who confirmed](docs/images/settings-history-light.png) |
| Whether agents must ask | Every setting change, with who asked and who confirmed |

When a node falls under its reserve and the rules have nothing left to remove, the strip above
the panels says so on every page, and the owner decides what goes:

| | |
| --- | --- |
| ![The strip above the panels saying a node is under its free-space reserve](docs/images/low-space-light.png) | ![The review window: what could go next, oldest first, with enough ticked to be back above the reserve](docs/images/storage-review-dark.png) |
| A node under its reserve | What could go, for the owner to decide |

A node checks itself: free space, its folders, `git`, the job runner, Docker and Xcode. While a
check fails it rests and takes no job, or holds back only Docker or Xcode jobs; the strip says so
once, with the node's own fix and Check now, a waiting job says which node holds it, and the
node's settings window lists every check and sets the least free space:

| | |
| --- | --- |
| ![The strip saying build-1 rests for a full disk and build-2 takes no Docker jobs, each with its fix and Check now, a disk under 10% free, and the jobs waiting for build-1](docs/images/resting-dark.png) | ![The Health tab of a node's settings: resting since a time, each check passing or failing with its fix, and the least free space](docs/images/health-tab-light.png) |
| A node that rests, and one without Docker | Every check, and the least free space |

While a job or a CI run downloads packages or a cache, its card shows how much has come and how
fast, and warns when no bytes arrive for a while:

![Running jobs and GitHub runs with their download meters: a known total, an open track and a stalled download](docs/images/downloads-dark.png)

A running job that has gone quiet is judged on its evidence: its output, its own CPU, what its
processes read and write, its services and its downloads. Its card says which it is: a slow
download, waiting on purpose, asking for input it will never get, or stuck:

![Running jobs on two machines: one working, a slow download, one waiting on purpose, one asking for input and one that looks stuck](docs/images/stuck-dark.png)

A machine with many cores can show its busiest cores and one line for the rest (compact view,
left). On a phone the page stacks into one column (right).

<p>
  <img src="docs/images/cpu-compact-light.png" alt="The CPU box in its compact view on a 32-core machine" width="68%">
  <img src="docs/images/phone-dark.png" alt="The dashboard at phone width" width="28%">
</p>

Every screen is built on one small design system, Gauge: its tokens, components and rules are in
[design-system.md](docs/design-system.md), with a reference page you can open in a browser
([specimen.html](docs/design-system/specimen.html)).

![The Gauge design system's reference page](docs/images/design-system-light.png)

### Proof that tests ran

A pass counts only if its log shows its tests ran. A finished job shows how many tests it ran. A
pass with fewer tests than the last pass, or none, is a failure, said in words under its name; a
drop the agent allowed shows the agent's reason:

![Finished jobs with their test counts: fewer tests than the last pass, a runner that ran none, a drop allowed with the agent's reason, and a job that requires a summary and printed none](docs/images/tests-light.png)

The job's page says what happened and what to do, with each runner beside the last pass, and
underlines the runners' own summary lines in the log:

![A job that failed on fewer tests: the strip with the command to allow it, the Tests panel per runner and the underlined summary lines in its log](docs/images/tests-job-dark.png)

### What jobs really use, and job sizes

Every job and GitHub run keeps its peak cores (its busiest 10 s) and memory, with the stage they
came in. The Usage page (and `mulebox usage`) shows each job's usual and highest peak on its node's
own scale, and the size that would have fitted every run:

![The Usage page: per node, each job's usual and highest peak of cores and memory as bars, and the size that fits every run](docs/images/usage-dark.png)

That size can go into `.mulebox.yml` as `size: {cores: 4, memory: 6GB}`, so a node fits jobs by
the cores and memory they need instead of one per slot. A node that is also your PC keeps room for
you, set in the Room for you panel of its settings window or with `mulebox machine config`:

![A node's settings window: Room for you, with the cores and memory kept for the owner and what jobs with a size share](docs/images/owner-room-light.png)

All pictures come from made-up data (`tools/screenshots.py`).

### Open it from your phone, with a password

By default the dashboard opens only through an ssh tunnel from the dev machine
(`mulebox dashboard open`), so it needs no password. To open it from any device on your network,
turn on `lan` mode on the coordinator node; the page then asks for a password:

<p>
  <img src="docs/images/sign-in-light.png" alt="The sign-in page, light theme" width="48%">
  <img src="docs/images/sign-in-dark.png" alt="The sign-in page, dark theme" width="48%">
</p>

1. In `~/.config/mulebox/node.toml` on the node, under `[dashboard]`, set who may connect and the
   node's own address: `lan_range = "192.168.1.0/24"` and `lan_address = "192.168.1.50"`.
2. On the node: `mulebox dashboard password` (asks twice, at least 10 characters), then
   `mulebox dashboard firewall > firewall.sh`, read it, and `sudo sh firewall.sh`.
3. Set `mode = "lan"` under `[dashboard]` and `mulebox service restart dashboard`.
4. Open `http://192.168.1.50:8090` (the node's address) on any device in that range.

A sign-in lasts 24 hours; restarting the dashboard signs everyone out. It is plain HTTP unless you
turn on HTTPS, and a network you trust can go without the password (`lan_password = false`).
All of it, step by step: [Dashboard on the LAN](docs/install.md#dashboard-on-the-lan).

## Features

### For agents

- **One command, the same answer.** `mulebox check` runs the project's checks on a node and gives
  back the output and exit code a local run would, with your files as they are now, committed or
  not. If you change files while it runs, the result says it is stale.
- **Every job has an id.** Send it with `--detach`, keep working or end the session, and come back:
  `mulebox wait <id>` gives the output and exit code, `status <id>` where it stands, `logs <id>` its
  log. A job runs to its end even when its agent went away, and the agent's next command tells it the
  result, once.
- **Three ways to wait**: follow the job, be pinged when it ends (`mulebox events --job <id>`), or
  check back later.
- **No duplicate work.** On exactly the same files, `check` joins the job already running or gives its
  recent result, failures included. `--again` forces a run.
- **Failures read fast.** A failed job ends with a short summary of the error and the stage it failed
  in (`logs <id> --summary`), with a hint when the failure reads like a lost network.
- **A pass proves its tests ran.** mulebox reads the summary of pytest, vitest, jest, Pest, PHPUnit,
  cargo, mocha, Playwright, XCTest, Swift Testing and `go test -v`. A pass where a runner ran no test,
  or fewer than the last pass on the branch (else the default branch), fails with exit 8 and says
  why. Tests removed on purpose: `mulebox check --fewer-tests "<why>"`, and the reason is kept.
  `tests: false` turns it off for a job that runs none.
- **Clear exit codes.** The check's own code on a failure; 5 for a job that could not start (a missing
  tool, an unreachable image, a bad lockfile); 8 for a pass that did not prove its tests ran; 2 for a
  config error, caught before anything is sent; 75 for a job a restart interrupted; 76 for a stuck job
  that was stopped.
- **Long jobs ask, they do not die.** There is no hard time limit. A long job asks its agent if all is
  well, with its last output line; the agent answers `mulebox ok`. Only a job that is really stuck,
  with no answer, stops.
- **A stuck job is said early.** After 2 minutes with nothing moving (a project may allow more), a
  running job is said to look stuck in `status`, `wait` and `events`, with what it last printed, so an
  agent stops waiting on a hung job. A slow download or a job waiting on purpose is told apart.
- **The position in line, and why.** A waiting job says where it stands, what runs ahead of it, and
  why it waits: its branch is busy, no machine has what it needs, a machine is paused.
- **Checked before anything is sent.** `mulebox doctor` checks the config, the node's tools and
  versions, the project's compose files and whether the node reaches the images' registries; it runs
  nothing.
- **Written for agents.** `mulebox contract` tells an agent how this project works through mulebox.
  The Claude Code skill teaches it the rest; `mulebox setup` installs it, and an agent whose skill is
  out of date is told so and updates it.
- **A result on the pull request.** With `github_status: true` in `.mulebox.yml`, `check` on an
  exact pushed commit posts its result as the commit status `mulebox/<job>`, through the dev
  machine's own `gh`, so it can be a required check. Nothing on GitHub reaches in to the node.
- **Problems reported safely.** `mulebox feedback draft` writes a GitHub issue with the job's ids,
  stages and log lines, scrubbed of addresses, names and secrets; `post` files it once you read it.

### Fast

- **Only changes cross the network.** Each project has a folder on the node, with a git worktree per
  branch, and a job sends only the files that changed since the last one.
- **Installs once.** `install` and `setup` run only when the lockfile, manifests or toolchain change,
  and a lost network during an install is tried again.
- **Download once, not every job.** Packages for pnpm, npm, Composer and pip are kept in a cache per
  project on the node, so the next job, a fresh container or the project's CI runner installs from
  there instead of the internet (`needs: [cache-pnpm]` in `.mulebox.yml`). On one real project, a
  second job reused all 73 packages and downloaded none; a Composer install ran with the network
  turned off.
- **Toolchains install themselves.** A project pins Node and pnpm, and the first job that needs a
  version installs it on the node, checked against the official checksums, once for every project.
- **Branches side by side.** Different branches run at once; a second job on the same branch waits.
- **Get ready ahead of time.** `mulebox warm` fetches toolchains, images and caches and runs the
  installs, with no command.
- **Quiet logs.** Image download progress is folded into one line, with the bytes on the stage.
- **Downloads you can see.** A package install or a CI cache restore shows its bytes, total and
  speed on the job's card and in `mulebox status`, and a download that stalls says so.
- **How long it usually takes.** Each job and each stage shows its usual length from past passed
  runs, beside the time so far.

### Real projects

- **`mulebox init`** writes `.mulebox.yml` from the project's own files: Node, pnpm, npm, yarn, PHP with
  Composer, Python, Flutter, Go and Rust, also one folder down (`api/`, `web/`), following what the
  project's CI uses.
- **Docker Compose.** Every job gets its own containers, names, networks and host ports (a port in use
  moves), removed on every outcome, files written as root included. Services get 65536 open files and
  the machine's job settings.
- **Browser tests.** Playwright against the job's containers, with browsers kept for the next job.
- **Several jobs per project**, each with its own command, setup, ports and containers or none, and
  `env:` values that build on each other.
- **Apple platforms** on a Mac node: a job pins an Xcode version, gets a simulator of its own,
  removed on every outcome, and caches for SwiftPM and CocoaPods; `init` writes the job for an
  Xcode project or a Swift package
  ([Apple builds](docs/install.md#apple-builds-on-a-mac-node)).
- **Isolated jobs**, for code you have not read: `isolation: container` in `.mulebox.yml` runs
  each job in a fresh, confined container with no ssh key, `gh` login, mulebox config or other
  project in sight, and no Docker socket. Its compose services still work, through a narrow door
  that lets the job reach only its own containers. A node's owner can make it the floor for every
  job there (`isolation = "container"` in `node.toml`), which a project cannot lower
  ([design](docs/design.md#isolation-per-job-m231-decided-by-the-user-2026-11-14)).
- **`mulebox run -- <cmd>`** runs any command on the node; `--in <service>` runs it in a compose
  service, `--take <path>` brings a changed file, such as a lockfile, back to the dev machine.

### GitHub Actions on the same machines

- **Runners for your private repositories** (`mulebox runner register --repo <owner>/<repo>`), with
  their own labels. A CI job waits for a slot in the same line as the agents, so the node never runs
  more than its slots. It needs admin rights on the repository, as GitHub lets only admins attach a
  runner, and `gh auth login` as that account on the dev machine
  ([what a runner needs](docs/install.md#github-runners)).
- **Only your own runs**: a runner refuses a fork's pull request, and a run anyone but you started,
  before any of it runs.
- **CI runs in the dashboard**: each step live, its output as the runner writes it, its length and
  result; passed, failed or cancelled from the runner's own record, with the failed step and GitHub's
  message. A run's CPU counts its containers.
- **Steered like any job**: freeze, boost, move in line, open on GitHub, cancel on GitHub.
- **Shared caches**: a runner can download through the project's package caches (`runner caches`).
- **Sized runs**: a runner's run can count as the cores and memory it uses (`runner size`).
- **On the node you pick**: give a node's runner a label of its own and name it in `runs-on:`, so a
  workflow goes to that node, such as a Mac for an iOS build ([GitHub runners](docs/install.md#github-runners)).
- **Public repositories only in a container** (`runner register --isolated`). See below for why.

**Public repositories.** On a public repository anyone can fork it and open a pull request,
and GitHub runs the workflow file from that pull request, not yours. A stranger can write
`runs-on: [self-hosted, mulebox]` and a step such as `curl ... | sh`, and on a plain runner it runs
on your node as your user, with Docker (as good as root there), next to your other projects'
runners. GitHub's own documentation advises against self-hosted runners on public repositories
for this reason. So a plain runner refuses a public repository. An isolated runner
(`mulebox runner register --isolated`) takes it: the guard refuses other people's runs before
anything runs, and every job runs in a fresh container with no folder of the node, no Docker
socket and no privileges, removed when the job ends. It needs Docker on the node and the node's
`gh` signed in as the repository's admin; what it does not cover (a shared kernel, your network)
is in [install.md](docs/install.md#github-runners).

### You steer

From the CLI or the dashboard, with no sign-in needed through the tunnel:

- **A job**: pause a waiting one (it keeps its place), freeze a running one with its containers and
  resume it where it stopped, boost it (the machine's CPU and disk first, nothing new starts beside
  it), move it to the front, up, down or to the end, cancel it.
- **The order of the line**: rules you set once, in the dashboard's Order panel or with
  `mulebox queue rules`. Levels for a project, a branch (such as `main`), GitHub runs or one
  workflow; aging, so a job that waited long moves up; shortest first; and fair turns, so one
  project's burst does not hold back another's single job. Every waiting job says why it stands
  where it does. All off by default, which keeps the order of arrival.
- **A machine**: pause (drain) it so it finishes what runs and takes nothing new, resume it, or remove
  it. Set its slots and priority from the dashboard or `mulebox machine config`, beside a
  suggestion from its cores and memory; the change reaches its `node.toml` and counts from the
  next job, with no restart. A `preferred` node takes jobs first, a `fallback` one only when the
  others are full. Dev mode keeps a node you are trying out away from your projects' jobs. Keep
  cores and memory for yourself on a node that is also your PC: jobs that declare a size share
  only the rest.
- **A project**: pause all its jobs and CI runs, for a set time or until resumed (`mulebox project
  pause`), or give it a level in line (`mulebox project priority`).
- **Everything at once**: the dashboard's Queue actions pause or resume every machine, and freeze or
  resume every running job.
- **Upgrades in line**: `mulebox setup <node> --queued` waits its turn like a job, next by default or
  `--behind` the jobs already waiting, then installs and the line goes on. `--when-idle` waits for
  running jobs; a running job is never cut short unless you say `--now`.
- **Clean up**: `mulebox projects` shows each project's folder and size; `project clean` removes old
  branch folders, `project reset` a whole project, on every node. Each node also cleans up on
  its own: the folder of a branch your dev machines no longer have goes at once, one unused for
  12 hours is slimmed (its installed packages and build output go, its files stay), one unused
  for 7 days goes, Docker's unused build cache and the images its jobs no longer use too, and
  past the space it may use (20 GB by default, yours to change) the oldest are slimmed, then removed, and from 80% of it agents are told to ask you for more: their request shows in the dashboard's strip for you to approve, at another size or not, or applies at once if you allow agents to, and every setting change is recorded with who asked and who confirmed. All of it is
  your setting; `mulebox storage` shows what it holds and what goes when, `--history` every
  cleanup and what it removed, `storage clean` runs one now (`--no-docker` leaves Docker),
  `project keep` keeps a folder.

### The dashboard

- **Live**: the line by machine, every running job with its stages as a waterfall and its log as it
  happens, and a note when a job is quiet but still working.
- **Top panels**: CPU over the last 5 minutes with a meter per core, or a compact view of the busiest
  cores; memory with what jobs use and swap; disk with Docker's share; network in and out; every
  machine with its slots and what it offers.
- **Tabs**: Queue, Failed, Passed and Recent, with live counts.
- **History** with search and filters you can share as a link, and **Statistics**: job minutes today,
  by day and since the first job, by kind, project, source and machine (also `mulebox stats`).
- **Machines page**: every node with its state, load, network, slots, version and last contact,
  and a settings window per node for its slots, priority, dev mode, room kept for you and disk rules.
- **Usage page**: each job's usual and highest peak of cores and memory, on its node's scale, and
  the size that fits every run; on a job's page, each peak under the stage it came in.
- **Storage page**: what mulebox holds on each node and what goes when, the automatic cleanup with
  Run now, the history of every cleanup, and the settings history: every change of a node's
  setting with who asked and who confirmed, and Undo.
- **Agents' requests** for more space in the strip, with Approve, another value or Decline, and an
  Agents window to let them apply at once, recorded.
- **Order panel**: the rules for the order of the line, set and saved from the page.
- **Download meters** on a job's card: bytes, total and speed, and a warning when one stalls.
- **Out of step**: a strip says when a dev machine, a worker or a skill runs another version, with the fix.
- **Light and dark** themes and two meter styles, remembered per browser, and a layout that works on
  a phone. An open page reloads itself after an upgrade, once no window is open on it.
- **From any device on your LAN**, with a password, a firewall rule and optional HTTPS, or read-only
  (`controls = false`).
- **Light on the node**: about 0.6% of one core and 46 MB with a page open.

### Machines and safety

- **One command to set up**: `mulebox setup <node>` installs a node from the dev machine, finds what it
  offers (Docker, Playwright, toolchains), writes the dev machine's config and proves it with a first job.
- **More nodes**: `mulebox setup <node> --worker-of <coordinator>` adds a worker, with a key that can
  only ask for work. Jobs go to a node that has what they need.
- **Linux and macOS**: services run under systemd on Linux and launchd on a Mac, managed the same
  way on both (`mulebox service status|restart|logs`). On a Mac a job runs in a process group of
  its own, found and stopped after a worker restart, and its GitHub runners are launchd agents.
- **Survives restarts**: services come back by themselves after a reboot; a running job ends as
  `interrupted` (exit 75) and is not run again by itself, and waiting jobs run.
- **On your own machines**: jobs travel over ssh to machines you own; no cloud service, no port open
  to the internet.
- **Private by default**: files that look like secrets are never uploaded, and logs are scrubbed of
  secrets before they are stored or shown.
- **Stays in its folders**: mulebox writes and deletes only inside its own roots on a node, checked
  for links and mounts. Jobs run under systemd with limits on Linux, in a process group of their
  own on a Mac, and nothing is left behind.
- **Old logs go by themselves** after 30 days; job records stay.

## Commands

Every command has its own help: `mulebox --help` lists them, `mulebox <command> --help` explains
one. `<node>` is a node's ssh name, `<id>` a job's id, which every job gets and every
command prints. The ones you and your agents use:

**Run jobs**, from a project folder:

| Command | What it does |
| --- | --- |
| `mulebox init` | write `.mulebox.yml` from the project's own files |
| `mulebox check [job]` | run a job from `.mulebox.yml` (default `check`) on a node; exits with its exit code. `--detach` returns at once with the id, `--again` runs even on files already tested, `--on <node>` on that node alone, `--fewer-tests "<why>"` lets a pass with fewer tests count |
| `mulebox run -- <cmd>` | run any command there, once; `--in <service>` runs it in a compose service, `--bare` without setup and containers, `--take <path>` brings a file it made back |
| `mulebox warm` | get toolchains, images, caches and installs ready ahead of a job |
| `mulebox doctor` | check the project and the node before sending anything; changes nothing |
| `mulebox contract` | how this project works through mulebox, written for agents |

**Follow jobs**:

| Command | What it does |
| --- | --- |
| `mulebox queue` | what is running, waiting and recently finished, and why a job waits |
| `mulebox status <id>` | one job's state, stage, last line and usual length |
| `mulebox wait <id>` | wait for a job and end with its result and exit code, as `check` would |
| `mulebox events --job <id>` | a job's changes of state as lines, for agents that want to be pinged |
| `mulebox logs <id>` | a job's log; `--summary` gives only the failure summary |
| `mulebox ok <id>` | answer a long job's question: all is well, let it go on |
| `mulebox projects` | every project that has run, with its folder and size on the node |
| `mulebox stats` | how long jobs ran, today, by day and in total |
| `mulebox usage` | the peak cores and memory each job really used, and a size that fits it |

**Steer the line**:

| Command | What it does |
| --- | --- |
| `mulebox cancel <id>` | cancel a job |
| `mulebox pause <id>`, `resume <id>` | hold a waiting job, or freeze a running one, and let it go again |
| `mulebox first`, `up`, `down`, `last <id>` | move a waiting job in line |
| `mulebox boost <id>`, `normal <id>` | give a job the machine first, and end that |
| `mulebox queue rules` | show or set the rules for the order of the line |
| `mulebox project pause`, `resume`, `paused` | hold all of a project's jobs and CI runs for a while |
| `mulebox project priority <project> [level]` | a project's level in line: low, normal, high |
| `mulebox project clean`, `reset` | remove old branch folders, or a project's whole folder, on every node |
| `mulebox project keep <project>` | keep a project's folders, or a branch's, from the automatic cleanup |
| `mulebox storage` | what mulebox holds on each node, and what goes when |
| `mulebox storage ask --size 30GB --reason "..."` | an agent, with your yes: more space for mulebox on a node |
| `mulebox storage requests`, `approve`, `decline` | answer agents' requests (`--size` for another value, `--note` for the agent) |
| `mulebox storage changes`, `undo <id>` | every setting change with who asked and who confirmed; undo the latest |
| `mulebox agents ask\|allow` | whether an agent's request waits for your yes or applies at once, recorded |

**Machines and setup**:

| Command | What it does |
| --- | --- |
| `mulebox setup <node>` | install or upgrade mulebox on a node from the dev machine; `--queued` waits its turn in line, `--worker-of <coordinator>` adds a worker, `--dev` in dev mode |
| `mulebox machine list`, `drain`, `resume`, `remove`, `check` | every node, online or not, resting with the fix; stop one taking jobs, bring it back, forget it; run its health checks now |
| `mulebox machine config <node>` | a node's slots, priority, dev mode, room kept for its owner and disk settings, applied from its next job |
| `mulebox service status`, `restart`, `logs` | on a node: mulebox's own services, systemd or launchd |
| `mulebox dashboard open` | the dashboard in your browser, through an ssh tunnel |
| `mulebox dashboard password`, `firewall`, `cert` | on the node: sign-in, firewall and HTTPS for `lan` mode |
| `mulebox runner register`, `unregister` | add or remove a GitHub Actions runner; `--isolated` for a fresh container per job |
| `mulebox skill install`, `update`, `status` | the agent skill in your Claude config folders |
| `mulebox feedback draft`, `post` | report a problem as a GitHub issue, scrubbed of private data first |
| `mulebox version` | this mulebox's version |

The rest of `mulebox --help` (`rpc`, `worker`, `coordinator`, `runner-hook` and others) is what
mulebox runs on the nodes itself; you do not call those.

## Documentation

| Page | For |
| --- | --- |
| [getting-started.md](docs/getting-started.md) | the first install and the first project, in order |
| [install.md](docs/install.md) | node, dev machine, upgrades, more nodes, GitHub runners, the dashboard |
| [agents.md](docs/agents.md) | everyday commands, every `.mulebox.yml` field, the agent rule |
| [troubleshooting.md](docs/troubleshooting.md) | what an error means and what to do |
| [design.md](docs/design.md) | how it works and why |
| [design-system.md](docs/design-system.md) | the dashboard's look: tokens, components, rules |
| [phases.md](docs/phases.md) | the roadmap: what is done and what is open |
| [releasing.md](docs/releasing.md) | CI and releases, for maintainers |

## For coding agents

mulebox ships a skill for Claude Code, [SKILL.md](mulebox/client/skill/SKILL.md), that teaches an
agent to send its work through mulebox in any project. You do not install it yourself:

```sh
mulebox setup <node>           # installs the skill in every Claude config folder, updates old copies
mulebox skill status           # which copies you have, and whether they match this mulebox
mulebox skill update           # bring them up to date by hand
```

The skill is part of mulebox, so the newest skill comes with the newest mulebox:
`uv tool upgrade mulebox` (or `pipx upgrade mulebox`), then `mulebox setup <node>` upgrades the
node and the skill together. An
agent whose skill is out of date is told so by mulebox itself and updates it. Details:
[install.md](docs/install.md#skill-for-coding-agents).

Agents without skills can read [docs/agents.md](docs/agents.md): everyday use, setting a project
up (`.mulebox.yml`, the agent rule), and moving GitHub Actions to mulebox runners. Point an agent
at it: "read mulebox's docs/agents.md and set this project up".

## Security

mulebox is for one owner and the projects that owner trusts. A job runs as the node's user, with
Docker, so it is not a sandbox: read the [security model](docs/install.md#security-model) before
pointing it at a machine that holds anything else. A plain GitHub runner takes private repositories
only; a public one needs an isolated runner, a fresh confined container per job
([why](#github-actions-on-the-same-machines)).

## Development

Requires Python 3.12 or newer, and Node.js 22 with npm for the dashboard's front end (`web/`,
[web/README.md](web/README.md)): from a checkout, `mulebox setup` builds it and stops without npm,
and the dashboard shows no page until it is built.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/mulebox --version
.venv/bin/python -m pytest              # includes the file-size check
.venv/bin/python -m pytest -n auto      # same, in parallel (about 5x faster)
.venv/bin/python tools/check_line_counts.py
(cd web && npm ci && npm run build)    # the dashboard's page, into mulebox/dashboard/app/
.venv/bin/python tools/screenshots.py   # the README's pictures, from the dashboard's stand-in data
```

After a VERSION bump, rerun the `pip install -e` step: the installed metadata keeps the old
version until then and the version test fails.

CI and the release process: [docs/releasing.md](docs/releasing.md). Rules for contributors and
agents: [AGENTS.md](AGENTS.md). Every change bumps [VERSION](VERSION) and adds an entry to
[PROJECT_LOG.md](PROJECT_LOG.md).

## License

[MIT](LICENSE).
