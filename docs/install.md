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
- `slots`, `capabilities`: see [interfaces.md](interfaces.md). A project's `needs` must be
  in `capabilities` of some worker, or its jobs are refused with that message. Add `docker`
  on a machine with Docker Engine and Compose v2 whose user is in the `docker` group, to
  run `compose:` projects, then restart the worker. mulebox fetches one small helper image
  the first time, and never removes images.
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

## Using the dashboard

From the laptop:

```sh
mulebox dashboard open                 # opens the browser; Ctrl-C closes the tunnel
mulebox dashboard open --no-browser    # only prints the URL
mulebox dashboard open --port 8091     # if local port 8090 is taken
```

If `[dashboard] port` was changed in `node.toml`, pass the same value as `--remote-port`.
Nothing but the SSH connection is exposed: the page is reached only through the tunnel.

### Skill for coding agents

`skills/mulebox/` in this repository is a skill that teaches a coding agent to work through
mulebox in any project. It is short on purpose: it sends the agent to `mulebox contract`.
For Claude Code, install it for all your projects by copying the folder:

```sh
cp -R skills/mulebox ~/.claude/skills/
```

Agents without skills can read [agents.md](agents.md) instead.

### Dashboard on the LAN

`lan` mode lets other devices, such as a phone, open the dashboard directly at
`http://<address>:8443`, with a password unless you turn it off (below). The tunnel above
keeps working. Reserve the
machine's address on your router first, so that it stays the same.

This is plain HTTP: the password and everything on the page cross your network
unencrypted, and browsers mark the page "Not secure". That is fine on a network where you
trust everyone. On an office or shared network, use the tunnel, or HTTPS (below).

On the build machine, add to `[dashboard]` in `node.toml`, leaving `mode` as it is for now:

```toml
lan_range = "192.168.1.0/24"   # who may connect; must be a private network
lan_address = "192.168.1.50"   # this machine, inside lan_range
lan_port = 8443                # optional
```

Then:

```sh
mulebox dashboard password                     # asks twice; at least 10 characters
mulebox dashboard firewall > firewall.sh       # read it, then:
sudo sh firewall.sh
```

Now set `mode = "lan"` and run `systemctl --user restart mulebox-dashboard`. If a step is
missing, the service stops and says which: see `journalctl --user -u mulebox-dashboard`.

The firewall script adds one nftables table that only affects `lan_port`, and a root unit,
`mulebox-dashboard-firewall`, that loads it at boot. It leaves ufw, Docker, VPN clients and
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

**Optional: no password.** On a network where you trust everyone, set `lan_password = false`
and restart; `mulebox dashboard password` is then not needed. The page opens directly for
any device in `lan_range`, and it still shows your job logs, so leave the password on
anywhere else. Set it back to `true` to bring sign-in back.

Changing the password: run `mulebox dashboard password`, then restart the service, which
signs everyone out. A session lasts 24 hours.
