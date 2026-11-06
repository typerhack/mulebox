# Troubleshooting

Start with `mulebox doctor` in the project's folder: it changes nothing, and it says whether the
file, the machine and the connection are fine. A failed job ends with a short summary, so read
the end of its output first; `mulebox logs <job-id> --summary` shows it again. What each exit
code means: [agents.md, section 1](agents.md#1-everyday-use-project-already-set-up).

## Connecting

| What you see | What to do |
| --- | --- |
| `client.toml: file not found` | The laptop is not set up: [install.md, section 2](install.md#2-install-on-the-laptop) |
| `build machine unreachable: cannot connect to build-1 over ssh` (exit 3) | Run `ssh build-1 true`. It must succeed and ask nothing. mulebox's ssh never prompts, so log in once by hand to accept the host key, and load a key with a passphrase into your ssh agent. Check `coordinator` in `client.toml` too: the template's `build-1` is an example |
| `node.toml: file not found` from `mulebox toolchain` on the laptop | That command belongs to the build machine: run it there, [install.md, Toolchains](install.md#toolchains) |
| `mulebox doctor` warns that client and build machine differ | Upgrade the older side: [install.md, Upgrade](install.md#upgrade) |

## Setting up a project

| What you see | What to do |
| --- | --- |
| `no .mulebox.yml here or in any parent directory` (exit 2) | Run it from the project, or write the file: [getting-started.md](getting-started.md#3-set-up-the-project) |
| `is not inside a git worktree` (exit 2) | mulebox uploads the files git knows about, so the project needs `git init` |
| `has no commits yet` (exit 2) | Commit once, then run it again. The job records the commit it came from |
| `no build machine offers docker` or another need (exit 4) | A person adds it to `capabilities` in `node.toml` and restarts the worker: [install.md, Node config](install.md#node-config) |
| `toolchain node ... is not installed on this worker` (exit 5) | Install that version on the build machine, or pin one it lists: [install.md, Toolchains](install.md#toolchains) |
| `snapshot is ... over the 1 GiB upload limit` | Add generated folders to `.gitignore`, or to `exclude` in `.mulebox.yml` |

## Jobs

| What you see | What to do |
| --- | --- |
| The job fails on the build machine and passes on the laptop | The usual causes: a file git ignores or a `.env` file, which are not uploaded; a tool that is only in your login shell's `PATH` (`command not found`, exit 127, and see [getting-started.md, section 2](getting-started.md#2-decide-where-the-projects-tools-come-from)); or macOS against Linux, such as the case of a file name |
| `queued, position 1; waiting: no build machine for this job is online` | Nothing starts until the worker is back: see the build machine section below |
| Waiting with no such line | Normal: there is one line for everyone. `mulebox queue` shows it. Use `--detach` to go on working |
| `stale` warning at the end | You edited files while it ran. The result belongs to the upload, so run it again |
| Exit 75, `interrupted` | The build machine restarted or the worker died. Run it again once |
| Exit 76, `stopped: stuck` | The job did nothing and nobody answered its question. It says nothing about your code: find what hangs, and run it again. |
| A job's log has expired | Logs are kept for 30 days by default: [install.md, Node config](install.md#node-config) |
| Containers refused, ports or caches behave oddly | [agents.md, 2a](agents.md#2a-projects-that-need-containers-compose) lists what is refused and why, and how ports and caches work |

## The build machine

| Problem | What to do |
| --- | --- |
| `git is required` | `sudo apt-get install git` on the machine, then run the same `mulebox setup` again |
| `Python cannot create virtual environments here` | `sudo apt-get install python3-venv` (or `python3.12-venv`), then rerun the installer |
| `Python 3.12 or newer is required` | install a newer Python and set `MULEBOX_PYTHON`, e.g. `MULEBOX_PYTHON=python3.12` |
| `'systemctl --user' does not work` | log in as the user over ssh or a desktop session; `su`/`sudo -u` sessions have no user manager |
| Services stop after logout or do not start at boot | `loginctl show-user alice -p Linger`; if `Linger=no`, run `sudo loginctl enable-linger alice` |
| Generated or edited `node.toml` does not validate | the error names the file and the field; fix it and rerun the installer |
| A service is not running | `systemctl --user status mulebox-worker mulebox-coordinator` |
| Job or worker errors | `journalctl --user -u mulebox-worker -e` and `journalctl --user -u mulebox-coordinator -e` |
| `pip` inside the venv | use `~/.mulebox/venv/bin/python -m pip ...` (the venv is built in a temp folder and moved, so its `bin/pip` script may point at the old path) |
| Old venvs and copied wheels pile up | everything in `~/.mulebox/tmp/` is safe to delete by hand |
| `compose:` services cannot reach each other (`Host is unreachable`), or a published port resets, while `docker0` containers work | NetworkManager is managing Docker's `br-*` bridges and detaches their ports. Check with `journalctl -u NetworkManager \| grep detached`; `docker network create` with no mulebox shows the same thing. Fix, as root: put `[keyfile]` and `unmanaged-devices=interface-name:br-*;interface-name:veth*` in a file in `/etc/NetworkManager/conf.d/` and reload NetworkManager. New bridges then work; profiles left from before do no harm |
| npm, pnpm or `node` fail with `ETIMEDOUT` after about 3 s while `curl` reaches the same address | connections take longer than Node's limit per address (250 ms), as they can over a VPN or a slow network. Add `NODE_OPTIONS = "--network-family-autoselection-attempt-timeout=5000"` under `[job_env]` in `node.toml` and restart the worker |

## Reporting a problem

`mulebox feedback draft <job-id> --summary "what happened"` writes a report with personal details
removed and sends nothing. Read it before you share it: [agents.md, section 4](agents.md#4-reporting-what-mulebox-could-not-handle).
