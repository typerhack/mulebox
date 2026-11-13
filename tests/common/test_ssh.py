"""Tests for mulebox.common.ssh. They never contact a real host.

Most tests point SSH_BINARY at a fake ssh script in tmp_path. The fake records its argv,
simulates a connection failure on request, and otherwise runs the single remote command
string with /bin/sh, exactly as sshd hands it to the remote user's shell. That makes the
quoting tests end to end: what the remote program sees is what we sent.
"""

import json
import subprocess
import sys
import time

import pytest

from mulebox.common import ssh
from mulebox.common.ssh import RemoteError, RemoteTimeout, SSHError, SSHUnavailable

FAKE_SSH = f"""#!{sys.executable}
import json, os, sys
args = sys.argv[1:]
log = os.environ.get("FAKE_SSH_LOG")
if log:
    with open(log, "w") as fh:
        json.dump(args, fh)
if os.environ.get("FAKE_SSH_DOWN"):
    sys.stderr.write("ssh: connect to host build-1 port 22: Connection refused\\n")
    sys.exit(255)
command = args[args.index("--") + 1:]
if len(command) != 1:
    sys.exit("fake ssh: expected exactly one command string")
os.execv("/bin/sh", ["/bin/sh", "-c", command[0]])
"""

PY = sys.executable
NASTY = [
    "two words",
    "it's",
    '"double"',
    "$(touch PWNED)",
    "`touch PWNED`",
    "; touch PWNED",
    "&& touch PWNED",
    "| touch PWNED",
    "> PWNED",
    "$HOME",
    "~",
    "*",
    "back\\slash",
    "new\nline",
    "tab\there",
    "",
    "-n",
    "--",
    "café",
]


@pytest.fixture
def fake_ssh(tmp_path, monkeypatch):
    script = tmp_path / "fake-ssh"
    script.write_text(FAKE_SSH)
    script.chmod(0o755)
    log = tmp_path / "ssh-argv.json"
    monkeypatch.setattr(ssh, "SSH_BINARY", str(script))
    monkeypatch.setenv("FAKE_SSH_LOG", str(log))
    monkeypatch.delenv("FAKE_SSH_DOWN", raising=False)
    monkeypatch.chdir(tmp_path)
    return log


def py(code: str, *args: str) -> list[str]:
    return [PY, "-c", code, *args]


# --- argv construction and validation -------------------------------------------------


def test_base_argv_matches_contract():
    assert ssh.ssh_base_argv("build-1") == [
        "ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3", "build-1",
    ]  # the keepalive: a node gone mid-job fails the call in ~30 s, not 10+ min
    assert "ConnectTimeout=3" in ssh.ssh_base_argv("alice@build-1", 3)


@pytest.mark.parametrize(
    "target", ["", "-oProxyCommand=touch PWNED", "-v", "build 1", "build-1\n", "a\tb"]
)
def test_bad_targets_are_rejected(target):
    with pytest.raises(SSHError):
        ssh.ssh_base_argv(target)
    with pytest.raises(SSHError):
        ssh.run_remote(target, ["true"])


def test_option_like_target_error_explains_why():
    with pytest.raises(SSHError, match="option"):
        ssh.ssh_base_argv("-oProxyCommand=x")


@pytest.mark.parametrize("value", [0, -1, True, 2.5, "10"])
def test_bad_connect_timeout_is_rejected(value):
    with pytest.raises(SSHError):
        ssh.ssh_base_argv("build-1", value)


@pytest.mark.parametrize("argv", [[], (), "mulebox rpc", ["mulebox", 1], ["a\0b"]])
def test_bad_argv_is_rejected_before_running(argv, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("ssh was started"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("ssh was started"))
    with pytest.raises(SSHError):
        ssh.run_remote("build-1", argv)
    with pytest.raises(SSHError):
        ssh.stream_remote("build-1", argv)  # validated eagerly, not on first next()


def test_run_remote_uses_argument_list_without_shell(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, b"out", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    argv = ["~/.mulebox/bin/mulebox", "rpc", "$(touch PWNED)"]
    result = ssh.run_remote("build-1", argv, stdin=b'{"v": 1}', timeout_s=7)
    cmd, kwargs = calls[0]
    assert cmd == ssh.ssh_base_argv("build-1") + ["--", ssh.shlex.join(argv)]
    assert cmd[-1] == "'~/.mulebox/bin/mulebox' rpc '$(touch PWNED)'"
    assert "shell" not in kwargs
    assert kwargs["input"] == b'{"v": 1}' and kwargs["timeout"] == 7
    assert result == ssh.RemoteResult(0, b"out", b"")


def test_run_remote_without_stdin_uses_devnull(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ssh.run_remote("build-1", ["true"])
    assert seen["stdin"] is subprocess.DEVNULL and "input" not in seen


# --- run_remote through the fake ssh ---------------------------------------------------


def test_nasty_arguments_arrive_unchanged(fake_ssh, tmp_path):
    code = "import json, sys; print(json.dumps(sys.argv[1:]))"
    result = ssh.run_remote("build-1", py(code, *NASTY))
    assert json.loads(result.stdout) == NASTY
    assert not (tmp_path / "PWNED").exists()
    logged = json.loads(fake_ssh.read_text())
    base = ssh.ssh_base_argv("build-1")[1:] + ["--"]
    assert logged[:len(base)] == base


def test_run_remote_passes_stdin_and_collects_output(fake_ssh):
    code = "import sys; d = sys.stdin.buffer.read(); sys.stdout.buffer.write(d[::-1]); sys.stderr.write('note')"
    result = ssh.run_remote("build-1", py(code), stdin=b"abc\x00def")
    assert result == ssh.RemoteResult(0, b"fed\x00cba", b"note")


def test_connection_failure_raises_ssh_unavailable(fake_ssh, monkeypatch):
    monkeypatch.setenv("FAKE_SSH_DOWN", "1")
    with pytest.raises(SSHUnavailable) as info:
        ssh.run_remote("build-1", ["true"], check=False)
    message = str(info.value)
    assert "build-1" in message and "`ssh build-1` works" in message
    assert "Connection refused" in message


def test_remote_failure_raises_remote_error(fake_ssh):
    code = "import sys; sys.stderr.write('boom\\n'); sys.exit(3)"
    with pytest.raises(RemoteError) as info:
        ssh.run_remote("build-1", py(code))
    assert info.value.exit_code == 3
    assert info.value.stderr == b"boom\n"
    assert "exit code 3" in str(info.value) and "boom" in str(info.value)


def test_remote_error_message_truncates_long_stderr(fake_ssh):
    code = "import sys; sys.stderr.write('x' * 10000 + 'TAIL'); sys.exit(1)"
    with pytest.raises(RemoteError) as info:
        ssh.run_remote("build-1", py(code))
    assert len(info.value.stderr) == 10004
    message = str(info.value)
    assert len(message) < ssh.MESSAGE_STDERR_CHARS + 200
    assert message.endswith("TAIL")


def test_check_false_returns_nonzero_result(fake_ssh):
    result = ssh.run_remote("build-1", py("import sys; sys.exit(4)"), check=False)
    assert result.exit_code == 4


def test_timeout_kills_and_raises(fake_ssh):
    start = time.monotonic()
    with pytest.raises(RemoteTimeout, match="did not finish within 0.5 s"):
        ssh.run_remote("build-1", py("import time; time.sleep(30)"), timeout_s=0.5)
    assert time.monotonic() - start < 10


def test_missing_ssh_binary_raises_ssh_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(ssh, "SSH_BINARY", str(tmp_path / "no-such-ssh"))
    with pytest.raises(SSHUnavailable, match="cannot start ssh"):
        ssh.run_remote("build-1", ["true"])
    with pytest.raises(SSHUnavailable):
        list(ssh.stream_remote("build-1", ["true"]))


# --- stream_remote ------------------------------------------------------------------


def test_stream_yields_lines_in_order(fake_ssh):
    code = "import sys; sys.stdout.write('one\\ntwo\\nlast-no-newline')"
    assert list(ssh.stream_remote("build-1", py(code))) == [b"one\n", b"two\n", b"last-no-newline"]


def test_stream_yields_lines_as_they_arrive(fake_ssh, tmp_path):
    gate = tmp_path / "gate"
    code = (
        "import os, sys, time\n"
        "print('first', flush=True)\n"
        f"while not os.path.exists({str(gate)!r}): time.sleep(0.01)\n"
        "print('second', flush=True)\n"
    )
    lines = ssh.stream_remote("build-1", py(code))
    assert next(lines) == b"first\n"  # would hang if output were buffered until exit
    gate.touch()
    assert list(lines) == [b"second\n"]


def test_stream_quotes_nasty_arguments(fake_ssh, tmp_path):
    code = "import json, sys; print(json.dumps(sys.argv[1:]))"
    (line,) = ssh.stream_remote("build-1", py(code, *NASTY))
    assert json.loads(line) == NASTY
    assert not (tmp_path / "PWNED").exists()


def test_stream_feeds_large_stdin(fake_ssh):
    data = b"".join(b"line %d\n" % i for i in range(200_000))
    lines = list(ssh.stream_remote("build-1", ["cat"], stdin=data))
    assert b"".join(lines) == data


def test_stream_survives_large_stderr(fake_ssh):
    code = (
        "import sys\n"
        "for i in range(2000):\n"
        "    sys.stderr.write('e' * 1000 + '\\n'); sys.stdout.write('%d\\n' % i)\n"
        "sys.stderr.flush(); sys.exit(2)\n"
    )
    lines = []
    with pytest.raises(RemoteError) as info:
        for line in ssh.stream_remote("build-1", py(code)):
            lines.append(line)
    assert len(lines) == 2000
    assert info.value.exit_code == 2
    assert len(info.value.stderr) == ssh.STDERR_KEEP_BYTES  # only the tail is kept


def test_stream_raises_after_yielding_on_failure(fake_ssh):
    code = "import sys; print('partial'); sys.stderr.write('bad'); sys.exit(5)"
    stream = ssh.stream_remote("build-1", py(code))
    assert next(stream) == b"partial\n"
    with pytest.raises(RemoteError, match="exit code 5") as info:
        next(stream)
    assert info.value.stderr == b"bad"


def test_stream_connection_failure(fake_ssh, monkeypatch):
    monkeypatch.setenv("FAKE_SSH_DOWN", "1")
    with pytest.raises(SSHUnavailable, match="`ssh build-1` works"):
        list(ssh.stream_remote("build-1", ["true"]))


def test_stream_early_stop_reaps_process(fake_ssh, monkeypatch):
    procs = []
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        procs.append(proc)
        return proc

    monkeypatch.setattr(subprocess, "Popen", recording_popen)
    code = "import time\nwhile True:\n    print('tick', flush=True); time.sleep(0.01)\n"
    stream = ssh.stream_remote("build-1", py(code), stdin=b"unused")
    assert next(stream) == b"tick\n"
    stream.close()
    assert procs[0].returncode is not None
    # stdout is ours and always closed. stderr may stay open while its reader thread still
    # waits on it (another process can hold the pipe); reap leaves it to that thread rather
    # than block the caller (0.5.1). Seen on Linux, where the fake ssh's child outlives it.
    assert procs[0].stdout.closed


def test_ssh_killed_by_a_signal_counts_as_connection_lost():
    with pytest.raises(SSHUnavailable, match="signal 9"):
        ssh.raise_for_exit("build-1", ["mulebox", "rpc"], -9, b"")
