"""Every error code mulebox prints, with its exit code, meaning and default fix: one table.

design.md, Errors with a code and a fix. Codes are dotted words, `area.what`. A released code
is never renamed or reused; a new case gets a new code. docs/agents.md and `mulebox contract`
are made from this table, and tests/common/test_error_codes.py ties every code the code names
to it. The exit codes are the contract's (client/report.py); a code refines one, never
replaces it.
"""

from __future__ import annotations

from dataclasses import dataclass

USAGE, UNREACHABLE, REFUSED, FAILED, NOT_STARTED = 2, 3, 4, 1, 5


@dataclass(frozen=True)
class Code:
    name: str
    exit: int
    meaning: str
    fix: str


_ALL = (
    Code("config.missing", USAGE, "no .mulebox.yml here or in a folder above",
         "`mulebox init` writes one for this project"),
    Code("config.invalid", USAGE, ".mulebox.yml is not valid",
         "correct the key the message names; `mulebox doctor` checks the whole file"),
    Code("config.client", USAGE, "this dev machine's client.toml is missing or not valid",
         "`mulebox setup <host>` writes it; or correct the key the message names"),
    Code("usage.invalid", USAGE, "the command was not used as it can be",
         "`mulebox <command> --help` shows how"),
    Code("project.snapshot", USAGE, "the worktree could not be packed for the node",
         "run it in the project's git worktree, after its first commit"),
    Code("project.not_git", USAGE, "the folder is not in a git worktree",
         "run it in the project's git checkout"),
    Code("project.no_commit", USAGE, "the repository has no commit yet",
         "commit once, then run it again"),
    Code("project.too_large", USAGE, "the worktree is over the node's upload limit",
         "leave build output and data out of git (.gitignore), or name them in `exclude:`"),
    Code("node.unreachable", UNREACHABLE, "the node did not answer; the job was not run",
         "`mulebox doctor`, then ask your user to check that the node is on and reachable"),
    Code("node.timeout", UNREACHABLE, "the node took too long to answer",
         "run it again; if it keeps happening, `mulebox doctor`"),
    Code("node.connection_lost", UNREACHABLE,
         "the live view lost the node; the job goes on there",
         "`mulebox wait <job-id>` gets its result"),
    Code("node.protocol", REFUSED, "the node's answer could not be read",
         "`mulebox doctor` compares the versions; `mulebox setup <host>` brings the node up"),
    Code("node.refused", REFUSED, "the node refused the request",
         "read the message; if it is not clear, tell your user"),
    Code("node.too_old", REFUSED, "the node's mulebox is too old for what was asked",
         "`mulebox setup <host>` upgrades it to this dev machine's mulebox"),
    Code("node.internal", REFUSED, "the node failed on the request",
         "run it again once; if it fails again, `mulebox feedback guide`"),
    Code("request.invalid", REFUSED, "the node found the request not valid",
         "`mulebox <command> --help`; if the command is right, `mulebox feedback guide`"),
    Code("request.not_found", REFUSED, "what the request names does not exist on the node",
         "check the name: `mulebox queue` lists jobs, `mulebox machine list` nodes, "
         "`mulebox projects` projects"),
    Code("request.conflict", REFUSED, "the request does not fit the state it found",
         "`mulebox queue` shows the state now; try again once it changed"),
    Code("request.too_large", REFUSED, "the request is over the node's size limit",
         "send less: fewer or smaller files"),
    Code("job.not_found", REFUSED, "the node has no job with that id",
         "`mulebox queue` lists the jobs; an id is printed by `check --detach`"),
    Code("job.no_files", REFUSED, "the job has no kept files to fetch",
         "name them with `keep:` in .mulebox.yml or `--keep <path>`, then run the job again; "
         "kept files stay 7 days (`files_days`)"),
    Code("job.no_node", REFUSED, "no node offers what the job needs, so it would wait forever",
         "`mulebox doctor` shows what each node offers; change `needs:`, or ask your user "
         "to set a node up for it"),
    Code("job.too_big", REFUSED, "no node has room for the job's `size:`",
         "lower `size:` in .mulebox.yml; `mulebox machine list` shows each node's cores"),
    Code("node.unknown", REFUSED, "no node has that name",
         "`mulebox machine list` names the nodes"),
    Code("setup.failed", FAILED, "setting up or upgrading the node did not finish",
         "fix what the message names and run the same `mulebox setup` again"),
    Code("feedback.failed", USAGE, "the feedback draft or post could not be made",
         "read the message; `mulebox feedback guide` has the steps"),
    # A job that could not start (exit 5): the worker's last word in its log (common/start_note.py).
    Code("start.failed", NOT_STARTED, "the node could not start the job; no project code ran",
         "run it again; if it fails the same way, `mulebox machine check <node>`"),
    Code("toolchain.failed", NOT_STARTED, "a pinned toolchain is missing or would not install",
         "pin a version the node has (the log lists them), or check that the version exists"),
    Code("compose.refused", NOT_STARTED, "the node refuses something in the compose files",
         "`mulebox doctor` shows what the node refuses; change the compose files"),
    Code("docker.failed", NOT_STARTED, "a Docker command failed on the node",
         "`mulebox machine check <node>`; if Docker is down, ask your user to start it there"),
    Code("images.unreachable", NOT_STARTED, "the node could not fetch an image over the network",
         "ask your user to check the node's network; `mulebox doctor` checks the registries"),
    Code("install.failed", NOT_STARTED, "the project's `install:` failed, so its code did not run",
         "read the install output above it; fix the lockfile or the `install:` line"),
    Code("xcode.missing", NOT_STARTED, "the Xcode a job pins is not on the Mac node",
         "`mulebox doctor` lists each Mac's Xcodes; pin one of them with `xcode:`"),
    Code("simulator.missing", NOT_STARTED, "no simulator runtime the job asks for is on the node",
         "`mulebox doctor` lists the runtimes; pin one of them"),
    Code("download.failed", NOT_STARTED, "a download the job needs failed",
         "run it again; if it repeats, ask your user to check the node's network"),
    Code("job.spec", NOT_STARTED, "the node could not use the job's settings",
         "`mulebox doctor` checks .mulebox.yml against the node"),
    Code("job.workspace", NOT_STARTED, "the node could not set up the job's folder",
         "run it again; if it repeats, `mulebox machine check <node>`"),
    Code("job.executor", NOT_STARTED, "the node could not start the job's process",
         "`mulebox machine check <node>`; ask your user for `mulebox service logs worker` there"),
    # The node's own commands and services, read by its owner.
    Code("node.config", USAGE, "this node's node.toml is missing or not valid",
         "correct the key the message names in node.toml; `mulebox setup <host>` from a dev "
         "machine writes it"),
    Code("node.store", USAGE, "the coordinator's store could not be opened",
         "`mulebox service status` on the node; `mulebox setup <host>` from a dev machine on "
         "the newest mulebox installs or upgrades it"),
    Code("node.unsafe_path", FAILED, "mulebox refused a path outside its roots or unsafe to touch",
         "nothing to force: mulebox only writes inside its roots; `mulebox feedback guide` if a "
         "path of its own was refused"),
    Code("service.failed", FAILED, "a mulebox service could not be installed or controlled",
         "`mulebox service status` and `mulebox service logs <name>` show why"),
    Code("worker.link", FAILED, "the worker could not reach its coordinator",
         "check `coordinator` in node.toml and that `ssh <coordinator>` works from this node"),
    Code("worker.key_refused", USAGE, "a worker key asked for something it may not do",
         "a worker key runs only `mulebox rpc`; set the worker up again with "
         "`mulebox setup <worker> --worker-of <coordinator>`"),
    Code("worker.key_invalid", USAGE, "the worker's name or public key is not valid",
         "give its name and one ssh public key line (`ssh-ed25519 AAAA...`) on stdin"),
    Code("dashboard.lan", USAGE, "the dashboard's LAN mode is not ready",
         "set `lan_range` and `lan_address` under [dashboard] in node.toml"),
    Code("dashboard.listen", FAILED, "the dashboard could not listen on its address",
         "the service tries again by itself; if it keeps failing, another program holds the "
         "port: `mulebox service logs dashboard`"),
    Code("runner.usage", USAGE, "the runner command was not used as it can be",
         "`mulebox runner <command> --help` shows how"),
    Code("runner.failed", FAILED, "a runner operation failed on the node",
         "`mulebox runner list`; `mulebox service logs worker` on the node shows why"),
    Code("runner.download", FAILED, "the GitHub runner could not be downloaded or checked",
         "run it again; if it repeats, ask your user to check the node's network"),
    Code("runner.place", FAILED, "an isolated runner's container could not be made or run",
         "`mulebox machine check <node>`; Docker must answer on the node"),
    Code("runner.refused_run", FAILED, "the runner refused a run not from its own accounts",
         "nothing on this runner: such a run belongs on GitHub's machines"),
    Code("github.failed", REFUSED, "`gh` or GitHub refused or could not answer",
         "`gh auth status` shows the login; the account must be an admin of the repository"),
    Code("hook.failed", FAILED, "a runner hook could not hold a build slot",
         "re-run the job on GitHub; `mulebox service logs worker` on the node shows why"),
    Code("hook.refused", FAILED, "the coordinator refused the runner's slot",
         "`mulebox queue` and `mulebox machine list` show what the node holds; re-run the job"),
    Code("hook.ended", FAILED, "the runner's reservation ended before it got a slot",
         "re-run the job on GitHub; `mulebox queue` shows what ended it"),
    Code("hook.timeout", FAILED, "the runner waited too long for a build slot",
         "`mulebox queue` shows what holds the slots; raise MULEBOX_HOOK_TIMEOUT_MIN if it "
         "should wait longer"),
    Code("mulebox.internal", FAILED, "mulebox failed in a way it did not expect",
         "run it again with MULEBOX_DEBUG=1 for the trace, then `mulebox feedback guide`"),
)
CODES: dict[str, Code] = {code.name: code for code in _ALL}

# The node's wire codes (interfaces-m1.md), as a reply from a coordinator older than 1.44 has
# only these: each read as the code it stands for.
FROM_WIRE = {"not_found": "request.not_found", "bad_request": "request.invalid",
             "conflict": "request.conflict", "no_worker": "job.no_node",
             "too_large": "request.too_large", "internal": "node.internal"}


def fix_for(name: str) -> str:
    return CODES[name].fix if name in CODES else CODES["mulebox.internal"].fix
