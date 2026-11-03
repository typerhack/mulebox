# Installing mulebox

mulebox has two sides:

- **Build machine** (Linux with systemd, Ubuntu first): runs the coordinator (the queue)
  and a worker (runs the jobs) as two systemd user services. In M1 both run on one
  machine, for one user.
- **Laptop** (macOS or Linux): the `mulebox` client that agents call. It reaches the build
  machine over ssh.

Examples below use the build machine `build-1` and the user `alice`.

## Requirements

Build machine:

- Linux with systemd; `systemctl --user` must work for the user (log in over ssh or a
  desktop session; `su` does not start a user manager).
- Python 3.12 or newer with `venv` support. On Ubuntu/Debian: `sudo apt-get install
  python3-venv` if the installer asks for it.
- Network access to PyPI for mulebox's dependencies.

Laptop:

- Python 3.12 or newer, a clone of mulebox, and ssh access to the build machine with a key
  (an entry in `~/.ssh/config` such as `Host build-1` keeps commands short).

## 1. Install on the build machine

From the mulebox clone on the laptop:

```sh
python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'   # once
tools/deploy.sh build-1
```

`tools/deploy.sh` builds a wheel, copies it together with `install/install.sh`,
`install/node.toml.example` and `install/systemd/` into `~/.mulebox/tmp/` on the build
machine, runs the installer there and prints the installed version.

To install by hand instead, copy the same files into one folder on the build machine and
run `bash install.sh mulebox-<version>-py3-none-any.whl`.

What the installer does (it never uses sudo and never deletes a folder):

| Step | Result |
| --- | --- |
| Checks | Linux, `systemctl --user`, Python >= 3.12, a working `python3 -m venv` |
| venv | `~/.mulebox/venv`, rebuilt only when the Python minor version changed |
| Command | `~/.mulebox/bin/mulebox` (symlink into the venv) |
| Node config | `~/.config/mulebox/node.toml`, written once from the template, then validated |
| Roots | `~/.mulebox/{jobs,cache,staging,runners}`, mode 750 |
| Services | `~/.config/systemd/user/mulebox-coordinator.service` and `mulebox-worker.service`, enabled and started; `mulebox-runner@.service` copied only |
| Linger | prints how to enable it if it is off |

Set `MULEBOX_PYTHON=python3.12` (or another interpreter) before running the installer to
use a Python other than `python3`.

### Keep the services running after logout

Without lingering, systemd stops user services when your last session ends. Enable it once
(this is the one step that needs sudo, and you run it yourself):

```sh
sudo loginctl enable-linger alice
```

### Node config

`~/.config/mulebox/node.toml` (template: [install/node.toml.example](../install/node.toml.example)):

- `name`: the short hostname by default.
- `roles`: `["coordinator", "worker"]` in M1. The installer starts only the services of
  the roles listed here.
- `roots`: the only folders mulebox writes to and deletes in. They must be separate,
  absolute, and not a system folder or your home folder itself.
- `slots`, `capabilities`, `dashboard`: see [interfaces.md](interfaces.md).

The installer never overwrites this file. After editing it, check it and restart:

```sh
~/.mulebox/venv/bin/python -c 'from mulebox.common.config import load_node_config; print(load_node_config())'
systemctl --user restart mulebox-coordinator mulebox-worker
```

## 2. Configure the laptop

Install the client from the clone (or the same wheel) and point it at the build machine:

```sh
python3 -m pip install --user .       # or use the clone's .venv/bin/mulebox
mkdir -p ~/.config/mulebox
cp install/client.toml.example ~/.config/mulebox/client.toml
```

Edit `~/.config/mulebox/client.toml` (template:
[install/client.toml.example](../install/client.toml.example)):

```toml
coordinator = "build-1"                  # ssh target: Host alias or alice@192.168.1.50
remote_bin = "~/.mulebox/bin/mulebox"
connect_timeout_s = 10
```

`$MULEBOX_CONFIG` can name another file. Check the connection:

```sh
ssh build-1 '~/.mulebox/bin/mulebox --version'
mulebox queue
```

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

## Upgrade

Pull the new version on the laptop and deploy again:

```sh
git pull && tools/deploy.sh build-1
```

The installer reinstalls the wheel into the existing venv, updates the unit files and
restarts the services. A running job is interrupted by the restart (state `interrupted`,
never replayed); upgrade when the queue is empty (`mulebox queue`). `node.toml` is kept.
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

## Troubleshooting

| Problem | What to do |
| --- | --- |
| `Python cannot create virtual environments here` | `sudo apt-get install python3-venv` (or `python3.12-venv`), then rerun the installer |
| `Python 3.12 or newer is required` | install a newer Python and set `MULEBOX_PYTHON`, e.g. `MULEBOX_PYTHON=python3.12` |
| `'systemctl --user' does not work` | log in as the user over ssh or a desktop session; `su`/`sudo -u` sessions have no user manager |
| Services stop after logout or do not start at boot | `loginctl show-user alice -p Linger`; if `Linger=no`, run `sudo loginctl enable-linger alice` |
| Generated or edited `node.toml` does not validate | the error names the file and the field; fix it and rerun the installer |
| A service is not running | `systemctl --user status mulebox-worker mulebox-coordinator` |
| Job or worker errors | `journalctl --user -u mulebox-worker -e` and `journalctl --user -u mulebox-coordinator -e` |
| `pip` inside the venv | use `~/.mulebox/venv/bin/python -m pip ...` (the venv is built in a temp folder and moved, so its `bin/pip` script may point at the old path) |
| Old venvs and copied wheels pile up | everything in `~/.mulebox/tmp/` is safe to delete by hand |
