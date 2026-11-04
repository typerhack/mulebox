"""Stands in for ssh: runs the mulebox command on this machine, against a temporary node.

Tests point `common.ssh.SSH_BINARY` at a wrapper of this file, so the real client talks to the
real coordinator code through the real process boundary, and no host is ever contacted.
`$LOCAL_NODE` is the node config; `$LOCAL_SSH_DOWN`, when that file exists, makes the
connection fail as a dropped ssh does. It is removed after `$LOCAL_SSH_DOWN_COUNT` failures.
"""

import os
import shlex
import sys


def down() -> bool:
    flag = os.environ.get("LOCAL_SSH_DOWN", "")
    if not flag or not os.path.exists(flag):
        return False
    with open(flag) as fh:
        left = int(fh.read() or "1")
    if left <= 1:
        os.unlink(flag)
    else:
        with open(flag, "w") as fh:
            fh.write(str(left - 1))
    return True


def main() -> None:
    if down():
        sys.stderr.write("ssh: connect to host build-1 port 22: Connection refused\n")
        os._exit(255)
    args = sys.argv[1:]
    command = shlex.split(args[args.index("--") + 1])[1:]
    if command[0].startswith("rpc"):
        command += ["--node-config", os.environ["LOCAL_NODE"]]
    os.execv(sys.executable, [sys.executable, "-m", "mulebox.cli", *command])


if __name__ == "__main__":
    main()
