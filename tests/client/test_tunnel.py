import io

from mulebox.client import report, tunnel
from mulebox.common import ssh
from mulebox.common.config import ClientConfig


class FakeProc:
    def __init__(self, code=None, wait_raises=None):
        self.returncode, self.wait_raises = code, wait_raises
        self.stopped = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.wait_raises:
            raise self.wait_raises
        return self.returncode

    def terminate(self):
        self.stopped = True
        self.wait_raises = None
        self.returncode = -15

    kill = terminate


def config():
    return ClientConfig(coordinator="build-1", connect_timeout_s=1)


def opened(proc, probe, **extra):
    out, argvs, urls = io.StringIO(), [], []

    def popen(argv, **kwargs):
        argvs.append(argv)
        return proc
    times = iter(range(100))
    code = tunnel.open_dashboard(
        config(), 8090, 8091, out, popen=popen, probe=probe, opener=urls.append,
        clock=lambda: next(times), sleep=lambda s: None, **extra)
    return code, out.getvalue(), argvs, urls


def test_tunnel_argv_binds_both_ends_to_loopback():
    argv = ssh.tunnel_argv("build-1", 8090, 8091)
    assert "127.0.0.1:8090:127.0.0.1:8091" in argv
    assert "-N" in argv and "ExitOnForwardFailure=yes" in argv and argv[-1] == "build-1"


def test_opens_the_browser_and_ctrl_c_closes_the_tunnel():
    proc = FakeProc(wait_raises=KeyboardInterrupt())
    code, text, _, urls = opened(proc, lambda url: True)
    assert code == 0 and urls == ["http://127.0.0.1:8090"]
    assert proc.stopped and "dashboard at http://127.0.0.1:8090" in text


def test_no_browser_only_prints():
    proc = FakeProc(wait_raises=KeyboardInterrupt())
    _, _, _, urls = opened(proc, lambda url: True, browser=False)
    assert urls == []


def test_busy_local_port_is_explained():
    code, text, _, urls = opened(FakeProc(code=255), lambda url: False)
    assert code == report.EXIT_UNREACHABLE and urls == []
    assert "port 8090 in use" in text


def test_a_dashboard_that_never_answers_is_explained():
    proc = FakeProc()
    code, text, _, urls = opened(proc, lambda url: False)
    assert code == report.EXIT_UNREACHABLE and urls == []
    assert "mulebox-dashboard" in text and proc.stopped
