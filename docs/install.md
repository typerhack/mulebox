# Installing mulebox

New here? [getting-started.md](getting-started.md) gives the order; this page has the details.

mulebox has two sides:

- **Build machine** (Linux with systemd, Ubuntu first): runs the coordinator (the queue)
  and a worker (runs the jobs) as two systemd user services, on one machine, for one user.
  Adding a second build machine is not finished yet: see the [roadmap](phases.md), M5.
- **Laptop** (macOS or Linux): the `mulebox` client that agents call. It reaches the build
  machine over ssh.

Examples below use the build machine `build-1` and the user `alice`.

## Requirements

Build machine:

- Linux with systemd; `systemctl --user` must work for the user (log in over ssh or a
  desktop session; `su` does not start a user manager).
- git. On Ubuntu/Debian: `sudo apt-get install git`.
- Python 3.12 or newer with `venv` support. On Ubuntu/Debian: `sudo apt-get install
  python3-venv`; a fresh Ubuntu does not have it.
- Network access to PyPI for mulebox's dependencies.

Laptop:

- mulebox (section 2), and ssh access to the build machine with a key
  (an entry in `~/.ssh/config` such as `Host build-1` keeps commands short). Log in once by
  hand so the machine's host key is known: mulebox's ssh never prompts, so a key with a
  passphrase must be in your ssh agent.

## 1. Install on the build machine

With mulebox on the laptop (section 2), one command:

```sh
mulebox setup build-1      # or alice@192.168.1.50
```

It checks the login, installs mulebox on the machine, finds out whether Docker works there and
fills `capabilities` if that list is empty, writes `~/.config/mulebox/client.toml` if you have
none, and runs a first job through the real queue. Each step that fails says what to do. Run it
again at any time, also to upgrade: `node.toml` is kept, and it stops if jobs are running unless
you add `--queued` (below), `--when-idle`, which waits for them while new jobs wait in line, or
`--now`.

To install by hand instead, copy `install.sh`, `node.toml.example` and `systemd/` from
`mulebox/machine/` and a wheel into one folder on the build machine, and run
`bash install.sh mulebox-<version>-py3-none-any.whl`.

What the installer does (it never uses sudo and never deletes a folder):

| Step | Result |
| --- | --- |
| Checks | Linux, `systemctl --user`, git, Python >= 3.12, a working `python3 -m venv` |
| venv | `~/.mulebox/venv`, rebuilt only when the Python minor version changed |
| Command | `~/.mulebox/bin/mulebox` (symlink into the venv), and `~/.local/bin/mulebox` so plain `mulebox` works in a login shell; a real file of that name is left alone |
| Node config | `~/.config/mulebox/node.toml`, written once from the template, then validated |
| Roots | `~/.mulebox/{jobs,projects,cache,staging,runners}`, mode 750 |
| Services | `~/.config/systemd/user/mulebox-coordinator.service` and `mulebox-worker.service`, enabled and started; `mulebox-runner@.service` copied only |
| Linger | prints how to enable it if it is off |

Set `MULEBOX_PYTHON=python3.12` (or another interpreter) before running the installer to
use a Python other than `python3`.

### Keep the services running after logout

Without lingering, systemd stops user services when your last session ends. The installer turns
it on if the machine allows that without a password. If it says it could not, run this once:

```sh
sudo loginctl enable-linger alice
```

### Node config

`~/.config/mulebox/node.toml` (template: [mulebox/machine/node.toml.example](../mulebox/machine/node.toml.example)):

- `name`: the short hostname by default.
- `roles`: `["coordinator", "worker"]`. The installer starts only the services of
  the roles listed here.
- `roots`: the only folders mulebox writes to and deletes in. They must be separate,
  absolute, and not a system folder or your home folder itself. `projects` is optional: left
  out, as in a `node.toml` from before 0.56.0, it is `projects` beside `jobs`.
- `slots`: jobs at the same time, 2 in a new install (1 if left out). Two heavy jobs share the
  machine's CPU and memory, so 1 suits a small machine. A job with a fixed port of its own needs
  `ports:` to run beside another; compose ports are moved already.
- `capabilities`: see [interfaces.md](interfaces.md). A project's `needs` must be
  in `capabilities` of some worker, or its jobs are refused with that message. Add `docker`
  on a machine with Docker Engine and Compose v2 whose user is in the `docker` group, to
  run `compose:` projects, then restart the worker. mulebox fetches one small helper image
  the first time, and never removes images.
- `mulebox setup` adds `docker` by itself to an empty list; a list you wrote is left alone.
- Add `playwright` for browser tests, once this has run on the machine, which needs root:
  `sudo npx playwright install-deps chromium` (node comes from any install, for example a
  mulebox toolchain). Browsers themselves are fetched by jobs into
  `<cache>/playwright`, once per version, and are kept, each some hundreds of MB, until you
  remove them. On a slow network, the first job with a new Playwright version takes minutes.
- Package caches need no setting: a project asks for one with `cache-pnpm` or `cache-composer`
  in `needs`, and they live in `<cache>/packages/<project>/`. Nothing removes them by itself.
  `mulebox cache list` shows their size, and `mulebox cache clear <project>` removes them,
  with no job of that project running. What sharing means: [agents.md](agents.md), 2a-1.
- `[job_env]`: environment for every job on this machine, for what the machine needs and a
  project should not have to know, such as a setting for a slow network. A project's `env:`
  overrides a value and can add to it with `${NAME}`. Names follow the rules of `env:`. It
  reaches commands of mulebox jobs and every service of a `compose:` project, where what a
  service sets itself wins. It replaces an `ENV` of the same name in an image, since mulebox
  cannot see that one. It does not reach a `RUN` line of an image build or GitHub runner
  jobs. Not for secrets: it ends up in job processes and in the job's compose file. As a
  safety net, a value whose name says it is a secret (`NPM_TOKEN`, `DB_PASSWORD`) is redacted
  from job logs wherever it appears.
- `[retention]`: `log_days` (default 30) is how long a job's log is kept after the job ended,
  and `step_days` (default 365, at least `log_days`) how long its stage rows are. The coordinator
  service removes what is older, once an hour and when it starts, from
  `<staging>/logs/` and nowhere else. A finished job's row stays for good.
- `[limits]`: when a stuck job stops, on the coordinator's machine, read when the coordinator
  service starts. `unattended_idle_min` (default 15) is the longest a job must show no output, CPU
  or network, with its question unanswered for a `timeout_min`, to count as stuck;
  `unattended_max_hours` (default 24) is the same for a job that cannot be measured. A working job
  has no limit, and GitHub runner jobs are not affected. The names date from before 0.55.0.
  What counts as activity: [agents.md](agents.md), 1a. Upgrade workers and the coordinator
  together: an older worker keeps `timeout_min` as a hard limit (exit 124).
- `dashboard`: `mode = "local"` serves the web dashboard on this machine's 127.0.0.1 only;
  `"off"` turns it off; `"lan"` also serves it to your network, see "Dashboard on the LAN"
  below. Contract: [interfaces-m2.md](interfaces-m2.md).

The installer never overwrites this file. After editing it, check it and restart:

```sh
~/.mulebox/venv/bin/python -c 'from mulebox.common.config import load_node_config; print(load_node_config())'
systemctl --user restart mulebox-coordinator mulebox-worker mulebox-dashboard
```

The dashboard (`mulebox-dashboard`) is installed and started with the coordinator. It
reads the queue's database read-only and never changes anything.

## 2. Install on the laptop

Any of these three. The binary needs no Python on the laptop; the build machine always needs it.

**With pipx** (or `uv tool install`), which also updates easily:

```sh
pipx install git+https://github.com/typerhack/mulebox
```

**As a binary**, for macOS on Apple silicon and Linux on x86-64. Take the file for your system from
the [releases page](https://github.com/typerhack/mulebox/releases). Download it with `curl` as
below: the binaries are not signed, so macOS refuses a file a browser fetched. It is a folder,
because a single file took 10 s to start on macOS:

```sh
curl -fsSLO https://github.com/typerhack/mulebox/releases/download/v1.0.0/mulebox-1.0.0-macos-arm64.tar.gz
mkdir -p ~/.local/share ~/.local/bin
tar xzf mulebox-1.0.0-macos-arm64.tar.gz -C ~/.local/share
ln -sf ~/.local/share/mulebox/mulebox ~/.local/bin/mulebox    # needs ~/.local/bin on your PATH
```

The macOS binary has only an ad-hoc signature, not an Apple Developer ID, so macOS kills it
(`zsh: killed`) when a browser downloaded it: the browser marks the file as from the internet, and
`curl` does not. If you used a browser, remove that mark once, then it runs:

```sh
xattr -dr com.apple.quarantine ~/.local/share/mulebox
```

**By hand**, from a clone. Give it a folder of its own: plain `pip install --user` is refused by
most current Python installs, Homebrew's and Ubuntu's among them
(`externally-managed-environment`).

```sh
python3 -m venv ~/.mulebox-client
~/.mulebox-client/bin/python -m pip install .
mkdir -p ~/.local/bin
ln -s ~/.mulebox-client/bin/mulebox ~/.local/bin/mulebox    # needs ~/.local/bin on your PATH
```

A clone holds the dashboard's front end as source (`web/`), so installing from one needs Node.js
22 and `npm` on the laptop: `mulebox setup` builds the front end before it installs a machine, and
stops with what to install when the build is missing or out of date and `npm` is not there. The
binary and a released wheel already carry the build and need no Node.

Then run `mulebox setup` (section 1). It writes `~/.config/mulebox/client.toml`; to change it later, the template is
[mulebox/machine/client.toml.example](../mulebox/machine/client.toml.example):

```toml
coordinator = "build-1"                  # ssh target: Host alias or alice@192.168.1.50
remote_bin = "~/.mulebox/bin/mulebox"
connect_timeout_s = 10
```

`$MULEBOX_CONFIG` can name another file.

Next: [set up a project](getting-started.md#2-decide-where-the-projects-tools-come-from).

## Toolchains

A project pins `node` and `pnpm` versions under `toolchain:` in its `.mulebox.yml`. Each version
installs itself the first time a job needs it, and is shared by every project. Node is verified
against the official checksums; pnpm needs a node, so pin both. To get one ready ahead of a job:

```sh
ssh build-1 '~/.mulebox/bin/mulebox toolchain install node 22.22.3'
ssh build-1 '~/.mulebox/bin/mulebox toolchain list'
```

`mulebox toolchain` runs on the build machine only. From the laptop, `mulebox doctor` in a
project says which versions the machine has. They live in `<cache>/toolchains/`. A job whose
version will not install does not start: it exits 5 with the reason and what is there.

## GitHub runners

A build machine can host self-hosted GitHub Actions runners, one user service each
(`mulebox-runner@<name>.service`; the installer copies the template but enables nothing).
A runner gets the same CPU and disk share as a mulebox job (`CPUWeight=50`), so CI and
agents' jobs share the machine evenly and both give way to its own use.
Each GitHub job then waits for a mulebox build slot, so runner jobs and agent jobs share one
queue. From the laptop, with `gh` logged in as a user with admin rights on the repository:

```sh
mulebox runner register --repo example-org/example-app            # labels: mulebox
mulebox runner register --repo example-org/example-app --labels mulebox,gpu --name build-1-app
mulebox runner unregister --repo example-org/example-app
```

`register` gets a short-lived registration token with `gh api`, then runs
`mulebox runner add` on the coordinator over ssh with the token on stdin. On the build
machine itself, pipe the token in (or paste it at the hidden prompt):

```sh
gh api -X POST repos/example-org/example-app/actions/runners/registration-token --jq .token \
  | ~/.mulebox/bin/mulebox runner add --repo example-org/example-app
~/.mulebox/bin/mulebox runner list
~/.mulebox/bin/mulebox runner remove build-1-example-app    # removal token on stdin
```

`runner add` downloads the latest `actions/runner` release for linux-x64 or linux-arm64,
checks its SHA-256 against the release notes, unpacks it into
`~/.mulebox/runners/<name>/` (default name `<node>-<repo>`), registers it with
`config.sh`, sets the job hooks in the runner's `.env` and starts the service. The token is
never put on a command line or in a log. `roots.runners` must stay `~/.mulebox/runners`
(the unit template runs runners from there). In workflows, use
`runs-on: [self-hosted, mulebox]`.

**One cache for the gate and CI.** A project's mulebox jobs download through its package caches;
a runner downloads through its own, so a package the gate already has can still fail to download
in CI. On the build machine, point a runner at the project's caches (the name in `.mulebox.yml`):

```sh
~/.mulebox/bin/mulebox runner caches build-1-example-app --project example-app   # all four
~/.mulebox/bin/mulebox runner caches build-1-example-app --project example-app --only cache-npm
~/.mulebox/bin/mulebox runner caches build-1-example-app --off
```

It sets `npm_config_cache`, `pnpm_config_store_dir`, `COMPOSER_CACHE_DIR`, `PIP_CACHE_DIR` and
`MULEBOX_CACHE_<TOOL>` (for a workflow's compose file) in the runner's `.env` and restarts its
service; a runner with a job running is refused. CI then writes into the cache the gate reads,
so do it only for a runner of a private repository whose pull requests you trust.

**Private repositories only.** Never attach a runner to a public repository: anyone can open a
pull request, and its workflow file comes from that pull request, so it can ask for your runner
whatever your own workflow says, and run its code on your build machine. `mulebox runner
register` refuses a public repository; one that turns public later keeps its runner until you
unregister it.
What a job can reach: [Security model](#security-model).

## More machines

One machine runs the coordinator; any number of others can be workers of it. Set the first one
up as above, then, from the laptop, with `ssh <host> true` working for both:

```sh
mulebox setup build-2 --worker-of build-1
```

It makes a key on `build-2` (`~/.config/mulebox/coordinator_key`), adds it to `build-1`'s
`~/.ssh/authorized_keys` for mulebox requests only, installs mulebox on `build-2` with a
`node.toml` that names `build-1` as its coordinator and runs no coordinator or dashboard, and
waits until `build-1` lists it online. `build-2` reaches `build-1` at the address this laptop
uses (`ssh -G build-1`); if it needs another one, add `--coordinator-address alice@192.168.1.50`.
The first time, `build-2` trusts `build-1`'s host key as it finds it.

Run it again to upgrade `build-2`; running jobs there stop it unless `--now`. The client keeps
talking to `build-1` only. A new node.toml written by the installer carries:

```toml
roles = ["worker"]
coordinator = "ssh://alice@192.168.1.50:22"
coordinator_key = "/home/alice/.config/mulebox/coordinator_key"
```

### Draining, removing and moving machines

```sh
mulebox machine list               # every machine: online, offline or draining, slots, version
mulebox machine drain build-2      # finish its jobs, take no new ones; --wait until they end
mulebox machine resume build-2     # take jobs again
mulebox machine remove build-2     # forget a stopped machine and take its key off
```

A drained machine still runs its GitHub runners, which take CI jobs from GitHub on their own:
stop them too (`mulebox runner remove` there) before taking the machine away. To take one away:

1. `mulebox machine drain build-2 --wait`.
2. On `build-2`: `systemctl --user disable --now mulebox-worker`.
3. `mulebox machine remove build-2`. It is refused while the machine is online or has jobs.

A removed machine whose worker starts again joins again with its next claim, unless its key is
gone, as it is after `remove` for a machine set up with `--worker-of`.

Moving the coordinator to another machine is done by hand, as it holds the queue's history:

1. On the old one, wait for no running job (`mulebox machine drain <name> --wait` for each), then
   `systemctl --user stop mulebox-coordinator mulebox-dashboard mulebox-worker`.
2. Copy `~/.mulebox/staging` (the store, logs and snapshots) to the same path on the new one, with
   the services stopped there, after `mulebox setup <new>` installed it.
3. Start the new one's services, point the laptop's `client.toml` `coordinator` at it, and run
   `mulebox setup <worker> --worker-of <new>` for each other machine, which writes their key on
   the new coordinator. A kept worker `node.toml` still names the old one: edit `coordinator`
   there, or remove that file before setup writes a new one.

Each machine's CPU and memory show on the dashboard and in `mulebox machine list`, as its worker
reports them. `machine list` also shows each machine's network in and out, over its physical
interfaces only (Wi-Fi, Ethernet): a VPN tunnel's traffic also crosses Wi-Fi, and a container's
crosses a bridge, so counting those would count the same bytes twice. Not yet: `mulebox project clean` or `reset` on another worker's folders.

## Security model

mulebox is for one owner and the projects that owner trusts. It is not a sandbox.

- Everyone who can `ssh` to a build machine can already run anything there, so the client commands
  have no accounts or permissions of their own.
- A job runs as the machine's normal user, in that user's systemd session, with Docker. A job,
  and any package a job installs, can read that user's files, including ssh keys, `node.toml`,
  the runners' credentials and the logs of other projects, and can change the coordinator's data
  and mulebox itself. Docker access makes that root in all but name.
- So a machine used as a desktop shares all of that with every job. A dedicated user keeps the
  desktop's files out of reach only without the `docker` group, and mulebox's Docker jobs need
  that group. For a real boundary, use a machine that holds nothing else.
- A worker on another machine reaches the coordinator with a key of its own. Its line in
  `authorized_keys` has `restrict` (no forwarding, no terminal) and a forced command,
  `mulebox ssh-gate`, which runs only `mulebox rpc` and `rpc-download <job>`, and over `rpc`
  only a worker's requests: claims, job reports, logs and runner slots. So that key cannot open a
  shell or submit work, but it can take and report jobs, and read any job's snapshot. A job on
  the worker can read that key, like everything else of its user.
- The compose checks stop a CI file's assumptions from reaching past the job, not an attacker.
- Redaction is a safety net built on patterns and on `[job_env]` values with a secret-looking
  name. Keep real secrets out of jobs: a value printed in another form is not found.
- With `mode = "lan"` and `lan_tls` off, the password and the session travel in the clear. With
  `lan_password = false`, every device in `lan_range` can read all queues and job logs, CI output
  from the machine's GitHub runners included.

## Upgrade

Update the laptop's own client (`pipx upgrade mulebox`, a new binary, or `git pull` and the same
`pip install .`), then send the same version to the machine:

```sh
mulebox setup build-1
```

The installer reinstalls the wheel into the existing venv, updates the unit files and
restarts the services. A running job is interrupted by the restart (state `interrupted`,
never replayed), so `mulebox setup` stops if a job is running. `--when-idle` waits instead: new jobs and CI runs wait in line, the running ones finish, the upgrade runs and the line moves on, and a killed laptop holds nothing for more than 2 minutes while waiting. `--now` upgrades at once. `node.toml`
is kept.

`mulebox setup <machine> --queued` does what `--when-idle` does without keeping the laptop: the
new version goes to the machine and becomes a row in its line, "mulebox upgrade to X", and the
command returns. Nothing new starts on that machine (jobs and CI runs wait), the running jobs
end, it installs, and the line goes on. With `--behind` the jobs already waiting go first. It
shows in `mulebox queue` and on the dashboard; `mulebox status <id>` follows it, `mulebox logs
<id>` has the installer's output, and while it waits it can be moved like a job or taken back
with `mulebox cancel <id>`. Once installing it cannot be cancelled. It does not run the first
job `setup` runs otherwise. If its waiter goes away (a reboot), the row goes after 90 s and the
machine runs jobs again.
Upgrade the coordinator and every worker together: a worker's stage rows and toolchain
reports, and detached jobs, need both to be new. `mulebox doctor` shows the versions.
When the Python minor version changed, the old venv is moved to
`~/.mulebox/tmp/venv-old-<date>.<pid>` and a new one is built.

## Uninstall (manual)

There is no uninstall script on purpose: removing files is your decision. On the build
machine:

```sh
systemctl --user disable --now mulebox-worker mulebox-coordinator
rm ~/.config/systemd/user/mulebox-worker.service ~/.config/systemd/user/mulebox-coordinator.service
rm ~/.config/systemd/user/mulebox-runner@.service   # after removing every runner
systemctl --user daemon-reload
```

Then remove `~/.mulebox/` (venv, roots with job folders, caches, queue database and logs)
and `~/.config/mulebox/` yourself once you no longer need them. Disable lingering if you
enabled it only for mulebox: `sudo loginctl disable-linger alice`. On the laptop, remove
`~/.config/mulebox/client.toml` and uninstall the client package.

## Checking Docker on a machine

`tools/drill_compose.py` starts a small `compose:` project on a real Docker daemon, checks
that what mulebox generates ends up labelled, private to the job and reachable by service
name, and removes it with the worker's teardown. It pulls nothing but needs `redis:7-alpine`,
or `--image` with `redis-cli` in it, and removes only what carries the labels of a job id it
made up. Run it from the laptop:

```sh
ssh build-1 '~/.mulebox/venv/bin/python - --real-docker' < tools/drill_compose.py
```

## Troubleshooting

See [troubleshooting.md](troubleshooting.md).

## Using the dashboard

From the laptop:

```sh
mulebox dashboard open                 # opens the browser; Ctrl-C closes the tunnel
mulebox dashboard open --no-browser    # only prints the URL
mulebox dashboard open --port 8091     # if local port 8090 is taken
```

If `[dashboard] port` was changed in `node.toml`, pass the same value as `--remote-port`.
Nothing but the SSH connection is exposed: the page is reached only through the tunnel.

### Steering jobs and machines

mulebox is meant for your own network, so whoever reaches the queue may steer it, from the
laptop or from the dashboard:

```sh
mulebox pause <job-id>      # a waiting job keeps its place and does not start;
                            # a running one is frozen where it is, its containers too
mulebox resume <job-id>     # goes on where it stopped
mulebox first <job-id>      # a waiting job goes to the front of the line
mulebox up <job-id>         # one place ahead (down: one back)
mulebox last <job-id>       # to the end of the line
mulebox boost <job-id>      # the job gets the machine's CPU and disk first, and the
                            # machine takes no new job until it ends
mulebox normal <job-id>     # ends the boost; the job keeps its place in line
mulebox machine pause <name>    # the same as `machine drain`: no new jobs there
mulebox project pause <name>... [--minutes 60]  # none of these projects' jobs or CI runs
                                # starts; the rest go on; ends by itself
mulebox project resume <name>...   # and `mulebox project paused` lists them
mulebox machine resume <name>
```

A paused job is not asked whether it is stuck, and resuming it answers what was asked meanwhile.
A paused job still holds its slot and its memory. A boost does not stop GitHub runners on that
machine from taking CI jobs; it only weighs the job above them.

## Skill for coding agents

The package ships a skill that teaches a coding agent to work through mulebox in any project.
It is short on purpose: it sends the agent to `mulebox contract`. You can read it in
[mulebox/client/skill/SKILL.md](../mulebox/client/skill/SKILL.md).

For Claude Code, `mulebox setup` installs it for all your projects: into every Claude config
folder on the laptop that has no copy yet, and it updates the copies that are out of date.
`mulebox setup <host> --no-skill` installs none (out-of-date copies are still updated). By hand:

```sh
mulebox skill install    # into every Claude config folder that exists here
mulebox skill status     # how each copy stands against this mulebox; changes nothing
mulebox skill update     # replace out-of-date copies, after upgrading mulebox
```

These cover `~/.claude`, `~/.claude-work` and the folder `CLAUDE_CONFIG_DIR` names, those that
exist; `--config-dir <folder>` names one instead, and may repeat. `update` replaces hand edits
in a copy, and leaves alone a skill folder that is a link.

The skill moves with mulebox, so its version is always the laptop's mulebox: there is no
separate download, and the newest skill is the newest mulebox's. Upgrading goes: upgrade mulebox
on the laptop (`pipx upgrade mulebox`, or a new binary), then `mulebox setup <host>` installs that
same version on the build machine and, at its end, updates the out-of-date skill copies on the
laptop. A copy
that is still old, after an upgrade without `setup`, is caught by the session: the skill tells
the agent to run `mulebox contract` first, which says on stderr when an installed copy differs
from this mulebox's; the agent then runs `mulebox skill update`, reads the skill again and tells
you. `mulebox doctor` reports it too. Copies from before 0.82.0 lack that last step, but still
run the contract first, so the agent sees the notice.

The dashboard shows the same, for every laptop that sent a job in the last two weeks: a strip
above the panels names a laptop on another mulebox than the build machine, a laptop whose skill
is out of date, and a worker on another mulebox than the coordinator, each with its fix.

Agents without skills can read [agents.md](agents.md) instead.

## Dashboard on the LAN

`lan` mode lets other devices, such as a phone, open the dashboard directly at
`http://<address>:8090`, the same port as on the machine itself, with a password unless you turn it off (below). The tunnel above
keeps working. Reserve the
machine's address on your router first, so that it stays the same.

This is plain HTTP: the password and everything on the page cross your network
unencrypted, and browsers mark the page "Not secure". That is fine on a network where you
trust everyone. On an office or shared network, use the tunnel, or HTTPS (below).

On the build machine, add to `[dashboard]` in `node.toml`, leaving `mode` as it is for now:

```toml
lan_range = "192.168.1.0/24"   # who may connect; must be a private network
lan_address = "192.168.1.50"   # this machine, inside lan_range
```

Then:

```sh
mulebox dashboard password                     # asks twice; at least 10 characters
mulebox dashboard firewall > firewall.sh       # read it, then:
sudo sh firewall.sh
```

Now set `mode = "lan"` and run `systemctl --user restart mulebox-dashboard`. If a step is
missing, the service stops and says which: see `journalctl --user -u mulebox-dashboard`.

The firewall script adds one nftables table that only affects the dashboard's port, and a root unit,
`mulebox-dashboard-firewall`, that loads it at boot. If the port changes, run the two
firewall lines again. It leaves ufw, Docker, VPN clients and
SSH alone, and it is the only step that needs root. To remove it:

```sh
sudo systemctl disable --now mulebox-dashboard-firewall
sudo rm /etc/systemd/system/mulebox-dashboard-firewall.service
sudo rm /etc/mulebox/dashboard-firewall.nft
```

**Optional: HTTPS.** Set `lan_tls = true`, run `mulebox dashboard cert` and restart. To
avoid a browser warning on every visit, trust the certificate on each device: copy
`~/.config/mulebox/dashboard/cert.pem` there and compare its SHA-256 fingerprint with the
one the command printed.

- macOS: open it in Keychain Access, then set Trust to Always Trust.
- iPhone: install the profile, then turn it on in Settings > General > About > Certificate
  Trust Settings.
- Android: Settings > Security > More security settings > Install from device storage > CA
  certificate. The exact path differs by phone.

The device treats it as a certificate authority, the only kind phones fully trust, but it
is limited to this one address and cannot vouch for any other site. It lasts 825 days;
replace it with `mulebox dashboard cert --force`, then trust the new one on each device.
Trusting it on a phone has not been tried yet.

**Buttons.** A job's page has Cancel, Pause or Resume, To front, Up, Down, To end and Boost,
each waiting job in the Queue tab has the same four arrows, and each machine in
the Machines box has Pause or Resume, through the tunnel and at the LAN address alike (see
[Steering jobs and machines](#steering-jobs-and-machines)). To have a page that only shows, set
`controls = false` under `[dashboard]` and restart.

**Optional: no password.** On a network where you trust everyone, set `lan_password = false`
and restart; `mulebox dashboard password` is then not needed. The page opens directly for
any device in `lan_range`, and it still shows your job logs, so leave the password on
anywhere else. Set it back to `true` to bring sign-in back.

Changing the password: run `mulebox dashboard password`, then restart the service, which
signs everyone out. A session lasts 24 hours.
