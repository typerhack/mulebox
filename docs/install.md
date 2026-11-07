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
  python3-venv` if the installer asks for it.
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
you add `--when-idle`, which waits for them while new jobs wait in line, or `--now`.

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
pipx install git+https://github.com/example-org/mulebox
```

**As a binary**, for macOS on Apple silicon and Linux on x86-64. Take the file for your system from
the [releases page](https://github.com/example-org/mulebox/releases). Download it with `curl` as
below: the binaries are not signed, so macOS refuses a file a browser fetched. It is a folder,
because a single file took 10 s to start on macOS:

```sh
curl -fsSLO https://github.com/example-org/mulebox/releases/download/v1.0.0/mulebox-1.0.0-macos-arm64.tar.gz
mkdir -p ~/.local/share ~/.local/bin
tar xzf mulebox-1.0.0-macos-arm64.tar.gz -C ~/.local/share
ln -sf ~/.local/share/mulebox/mulebox ~/.local/bin/mulebox    # needs ~/.local/bin on your PATH
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

**Private repositories only.** Never attach a runner to a public repository: anyone can open a
pull request, and its workflow file comes from that pull request, so it can ask for your runner
whatever your own workflow says, and run its code on your build machine.
What a job can reach: [Security model](#security-model).

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

## Skill for coding agents

The package ships a skill that teaches a coding agent to work through mulebox in any project.
It is short on purpose: it sends the agent to `mulebox contract`. For Claude Code, install it
for all your projects:

```sh
mulebox skill install    # into every Claude config folder that exists here
mulebox skill status     # how each copy stands against this mulebox; changes nothing
mulebox skill update     # replace out-of-date copies, after upgrading mulebox
```

These cover `~/.claude`, `~/.claude-work` and the folder `CLAUDE_CONFIG_DIR` names, those that
exist; `--config-dir <folder>` names one instead, and may repeat. `update` replaces hand edits
in a copy, and leaves alone a skill folder that is a link. The skill says which contract schema
it was written for; when `mulebox contract` shows a higher one, the agent tells you, and
`mulebox doctor` reports it too. Agents never update it themselves.

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

**Optional: a cancel button.** Set `cancel_button = true` under `[dashboard]` and restart. A job's
page then has a `Cancel job` button for whoever signed in at the LAN address. It needs
`mode = "lan"` and a password: with `lan_password = false`, and through the tunnel, there is no
button, as nobody has signed in there. `mulebox cancel` works either way.

**Optional: no password.** On a network where you trust everyone, set `lan_password = false`
and restart; `mulebox dashboard password` is then not needed. The page opens directly for
any device in `lan_range`, and it still shows your job logs, so leave the password on
anywhere else. Set it back to `true` to bring sign-in back.

Changing the password: run `mulebox dashboard password`, then restart the service, which
signs everyone out. A session lasts 24 hours.
