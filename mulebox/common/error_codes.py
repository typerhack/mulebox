"""Every error code mulebox prints, with its exit code, meaning and default fix: one table.

design.md, Errors with a code and a fix. Codes are dotted words, `area.what`. A released code
is never renamed or reused; a new case gets a new code. docs/agents.md and `mulebox contract`
are made from this table, and tests/common/test_error_codes.py ties every code the code names
to it. The exit codes are the contract's (client/report.py); a code refines one, never
replaces it.
"""

from __future__ import annotations

from dataclasses import dataclass

USAGE, UNREACHABLE, REFUSED, FAILED = 2, 3, 4, 1


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
